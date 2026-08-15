from __future__ import annotations

from datetime import UTC, datetime

from PySide6.QtCore import QSettings, Qt

from battery_usage_widget.autostart import VALUE_NAME, AutostartManager
from battery_usage_widget.models import BatterySnapshot, BatteryState
from battery_usage_widget.widget import (
    FloatingBatteryWidget,
    format_capacity,
    format_power,
    format_time,
    presentation_for,
)
from tests.test_windows_integration import FakeRegistry


def make_snapshot(
    *,
    state: BatteryState = BatteryState.DISCHARGING,
    percent: int | None = 64,
    ac_online: bool | None = False,
    rate: int | None = -18_500,
) -> BatterySnapshot:
    return BatterySnapshot(
        state=state,
        percent=percent,
        ac_online=ac_online,
        battery_present=state != BatteryState.NO_BATTERY,
        battery_saver=False,
        remaining_seconds=7_200,
        full_life_seconds=None,
        max_capacity_mwh=85_070,
        remaining_capacity_mwh=54_445,
        power_rate_mw=rate,
        fetched_at=datetime(2026, 8, 15, tzinfo=UTC),
    )


def test_battery_formatters_and_presentation() -> None:
    assert format_time(7_200) == "約 2 小時 0 分"
    assert format_time(None) == "Windows 尚未提供"
    assert format_power(-18_500) == "耗電 18.5 W"
    assert format_power(45_000) == "充電 45.0 W"
    assert format_capacity(54_445, 85_070) == "54.4 / 85.1 Wh"
    assert presentation_for(make_snapshot()) == ("normal", "● 使用電池")
    assert presentation_for(make_snapshot(percent=10)) == ("critical", "⚠ 電量緊迫")


def test_widget_is_topmost_and_renders_real_battery_fields(qtbot, tmp_path) -> None:
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    autostart = AutostartManager(FakeRegistry(), executable="battery.exe", frozen=False)
    widget = FloatingBatteryWidget(settings, autostart, enable_tray=False)
    qtbot.addWidget(widget)
    widget.show()
    widget.set_snapshot(make_snapshot())

    assert widget.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    assert widget.windowFlags() & Qt.WindowType.FramelessWindowHint
    assert widget.percent_label.text() == "64%"
    assert widget.state_badge.text() == "● 使用電池"
    assert widget.progress_bar.value() == 64
    assert widget.source_value.text() == "電池供電"
    assert widget.time_value.text() == "約 2 小時 0 分"
    assert widget.power_value.text() == "耗電 18.5 W"
    assert widget.capacity_value.text() == "54.4 / 85.1 Wh"
    assert widget.refresh_button.accessibleName() == "立即更新電池狀態"
    assert widget.percent_label.minimumWidth() >= 145
    assert widget.status_label.minimumWidth() >= 132


def test_widget_distinguishes_charging_and_no_battery(qtbot, tmp_path) -> None:
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    autostart = AutostartManager(FakeRegistry(), executable="battery.exe", frozen=False)
    widget = FloatingBatteryWidget(settings, autostart, enable_tray=False)
    qtbot.addWidget(widget)

    widget.set_snapshot(
        make_snapshot(
            state=BatteryState.CHARGING,
            percent=72,
            ac_online=True,
            rate=42_000,
        )
    )
    assert widget.state_badge.text() == "⚡ 充電中"
    assert widget.state_badge.property("state") == "charging"
    assert widget.power_value.text() == "充電 42.0 W"

    widget.set_snapshot(
        make_snapshot(
            state=BatteryState.NO_BATTERY,
            percent=None,
            ac_online=True,
            rate=None,
        )
    )
    assert widget.percent_label.text() == "--%"
    assert widget.state_badge.text() == "○ 未偵測到電池"
    assert "沒有偵測到" in widget.summary_label.text()


def test_close_without_tray_requests_exit(qtbot, tmp_path) -> None:
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    autostart = AutostartManager(FakeRegistry(), executable="battery.exe", frozen=False)
    widget = FloatingBatteryWidget(settings, autostart, enable_tray=False)
    qtbot.addWidget(widget)
    widget.show()

    with qtbot.waitSignal(widget.exit_requested, timeout=1_000):
        widget.close()


def test_battery_autostart_uses_its_own_registry_value(tmp_path) -> None:
    backend = FakeRegistry()
    executable = tmp_path / "Battery Usage Widget.exe"
    manager = AutostartManager(backend, executable=str(executable), frozen=True)

    manager.set_enabled(True)
    assert backend.values[VALUE_NAME] == f'"{executable.resolve()}"'
    manager.set_enabled(False)
    assert VALUE_NAME not in backend.values
