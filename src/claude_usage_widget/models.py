from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import Enum


class ConnectionState(Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    AUTH_REQUIRED = "auth_required"
    INTEGRATION_REQUIRED = "integration_required"
    WAITING_FOR_DATA = "waiting_for_data"
    READY = "ready"
    STALE = "stale"
    MISSING_CLI = "missing_cli"
    OUTDATED_CLI = "outdated_cli"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class RateLimitWindowView:
    key: str
    label: str
    used_percent: int
    remaining_percent: int
    window_duration_mins: int | None
    resets_at: int | None


@dataclass(frozen=True, slots=True)
class UsageSnapshot:
    windows: tuple[RateLimitWindowView, ...] = ()
    model_name: str | None = None
    cli_version: str | None = None
    fetched_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    stale: bool = False

    def as_stale(self) -> UsageSnapshot:
        return replace(self, stale=True)
