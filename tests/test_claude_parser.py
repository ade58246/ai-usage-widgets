from __future__ import annotations

from datetime import UTC, datetime

from claude_usage_widget.parser import parse_statusline_cache


def test_parses_official_five_hour_and_seven_day_windows() -> None:
    snapshot = parse_statusline_cache(
        {
            "captured_at": "2026-08-11T08:30:00Z",
            "version": "2.1.223",
            "model": {"display_name": "Opus"},
            "rate_limits": {
                "five_hour": {"used_percentage": 23.5, "resets_at": 2_000_000_000},
                "seven_day": {"used_percentage": 41.2, "resets_at": 2_000_100_000},
            },
        }
    )

    assert [window.key for window in snapshot.windows] == ["five_hour", "seven_day"]
    assert snapshot.windows[0].remaining_percent == 76
    assert snapshot.windows[0].window_duration_mins == 300
    assert snapshot.windows[1].remaining_percent == 59
    assert snapshot.windows[1].window_duration_mins == 10_080
    assert snapshot.model_name == "Opus"
    assert snapshot.cli_version == "2.1.223"
    assert snapshot.fetched_at == datetime(2026, 8, 11, 8, 30, tzinfo=UTC)


def test_clamps_percentages_and_keeps_missing_reset_time() -> None:
    snapshot = parse_statusline_cache(
        {
            "rate_limits": {
                "five_hour": {"used_percentage": -10},
                "seven_day": {"used_percentage": 140, "resets_at": None},
            }
        }
    )

    assert snapshot.windows[0].remaining_percent == 100
    assert snapshot.windows[0].resets_at is None
    assert snapshot.windows[1].remaining_percent == 0
    assert snapshot.windows[1].resets_at is None


def test_handles_optional_and_future_windows() -> None:
    snapshot = parse_statusline_cache(
        {
            "rate_limits": {
                "five_hour": None,
                "seven_day_opus": {"used_percentage": 75, "resets_at": 2_000_000_000},
                "future_bucket": {"used_percentage": 10},
                "invalid": {"used_percentage": "10"},
            },
            "unknown": {"ignored": True},
        }
    )

    assert [window.key for window in snapshot.windows] == ["seven_day_opus", "future_bucket"]
    assert snapshot.windows[0].label == "7 天 Opus 用量"
    assert snapshot.windows[1].label == "Future Bucket"
