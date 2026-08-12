from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal

from claude_usage_widget.integration import IntegrationError, StatusLineIntegration
from claude_usage_widget.models import ConnectionState, UsageSnapshot
from claude_usage_widget.parser import parse_statusline_cache

MIN_CLAUDE_VERSION = (2, 1, 80)
STALE_AFTER_SECONDS = 5 * 60


def parse_claude_version(output: str) -> tuple[int, int, int] | None:
    match = re.search(r"(?<!\d)(\d+)\.(\d+)\.(\d+)(?!\d)", output)
    if not match:
        return None
    return tuple(int(group) for group in match.groups())  # type: ignore[return-value]


def _windows_environment_path() -> str:
    paths = [os.environ.get("PATH", "")]
    if os.name != "nt":
        return os.pathsep.join(filter(None, paths))
    try:
        import winreg

        locations = (
            (winreg.HKEY_CURRENT_USER, r"Environment"),
            (
                winreg.HKEY_LOCAL_MACHINE,
                r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
            ),
        )
        for hive, key_name in locations:
            try:
                with winreg.OpenKey(hive, key_name) as key:
                    value, _ = winreg.QueryValueEx(key, "Path")
            except OSError:
                continue
            if isinstance(value, str):
                paths.append(os.path.expandvars(value))
    except ImportError:
        pass
    return os.pathsep.join(filter(None, paths))


def find_claude_executable() -> str | None:
    configured = os.environ.get("CLAUDE_CODE_EXECUTABLE")
    if configured and Path(configured).is_file():
        return str(Path(configured).resolve())
    search_path = _windows_environment_path()
    names = ("claude.exe", "claude.cmd", "claude.bat", "claude.ps1", "claude")
    for name in names:
        executable = shutil.which(name, path=search_path)
        if executable:
            return str(Path(executable).resolve())
    return None


def command_for_claude(executable: str, *arguments: str) -> list[str]:
    suffix = Path(executable).suffix.lower()
    if os.name == "nt" and suffix in {".cmd", ".bat"}:
        return [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", executable, *arguments]
    if os.name == "nt" and suffix == ".ps1":
        return [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            executable,
            *arguments,
        ]
    return [executable, *arguments]


def run_claude_command(executable: str, *arguments: str, timeout: float = 10) -> str:
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    completed = subprocess.run(
        command_for_claude(executable, *arguments),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
        creationflags=creation_flags,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(detail or f"Claude CLI 結束碼：{completed.returncode}")
    return completed.stdout


def read_claude_auth_status(executable: str) -> Mapping[str, Any]:
    output = run_claude_command(executable, "auth", "status", "--json")
    try:
        payload = json.loads(output)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Claude CLI 回傳了無法解析的登入狀態。") from exc
    if not isinstance(payload, Mapping):
        raise RuntimeError("Claude CLI 登入狀態格式不正確。")
    return payload


class ClaudeUsageClient(QObject):
    state_changed = Signal(object)
    account_changed = Signal(object)
    usage_received = Signal(object)
    error_occurred = Signal(str)
    refreshing_changed = Signal(bool)
    integration_changed = Signal(bool)

    def __init__(
        self,
        integration: StatusLineIntegration | None = None,
        *,
        executable: str | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.integration = integration or StatusLineIntegration()
        self._configured_executable = executable
        self._executable: str | None = None
        self._state = ConnectionState.STOPPED
        self._snapshot: UsageSnapshot | None = None
        self._refreshing = False

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(10_000)
        self._poll_timer.timeout.connect(self._read_cache)
        self._auth_timer = QTimer(self)
        self._auth_timer.setInterval(60_000)
        self._auth_timer.timeout.connect(self.refresh)

    @property
    def state(self) -> ConnectionState:
        return self._state

    @property
    def executable(self) -> str | None:
        return self._executable

    def start(self) -> None:
        self._set_state(ConnectionState.STARTING)
        executable = self._configured_executable or find_claude_executable()
        if not executable:
            self._set_state(ConnectionState.MISSING_CLI)
            self.error_occurred.emit(
                "找不到 Claude Code CLI。請先安裝或更新 Claude Code，並確認 claude 位於 PATH。"
            )
            return
        try:
            version_output = run_claude_command(executable, "--version", timeout=5)
        except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
            self._set_state(ConnectionState.ERROR)
            self.error_occurred.emit(f"無法執行 Claude Code CLI：{exc}")
            return
        version = parse_claude_version(version_output)
        if version is None:
            self._set_state(ConnectionState.ERROR)
            self.error_occurred.emit("無法判斷 Claude Code CLI 版本。")
            return
        if version < MIN_CLAUDE_VERSION:
            current = ".".join(str(part) for part in version)
            self._set_state(ConnectionState.OUTDATED_CLI)
            self.error_occurred.emit(
                f"Claude Code {current} 過舊；status line 用量欄位需要 2.1.80 以上。"
            )
            return

        self._executable = executable
        self._poll_timer.start()
        self._auth_timer.start()
        self.refresh()

    def stop(self) -> None:
        self._poll_timer.stop()
        self._auth_timer.stop()
        self._set_refreshing(False)
        self._set_state(ConnectionState.STOPPED)

    def refresh(self) -> None:
        if not self._executable:
            self.start()
            return
        self._set_refreshing(True)
        try:
            account = read_claude_auth_status(self._executable)
        except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
            self._set_state(ConnectionState.ERROR)
            self.error_occurred.emit(f"無法讀取 Claude 登入狀態：{exc}")
            self._set_refreshing(False)
            return

        self.account_changed.emit(dict(account))
        if not account.get("loggedIn"):
            self._set_state(ConnectionState.AUTH_REQUIRED)
            self._set_refreshing(False)
            return
        try:
            installed = self.integration.is_installed()
        except IntegrationError as exc:
            self._set_state(ConnectionState.ERROR)
            self.error_occurred.emit(str(exc))
            self._set_refreshing(False)
            return
        self.integration_changed.emit(installed)
        if not installed:
            self._set_state(ConnectionState.INTEGRATION_REQUIRED)
            self._set_refreshing(False)
            return
        self._read_cache()
        self._set_refreshing(False)

    def install_integration(self) -> None:
        try:
            self.integration.install()
        except IntegrationError as exc:
            self.error_occurred.emit(str(exc))
            return
        self.integration_changed.emit(True)
        self._set_state(ConnectionState.WAITING_FOR_DATA)
        self.refresh()

    def _read_cache(self) -> None:
        try:
            if not self.integration.is_installed():
                return
            payload = self.integration.read_cache()
        except IntegrationError as exc:
            self._set_state(ConnectionState.ERROR)
            self.error_occurred.emit(str(exc))
            return
        if payload is None:
            self._set_state(ConnectionState.WAITING_FOR_DATA)
            return
        snapshot = parse_statusline_cache(payload)
        if not snapshot.windows:
            self._set_state(ConnectionState.WAITING_FOR_DATA)
            return
        age = (datetime.now(UTC) - snapshot.fetched_at).total_seconds()
        if age > STALE_AFTER_SECONDS:
            snapshot = snapshot.as_stale()
            self._set_state(ConnectionState.STALE)
        else:
            self._set_state(ConnectionState.READY)
        if snapshot != self._snapshot:
            self._snapshot = snapshot
            self.usage_received.emit(snapshot)

    def _set_state(self, state: ConnectionState) -> None:
        if self._state == state:
            return
        self._state = state
        self.state_changed.emit(state)

    def _set_refreshing(self, refreshing: bool) -> None:
        if self._refreshing == refreshing:
            return
        self._refreshing = refreshing
        self.refreshing_changed.emit(refreshing)


def launch_claude_login(executable: str) -> None:
    creation_flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0) if os.name == "nt" else 0
    subprocess.Popen(
        command_for_claude(executable, "auth", "login"),
        creationflags=creation_flags,
        close_fds=True,
    )
