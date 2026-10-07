"""Run a compiled program with a time limit, capturing stdout and stderr.

On Linux, pipes are multiplexed with ``select``. Windows cannot select on
pipes, so there stdout/stderr are read by threads instead.
"""

from __future__ import annotations

import os
import selectors
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .errors import CprunError, ExitCode

try:
    import resource
except ImportError:  # pragma: no cover - non-POSIX
    resource = None

SIGNAL_HINTS = {
    "SIGSEGV": "invalid memory access: out-of-bounds index, null/dangling pointer, or stack overflow",
    "SIGABRT": "abort() was called: failed assert, uncaught exception, or std::bad_alloc",
    "SIGFPE": "arithmetic error: integer division or modulo by zero",
    "SIGBUS": "bus error: invalid memory access",
    "SIGILL": "illegal instruction: often a non-void function that does not return a value",
    "SIGKILL": "killed: possibly out of memory",
    "SIGTERM": "terminated by another process",
    # Windows exception codes (NTSTATUS)
    "ACCESS_VIOLATION": "invalid memory access: out-of-bounds index or null/dangling pointer",
    "STACK_OVERFLOW": "stack overflow: recursion is too deep",
    "INTEGER_DIVIDE_BY_ZERO": "integer division or modulo by zero",
    "STACK_BUFFER_OVERRUN": "abort() was called (failed assert, uncaught exception) or a buffer overrun",
    "ILLEGAL_INSTRUCTION": "illegal instruction: often a non-void function that does not return a value",
    "DLL_NOT_FOUND": "a required DLL was not found (e.g. libstdc++-6.dll); compile with -static",
    "NO_MEMORY": "out of memory",
    "HEAP_CORRUPTION": "heap corruption: writing outside of an allocated array",
    "CONTROL_C_EXIT": "stopped with Ctrl+C",
}

IS_WINDOWS = os.name == "nt"
USE_THREADS = IS_WINDOWS  # tests switch this on to exercise the Windows code path on Linux

WINDOWS_STATUS_NAMES = {
    0xC0000005: "ACCESS_VIOLATION",
    0xC00000FD: "STACK_OVERFLOW",
    0xC0000094: "INTEGER_DIVIDE_BY_ZERO",
    0xC0000409: "STACK_BUFFER_OVERRUN",
    0xC000001D: "ILLEGAL_INSTRUCTION",
    0xC0000135: "DLL_NOT_FOUND",
    0xC0000017: "NO_MEMORY",
    0xC0000374: "HEAP_CORRUPTION",
    0xC000013A: "CONTROL_C_EXIT",
    0xC000008E: "FLOAT_DIVIDE_BY_ZERO",
}

_CHUNK = 1 << 16


@dataclass
class RunResult:
    stdout: bytes
    stderr: bytes
    returncode: Optional[int]
    elapsed: float
    timed_out: bool = False
    output_limit_exceeded: bool = False

    @property
    def signal_number(self) -> Optional[int]:
        if self.returncode is not None and self.returncode < 0:
            return -self.returncode
        return None

    @property
    def windows_status(self) -> Optional[int]:
        """A Windows exception code such as 0xC0000005, if the program crashed with one."""
        if self.returncode is None or -256 < self.returncode < 0:
            return None  # small negative numbers are POSIX signals
        code = self.returncode & 0xFFFFFFFF
        return code if code >= 0xC0000000 else None

    @property
    def signal_name(self) -> Optional[str]:
        status = self.windows_status
        if status is not None:
            return WINDOWS_STATUS_NAMES.get(status, f"0x{status:08X}")
        num = self.signal_number
        if num is None:
            return None
        try:
            return signal.Signals(num).name
        except ValueError:
            return f"signal {num}"

    @property
    def exit_status(self) -> Optional[int]:
        """Exit status as a shell reports it (128 + signal for signals)."""
        num = self.signal_number
        if num is not None:
            return 128 + num
        return self.returncode

    @property
    def exit_status_text(self) -> str:
        status = self.windows_status
        if status is not None:
            return f"{status} (0x{status:08X})"
        return str(self.exit_status)

    @property
    def runtime_error(self) -> bool:
        return not self.timed_out and not self.output_limit_exceeded and self.returncode != 0

    @property
    def ok(self) -> bool:
        return not self.timed_out and not self.output_limit_exceeded and self.returncode == 0


def disable_core_dumps() -> None:
    """Skip core dumps for crashing programs. On Ubuntu, apport otherwise takes
    about a second to collect each SIGSEGV/SIGABRT before the process can be
    reaped. A limit of 1 byte (not 0) also disables pipe-based core handlers."""
    if resource is None:
        return
    try:
        _, hard = resource.getrlimit(resource.RLIMIT_CORE)
        resource.setrlimit(resource.RLIMIT_CORE, (min(1, hard) if hard != resource.RLIM_INFINITY else 1, hard))
    except (ValueError, OSError):
        pass


def disable_crash_dialogs() -> None:
    """Windows: don't show "program has stopped working" (or start a debugger) when a
    program crashes. The setting is inherited by child processes, so a crash
    becomes an exit code immediately instead of hanging until the time limit."""
    if not IS_WINDOWS:
        return
    try:
        import ctypes

        SEM_FAILCRITICALERRORS, SEM_NOGPFAULTERRORBOX, SEM_NOOPENFILEERRORBOX = 0x0001, 0x0002, 0x8000
        ctypes.windll.kernel32.SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX | SEM_NOOPENFILEERRORBOX)
    except (ImportError, AttributeError, OSError):
        pass


def raise_stack_limit(megabytes: int) -> None:
    """Raise the soft stack limit (inherited by the program) so deep recursion works
    like it does on most online judges. ``0`` keeps the system default."""
    if resource is None or megabytes <= 0:
        return
    try:
        soft, hard = resource.getrlimit(resource.RLIMIT_STACK)
        wanted = megabytes * 1024 * 1024
        if hard != resource.RLIM_INFINITY:
            wanted = min(wanted, hard)
        if soft == resource.RLIM_INFINITY or soft >= wanted:
            return
        resource.setrlimit(resource.RLIMIT_STACK, (wanted, hard))
    except (ValueError, OSError):
        pass


def _decode_status(status: int) -> int:
    if os.WIFSIGNALED(status):
        return -os.WTERMSIG(status)
    if os.WIFEXITED(status):
        return os.WEXITSTATUS(status)
    return status


def _kill_group(proc: subprocess.Popen) -> None:
    if IS_WINDOWS:
        # Kill the program and anything it started.
        try:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except OSError:
            pass
        try:
            proc.kill()
        except OSError:
            pass
        return
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        try:
            proc.kill()
        except OSError:
            pass


def _reap(proc: subprocess.Popen, deadline: Optional[float]) -> bool:
    """Wait for the process to exit. Returns False if ``deadline`` passed first."""
    delay = 0.0001
    while True:
        try:
            pid, status = os.waitpid(proc.pid, 0 if deadline is None else os.WNOHANG)
        except ChildProcessError:  # already reaped elsewhere
            proc.poll()
            return proc.returncode is not None
        if pid != 0:
            proc.returncode = _decode_status(status)
            return True
        if time.perf_counter() >= deadline:
            return False
        time.sleep(delay)
        delay = min(delay * 2, 0.005)


def _pump(proc: subprocess.Popen, data: Optional[bytes], deadline: float, limit: int):
    """Feed stdin and collect stdout/stderr until both close, the deadline passes,
    or the output limit is exceeded."""
    sel = selectors.DefaultSelector()
    out_fd, err_fd = proc.stdout.fileno(), proc.stderr.fileno()
    chunks = {out_fd: [], err_fd: []}
    sel.register(out_fd, selectors.EVENT_READ)
    sel.register(err_fd, selectors.EVENT_READ)

    in_fd = None
    view = memoryview(data) if data else None
    offset = 0
    if proc.stdin is not None:
        if data:
            in_fd = proc.stdin.fileno()
            os.set_blocking(in_fd, False)
            sel.register(in_fd, selectors.EVENT_WRITE)
        else:
            proc.stdin.close()

    total = 0
    timed_out = limit_hit = False
    try:
        while sel.get_map():
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                timed_out = True
                break
            for key, _ in sel.select(remaining):
                fd = key.fd
                if fd == in_fd:
                    try:
                        offset += os.write(fd, view[offset:offset + _CHUNK])
                    except BlockingIOError:
                        continue
                    except OSError:  # program exited or closed its stdin
                        offset = len(view)
                    if offset >= len(view):
                        sel.unregister(fd)
                        proc.stdin.close()
                        in_fd = None
                    continue
                chunk = os.read(fd, _CHUNK)
                if not chunk:
                    sel.unregister(fd)
                    continue
                chunks[fd].append(chunk)
                total += len(chunk)
                if limit and total > limit:
                    limit_hit = True
            if limit_hit:
                break
    finally:
        sel.close()
    return b"".join(chunks[out_fd]), b"".join(chunks[err_fd]), timed_out, limit_hit


def _run_threaded(proc: subprocess.Popen, data: Optional[bytes], start: float, timeout: float, limit: int):
    """Collect output with reader threads (works on Windows, where pipes cannot be selected)."""
    chunks = {"out": [], "err": []}
    total = [0]
    lock = threading.Lock()
    limit_event = threading.Event()

    def reader(stream, key):
        try:
            while True:
                chunk = stream.read1(_CHUNK)
                if not chunk:
                    break
                with lock:
                    chunks[key].append(chunk)
                    total[0] += len(chunk)
                    if limit and total[0] > limit:
                        limit_event.set()
                        break
        except (OSError, ValueError):
            pass

    def writer():
        try:
            proc.stdin.write(data)
        except (OSError, ValueError):  # program exited or closed its stdin
            pass
        finally:
            try:
                proc.stdin.close()
            except OSError:
                pass

    threads = [threading.Thread(target=reader, args=(proc.stdout, "out"), daemon=True),
               threading.Thread(target=reader, args=(proc.stderr, "err"), daemon=True)]
    if proc.stdin is not None:
        if data:
            threads.append(threading.Thread(target=writer, daemon=True))
        else:
            proc.stdin.close()
    for t in threads:
        t.start()

    deadline = start + timeout
    timed_out = limit_hit = False
    while True:
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            timed_out = True
            break
        try:
            proc.wait(timeout=min(remaining, 0.05))
            break
        except subprocess.TimeoutExpired:
            if limit_event.is_set():
                limit_hit = True
                break
    elapsed = time.perf_counter() - start
    if timed_out or limit_hit:
        _kill_group(proc)
        proc.wait()
    for t in threads:
        t.join(timeout=2)
    with lock:
        out, err = b"".join(chunks["out"]), b"".join(chunks["err"])
    return out, err, elapsed, timed_out, limit_hit or limit_event.is_set()


def run_program(executable: Path, *, stdin_path: Optional[Path] = None, stdin_data: Optional[bytes] = None,
                timeout: float = 2.0, cwd: Optional[Path] = None, output_limit: int = 256 << 20) -> RunResult:
    stdin_file = None
    if stdin_path is not None:
        try:
            stdin_file = open(stdin_path, "rb")
        except OSError as e:
            raise CprunError(f"cannot read {stdin_path}.", f"Reason: {e.strerror}", code=ExitCode.SYSTEM)
        stdin_arg = stdin_file
    elif stdin_data is not None:
        stdin_arg = subprocess.PIPE
    else:
        stdin_arg = subprocess.DEVNULL

    try:
        start = time.perf_counter()
        if IS_WINDOWS:
            # A separate process group: Ctrl+C reaches cprun, which then stops the program.
            extra = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        else:
            extra = {"start_new_session": True}
        proc = subprocess.Popen([str(executable)], stdin=stdin_arg, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, cwd=str(cwd) if cwd else None, **extra)
    except OSError as e:
        raise CprunError(f"cannot execute {executable}.", f"Reason: {e.strerror}", code=ExitCode.SYSTEM)
    finally:
        if stdin_file is not None:
            stdin_file.close()

    deadline = start + timeout
    try:
        if USE_THREADS:
            stdout, stderr, elapsed, timed_out, limit_hit = _run_threaded(
                proc, stdin_data, start, timeout, output_limit)
            return RunResult(stdout, stderr, proc.returncode, min(elapsed, timeout) if timed_out else elapsed,
                             timed_out, limit_hit)
        stdout, stderr, timed_out, limit_hit = _pump(proc, stdin_data, deadline, output_limit)
        if not (timed_out or limit_hit) and not _reap(proc, deadline):
            timed_out = True  # closed its output but kept running
        elapsed = time.perf_counter() - start
        if timed_out or limit_hit:
            _kill_group(proc)
            _reap(proc, None)
    except KeyboardInterrupt:
        _kill_group(proc)
        if USE_THREADS:
            proc.wait()
        else:
            _reap(proc, None)
        raise
    finally:
        for f in (proc.stdin, proc.stdout, proc.stderr):
            if f is not None:
                try:
                    f.close()
                except OSError:
                    pass

    return RunResult(
        stdout=stdout,
        stderr=stderr,
        returncode=proc.returncode,
        elapsed=min(elapsed, timeout) if timed_out else elapsed,
        timed_out=timed_out,
        output_limit_exceeded=limit_hit,
    )
