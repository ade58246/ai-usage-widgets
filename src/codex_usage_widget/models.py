from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import Enum


class ConnectionState(Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    HANDSHAKING = "handshaking"
    CHECKING_ACCOUNT = "checking_account"
    AUTH_REQUIRED = "auth_required"
    AUTHENTICATING = "authenticating"
    READY = "ready"
    RECONNECTING = "reconnecting"
    MISSING_CLI = "missing_cli"
    OUTDATED_CLI = "outdated_cli"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class RateLimitWindowView:
    limit_id: str
    label: str
    window_kind: str
    used_percent: int
    remaining_percent: int
    window_duration_mins: int | None
    resets_at: int | None
    reached_type: str | None = None


@dataclass(frozen=True, slots=True)
class CreditBalanceView:
    bucket_label: str
    balance: str | None
    has_credits: bool
    unlimited: bool


@dataclass(frozen=True, slots=True)
class SpendLimitView:
    bucket_label: str
    limit: str
    used: str
    remaining_percent: int
    resets_at: int


@dataclass(frozen=True, slots=True)
class UsageSnapshot:
    windows: tuple[RateLimitWindowView, ...] = ()
    plan_types: tuple[str, ...] = ()
    credit_balances: tuple[CreditBalanceView, ...] = ()
    spend_limits: tuple[SpendLimitView, ...] = ()
    reset_credit_count: int | None = None
    fetched_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    stale: bool = False

    def as_stale(self) -> UsageSnapshot:
        return replace(self, stale=True)
