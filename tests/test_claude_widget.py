from __future__ import annotations

from datetime import UTC, datetime

from PySide6.QtCore import QSettings, Qt

from claude_usage_widget.autostart import AutostartManager
from claude_usage_widget.models import ConnectionState, RateLimitWindowView, UsageSnapshot
from claude_usage_widget.widget import FloatingUsageWidget, format_countdown, severity_for
from tests.test_windows_integration import FakeRegistry


def make_snapshot() -> UsageSnapshot:
    return UsageSnapshot(
        windows=(
            RateLimitWindowView(
                key="five_hour",
                label="5 小時用量",
                used_percent=75,
                remaining_percent=25,
                window_duration_mins=300,
                resets_at=2_000_000_000,
            ),
        ),
        model_name="Opus",
        cli_version="2.1.223",
        fetched_at=datetime(2026, 8, 11, tzinfo=UTC),
    )


def test_formatters_and_severity() -> None:
    assert format_countdown(1_061, now=1_000) == "1 分 1 秒後重設"
    assert severity_for(make_snapshot().windows[0]) == ("warning", "注意")


def test_widget_is_topmost_and_renders_snapshot(qtbot, tmp_path) -> None:
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    autostart = AutostartManager(FakeRegistry(), executable="widget.exe", frozen=False)
    widget = FloatingUsageWidget(settings, autostart, enable_tray=False)
    qtbot.addWidget(widget)
    widget.show()
    widget.set_snapshot(make_snapshot())
    widget.set_connection_state(ConnectionState.READY)

    assert widget.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    assert widget.windowFlags() & Qt.WindowType.FramelessWindowHint
    assert len(widget._usage_rows) == 1
    assert widget._usage_rows[0].window_data.remaining_percent == 25


def test_integration_state_exposes_keyboard_button(qtbot, tmp_path) -> None:
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    autostart = AutostartManager(FakeRegistry(), executable="widget.exe", frozen=False)
    widget = FloatingUsageWidget(settings, autostart, enable_tray=False)
    qtbot.addWidget(widget)

    widget.set_connection_state(ConnectionState.INTEGRATION_REQUIRED)

    assert widget.integration_button.isVisible() is False  # Parent is not shown yet.
    widget.show()
    assert widget.integration_button.isVisible() is True
    assert widget.integration_button.focusPolicy() & Qt.FocusPolicy.TabFocus
