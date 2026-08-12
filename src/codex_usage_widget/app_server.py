from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QProcess, QTimer, QUrl, Signal

from codex_usage_widget import __version__
from codex_usage_widget.models import ConnectionState, UsageSnapshot
from codex_usage_widget.parser import parse_rate_limits

MIN_CODEX_VERSION = (0, 147, 0)
RESTART_DELAYS_MS = (1_000, 2_000, 5_000, 10_000, 30_000)
REQUEST_TIMEOUT_MS = 15_000

SuccessCallback = Callable[[Mapping[str, Any]], None]
ErrorCallback = Callable[[str], None]


@dataclass(slots=True)
class PendingRequest:
    method: str
    callback: SuccessCallback | None
    errback: ErrorCallback | None
    timer: QTimer


class JsonLineBuffer:
    """Incrementally split UTF-8 JSONL without assuming process read boundaries."""

    def __init__(self) -> None:
        self._buffer = bytearray()

    def feed(self, data: bytes) -> list[Mapping[str, Any]]:
        self._buffer.extend(data)
        messages: list[Mapping[str, Any]] = []
        while True:
            newline = self._buffer.find(b"\n")
            if newline < 0:
                break
            raw_line = bytes(self._buffer[:newline]).rstrip(b"\r")
            del self._buffer[: newline + 1]
            if not raw_line:
                continue
            try:
                message = json.loads(raw_line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if isinstance(message, Mapping):
                messages.append(message)
        return messages

    def clear(self) -> None:
        self._buffer.clear()


def parse_codex_version(output: str) -> tuple[int, int, int] | None:
    match = re.search(r"(?<!\d)(\d+)\.(\d+)\.(\d+)(?!\d)", output)
    if not match:
        return None
    return tuple(int(group) for group in match.groups())  # type: ignore[return-value]


def find_codex_executable() -> str | None:
    executable = shutil.which("codex")
    return str(Path(executable).resolve()) if executable else None


def read_codex_version(executable: str) -> tuple[int, int, int] | None:
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    try:
        completed = subprocess.run(
            [executable, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
            creationflags=creation_flags,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return parse_codex_version(f"{completed.stdout}\n{completed.stderr}")


class CodexAppServerClient(QObject):
    state_changed = Signal(object)
    account_changed = Signal(object)
    usage_received = Signal(object)
    login_url_ready = Signal(QUrl)
    error_occurred = Signal(str)
    refreshing_changed = Signal(bool)
    diagnostic = Signal(str)

    def __init__(
        self,
        executable: str | None = None,
        *,
        app_server_args: list[str] | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._configured_executable = executable
        self._app_server_args = app_server_args
        self._executable: str | None = None
        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        self._process.started.connect(self._on_process_started)
        self._process.readyReadStandardOutput.connect(self._read_stdout)
        self._process.readyReadStandardError.connect(self._read_stderr)
        self._process.finished.connect(self._on_process_finished)
        self._process.errorOccurred.connect(self._on_process_error)

        self._line_buffer = JsonLineBuffer()
        self._pending: dict[int, PendingRequest] = {}
        self._next_request_id = 1
        self._state = ConnectionState.STOPPED
        self._initialized = False
        self._stopping = False
        self._refreshing = False
        self._restart_index = 0
        self._restart_scheduled = False

        self._periodic_refresh = QTimer(self)
        self._periodic_refresh.setInterval(60_000)
        self._periodic_refresh.timeout.connect(self.refresh)

        self._event_refresh = QTimer(self)
        self._event_refresh.setSingleShot(True)
        self._event_refresh.setInterval(250)
        self._event_refresh.timeout.connect(self.refresh)

        self._restart_timer = QTimer(self)
        self._restart_timer.setSingleShot(True)
        self._restart_timer.timeout.connect(self._restart_now)

    @property
    def state(self) -> ConnectionState:
        return self._state

    @property
    def executable(self) -> str | None:
        return self._executable

    def start(self) -> None:
        if self._process.state() != QProcess.ProcessState.NotRunning:
            return
        self._stopping = False
        self._restart_scheduled = False
        self._initialized = False
        self._line_buffer.clear()

        executable = self._configured_executable or find_codex_executable()
        if not executable:
            self._set_state(ConnectionState.MISSING_CLI)
            self.error_occurred.emit(
                "找不到 Codex CLI。請先安裝 Codex，並確認 codex 指令位於 PATH。"
            )
            return

        version = read_codex_version(executable)
        if version is None:
            self._set_state(ConnectionState.ERROR)
            self.error_occurred.emit("無法讀取 Codex CLI 版本。")
            return
        if version < MIN_CODEX_VERSION:
            self._set_state(ConnectionState.OUTDATED_CLI)
            current = ".".join(str(part) for part in version)
            minimum = ".".join(str(part) for part in MIN_CODEX_VERSION)
            self.error_occurred.emit(f"Codex CLI {current} 過舊；至少需要 {minimum}。")
            return

        self._executable = executable
        self._set_state(ConnectionState.STARTING)
        self._process.setProgram(executable)
        self._process.setArguments(self._app_server_args or ["app-server", "--listen", "stdio://"])
        self._process.start()

    def stop(self) -> None:
        self._stopping = True
        self._restart_timer.stop()
        self._periodic_refresh.stop()
        self._event_refresh.stop()
        self._fail_all_pending("應用程式正在結束")
        if self._process.state() != QProcess.ProcessState.NotRunning:
            self._process.terminate()
            if not self._process.waitForFinished(1_500):
                self._process.kill()
                self._process.waitForFinished(500)
        self._initialized = False
        self._set_refreshing(False)
        self._set_state(ConnectionState.STOPPED)

    def start_login(self) -> None:
        if not self._initialized:
            self.error_occurred.emit("app-server 尚未完成初始化。")
            return
        self._set_state(ConnectionState.AUTHENTICATING)
        self._send_request(
            "account/login/start",
            {
                "type": "chatgpt",
                "useHostedLoginSuccessPage": True,
                "appBrand": "codex",
            },
            callback=self._on_login_started,
            errback=self._on_login_failed,
        )

    def refresh(self) -> None:
        if not self._initialized or self._state not in {
            ConnectionState.READY,
            ConnectionState.ERROR,
        }:
            return
        if self._has_pending_method("account/rateLimits/read"):
            return
        self._set_refreshing(True)
        self._send_request(
            "account/rateLimits/read",
            callback=self._on_rate_limits,
            errback=self._on_rate_limits_failed,
        )

    def _on_process_started(self) -> None:
        self._set_state(ConnectionState.HANDSHAKING)
        self._send_request(
            "initialize",
            {
                "clientInfo": {
                    "name": "codex_usage_widget",
                    "title": "Codex Usage Widget",
                    "version": __version__,
                }
            },
            callback=self._on_initialized,
            errback=self._on_handshake_failed,
        )

    def _on_initialized(self, _result: Mapping[str, Any]) -> None:
        self._send_notification("initialized", {})
        self._initialized = True
        self._set_state(ConnectionState.CHECKING_ACCOUNT)
        self._read_account()

    def _on_handshake_failed(self, message: str) -> None:
        self.error_occurred.emit(f"無法初始化 Codex app-server：{message}")
        self._set_state(ConnectionState.ERROR)
        self._schedule_restart()

    def _read_account(self) -> None:
        if not self._initialized or self._has_pending_method("account/read"):
            return
        self._set_state(ConnectionState.CHECKING_ACCOUNT)
        self._send_request(
            "account/read",
            {"refreshToken": False},
            callback=self._on_account_read,
            errback=self._on_account_failed,
        )

    def _on_account_read(self, result: Mapping[str, Any]) -> None:
        account = result.get("account")
        account_mapping = account if isinstance(account, Mapping) else None
        self.account_changed.emit(dict(account_mapping) if account_mapping else None)

        if account_mapping is None:
            self._periodic_refresh.stop()
            self._set_state(ConnectionState.AUTH_REQUIRED)
            return

        account_type = account_mapping.get("type")
        supported = {
            "chatgpt",
            "chatgptAuthTokens",
            "agentIdentity",
            "personalAccessToken",
        }
        if account_type not in supported:
            self._periodic_refresh.stop()
            self._set_state(ConnectionState.AUTH_REQUIRED)
            self.error_occurred.emit("目前登入方式無法讀取 ChatGPT 用量，請改用 ChatGPT 登入。")
            return

        self._restart_index = 0
        self._set_state(ConnectionState.READY)
        self._periodic_refresh.start()
        self.refresh()

    def _on_account_failed(self, message: str) -> None:
        self._set_state(ConnectionState.ERROR)
        self.error_occurred.emit(f"無法讀取帳號狀態：{message}")

    def _on_login_started(self, result: Mapping[str, Any]) -> None:
        auth_url = result.get("authUrl")
        if not isinstance(auth_url, str) or not auth_url:
            self._on_login_failed("伺服器未回傳登入網址")
            return
        self.login_url_ready.emit(QUrl(auth_url))

    def _on_login_failed(self, message: str) -> None:
        self._set_state(ConnectionState.AUTH_REQUIRED)
        self.error_occurred.emit(f"無法開始 ChatGPT 登入：{message}")

    def _on_rate_limits(self, result: Mapping[str, Any]) -> None:
        self._set_refreshing(False)
        try:
            snapshot: UsageSnapshot = parse_rate_limits(result)
        except (TypeError, ValueError) as exc:
            self._on_rate_limits_failed(f"回應格式無法解析：{exc}")
            return
        self._set_state(ConnectionState.READY)
        self.usage_received.emit(snapshot)

    def _on_rate_limits_failed(self, message: str) -> None:
        self._set_refreshing(False)
        self._set_state(ConnectionState.ERROR)
        self.error_occurred.emit(f"無法更新用量：{message}")

    def _send_request(
        self,
        method: str,
        params: Mapping[str, Any] | None = None,
        *,
        callback: SuccessCallback | None = None,
        errback: ErrorCallback | None = None,
    ) -> int | None:
        if self._process.state() != QProcess.ProcessState.Running:
            if errback:
                errback("app-server 未執行")
            return None

        request_id = self._next_request_id
        self._next_request_id += 1
        message: dict[str, Any] = {"method": method, "id": request_id}
        if params is not None:
            message["params"] = dict(params)

        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.setInterval(REQUEST_TIMEOUT_MS)
        timer.timeout.connect(lambda request_id=request_id: self._request_timed_out(request_id))
        self._pending[request_id] = PendingRequest(method, callback, errback, timer)
        timer.start()
        self._write_message(message)
        return request_id

    def _send_notification(self, method: str, params: Mapping[str, Any]) -> None:
        self._write_message({"method": method, "params": dict(params)})

    def _write_message(self, message: Mapping[str, Any]) -> None:
        if self._process.state() != QProcess.ProcessState.Running:
            return
        payload = json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n"
        self._process.write(payload.encode("utf-8"))

    def _read_stdout(self) -> None:
        data = bytes(self._process.readAllStandardOutput())
        for message in self._line_buffer.feed(data):
            self._handle_message(message)

    def _read_stderr(self) -> None:
        raw = bytes(self._process.readAllStandardError()).decode("utf-8", errors="replace")
        if raw.strip():
            self.diagnostic.emit("Codex app-server 回報診斷訊息。")

    def _handle_message(self, message: Mapping[str, Any]) -> None:
        if "id" in message and "method" not in message:
            self._handle_response(message)
            return
        method = message.get("method")
        if not isinstance(method, str):
            return
        if "id" in message:
            self._write_message(
                {
                    "id": message["id"],
                    "error": {"code": -32601, "message": "Method not supported"},
                }
            )
            return
        params = message.get("params")
        self._handle_notification(method, params if isinstance(params, Mapping) else {})

    def _handle_response(self, message: Mapping[str, Any]) -> None:
        request_id = message.get("id")
        if not isinstance(request_id, int):
            return
        pending = self._pending.pop(request_id, None)
        if pending is None:
            return
        pending.timer.stop()
        pending.timer.deleteLater()

        error = message.get("error")
        if isinstance(error, Mapping):
            raw_message = error.get("message")
            text = raw_message if isinstance(raw_message, str) else "未知的 app-server 錯誤"
            if pending.errback:
                pending.errback(text[:500])
            return

        result = message.get("result")
        if pending.callback:
            pending.callback(result if isinstance(result, Mapping) else {})

    def _handle_notification(self, method: str, params: Mapping[str, Any]) -> None:
        if method == "account/rateLimits/updated":
            self._event_refresh.start()
            return
        if method == "account/login/completed":
            if params.get("success") is True:
                self._read_account()
            else:
                error = params.get("error")
                self._on_login_failed(error if isinstance(error, str) else "登入未完成")
            return
        if method == "account/updated" and self._state != ConnectionState.AUTHENTICATING:
            self._read_account()

    def _request_timed_out(self, request_id: int) -> None:
        pending = self._pending.pop(request_id, None)
        if pending is None:
            return
        pending.timer.deleteLater()
        if pending.errback:
            pending.errback(f"{pending.method} 等候回應逾時")

    def _has_pending_method(self, method: str) -> bool:
        return any(pending.method == method for pending in self._pending.values())

    def _fail_all_pending(self, message: str) -> None:
        pending_items = list(self._pending.values())
        self._pending.clear()
        for pending in pending_items:
            pending.timer.stop()
            pending.timer.deleteLater()
            if pending.errback:
                pending.errback(message)

    def _on_process_finished(self, _exit_code: int, _exit_status: QProcess.ExitStatus) -> None:
        self._initialized = False
        self._periodic_refresh.stop()
        self._set_refreshing(False)
        self._fail_all_pending("Codex app-server 已停止")
        if not self._stopping:
            self.error_occurred.emit("Codex app-server 已中斷，正在重新連線。")
            self._schedule_restart()

    def _on_process_error(self, _error: QProcess.ProcessError) -> None:
        if not self._stopping and self._process.state() == QProcess.ProcessState.NotRunning:
            self._schedule_restart()

    def _schedule_restart(self) -> None:
        if self._stopping or self._restart_scheduled:
            return
        self._restart_scheduled = True
        self._set_state(ConnectionState.RECONNECTING)
        delay = RESTART_DELAYS_MS[min(self._restart_index, len(RESTART_DELAYS_MS) - 1)]
        self._restart_index += 1
        self._restart_timer.start(delay)

    def _restart_now(self) -> None:
        self._restart_scheduled = False
        if not self._stopping:
            self.start()

    def _set_state(self, state: ConnectionState) -> None:
        if state == self._state:
            return
        self._state = state
        self.state_changed.emit(state)

    def _set_refreshing(self, refreshing: bool) -> None:
        if refreshing == self._refreshing:
            return
        self._refreshing = refreshing
        self.refreshing_changed.emit(refreshing)
