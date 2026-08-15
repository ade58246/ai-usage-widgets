from __future__ import annotations

import time
from collections.abc import Iterable

from PySide6.QtCore import QByteArray, QDateTime, QLocale, QPoint, QSettings, Qt, QTimer, Signal
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QColor,
    QFont,
    QGuiApplication,
    QKeyEvent,
    QMouseEvent,
    QMoveEvent,
    QShowEvent,
)
from PySide6.QtWidgets import (
    QColorDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QMenu,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QStackedWidget,
    QSystemTrayIcon,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from codex_usage_widget.autostart import AutostartManager
from codex_usage_widget.icon_factory import create_meter_icon
from codex_usage_widget.models import ConnectionState, RateLimitWindowView, UsageSnapshot
from codex_usage_widget.theme import build_stylesheet, is_dark_theme

MIN_OPACITY_PERCENT = 35
MAX_OPACITY_PERCENT = 100


def format_duration(minutes: int | None) -> str:
    if minutes is None:
        return "時間窗未知"
    if minutes >= 1_440 and minutes % 1_440 == 0:
        days = minutes // 1_440
        return f"{days} 天"
    if minutes >= 60 and minutes % 60 == 0:
        hours = minutes // 60
        return f"{hours} 小時"
    return f"{minutes} 分鐘"


def format_quota_window(minutes: int | None) -> str:
    if minutes is None:
        return "額度時間窗未知"
    return f"{format_duration(minutes)}額度"


def format_countdown(timestamp: int | None, *, now: int | None = None) -> str:
    if timestamp is None:
        return "重設時間未知"
    remaining = max(0, timestamp - (int(time.time()) if now is None else now))
    if remaining == 0:
        return "即將重設"
    days, remainder = divmod(remaining, 86_400)
    hours, remainder = divmod(remainder, 3_600)
    minutes, seconds = divmod(remainder, 60)
    if days:
        return f"{days} 天 {hours} 小時後重設"
    if hours:
        return f"{hours} 小時 {minutes} 分後重設"
    if minutes:
        return f"{minutes} 分 {seconds} 秒後重設"
    return f"{seconds} 秒後重設"


def format_absolute_time(timestamp: int | None) -> str:
    if timestamp is None:
        return "伺服器未提供重設時間"
    date_time = QDateTime.fromSecsSinceEpoch(timestamp).toLocalTime()
    formatted = QLocale.system().toString(date_time, QLocale.FormatType.ShortFormat)
    return f"本地重設時間：{formatted}"


def severity_for(window: RateLimitWindowView) -> tuple[str, str]:
    if window.reached_type:
        return "critical", "已達上限"
    if window.remaining_percent < 20:
        return "critical", "緊迫"
    if window.remaining_percent <= 50:
        return "warning", "注意"
    return "normal", "正常"


def _refresh_style(widget: QWidget) -> None:
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


class DraggableHeader(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Header")
        self._drag_offset: QPoint | None = None

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = (
                event.globalPosition().toPoint() - self.window().frameGeometry().topLeft()
            )
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.window().move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_offset = None
        super().mouseReleaseEvent(event)


class AppearancePanel(QFrame):
    appearance_changed = Signal(int, object)
    close_requested = Signal()

    def __init__(
        self,
        opacity_percent: int,
        important_text_color: str | None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("AppearancePanel")
        self._important_text_color = self._normalize_color(important_text_color)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(10)

        heading = QHBoxLayout()
        heading.setSpacing(6)
        title_column = QVBoxLayout()
        title_column.setSpacing(1)
        title = QLabel("外觀與可讀性")
        title.setObjectName("PanelTitle")
        description = QLabel("即時調整透明度；重點色會同步套用文字與用量條。")
        description.setObjectName("Muted")
        description.setWordWrap(True)
        title_column.addWidget(title)
        title_column.addWidget(description)
        heading.addLayout(title_column, 1)
        self.done_button = QToolButton()
        self.done_button.setText("收合")
        self.done_button.setToolTip("收合介面外觀調整")
        self.done_button.setAccessibleName("收合介面外觀調整")
        self.done_button.clicked.connect(self.close_requested.emit)
        heading.addWidget(self.done_button)
        layout.addLayout(heading)

        opacity_heading = QHBoxLayout()
        opacity_label = QLabel("介面透明度")
        opacity_label.setObjectName("FieldLabel")
        self.opacity_value_label = QLabel()
        self.opacity_value_label.setObjectName("ValuePill")
        opacity_heading.addWidget(opacity_label)
        opacity_heading.addStretch(1)
        opacity_heading.addWidget(self.opacity_value_label)
        layout.addLayout(opacity_heading)

        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(MIN_OPACITY_PERCENT, MAX_OPACITY_PERCENT)
        self.opacity_slider.setValue(
            max(MIN_OPACITY_PERCENT, min(MAX_OPACITY_PERCENT, opacity_percent))
        )
        self.opacity_slider.setSingleStep(5)
        self.opacity_slider.setPageStep(10)
        self.opacity_slider.setTracking(True)
        self.opacity_slider.setMinimumHeight(30)
        self.opacity_slider.setAccessibleName("介面透明度")
        self.opacity_slider.setAccessibleDescription(
            f"可調整為 {MIN_OPACITY_PERCENT}% 到 {MAX_OPACITY_PERCENT}%"
        )
        self.opacity_slider.valueChanged.connect(self._opacity_changed)
        layout.addWidget(self.opacity_slider)

        color_label = QLabel("重點資訊顏色")
        color_label.setObjectName("FieldLabel")
        layout.addWidget(color_label)

        color_row = QHBoxLayout()
        color_row.setSpacing(8)
        self.color_swatch = QFrame()
        self.color_swatch.setObjectName("ColorSwatch")
        self.color_swatch.setFixedSize(30, 30)
        self.color_swatch.setAccessibleName("目前重點資訊顏色")
        color_row.addWidget(self.color_swatch)
        self.color_button = QPushButton()
        self.color_button.setObjectName("ColorButton")
        self.color_button.setAccessibleName("選擇重點文字顏色")
        self.color_button.clicked.connect(self._choose_color)
        color_row.addWidget(self.color_button, 1)
        self.color_value_label = QLabel()
        self.color_value_label.setObjectName("Metadata")
        color_row.addWidget(self.color_value_label)
        layout.addLayout(color_row)

        preview = QFrame()
        preview.setObjectName("AppearancePreview")
        preview_layout = QVBoxLayout(preview)
        preview_layout.setContentsMargins(10, 8, 10, 8)
        preview_layout.setSpacing(5)
        preview_heading = QHBoxLayout()
        preview_caption = QLabel("顏色效果預覽")
        preview_caption.setObjectName("Metadata")
        self.preview_label = QLabel("重要文字")
        self.preview_label.setProperty("important", True)
        preview_heading.addWidget(preview_caption)
        preview_heading.addStretch(1)
        preview_heading.addWidget(self.preview_label)
        preview_layout.addLayout(preview_heading)
        self.preview_bar = QProgressBar()
        self.preview_bar.setRange(0, 100)
        self.preview_bar.setValue(100)
        self.preview_bar.setTextVisible(False)
        self.preview_bar.setProperty("important", True)
        self.preview_bar.setAccessibleName("重點顏色示意色條")
        preview_layout.addWidget(self.preview_bar)
        self.preview_note = QLabel("僅供外觀預覽，不代表剩餘用量。")
        self.preview_note.setObjectName("Metadata")
        self.preview_note.setWordWrap(True)
        preview_layout.addWidget(self.preview_note)
        layout.addWidget(preview)

        buttons = QHBoxLayout()
        self.reset_button = QPushButton("恢復預設")
        self.reset_button.setObjectName("SecondaryButton")
        self.reset_button.setToolTip("清除自訂重點文字色並將透明度恢復為 100%")
        self.reset_button.clicked.connect(self._reset_defaults)
        buttons.addWidget(self.reset_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        self._update_opacity_label()
        self._update_color_button()

    @property
    def opacity_percent(self) -> int:
        return self.opacity_slider.value()

    @property
    def important_text_color(self) -> str | None:
        return self._important_text_color

    @staticmethod
    def _normalize_color(value: str | None) -> str | None:
        color = QColor(value or "")
        return color.name() if color.isValid() else None

    def _opacity_changed(self, _value: int) -> None:
        self._update_opacity_label()
        self.appearance_changed.emit(self.opacity_percent, self.important_text_color)

    def _update_opacity_label(self) -> None:
        self.opacity_value_label.setText(f"{self.opacity_percent}%")

    def _choose_color(self) -> None:
        initial = QColor(self._important_text_color or "#0B63CE")
        selected = QColorDialog.getColor(initial, self, "選擇 Codex 重點文字顏色")
        if not selected.isValid():
            return
        self._important_text_color = selected.name()
        self._update_color_button()
        self.appearance_changed.emit(self.opacity_percent, self.important_text_color)

    def _update_color_button(self) -> None:
        if self._important_text_color is None:
            color = QColor("#69A9FF" if is_dark_theme() else "#0B63CE")
            self.color_button.setText("選擇顏色…")
            self.color_value_label.setText("系統預設")
        else:
            color = QColor(self._important_text_color)
            self.color_button.setText("變更顏色…")
            self.color_value_label.setText(color.name().upper())
        self.color_swatch.setStyleSheet(
            f"background: {color.name()}; border: 2px solid rgba(255, 255, 255, 150);"
            "border-radius: 9px;"
        )

    def _reset_defaults(self) -> None:
        self.opacity_slider.blockSignals(True)
        self.opacity_slider.setValue(MAX_OPACITY_PERCENT)
        self.opacity_slider.blockSignals(False)
        self._important_text_color = None
        self._update_opacity_label()
        self._update_color_button()
        self.appearance_changed.emit(self.opacity_percent, self.important_text_color)

    def set_appearance(self, opacity_percent: int, important_text_color: str | None) -> None:
        self.opacity_slider.blockSignals(True)
        self.opacity_slider.setValue(
            max(MIN_OPACITY_PERCENT, min(MAX_OPACITY_PERCENT, opacity_percent))
        )
        self.opacity_slider.blockSignals(False)
        self._important_text_color = self._normalize_color(important_text_color)
        self._update_opacity_label()
        self._update_color_button()


class UsageRow(QFrame):
    def __init__(self, window: RateLimitWindowView, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("UsageRow")
        self.window_data = window

        outer_layout = QHBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)
        accent = QFrame()
        accent.setObjectName("UsageAccent")
        accent.setFixedWidth(5)
        accent.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        outer_layout.addWidget(accent)

        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)
        outer_layout.addWidget(body, 1)

        heading = QHBoxLayout()
        title = QLabel(window.label)
        title.setObjectName("UsageTitle")
        title.setProperty("important", True)
        self.title_label = title
        title.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        title.setWordWrap(True)
        duration_text = format_quota_window(window.window_duration_mins)
        duration = QLabel(duration_text)
        duration.setObjectName("WindowChip")
        duration.setToolTip(f"Codex 回傳的 {window.window_kind} 時間窗")
        self.duration_label = duration
        heading.addWidget(title)
        heading.addWidget(duration, 0, Qt.AlignmentFlag.AlignRight)
        layout.addLayout(heading)

        value_row = QHBoxLayout()
        percent = QLabel(f"{window.remaining_percent}% 剩餘")
        percent.setObjectName("UsagePercent")
        percent_font = percent.font()
        percent_font.setPointSizeF(max(19.0, percent_font.pointSizeF() * 1.5))
        percent_font.setWeight(QFont.Weight.DemiBold)
        percent.setFont(percent_font)
        percent.setProperty("important", True)
        self.percent_label = percent
        severity, severity_label = severity_for(window)
        percent.setProperty("severity", severity)
        badge = QLabel(f"● {severity_label}")
        badge.setObjectName("StatusBadge")
        badge.setProperty("severity", severity)
        value_row.addWidget(percent)
        value_row.addStretch(1)
        value_row.addWidget(badge)
        layout.addLayout(value_row)

        progress = QProgressBar()
        progress.setObjectName("UsageProgress")
        progress.setRange(0, 100)
        progress.setValue(window.remaining_percent)
        progress.setTextVisible(False)
        progress.setMinimumHeight(10)
        progress.setProperty("severity", severity)
        progress.setProperty("important", True)
        self.progress_bar = progress
        progress.setAccessibleName(f"{window.label} {duration_text}剩餘用量")
        progress.setAccessibleDescription(f"剩餘 {window.remaining_percent}%，狀態{severity_label}")
        layout.addWidget(progress)

        self.reset_label = QLabel()
        self.reset_label.setObjectName("ResetLabel")
        self.reset_label.setProperty("important", True)
        self.reset_label.setWordWrap(True)
        layout.addWidget(self.reset_label)
        self.update_countdown()

    def update_countdown(self) -> None:
        timestamp = self.window_data.resets_at
        self.reset_label.setText(f"⏱ {format_countdown(timestamp)}")
        self.reset_label.setToolTip(format_absolute_time(timestamp))


class FloatingUsageWidget(QWidget):
    refresh_requested = Signal()
    login_requested = Signal()
    exit_requested = Signal()

    def __init__(
        self,
        settings: QSettings,
        autostart: AutostartManager,
        *,
        enable_tray: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.settings = settings
        self.autostart = autostart
        self._snapshot: UsageSnapshot | None = None
        self._usage_rows: list[UsageRow] = []
        self._quitting = False
        self._position_initialized = False
        self._opacity_percent = self._load_opacity_setting()
        self._important_text_color = self._load_important_text_color_setting()

        self._appearance_sync_timer = QTimer(self)
        self._appearance_sync_timer.setSingleShot(True)
        self._appearance_sync_timer.setInterval(300)
        self._appearance_sync_timer.timeout.connect(self.settings.sync)

        self.setObjectName("FloatingUsageWidget")
        self.setWindowTitle("Codex 剩餘用量")
        self.setWindowIcon(create_meter_icon())
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMinimumWidth(340)
        self.setMaximumWidth(460)
        self.resize(380, 320)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(11, 11, 11, 14)
        self.card = QFrame()
        self.card.setObjectName("Card")
        shadow = QGraphicsDropShadowEffect(self.card)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 5)
        shadow.setColor(QColor(0, 0, 0, 72))
        self.card.setGraphicsEffect(shadow)
        outer.addWidget(self.card)

        self.card_layout = QVBoxLayout(self.card)
        self.card_layout.setContentsMargins(18, 16, 18, 16)
        self.card_layout.setSpacing(12)

        header = DraggableHeader()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(6)
        brand_mark = QLabel("C")
        brand_mark.setObjectName("BrandMark")
        brand_mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand_mark.setFixedSize(38, 38)
        brand_mark.setAccessibleName("Codex")
        header_layout.addWidget(brand_mark)
        title_column = QVBoxLayout()
        title_column.setSpacing(2)
        title = QLabel("Codex 剩餘用量")
        title.setObjectName("Title")
        self.account_label = QLabel("正在連線…")
        self.account_label.setObjectName("Muted")
        self.account_label.setWordWrap(True)
        title_column.addWidget(title)
        title_column.addWidget(self.account_label)
        header_layout.addLayout(title_column, 1)

        self.close_button = QToolButton()
        self.close_button.setObjectName("HeaderButton")
        self.close_button.setText("×")
        self.close_button.setToolTip("縮到系統匣")
        self.close_button.setAccessibleName("縮到系統匣")
        self.close_button.setFixedSize(36, 36)
        self.close_button.clicked.connect(self.close)
        header_layout.addWidget(self.close_button)
        self.card_layout.addWidget(header)

        action_bar = QFrame()
        action_bar.setObjectName("ActionBar")
        action_layout = QHBoxLayout(action_bar)
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setSpacing(8)

        self.appearance_button = QPushButton("外觀與透明度")
        self.appearance_button.setObjectName("ActionButton")
        self.appearance_button.setToolTip("展開透明度與重點資訊顏色設定")
        self.appearance_button.setAccessibleName("顯示介面外觀與透明度調整")
        self.appearance_button.setCheckable(True)
        self.appearance_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.appearance_button.clicked.connect(self._set_appearance_panel_visible)
        action_layout.addWidget(self.appearance_button, 1)

        self.refresh_button = QPushButton("立即更新")
        self.refresh_button.setObjectName("ActionButton")
        self.refresh_button.setToolTip("立即重新讀取 Codex 剩餘用量")
        self.refresh_button.setAccessibleName("立即更新用量")
        self.refresh_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_button.clicked.connect(self.refresh_requested.emit)
        action_layout.addWidget(self.refresh_button, 1)
        self.card_layout.addWidget(action_bar)

        self.appearance_panel = AppearancePanel(
            self._opacity_percent,
            self._important_text_color,
        )
        self.appearance_panel.appearance_changed.connect(self._apply_inline_appearance)
        self.appearance_panel.close_requested.connect(
            lambda: self._set_appearance_panel_visible(False)
        )
        self.appearance_panel.hide()
        self.card_layout.addWidget(self.appearance_panel)

        self.status_label = QLabel("● 啟動中")
        self.status_label.setObjectName("StatusLabel")
        self.status_label.setProperty("connection", "working")
        self.status_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        status_row = QHBoxLayout()
        status_row.setContentsMargins(0, 0, 0, 0)
        status_row.addWidget(
            self.status_label,
            0,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )
        status_row.addStretch(1)
        self.card_layout.addLayout(status_row)

        self.error_banner = QLabel()
        self.error_banner.setObjectName("ErrorBanner")
        self.error_banner.setWordWrap(True)
        self.error_banner.hide()
        self.card_layout.addWidget(self.error_banner)

        self.stack = QStackedWidget()
        self.card_layout.addWidget(self.stack, 1)

        message_page = QWidget()
        message_layout = QVBoxLayout(message_page)
        message_layout.setContentsMargins(4, 18, 4, 18)
        message_layout.setSpacing(12)
        self.message_label = QLabel("正在連線到 Codex app-server…")
        self.message_label.setObjectName("Muted")
        self.message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message_label.setWordWrap(True)
        message_layout.addWidget(self.message_label)
        self.login_button = QPushButton("使用 ChatGPT 登入")
        self.login_button.setObjectName("PrimaryButton")
        self.login_button.setAccessibleName("使用 ChatGPT 登入")
        self.login_button.clicked.connect(self.login_requested.emit)
        self.login_button.hide()
        message_layout.addWidget(self.login_button)
        message_layout.addStretch(1)
        self.stack.addWidget(message_page)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(10)
        self.scroll.setWidget(self.content)
        self.stack.addWidget(self.scroll)

        self.updated_label = QLabel("尚未取得資料")
        self.updated_label.setObjectName("Metadata")
        self.updated_label.setWordWrap(True)
        self.updated_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.card_layout.addWidget(self.updated_label)

        self._countdown_timer = QTimer(self)
        self._countdown_timer.setInterval(1_000)
        self._countdown_timer.timeout.connect(self._update_countdowns)
        self._countdown_timer.start()

        self._save_position_timer = QTimer(self)
        self._save_position_timer.setSingleShot(True)
        self._save_position_timer.setInterval(250)
        self._save_position_timer.timeout.connect(self._save_geometry)

        self.tray_icon: QSystemTrayIcon | None = None
        self.autostart_action: QAction | None = None
        tray_available = enable_tray and QSystemTrayIcon.isSystemTrayAvailable()
        if tray_available:
            self._create_tray()

        self._apply_theme()
        hints = QGuiApplication.styleHints()
        hints.colorSchemeChanged.connect(lambda _scheme: self._apply_theme())
        self.set_connection_state(ConnectionState.STARTING)

    @property
    def tray_available(self) -> bool:
        return bool(self.tray_icon and self.tray_icon.isVisible())

    def show_or_raise(self) -> None:
        self.show()
        self._clamp_to_visible_screen()
        self.raise_()
        self.activateWindow()

    def prepare_quit(self) -> None:
        self._quitting = True
        self._save_geometry()
        if self._appearance_sync_timer.isActive():
            self._appearance_sync_timer.stop()
            self.settings.sync()
        if self.tray_icon:
            self.tray_icon.hide()

    def set_connection_state(self, state: ConnectionState) -> None:
        labels = {
            ConnectionState.STOPPED: "○ 已停止",
            ConnectionState.STARTING: "◌ 正在啟動 Codex",
            ConnectionState.HANDSHAKING: "◌ 正在初始化",
            ConnectionState.CHECKING_ACCOUNT: "◌ 正在檢查帳號",
            ConnectionState.AUTH_REQUIRED: "○ 需要登入",
            ConnectionState.AUTHENTICATING: "◌ 等候瀏覽器登入",
            ConnectionState.READY: "● 已連線",
            ConnectionState.RECONNECTING: "↻ 正在重新連線",
            ConnectionState.MISSING_CLI: "⚠ 找不到 Codex CLI",
            ConnectionState.OUTDATED_CLI: "⚠ Codex CLI 過舊",
            ConnectionState.ERROR: "⚠ 連線異常",
        }
        self.status_label.setText(labels[state])
        if state == ConnectionState.READY:
            connection_style = "ready"
        elif state in {
            ConnectionState.MISSING_CLI,
            ConnectionState.OUTDATED_CLI,
            ConnectionState.ERROR,
        }:
            connection_style = "warning"
        elif state in {ConnectionState.STOPPED, ConnectionState.AUTH_REQUIRED}:
            connection_style = "neutral"
        else:
            connection_style = "working"
        self.status_label.setProperty("connection", connection_style)
        _refresh_style(self.status_label)
        self.login_button.setVisible(state == ConnectionState.AUTH_REQUIRED)
        if state == ConnectionState.AUTH_REQUIRED:
            self.message_label.setText(
                "登入 ChatGPT 後，小工具會透過 Codex app-server 讀取目前帳號的用量。"
            )
            self.stack.setCurrentIndex(0)
        elif state in {ConnectionState.MISSING_CLI, ConnectionState.OUTDATED_CLI}:
            self.stack.setCurrentIndex(0)
        elif state in {
            ConnectionState.STARTING,
            ConnectionState.HANDSHAKING,
            ConnectionState.CHECKING_ACCOUNT,
        }:
            if self._snapshot is None:
                self.message_label.setText("正在連線到 Codex app-server…")
                self.stack.setCurrentIndex(0)
        elif state == ConnectionState.READY and self._snapshot is not None:
            self.stack.setCurrentIndex(1)
        self.refresh_button.setEnabled(state in {ConnectionState.READY, ConnectionState.ERROR})

    def set_refreshing(self, refreshing: bool) -> None:
        self.refresh_button.setText("更新中…" if refreshing else "立即更新")
        self.refresh_button.setProperty("busy", refreshing)
        _refresh_style(self.refresh_button)
        if refreshing and self._snapshot is not None:
            self.status_label.setText("◌ 更新中")
            self.status_label.setProperty("connection", "working")
            _refresh_style(self.status_label)

    def set_account(self, account: object) -> None:
        if not isinstance(account, dict):
            self.account_label.setText("尚未登入 ChatGPT")
            return
        email = account.get("email")
        plan = account.get("planType")
        parts = [part for part in (email, plan) if isinstance(part, str) and part]
        self.account_label.setText(" · ".join(parts) if parts else "ChatGPT 帳號")

    def set_snapshot(self, snapshot: UsageSnapshot) -> None:
        self._snapshot = snapshot
        self.error_banner.hide()
        self._clear_layout(self.content_layout)
        self._usage_rows.clear()

        if snapshot.windows:
            for window in snapshot.windows:
                row = UsageRow(window)
                self.content_layout.addWidget(row)
                self._usage_rows.append(row)
        else:
            empty = QLabel("伺服器沒有回傳可顯示的用量時間窗。")
            empty.setObjectName("Muted")
            empty.setWordWrap(True)
            self.content_layout.addWidget(empty)

        metadata = self._metadata_lines(snapshot)
        if metadata:
            metadata_card = QFrame()
            metadata_card.setObjectName("MetadataCard")
            metadata_layout = QVBoxLayout(metadata_card)
            metadata_layout.setContentsMargins(12, 10, 12, 10)
            metadata_layout.setSpacing(5)
            metadata_heading = QLabel("帳號與額度")
            metadata_heading.setObjectName("SectionLabel")
            metadata_layout.addWidget(metadata_heading)
            for line in metadata:
                label = QLabel(line)
                label.setObjectName("Metadata")
                label.setWordWrap(True)
                metadata_layout.addWidget(label)
            self.content_layout.addWidget(metadata_card)

        self.content_layout.addStretch(1)
        local_time = snapshot.fetched_at.astimezone().strftime("%H:%M:%S")
        stale_text = " · 資料可能已過期" if snapshot.stale else ""
        self.updated_label.setText(f"最後更新：{local_time}{stale_text}")
        self.stack.setCurrentIndex(1)
        self._update_tray_tooltip()
        QTimer.singleShot(0, self._fit_to_screen)

    def set_error(self, message: str) -> None:
        if self._snapshot is not None and not self._snapshot.stale:
            self.set_snapshot(self._snapshot.as_stale())
        self.error_banner.setText(f"⚠ {message}")
        self.error_banner.show()
        if self._snapshot is None:
            self.message_label.setText(message)
            self.stack.setCurrentIndex(0)
        QTimer.singleShot(0, self._fit_to_screen)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            if self.appearance_panel.isVisible():
                self._set_appearance_panel_visible(False)
                event.accept()
                return
            if self.tray_available:
                self.hide()
            else:
                self.exit_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._save_geometry()
        if not self._quitting and self.tray_available:
            self.hide()
            event.ignore()
            return
        if not self._quitting:
            self.exit_requested.emit()
        event.accept()

    def moveEvent(self, event: QMoveEvent) -> None:
        if self._position_initialized:
            self._save_position_timer.start()
        super().moveEvent(event)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if not self._position_initialized:
            self._restore_or_position()
            self._position_initialized = True
        self._clamp_to_visible_screen()

    def _create_tray(self) -> None:
        self.tray_icon = QSystemTrayIcon(self.windowIcon(), self)
        menu = QMenu()
        show_action = QAction("顯示／隱藏", menu)
        show_action.triggered.connect(self._toggle_visibility)
        menu.addAction(show_action)
        refresh_action = QAction("立即更新", menu)
        refresh_action.triggered.connect(self.refresh_requested.emit)
        menu.addAction(refresh_action)
        appearance_action = QAction("顯示外觀調整", menu)
        appearance_action.triggered.connect(self._show_appearance_panel)
        menu.addAction(appearance_action)
        menu.addSeparator()
        self.autostart_action = QAction("登入 Windows 後自動啟動", menu)
        self.autostart_action.setCheckable(True)
        self.autostart_action.setEnabled(self.autostart.supported)
        if not self.autostart.supported:
            self.autostart_action.setText("登入 Windows 後自動啟動（打包版）")
        else:
            self.autostart.repair_if_enabled()
            self.autostart_action.setChecked(self.autostart.is_enabled())
        self.autostart_action.toggled.connect(self._set_autostart)
        menu.addAction(self.autostart_action)
        menu.addSeparator()
        exit_action = QAction("完全退出", menu)
        exit_action.triggered.connect(self.exit_requested.emit)
        menu.addAction(exit_action)
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.setToolTip("Codex 剩餘用量")
        self.tray_icon.activated.connect(self._tray_activated)
        self.tray_icon.show()

    def _tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in {
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        }:
            self._toggle_visibility()

    def _toggle_visibility(self) -> None:
        if self.isVisible():
            self.hide()
            self._save_geometry()
        else:
            self.show_or_raise()

    def _set_autostart(self, enabled: bool) -> None:
        if not self.autostart.supported:
            return
        try:
            self.autostart.set_enabled(enabled)
        except (OSError, RuntimeError) as exc:
            if self.autostart_action:
                self.autostart_action.blockSignals(True)
                self.autostart_action.setChecked(not enabled)
                self.autostart_action.blockSignals(False)
            self.set_error(f"無法變更自動啟動設定：{exc}")

    def _load_opacity_setting(self) -> int:
        value = self.settings.value("appearance/opacity_percent", MAX_OPACITY_PERCENT)
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = MAX_OPACITY_PERCENT
        return max(MIN_OPACITY_PERCENT, min(MAX_OPACITY_PERCENT, parsed))

    def _load_important_text_color_setting(self) -> str | None:
        value = self.settings.value("appearance/important_text_color", "")
        color = QColor(str(value) if value is not None else "")
        if not color.isValid():
            legacy_value = self.settings.value("appearance/background_color", "")
            color = QColor(str(legacy_value) if legacy_value is not None else "")
            if color.isValid():
                self.settings.setValue("appearance/important_text_color", color.name())
        if self.settings.contains("appearance/background_color"):
            self.settings.remove("appearance/background_color")
            self.settings.sync()
        return color.name() if color.isValid() else None

    def _show_appearance_panel(self) -> None:
        self.show_or_raise()
        self._set_appearance_panel_visible(True)

    def _set_appearance_panel_visible(self, visible: bool) -> None:
        self.appearance_button.setChecked(visible)
        self.appearance_panel.setVisible(visible)
        if visible:
            self.appearance_panel.opacity_slider.setFocus()
        QTimer.singleShot(0, self._fit_to_screen)

    def _apply_inline_appearance(self, opacity_percent: int, important_text_color: object) -> None:
        color = important_text_color if isinstance(important_text_color, str) else None
        self._set_appearance(opacity_percent, color, persist=True)

    def _set_appearance(
        self,
        opacity_percent: int,
        important_text_color: str | None,
        *,
        persist: bool = False,
    ) -> None:
        next_opacity = max(
            MIN_OPACITY_PERCENT,
            min(MAX_OPACITY_PERCENT, int(opacity_percent)),
        )
        color = QColor(important_text_color or "")
        next_color = color.name() if color.isValid() else None
        color_changed = next_color != self._important_text_color
        self._opacity_percent = next_opacity
        self._important_text_color = next_color
        if hasattr(self, "appearance_panel"):
            panel = self.appearance_panel
            if (
                panel.opacity_percent != self._opacity_percent
                or panel.important_text_color != self._important_text_color
            ):
                panel.set_appearance(
                    self._opacity_percent,
                    self._important_text_color,
                )
        if persist:
            self.settings.setValue("appearance/opacity_percent", self._opacity_percent)
            if self._important_text_color is None:
                self.settings.remove("appearance/important_text_color")
            else:
                self.settings.setValue(
                    "appearance/important_text_color",
                    self._important_text_color,
                )
            self._appearance_sync_timer.start()
        self.setWindowOpacity(self._opacity_percent / 100)
        if color_changed:
            self._apply_theme()

    def _metadata_lines(self, snapshot: UsageSnapshot) -> list[str]:
        lines: list[str] = []
        if snapshot.plan_types:
            lines.append(f"方案：{' / '.join(snapshot.plan_types)}")
        for credits in snapshot.credit_balances:
            if credits.unlimited:
                detail = "無限額"
            elif credits.balance:
                detail = f"餘額 {credits.balance}"
            else:
                detail = "有可用點數" if credits.has_credits else "無可用點數"
            lines.append(f"{credits.bucket_label} 點數：{detail}")
        for spend in snapshot.spend_limits:
            lines.append(
                f"{spend.bucket_label} 個人額度：剩餘 {spend.remaining_percent}%"
                f"（已用 {spend.used}／上限 {spend.limit}）"
            )
        if snapshot.reset_credit_count is not None:
            lines.append(f"可用重設點數：{snapshot.reset_credit_count}")
        return lines

    def _update_countdowns(self) -> None:
        for row in self._usage_rows:
            row.update_countdown()

    def _update_tray_tooltip(self) -> None:
        if not self.tray_icon:
            return
        if not self._snapshot or not self._snapshot.windows:
            self.tray_icon.setToolTip("Codex 剩餘用量")
            return
        tightest = min(self._snapshot.windows, key=lambda window: window.remaining_percent)
        self.tray_icon.setToolTip(f"Codex：最低剩餘 {tightest.remaining_percent}%")

    def _restore_or_position(self) -> None:
        saved = self.settings.value("window/geometry")
        if isinstance(saved, QByteArray) and not saved.isEmpty() and self.restoreGeometry(saved):
            self._clamp_to_visible_screen()
            return
        self._fit_to_screen()
        screen = QGuiApplication.primaryScreen()
        if screen:
            area = screen.availableGeometry()
            self.move(area.right() - self.width() - 16, area.top() + 16)

    def _save_geometry(self) -> None:
        if self._position_initialized:
            self.settings.setValue("window/geometry", self.saveGeometry())

    def _fit_to_screen(self) -> None:
        screen = (
            QGuiApplication.screenAt(self.frameGeometry().center())
            or QGuiApplication.primaryScreen()
        )
        max_height = int(screen.availableGeometry().height() * 0.7) if screen else 720
        margins = self.card_layout.contentsMargins()
        chrome_height = margins.top() + margins.bottom()
        visible_items = 0
        for index in range(self.card_layout.count()):
            item = self.card_layout.itemAt(index)
            widget = item.widget()
            if widget is None or widget is self.stack or not widget.isVisible():
                continue
            chrome_height += widget.sizeHint().height()
            visible_items += 1
        chrome_height += self.card_layout.spacing() * visible_items

        page = self.stack.currentWidget()
        if page is self.scroll:
            self.content.adjustSize()
            page_height = max(100, self.content.sizeHint().height())
        else:
            page_height = max(140, page.sizeHint().height() if page else 140)
        stack_height = min(page_height, max(100, max_height - chrome_height - 16))
        self.stack.setFixedHeight(stack_height)
        desired = min(max(260, chrome_height + stack_height + 16), max_height)
        self.resize(380, desired)
        self._clamp_to_visible_screen()

    def _clamp_to_visible_screen(self) -> None:
        screens = QGuiApplication.screens()
        if not screens:
            return
        geometry = self.frameGeometry()
        screen = next(
            (
                candidate
                for candidate in screens
                if candidate.availableGeometry().intersects(geometry)
            ),
            QGuiApplication.primaryScreen() or screens[0],
        )
        area = screen.availableGeometry()
        x = min(max(geometry.x(), area.left()), max(area.left(), area.right() - self.width() + 1))
        y = min(max(geometry.y(), area.top()), max(area.top(), area.bottom() - self.height() + 1))
        if (x, y) != (geometry.x(), geometry.y()):
            self.move(x, y)

    def _apply_theme(self) -> None:
        self.setWindowOpacity(self._opacity_percent / 100)
        self.setStyleSheet(build_stylesheet(is_dark_theme(), self._important_text_color))
        for row in self._usage_rows:
            _refresh_style(row)

    @staticmethod
    def _clear_layout(layout: QVBoxLayout, keep: Iterable[QWidget] = ()) -> None:
        keep_set = set(keep)
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None and widget not in keep_set:
                widget.deleteLater()
