from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from codex_usage_widget.models import (
    CreditBalanceView,
    RateLimitWindowView,
    SpendLimitView,
    UsageSnapshot,
)


def _mapping(value: Any) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value)


def _required_int(value: Any, default: int = 0) -> int:
    parsed = _optional_int(value)
    return default if parsed is None else parsed


def _bucket_label(snapshot: Mapping[str, Any], fallback_id: str) -> str:
    for key in ("limitName", "limitId"):
        value = snapshot.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return fallback_id.strip() or "Codex"


def parse_rate_limits(
    result: Mapping[str, Any], *, fetched_at: datetime | None = None
) -> UsageSnapshot:
    """Normalize the stable app-server rate-limit response for presentation."""

    multi = _mapping(result.get("rateLimitsByLimitId"))
    if multi:
        raw_buckets = list(multi.items())
    else:
        legacy = _mapping(result.get("rateLimits")) or {}
        legacy_id = legacy.get("limitId")
        fallback_id = legacy_id if isinstance(legacy_id, str) and legacy_id else "codex"
        raw_buckets = [(fallback_id, legacy)]

    windows: list[RateLimitWindowView] = []
    plan_types: list[str] = []
    credit_balances: list[CreditBalanceView] = []
    spend_limits: list[SpendLimitView] = []

    for raw_id, raw_snapshot in raw_buckets:
        snapshot = _mapping(raw_snapshot)
        if snapshot is None:
            continue

        limit_id_value = snapshot.get("limitId")
        limit_id = (
            limit_id_value.strip()
            if isinstance(limit_id_value, str) and limit_id_value.strip()
            else str(raw_id)
        )
        label = _bucket_label(snapshot, limit_id)
        reached_type = snapshot.get("rateLimitReachedType")
        if not isinstance(reached_type, str):
            reached_type = None

        for kind in ("primary", "secondary"):
            raw_window = _mapping(snapshot.get(kind))
            if raw_window is None:
                continue
            used_percent = max(0, min(100, _required_int(raw_window.get("usedPercent"))))
            windows.append(
                RateLimitWindowView(
                    limit_id=limit_id,
                    label=label,
                    window_kind=kind,
                    used_percent=used_percent,
                    remaining_percent=100 - used_percent,
                    window_duration_mins=_optional_int(raw_window.get("windowDurationMins")),
                    resets_at=_optional_int(raw_window.get("resetsAt")),
                    reached_type=reached_type,
                )
            )

        plan_type = snapshot.get("planType")
        if isinstance(plan_type, str) and plan_type and plan_type not in plan_types:
            plan_types.append(plan_type)

        credits = _mapping(snapshot.get("credits"))
        if credits is not None:
            balance = credits.get("balance")
            credit_balances.append(
                CreditBalanceView(
                    bucket_label=label,
                    balance=balance if isinstance(balance, str) else None,
                    has_credits=bool(credits.get("hasCredits", False)),
                    unlimited=bool(credits.get("unlimited", False)),
                )
            )

        individual_limit = _mapping(snapshot.get("individualLimit"))
        if individual_limit is not None:
            remaining = max(0, min(100, _required_int(individual_limit.get("remainingPercent"))))
            resets_at = _optional_int(individual_limit.get("resetsAt"))
            if resets_at is not None:
                spend_limits.append(
                    SpendLimitView(
                        bucket_label=label,
                        limit=str(individual_limit.get("limit", "")),
                        used=str(individual_limit.get("used", "")),
                        remaining_percent=remaining,
                        resets_at=resets_at,
                    )
                )

    reset_credit_count: int | None = None
    reset_credits = _mapping(result.get("rateLimitResetCredits"))
    if reset_credits is not None:
        reset_credit_count = _optional_int(reset_credits.get("availableCount"))

    return UsageSnapshot(
        windows=tuple(windows),
        plan_types=tuple(plan_types),
        credit_balances=tuple(credit_balances),
        spend_limits=tuple(spend_limits),
        reset_credit_count=reset_credit_count,
        fetched_at=fetched_at or datetime.now(UTC),
    )
