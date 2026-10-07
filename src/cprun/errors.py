"""Exit codes and user-facing error types."""

from __future__ import annotations


class ExitCode:
    OK = 0
    FAILURE = 1  # runtime error, wrong answer, failed sample
    USAGE = 2  # invalid arguments / missing files the user must provide
    COMPILE = 3  # compilation failed
    TIMEOUT = 4  # time limit exceeded
    SYSTEM = 5  # configuration or system error
    INTERRUPTED = 130  # Ctrl+C


class CprunError(Exception):
    """An error that is shown to the user as a readable message.

    ``message`` is printed after ``[CPRUN] Error:``. Each extra block is
    printed after a blank line (details, how to fix it, ...).
    """

    def __init__(self, message: str, *blocks: str, code: int = ExitCode.SYSTEM):
        super().__init__(message)
        self.message = message
        self.blocks = [b for b in blocks if b]
        self.code = code


class UsageError(CprunError):
    def __init__(self, message: str, *blocks: str):
        super().__init__(message, *blocks, code=ExitCode.USAGE)


class ExitRequest(Exception):
    """Stop with an exit code; the reason has already been reported."""

    def __init__(self, code: int):
        super().__init__(code)
        self.code = code
