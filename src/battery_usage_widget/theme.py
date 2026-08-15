from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication


@dataclass(frozen=True, slots=True)
class ThemeTokens:
    surface: str
    surface_alt: str
    battery_surface: str
    details_surface: str
    controls_surface: str
    on_surface: str
    on_surface_muted: str
    outline: str
    charging: str
    normal: str
    normal_fill_start: str
    normal_fill_end: str
    decorative_secondary: str
    decorative_tertiary: str
    decorative_quaternary: str
    warning: str
    critical: str
    focus: str


LIGHT_TOKENS = ThemeTokens(
    surface="#FFFCF5",
    surface_alt="#FFF7E8",
    battery_surface="#FFF1D6",
    details_surface="#EEF8F2",
    controls_surface="#F5EEFC",
    on_surface="#2D241B",
    on_surface_muted="#665747",
    outline="#E4CDA6",
    charging="#236BAA",
    normal="#7D4A0C",
    normal_fill_start="#F6C85F",
    normal_fill_end="#F0A35B",
    decorative_secondary="#A94638",
    decorative_tertiary="#316B59",
    decorative_quaternary="#67569A",
    warning="#795600",
    critical="#A8322A",
    focus="#245F9E",
)

DARK_TOKENS = ThemeTokens(
    surface="#28241F",
    surface_alt="#373128",
    battery_surface="#3A3023",
    details_surface="#2C3731",
    controls_surface="#342F3B",
    on_surface="#FFF9EF",
    on_surface_muted="#D8CBB8",
    outline="#6E604C",
    charging="#7BBFFF",
    normal="#FFD48A",
    normal_fill_start="#E8B84F",
    normal_fill_end="#E99B55",
    decorative_secondary="#FF9D86",
    decorative_tertiary="#8BD5BC",
    decorative_quaternary="#C8BAF6",
    warning="#F2C14E",
    critical="#FF8B84",
    focus="#7AB8FF",
)


def is_dark_theme() -> bool:
    return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark


def _with_alpha(color: str, alpha: int) -> str:
    value = QColor(color)
    return f"rgba({value.red()}, {value.green()}, {value.blue()}, {alpha})"


def build_stylesheet(dark: bool) -> str:
    token = DARK_TOKENS if dark else LIGHT_TOKENS
    normal_soft = _with_alpha(token.normal_fill_start, 54)
    secondary_soft = _with_alpha(token.decorative_secondary, 26)
    tertiary_soft = _with_alpha(token.decorative_tertiary, 24)
    quaternary_soft = _with_alpha(token.decorative_quaternary, 26)
    tertiary_border = _with_alpha(token.decorative_tertiary, 92)
    quaternary_border = _with_alpha(token.decorative_quaternary, 86)
    charging_soft = _with_alpha(token.charging, 32)
    warning_soft = _with_alpha(token.warning, 30)
    critical_soft = _with_alpha(token.critical, 30)
    return f"""
        QWidget {{
            color: {token.on_surface};
            font-family: "Segoe UI Variable", "Microsoft JhengHei UI", "Segoe UI";
            font-size: 12pt;
        }}
        QFrame#Card {{
            background: qlineargradient(
                x1: 0, y1: 0, x2: 1, y2: 1,
                stop: 0 {token.surface}, stop: 0.72 {token.surface},
                stop: 1 {token.surface_alt}
            );
            border: 1px solid {token.outline};
            border-radius: 18px;
        }}
        QFrame#Header {{ background: transparent; border: none; }}
        QLabel#BrandMark {{
            color: {token.surface};
            background: qlineargradient(
                x1: 0, y1: 0, x2: 1, y2: 1,
                stop: 0 {token.decorative_secondary},
                stop: 0.52 {token.normal_fill_end},
                stop: 1 {token.normal_fill_start}
            );
            border: none;
            border-radius: 11px;
            font-size: 17pt;
            font-weight: 700;
        }}
        QLabel#Title {{ font-size: 16pt; font-weight: 650; }}
        QLabel#Muted, QLabel#Metadata {{
            color: {token.on_surface_muted};
            font-size: 10pt;
        }}
        QLabel#StatusLabel {{
            color: {token.normal};
            background: {normal_soft};
            border: 1px solid {token.normal_fill_end};
            border-radius: 9px;
            padding: 3px 9px;
            font-size: 9pt;
            font-weight: 600;
        }}
        QLabel#ErrorBanner {{
            color: {token.critical};
            background: {critical_soft};
            border: 1px solid {token.critical};
            border-radius: 10px;
            padding: 9px;
        }}
        QFrame#BatteryCard {{
            background: qlineargradient(
                x1: 0, y1: 0, x2: 1, y2: 1,
                stop: 0 {token.battery_surface},
                stop: 0.72 {token.surface_alt},
                stop: 1 {secondary_soft}
            );
            border: 1px solid {token.normal_fill_end};
            border-radius: 13px;
        }}
        QFrame#DetailsCard {{
            background: qlineargradient(
                x1: 0, y1: 0, x2: 1, y2: 1,
                stop: 0 {token.details_surface},
                stop: 0.78 {token.surface_alt},
                stop: 1 {tertiary_soft}
            );
            border: 1px solid {tertiary_border};
            border-radius: 13px;
        }}
        QFrame#TransparencyCard {{
            background: qlineargradient(
                x1: 0, y1: 0, x2: 1, y2: 1,
                stop: 0 {token.controls_surface},
                stop: 0.72 {token.surface_alt},
                stop: 1 {quaternary_soft}
            );
            border: 1px solid {quaternary_border};
            border-radius: 13px;
        }}
        QLabel#BatteryPercent {{ font-size: 28pt; font-weight: 700; }}
        QLabel#StateBadge {{
            border: 1px solid {token.outline};
            border-radius: 9px;
            padding: 4px 8px;
            font-size: 10pt;
            font-weight: 600;
        }}
        QLabel#StateBadge[state="charging"] {{
            color: {token.charging};
            background: {charging_soft};
            border-color: {token.charging};
        }}
        QLabel#StateBadge[state="normal"] {{
            color: {token.normal};
            background: {normal_soft};
            border-color: {token.normal_fill_end};
        }}
        QLabel#StateBadge[state="warning"] {{
            color: {token.warning};
            background: {warning_soft};
            border-color: {token.warning};
        }}
        QLabel#StateBadge[state="critical"] {{
            color: {token.critical};
            background: {critical_soft};
            border-color: {token.critical};
        }}
        QLabel#StateBadge[state="neutral"] {{ color: {token.on_surface_muted}; }}
        QLabel#Summary {{ color: {token.on_surface_muted}; font-size: 11pt; }}
        QLabel#DetailLabel {{ color: {token.on_surface_muted}; font-size: 10pt; }}
        QLabel#DetailValue {{
            color: {token.decorative_tertiary};
            font-size: 10pt;
            font-weight: 600;
        }}
        QLabel#TransparencyLabel {{
            color: {token.decorative_quaternary};
            font-size: 10pt;
        }}
        QLabel#TransparencyValue {{
            color: {token.normal};
            background: qlineargradient(
                x1: 0, y1: 0, x2: 1, y2: 0,
                stop: 0 {normal_soft}, stop: 1 {secondary_soft}
            );
            border: 1px solid {token.normal_fill_end};
            border-radius: 8px;
            padding: 3px 6px;
            font-size: 9pt;
            font-weight: 600;
        }}
        QSlider::groove:horizontal {{
            height: 8px;
            border-radius: 4px;
            background: {token.outline};
        }}
        QSlider::sub-page:horizontal {{
            border-radius: 4px;
            background: qlineargradient(
                x1: 0, y1: 0, x2: 1, y2: 0,
                stop: 0 {token.normal_fill_start},
                stop: 0.62 {token.normal_fill_end},
                stop: 1 {token.decorative_secondary}
            );
        }}
        QSlider::add-page:horizontal {{
            border-radius: 4px;
            background: {token.outline};
        }}
        QSlider::handle:horizontal {{
            width: 22px;
            margin: -7px 0;
            border: 3px solid {token.surface_alt};
            border-radius: 11px;
            background: {token.decorative_quaternary};
        }}
        QSlider:focus {{
            border: 2px solid {token.focus};
            border-radius: 6px;
        }}
        QProgressBar#BatteryProgress {{
            min-height: 14px;
            max-height: 14px;
            border: none;
            border-radius: 7px;
            background: {token.outline};
        }}
        QProgressBar#BatteryProgress::chunk {{
            border-radius: 7px;
            background: qlineargradient(
                x1: 0, y1: 0, x2: 1, y2: 0,
                stop: 0 {token.normal_fill_start},
                stop: 0.55 {token.normal_fill_end},
                stop: 1 {token.decorative_secondary}
            );
        }}
        QProgressBar#BatteryProgress[state="charging"]::chunk {{
            background: {token.charging};
        }}
        QProgressBar#BatteryProgress[state="warning"]::chunk {{
            background: {token.warning};
        }}
        QProgressBar#BatteryProgress[state="critical"]::chunk {{
            background: {token.critical};
        }}
        QPushButton, QToolButton {{
            min-height: 36px;
            border: 1px solid {token.outline};
            border-radius: 9px;
            padding: 2px 10px;
            background: {token.surface_alt};
            color: {token.on_surface};
        }}
        QPushButton:hover, QToolButton:hover {{
            background: {quaternary_soft};
            border-color: {token.decorative_quaternary};
        }}
        QPushButton:focus, QToolButton:focus {{ border: 2px solid {token.focus}; }}
        QToolButton#HeaderButton {{
            min-width: 36px;
            max-width: 36px;
            min-height: 36px;
            max-height: 36px;
            padding: 0;
            background: transparent;
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
