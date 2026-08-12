from __future__ import annotations

import json
import os
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

INTEGRATION_MARKER = "ClaudeUsageWidgetStatusCapture-v1"


class IntegrationError(RuntimeError):
    pass


class IntegrationConflictError(IntegrationError):
    pass


@dataclass(frozen=True, slots=True)
class IntegrationPaths:
    settings: Path
    app_data: Path
    capture_script: Path
    cache: Path
    backup: Path
    metadata: Path

    @classmethod
    def default(cls) -> IntegrationPaths:
        local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        app_data = local_app_data / "ClaudeUsageWidget"
        return cls(
            settings=Path.home() / ".claude" / "settings.json",
            app_data=app_data,
            capture_script=app_data / "capture-statusline.ps1",
            cache=app_data / "usage.json",
            backup=app_data / "settings-before-integration.json",
            metadata=app_data / "integration.json",
        )


def _read_json(path: Path, *, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IntegrationError(f"無法讀取 {path}：{exc}") from exc


def _atomic_write(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(text, encoding=encoding)
    temporary.replace(path)


def _ps_literal(path: Path) -> str:
    return str(path).replace("'", "''")


def build_capture_script(cache_path: Path) -> str:
    cache = _ps_literal(cache_path)
    return f"""# {INTEGRATION_MARKER}
$ErrorActionPreference = 'SilentlyContinue'
$raw = [Console]::In.ReadToEnd()
try {{
    $inputData = $raw | ConvertFrom-Json
}} catch {{
    Write-Output 'Claude'
    exit 0
}}

$payload = [ordered]@{{
    captured_at = [DateTime]::UtcNow.ToString('o')
    version = $inputData.version
    model = if ($null -ne $inputData.model) {{
        [ordered]@{{ display_name = $inputData.model.display_name }}
    }} else {{ $null }}
    rate_limits = $inputData.rate_limits
}}

$cachePath = '{cache}'
$cacheDirectory = Split-Path -Parent $cachePath
New-Item -ItemType Directory -Force -Path $cacheDirectory | Out-Null
$temporary = "$cachePath.tmp.$PID"
$payload | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $temporary -Encoding utf8
Move-Item -LiteralPath $temporary -Destination $cachePath -Force

$parts = @()
if ($null -ne $inputData.rate_limits.five_hour.used_percentage) {{
    $parts += ('5h 已用 {{0:N0}}%' -f $inputData.rate_limits.five_hour.used_percentage)
}}
if ($null -ne $inputData.rate_limits.seven_day.used_percentage) {{
    $parts += ('7d 已用 {{0:N0}}%' -f $inputData.rate_limits.seven_day.used_percentage)
}}
if ($parts.Count -gt 0) {{
    Write-Output ('Claude | ' + ($parts -join ' | '))
}} else {{
    Write-Output 'Claude 用量：等待第一個 API 回應'
}}
"""


class StatusLineIntegration:
    def __init__(self, paths: IntegrationPaths | None = None) -> None:
        self.paths = paths or IntegrationPaths.default()

    @property
    def command(self) -> str:
        script = self.paths.capture_script.as_posix()
        return f'powershell -NoProfile -ExecutionPolicy Bypass -File "{script}"'

    def existing_status_line(self) -> Mapping[str, Any] | None:
        settings = _read_json(self.paths.settings, default={})
        if not isinstance(settings, Mapping):
            raise IntegrationError("Claude settings.json 的根節點必須是 JSON 物件。")
        status_line = settings.get("statusLine")
        return status_line if isinstance(status_line, Mapping) else None

    def is_installed(self) -> bool:
        status_line = self.existing_status_line()
        if not status_line:
            return False
        return status_line.get("command") == self.command and self.paths.capture_script.exists()

    def has_conflict(self) -> bool:
        status_line = self.existing_status_line()
        return bool(status_line and status_line.get("command") != self.command)

    def install(self) -> None:
        settings_existed = self.paths.settings.exists()
        settings = _read_json(self.paths.settings, default={})
        if not isinstance(settings, dict):
            raise IntegrationError("Claude settings.json 的根節點必須是 JSON 物件。")
        previous = settings.get("statusLine")
        if isinstance(previous, Mapping) and previous.get("command") != self.command:
            raise IntegrationConflictError(
                "已偵測到其他 Claude status line；為避免覆蓋，請先停用原設定。"
            )

        self.paths.app_data.mkdir(parents=True, exist_ok=True)
        if self.paths.settings.exists() and not self.paths.backup.exists():
            shutil.copy2(self.paths.settings, self.paths.backup)
        _atomic_write(
            self.paths.capture_script,
            build_capture_script(self.paths.cache),
            encoding="utf-8-sig",
        )

        settings["statusLine"] = {
            "type": "command",
            "command": self.command,
            "padding": 0,
            "refreshInterval": 60,
        }
        _atomic_write(
            self.paths.settings,
            json.dumps(settings, ensure_ascii=False, indent=2) + "\n",
        )
        metadata = {
            "marker": INTEGRATION_MARKER,
            "settings_existed": settings_existed,
            "previous_status_line": previous,
        }
        _atomic_write(
            self.paths.metadata,
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        )

    def uninstall(self) -> None:
        settings = _read_json(self.paths.settings, default={})
        if not isinstance(settings, dict):
            raise IntegrationError("Claude settings.json 的根節點必須是 JSON 物件。")
        current = settings.get("statusLine")
        if not isinstance(current, Mapping) or current.get("command") != self.command:
            return

        metadata = _read_json(self.paths.metadata, default={})
        previous = metadata.get("previous_status_line") if isinstance(metadata, Mapping) else None
        if isinstance(previous, Mapping):
            settings["statusLine"] = dict(previous)
        else:
            settings.pop("statusLine", None)
        _atomic_write(
            self.paths.settings,
            json.dumps(settings, ensure_ascii=False, indent=2) + "\n",
        )

    def read_cache(self) -> Mapping[str, Any] | None:
        payload = _read_json(self.paths.cache, default=None)
        if payload is None:
            return None
        if not isinstance(payload, Mapping):
            raise IntegrationError("Claude 用量快取格式不正確。")
        return payload
