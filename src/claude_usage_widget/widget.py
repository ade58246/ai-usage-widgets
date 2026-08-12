from __future__ import annotations

import time
from collections.abc import Iterable

from PySide6.QtCore import QByteArray, QDateTime, QLocale, QPoint, QSettings, Qt, QTimer, Signal
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QFont,
    QGuiApplication,
    QKeyEvent,
    QMouseEvent,
    QMoveEvent,
    QShowEvent,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QSystemTrayIcon,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from claude_usage_widget.autostart import AutostartManager
from claude_usage_widget.icon_factory import create_meter_icon
from claude_usage_widget.models import ConnectionState, RateLimitWindowView, UsageSnapshot
from claude_usage_widget.theme import build_stylesheet, is_dark_theme


def format_duration(minutes: int | None) -> str:
    if minutes is None:
        return "時間窗未知"
    if minutes >= 1_440 and minutes % 1_440 == 0:
        return f"{minutes // 1_440} 天"
    if minutes >= 60 and minutes % 60 == 0:
        return f"{minutes // 60} 小時"
    return f"{minutes} 分鐘"


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
        return "Claude 未提供重設時間"
    date_time = QDateTime.fromSecsSinceEpoch(timestamp).toLocalTime()
    formatted = QLocale.system().toString(date_time, QLocale.FormatType.ShortFormat)
    return f"本地重設時間：{formatted}"


def severity_for(window: RateLimitWindowView) -> tuple[str, str]:
    if window.remaining_percent < 20:
        return "critical", "緊迫"
    if window.remaining_percent <= 50:
        return "warning", "注意"
    return "normal", "正常"


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


class UsageRow(QFrame):
    def __init__(self, window: RateLimitWindowView, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("UsageRow")
        self.window_data = window
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        heading = QHBoxLayout()
        title = QLabel(window.label)
        title.setWordWrap(True)
        title.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        duration = QLabel(format_duration(window.window_duration_mins))
        duration.setObjectName("Muted")
        heading.addWidget(title)
        heading.addWidget(duration, 0, Qt.AlignmentFlag.AlignRight)
        layout.addLayout(heading)

        value_row = QHBoxLayout()
        percent = QLabel(f"{window.remaining_percent}% 剩餘")
        font = percent.font()
        font.setPointSizeF(max(15.0, font.pointSizeF() * 1.25))
        font.setWeight(QFont.Weight.DemiBold)
        percent.setFont(font)
        severity, severity_label = severity_for(window)
        percent.setProperty("severity", severity)
        badge = QLabel(f"● {severity_label}")
        badge.setProperty("severity", severity)
        value_row.addWidget(percent)
        value_row.addStretch(1)
        value_row.addWidget(badge)
        layout.addLayout(value_row)

        progress = QProgressBar()
        progress.setRange(0, 100)
        progress.setValue(window.remaining_percent)
        progress.setTextVisible(False)
        progress.setProperty("severity", severity)
        progress.setAccessibleName(f"{window.label}剩餘用量")
        progress.setAccessibleDescription(f"剩餘 {window.remaining_percent}%，狀態{severity_label}")
        layout.addWidget(progress)

        self.reset_label = QLabel()
        self.reset_label.setObjectName("ResetLabel")
        self.reset_label.setWordWrap(True)
        layout.addWidget(self.reset_label)
        self.update_countdown()

    def update_countdown(self) -> None:
        self.reset_label.setText(format_countdown(self.window_data.resets_at))
        self.reset_label.setToolTip(format_absolute_time(self.window_data.resets_at))


class FloatingUsageWidget(QWidget):
    refresh_requested = Signal()
    integration_requested = Signal()
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

        self.setObjectName("FloatingUsageWidget")
        self.setWindowTitle("Claude 剩餘用量")
        self.setWindowIcon(create_meter_icon())
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMinimumWidth(320)
        self.setMaximumWidth(420)
        self.resize(360, 300)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        self.card = QFrame()
        self.card.setObjectName("Card")
        outer.addWidget(self.card)
        self.card_layout = QVBoxLayout(self.card)
        self.card_layout.setContentsMargins(14, 12, 14, 14)
        self.card_layout.setSpacing(10)

        header = DraggableHeader()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(6)
        title_column = QVBoxLayout()
        title_column.setSpacing(1)
        title = QLabel("Claude 剩餘用量")
        title.setObjectName("Title")
        self.account_label = QLabel("正在檢查 Claude Code…")
        self.account_label.setObjectName("Muted")
        self.account_label.setWordWrap(True)
        title_column.addWidget(title)
        title_column.addWidget(self.account_label)
        header_layout.addLayout(title_column, 1)

        self.refresh_button = QToolButton()
        self.refresh_button.setText("↻")
        self.refresh_button.setToolTip("重新讀取本機用量快取")
        self.refresh_button.setAccessibleName("重新讀取 Claude 用量")
        self.refresh_button.clicked.connect(self.refresh_requested.emit)
        header_layout.addWidget(self.refresh_button)
        self.close_button = QToolButton()
        self.close_button.setText("×")
        self.close_button.setToolTip("縮到系統匣")
        self.close_button.setAccessibleName("縮到系統匣")
        self.close_button.clicked.connect(self.close)
        header_layout.addWidget(self.close_button)
        self.card_layout.addWidget(header)

        self.status_label = QLabel("◌ 啟動中")
        self.status_label.setObjectName("StatusLabel")
        self.card_layout.addWidget(self.status_label)
        self.banner = QLabel()
        self.banner.setWordWrap(True)
        self.banner.hide()
        self.card_layout.addWidget(self.banner)

        self.stack = QStackedWidget()
        self.card_layout.addWidget(self.stack, 1)
        message_page = QWidget()
        message_layout = QVBoxLayout(message_page)
        message_layout.setContentsMargins(4, 18, 4, 18)
        message_layout.setSpacing(12)
        self.message_label = QLabel("正在檢查 Claude Code…")
        self.message_label.setObjectName("Muted")
        self.message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message_label.setWordWrap(True)
        message_layout.addWidget(self.message_label)
        self.integration_button = QPushButton("啟用 Claude 用量整合")
        self.integration_button.setObjectName("PrimaryButton")
        self.integration_button.setAccessibleName("啟用 Claude status line 用量整合")
        self.integration_button.clicked.connect(self.integration_requested.emit)
        self.integration_button.hide()
        message_layout.addWidget(self.integration_button)
        self.login_button = QPushButton("開啟 Claude 登入")
        self.login_button.setObjectName("PrimaryButton")
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
        self.content_layout.setSpacing(8)
        self.scroll.setWidget(self.content)
        self.stack.addWidget(self.scroll)

        self.updated_label = QLabel("尚未取得資料")
        self.updated_label.setObjectName("Metadata")
        self.updated_label.setWordWrap(True)
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
        if enable_tray and QSystemTrayIcon.isSystemTrayAvailable():
            self._create_tray()

        self._apply_theme()
        QGuiApplication.styleHints().colorSchemeChanged.connect(lambda _scheme: self._apply_theme())
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
        if self.tray_icon:
            self.tray_icon.hide()

    def set_connection_state(self, state: ConnectionState) -> None:
        labels = {
            ConnectionState.STOPPED: "○ 已停止",
            ConnectionState.STARTING: "◌ 正在檢查 Claude Code",
            ConnectionState.AUTH_REQUIRED: "○ 需要登入 Claude",
            ConnectionState.INTEGRATION_REQUIRED: "○ 需要啟用用量整合",
            ConnectionState.WAITING_FOR_DATA: "◌ 等待 Claude 用量資料",
            ConnectionState.READY: "● 資料已同步",
            ConnectionState.STALE: "○ 等待 Claude 更新",
            ConnectionState.MISSING_CLI: "⚠ 找不到 Claude Code CLI",
            ConnectionState.OUTDATED_CLI: "⚠ Claude Code CLI 過舊",
            ConnectionState.ERROR: "⚠ 讀取異常",
        }
        self.status_label.setText(labels[state])
        self.integration_button.setVisible(state == ConnectionState.INTEGRATION_REQUIRED)
        self.login_button.setVisible(state == ConnectionState.AUTH_REQUIRED)

        if state == ConnectionState.AUTH_REQUIRED:
            self.message_label.setText("請先透過 Claude Code 登入 Claude.ai 訂閱帳號。")
            self.stack.setCurrentIndex(0)
        elif state == ConnectionState.INTEGRATION_REQUIRED:
            self.message_label.setText(
                "啟用後會在 Claude settings.json 加入官方 status line 擷取器；"
                "只保存用量與重設時間，不接觸 OAuth token。"
            )
            self.stack.setCurrentIndex(0)
        elif state == ConnectionState.WAITING_FOR_DATA:
            self.message_label.setText(
                "整合已就緒。請重新啟動 Claude Code 並完成一次正常回應，"
                "小工具就會取得 5 小時與 7 天用量。"
            )
            if self._snapshot is None:
                self.stack.setCurrentIndex(0)
        elif state in {ConnectionState.MISSING_CLI, ConnectionState.OUTDATED_CLI}:
            self.stack.setCurrentIndex(0)
        elif state in {ConnectionState.READY, ConnectionState.STALE} and self._snapshot:
            self.stack.setCurrentIndex(1)
        self.refresh_button.setEnabled(
            state
            in {
                ConnectionState.READY,
                ConnectionState.STALE,
                ConnectionState.WAITING_FOR_DATA,
                ConnectionState.ERROR,
            }
        )
        QTimer.singleShot(0, self._fit_to_screen)

    def set_refreshing(self, refreshing: bool) -> None:
        self.refresh_button.setText("…" if refreshing else "↻")
        self.refresh_button.setEnabled(not refreshing)

    def set_account(self, account: object) -> None:
        if not isinstance(account, dict) or not account.get("loggedIn"):
            self.account_label.setText("尚未登入 Claude")
            return
        email = account.get("email")
        plan = account.get("subscriptionType")
        parts = [str(value) for value in (email, plan) if isinstance(value, str) and value]
        self.account_label.setText(" · ".join(parts) if parts else "Claude.ai 帳號")

    def set_snapshot(self, snapshot: UsageSnapshot) -> None:
        self._snapshot = snapshot
        self.banner.hide()
        self._clear_layout(self.content_layout)
        self._usage_rows.clear()
        for window in snapshot.windows:
            row = UsageRow(window)
            self.content_layout.addWidget(row)
            self._usage_rows.append(row)

        metadata = []
        if snapshot.model_name:
            metadata.append(f"最近模型：{snapshot.model_name}")
        if snapshot.cli_version:
            metadata.append(f"Claude Code：{snapshot.cli_version}")
        if metadata:
            card = QFrame()
            card.setObjectName("MetadataCard")
            layout = QVBoxLayout(card)
            layout.setContentsMargins(12, 10, 12, 10)
            for line in metadata:
                label = QLabel(line)
                label.setObjectName("Metadata")
                label.setWordWrap(True)
                layout.addWidget(label)
            self.content_layout.addWidget(card)
        self.content_layout.addStretch(1)

        local_time = snapshot.fetched_at.astimezone().strftime("%H:%M:%S")
        stale_text = " · 等待 Claude Code 的下一次更新" if snapshot.stale else ""
        self.updated_label.setText(f"資料時間：{local_time}{stale_text}")
        self.stack.setCurrentIndex(1)
        self._update_tray_tooltip()
        QTimer.singleShot(0, self._fit_to_screen)

    def set_error(self, message: str) -> None:
        self.banner.setObjectName("ErrorBanner")
        self.banner.setText(f"⚠ {message}")
        self.banner.show()
        if self._snapshot is None:
            self.message_label.setText(message)
            self.stack.setCurrentIndex(0)
        QTimer.singleShot(0, self._fit_to_screen)

    def set_notice(self, message: str) -> None:
        self.banner.setObjectName("NoticeBanner")
        self.banner.setText(f"✓ {message}")
        self.banner.show()
        QTimer.singleShot(0, self._fit_to_screen)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
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
        refresh_action = QAction("重新讀取用量", menu)
        refresh_action.triggered.connect(self.refresh_requested.emit)
        menu.addAction(refresh_action)
        integration_action = QAction("啟用 Claude 用量整合", menu)
        integration_action.triggered.connect(self.integration_requested.emit)
        menu.addAction(integration_action)
        menu.addSeparator()
        self.autostart_action = QAction("登入 Windows 後自動啟動", menu)
        self.autostart_action.setCheckable(True)
        self.autostart_action.setEnabled(self.autostart.supported)
        if self.autostart.supported:
            self.autostart.repair_if_enabled()
            self.autostart_action.setChecked(self.autostart.is_enabled())
        else:
            self.autostart_action.setText("登入 Windows 後自動啟動（打包版）")
        self.autostart_action.toggled.connect(self._set_autostart)
        menu.addAction(self.autostart_action)
        menu.addSeparator()
        exit_action = QAction("完全退出", menu)
        exit_action.triggered.connect(self.exit_requested.emit)
        menu.addAction(exit_action)
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.setToolTip("Claude 剩餘用量")
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

    def _update_countdowns(self) -> None:
        for row in self._usage_rows:
            row.update_countdown()

    def _update_tray_tooltip(self) -> None:
        if not self.tray_icon or not self._snapshot or not self._snapshot.windows:
            return
        tightest = min(self._snapshot.windows, key=lambda window: window.remaining_percent)
        self.tray_icon.setToolTip(f"Claude：最低剩餘 {tightest.remaining_percent}%")

    def _restore_or_position(self) -> None:
        saved = self.settings.value("window/geometry")
        if isinstance(saved, QByteArray) and not saved.isEmpty() and self.restoreGeometry(saved):
            self._clamp_to_visible_screen()
            return
        self._fit_to_screen()
        screen = QGuiApplication.primaryScreen()
        if screen:
            area = screen.availableGeometry()
            self.move(
                area.right() - self.width() - 16,
                area.bottom() - self.height() - 16,
            )

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
        self.resize(360, desired)
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
        self.setStyleSheet(build_stylesheet(is_dark_theme()))

    @staticmethod
    def _clear_layout(layout: QVBoxLayout, keep: Iterable[QWidget] = ()) -> None:
        keep_set = set(keep)
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None and widget not in keep_set:
                widget.deleteLater()
