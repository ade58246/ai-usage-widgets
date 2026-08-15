from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum


class BatteryState(Enum):
    CHARGING = "charging"
    FULL = "full"
    DISCHARGING = "discharging"
    PLUGGED_IN = "plugged_in"
    ON_BATTERY = "on_battery"
    NO_BATTERY = "no_battery"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class BatterySnapshot:
    state: BatteryState
    percent: int | None
    ac_online: bool | None
    battery_present: bool
    battery_saver: bool | None
    remaining_seconds: int | None
    full_life_seconds: int | None
    max_capacity_mwh: int | None
    remaining_capacity_mwh: int | None
    power_rate_mw: int | None
    fetched_at: datetime = field(default_factory=lambda: datetime.now(UTC))
