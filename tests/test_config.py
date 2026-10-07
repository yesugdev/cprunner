import os
import unittest
from unittest import mock

from tests.helpers import TempDirTestCase

from cprun import minitoml
from cprun.compiler import normalize_standard, standard_label
from cprun.config import Config, apply_values, load_config
from cprun.errors import CprunError


class StandardTest(unittest.TestCase):
    def test_normalize(self):
        for raw in ("c++20", "C++20", "cpp20", "20", "-std=c++20", " c++20 "):
            self.assertEqual(normalize_standard(raw), "c++20")
        self.assertEqual(normalize_standard("gnu++17"), "gnu++17")
        self.assertEqual(normalize_standard("c++23"), "c++23")

    def test_invalid(self):
        for raw in ("c++99", "java", "", "c++"):
            with self.assertRaises(ValueError):
                normalize_standard(raw)

    def test_label(self):
        self.assertEqual(standard_label("c++17"), "C++17")
        self.assertEqual(standard_label("gnu++20"), "GNU++20")


class MiniTomlTest(unittest.TestCase):
    def test_values(self):
        data = minitoml.loads(
            'compiler = "g++-13"  # comment\n'
            "standard = 'c++20'\n"
            "timeout = 2.5\n"
            "stack_mb = 512\n"
            "color = false\n"
            'flags = ["-DLOCAL", "-Wall"]\n'
            'path = "a#b\\tc"\n'
        )
        self.assertEqual(data["compiler"], "g++-13")
        self.assertEqual(data["standard"], "c++20")
        self.assertEqual(data["timeout"], 2.5)
        self.assertEqual(data["stack_mb"], 512)
        self.assertIs(data["color"], False)
        self.assertEqual(data["flags"], ["-DLOCAL", "-Wall"])
        self.assertEqual(data["path"], "a#b\tc")

    def test_errors(self):
        for text in ("x", "x = ", 'x = "open', "[table]", "x = 1\nx = 2", "x = bogus"):
            with self.assertRaises(minitoml.TomlError, msg=text):
                minitoml.loads(text)


class ConfigTest(TempDirTestCase):
    def test_defaults(self):
        with mock.patch.dict(os.environ, {"CPRUN_CONFIG": str(self.dir / "missing.toml")}):
            config = load_config(None)
        self.assertEqual(config.compiler, "g++")
        self.assertEqual(config.standard, "c++17")
        self.assertEqual(config.timeout, 2.0)
        self.assertEqual(config.optimization, "-O2")
        self.assertTrue(config.color)

    def test_global_and_local_files(self):
        global_cfg = self.write("global.toml", 'standard = "c++20"\ntimeout = 5\noptimization = "O3"\ncolor = false\n')
        contest = self.dir / "contest"
        contest.mkdir()
        self.write("cprun.toml", "timeout = 3\ncf_contest = 1846\nflags = \"-DLOCAL -Wshadow\"\n", contest)
        with mock.patch.dict(os.environ, {"CPRUN_CONFIG": str(global_cfg)}):
            config = load_config(contest)
        self.assertEqual(config.standard, "c++20")
        self.assertEqual(config.timeout, 3.0)  # local overrides global
        self.assertEqual(config.optimization, "-O3")
        self.assertFalse(config.color)
        self.assertEqual(config.cf_contest, "1846")
        self.assertEqual(config.flags, ["-DLOCAL", "-Wshadow"])
        self.assertEqual(len(config.loaded_files), 2)

    def test_invalid_values(self):
        for values in ({"timeout": -1}, {"timeout": "fast"}, {"standard": "c++99"}, {"color": "yes"},
                       {"flags": [1, 2]}, {"stack_mb": -5}, {"cf_contest": "abc"}):
            with self.assertRaises(CprunError, msg=str(values)) as cm:
                apply_values(Config(), values, self.dir / "config.toml")
            self.assertEqual(cm.exception.code, 5)

    def test_unknown_key_warns(self):
        config = Config()
        apply_values(config, {"colour": True}, self.dir / "c.toml")
        self.assertEqual(len(config.warnings), 1)

    def test_invalid_toml_file(self):
        bad = self.write("bad.toml", "timeout = = 3\n")
        with mock.patch.dict(os.environ, {"CPRUN_CONFIG": str(bad)}):
            with self.assertRaises(CprunError) as cm:
                load_config(None)
        self.assertEqual(cm.exception.code, 5)


if __name__ == "__main__":
    unittest.main()
