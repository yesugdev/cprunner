"""Support for ``cprun --uninstall`` (removes only what install.sh installed)."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Dict, Optional

from .errors import CprunError, ExitCode
from .term import Console

MANIFEST_NAME = "install-manifest.txt"
LAUNCHER_MARKER = "# cprun-launcher"


def install_root() -> Optional[Path]:
    root = Path(__file__).resolve().parent.parent
    return root if (root / MANIFEST_NAME).is_file() else None


def read_manifest(root: Path) -> Dict[str, str]:
    entries = {}
    for line in (root / MANIFEST_NAME).read_text().splitlines():
        key, sep, value = line.partition("=")
        if sep:
            entries[key.strip()] = value.strip()
    return entries


def _windows_uninstaller() -> Optional[Path]:
    # Windows layout: <install dir>\lib\cprun\ (this package) and <install dir>\uninstall.exe
    candidate = Path(__file__).resolve().parent.parent.parent / "uninstall.exe"
    return candidate if candidate.is_file() else None


def uninstall(console: Console) -> int:
    if os.name == "nt":
        uninstaller = _windows_uninstaller()
        if uninstaller is None:
            raise CprunError("this copy of cprun was not installed with the Windows installer.",
                             "Remove it from Settings > Apps, or delete its folder.", code=ExitCode.SYSTEM)
        import subprocess

        subprocess.Popen([str(uninstaller)])
        console.line(f"{console.tag()} Started the uninstaller: {uninstaller}")
        return ExitCode.OK
    root = install_root()
    if root is None:
        raise CprunError(
            "this copy of cprun was not installed with install.sh.",
            f"It runs from {Path(__file__).resolve().parent.parent}.\n"
            "Nothing was removed. To remove an installed copy, run ./uninstall.sh from the repository.",
            code=ExitCode.SYSTEM,
        )
    manifest = read_manifest(root)
    removed = []

    launcher = manifest.get("launcher")
    if launcher:
        path = Path(launcher)
        try:
            if path.is_file() and LAUNCHER_MARKER in path.read_text(errors="replace"):
                path.unlink()
                removed.append(str(path))
        except OSError as e:
            raise CprunError(f"cannot remove {path}.", f"Reason: {e.strerror}", code=ExitCode.SYSTEM)

    share = Path(manifest.get("share", str(root))).resolve()
    if share != root:
        raise CprunError("install manifest is inconsistent; refusing to delete files.",
                         f"Expected {root}, manifest says {share}.", code=ExitCode.SYSTEM)
    try:
        shutil.rmtree(share)
        removed.append(str(share))
    except OSError as e:
        raise CprunError(f"cannot remove {share}.", f"Reason: {e.strerror}", code=ExitCode.SYSTEM)

    for item in removed:
        console.line(f"{console.tag()} Removed {item}")
    console.line(f"{console.tag()} Uninstallation complete.")
    console.line()
    console.line("Your configuration (~/.config/cprun) and contest files (.cc, .in, .out) were not touched.")
    return ExitCode.OK
