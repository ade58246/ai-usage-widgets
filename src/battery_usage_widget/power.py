from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from datetime import UTC, datetime

from PySide6.QtCore import QObject, QTimer, Signal

from battery_usage_widget.models import BatterySnapshot, BatteryState

UNKNOWN_BYTE = 0xFF
UNKNOWN_DWORD = 0xFFFFFFFF
NO_SYSTEM_BATTERY = 0x80
BATTERY_CHARGING = 0x08
SYSTEM_BATTERY_STATE_LEVEL = 5
POLL_INTERVAL_MS = 5_000


class SystemPowerStatus(ctypes.Structure):
    _fields_ = [
        ("ACLineStatus", ctypes.c_ubyte),
        ("BatteryFlag", ctypes.c_ubyte),
        ("BatteryLifePercent", ctypes.c_ubyte),
        ("SystemStatusFlag", ctypes.c_ubyte),
        ("BatteryLifeTime", wintypes.DWORD),
        ("BatteryFullLifeTime", wintypes.DWORD),
    ]


class SystemBatteryState(ctypes.Structure):
    _fields_ = [
        ("AcOnLine", ctypes.c_ubyte),
        ("BatteryPresent", ctypes.c_ubyte),
        ("Charging", ctypes.c_ubyte),
        ("Discharging", ctypes.c_ubyte),
        ("Spare1", ctypes.c_ubyte * 3),
        ("Tag", ctypes.c_ubyte),
        ("MaxCapacity", wintypes.DWORD),
        ("RemainingCapacity", wintypes.DWORD),
        ("Rate", wintypes.DWORD),
        ("EstimatedTime", wintypes.DWORD),
        ("DefaultAlert1", wintypes.DWORD),
        ("DefaultAlert2", wintypes.DWORD),
    ]


def _known_seconds(value: int) -> int | None:
    return None if value == UNKNOWN_DWORD else int(value)


def _known_capacity(value: int, *, allow_zero: bool = False) -> int | None:
    if value == UNKNOWN_DWORD or (value == 0 and not allow_zero):
        return None
    return int(value)


def normalize_snapshot(
    power: SystemPowerStatus,
    battery: SystemBatteryState | None,
    *,
    fetched_at: datetime | None = None,
) -> BatterySnapshot:
    native_present = None if battery is None else bool(battery.BatteryPresent)
    battery_flag = int(power.BatteryFlag)
    battery_present = battery_flag != NO_SYSTEM_BATTERY
    if native_present is not None:
        battery_present = native_present

    ac_online = {0: False, 1: True}.get(int(power.ACLineStatus))
    if battery is not None:
        ac_online = bool(battery.AcOnLine)

    percent = int(power.BatteryLifePercent)
    if not 0 <= percent <= 100:
        percent = -1

    max_capacity = None
    remaining_capacity = None
    power_rate = None
    estimated_time = None
    charging = battery_flag != UNKNOWN_BYTE and bool(battery_flag & BATTERY_CHARGING)
    discharging = ac_online is False
    if battery is not None:
        max_capacity = _known_capacity(int(battery.MaxCapacity))
        remaining_capacity = _known_capacity(int(battery.RemainingCapacity), allow_zero=True)
        raw_rate = int(battery.Rate)
        power_rate = None if raw_rate == UNKNOWN_DWORD else ctypes.c_int32(raw_rate).value
        estimated_time = _known_seconds(int(battery.EstimatedTime))
        charging = bool(battery.Charging) or charging
        discharging = bool(battery.Discharging) or discharging

    if percent < 0 and max_capacity and remaining_capacity is not None:
        percent = round(remaining_capacity / max_capacity * 100)
    normalized_percent = None if percent < 0 else max(0, min(100, percent))

    if not battery_present:
        state = BatteryState.NO_BATTERY
    elif ac_online and normalized_percent == 100 and not charging:
        state = BatteryState.FULL
    elif charging:
        state = BatteryState.CHARGING
    elif discharging:
        state = BatteryState.DISCHARGING
    elif ac_online:
        state = BatteryState.PLUGGED_IN
    elif ac_online is False:
        state = BatteryState.ON_BATTERY
    else:
        state = BatteryState.UNKNOWN

    reported_remaining = _known_seconds(int(power.BatteryLifeTime))
    remaining_seconds = reported_remaining if reported_remaining is not None else estimated_time
    full_life_seconds = _known_seconds(int(power.BatteryFullLifeTime))
    saver_flag = int(power.SystemStatusFlag)
    battery_saver = bool(saver_flag) if saver_flag in {0, 1} else None

    return BatterySnapshot(
        state=state,
        percent=normalized_percent,
        ac_online=ac_online,
        battery_present=battery_present,
        battery_saver=battery_saver,
        remaining_seconds=remaining_seconds,
        full_life_seconds=full_life_seconds,
        max_capacity_mwh=max_capacity,
        remaining_capacity_mwh=remaining_capacity,
        power_rate_mw=power_rate,
        fetched_at=fetched_at or datetime.now(UTC),
    )


class WindowsBatteryReader:
    def __init__(self) -> None:
        if os.name != "nt":
            raise RuntimeError("電池小工具只支援 Windows。")
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._powrprof = ctypes.WinDLL("powrprof")
        self._kernel32.GetSystemPowerStatus.argtypes = [ctypes.POINTER(SystemPowerStatus)]
        self._kernel32.GetSystemPowerStatus.restype = wintypes.BOOL
        self._powrprof.CallNtPowerInformation.argtypes = [
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.ULONG,
            ctypes.c_void_p,
            wintypes.ULONG,
        ]
        self._powrprof.CallNtPowerInformation.restype = ctypes.c_long

    def read(self) -> BatterySnapshot:
        power = SystemPowerStatus()
        if not self._kernel32.GetSystemPowerStatus(ctypes.byref(power)):
            error_code = ctypes.get_last_error()
            raise OSError(error_code, "Windows 無法讀取系統電源狀態")

        battery = SystemBatteryState()
        status = self._powrprof.CallNtPowerInformation(
            SYSTEM_BATTERY_STATE_LEVEL,
            None,
            0,
            ctypes.byref(battery),
            ctypes.sizeof(battery),
        )
        return normalize_snapshot(power, battery if status == 0 else None)


class BatteryMonitor(QObject):
    snapshot_received = Signal(object)
    error_occurred = Signal(str)
    refreshing_changed = Signal(bool)

    def __init__(
        self,
        reader: WindowsBatteryReader | None = None,
        *,
        interval_ms: int = POLL_INTERVAL_MS,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.reader = reader or WindowsBatteryReader()
        self.timer = QTimer(self)
        self.timer.setInterval(interval_ms)
        self.timer.timeout.connect(self.refresh)
        self._refreshing = False

    def start(self) -> None:
        self.timer.start()
        self.refresh()

    def stop(self) -> None:
        self.timer.stop()

    def refresh(self) -> None:
        if self._refreshing:
            return
        self._refreshing = True
        self.refreshing_changed.emit(True)
        try:
            self.snapshot_received.emit(self.reader.read())
        except (OSError, RuntimeError) as exc:
            self.error_occurred.emit(str(exc))
        finally:
            self._refreshing = False
            self.refreshing_changed.emit(False)
