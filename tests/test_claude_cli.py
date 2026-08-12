from __future__ import annotations

from claude_usage_widget.claude_cli import command_for_claude, parse_claude_version


def test_parses_claude_code_version() -> None:
    assert parse_claude_version("2.1.223 (Claude Code)") == (2, 1, 223)
    assert parse_claude_version("Claude Code") is None


def test_builds_windows_wrappers_for_script_launchers(monkeypatch) -> None:
    monkeypatch.setattr("claude_usage_widget.claude_cli.os.name", "nt")
    monkeypatch.setenv("COMSPEC", "C:\\Windows\\System32\\cmd.exe")
    cmd = command_for_claude("C:\\tools\\claude.cmd", "auth", "status")
    ps1 = command_for_claude("C:\\tools\\claude.ps1", "--version")

    assert cmd[:4] == [
        "C:\\Windows\\System32\\cmd.exe",
        "/d",
        "/c",
        "C:\\tools\\claude.cmd",
    ]
    assert ps1[0] == "powershell.exe"
    assert ps1[-2:] == ["C:\\tools\\claude.ps1", "--version"]
