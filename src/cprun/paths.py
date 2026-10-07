"""Source file validation and derived file names (D.cc -> D.in, D.out, .cprun/)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .errors import UsageError

SUPPORTED_EXTENSIONS = (".cc", ".cpp", ".cxx")
BUILD_DIR_NAME = ".cprun"


def split_source_name(name: str):
    """Split ``D.cc`` into ``("D", ".cc")``. The extension is lowercased."""
    stem, ext = os.path.splitext(name)
    return stem, ext.lower()


def is_supported_source(name: str) -> bool:
    stem, ext = split_source_name(name)
    return bool(stem) and ext in SUPPORTED_EXTENSIONS


@dataclass(frozen=True)
class ProblemPaths:
    source: Path

    @property
    def directory(self) -> Path:
        return self.source.parent

    @property
    def name(self) -> str:
        return self.source.name

    @property
    def stem(self) -> str:
        return split_source_name(self.source.name)[0]

    @property
    def input(self) -> Path:
        return self.directory / f"{self.stem}.in"

    @property
    def output(self) -> Path:
        return self.directory / f"{self.stem}.out"

    @property
    def tests_dir(self) -> Path:
        """Folder for numbered tests: D_tests/1.in, D_tests/1.out, ..."""
        return self.directory / f"{self.stem}_tests"

    @property
    def build_dir(self) -> Path:
        return self.directory / BUILD_DIR_NAME

    def display(self, path: Path) -> str:
        """A short, readable form of ``path`` relative to the working directory."""
        try:
            rel = os.path.relpath(path)
        except ValueError:
            return str(path)
        if rel.startswith(os.pardir + os.sep + os.pardir):
            return str(path)
        return rel


def derive_paths(source) -> ProblemPaths:
    return ProblemPaths(Path(os.path.abspath(os.path.expanduser(str(source)))))


def resolve_source(arg: str, must_exist: bool = True) -> ProblemPaths:
    """Validate the source argument and return the derived paths.

    With ``must_exist=False`` a missing source is accepted (so it can be created),
    unless another source with the same name but a different extension exists.
    """
    if not arg:
        raise UsageError("no source file given.", "Usage:\n    cprun D.cc\n    cprun D.cpp")
    path = Path(os.path.expanduser(arg))
    stem, ext = split_source_name(path.name)

    if not stem or not ext:
        blocks = ["Usage:\n    cprun D.cc\n    cprun D.cpp"]
        candidates = [path.parent / (path.name + e) for e in SUPPORTED_EXTENSIONS]
        existing = [c for c in candidates if c.is_file()]
        if existing:
            blocks.append(f"Did you mean:\n    cprun {os.path.join(os.path.dirname(arg), existing[0].name)}")
        raise UsageError("source file extension is required.", *blocks)

    if ext not in SUPPORTED_EXTENSIONS:
        raise UsageError(
            f"unsupported source extension: {os.path.splitext(path.name)[1]}",
            "Currently supported:\n" + "\n".join(SUPPORTED_EXTENSIONS),
        )

    if not path.exists():
        if must_exist:
            raise UsageError("source file not found:", arg, f"To create it from the template, run:\n\n    cprun {arg}")
        parent = path.parent if str(path.parent) else Path(".")
        if not parent.is_dir():
            raise UsageError(f"directory not found: {parent}", "Create the directory first.")
        others = [parent / (stem + e) for e in SUPPORTED_EXTENSIONS if e != ext]
        existing = [o for o in others if o.exists()]
        if existing:
            raise UsageError(
                "source file not found:", arg,
                f"Did you mean:\n    cprun {os.path.join(os.path.dirname(arg), existing[0].name)}",
            )
    if path.is_dir():
        raise UsageError(f"{arg} is a directory, not a source file.")

    return derive_paths(path)
