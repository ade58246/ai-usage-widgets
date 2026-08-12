from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from claude_usage_widget.models import RateLimitWindowView, UsageSnapshot

WINDOWS: dict[str, tuple[str, int | None]] = {
    "five_hour": ("5 小時用量", 300),
    "seven_day": ("7 天用量", 10_080),
    "seven_day_opus": ("7 天 Opus 用量", 10_080),
    "seven_day_sonnet": ("7 天 Sonnet 用量", 10_080),
    "overage": ("額外用量", None),
}


def _mapping(value: Any) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _timestamp(value: Any) -> int | None:
    number = _number(value)
    return int(number) if number is not None else None


def _captured_at(value: Any) -> datetime:
    if not isinstance(value, str):
        return datetime.now(UTC)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(UTC)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def parse_statusline_cache(payload: Mapping[str, Any]) -> UsageSnapshot:
    """Normalize the privacy-filtered Claude Code status-line cache."""

    limits = _mapping(payload.get("rate_limits")) or {}
    ordered_keys = [*WINDOWS]
    ordered_keys.extend(key for key in limits if key not in WINDOWS)
    windows: list[RateLimitWindowView] = []

    for key in ordered_keys:
        raw_window = _mapping(limits.get(key))
        if raw_window is None:
            continue
        used = _number(raw_window.get("used_percentage"))
        if used is None:
            continue
        used_percent = round(max(0.0, min(100.0, used)))
        default_label, duration = WINDOWS.get(
            key, (key.replace("_", " ").strip().title() or "Claude", None)
        )
        windows.append(
            RateLimitWindowView(
                key=key,
                label=default_label,
                used_percent=used_percent,
                remaining_percent=100 - used_percent,
                window_duration_mins=duration,
                resets_at=_timestamp(raw_window.get("resets_at")),
            )
        )

    model = _mapping(payload.get("model"))
    model_name = model.get("display_name") if model else None
    if not isinstance(model_name, str) or not model_name.strip():
        model_name = None
    version = payload.get("version")
    if not isinstance(version, str) or not version.strip():
        version = None

    return UsageSnapshot(
        windows=tuple(windows),
        model_name=model_name,
        cli_version=version,
        fetched_at=_captured_at(payload.get("captured_at")),
    )
