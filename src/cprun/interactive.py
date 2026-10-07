"""Reading input typed by the user (or piped in) and saving it to the .in file."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from .errors import CprunError, ExitCode
from .term import Console, stream_is_tty

EOF_KEY = "Ctrl+Z, then Enter," if os.name == "nt" else "Ctrl+D"


def read_user_input(console: Console, stdin=None) -> bytes:
    """Read input until EOF (Ctrl+D on a Linux terminal, Ctrl+Z Enter on Windows)."""
    stdin = stdin if stdin is not None else sys.stdin
    tty = stream_is_tty(stdin)
    if tty:
        console.line("Enter input.")
        console.line(f"Press {EOF_KEY} when finished:")
        console.line()
    try:
        buffer = getattr(stdin, "buffer", None)
        data = buffer.read() if buffer is not None else stdin.read().encode("utf-8")
    except KeyboardInterrupt:
        console.line()
        raise CprunError("input cancelled. Nothing was saved.", code=ExitCode.INTERRUPTED)
    if tty:
        if data and not data.endswith(b"\n"):
            console.line()  # Ctrl+D pressed in the middle of a line
        console.line()
    if data and not data.endswith(b"\n"):
        data += b"\n"
    return data


def save_file(path: Path, data: bytes, display: str) -> None:
    """Write ``data`` to ``path`` atomically (never leaves a half-written file)."""
    tmp = path.with_name(f".{path.name}.cprun-tmp")
    try:
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except OSError as e:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise CprunError(
            f"{display} cannot be written.",
            f"Reason: {e.strerror}",
            "Check that you have write permission in this directory.",
            code=ExitCode.SYSTEM,
        )
