from __future__ import annotations

import sys

from PySide6.QtCore import QObject, QSettings, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication

from codex_usage_widget import __version__
from codex_usage_widget.app_server import CodexAppServerClient
from codex_usage_widget.autostart import AutostartManager
from codex_usage_widget.single_instance import SingleInstance
from codex_usage_widget.widget import FloatingUsageWidget


class ApplicationController(QObject):
    def __init__(
        self,
        app: QApplication,
        widget: FloatingUsageWidget,
        client: CodexAppServerClient,
        instance: SingleInstance,
    ) -> None:
        super().__init__(app)
        self.app = app
        self.widget = widget
        self.client = client
        self.instance = instance
        self._shutting_down = False

        client.state_changed.connect(widget.set_connection_state)
        client.account_changed.connect(widget.set_account)
        client.usage_received.connect(widget.set_snapshot)
        client.error_occurred.connect(widget.set_error)
        client.refreshing_changed.connect(widget.set_refreshing)
        client.login_url_ready.connect(self._open_login_url)

        widget.refresh_requested.connect(client.refresh)
        widget.login_requested.connect(client.start_login)
        widget.exit_requested.connect(app.quit)
        instance.activation_requested.connect(widget.show_or_raise)
        app.aboutToQuit.connect(self.shutdown)

    def start(self) -> None:
        self.widget.show_or_raise()
        QTimer.singleShot(0, self.client.start)

    def shutdown(self) -> None:
        if self._shutting_down:
            return
        self._shutting_down = True
        self.widget.prepare_quit()
        self.client.stop()
        self.instance.close()

    def _open_login_url(self, url: QUrl) -> None:
        if not QDesktopServices.openUrl(url):
            self.widget.set_error("無法開啟系統瀏覽器，請檢查 Windows 的預設瀏覽器設定。")


def create_application(argv: list[str] | None = None) -> QApplication:
    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("Codex Usage Widget")
    app.setApplicationDisplayName("Codex 剩餘用量")
    app.setOrganizationName("CodexUsageWidget")
    app.setApplicationVersion(__version__)
    app.setQuitOnLastWindowClosed(False)
    app.setStyle("Fusion")
    return app


def main(argv: list[str] | None = None) -> int:
    raw_args = list(argv if argv is not None else sys.argv)
    smoke_test = "--smoke-test" in raw_args
    qt_args = [argument for argument in raw_args if argument != "--smoke-test"]
    app = create_application(qt_args)
    instance = SingleInstance()
    if not instance.acquire():
        return 0

    settings = QSettings()
    autostart = AutostartManager()
    widget = FloatingUsageWidget(settings, autostart)
    client = CodexAppServerClient()
    controller = ApplicationController(app, widget, client, instance)
    controller.start()
    if smoke_test:
        QTimer.singleShot(3_000, app.quit)
    exit_code = app.exec()
    controller.shutdown()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
