"""Windows installer helper: add or remove the cprun folder in the user's PATH.

Called by the NSIS installer (windows/cprun.nsi):

    python\\python.exe -I -m cprun.winsetup add    C:\\...\\cprun
    python\\python.exe -I -m cprun.winsetup remove C:\\...\\cprun

Only the current user's PATH (HKCU\\Environment) is changed, so no
administrator rights are needed. Done in Python instead of NSIS because NSIS
strings are limited to 1024 characters and would truncate long PATH values.
"""

from __future__ import annotations

import os
import sys
from typing import List


def _norm(entry: str) -> str:
    return os.path.normcase(os.path.normpath(entry.strip().strip('"'))) if entry.strip() else ""


def path_with(path_value: str, folder: str) -> str:
    """Return PATH with ``folder`` appended (unchanged if already present)."""
    entries = [e for e in path_value.split(";") if e]
    if any(_norm(e) == _norm(folder) for e in entries):
        return path_value
    return ";".join(entries + [folder])


def path_without(path_value: str, folder: str) -> str:
    """Return PATH with every occurrence of ``folder`` removed."""
    entries: List[str] = [e for e in path_value.split(";") if e]
    return ";".join(e for e in entries if _norm(e) != _norm(folder))


def _update_user_path(transform) -> bool:
    import ctypes
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0,
                        winreg.KEY_READ | winreg.KEY_WRITE) as key:
        try:
            value, kind = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            value, kind = "", winreg.REG_EXPAND_SZ
        new_value = transform(value)
        if new_value == value:
            return False
        if kind not in (winreg.REG_SZ, winreg.REG_EXPAND_SZ):
            kind = winreg.REG_EXPAND_SZ
        winreg.SetValueEx(key, "Path", 0, kind, new_value)

    # Tell Explorer and new terminals that the environment changed.
    HWND_BROADCAST, WM_SETTINGCHANGE, SMTO_ABORTIFHUNG = 0xFFFF, 0x001A, 0x0002
    result = ctypes.c_ulong()
    ctypes.windll.user32.SendMessageTimeoutW(HWND_BROADCAST, WM_SETTINGCHANGE, 0, "Environment",
                                             SMTO_ABORTIFHUNG, 5000, ctypes.byref(result))
    return True


def main(argv: List[str]) -> int:
    if len(argv) != 2 or argv[0] not in ("add", "remove"):
        print("usage: python -m cprun.winsetup add|remove FOLDER", file=sys.stderr)
        return 2
    action, folder = argv
    if os.name != "nt":
        print("cprun.winsetup only works on Windows", file=sys.stderr)
        return 2
    if action == "add":
        _update_user_path(lambda value: path_with(value, folder))
    else:
        _update_user_path(lambda value: path_without(value, folder))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
