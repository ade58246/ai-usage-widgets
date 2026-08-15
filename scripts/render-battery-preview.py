from __future__ import annotations

import argparse
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from battery_usage_widget.autostart import AutostartManager
from battery_usage_widget.models import BatterySnapshot, BatteryState
from battery_usage_widget.widget import FloatingBatteryWidget


def main() -> int:
    parser = argparse.ArgumentParser(description="產生電池小工具預覽圖")
    parser.add_argument(
        "output",
        nargs="?",
        default="assets/battery-widget-preview.png",
        help="PNG 輸出路徑",
    )
    args = parser.parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])

    with tempfile.TemporaryDirectory(prefix="battery-widget-preview-") as temp_dir:
        settings = QSettings(
            str(Path(temp_dir) / "preview.ini"),
            QSettings.Format.IniFormat,
        )
        widget = FloatingBatteryWidget(
            settings,
            AutostartManager(executable="BatteryUsageWidget.exe", frozen=False),
            enable_tray=False,
        )
        widget.set_snapshot(
            BatterySnapshot(
                state=BatteryState.FULL,
                percent=100,
                ac_online=True,
                battery_present=True,
                battery_saver=False,
                remaining_seconds=None,
                full_life_seconds=None,
                max_capacity_mwh=85_070,
                remaining_capacity_mwh=85_070,
                power_rate_mw=0,
                fetched_at=datetime.now(UTC),
            )
        )
        widget.show()
        app.processEvents()
        widget._fit_to_screen()
        app.processEvents()
        if not widget.grab().save(str(output), "PNG"):
            return 1
        widget.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
