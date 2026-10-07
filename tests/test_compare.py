import unittest

from tests.helpers import SRC  # noqa: F401  (sets up sys.path)

from cprun.compare import compare, outputs_match, tokenize, tokens_equal


class TokenizeTest(unittest.TestCase):
    def test_whitespace_normalization(self):
        self.assertEqual(tokenize(b"  1   2\t3 \r\n\n4\n\n\n"), [b"1", b"2", b"3", b"4"])
        self.assertEqual(tokenize(b""), [])
        self.assertEqual(tokenize(b" \n\t\r\n"), [])


class CompareTest(unittest.TestCase):
    def test_equal_ignoring_layout(self):
        self.assertTrue(outputs_match(b"1 2 3", b"1    2\n3"))
        self.assertTrue(outputs_match(b"1 2 3\n", b"  1 2 3  \n\n\n"))
        self.assertTrue(outputs_match(b"1\t2", b"1 2"))
        self.assertTrue(outputs_match(b"YES\r\nNO\r\n", b"YES\nNO"))
        self.assertTrue(outputs_match(b"", b"\n\n"))

    def test_different_tokens_fail(self):
        self.assertFalse(outputs_match(b"1 2 3", b"1 2 4"))
        self.assertFalse(outputs_match(b"YES", b"yes"))
        self.assertFalse(outputs_match(b"12", b"1 2"))

    def test_mismatch_position_and_line(self):
        r = compare(b"YES NO YES YES", b"YES NO\nNO YES")
        self.assertFalse(r.ok)
        self.assertEqual(r.kind, "mismatch")
        self.assertEqual(r.position, 3)
        self.assertEqual(r.expected.text, b"YES")
        self.assertEqual(r.received.text, b"NO")
        self.assertEqual(r.received.line, 2)
        self.assertEqual(r.expected.line, 1)

    def test_missing_token(self):
        r = compare(b"1 2 3 4 5 6 42", b"1 2 3 4 5 6")
        self.assertEqual(r.kind, "missing")
        self.assertEqual(r.position, 7)
        self.assertEqual(r.expected.text, b"42")
        self.assertIsNone(r.received)

    def test_extra_tokens(self):
        r = compare(b"1 2 3 4 5 6 7 8 9 10", b"1 2 3 4 5 6 7 8 9 10 123 456")
        self.assertEqual(r.kind, "extra")
        self.assertEqual(r.position, 11)
        self.assertEqual(r.received.text, b"123")
        self.assertEqual((r.expected_count, r.received_count), (10, 12))

    def test_ok_result(self):
        r = compare(b"60\n", b"60")
        self.assertTrue(r.ok)
        self.assertEqual(r.kind, "ok")


class EpsilonTest(unittest.TestCase):
    def test_numeric_tolerance(self):
        self.assertTrue(tokens_equal(b"0.333333", b"0.3333334", 1e-6))
        self.assertTrue(tokens_equal(b"1000000.0", b"1000000.5", 1e-6))  # relative
        self.assertFalse(tokens_equal(b"0.3", b"0.4", 1e-6))
        self.assertFalse(tokens_equal(b"0.333333", b"0.3333334", None))
        self.assertFalse(tokens_equal(b"YES", b"NO", 1e-6))
        self.assertFalse(tokens_equal(b"nan", b"nan2", 1e-6))

    def test_compare_with_eps(self):
        self.assertTrue(compare(b"1.5 2.0", b"1.5000001 2", eps=1e-6).ok)
        self.assertFalse(compare(b"1.5 2.0", b"1.6 2", eps=1e-6).ok)


if __name__ == "__main__":
    unittest.main()
