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
    surface = QColor(token.surface)
    on_surface = QColor(token.on_surface)
    elevation_tint = QColor("#FFFFFF" if dark else "#000000")
    surface_elevated = _mix(surface, elevation_tint, 0.04)
    surface_deep = _mix(surface, elevation_tint, 0.075)
    outline_soft = _mix(surface, on_surface, 0.18)
    accent_soft = _mix(surface, QColor(token.important_text), 0.12)
    interactive_soft = _mix(surface, QColor(token.interactive), 0.12)
    normal_soft = _mix(surface, QColor(token.normal), 0.12)
    warning_soft = _mix(surface, QColor(token.warning), 0.12)
    critical_soft = _mix(surface, QColor(token.critical), 0.11)
    return f"""
        QWidget {{
            color: {token.on_surface};
            font-family: "Microsoft JhengHei UI";
            font-size: 12pt;
        }}
        QFrame#Card {{
            background: qlineargradient(
                x1: 0, y1: 0, x2: 0, y2: 1,
                stop: 0 {token.surface}, stop: 1 {surface_elevated}
            );
            border: 1px solid {outline_soft};
            border-radius: 18px;
        }}
        QFrame#AppearancePanel {{
            background: {surface_deep};
            border: 1px solid {outline_soft};
            border-radius: 13px;
        }}
        QFrame#AppearancePreview {{
            background: {token.surface};
            border: 1px solid {outline_soft};
            border-radius: 9px;
        }}
        QFrame#Header {{
            background: transparent;
            border: none;
        }}
        QFrame#ActionBar {{
            background: transparent;
            border: none;
        }}
        QLabel#BrandMark {{
            color: {token.surface};
            background: {token.important_text};
            border: none;
            border-radius: 11px;
            font-size: 16pt;
            font-weight: 700;
        }}
        QLabel#Title {{
            font-size: 16pt;
            font-weight: 650;
        }}
        QLabel#PanelTitle {{
            font-size: 13pt;
            font-weight: 600;
        }}
        QLabel#FieldLabel, QLabel#SectionLabel {{
            font-size: 10pt;
            font-weight: 600;
            color: {token.on_surface};
        }}
        QLabel#ValuePill {{
            color: {token.important_text};
            background: {accent_soft};
            border: 1px solid {token.important_text};
            border-radius: 8px;
            padding: 2px 8px;
            font-size: 9pt;
            font-weight: 600;
        }}
        QLabel#Muted, QLabel#Metadata, QLabel#ResetLabel {{
            color: {token.on_surface_muted};
            font-size: 10pt;
        }}
        QLabel#StatusLabel {{
            border: 1px solid {outline_soft};
            border-radius: 9px;
            padding: 3px 9px;
            font-size: 9pt;
            font-weight: 600;
        }}
        QLabel#StatusLabel[connection="ready"] {{
            color: {token.normal};
            background: {normal_soft};
            border-color: {token.normal};
        }}
        QLabel#StatusLabel[connection="working"] {{
            color: {token.interactive};
            background: {interactive_soft};
            border-color: {token.interactive};
        }}
        QLabel#StatusLabel[connection="warning"] {{
            color: {token.critical};
            background: {critical_soft};
            border-color: {token.critical};
        }}
        QLabel#StatusLabel[connection="neutral"] {{
            color: {token.on_surface_muted};
            background: {surface_deep};
        }}
        QLabel#ErrorBanner {{
            background: {critical_soft};
            color: {token.critical};
            border: 1px solid {token.critical};
            border-radius: 10px;
            padding: 10px;
        }}
        QFrame#UsageRow {{
            background: {surface_elevated};
            border: 1px solid {outline_soft};
            border-radius: 13px;
        }}
        QFrame#UsageRow[available="false"] {{
            background: {surface_deep};
            border-style: dashed;
        }}
        QFrame#UsageAccent {{
            background: {token.important_text};
            border: none;
            border-radius: 2px;
        }}
        QFrame#UsageAccent[available="false"] {{
            background: {outline_soft};
        }}
        QFrame#MetadataCard {{
            background: {surface_deep};
            border: 1px solid {outline_soft};
            border-radius: 11px;
        }}
        QLabel#UsageTitle {{
            font-size: 12pt;
            font-weight: 600;
        }}
        QLabel#UsagePercent {{
            font-weight: 650;
        }}
        QLabel#UsageUnavailable {{
            color: {token.on_surface_muted};
            font-size: 15pt;
            font-weight: 600;
        }}
        QLabel#WindowChip {{
            color: {token.on_surface_muted};
            background: {token.surface};
            border: 1px solid {outline_soft};
            border-radius: 8px;
            padding: 3px 7px;
            font-size: 9pt;
        }}
        QPushButton, QToolButton {{
            min-height: 36px;
            border: 1px solid {outline_soft};
            border-radius: 9px;
            padding: 2px 10px;
            background: {surface_elevated};
            color: {token.on_surface};
        }}
        QPushButton:hover, QToolButton:hover {{
            border-color: {token.interactive};
            background: {interactive_soft};
        }}
        QToolButton#HeaderButton {{
            min-width: 34px;
            min-height: 34px;
            max-width: 34px;
            max-height: 34px;
            padding: 0;
            border: 1px solid transparent;
            border-radius: 10px;
            background: transparent;
            font-size: 14pt;
        }}
        QToolButton#HeaderButton:hover {{
            border-color: {outline_soft};
            background: {surface_deep};
        }}
        QToolButton:checked {{
            border-color: {token.interactive};
            color: {token.interactive};
        }}
        QToolButton#HeaderButton:checked {{
            border-color: {token.important_text};
            color: {token.important_text};
            background: {accent_soft};
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
        QPushButton#SecondaryButton {{
            background: transparent;
        }}
        QPushButton#ColorButton {{
            text-align: left;
            font-weight: 600;
        }}
        QPushButton#ActionButton {{
            min-height: 40px;
            background: {token.surface};
            border-color: {outline_soft};
            font-size: 10pt;
            font-weight: 600;
        }}
        QPushButton#ActionButton:hover {{
            background: {interactive_soft};
            border-color: {token.interactive};
        }}
        QPushButton#ActionButton:checked {{
            color: {token.important_text};
            background: {accent_soft};
            border-color: {token.important_text};
        }}
        QPushButton#ActionButton[busy="true"] {{
            color: {token.interactive};
            background: {interactive_soft};
        }}
        QSlider::groove:horizontal {{
            height: 8px;
            border-radius: 4px;
            background: {outline_soft};
        }}
        QSlider::sub-page:horizontal {{
            border-radius: 4px;
            background: {token.interactive};
        }}
        QSlider::add-page:horizontal {{
            border-radius: 4px;
            background: {outline_soft};
        }}
        QSlider::handle:horizontal {{
            width: 22px;
            margin: -7px 0;
            border: 3px solid {token.surface};
            border-radius: 11px;
            background: {token.interactive};
        }}
        QSlider:focus {{
            border: 2px solid {token.focus};
            border-radius: 6px;
        }}
        QProgressBar {{
            min-height: 10px;
            max-height: 10px;
            border: none;
            border-radius: 5px;
            background: {outline_soft};
            text-align: center;
        }}
        QProgressBar::chunk {{
            border-radius: 5px;
            background: {token.normal};
        }}
        QProgressBar[severity="warning"]::chunk {{ background: {token.warning}; }}
        QProgressBar[severity="critical"]::chunk {{ background: {token.critical}; }}
        QProgressBar[important="true"]::chunk {{
            background: {token.important_text};
        }}
        QLabel#StatusBadge {{
            border: 1px solid {outline_soft};
            border-radius: 8px;
            padding: 3px 7px;
            font-size: 9pt;
            font-weight: 600;
        }}
        QLabel#StatusBadge[severity="normal"] {{
            color: {token.normal};
            background: {normal_soft};
            border-color: {token.normal};
            font-weight: 600;
        }}
        QLabel#StatusBadge[severity="warning"] {{
            color: {token.warning};
            background: {warning_soft};
            border-color: {token.warning};
            font-weight: 600;
        }}
        QLabel#StatusBadge[severity="critical"] {{
            color: {token.critical};
            background: {critical_soft};
            border-color: {token.critical};
            font-weight: 600;
        }}
        QLabel#StatusBadge[severity="unavailable"] {{
            color: {token.on_surface_muted};
            background: {surface_deep};
            border-color: {outline_soft};
        }}
        QLabel[important="true"] {{
            color: {token.important_text};
            font-weight: 600;
        }}
        QScrollArea, QScrollArea > QWidget > QWidget {{
            background: transparent;
            border: none;
        }}
        QScrollBar:vertical {{
            width: 8px;
            margin: 2px 0;
            border: none;
            background: transparent;
        }}
        QScrollBar::handle:vertical {{
            min-height: 28px;
            border-radius: 4px;
            background: {outline_soft};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0;
        }}
        QMenu {{
            background: {token.surface};
            color: {token.on_surface};
            border: 1px solid {outline_soft};
            padding: 6px;
        }}
        QMenu::item {{ padding: 7px 24px 7px 12px; border-radius: 5px; }}
        QMenu::item:selected {{ background: {interactive_soft}; }}
    """
