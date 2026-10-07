"""Watch mode: re-run whenever the source (or input / sample files) change.

Uses Linux inotify through ctypes (no dependencies, no busy polling). The
parent directory is watched rather than the file itself because many editors
save by writing a new file and renaming it over the old one. Falls back to
light polling where inotify is unavailable.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import os
import select
import struct
import sys
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

IN_MODIFY = 0x00000002
IN_CLOSE_WRITE = 0x00000008
IN_MOVED_TO = 0x00000080
IN_CREATE = 0x00000100
IN_DELETE = 0x00000200
_MASK = IN_MODIFY | IN_CLOSE_WRITE | IN_MOVED_TO | IN_CREATE | IN_DELETE
_EVENT_HEADER = struct.Struct("iIII")

DEBOUNCE_SECONDS = 0.15
POLL_SECONDS = 0.3


class InotifyWatcher:
    def __init__(self, directories: List[Path]):
        libc_name = ctypes.util.find_library("c") or "libc.so.6"
        self._libc = ctypes.CDLL(libc_name, use_errno=True)
        self.fd = self._libc.inotify_init1(os.O_NONBLOCK | os.O_CLOEXEC)
        if self.fd < 0:
            raise OSError(ctypes.get_errno(), "inotify_init1 failed")
        for d in directories:
            wd = self._libc.inotify_add_watch(self.fd, os.fsencode(str(d)), _MASK)
            if wd < 0:
                err = ctypes.get_errno()
                os.close(self.fd)
                raise OSError(err, f"cannot watch {d}")

    def wait(self, timeout: Optional[float]) -> List[str]:
        """Block until events arrive (or timeout) and return the changed file names."""
        ready, _, _ = select.select([self.fd], [], [], timeout)
        if not ready:
            return []
        names = []
        while True:
            try:
                data = os.read(self.fd, 64 * 1024)
            except BlockingIOError:
                break
            offset = 0
            while offset + _EVENT_HEADER.size <= len(data):
                _, _, _, length = _EVENT_HEADER.unpack_from(data, offset)
                offset += _EVENT_HEADER.size
                name = data[offset:offset + length].split(b"\0", 1)[0]
                offset += length
                if name:
                    names.append(os.fsdecode(name))
        return names

    def close(self) -> None:
        try:
            os.close(self.fd)
        except OSError:
            pass


class PollingWatcher:
    def __init__(self, directories: List[Path]):
        self.directories = directories

    def wait(self, timeout: Optional[float]) -> List[str]:
        time.sleep(POLL_SECONDS if timeout is None else min(timeout, POLL_SECONDS))
        return ["*"]  # the caller compares snapshots

    def close(self) -> None:
        pass


def make_watcher(directories: List[Path]):
    if not sys.platform.startswith("linux"):
        return PollingWatcher(directories), "polling"
    try:
        return InotifyWatcher(directories), "inotify"
    except (OSError, AttributeError):
        return PollingWatcher(directories), "polling"


Snapshot = Dict[str, Tuple[int, int]]


def snapshot(directories: List[Path], relevant: Callable[[str], bool]) -> Snapshot:
    state: Snapshot = {}
    for d in directories:
        try:
            with os.scandir(d) as it:
                for entry in it:
                    if relevant(entry.name):
                        try:
                            st = entry.stat()
                        except OSError:
                            continue
                        state[os.path.join(str(d), entry.name)] = (st.st_mtime_ns, st.st_size)
        except OSError:
            continue
    return state


def changed_files(before: Snapshot, after: Snapshot) -> List[str]:
    return sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))


def watch_loop(directories: List[Path], relevant: Callable[[str], bool],
               on_change: Callable[[List[str]], None]) -> str:
    """Call ``on_change(paths)`` whenever relevant files change. Runs until Ctrl+C."""
    watcher, kind = make_watcher(directories)
    state = snapshot(directories, relevant)
    try:
        while True:
            names = watcher.wait(None)
            if not any(n == "*" or relevant(n) for n in names):
                continue
            # Debounce: editors often produce several events per save.
            while watcher.wait(DEBOUNCE_SECONDS) and kind == "inotify":
                pass
            new_state = snapshot(directories, relevant)
            changes = changed_files(state, new_state)
            state = new_state
            if changes:
                # Changes made while on_change runs are still queued and
                # compared against ``state``, so they trigger another run.
                on_change(changes)
    finally:
        watcher.close()
