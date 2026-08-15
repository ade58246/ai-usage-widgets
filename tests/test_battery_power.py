from __future__ import annotations

import ctypes
from datetime import UTC, datetime

from battery_usage_widget.models import BatterySnapshot, BatteryState
from battery_usage_widget.power import (
    UNKNOWN_DWORD,
    BatteryMonitor,
    SystemBatteryState,
    SystemPowerStatus,
    normalize_snapshot,
)


def make_power(
    *,
    ac: int = 1,
    flag: int = 1,
    percent: int = 100,
    saver: int = 0,
    life: int = UNKNOWN_DWORD,
    full_life: int = UNKNOWN_DWORD,
) -> SystemPowerStatus:
    return SystemPowerStatus(ac, flag, percent, saver, life, full_life)


def make_battery(
    *,
    ac: int = 1,
    present: int = 1,
    charging: int = 0,
    discharging: int = 0,
    maximum: int = 85_070,
    remaining: int = 85_070,
    rate: int = 0,
    estimated: int = UNKNOWN_DWORD,
) -> SystemBatteryState:
    battery = SystemBatteryState()
    battery.AcOnLine = ac
    battery.BatteryPresent = present
    battery.Charging = charging
    battery.Discharging = discharging
    battery.MaxCapacity = maximum
    battery.RemainingCapacity = remaining
    battery.Rate = rate
    battery.EstimatedTime = estimated
    return battery


def test_full_battery_on_ac_is_normalized_from_this_computers_shape() -> None:
    fetched_at = datetime(2026, 8, 15, tzinfo=UTC)
    snapshot = normalize_snapshot(
        make_power(),
        make_battery(),
        fetched_at=fetched_at,
    )

    assert snapshot.state == BatteryState.FULL
    assert snapshot.percent == 100
    assert snapshot.ac_online is True
    assert snapshot.remaining_seconds is None
    assert snapshot.max_capacity_mwh == 85_070
    assert snapshot.remaining_capacity_mwh == 85_070
    assert snapshot.power_rate_mw == 0
    assert snapshot.fetched_at == fetched_at


def test_discharging_rate_and_estimated_time_are_preserved() -> None:
    negative_rate = ctypes.c_uint32(-18_500).value
    snapshot = normalize_snapshot(
        make_power(ac=0, flag=1, percent=64, life=7_200),
        make_battery(
            ac=0,
            discharging=1,
            remaining=54_445,
            rate=negative_rate,
            estimated=7_200,
        ),
    )

    assert snapshot.state == BatteryState.DISCHARGING
    assert snapshot.percent == 64
    assert snapshot.remaining_seconds == 7_200
    assert snapshot.power_rate_mw == -18_500


def test_unknown_percent_falls_back_to_capacity_ratio() -> None:
    snapshot = normalize_snapshot(
        make_power(ac=0, percent=255),
        make_battery(ac=0, discharging=1, maximum=80_000, remaining=20_000),
    )

    assert snapshot.percent == 25
    assert snapshot.state == BatteryState.DISCHARGING


def test_unknown_flags_do_not_claim_no_battery_or_charging() -> None:
    snapshot = normalize_snapshot(
        make_power(ac=255, flag=255, percent=50, life=0),
        None,
    )

    assert snapshot.battery_present is True
    assert snapshot.state == BatteryState.UNKNOWN
    assert snapshot.remaining_seconds == 0


def test_no_battery_is_reported_without_fabricating_values() -> None:
    snapshot = normalize_snapshot(
        make_power(flag=128, percent=255),
        make_battery(present=0, maximum=0, remaining=0, rate=UNKNOWN_DWORD),
    )

    assert snapshot.state == BatteryState.NO_BATTERY
    assert snapshot.battery_present is False
    assert snapshot.percent is None
    assert snapshot.max_capacity_mwh is None
    assert snapshot.power_rate_mw is None


class FakeReader:
    def __init__(self, result: BatterySnapshot | Exception) -> None:
        self.result = result

    def read(self) -> BatterySnapshot:
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def test_monitor_emits_snapshot_and_errors(qtbot) -> None:
    snapshot = normalize_snapshot(make_power(), make_battery())
    monitor = BatteryMonitor(FakeReader(snapshot), interval_ms=60_000)

    with qtbot.waitSignal(monitor.snapshot_received, timeout=1_000) as received:
        monitor.start()
    assert received.args == [snapshot]
    monitor.stop()

    failing = BatteryMonitor(FakeReader(RuntimeError("讀取失敗")), interval_ms=60_000)
    with qtbot.waitSignal(failing.error_occurred, timeout=1_000) as error:
        failing.refresh()
    assert error.args == ["讀取失敗"]
