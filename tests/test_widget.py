from __future__ import annotations

from datetime import UTC, datetime

import pytest
from PySide6.QtCore import QSettings, Qt

from codex_usage_widget.autostart import AutostartManager
from codex_usage_widget.models import RateLimitWindowView, UsageSnapshot
from codex_usage_widget.widget import (
    AppearancePanel,
    FloatingUsageWidget,
    format_countdown,
    format_duration,
    severity_for,
)
from tests.test_windows_integration import FakeRegistry


def make_snapshot() -> UsageSnapshot:
    return UsageSnapshot(
        windows=(
            RateLimitWindowView(
                limit_id="codex",
                label="Codex",
                window_kind="primary",
                used_percent=75,
                remaining_percent=25,
                window_duration_mins=300,
                resets_at=2_000_000_000,
            ),
        ),
        plan_types=("plus",),
        reset_credit_count=1,
        fetched_at=datetime(2026, 8, 11, tzinfo=UTC),
    )


def test_formatters_and_severity() -> None:
    assert format_duration(300) == "5 小時"
    assert format_duration(None) == "時間窗未知"
    assert format_countdown(1_061, now=1_000) == "1 分 1 秒後重設"
    assert severity_for(make_snapshot().windows[0]) == ("warning", "注意")


def test_widget_is_topmost_and_renders_snapshot(qtbot, tmp_path) -> None:
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    autostart = AutostartManager(FakeRegistry(), executable="widget.exe", frozen=False)
    widget = FloatingUsageWidget(settings, autostart, enable_tray=False)
    qtbot.addWidget(widget)
    widget.show()
    widget.set_snapshot(make_snapshot())

    assert widget.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    assert widget.windowFlags() & Qt.WindowType.FramelessWindowHint
    assert len(widget._usage_rows) == 1
    assert widget._usage_rows[0].window_data.remaining_percent == 25
    assert widget._usage_rows[0].title_label.property("important") is True
    assert widget._usage_rows[0].percent_label.property("important") is True
    assert widget._usage_rows[0].reset_label.property("important") is True
    assert widget._usage_rows[0].progress_bar.property("important") is True


def test_close_without_tray_requests_exit(qtbot, tmp_path) -> None:
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    autostart = AutostartManager(FakeRegistry(), executable="widget.exe", frozen=False)
    widget = FloatingUsageWidget(settings, autostart, enable_tray=False)
    qtbot.addWidget(widget)
    widget.show()

    with qtbot.waitSignal(widget.exit_requested, timeout=1_000):
        widget.close()


def test_saved_appearance_is_migrated_and_can_be_updated(qtbot, tmp_path) -> None:
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    settings.setValue("appearance/opacity_percent", 65)
    settings.setValue("appearance/background_color", "#123456")
    autostart = AutostartManager(FakeRegistry(), executable="widget.exe", frozen=False)

    widget = FloatingUsageWidget(settings, autostart, enable_tray=False)
    qtbot.addWidget(widget)
    widget.show()

    assert widget.windowOpacity() == pytest.approx(0.65, abs=1 / 255)
    assert "#123456" in widget.styleSheet()
    assert widget.appearance_button.accessibleName() == "顯示介面外觀調整"
    assert settings.value("appearance/important_text_color") == "#123456"
    assert settings.value("appearance/background_color") is None

    widget._set_appearance(55, "#ABCDEF", persist=True)
    assert widget.windowOpacity() == pytest.approx(0.55, abs=1 / 255)
    assert settings.value("appearance/opacity_percent", type=int) == 55
    assert settings.value("appearance/important_text_color") == "#abcdef"


def test_appearance_panel_is_inline_and_persists_changes(qtbot, tmp_path) -> None:
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    autostart = AutostartManager(FakeRegistry(), executable="widget.exe", frozen=False)
    widget = FloatingUsageWidget(settings, autostart, enable_tray=False)
    qtbot.addWidget(widget)
    widget.show()

    assert isinstance(widget.appearance_panel, AppearancePanel)
    assert widget.appearance_panel.isHidden()

    widget.appearance_button.click()
    assert widget.appearance_panel.isVisible()
    assert widget.appearance_button.isChecked()

    widget.appearance_panel.opacity_slider.setValue(70)
    assert widget.appearance_panel.opacity_value_label.text() == "70%"
    assert settings.value("appearance/opacity_percent", type=int) == 70

    widget.appearance_panel.appearance_changed.emit(70, "#123456")
    assert settings.value("appearance/important_text_color") == "#123456"

    widget.appearance_panel._reset_defaults()
    assert widget.appearance_panel.opacity_percent == 100
    assert widget.appearance_panel.important_text_color is None
    assert settings.value("appearance/opacity_percent", type=int) == 100
    assert settings.value("appearance/important_text_color") is None

    qtbot.keyClick(widget, Qt.Key.Key_Escape)
    assert widget.appearance_panel.isHidden()
    assert widget.isVisible()
