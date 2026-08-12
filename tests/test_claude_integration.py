from __future__ import annotations

import json
import subprocess

import pytest

from claude_usage_widget.integration import (
    INTEGRATION_MARKER,
    IntegrationConflictError,
    IntegrationPaths,
    StatusLineIntegration,
    build_capture_script,
)


def make_paths(tmp_path) -> IntegrationPaths:
    app_data = tmp_path / "app-data"
    return IntegrationPaths(
        settings=tmp_path / ".claude" / "settings.json",
        app_data=app_data,
        capture_script=app_data / "capture-statusline.ps1",
        cache=app_data / "usage.json",
        backup=app_data / "settings-before-integration.json",
        metadata=app_data / "integration.json",
    )


def test_installs_privacy_filtered_status_line_and_preserves_settings(tmp_path) -> None:
    paths = make_paths(tmp_path)
    paths.settings.parent.mkdir(parents=True)
    paths.settings.write_text('{"autoUpdatesChannel":"stable"}\n', encoding="utf-8")
    integration = StatusLineIntegration(paths)

    integration.install()

    settings = json.loads(paths.settings.read_text(encoding="utf-8"))
    assert settings["autoUpdatesChannel"] == "stable"
    assert settings["statusLine"]["command"] == integration.command
    assert settings["statusLine"]["refreshInterval"] == 60
    assert integration.is_installed() is True
    assert paths.backup.exists()
    script = paths.capture_script.read_text(encoding="utf-8")
    assert INTEGRATION_MARKER in script
    assert "rate_limits" in script
    assert "transcript_path" not in script
    assert "accessToken" not in script
    assert "refreshToken" not in script


def test_refuses_to_overwrite_existing_status_line(tmp_path) -> None:
    paths = make_paths(tmp_path)
    paths.settings.parent.mkdir(parents=True)
    paths.settings.write_text(
        json.dumps({"statusLine": {"type": "command", "command": "my-status.exe"}}),
        encoding="utf-8",
    )
    integration = StatusLineIntegration(paths)

    with pytest.raises(IntegrationConflictError):
        integration.install()
    assert integration.has_conflict() is True


def test_uninstall_restores_previous_absence(tmp_path) -> None:
    paths = make_paths(tmp_path)
    paths.settings.parent.mkdir(parents=True)
    paths.settings.write_text('{"theme":"dark"}\n', encoding="utf-8")
    integration = StatusLineIntegration(paths)
    integration.install()

    integration.uninstall()

    settings = json.loads(paths.settings.read_text(encoding="utf-8"))
    assert settings == {"theme": "dark"}


def test_capture_script_only_builds_sanitized_payload(tmp_path) -> None:
    script = build_capture_script(tmp_path / "usage.json")
    assert "captured_at" in script
    assert "display_name" in script
    assert "rate_limits" in script
    assert "workspace" not in script
    assert "transcript" not in script
    assert "session_id" not in script


def test_capture_script_writes_only_allowed_fields(tmp_path) -> None:
    cache = tmp_path / "usage.json"
    script_path = tmp_path / "capture-statusline.ps1"
    script_path.write_text(build_capture_script(cache), encoding="utf-8-sig")
    input_payload = {
        "cwd": "C:/private/project",
        "session_id": "secret-session",
        "transcript_path": "C:/private/transcript.jsonl",
        "version": "2.1.223",
        "model": {"display_name": "Opus", "id": "private-model-id"},
        "rate_limits": {
            "five_hour": {"used_percentage": 25, "resets_at": 2_000_000_000},
            "seven_day": {"used_percentage": 40, "resets_at": 2_000_100_000},
        },
    }

    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
        ],
        input=json.dumps(input_payload),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=30,
    )

    assert completed.returncode == 0, completed.stderr
    saved = json.loads(cache.read_text(encoding="utf-8-sig"))
    assert set(saved) == {"captured_at", "version", "model", "rate_limits"}
    assert saved["model"] == {"display_name": "Opus"}
    assert saved["rate_limits"] == input_payload["rate_limits"]
