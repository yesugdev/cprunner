"""Terminal output: colors, message prefixes, and program output display.

Status messages ([CPRUN] ...) go to stderr so that the program's own stdout
stays clean when cprun is used in pipelines. Program output and sample test
results go to stdout.
"""

from __future__ import annotations

import os
import sys

_CODES = {
    "bold": "1",
    "dim": "2",
    "red": "31",
    "green": "32",
    "yellow": "33",
    "blue": "34",
    "magenta": "35",
    "cyan": "36",
}


_windows_vt_enabled = {}


def _enable_windows_vt(stream) -> bool:
    """Turn on ANSI escape processing in a Windows console (Windows 10+)."""
    try:
        fd = stream.fileno()
    except (AttributeError, ValueError, OSError):
        return False
    if fd in _windows_vt_enabled:
        return _windows_vt_enabled[fd]
    ok = False
    try:
        import ctypes
        import msvcrt

        kernel32 = ctypes.windll.kernel32
        handle = msvcrt.get_osfhandle(fd)
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
            ok = bool(kernel32.SetConsoleMode(handle, mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING))
    except (ImportError, AttributeError, OSError):
        ok = False
    _windows_vt_enabled[fd] = ok
    return ok


def stream_supports_color(stream) -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("TERM") == "dumb":
        return False
    try:
        if not stream.isatty():
            return False
    except (AttributeError, ValueError):
        return False
    if os.name == "nt":
        return _enable_windows_vt(stream)
    return True


def stream_is_tty(stream) -> bool:
    try:
        return stream.isatty()
    except (AttributeError, ValueError):
        return False


def format_time(seconds: float) -> str:
    return f"{seconds:.3f}s"


def truncate_lines(text: str, max_lines: int, max_width: int = 0):
    """Return (text, hidden_line_count), keeping at most ``max_lines`` lines."""
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    hidden = 0
    if max_lines > 0 and len(lines) > max_lines:
        hidden = len(lines) - max_lines
        lines = lines[:max_lines]
    if max_width > 0:
        lines = [ln if len(ln) <= max_width else ln[:max_width] + " ..." for ln in lines]
    return "\n".join(lines), hidden


class Console:
    def __init__(self, out=None, err=None, color: bool = True, quiet: bool = False, verbose: bool = False):
        self.out = out if out is not None else sys.stdout
        self.err = err if err is not None else sys.stderr
        self.color_out = False
        self.color_err = False
        self.quiet = quiet
        self.verbose_enabled = verbose
        self.configure(color=color)

    def configure(self, color=None, quiet=None, verbose=None) -> None:
        if color is not None:
            self.color_out = bool(color) and stream_supports_color(self.out)
            self.color_err = bool(color) and stream_supports_color(self.err)
        if quiet is not None:
            self.quiet = quiet
        if verbose is not None:
            self.verbose_enabled = verbose

    @property
    def out_is_tty(self) -> bool:
        return stream_is_tty(self.out)

    # -- styling -----------------------------------------------------------

    def style(self, text: str, *styles: str, stream: str = "err") -> str:
        enabled = self.color_err if stream == "err" else self.color_out
        if not enabled or not styles:
            return text
        codes = ";".join(_CODES[s] for s in styles)
        return f"\033[{codes}m{text}\033[0m"

    # -- raw writing -------------------------------------------------------

    def _stream(self, stream: str):
        return self.err if stream == "err" else self.out

    def write(self, text: str, stream: str = "err") -> None:
        f = self._stream(stream)
        f.write(text)
        f.flush()

    def line(self, text: str = "", stream: str = "err") -> None:
        self.write(text + "\n", stream)

    def write_bytes(self, data: bytes, stream: str = "out") -> None:
        f = self._stream(stream)
        f.flush()
        buffer = getattr(f, "buffer", None)
        if buffer is not None:
            buffer.write(data)
            buffer.flush()
        else:
            f.write(data.decode("utf-8", errors="replace"))
            f.flush()

    # -- message kinds -----------------------------------------------------

    def tag(self, stream: str = "err") -> str:
        return self.style("[CPRUN]", "cyan", stream=stream)

    def info(self, message: str) -> None:
        if not self.quiet:
            self.line(f"{self.tag()} {message}")

    def success(self, message: str) -> None:
        if not self.quiet:
            self.line(f"{self.tag()} {self.style(message, 'green')}")

    def verbose(self, message: str) -> None:
        if self.verbose_enabled:
            self.line(f"{self.tag()} {self.style(message, 'dim')}")

    def warning(self, message: str) -> None:
        self.line(f"{self.style('[WARNING]', 'yellow', 'bold')} {self.style(message, 'yellow')}")

    def error(self, message: str) -> None:
        self.line(f"{self.style('[CPRUN] Error:', 'red', 'bold')} {message}")

    def alert(self, message: str) -> None:
        """A prominent failure status line such as RUNTIME ERROR."""
        self.line(f"{self.tag()} {self.style(message, 'red', 'bold')}")

    def blank(self) -> None:
        if not self.quiet:
            self.line()

    def heading(self, text: str, stream: str = "err") -> None:
        if not self.quiet:
            self.line(self.style(text, "bold", stream=stream), stream)

    def show_error(self, message: str, blocks) -> None:
        self.error(message)
        for block in blocks:
            self.line()
            self.line(block)
