"""Token-based output comparison, like most online judge checkers.

Whitespace of any kind (spaces, tabs, newlines, CRLF) only separates tokens, so
leading/trailing whitespace, repeated spaces and trailing empty lines are ignored.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import List, Optional

_TOKEN_RE = re.compile(rb"\S+")
_NUMBER_RE = re.compile(rb"[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?")


@dataclass
class Token:
    text: bytes
    line: int  # 1-based line number in the output


@dataclass
class CompareResult:
    ok: bool
    kind: str  # "ok", "mismatch", "missing", "extra"
    position: int = 0  # 1-based token position of the first difference
    expected: Optional[Token] = None
    received: Optional[Token] = None
    expected_count: int = 0
    received_count: int = 0


def tokenize(data: bytes) -> List[bytes]:
    return data.split()


def tokenize_with_lines(data: bytes) -> List[Token]:
    tokens = []
    line = 1
    last = 0
    for m in _TOKEN_RE.finditer(data):
        line += data.count(b"\n", last, m.start())
        last = m.start()
        tokens.append(Token(m.group(), line))
    return tokens


def tokens_equal(expected: bytes, received: bytes, eps: Optional[float] = None) -> bool:
    if expected == received:
        return True
    if eps is None:
        return False
    if not (_NUMBER_RE.fullmatch(expected) and _NUMBER_RE.fullmatch(received)):
        return False
    try:
        a, b = float(expected), float(received)
    except ValueError:
        return False
    if math.isnan(a) or math.isnan(b):
        return False
    diff = abs(a - b)
    return diff <= eps or diff <= eps * abs(a)


def compare(expected: bytes, received: bytes, eps: Optional[float] = None) -> CompareResult:
    exp = tokenize_with_lines(expected.replace(b"\r", b""))
    got = tokenize_with_lines(received.replace(b"\r", b""))
    for i, (e, g) in enumerate(zip(exp, got)):
        if not tokens_equal(e.text, g.text, eps):
            return CompareResult(False, "mismatch", i + 1, e, g, len(exp), len(got))
    if len(got) < len(exp):
        i = len(got)
        return CompareResult(False, "missing", i + 1, exp[i], None, len(exp), len(got))
    if len(got) > len(exp):
        i = len(exp)
        return CompareResult(False, "extra", i + 1, None, got[i], len(exp), len(got))
    return CompareResult(True, "ok", 0, None, None, len(exp), len(got))


def outputs_match(expected: bytes, received: bytes, eps: Optional[float] = None) -> bool:
    return compare(expected, received, eps).ok
