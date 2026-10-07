"""Shared helpers for the cprun test suite."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

HAVE_GXX = shutil.which("g++") is not None
requires_gxx = unittest.skipUnless(HAVE_GXX, "g++ is not installed")

SUM_PROGRAM = """#include <iostream>
using namespace std;

int main() {
    int a, b;
    cin >> a >> b;
    cout << a + b << '\\n';
}
"""


def cprun_env(directory: Path, **extra) -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC)
    env["CPRUN_CONFIG"] = str(directory / "no-such-config.toml")
    env["NO_COLOR"] = "1"
    env.pop("XDG_CONFIG_HOME", None)
    env.update(extra)
    return env


def run_cprun(args, cwd: Path, stdin: bytes = b"", timeout: float = 60, **env_extra):
    return subprocess.run(
        [sys.executable, "-m", "cprun", *args],
        cwd=str(cwd),
        input=stdin,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=cprun_env(cwd, **env_extra),
        timeout=timeout,
    )


class TempDirTestCase(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="cprun-test-", suffix="-tmp"))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def write(self, name: str, content, directory: Path = None) -> Path:
        path = (directory or self.dir) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content)
        return path

    def compile(self, name: str, code: str) -> Path:
        src = self.write(name, code)
        exe = self.dir / (src.stem + ".exe")
        subprocess.run(["g++", "-O1", "-o", str(exe), str(src)], check=True)
        return exe
