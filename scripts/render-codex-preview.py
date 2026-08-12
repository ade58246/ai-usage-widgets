from __future__ import annotations

import argparse
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from codex_usage_widget.autostart import AutostartManager
from codex_usage_widget.models import (
    ConnectionState,
    RateLimitWindowView,
    UsageSnapshot,
)
from codex_usage_widget.widget import FloatingUsageWidget


def main() -> int:
    parser = argparse.ArgumentParser(description="產生 Codex 小工具預覽圖")
    parser.add_argument(
        "output",
        nargs="?",
        default="assets/codex-widget-preview.png",
        help="PNG 輸出路徑",
    )
    parser.add_argument("--appearance", action="store_true", help="展開外觀面板")
    arguments = parser.parse_args()
    output = Path(arguments.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])

    with tempfile.TemporaryDirectory(prefix="codex-widget-preview-") as temp_dir:
        settings = QSettings(
            str(Path(temp_dir) / "preview.ini"),
            QSettings.Format.IniFormat,
        )
        autostart = AutostartManager(executable="CodexUsageWidget.exe", frozen=False)
        widget = FloatingUsageWidget(settings, autostart, enable_tray=False)
        widget.set_account({"email": "demo@example.com", "planType": "Plus"})
        now = int(time.time())
        widget.set_snapshot(
            UsageSnapshot(
                windows=(
                    RateLimitWindowView(
                        limit_id="codex",
                        label="Codex",
                        window_kind="primary",
                        used_percent=28,
                        remaining_percent=72,
                        window_duration_mins=300,
                        resets_at=now + 7_920,
                    ),
                    RateLimitWindowView(
                        limit_id="codex",
                        label="Codex",
                        window_kind="secondary",
                        used_percent=64,
                        remaining_percent=36,
                        window_duration_mins=10_080,
                        resets_at=now + 302_400,
                    ),
                ),
                plan_types=("plus",),
                reset_credit_count=2,
                fetched_at=datetime.now(UTC),
            )
        )
        widget.set_connection_state(ConnectionState.READY)
        widget.show()
        if arguments.appearance:
            widget._set_appearance_panel_visible(True)
        app.processEvents()
        widget._fit_to_screen()
        app.processEvents()
        if not widget.grab().save(str(output), "PNG"):
            return 1
        widget.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
