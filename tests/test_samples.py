import unittest

from tests.helpers import TempDirTestCase

from cprun.paths import derive_paths
from cprun.samples import (
    SampleParseError,
    discover_local_samples,
    find_numbered_pairs,
    format_samples,
    parse_samples_text,
)

TWO_TESTS = """=== TEST 1 ===
INPUT
5
1 2 3 4 5
OUTPUT
15

=== TEST 2 ===
INPUT
3
10 20 30
OUTPUT
60
"""


class ParseSamplesTest(unittest.TestCase):
    def test_multiple_tests(self):
        samples = parse_samples_text(TWO_TESTS)
        self.assertEqual(len(samples), 2)
        self.assertEqual(samples[0].input, b"5\n1 2 3 4 5\n")
        self.assertEqual(samples[0].expected, b"15\n")
        self.assertEqual(samples[1].input, b"3\n10 20 30\n")
        self.assertEqual(samples[1].expected, b"60\n")

    def test_trailing_blank_lines_are_dropped(self):
        samples = parse_samples_text("INPUT\n1 2\n\n\nOUTPUT\n3\n\n\n")
        self.assertEqual(samples[0].input, b"1 2\n")
        self.assertEqual(samples[0].expected, b"3\n")

    def test_headers_are_optional(self):
        samples = parse_samples_text("INPUT\n1\nOUTPUT\n2\nINPUT\n3\nOUTPUT\n4\n")
        self.assertEqual([s.expected for s in samples], [b"2\n", b"4\n"])

    def test_crlf_and_case_insensitive_markers(self):
        samples = parse_samples_text("=== test 1 ===\r\ninput:\r\n7\r\noutput:\r\n8\r\n")
        self.assertEqual(samples[0].input, b"7\n")
        self.assertEqual(samples[0].expected, b"8\n")

    def test_test_without_output_is_unchecked(self):
        samples = parse_samples_text("=== TEST 1 ===\nINPUT\n1 2\n")
        self.assertEqual(len(samples), 1)
        self.assertIsNone(samples[0].expected)

    def test_comments_outside_sections(self):
        samples = parse_samples_text("# downloaded\n\n=== TEST 1 ===\nINPUT\n#.#\nOUTPUT\n1\n")
        self.assertEqual(samples[0].input, b"#.#\n")  # '#' inside a section is data

    def test_input_can_contain_equals_rows(self):
        samples = parse_samples_text("=== TEST 1 ===\nINPUT\n=====\nOUTPUT\n0\n")
        self.assertEqual(samples[0].input, b"=====\n")

    def test_output_without_input_is_an_error(self):
        with self.assertRaises(SampleParseError) as cm:
            parse_samples_text("OUTPUT\n1\n", "D.samples")
        self.assertIn("line 1", cm.exception.message)

    def test_stray_text_is_an_error(self):
        with self.assertRaises(SampleParseError):
            parse_samples_text("hello\nINPUT\n1\nOUTPUT\n1\n")

    def test_empty_file(self):
        self.assertEqual(parse_samples_text(""), [])

    def test_format_round_trip(self):
        samples = parse_samples_text(TWO_TESTS)
        again = parse_samples_text(format_samples(samples, comment="source: test"))
        self.assertEqual([(s.input, s.expected) for s in samples], [(s.input, s.expected) for s in again])


class DiscoverSamplesTest(TempDirTestCase):
    def paths(self):
        self.write("D.cc", "int main(){}")
        return derive_paths(self.dir / "D.cc")

    def test_samples_file(self):
        self.write("D.samples", TWO_TESTS)
        samples, origins = discover_local_samples(self.paths())
        self.assertEqual(len(samples), 2)
        self.assertTrue(origins[0].endswith("D.samples"))

    def test_sample_file_and_samples_directory(self):
        self.write("D.sample", "INPUT\n1\nOUTPUT\n1\n")
        self.write("samples/D", "INPUT\n2\nOUTPUT\n2\n")
        self.write("samples/D.txt", "INPUT\n3\nOUTPUT\n3\n")
        samples, _ = discover_local_samples(self.paths())
        self.assertEqual([s.input for s in samples], [b"1\n", b"2\n", b"3\n"])

    def test_numbered_pairs_in_natural_order(self):
        for n in (10, 2, 1, 3):
            self.write(f"D{n}.in", f"{n}\n")
            self.write(f"D{n}.out", f"{n * 2}\n")
        samples, _ = discover_local_samples(self.paths())
        self.assertEqual([s.input for s in samples], [b"1\n", b"2\n", b"3\n", b"10\n"])
        self.assertEqual(samples[3].expected, b"20\n")

    def test_pairs_ignore_main_input_and_other_problems(self):
        self.write("D.in", "main input\n")
        self.write("D.out", "main output\n")
        self.write("D1.cc", "int main(){}")  # D1 is another problem (e.g. D1/D2)
        self.write("D1.in", "x\n")
        self.write("D2.in", "y\n")
        self.write("D2.ans", "z\n")
        self.write("E1.in", "other\n")
        pairs = find_numbered_pairs(self.dir, "D")
        self.assertEqual([(n, p.name, e.name) for n, p, e in pairs], [(2, "D2.in", "D2.ans")])

    def test_input_without_output_is_unchecked(self):
        self.write("D1.in", "1\n")
        samples, _ = discover_local_samples(self.paths())
        self.assertIsNone(samples[0].expected)

    def test_nested_samples_directory(self):
        self.write("samples/D/1.in", "a\n")
        self.write("samples/D/1.out", "b\n")
        self.write("samples/D/2.in", "c\n")
        self.write("samples/D/2.out", "d\n")
        samples, _ = discover_local_samples(self.paths())
        self.assertEqual([s.expected for s in samples], [b"b\n", b"d\n"])

    def test_no_samples(self):
        samples, origins = discover_local_samples(self.paths())
        self.assertEqual((samples, origins), ([], []))


if __name__ == "__main__":
    unittest.main()
