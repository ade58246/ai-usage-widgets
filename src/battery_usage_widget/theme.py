from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication


@dataclass(frozen=True, slots=True)
class ThemeTokens:
    surface: str
    surface_alt: str
    on_surface: str
    on_surface_muted: str
    outline: str
    charging: str
    normal: str
    warning: str
    critical: str
    focus: str


LIGHT_TOKENS = ThemeTokens(
    surface="#FFFBF6",
    surface_alt="#FFF1DE",
    on_surface="#2B1D12",
    on_surface_muted="#6F5743",
    outline="#E7C5A0",
    charging="#0B6FCC",
    normal="#A74400",
    warning="#806000",
    critical="#B42318",
    focus="#0067C0",
)

DARK_TOKENS = ThemeTokens(
    surface="#2B2119",
    surface_alt="#3B2C20",
    on_surface="#FFF7EF",
    on_surface_muted="#D7C0AA",
    outline="#72553E",
    charging="#70B7FF",
    normal="#FFB15C",
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
    normal_soft = _with_alpha(token.normal, 32)
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
            background: {token.surface};
            border: 1px solid {token.outline};
            border-radius: 18px;
        }}
        QFrame#Header {{ background: transparent; border: none; }}
        QLabel#BrandMark {{
            color: {token.surface};
            background: {token.normal};
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
            border: 1px solid {token.normal};
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
        QFrame#BatteryCard, QFrame#DetailsCard, QFrame#TransparencyCard {{
            background: {token.surface_alt};
            border: 1px solid {token.outline};
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
            border-color: {token.normal};
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
        QLabel#DetailValue {{ font-size: 10pt; font-weight: 600; }}
        QLabel#TransparencyLabel {{
            color: {token.on_surface_muted};
            font-size: 10pt;
        }}
        QLabel#TransparencyValue {{
            color: {token.normal};
            background: {normal_soft};
            border: 1px solid {token.normal};
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
            background: {token.normal};
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
            background: {token.normal};
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
            background: {token.normal};
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
        QPushButton:hover, QToolButton:hover {{ border-color: {token.charging}; }}
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
