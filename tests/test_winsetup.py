import unittest

from tests.helpers import SRC  # noqa: F401  (sets up sys.path)

from cprun.winsetup import path_with, path_without

INSTALL = r"C:\Users\bat\AppData\Local\Programs\cprun"


class WindowsPathTest(unittest.TestCase):
    def test_add(self):
        self.assertEqual(path_with(r"C:\a;C:\b", INSTALL), r"C:\a;C:\b;" + INSTALL)
        self.assertEqual(path_with("", INSTALL), INSTALL)

    def test_add_is_idempotent_and_case_insensitive_on_windows_style_paths(self):
        once = path_with(r"C:\a", INSTALL)
        self.assertEqual(path_with(once, INSTALL), once)

    def test_remove(self):
        value = r"C:\a;" + INSTALL + r";C:\b"
        self.assertEqual(path_without(value, INSTALL), r"C:\a;C:\b")
        self.assertEqual(path_without(r"C:\a", INSTALL), r"C:\a")

    def test_empty_entries_are_dropped(self):
        self.assertEqual(path_without(r"C:\a;;" + INSTALL + ";", INSTALL), r"C:\a")


if __name__ == "__main__":
    unittest.main()
