from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication


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


LIGHT_TOKENS = ThemeTokens(
    surface="#FCFAF8",
    surface_alt="#F4EEE9",
    on_surface="#28211D",
    on_surface_muted="#675B54",
    outline="#D9CCC4",
    interactive="#9C4529",
    interactive_hover="#7F351E",
    normal="#197A55",
    warning="#8A5C00",
    critical="#B42318",
    focus="#0067C0",
)

DARK_TOKENS = ThemeTokens(
    surface="#25211F",
    surface_alt="#302B28",
    on_surface="#F8F2EE",
    on_surface_muted="#C9BBB2",
    outline="#5A4E48",
    interactive="#E58B6B",
    interactive_hover="#F1A083",
    normal="#66D6A3",
    warning="#F2C14E",
    critical="#FF8B84",
    focus="#7AB8FF",
)


def is_dark_theme() -> bool:
    return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark


def build_stylesheet(dark: bool) -> str:
    token = DARK_TOKENS if dark else LIGHT_TOKENS
    primary_text = "#241813" if dark else "#FFFFFF"
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
        QFrame#Header {{ background: transparent; border: none; }}
        QLabel#Title {{ font-size: 15pt; font-weight: 600; }}
        QLabel#Muted, QLabel#Metadata, QLabel#ResetLabel {{
            color: {token.on_surface_muted};
            font-size: 10pt;
        }}
        QLabel#StatusLabel {{ color: {token.on_surface_muted}; font-size: 9pt; }}
        QLabel#ErrorBanner {{
            background: {token.surface_alt};
            color: {token.critical};
            border: 1px solid {token.critical};
            border-radius: 8px;
            padding: 8px;
        }}
        QLabel#NoticeBanner {{
            background: {token.surface_alt};
            color: {token.normal};
            border: 1px solid {token.normal};
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
        QPushButton:hover, QToolButton:hover {{ border-color: {token.interactive}; }}
        QPushButton:focus, QToolButton:focus {{ border: 2px solid {token.focus}; }}
        QPushButton#PrimaryButton {{
            color: {primary_text};
            background: {token.interactive};
            border-color: {token.interactive};
            font-weight: 600;
        }}
        QPushButton#PrimaryButton:hover {{ background: {token.interactive_hover}; }}
        QProgressBar {{
            min-height: 12px;
            max-height: 12px;
            border: none;
            border-radius: 6px;
            background: {token.outline};
        }}
        QProgressBar::chunk {{ border-radius: 6px; background: {token.normal}; }}
        QProgressBar[severity="warning"]::chunk {{ background: {token.warning}; }}
        QProgressBar[severity="critical"]::chunk {{ background: {token.critical}; }}
        QLabel[severity="normal"] {{ color: {token.normal}; font-weight: 600; }}
        QLabel[severity="warning"] {{ color: {token.warning}; font-weight: 600; }}
        QLabel[severity="critical"] {{ color: {token.critical}; font-weight: 600; }}
        QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
        QMenu {{
            background: {token.surface};
            color: {token.on_surface};
            border: 1px solid {token.outline};
            padding: 6px;
        }}
        QMenu::item {{ padding: 7px 24px 7px 12px; border-radius: 5px; }}
        QMenu::item:selected {{ background: {token.surface_alt}; }}
    """
