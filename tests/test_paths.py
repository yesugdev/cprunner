import os
import unittest
from pathlib import Path

from tests.helpers import TempDirTestCase

from cprun.errors import ExitCode, UsageError
from cprun.paths import derive_paths, is_supported_source, resolve_source, split_source_name


class SourceDetectionTest(unittest.TestCase):
    def test_split_source_name(self):
        self.assertEqual(split_source_name("D.cc"), ("D", ".cc"))
        self.assertEqual(split_source_name("solution.cpp"), ("solution", ".cpp"))
        self.assertEqual(split_source_name("A.cxx"), ("A", ".cxx"))
        self.assertEqual(split_source_name("my.solution.cpp"), ("my.solution", ".cpp"))
        self.assertEqual(split_source_name("D"), ("D", ""))

    def test_supported_extensions(self):
        for name in ("D.cc", "D.cpp", "D.cxx", "main.cc", "D.CPP"):
            self.assertTrue(is_supported_source(name), name)
        for name in ("D", "D.java", "D.c", "D.py", "D.in", ".cpp"):
            self.assertFalse(is_supported_source(name), name)


class DerivedFileNamesTest(unittest.TestCase):
    def check(self, source, stem):
        p = derive_paths(Path("/contest/Round-724") / source)
        self.assertEqual(p.input, Path(f"/contest/Round-724/{stem}.in"))
        self.assertEqual(p.output, Path(f"/contest/Round-724/{stem}.out"))
        self.assertEqual(p.build_dir, Path("/contest/Round-724/.cprun"))
        self.assertEqual(p.stem, stem)

    def test_cc(self):
        self.check("D.cc", "D")

    def test_cpp(self):
        self.check("solution.cpp", "solution")

    def test_cxx(self):
        self.check("A.cxx", "A")

    def test_dotted_name(self):
        self.check("my.sol.cpp", "my.sol")

    def test_files_live_next_to_source(self):
        p = derive_paths("sub/dir/B.cc")
        self.assertEqual(p.input.parent, p.source.parent)
        self.assertEqual(p.output.parent, p.source.parent)
        self.assertTrue(p.source.is_absolute())


class ResolveSourceTest(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.old_cwd = os.getcwd()
        os.chdir(self.dir)

    def tearDown(self):
        os.chdir(self.old_cwd)
        super().tearDown()

    def test_valid_source(self):
        self.write("D.cc", "int main(){}")
        p = resolve_source("D.cc")
        self.assertEqual(p.source.parent.resolve(), self.dir.resolve())
        self.assertEqual(p.name, "D.cc")
        self.assertEqual(p.display(p.input), "D.in")

    def test_extension_required(self):
        self.write("D.cc", "int main(){}")
        with self.assertRaises(UsageError) as cm:
            resolve_source("D")
        self.assertIn("extension is required", cm.exception.message)
        self.assertEqual(cm.exception.code, ExitCode.USAGE)
        self.assertTrue(any("cprun D.cc" in b for b in cm.exception.blocks))

    def test_unsupported_extension(self):
        self.write("D.java", "class D {}")
        with self.assertRaises(UsageError) as cm:
            resolve_source("D.java")
        self.assertIn("unsupported source extension: .java", cm.exception.message)

    def test_missing_source(self):
        with self.assertRaises(UsageError) as cm:
            resolve_source("X.cc")
        self.assertIn("not found", cm.exception.message)
        self.assertIn("X.cc", cm.exception.blocks)

    def test_directory_is_rejected(self):
        (self.dir / "dir.cc").mkdir()
        with self.assertRaises(UsageError):
            resolve_source("dir.cc")


if __name__ == "__main__":
    unittest.main()
