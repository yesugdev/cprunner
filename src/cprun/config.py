"""Configuration loading.

Precedence (lowest to highest):
    built-in defaults
    ~/.config/cprun/config.toml   (or $CPRUN_CONFIG, or $XDG_CONFIG_HOME/cprun/config.toml;
                                   on Windows %APPDATA%\\cprun\\config.toml)
    cprun.toml in the source directory or the nearest parent directory
    command-line options
"""

from __future__ import annotations

import os
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from .compiler import normalize_standard
from .errors import CprunError, ExitCode

LOCAL_CONFIG_NAME = "cprun.toml"


@dataclass
class Config:
    compiler: str = "g++"
    standard: str = "c++17"
    timeout: float = 2.0
    optimization: str = "-O2"
    flags: List[str] = field(default_factory=list)
    debug_flags: List[str] = field(default_factory=lambda: ["-g", "-O0", "-Wall", "-Wextra"])
    color: bool = True
    stack_mb: int = 1024
    output_limit_mb: int = 256
    display_lines: int = 200
    eps: Optional[float] = None
    cf_contest: Optional[str] = None
    template: Optional[str] = None
    loaded_files: List[Path] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def global_config_path() -> Path:
    override = os.environ.get("CPRUN_CONFIG")
    if override:
        return Path(os.path.expanduser(override))
    if os.name == "nt" and os.environ.get("APPDATA"):
        return Path(os.environ["APPDATA"]) / "cprun" / "config.toml"
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return Path(base) / "cprun" / "config.toml"


def find_local_config(start: Path) -> Optional[Path]:
    home = Path(os.path.expanduser("~")).resolve()
    current = start.resolve()
    while True:
        candidate = current / LOCAL_CONFIG_NAME
        if candidate.is_file():
            return candidate
        if current == home or current.parent == current:
            return None
        current = current.parent


def _parse_toml(text: str) -> dict:
    try:
        import tomllib  # Python 3.11+
    except ImportError:
        from . import minitoml

        return minitoml.loads(text)
    return tomllib.loads(text)


def _read_file(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise CprunError(f"cannot read configuration file {path}.", f"Reason: {e.strerror}", code=ExitCode.SYSTEM)
    try:
        return _parse_toml(text)
    except ValueError as e:  # tomllib.TOMLDecodeError and minitoml.TomlError are ValueErrors
        raise CprunError(
            f"invalid configuration file {path}.",
            f"Reason: {e}",
            "Fix the file or remove it to use the defaults.",
            code=ExitCode.SYSTEM,
        )


def _bad(path: Path, key: str, expected: str, value) -> CprunError:
    return CprunError(
        f"invalid value for '{key}' in {path}.",
        f"Expected {expected}, got: {value!r}",
        code=ExitCode.SYSTEM,
    )


def _as_flag_list(value, path, key) -> List[str]:
    if isinstance(value, str):
        return shlex.split(value)
    if isinstance(value, list) and all(isinstance(v, str) for v in value):
        return list(value)
    raise _bad(path, key, "a string or a list of strings", value)


def _positive_number(value, path, key) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise _bad(path, key, "a positive number", value)
    return float(value)


def _non_negative_int(value, path, key) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise _bad(path, key, "a non-negative integer", value)
    return value


def apply_values(config: Config, values: dict, path: Path) -> None:
    for key, value in values.items():
        if key == "compiler":
            if not isinstance(value, str) or not value.strip():
                raise _bad(path, key, "a compiler name such as \"g++\"", value)
            config.compiler = value.strip()
        elif key == "standard":
            try:
                config.standard = normalize_standard(str(value))
            except ValueError:
                raise _bad(path, key, "a C++ standard such as \"c++17\" or \"c++20\"", value)
        elif key == "timeout":
            config.timeout = _positive_number(value, path, key)
        elif key == "optimization":
            if not isinstance(value, str) or not value.strip():
                raise _bad(path, key, "a flag such as \"-O2\"", value)
            value = value.strip()
            config.optimization = value if value.startswith("-") else "-" + value
        elif key == "flags":
            config.flags = _as_flag_list(value, path, key)
        elif key == "debug_flags":
            config.debug_flags = _as_flag_list(value, path, key)
        elif key == "color":
            if isinstance(value, str) and value.lower() in ("auto", "always", "never"):
                config.color = value.lower() != "never"
            elif isinstance(value, bool):
                config.color = value
            else:
                raise _bad(path, key, "true or false", value)
        elif key == "stack_mb":
            config.stack_mb = _non_negative_int(value, path, key)
        elif key == "output_limit_mb":
            config.output_limit_mb = _non_negative_int(value, path, key)
        elif key == "display_lines":
            config.display_lines = _non_negative_int(value, path, key)
        elif key == "eps":
            config.eps = _positive_number(value, path, key)
        elif key == "template":
            if not isinstance(value, str) or not value.strip():
                raise _bad(path, key, "a path to a template file", value)
            template = os.path.expanduser(value.strip())
            if not os.path.isabs(template):
                template = str(path.parent / template)  # relative to the config file
            config.template = template
        elif key == "cf_contest":
            if isinstance(value, bool) or not isinstance(value, (int, str)) or not str(value).strip().isdigit():
                raise _bad(path, key, "a Codeforces contest id such as 1846", value)
            config.cf_contest = str(value).strip()
        else:
            config.warnings.append(f"unknown configuration key '{key}' in {path} (ignored)")


def load_config(source_dir: Optional[Path] = None) -> Config:
    config = Config()
    files = []
    global_path = global_config_path()
    if global_path.is_file():
        files.append(global_path)
    if source_dir is not None:
        local = find_local_config(source_dir)
        if local is not None and local not in files:
            files.append(local)
    for path in files:
        apply_values(config, _read_file(path), path)
        config.loaded_files.append(path)
    return config
