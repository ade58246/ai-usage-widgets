from __future__ import annotations

import sys
from pathlib import Path

from codex_usage_widget.app_server import (
    CodexAppServerClient,
    JsonLineBuffer,
    parse_codex_version,
)
from codex_usage_widget.models import ConnectionState


def test_json_line_buffer_handles_fragmented_and_invalid_lines() -> None:
    buffer = JsonLineBuffer()
    assert buffer.feed(b'{"id":1,"result":') == []
    messages = buffer.feed(b'{}}\r\nnot-json\n{"method":"ready"}\n')
    assert messages == [{"id": 1, "result": {}}, {"method": "ready"}]


def test_parse_codex_version() -> None:
    assert parse_codex_version("codex-cli 0.147.0") == (0, 147, 0)
    assert parse_codex_version("unknown") is None


def test_fake_server_handshake_refresh_and_sparse_notification(qtbot) -> None:
    fake = Path(__file__).with_name("fake_app_server.py")
    client = CodexAppServerClient(
        executable=sys.executable,
        app_server_args=[str(fake)],
    )
    snapshots = []
    client.usage_received.connect(snapshots.append)

    client.start()
    qtbot.waitUntil(lambda: len(snapshots) >= 2, timeout=6_000)

    assert snapshots[0].windows[0].remaining_percent == 75
    assert snapshots[-1].windows[0].remaining_percent == 70
    assert client.state == ConnectionState.READY
    client.stop()


def test_fake_server_browser_login_flow(qtbot) -> None:
    fake = Path(__file__).with_name("fake_app_server.py")
    client = CodexAppServerClient(
        executable=sys.executable,
        app_server_args=[str(fake), "--auth-required"],
    )
    urls = []
    snapshots = []
    client.login_url_ready.connect(urls.append)
    client.usage_received.connect(snapshots.append)

    client.start()
    qtbot.waitUntil(lambda: client.state == ConnectionState.AUTH_REQUIRED, timeout=4_000)
    client.start_login()
    qtbot.waitUntil(lambda: bool(urls) and bool(snapshots), timeout=5_000)

    assert urls[0].toString() == "https://chatgpt.com/fake-login"
    assert snapshots[0].windows[0].remaining_percent == 75
    client.stop()
