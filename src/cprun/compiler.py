"""Compilation with a content-addressed cache in ``.cprun/``."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List

from .errors import CprunError, ExitCode
from .paths import ProblemPaths

CACHE_FORMAT = 1

IS_WINDOWS = os.name == "nt"
EXE_SUFFIX = ".exe" if IS_WINDOWS else ""

WINDOWS_GCC_INSTALL_HINT = """Install a C++ compiler (MinGW-w64 g++), for example with winget:

    winget install BrechtSanders.WinLibs.POSIX.UCRT

or with MSYS2 (https://www.msys2.org):

    pacman -S mingw-w64-ucrt-x86_64-gcc

and add C:\\msys64\\ucrt64\\bin to PATH.

Then open a new terminal and check:  g++ --version"""

GCC_INSTALL_HINT = """Install GCC:

Ubuntu/Debian:
    sudo apt install g++

Fedora:
    sudo dnf install gcc-c++

Arch:
    sudo pacman -S gcc"""

_STANDARD_RE = re.compile(r"^(c|gnu)\+\+(98|03|0x|11|1y|14|1z|17|2a|20|2b|23|2c|26)$")
VALID_STANDARDS_TEXT = "c++11, c++14, c++17, c++20, c++23, c++26 (or gnu++17, gnu++20, ...)"


def normalize_standard(value: str) -> str:
    """Accept ``c++20``, ``C++20``, ``cpp20``, ``20``, ``-std=c++20`` and return ``c++20``."""
    v = value.strip().lower().replace(" ", "")
    if v.startswith("-std="):
        v = v[len("-std="):]
    if re.fullmatch(r"\d{2}", v):
        v = "c++" + v
    elif v.startswith("cpp"):
        v = "c++" + v[3:]
    elif v.startswith("gnucpp"):
        v = "gnu++" + v[6:]
    if not _STANDARD_RE.match(v):
        raise ValueError(value)
    return v


def standard_label(standard: str) -> str:
    """``c++17`` -> ``C++17``, ``gnu++20`` -> ``GNU++20``."""
    return standard.upper()


def find_compiler(name: str) -> str:
    path = shutil.which(name)
    if path:
        return path
    if os.path.basename(name) in ("g++", "g++.exe"):
        hint = WINDOWS_GCC_INSTALL_HINT if IS_WINDOWS else GCC_INSTALL_HINT
        raise CprunError("g++ was not found.", hint, code=ExitCode.SYSTEM)
    raise CprunError(
        f"compiler '{name}' was not found.",
        "Check the --compiler option or the 'compiler' setting in ~/.config/cprun/config.toml.",
        code=ExitCode.SYSTEM,
    )


def _supports_diagnostic_color(compiler: str) -> bool:
    base = os.path.basename(compiler)
    return any(token in base for token in ("g++", "gcc", "clang", "c++"))


def _is_gcc_like(compiler: str) -> bool:
    base = os.path.basename(compiler).lower()
    return any(token in base for token in ("g++", "gcc", "clang", "c++"))


@dataclass
class BuildSettings:
    compiler: str
    compiler_path: str
    standard: str
    debug: bool
    flags: List[str]

    @property
    def standard_label(self) -> str:
        return standard_label(self.standard)


def make_build_settings(compiler: str, standard: str, debug: bool, optimization: str,
                        extra_flags: List[str], debug_flags: List[str]) -> BuildSettings:
    if debug:
        flags = list(debug_flags) + ["-pipe"]
    else:
        flags = [optimization, "-pipe"]
    if IS_WINDOWS and _is_gcc_like(compiler):
        # Static linking avoids "libstdc++-6.dll not found"; a 256 MB stack lets deep
        # recursion work (Windows' default stack is only 1 MB).
        flags += ["-static", "-Wl,--stack,268435456"]
    flags += list(extra_flags)
    return BuildSettings(
        compiler=compiler,
        compiler_path=find_compiler(compiler),
        standard=standard,
        debug=debug,
        flags=flags,
    )


@dataclass
class CompileResult:
    ok: bool
    diagnostics: str
    elapsed: float
    command: List[str]


def ensure_build_dir(path: Path) -> None:
    try:
        path.mkdir(exist_ok=True)
    except OSError as e:
        raise CprunError(
            f"cannot create build directory {path}.",
            f"Reason: {e.strerror}",
            "Check that you have write permission in this directory.",
            code=ExitCode.SYSTEM,
        )
    gitignore = path / ".gitignore"
    if not gitignore.exists():
        try:
            gitignore.write_text("# Created by cprun: build cache, safe to delete.\n*\n")
        except OSError:
            pass


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _parse_depfile(text: str) -> List[str]:
    """Parse a Makefile dependency file produced by ``-MMD``."""
    text = text.replace("\\\n", " ")
    _, sep, rest = text.partition(": ")
    if not sep:
        return []
    deps = []
    for token in re.split(r"(?<!\\)\s+", rest.strip()):
        if token:
            deps.append(token.replace("\\ ", " ").replace("$$", "$"))
    return deps


class Builder:
    def __init__(self, paths: ProblemPaths, settings: BuildSettings):
        self.paths = paths
        self.settings = settings
        suffix = "-debug" if settings.debug else ""
        self.executable = paths.build_dir / f"{paths.stem}{suffix}{EXE_SUFFIX}"
        self.meta_path = paths.build_dir / f"{paths.stem}{suffix}.meta"

    def _key(self) -> dict:
        try:
            source_hash = _file_sha256(self.paths.source)
        except OSError as e:
            raise CprunError(f"cannot read {self.paths.name}.", f"Reason: {e.strerror}", code=ExitCode.SYSTEM)
        compiler_real = os.path.realpath(self.settings.compiler_path)
        try:
            st = os.stat(compiler_real)
            compiler_id = [st.st_mtime_ns, st.st_size]
        except OSError:
            compiler_id = None
        return {
            "format": CACHE_FORMAT,
            "source": source_hash,
            "compiler": compiler_real,
            "compiler_id": compiler_id,
            "standard": self.settings.standard,
            "flags": list(self.settings.flags),
            "debug": self.settings.debug,
        }

    def is_up_to_date(self) -> bool:
        try:
            meta = json.loads(self.meta_path.read_text())
        except (OSError, ValueError):
            return False
        if not isinstance(meta, dict) or meta.get("key") != self._key():
            return False
        if not os.access(self.executable, os.X_OK):
            return False
        for dep in meta.get("deps", []):
            try:
                path, mtime_ns, size = dep
                st = os.stat(path)
            except (OSError, ValueError, TypeError):
                return False
            if st.st_mtime_ns != mtime_ns or st.st_size != size:
                return False
        return True

    def display_command(self) -> List[str]:
        rel_exe = os.path.join(self.paths.build_dir.name, self.executable.name)
        return [self.settings.compiler, f"-std={self.settings.standard}", *self.settings.flags,
                self.paths.name, "-o", rel_exe]

    def build(self, color: bool = False) -> CompileResult:
        build_dir = self.paths.build_dir
        ensure_build_dir(build_dir)
        key = self._key()  # hash the source *before* compiling it
        # Ends in .exe so MinGW does not append another extension.
        tmp_name = f".{self.executable.name}.{os.getpid()}.tmp.exe"
        tmp_exe = build_dir / tmp_name
        dep_file = build_dir / (tmp_name + ".d")
        rel = build_dir.name
        cmd = [self.settings.compiler_path, f"-std={self.settings.standard}", *self.settings.flags]
        if color and _supports_diagnostic_color(self.settings.compiler):
            cmd.append("-fdiagnostics-color=always")
        cmd += ["-MMD", "-MF", os.path.join(rel, dep_file.name),
                self.paths.name, "-o", os.path.join(rel, tmp_name)]

        start = time.perf_counter()
        try:
            proc = subprocess.run(cmd, cwd=str(self.paths.directory), stdin=subprocess.DEVNULL,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except OSError as e:
            raise CprunError(f"cannot run compiler {self.settings.compiler}.", f"Reason: {e.strerror}",
                             code=ExitCode.SYSTEM)
        except KeyboardInterrupt:
            self._remove(tmp_exe, dep_file)
            raise
        elapsed = time.perf_counter() - start
        diagnostics = (proc.stdout + proc.stderr).decode("utf-8", errors="replace")

        if proc.returncode != 0 or not tmp_exe.exists():
            self._remove(tmp_exe, dep_file)
            return CompileResult(False, diagnostics, elapsed, self.display_command())

        try:
            os.replace(tmp_exe, self.executable)
        except OSError as e:
            self._remove(tmp_exe, dep_file)
            blocks = [f"Reason: {e.strerror}"]
            if IS_WINDOWS:
                blocks.append("If the program is still running (e.g. in another terminal), close it and try again.")
            raise CprunError(f"cannot write {self.executable}.", *blocks, code=ExitCode.SYSTEM)

        deps = []
        try:
            for dep in _parse_depfile(dep_file.read_text(errors="replace")):
                dep_path = os.path.normpath(os.path.join(str(self.paths.directory), dep))
                if dep_path == os.path.normpath(str(self.paths.source)):
                    continue
                st = os.stat(dep_path)
                deps.append([dep_path, st.st_mtime_ns, st.st_size])
        except OSError:
            pass
        self._remove(dep_file)

        meta = {"key": key, "deps": deps, "built_at": time.time()}
        tmp_meta = self.meta_path.with_name(self.meta_path.name + ".tmp")
        try:
            tmp_meta.write_text(json.dumps(meta, indent=1))
            os.replace(tmp_meta, self.meta_path)
        except OSError:
            self._remove(tmp_meta)  # caching is best-effort
        return CompileResult(True, diagnostics, elapsed, self.display_command())

    @staticmethod
    def _remove(*paths: Path) -> None:
        for p in paths:
            try:
                p.unlink()
            except OSError:
                pass
