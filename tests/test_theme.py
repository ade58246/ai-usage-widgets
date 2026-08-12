from __future__ import annotations

from codex_usage_widget.theme import (
    DARK_TOKENS,
    LIGHT_TOKENS,
    build_stylesheet,
    theme_tokens,
)


def test_custom_dark_important_text_keeps_the_light_card_background() -> None:
    tokens = theme_tokens(False, "#102030")

    assert tokens.surface == LIGHT_TOKENS.surface
    assert tokens.surface_alt == LIGHT_TOKENS.surface_alt
    assert tokens.on_surface == LIGHT_TOKENS.on_surface
    assert tokens.important_text == "#102030"
    assert tokens.interactive == LIGHT_TOKENS.interactive


def test_custom_light_important_text_keeps_the_dark_card_background() -> None:
    tokens = theme_tokens(True, "#F4E7D3")

    assert tokens.surface == DARK_TOKENS.surface
    assert tokens.on_surface == DARK_TOKENS.on_surface
    assert tokens.important_text == "#f4e7d3"
    assert tokens.interactive == DARK_TOKENS.interactive


def test_low_contrast_important_text_is_adjusted_for_readability() -> None:
    tokens = theme_tokens(False, LIGHT_TOKENS.surface)

    assert tokens.surface == LIGHT_TOKENS.surface
    assert tokens.important_text != LIGHT_TOKENS.surface


def test_invalid_important_text_color_falls_back_to_system_theme() -> None:
    assert theme_tokens(False, "not-a-color") == LIGHT_TOKENS
    assert theme_tokens(True, None) == DARK_TOKENS


def test_usage_progress_fill_uses_the_same_color_as_important_text() -> None:
    stylesheet = build_stylesheet(False, "#102030")

    assert 'QProgressBar[important="true"]::chunk' in stylesheet
    assert "background: #102030;" in stylesheet
