from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from codex_usage_widget.autostart import VALUE_NAME, AutostartManager
from codex_usage_widget.single_instance import SingleInstance


@dataclass
class FakeRegistry:
    values: dict[str, str] = field(default_factory=dict)

    def get(self, name: str) -> str | None:
        return self.values.get(name)

    def set(self, name: str, value: str) -> None:
        self.values[name] = value

    def delete(self, name: str) -> None:
        self.values.pop(name, None)


def test_autostart_manager_quotes_and_repairs_executable_path(tmp_path) -> None:
    backend = FakeRegistry()
    executable = tmp_path / "Codex Usage Widget.exe"
    manager = AutostartManager(backend, executable=str(executable), frozen=True)

    manager.set_enabled(True)
    assert backend.values[VALUE_NAME] == f'"{executable.resolve()}"'
    assert manager.is_enabled() is True

    backend.values[VALUE_NAME] = '"C:\\old\\CodexUsageWidget.exe"'
    manager.repair_if_enabled()
    assert backend.values[VALUE_NAME] == manager.command

    manager.set_enabled(False)
    assert manager.is_enabled() is False


def test_autostart_is_disabled_for_source_runs() -> None:
    manager = AutostartManager(FakeRegistry(), executable="widget.exe", frozen=False)
    assert manager.supported is False
    with pytest.raises(RuntimeError):
        manager.set_enabled(True)


def test_second_instance_notifies_primary(qtbot) -> None:
    name = "codex-usage-widget-test-instance"
    first = SingleInstance(name)
    second = SingleInstance(name)
    activations: list[bool] = []
    first.activation_requested.connect(lambda: activations.append(True))
    assert first.acquire() is True
    assert second.acquire() is False
    qtbot.waitUntil(lambda: bool(activations), timeout=2_000)
    first.close()
    second.close()
