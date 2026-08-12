from __future__ import annotations

import subprocess
import sys

from PySide6.QtCore import QObject, QSettings, QTimer
from PySide6.QtWidgets import QApplication

from claude_usage_widget import __version__
from claude_usage_widget.autostart import AutostartManager
from claude_usage_widget.claude_cli import ClaudeUsageClient, launch_claude_login
from claude_usage_widget.single_instance import SingleInstance
from claude_usage_widget.widget import FloatingUsageWidget


class ApplicationController(QObject):
    def __init__(
        self,
        app: QApplication,
        widget: FloatingUsageWidget,
        client: ClaudeUsageClient,
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
        widget.refresh_requested.connect(client.refresh)
        widget.integration_requested.connect(self._install_integration)
        widget.login_requested.connect(self._start_login)
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

    def _install_integration(self) -> None:
        was_installed = self.client.integration.is_installed()
        self.client.install_integration()
        if not was_installed and self.client.integration.is_installed():
            self.widget.set_notice("整合已啟用。請重新啟動 Claude Code 並完成一次正常回應。")

    def _start_login(self) -> None:
        if not self.client.executable:
            self.widget.set_error("找不到可用的 Claude Code CLI。")
            return
        try:
            launch_claude_login(self.client.executable)
        except (OSError, subprocess.SubprocessError) as exc:
            self.widget.set_error(f"無法開啟 Claude 登入視窗：{exc}")


def create_application(argv: list[str] | None = None) -> QApplication:
    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("Claude Usage Widget")
    app.setApplicationDisplayName("Claude 剩餘用量")
    app.setOrganizationName("ClaudeUsageWidget")
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

    widget = FloatingUsageWidget(QSettings(), AutostartManager())
    client = ClaudeUsageClient()
    controller = ApplicationController(app, widget, client, instance)
    controller.start()
    if smoke_test:
        QTimer.singleShot(3_000, app.quit)
    exit_code = app.exec()
    controller.shutdown()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
