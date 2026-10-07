"""Sample test discovery and the ``D.samples`` file format.

Format::

    === TEST 1 ===
    INPUT
    5
    1 2 3 4 5
    OUTPUT
    15

    === TEST 2 ===
    ...

Header lines (``=== TEST n ===``) are optional: an ``INPUT`` line after a
complete test starts a new test. Lines starting with ``#`` outside of
INPUT/OUTPUT sections are comments. A test without an OUTPUT section is run
but not checked.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from .errors import CprunError, ExitCode
from .paths import SUPPORTED_EXTENSIONS, ProblemPaths

_HEADER_RE = re.compile(r"^\s*=+\s*TEST\b[^=]*=+\s*$", re.IGNORECASE)
_INPUT_RE = re.compile(r"^\s*INPUT\s*:?\s*$", re.IGNORECASE)
_OUTPUT_RE = re.compile(r"^\s*OUTPUT\s*:?\s*$", re.IGNORECASE)


@dataclass
class Sample:
    input: bytes
    expected: Optional[bytes]
    origin: str  # where the test came from (shown next to the result)
    empty: bool = False  # an unfilled test file pair: skipped


class SampleParseError(CprunError):
    def __init__(self, origin: str, lineno: int, message: str):
        super().__init__(
            f"cannot parse sample file {origin} (line {lineno}): {message}",
            "Expected format:\n\n=== TEST 1 ===\nINPUT\n<input lines>\nOUTPUT\n<expected output lines>",
            code=ExitCode.USAGE,
        )


def _join(lines: List[str]) -> bytes:
    while lines and not lines[-1].strip():
        lines = lines[:-1]
    if not lines:
        return b""
    return ("\n".join(lines) + "\n").encode("utf-8")


def parse_samples_text(text: str, origin: str = "<samples>") -> List[Sample]:
    samples: List[Sample] = []
    input_lines: Optional[List[str]] = None
    output_lines: Optional[List[str]] = None
    section = None  # None, "input", "output"
    test_start = 0

    def finish():
        nonlocal input_lines, output_lines, section, test_start
        if input_lines is not None:
            expected = _join(output_lines) if output_lines is not None else None
            samples.append(Sample(_join(input_lines), expected, f"{origin}:{test_start}"))
        input_lines, output_lines, section, test_start = None, None, None, 0

    for lineno, line in enumerate(text.splitlines(), 1):
        if _HEADER_RE.match(line):
            finish()
            test_start = lineno
            continue
        if _INPUT_RE.match(line):
            if input_lines is not None:
                if output_lines is None:
                    raise SampleParseError(origin, lineno, "INPUT appears twice in the same test")
                finish()
            if not test_start:
                test_start = lineno
            input_lines, section = [], "input"
            continue
        if _OUTPUT_RE.match(line):
            if input_lines is None:
                raise SampleParseError(origin, lineno, "OUTPUT without a preceding INPUT")
            if output_lines is not None:
                raise SampleParseError(origin, lineno, "OUTPUT appears twice in the same test")
            output_lines, section = [], "output"
            continue
        if section == "input":
            input_lines.append(line)
        elif section == "output":
            output_lines.append(line)
        elif line.strip() and not line.lstrip().startswith("#"):
            raise SampleParseError(origin, lineno, "text outside of an INPUT or OUTPUT section")
    finish()
    return samples


def format_samples(samples: List[Sample], comment: str = "") -> str:
    parts = []
    if comment:
        parts.append(f"# {comment}\n\n")
    for i, s in enumerate(samples, 1):
        parts.append(f"=== TEST {i} ===\nINPUT\n")
        parts.append(s.input.decode("utf-8", errors="replace"))
        if s.expected is not None:
            parts.append("OUTPUT\n")
            parts.append(s.expected.decode("utf-8", errors="replace"))
        parts.append("\n")
    return "".join(parts)


def read_sample_file(path: Path, display: str) -> List[Sample]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        raise CprunError(f"cannot read {display}.", f"Reason: {e.strerror}", code=ExitCode.SYSTEM)
    return parse_samples_text(text, display)


def _read_bytes(path: Path, display: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as e:
        raise CprunError(f"cannot read {display}.", f"Reason: {e.strerror}", code=ExitCode.SYSTEM)


def find_numbered_pairs(directory: Path, stem: str, require_stem: bool = True):
    """Find ``D1.in``/``D1.out`` style pairs, sorted by number.

    Returns a list of ``(number, input_path, expected_path_or_None)``.
    Pairs whose name is itself a source file in the directory (``D1.cc`` next to
    ``D1.in``) are skipped: those belong to a different problem.
    """
    prefix = re.escape(stem) + r"[-_.]?"
    pattern = re.compile(rf"^{prefix if require_stem else '(?:' + prefix + ')?'}(\d+)\.in$")
    found = []
    try:
        entries = list(directory.iterdir())
    except OSError:
        return []
    for entry in entries:
        m = pattern.match(entry.name)
        if not m or not entry.is_file():
            continue
        base = entry.name[:-len(".in")]
        if require_stem and any((directory / (base + ext)).exists() for ext in SUPPORTED_EXTENSIONS):
            continue
        expected = None
        for ext in (".out", ".ans"):
            candidate = directory / (base + ext)
            if candidate.is_file():
                expected = candidate
                break
        found.append((int(m.group(1)), entry, expected))
    found.sort(key=lambda item: (item[0], item[1].name))
    return found


def _file_pair_sample(inp: Path, out: Optional[Path], paths: ProblemPaths) -> Sample:
    """A test from an .in/.out file pair. A blank .out means "not filled in yet":
    the test runs but is not checked. A pair where both files are blank is skipped."""
    data = _read_bytes(inp, paths.display(inp))
    expected = _read_bytes(out, paths.display(out)) if out is not None else None
    if expected is not None and not expected.strip():
        expected = None
    return Sample(data, expected, paths.display(inp), empty=not data.strip() and expected is None)


def _pairs_to_samples(pairs, paths: ProblemPaths) -> List[Sample]:
    return [_file_pair_sample(inp, out, paths) for _, inp, out in pairs]


def has_multiple_tests(paths: ProblemPaths) -> bool:
    """True if the problem has test files besides D.in / D.out."""
    directory, stem = paths.directory, paths.stem
    sample_dir = directory / "samples"
    for f in (directory / f"{stem}.samples", directory / f"{stem}.sample", sample_dir / stem,
              sample_dir / f"{stem}.txt", sample_dir / f"{stem}.samples"):
        if f.exists():
            return True
    if paths.tests_dir.is_dir() and find_numbered_pairs(paths.tests_dir, stem, require_stem=False):
        return True
    return bool(find_numbered_pairs(directory, stem))


def discover_local_samples(paths: ProblemPaths):
    """Return ``(samples, origins)`` for all local sample sources of the problem."""
    directory, stem = paths.directory, paths.stem
    samples: List[Sample] = []
    origins: List[str] = []

    # The main D.in / D.out pair (D.out holds the expected answer).
    if paths.input.is_file() and paths.output.is_file():
        main = _file_pair_sample(paths.input, paths.output, paths)
        if not main.empty:
            samples.append(main)
            origins.append(f"{paths.display(paths.input)} + {paths.display(paths.output)}")

    sample_dir = directory / "samples"
    files = [
        directory / f"{stem}.samples",
        directory / f"{stem}.sample",
        sample_dir / stem,
        sample_dir / f"{stem}.txt",
        sample_dir / f"{stem}.samples",
    ]
    for f in files:
        if f.is_file():
            found = read_sample_file(f, paths.display(f))
            if found:
                samples += found
                origins.append(paths.display(f))

    pairs = find_numbered_pairs(directory, stem)
    if pairs:
        samples += _pairs_to_samples(pairs, paths)
        origins.append(f"{len(pairs)} numbered .in/.out file(s)")

    for nested in (paths.tests_dir, sample_dir / stem):
        if nested.is_dir():
            pairs = find_numbered_pairs(nested, stem, require_stem=False)
            if pairs:
                samples += _pairs_to_samples(pairs, paths)
                origins.append(paths.display(nested) + "/")

    return samples, origins


NO_SAMPLES_HELP = """Create one of the following next to {name}:

    {stem}.samples        (or {stem}.sample, samples/{stem}, samples/{stem}.txt)

        === TEST 1 ===
        INPUT
        <input>
        OUTPUT
        <expected output>

    {stem}1.in + {stem}1.out, {stem}2.in + {stem}2.out, ...

Or download them from Codeforces:

    cprun {name} --cf-url https://codeforces.com/contest/<id>/problem/<letter>"""
