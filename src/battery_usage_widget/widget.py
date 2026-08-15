from __future__ import annotations

from PySide6.QtCore import QByteArray, QPoint, QSettings, Qt, QTimer, Signal
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QColor,
    QGuiApplication,
    QKeyEvent,
    QMouseEvent,
    QMoveEvent,
    QShowEvent,
)
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QProgressBar,
    QSizePolicy,
    QSlider,
    QSystemTrayIcon,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from battery_usage_widget.autostart import AutostartManager
from battery_usage_widget.icon_factory import create_battery_icon
from battery_usage_widget.models import BatterySnapshot, BatteryState
from battery_usage_widget.theme import build_stylesheet, is_dark_theme

MIN_OPACITY_PERCENT = 35
MAX_OPACITY_PERCENT = 100


def format_time(seconds: int | None) -> str:
    if seconds is None:
        return "Windows 尚未提供"
    seconds = max(0, seconds)
    hours, remainder = divmod(seconds, 3_600)
    minutes = remainder // 60
    if hours:
        return f"約 {hours} 小時 {minutes} 分"
    return f"約 {minutes} 分鐘"


def format_power(rate_mw: int | None) -> str:
    if rate_mw is None:
        return "未知"
    watts = abs(rate_mw) / 1_000
    if rate_mw > 0:
        return f"充電 {watts:.1f} W"
    if rate_mw < 0:
        return f"耗電 {watts:.1f} W"
    return "0.0 W"


def format_capacity(remaining_mwh: int | None, maximum_mwh: int | None) -> str:
    if remaining_mwh is None or maximum_mwh is None:
        return "未知"
    return f"{remaining_mwh / 1_000:.1f} / {maximum_mwh / 1_000:.1f} Wh"


def presentation_for(snapshot: BatterySnapshot) -> tuple[str, str]:
    percent = snapshot.percent
    if snapshot.state == BatteryState.CHARGING:
        return "charging", "⚡ 充電中"
    if snapshot.state == BatteryState.FULL:
        return "normal", "● 已充滿"
    if snapshot.state == BatteryState.NO_BATTERY:
        return "neutral", "○ 未偵測到電池"
    if percent is not None and percent <= 15:
        return "critical", "⚠ 電量緊迫"
    if percent is not None and percent <= 35:
        return "warning", "▲ 電量偏低"
    if snapshot.state in {BatteryState.DISCHARGING, BatteryState.ON_BATTERY}:
        return "normal", "● 使用電池"
    if snapshot.state == BatteryState.PLUGGED_IN:
        return "normal", "● 已接電源"
    return "neutral", "○ 狀態未知"


def summary_for(snapshot: BatterySnapshot) -> str:
    if snapshot.state == BatteryState.CHARGING:
        return f"正在透過外部電源充電 · {format_power(snapshot.power_rate_mw)}"
    if snapshot.state == BatteryState.FULL:
        return "電池已充滿，目前使用外部電源。"
    if snapshot.state in {BatteryState.DISCHARGING, BatteryState.ON_BATTERY}:
        return f"預估可使用 {format_time(snapshot.remaining_seconds).removeprefix('約 ')}"
    if snapshot.state == BatteryState.PLUGGED_IN:
        return "已接上外部電源，目前未充電。"
    if snapshot.state == BatteryState.NO_BATTERY:
        return "Windows 沒有偵測到系統電池。"
    return "Windows 尚未提供完整的電池狀態。"


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


class FloatingBatteryWidget(QWidget):
    refresh_requested = Signal()
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
        self._snapshot: BatterySnapshot | None = None
        self._quitting = False
        self._position_initialized = False
        self._opacity_percent = self._load_opacity_setting()

        self.setObjectName("FloatingBatteryWidget")
        self.setWindowTitle("電池用量與充電狀態")
        self.setWindowIcon(create_battery_icon())
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMinimumWidth(350)
        self.setMaximumWidth(480)
        self.resize(390, 470)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(11, 11, 11, 14)
        self.card = QFrame()
        self.card.setObjectName("Card")
        shadow = QGraphicsDropShadowEffect(self.card)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 5)
        shadow.setColor(QColor(105, 76, 38, 58))
        self.card.setGraphicsEffect(shadow)
        outer.addWidget(self.card)

        self.card_layout = QVBoxLayout(self.card)
        self.card_layout.setContentsMargins(18, 16, 18, 16)
        self.card_layout.setSpacing(12)

        header = DraggableHeader()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(7)
        brand = QLabel("⚡")
        brand.setObjectName("BrandMark")
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand.setFixedSize(40, 40)
        brand.setAccessibleName("電池")
        header_layout.addWidget(brand)
        title_column = QVBoxLayout()
        title_column.setSpacing(1)
        title = QLabel("電池狀態")
        title.setObjectName("Title")
        subtitle = QLabel("Windows 電源監測 · 每 5 秒更新")
        subtitle.setObjectName("Muted")
        title_column.addWidget(title)
        title_column.addWidget(subtitle)
        header_layout.addLayout(title_column, 1)

        self.refresh_button = QToolButton()
        self.refresh_button.setObjectName("HeaderButton")
        self.refresh_button.setText("↻")
        self.refresh_button.setToolTip("立即更新電池狀態")
        self.refresh_button.setAccessibleName("立即更新電池狀態")
        self.refresh_button.clicked.connect(self.refresh_requested.emit)
        header_layout.addWidget(self.refresh_button)
        self.close_button = QToolButton()
        self.close_button.setObjectName("HeaderButton")
        self.close_button.setText("×")
        self.close_button.setToolTip("縮到系統匣")
        self.close_button.setAccessibleName("縮到系統匣")
        self.close_button.clicked.connect(self.close)
        header_layout.addWidget(self.close_button)
        self.card_layout.addWidget(header)

        self.status_label = QLabel("◌ 正在讀取")
        self.status_label.setObjectName("StatusLabel")
        self.status_label.setMinimumWidth(132)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.card_layout.addWidget(self.status_label, 0, Qt.AlignmentFlag.AlignLeft)

        self.error_banner = QLabel()
        self.error_banner.setObjectName("ErrorBanner")
        self.error_banner.setWordWrap(True)
        self.error_banner.hide()
        self.card_layout.addWidget(self.error_banner)

        battery_card = QFrame()
        battery_card.setObjectName("BatteryCard")
        battery_layout = QVBoxLayout(battery_card)
        battery_layout.setContentsMargins(15, 14, 15, 14)
        battery_layout.setSpacing(10)
        value_row = QHBoxLayout()
        self.percent_label = QLabel("--%")
        self.percent_label.setObjectName("BatteryPercent")
        self.percent_label.setMinimumWidth(145)
        self.percent_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self.state_badge = QLabel("○ 等待資料")
        self.state_badge.setObjectName("StateBadge")
        self.state_badge.setProperty("state", "neutral")
        value_row.addWidget(self.percent_label)
        value_row.addStretch(1)
        value_row.addWidget(self.state_badge)
        battery_layout.addLayout(value_row)
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("BatteryProgress")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setProperty("state", "neutral")
        self.progress_bar.setAccessibleName("電池剩餘電量")
        battery_layout.addWidget(self.progress_bar)
        self.summary_label = QLabel("正在讀取這台電腦的電池狀態…")
        self.summary_label.setObjectName("Summary")
        self.summary_label.setWordWrap(True)
        battery_layout.addWidget(self.summary_label)
        self.card_layout.addWidget(battery_card)

        details_card = QFrame()
        details_card.setObjectName("DetailsCard")
        details_layout = QGridLayout(details_card)
        details_layout.setContentsMargins(14, 12, 14, 12)
        details_layout.setHorizontalSpacing(12)
        details_layout.setVerticalSpacing(8)
        self.source_value = self._add_detail(details_layout, 0, "電源來源")
        self.time_value = self._add_detail(details_layout, 1, "預估時間")
        self.power_value = self._add_detail(details_layout, 2, "即時功率")
        self.capacity_value = self._add_detail(details_layout, 3, "電池容量")
        self.saver_value = self._add_detail(details_layout, 4, "省電模式")
        self.card_layout.addWidget(details_card)

        transparency_card = QFrame()
        transparency_card.setObjectName("TransparencyCard")
        transparency_layout = QHBoxLayout(transparency_card)
        transparency_layout.setContentsMargins(14, 9, 12, 9)
        transparency_layout.setSpacing(10)
        transparency_label = QLabel("介面透明度")
        transparency_label.setObjectName("TransparencyLabel")
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(MIN_OPACITY_PERCENT, MAX_OPACITY_PERCENT)
        self.opacity_slider.setValue(self._opacity_percent)
        self.opacity_slider.setSingleStep(5)
        self.opacity_slider.setPageStep(10)
        self.opacity_slider.setTracking(True)
        self.opacity_slider.setMinimumWidth(125)
        self.opacity_slider.setMinimumHeight(30)
        self.opacity_slider.setToolTip("35% 較透明；100% 完全不透明")
        self.opacity_slider.setAccessibleName("電池狀態介面透明度")
        self.opacity_slider.setAccessibleDescription(
            f"可調整為 {MIN_OPACITY_PERCENT}% 到 {MAX_OPACITY_PERCENT}%"
        )
        transparency_label.setBuddy(self.opacity_slider)
        self.opacity_value_label = QLabel(f"{self._opacity_percent}%")
        self.opacity_value_label.setObjectName("TransparencyValue")
        self.opacity_value_label.setMinimumWidth(46)
        self.opacity_value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.opacity_value_label.setAccessibleName("目前介面透明度")
        transparency_layout.addWidget(transparency_label)
        transparency_layout.addWidget(self.opacity_slider, 1)
        transparency_layout.addWidget(self.opacity_value_label)
        self.card_layout.addWidget(transparency_card)
        self.opacity_slider.valueChanged.connect(
            lambda value: self._set_opacity_percent(value, persist=True)
        )

        self.updated_label = QLabel("尚未取得資料")
        self.updated_label.setObjectName("Metadata")
        self.updated_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.card_layout.addWidget(self.updated_label)

        self._save_position_timer = QTimer(self)
        self._save_position_timer.setSingleShot(True)
        self._save_position_timer.setInterval(250)
        self._save_position_timer.timeout.connect(self._save_geometry)

        self._opacity_sync_timer = QTimer(self)
        self._opacity_sync_timer.setSingleShot(True)
        self._opacity_sync_timer.setInterval(300)
        self._opacity_sync_timer.timeout.connect(self.settings.sync)

        self.tray_icon: QSystemTrayIcon | None = None
        self.autostart_action: QAction | None = None
        if enable_tray and QSystemTrayIcon.isSystemTrayAvailable():
            self._create_tray()

        self._apply_theme()
        self._set_opacity_percent(self._opacity_percent, persist=False)
        QGuiApplication.styleHints().colorSchemeChanged.connect(lambda _scheme: self._apply_theme())

    @staticmethod
    def _add_detail(layout: QGridLayout, row: int, label_text: str) -> QLabel:
        label = QLabel(label_text)
        label.setObjectName("DetailLabel")
        value = QLabel("—")
        value.setObjectName("DetailValue")
        value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        value.setWordWrap(True)
        layout.addWidget(label, row, 0)
        layout.addWidget(value, row, 1)
        return value

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
        if self._opacity_sync_timer.isActive():
            self._opacity_sync_timer.stop()
            self.settings.sync()
        if self.tray_icon:
            self.tray_icon.hide()

    def set_snapshot(self, snapshot: BatterySnapshot) -> None:
        self._snapshot = snapshot
        self.error_banner.hide()
        style_state, state_text = presentation_for(snapshot)
        self.percent_label.setText(
            f"{snapshot.percent}%" if snapshot.percent is not None else "--%"
        )
        self.state_badge.setText(state_text)
        self.state_badge.setProperty("state", style_state)
        self.progress_bar.setValue(snapshot.percent or 0)
        self.progress_bar.setProperty("state", style_state)
        self.progress_bar.setAccessibleDescription(
            "電量未知" if snapshot.percent is None else f"剩餘 {snapshot.percent}%"
        )
        _refresh_style(self.state_badge)
        _refresh_style(self.progress_bar)
        self.summary_label.setText(summary_for(snapshot))
        self.source_value.setText(
            "外部電源"
            if snapshot.ac_online
            else "電池供電"
            if snapshot.ac_online is not None
            else "未知"
        )
        if snapshot.state in {BatteryState.DISCHARGING, BatteryState.ON_BATTERY}:
            time_text = format_time(snapshot.remaining_seconds)
        elif snapshot.state == BatteryState.FULL:
            time_text = "已充滿"
        elif snapshot.state == BatteryState.CHARGING:
            time_text = "充滿時間未提供"
        else:
            time_text = "不適用" if snapshot.ac_online else "Windows 尚未提供"
        self.time_value.setText(time_text)
        self.power_value.setText(format_power(snapshot.power_rate_mw))
        self.capacity_value.setText(
            format_capacity(snapshot.remaining_capacity_mwh, snapshot.max_capacity_mwh)
        )
        self.saver_value.setText(
            "已開啟"
            if snapshot.battery_saver
            else "未開啟"
            if snapshot.battery_saver is not None
            else "未知"
        )
        self.status_label.setText("● 即時監測中")
        local_time = snapshot.fetched_at.astimezone().strftime("%H:%M:%S")
        self.updated_label.setText(f"最後更新：{local_time}")
        self._update_tray_tooltip()
        QTimer.singleShot(0, self._fit_to_screen)

    def set_error(self, message: str) -> None:
        self.error_banner.setText(f"⚠ {message}")
        self.error_banner.show()
        self.status_label.setText("⚠ 讀取異常")
        QTimer.singleShot(0, self._fit_to_screen)

    def set_refreshing(self, refreshing: bool) -> None:
        self.refresh_button.setText("…" if refreshing else "↻")
        self.refresh_button.setEnabled(not refreshing)

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
        self.setWindowOpacity(self._opacity_percent / 100)
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
        self.tray_icon.setToolTip("電池用量與充電狀態")
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

    def _set_opacity_percent(self, opacity_percent: int, *, persist: bool) -> None:
        next_opacity = max(
            MIN_OPACITY_PERCENT,
            min(MAX_OPACITY_PERCENT, int(opacity_percent)),
        )
        self._opacity_percent = next_opacity
        if self.opacity_slider.value() != next_opacity:
            self.opacity_slider.blockSignals(True)
            self.opacity_slider.setValue(next_opacity)
            self.opacity_slider.blockSignals(False)
        self.opacity_value_label.setText(f"{next_opacity}%")
        self.opacity_value_label.setAccessibleDescription(f"目前為 {next_opacity}%")
        self.setWindowOpacity(next_opacity / 100)
        if persist:
            self.settings.setValue("appearance/opacity_percent", next_opacity)
            self._opacity_sync_timer.start()

    def _update_tray_tooltip(self) -> None:
        if not self.tray_icon or self._snapshot is None:
            return
        _style, state_text = presentation_for(self._snapshot)
        percent = f"{self._snapshot.percent}%" if self._snapshot.percent is not None else "未知"
        self.tray_icon.setToolTip(f"電池 {percent} · {state_text.lstrip('●⚡▲⚠○ ')}")

    def _restore_or_position(self) -> None:
        saved = self.settings.value("window/geometry")
        if isinstance(saved, QByteArray) and not saved.isEmpty() and self.restoreGeometry(saved):
            self._clamp_to_visible_screen()
            return
        self._fit_to_screen()
        screen = QGuiApplication.primaryScreen()
        if screen:
            area = screen.availableGeometry()
            self.move(area.left() + 16, area.bottom() - self.height() - 16)

    def _save_geometry(self) -> None:
        if self._position_initialized:
            self.settings.setValue("window/geometry", self.saveGeometry())

    def _fit_to_screen(self) -> None:
        self.card.adjustSize()
        desired_height = max(350, self.card.sizeHint().height() + 28)
        screen = (
            QGuiApplication.screenAt(self.frameGeometry().center())
            or QGuiApplication.primaryScreen()
        )
        max_height = int(screen.availableGeometry().height() * 0.8) if screen else 760
        self.resize(390, min(desired_height, max_height))
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
