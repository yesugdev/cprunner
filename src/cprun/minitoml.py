"""A minimal TOML reader used when ``tomllib`` is unavailable (Python < 3.11).

Supports what cprun's configuration needs: top-level ``key = value`` pairs
with strings, integers, floats, booleans and flat arrays, plus comments.
"""

from __future__ import annotations

import re


class TomlError(ValueError):
    pass


_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\", "b": "\b", "f": "\f"}


def _strip_comment(line: str) -> str:
    quote = None
    i = 0
    while i < len(line):
        ch = line[i]
        if quote:
            if ch == "\\" and quote == '"':
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in ('"', "'"):
            quote = ch
        elif ch == "#":
            return line[:i]
        i += 1
    return line


def _split_array_items(body: str, lineno: int):
    items, current, quote, depth = [], [], None, 0
    i = 0
    while i < len(body):
        ch = body[i]
        if quote:
            current.append(ch)
            if ch == "\\" and quote == '"' and i + 1 < len(body):
                current.append(body[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in ('"', "'"):
            quote = ch
            current.append(ch)
        elif ch == "[":
            raise TomlError(f"line {lineno}: nested arrays are not supported")
        elif ch == ",":
            items.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
        i += 1
    if quote:
        raise TomlError(f"line {lineno}: unterminated string")
    last = "".join(current).strip()
    if last:
        items.append(last)
    if any(item == "" for item in items):
        raise TomlError(f"line {lineno}: empty array element")
    return items


def _parse_value(text: str, lineno: int):
    if not text:
        raise TomlError(f"line {lineno}: missing value")
    if text.startswith('"'):
        if len(text) < 2 or not text.endswith('"'):
            raise TomlError(f"line {lineno}: unterminated string")
        out, i, body = [], 0, text[1:-1]
        while i < len(body):
            ch = body[i]
            if ch == "\\":
                if i + 1 >= len(body) or body[i + 1] not in _ESCAPES:
                    raise TomlError(f"line {lineno}: invalid escape sequence")
                out.append(_ESCAPES[body[i + 1]])
                i += 2
                continue
            if ch == '"':
                raise TomlError(f"line {lineno}: unexpected quote in string")
            out.append(ch)
            i += 1
        return "".join(out)
    if text.startswith("'"):
        if len(text) < 2 or not text.endswith("'") or "'" in text[1:-1]:
            raise TomlError(f"line {lineno}: invalid literal string")
        return text[1:-1]
    if text.startswith("["):
        if not text.endswith("]"):
            raise TomlError(f"line {lineno}: arrays must be on a single line")
        return [_parse_value(item, lineno) for item in _split_array_items(text[1:-1], lineno)]
    if text == "true":
        return True
    if text == "false":
        return False
    cleaned = text.replace("_", "")
    if re.fullmatch(r"[+-]?\d+", cleaned):
        return int(cleaned)
    if re.fullmatch(r"[+-]?(\d+\.\d*|\.\d+|\d+)([eE][+-]?\d+)?", cleaned):
        return float(cleaned)
    raise TomlError(f"line {lineno}: invalid value: {text}")


def loads(text: str) -> dict:
    result = {}
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = _strip_comment(raw).strip()
        if not line:
            continue
        if line.startswith("["):
            raise TomlError(f"line {lineno}: tables are not supported in cprun configuration")
        key, sep, value = line.partition("=")
        if not sep:
            raise TomlError(f"line {lineno}: expected 'key = value'")
        key = key.strip()
        if len(key) >= 2 and key[0] == key[-1] and key[0] in ('"', "'"):
            key = key[1:-1]
        if not re.fullmatch(r"[A-Za-z0-9_-]+", key):
            raise TomlError(f"line {lineno}: invalid key: {key}")
        if key in result:
            raise TomlError(f"line {lineno}: duplicate key: {key}")
        result[key] = _parse_value(value.strip(), lineno)
    return result
