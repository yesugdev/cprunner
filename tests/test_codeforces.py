import unittest
from pathlib import Path

from tests.helpers import TempDirTestCase

from cprun.codeforces import detect_url, parse_problem_html, problem_url, validate_url
from cprun.errors import CprunError
from cprun.paths import derive_paths

FIXTURE = Path(__file__).parent / "fixtures" / "codeforces_problem.html"


class ParseHtmlTest(unittest.TestCase):
    def test_parses_both_page_formats(self):
        samples = parse_problem_html(FIXTURE.read_text())
        self.assertEqual(len(samples), 2)
        self.assertEqual(samples[0].input, b"2\n1 2\n3 4\n")
        self.assertEqual(samples[0].expected, b"3\n7\n")
        self.assertEqual(samples[1].input, b"1\n10 & 20\n")
        self.assertEqual(samples[1].expected, b"30\n")

    def test_page_without_samples(self):
        self.assertEqual(parse_problem_html("<html><pre>x</pre></html>"), [])


class UrlTest(TempDirTestCase):
    def test_problem_url(self):
        self.assertEqual(problem_url("1846", "d"), "https://codeforces.com/contest/1846/problem/D")
        self.assertEqual(problem_url("104114", "A"), "https://codeforces.com/gym/104114/problem/A")

    def test_validate_url(self):
        for url in ("https://codeforces.com/contest/724/problem/D",
                    "https://codeforces.com/problemset/problem/1846/D2",
                    "https://codeforces.com/gym/104114/problem/A",
                    "http://m1.codeforces.com/contest/724/problem/D/"):
            self.assertEqual(validate_url(url), url)
        for url in ("https://example.com/contest/724/problem/D", "codeforces.com/contest/1/problem/A", "D"):
            with self.assertRaises(CprunError):
                validate_url(url)

    def test_detect_from_file_name(self):
        p = derive_paths(self.dir / "1846D.cc")
        url, _ = detect_url(p, None)
        self.assertEqual(url, "https://codeforces.com/contest/1846/problem/D")

    def test_detect_from_config(self):
        p = derive_paths(self.dir / "B.cpp")
        url, how = detect_url(p, "1900")
        self.assertEqual(url, "https://codeforces.com/contest/1900/problem/B")
        self.assertIn("configuration", how)

    def test_detect_from_directory(self):
        for dirname in ("1846", "contest-1846", "cf1846", "Round-1846"):
            d = self.dir / dirname
            d.mkdir()
            url, _ = detect_url(derive_paths(d / "D.cc"), None)
            self.assertEqual(url, "https://codeforces.com/contest/1846/problem/D", dirname)

    def test_undetectable(self):
        d = self.dir / "practice"
        d.mkdir()
        with self.assertRaises(CprunError):
            detect_url(derive_paths(d / "D.cc"), None)
        with self.assertRaises(CprunError):
            detect_url(derive_paths(d / "solution.cc"), "1846")


if __name__ == "__main__":
    unittest.main()
