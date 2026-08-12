from datetime import UTC, datetime

from codex_usage_widget.parser import parse_rate_limits


def test_multi_bucket_view_wins_over_legacy_and_includes_every_window() -> None:
    result = {
        "rateLimits": {
            "limitId": "legacy",
            "primary": {"usedPercent": 99},
        },
        "rateLimitsByLimitId": {
            "codex": {
                "limitId": "codex",
                "limitName": None,
                "planType": "plus",
                "primary": {
                    "usedPercent": 25,
                    "windowDurationMins": 300,
                    "resetsAt": 1_800_000_000,
                },
                "secondary": {
                    "usedPercent": 50,
                    "windowDurationMins": 10_080,
                    "resetsAt": 1_800_100_000,
                },
            },
            "other": {
                "limitName": "其他工作",
                "primary": {"usedPercent": 10},
            },
        },
    }

    snapshot = parse_rate_limits(result)

    assert [window.limit_id for window in snapshot.windows] == ["codex", "codex", "other"]
    assert [window.remaining_percent for window in snapshot.windows] == [75, 50, 90]
    assert snapshot.windows[2].label == "其他工作"
    assert snapshot.plan_types == ("plus",)


def test_legacy_fallback_clamps_percent_and_preserves_unknown_times() -> None:
    fetched_at = datetime(2026, 8, 11, tzinfo=UTC)
    snapshot = parse_rate_limits(
        {
            "rateLimits": {
                "limitId": "codex",
                "primary": {
                    "usedPercent": 150,
                    "windowDurationMins": None,
                    "resetsAt": None,
                },
                "secondary": None,
            }
        },
        fetched_at=fetched_at,
    )

    assert len(snapshot.windows) == 1
    assert snapshot.windows[0].used_percent == 100
    assert snapshot.windows[0].remaining_percent == 0
    assert snapshot.windows[0].window_duration_mins is None
    assert snapshot.windows[0].resets_at is None
    assert snapshot.fetched_at == fetched_at


def test_credits_spend_controls_and_reset_credit_count_are_normalized() -> None:
    snapshot = parse_rate_limits(
        {
            "rateLimits": {
                "limitId": "codex",
                "limitName": "Codex",
                "credits": {"balance": "12.50", "hasCredits": True, "unlimited": False},
                "individualLimit": {
                    "limit": "100",
                    "used": "40",
                    "remainingPercent": 60,
                    "resetsAt": 1_800_000_000,
                },
            },
            "rateLimitResetCredits": {"availableCount": 2, "credits": None},
        }
    )

    assert snapshot.credit_balances[0].balance == "12.50"
    assert snapshot.credit_balances[0].has_credits is True
    assert snapshot.spend_limits[0].remaining_percent == 60
    assert snapshot.reset_credit_count == 2


def test_empty_or_unknown_fields_do_not_crash_parser() -> None:
    snapshot = parse_rate_limits({"rateLimits": {"unexpected": {"value": 1}}})
    assert snapshot.windows == ()
    assert snapshot.plan_types == ()
