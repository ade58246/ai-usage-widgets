from __future__ import annotations

import sys

from PySide6.QtCore import QObject, QSettings, QTimer
from PySide6.QtWidgets import QApplication

from battery_usage_widget import __version__
from battery_usage_widget.autostart import AutostartManager
from battery_usage_widget.power import BatteryMonitor
from battery_usage_widget.single_instance import SingleInstance
from battery_usage_widget.widget import FloatingBatteryWidget


class ApplicationController(QObject):
    def __init__(
        self,
        app: QApplication,
        widget: FloatingBatteryWidget,
        monitor: BatteryMonitor,
        instance: SingleInstance,
    ) -> None:
        super().__init__(app)
        self.app = app
        self.widget = widget
        self.monitor = monitor
        self.instance = instance
        self._shutting_down = False

        monitor.snapshot_received.connect(widget.set_snapshot)
        monitor.error_occurred.connect(widget.set_error)
        monitor.refreshing_changed.connect(widget.set_refreshing)
        widget.refresh_requested.connect(monitor.refresh)
        widget.exit_requested.connect(app.quit)
        instance.activation_requested.connect(widget.show_or_raise)
        app.aboutToQuit.connect(self.shutdown)

    def start(self) -> None:
        self.widget.show_or_raise()
        QTimer.singleShot(0, self.monitor.start)

    def shutdown(self) -> None:
        if self._shutting_down:
            return
        self._shutting_down = True
        self.widget.prepare_quit()
        self.monitor.stop()
        self.instance.close()


def create_application(argv: list[str] | None = None) -> QApplication:
    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("Battery Usage Widget")
    app.setApplicationDisplayName("電池用量與充電狀態")
    app.setOrganizationName("BatteryUsageWidget")
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

    widget = FloatingBatteryWidget(QSettings(), AutostartManager())
    monitor = BatteryMonitor()
    controller = ApplicationController(app, widget, monitor, instance)
    controller.start()
    if smoke_test:
        QTimer.singleShot(3_000, app.quit)
    exit_code = app.exec()
    controller.shutdown()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
