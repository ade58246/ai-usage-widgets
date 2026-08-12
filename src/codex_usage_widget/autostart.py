from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Protocol

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "CodexUsageWidget"


class RegistryBackend(Protocol):
    def get(self, name: str) -> str | None: ...

    def set(self, name: str, value: str) -> None: ...

    def delete(self, name: str) -> None: ...


class WindowsRegistryBackend:
    def get(self, name: str) -> str | None:
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                value, _value_type = winreg.QueryValueEx(key, name)
        except FileNotFoundError:
            return None
        return value if isinstance(value, str) else None

    def set(self, name: str, value: str) -> None:
        import winreg

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)

    def delete(self, name: str) -> None:
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, name)
        except FileNotFoundError:
            return


class AutostartManager:
    def __init__(
        self,
        backend: RegistryBackend | None = None,
        *,
        executable: str | None = None,
        frozen: bool | None = None,
    ) -> None:
        self._frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
        self._executable = Path(executable or sys.executable).resolve()
        self._backend = backend or (WindowsRegistryBackend() if os.name == "nt" else None)

    @property
    def supported(self) -> bool:
        return self._frozen and self._backend is not None

    @property
    def command(self) -> str:
        return f'"{self._executable}"'

    def is_enabled(self) -> bool:
        return bool(self.supported and self._backend and self._backend.get(VALUE_NAME))

    def set_enabled(self, enabled: bool) -> None:
        if not self.supported or self._backend is None:
            raise RuntimeError("自動啟動只在 Windows 打包版中提供。")
        if enabled:
            self._backend.set(VALUE_NAME, self.command)
        else:
            self._backend.delete(VALUE_NAME)

    def repair_if_enabled(self) -> None:
        if not self.supported or self._backend is None:
            return
        current = self._backend.get(VALUE_NAME)
        if current and current != self.command:
            self._backend.set(VALUE_NAME, self.command)
