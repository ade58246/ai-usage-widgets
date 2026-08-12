from __future__ import annotations

from dataclasses import dataclass, replace

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication


@dataclass(frozen=True, slots=True)
class ThemeTokens:
    surface: str
    surface_alt: str
    on_surface: str
    on_surface_muted: str
    outline: str
    interactive: str
    interactive_hover: str
    normal: str
    warning: str
    critical: str
    focus: str
    important_text: str


LIGHT_TOKENS = ThemeTokens(
    surface="#F8FAFC",
    surface_alt="#EEF2F6",
    on_surface="#172033",
    on_surface_muted="#526078",
    outline="#CAD2DF",
    interactive="#0B63CE",
    interactive_hover="#084FA7",
    normal="#197A55",
    warning="#9A6700",
    critical="#B42318",
    focus="#0067C0",
    important_text="#0B63CE",
)

DARK_TOKENS = ThemeTokens(
    surface="#20232A",
    surface_alt="#2A2E37",
    on_surface="#F3F5F7",
    on_surface_muted="#B9C1CC",
    outline="#4A5260",
    interactive="#69A9FF",
    interactive_hover="#8ABEFF",
    normal="#66D6A3",
    warning="#F2C14E",
    critical="#FF8B84",
    focus="#7AB8FF",
    important_text="#69A9FF",
)


def is_dark_theme() -> bool:
    hints = QGuiApplication.styleHints()
    return hints.colorScheme() == Qt.ColorScheme.Dark


def _mix(first: QColor, second: QColor, second_ratio: float) -> str:
    ratio = max(0.0, min(1.0, second_ratio))
    channels = (
        round(first.red() * (1 - ratio) + second.red() * ratio),
        round(first.green() * (1 - ratio) + second.green() * ratio),
        round(first.blue() * (1 - ratio) + second.blue() * ratio),
    )
    return QColor(*channels).name()


def _relative_luminance(color: QColor) -> float:
    def linear(channel: int) -> float:
        normalized = channel / 255
        if normalized <= 0.04045:
            return normalized / 12.92
        return ((normalized + 0.055) / 1.055) ** 2.4

    red, green, blue = (linear(color.red()), linear(color.green()), linear(color.blue()))
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _contrast_ratio(first: QColor, second: QColor) -> float:
    lighter, darker = sorted(
        (_relative_luminance(first), _relative_luminance(second)), reverse=True
    )
    return (lighter + 0.05) / (darker + 0.05)


def _accessible_text_color(requested: QColor, surface: QColor, fallback: QColor) -> str:
    if _contrast_ratio(requested, surface) >= 4.5:
        return requested.name()
    for step in range(1, 21):
        candidate = QColor(_mix(requested, fallback, step / 20))
        if _contrast_ratio(candidate, surface) >= 4.5:
            return candidate.name()
    return fallback.name()


def theme_tokens(dark: bool, important_text_override: str | None = None) -> ThemeTokens:
    base = DARK_TOKENS if dark else LIGHT_TOKENS
    color = QColor(important_text_override or "")
    if not color.isValid():
        return base

    return replace(
        base,
        important_text=_accessible_text_color(
            color,
            QColor(base.surface),
            QColor(base.on_surface),
        ),
    )


def build_stylesheet(dark: bool, important_text_override: str | None = None) -> str:
    token = theme_tokens(dark, important_text_override)
    return f"""
        QWidget {{
            color: {token.on_surface};
            font-family: "Segoe UI Variable", "Segoe UI";
            font-size: 12pt;
        }}
        QFrame#Card {{
            background: {token.surface};
            border: 1px solid {token.outline};
            border-radius: 14px;
        }}
        QFrame#AppearancePanel {{
            background: {token.surface_alt};
            border: 1px solid {token.outline};
            border-radius: 10px;
        }}
        QFrame#Header {{
            background: transparent;
            border: none;
        }}
        QLabel#Title {{
            font-size: 15pt;
            font-weight: 600;
        }}
        QLabel#PanelTitle {{
            font-size: 12pt;
            font-weight: 600;
        }}
        QLabel#Muted, QLabel#Metadata, QLabel#ResetLabel {{
            color: {token.on_surface_muted};
            font-size: 10pt;
        }}
        QLabel#StatusLabel {{
            color: {token.on_surface_muted};
            font-size: 9pt;
        }}
        QLabel#ErrorBanner {{
            background: {token.surface_alt};
            color: {token.critical};
            border: 1px solid {token.critical};
            border-radius: 8px;
            padding: 8px;
        }}
        QFrame#UsageRow, QFrame#MetadataCard {{
            background: {token.surface_alt};
            border: 1px solid {token.outline};
            border-radius: 10px;
        }}
        QPushButton, QToolButton {{
            min-height: 36px;
            border: 1px solid {token.outline};
            border-radius: 8px;
            padding: 2px 10px;
            background: {token.surface_alt};
            color: {token.on_surface};
        }}
        QPushButton:hover, QToolButton:hover {{
            border-color: {token.interactive};
        }}
        QToolButton:checked {{
            border-color: {token.interactive};
            color: {token.interactive};
        }}
        QPushButton:focus, QToolButton:focus {{
            border: 2px solid {token.focus};
        }}
        QPushButton#PrimaryButton {{
            color: {"#08111F" if dark else "#FFFFFF"};
            background: {token.interactive};
            border-color: {token.interactive};
            font-weight: 600;
        }}
        QPushButton#PrimaryButton:hover {{
            background: {token.interactive_hover};
        }}
        QSlider::groove:horizontal {{
            height: 6px;
            border-radius: 3px;
            background: {token.outline};
        }}
        QSlider::handle:horizontal {{
            width: 18px;
            margin: -7px 0;
            border: 2px solid {token.surface};
            border-radius: 9px;
            background: {token.interactive};
        }}
        QSlider:focus {{
            border: 1px solid {token.focus};
            border-radius: 4px;
        }}
        QProgressBar {{
            min-height: 12px;
            max-height: 12px;
            border: none;
            border-radius: 6px;
            background: {token.outline};
            text-align: center;
        }}
        QProgressBar::chunk {{
            border-radius: 6px;
            background: {token.normal};
        }}
        QProgressBar[severity="warning"]::chunk {{ background: {token.warning}; }}
        QProgressBar[severity="critical"]::chunk {{ background: {token.critical}; }}
        QProgressBar[important="true"]::chunk {{
            background: {token.important_text};
        }}
        QLabel[severity="normal"] {{ color: {token.normal}; font-weight: 600; }}
        QLabel[severity="warning"] {{ color: {token.warning}; font-weight: 600; }}
        QLabel[severity="critical"] {{ color: {token.critical}; font-weight: 600; }}
        QLabel[important="true"] {{
            color: {token.important_text};
            font-weight: 600;
        }}
        QScrollArea, QScrollArea > QWidget > QWidget {{
            background: transparent;
            border: none;
        }}
        QMenu {{
            background: {token.surface};
            color: {token.on_surface};
            border: 1px solid {token.outline};
            padding: 6px;
        }}
        QMenu::item {{ padding: 7px 24px 7px 12px; border-radius: 5px; }}
        QMenu::item:selected {{ background: {token.surface_alt}; }}
    """
