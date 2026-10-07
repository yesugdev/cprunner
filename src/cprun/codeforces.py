"""Download sample tests from a Codeforces problem page (optional, needs internet)."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path
from typing import List, Optional, Tuple

from .errors import CprunError, ExitCode
from .paths import ProblemPaths
from .samples import Sample

_URL_RE = re.compile(
    r"^https?://(?:[\w-]+\.)?codeforces\.(?:com|ml|es)/"
    r"(?:contest/(\d+)/problem/(\w+)|problemset/problem/(\d+)/(\w+)|gym/(\d+)/problem/(\w+))/?(?:[?#].*)?$",
    re.IGNORECASE,
)
_STEM_RE = re.compile(r"^(\d+)?([A-Za-z]\d?)$")
_DIR_PATTERNS = [
    re.compile(r"^(\d{1,6})$"),
    re.compile(r"(?:contest|cf|codeforces|round|gym)[-_ ]?(\d{1,6})$", re.IGNORECASE),
]


class CodeforcesError(CprunError):
    def __init__(self, message: str, *blocks: str):
        super().__init__(message, *blocks, code=ExitCode.FAILURE)


def problem_url(contest: str, index: str) -> str:
    kind = "gym" if int(contest) >= 100000 else "contest"
    return f"https://codeforces.com/{kind}/{contest}/problem/{index.upper()}"


def validate_url(url: str) -> str:
    if not _URL_RE.match(url.strip()):
        raise CprunError(
            f"not a Codeforces problem URL: {url}",
            "Expected for example:\n    https://codeforces.com/contest/1846/problem/D\n"
            "    https://codeforces.com/problemset/problem/1846/D",
            code=ExitCode.USAGE,
        )
    return url.strip()


def contest_from_directory(directory: Path) -> Optional[Tuple[str, str]]:
    """Look for a contest id in the source directory name or its parent's name."""
    for d in (directory, directory.parent):
        for pattern in _DIR_PATTERNS:
            m = pattern.search(d.name)
            if m:
                return m.group(1), d.name
    return None


def detect_url(paths: ProblemPaths, cf_contest: Optional[str]):
    """Return ``(url, explanation)`` or raise a CprunError explaining what is missing."""
    m = _STEM_RE.match(paths.stem)
    if not m:
        raise CprunError(
            f"cannot detect the Codeforces problem for {paths.name}.",
            "Name the file after the problem letter (D.cc) or give the URL:\n\n"
            f"    cprun {paths.name} --cf-url https://codeforces.com/contest/<id>/problem/<letter>",
            code=ExitCode.USAGE,
        )
    stem_contest, index = m.group(1), m.group(2).upper()
    if stem_contest:
        return problem_url(stem_contest, index), f"from file name {paths.name}"
    if cf_contest:
        return problem_url(cf_contest, index), "from configuration (cf_contest)"
    found = contest_from_directory(paths.directory)
    if found:
        return problem_url(found[0], index), f"from directory name '{found[1]}'"
    raise CprunError(
        "cannot detect the Codeforces contest id.",
        "Use one of:\n\n"
        f"    cprun {paths.name} --cf-url https://codeforces.com/contest/<id>/problem/{index}\n\n"
        "    a directory named after the contest id, e.g. 1846/ or contest-1846/\n\n"
        "    cf_contest = 1846   in cprun.toml in the contest directory",
        code=ExitCode.USAGE,
    )


class _SampleHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.div_stack: List[set] = []
        self.capture_kind: Optional[str] = None
        self.pre_depth = 0
        self.buffer: List[str] = []
        self.blocks: List[Tuple[str, str]] = []

    def _context_kind(self) -> Optional[str]:
        if not any("sample-test" in classes for classes in self.div_stack):
            return None
        for classes in reversed(self.div_stack):
            if "input" in classes:
                return "input"
            if "output" in classes:
                return "output"
        return None

    def handle_starttag(self, tag, attrs):
        if tag == "div":
            classes = set((dict(attrs).get("class") or "").split())
            self.div_stack.append(classes)
        elif tag == "pre":
            if self.pre_depth == 0:
                kind = self._context_kind()
                if kind:
                    self.capture_kind = kind
                    self.buffer = []
            self.pre_depth += 1
        elif tag == "br" and self.capture_kind:
            self.buffer.append("\n")

    def handle_endtag(self, tag):
        if tag == "div":
            if self.div_stack:
                self.div_stack.pop()
            if self.capture_kind and self.buffer and not self.buffer[-1].endswith("\n"):
                self.buffer.append("\n")
        elif tag == "pre" and self.pre_depth:
            self.pre_depth -= 1
            if self.pre_depth == 0 and self.capture_kind:
                self.blocks.append((self.capture_kind, "".join(self.buffer)))
                self.capture_kind = None

    def handle_data(self, data):
        if self.capture_kind:
            self.buffer.append(data)


def _normalize_block(text: str) -> bytes:
    lines = [ln.rstrip() for ln in text.replace("\r", "").split("\n")]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return ("\n".join(lines) + "\n").encode("utf-8") if lines else b""


def parse_problem_html(html: str, origin: str = "codeforces") -> List[Sample]:
    parser = _SampleHTMLParser()
    parser.feed(html)
    parser.close()
    samples = []
    pending_input: Optional[bytes] = None
    for kind, text in parser.blocks:
        if kind == "input":
            pending_input = _normalize_block(text)
        elif pending_input is not None:
            samples.append(Sample(pending_input, _normalize_block(text), origin))
            pending_input = None
    return samples


def fetch_samples(url: str, timeout: float = 10.0) -> List[Sample]:
    import urllib.error
    import urllib.request

    sep = "&" if "?" in url else "?"
    request = urllib.request.Request(
        url + f"{sep}locale=en",
        headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) cprun",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.8",
        },
    )
    fallback = "Save the samples manually in a .samples file and run with --samples."
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            html = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        reason = f"HTTP {e.code} {e.reason}"
        if e.code in (403, 503):
            reason += " (Codeforces may be blocking automated requests right now)"
        raise CodeforcesError(f"cannot download {url}", f"Reason: {reason}", fallback)
    except urllib.error.URLError as e:
        raise CodeforcesError(f"cannot download {url}", f"Reason: {e.reason} (no internet connection?)", fallback)
    except (OSError, ValueError) as e:
        raise CodeforcesError(f"cannot download {url}", f"Reason: {e}", fallback)

    samples = parse_problem_html(html, url)
    if not samples:
        raise CodeforcesError(
            f"no sample tests found on {url}",
            "The page may require a login, be a redirect/captcha page, or the problem may not exist.",
            fallback,
        )
    return samples


def cache_path(paths: ProblemPaths) -> Path:
    return paths.build_dir / f"{paths.stem}.cf.samples"
