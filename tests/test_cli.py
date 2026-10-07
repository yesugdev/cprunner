"""End-to-end tests: run the real ``cprun`` command in a temporary contest directory."""

import shutil
import unittest

from tests.helpers import SUM_PROGRAM, TempDirTestCase, requires_gxx, run_cprun

from cprun.cli import parse_args
from cprun.errors import UsageError


class ArgumentParsingTest(unittest.TestCase):
    def test_flags(self):
        a = parse_args(["D.cc", "--samples", "--debug", "--std=c++20", "--timeout=5"])
        self.assertEqual(a.source, "D.cc")
        self.assertTrue(a.samples and a.debug)
        self.assertEqual(a.std, "c++20")
        self.assertEqual(a.timeout, "5")

    def test_options_before_source(self):
        a = parse_args(["--input", "D.cpp"])
        self.assertTrue(a.input)
        self.assertEqual(a.source, "D.cpp")

    def test_conflicting_modes(self):
        for argv in (["D.cc", "--input", "--stdin"], ["D.cc", "--samples", "--stdin"], ["D.cc", "--nope"]):
            with self.assertRaises(UsageError):
                parse_args(argv)

    def test_no_abbreviations(self):
        with self.assertRaises(UsageError):
            parse_args(["D.cc", "--samp"])


class CliWithoutCompilerTest(TempDirTestCase):
    def test_no_arguments_shows_usage(self):
        r = run_cprun([], self.dir)
        self.assertEqual(r.returncode, 2)
        self.assertIn(b"Usage:\n    cprun <source>", r.stderr)
        self.assertIn(b"cprun D.cc --samples", r.stderr)

    def test_help_and_version(self):
        r = run_cprun(["--help"], self.dir)
        self.assertEqual(r.returncode, 0)
        self.assertIn(b"--samples", r.stdout)
        r = run_cprun(["--version"], self.dir)
        self.assertEqual(r.returncode, 0)
        self.assertRegex(r.stdout, rb"^cprun \d+\.\d+\.\d+\n$")

    def test_extension_required(self):
        self.write("D.cc", SUM_PROGRAM)
        r = run_cprun(["D"], self.dir)
        self.assertEqual(r.returncode, 2)
        self.assertIn(b"[CPRUN] Error: source file extension is required.", r.stderr)

    def test_unsupported_extension(self):
        r = run_cprun(["D.java"], self.dir)
        self.assertEqual(r.returncode, 2)
        self.assertIn(b"unsupported source extension: .java", r.stderr)
        self.assertIn(b".cc\n.cpp\n.cxx", r.stderr)

    def test_missing_source_is_created_from_template(self):
        r = run_cprun(["D.cc"], self.dir)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(b"Created D.cc from the default template", r.stderr)
        self.assertIn(b"int main()", (self.dir / "D.cc").read_bytes())
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), ["D.cc", "D.in", "D.out"])

    def test_samples_n_creates_missing_source(self):
        r = run_cprun(["A.cc", "samples", "5"], self.dir)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.dir / "A.cc").is_file())
        self.assertTrue((self.dir / "A_tests" / "5.out").is_file())
        self.assertFalse((self.dir / "A.in").exists())

    def test_user_template(self):
        cfg_dir = self.dir / "cfg"
        self.write("template.cpp", "// my template\n", cfg_dir)
        r = run_cprun(["B.cpp"], self.dir, CPRUN_CONFIG=str(cfg_dir / "config.toml"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.dir / "B.cpp").read_text(), "// my template\n")
        self.write("config.toml", 'template = "other.cpp"\n', cfg_dir)
        self.write("other.cpp", "// other\n", cfg_dir)
        run_cprun(["C.cc"], self.dir, CPRUN_CONFIG=str(cfg_dir / "config.toml"))
        self.assertEqual((self.dir / "C.cc").read_text(), "// other\n")

    def test_existing_source_is_never_replaced(self):
        self.write("D.cc", "// mine\n")
        run_cprun(["D.cc", "samples", "1"], self.dir)
        self.assertEqual((self.dir / "D.cc").read_text(), "// mine\n")

    def test_missing_source_not_created_in_other_modes(self):
        for args in (["--samples"], ["--stdin"], ["--input"]):
            r = run_cprun(["D.cc", *args], self.dir)
            self.assertEqual(r.returncode, 2, args)
            self.assertIn(b"source file not found:\n\nD.cc", r.stderr)
            self.assertFalse((self.dir / "D.cc").exists())

    def test_other_extension_is_not_created(self):
        self.write("D.cc", SUM_PROGRAM)
        r = run_cprun(["D.cpp"], self.dir)
        self.assertEqual(r.returncode, 2)
        self.assertIn(b"cprun D.cc", r.stderr)
        self.assertFalse((self.dir / "D.cpp").exists())

    def test_invalid_option_values(self):
        self.write("D.cc", SUM_PROGRAM)
        for args in (["--timeout=abc"], ["--timeout=-1"], ["--std=c++99"], ["--watch", "--stdin"],
                     ["--input", "--cf"], ["--eps=x"], ["--run"], ["--verbose"], ["-q"], ["--force"],
                     ["--compiler=clang++"], ["--no-color"]):
            r = run_cprun(["D.cc", *args], self.dir)
            self.assertEqual(r.returncode, 2, args)
            self.assertIn(b"[CPRUN] Error:", r.stderr)
            self.assertNotIn(b"Traceback", r.stderr)

    def test_missing_compiler(self):
        self.write("D.cc", SUM_PROGRAM)
        cfg = self.write("cfg.toml", 'compiler = "no-such-compiler++"\n')
        r = run_cprun(["D.cc"], self.dir, CPRUN_CONFIG=str(cfg))
        self.assertEqual(r.returncode, 5)
        self.assertIn(b"compiler 'no-such-compiler++' was not found", r.stderr)

    def test_invalid_config(self):
        self.write("D.cc", SUM_PROGRAM)
        cfg = self.write("bad.toml", "timeout = -3\n")
        r = run_cprun(["D.cc"], self.dir, CPRUN_CONFIG=str(cfg))
        self.assertEqual(r.returncode, 5)
        self.assertIn(b"invalid value for 'timeout'", r.stderr)


@requires_gxx
class NormalModeTest(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.write("D.cc", SUM_PROGRAM)

    def test_first_run_creates_empty_input_and_output(self):
        r = run_cprun(["D.cc"], self.dir)
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn(b"[CPRUN] Created D.in and D.out.", r.stderr)
        self.assertIn(b"expected output in D.out", r.stderr)
        self.assertNotIn(b"Compiling", r.stderr)
        self.assertEqual((self.dir / "D.in").read_bytes(), b"")
        self.assertEqual((self.dir / "D.out").read_bytes(), b"")
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), ["D.cc", "D.in", "D.out"])

    def test_accepted(self):
        self.write("D.in", "10 20\n")
        self.write("D.out", "30\n")
        r = run_cprun(["D.cc"], self.dir)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(b"[CPRUN] Compiling D.cc with C++17...", r.stderr)
        self.assertIn(b"[CPRUN] ACCEPTED", r.stderr)
        self.assertRegex(r.stderr, rb"\[CPRUN\] Time: \d+\.\d{3}s")
        self.assertEqual(r.stdout, b"30\n")
        self.assertEqual((self.dir / ".cprun" / "D.actual").read_bytes(), b"30\n")

    def test_accepted_ignores_whitespace_differences(self):
        self.write("D.in", "1 2\n")
        self.write("D.out", "  3  \r\n\n\n")
        self.assertEqual(run_cprun(["D.cc"], self.dir).returncode, 0)

    def test_wrong_answer(self):
        self.write("D.in", "10 20\n")
        self.write("D.out", "31\n")
        r = run_cprun(["D.cc"], self.dir)
        self.assertEqual(r.returncode, 1)
        self.assertIn(b"[CPRUN] WRONG ANSWER", r.stderr)
        self.assertIn(b"Mismatch at token 1 (line 1):\nExpected: 31\nReceived: 30", r.stderr)
        self.assertEqual((self.dir / "D.out").read_bytes(), b"31\n")  # expected answer is never overwritten

    def test_empty_expected_output_is_not_checked(self):
        self.write("D.in", "1 2\n")
        r = run_cprun(["D.cc"], self.dir)  # D.out is created empty
        self.assertEqual(r.returncode, 0)
        self.assertIn(b"[CPRUN] Created D.out.", r.stderr)
        self.assertIn(b"D.out is empty", r.stderr)
        self.assertEqual(r.stdout, b"3\n")


    def test_existing_files_are_not_modified(self):
        self.write("D.in", "1 2\n")
        self.write("D.out", "3\n")
        r = run_cprun(["D.cc"], self.dir, stdin=b"100 200\n")
        self.assertEqual(r.returncode, 0)
        self.assertIn(b"[CPRUN] Input: D.in   Expected output: D.out", r.stderr)
        self.assertEqual((self.dir / "D.in").read_bytes(), b"1 2\n")
        self.assertEqual((self.dir / "D.out").read_bytes(), b"3\n")


    def test_input_mode_replaces_input(self):
        self.write("D.in", "1 2\n")
        r = run_cprun(["D.cc", "--input"], self.dir, stdin=b"30 30\n")
        self.assertEqual(r.returncode, 0)
        self.assertIn(b"[CPRUN] Direct input mode", r.stderr)
        self.assertIn(b"[CPRUN] Created D.out.", r.stderr)
        self.assertIn(b"[CPRUN] Input saved to D.in", r.stderr)
        self.assertEqual((self.dir / "D.in").read_bytes(), b"30 30\n")
        self.assertEqual(r.stdout, b"60\n")

    def test_stderr_is_shown_but_not_compared(self):
        self.write("E.cc", '#include <cstdio>\nint main(){puts("answer");fprintf(stderr,"debug info\\n");}')
        self.write("E.in", "")
        self.write("E.out", "answer\n")
        r = run_cprun(["E.cc"], self.dir)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(b"stderr:\ndebug info", r.stderr)
        self.assertIn(b"ACCEPTED", r.stderr)
        self.assertEqual(r.stdout, b"answer\n")

    def test_cache_and_recompile(self):
        self.write("D.in", "1 2\n")
        r1 = run_cprun(["D.cc"], self.dir)
        self.assertIn(b"Compiling", r1.stderr)
        r2 = run_cprun(["D.cc"], self.dir)
        self.assertIn(b"[CPRUN] D.cc unchanged.\n[CPRUN] Using cached executable.", r2.stderr)
        r3 = run_cprun(["D.cc", "--std=c++20"], self.dir)
        self.assertIn(b"Compiling D.cc with C++20", r3.stderr)
        shutil.rmtree(self.dir / ".cprun")  # deleting the cache forces a rebuild
        r4 = run_cprun(["D.cc"], self.dir)
        self.assertIn(b"Compiling", r4.stderr)
        self.write("D.cc", SUM_PROGRAM.replace("a + b", "a * b"))
        r5 = run_cprun(["D.cc"], self.dir)
        self.assertIn(b"Compiling", r5.stderr)
        self.assertEqual(r5.stdout, b"2\n")

    def test_debug_mode_uses_separate_executable(self):
        self.write("D.in", "1 2\n")
        r = run_cprun(["D.cc", "--debug"], self.dir)
        self.assertEqual(r.returncode, 0)
        self.assertIn(b"[CPRUN] DEBUG MODE", r.stderr)
        self.assertTrue((self.dir / ".cprun" / "D-debug").is_file())

    def test_compilation_failure(self):
        self.write("B.cc", "int main() { undeclared_function(); }\n")
        self.write("B.in", "\n")
        r = run_cprun(["B.cc"], self.dir)
        self.assertEqual(r.returncode, 3)
        self.assertIn(b"[CPRUN] Compilation failed.", r.stderr)
        self.assertIn(b"undeclared_function", r.stderr)
        self.assertNotIn(b"Running", r.stderr)
        self.assertEqual((self.dir / "B.out").read_bytes(), b"")

    def test_runtime_error(self):
        self.write("S.cc", "int main(){volatile int*p=nullptr;*p=1;}")
        self.write("S.in", "")
        r = run_cprun(["S.cc"], self.dir)
        self.assertEqual(r.returncode, 1)
        self.assertIn(b"[CPRUN] RUNTIME ERROR", r.stderr)
        self.assertIn(b"Exit code: 139", r.stderr)
        self.assertIn(b"Signal: SIGSEGV", r.stderr)

    def test_nonzero_exit_code(self):
        self.write("N.cc", "int main(){return 7;}")
        self.write("N.in", "")
        r = run_cprun(["N.cc"], self.dir)
        self.assertEqual(r.returncode, 1)
        self.assertIn(b"Exit code: 7", r.stderr)

    def test_timeout(self):
        self.write("L.cc", "int main(){volatile long x=0;for(;;)x++;}")
        self.write("L.in", "")
        r = run_cprun(["L.cc", "--timeout=0.5"], self.dir, timeout=30)
        self.assertEqual(r.returncode, 4)
        self.assertIn(b"[CPRUN] TIME LIMIT EXCEEDED", r.stderr)
        self.assertIn(b"Limit: 0.50 seconds", r.stderr)

    def test_timeout_from_config(self):
        self.write("L.cc", "int main(){volatile long x=0;for(;;)x++;}")
        self.write("L.in", "")
        self.write("cprun.toml", "timeout = 0.4\n")
        r = run_cprun(["L.cc"], self.dir, timeout=30)
        self.assertIn(b"Limit: 0.40 seconds", r.stderr)
        r = run_cprun(["L.cc", "--timeout=0.3"], self.dir, timeout=30)  # CLI overrides config
        self.assertIn(b"Limit: 0.30 seconds", r.stderr)

    def test_source_in_other_directory(self):
        sub = self.dir / "round"
        sub.mkdir()
        self.write("A.cpp", SUM_PROGRAM, sub)
        run_cprun(["round/A.cpp"], self.dir)
        self.assertTrue((sub / "A.in").is_file())
        self.assertTrue((sub / "A.out").is_file())
        (sub / "A.in").write_text("5 6\n")
        (sub / "A.out").write_text("11\n")
        r = run_cprun(["round/A.cpp"], self.dir)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((sub / ".cprun" / "A").is_file())


@requires_gxx
class MultipleTestsTest(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.write("a.cc", SUM_PROGRAM)

    def test_create_numbered_test_files(self):
        r = run_cprun(["a.cc", "samples", "3"], self.dir)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), ["a.cc", "a_tests"])
        names = sorted(p.name for p in (self.dir / "a_tests").iterdir())
        self.assertEqual(names, ["1.in", "1.out", "2.in", "2.out", "3.in", "3.out"])
        self.assertIn(b"Created 6 file(s) in a_tests/", r.stderr)

    def test_create_keeps_existing_files(self):
        self.write("a_tests/1.in", "1 2\n")
        r = run_cprun(["a.cc", "--samples", "2"], self.dir)  # alternative spelling
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.dir / "a_tests" / "1.in").read_text(), "1 2\n")
        self.assertTrue((self.dir / "a_tests" / "2.out").is_file())
        self.assertIn(b"Kept existing file(s) in a_tests/: 1.in", r.stderr)

    def test_each_problem_has_its_own_folder(self):
        self.write("D1.cc", SUM_PROGRAM)
        self.write("D2.cc", SUM_PROGRAM)
        run_cprun(["D1.cc", "samples", "2"], self.dir)
        run_cprun(["D2.cc", "samples", "1"], self.dir)
        self.assertTrue((self.dir / "D1_tests" / "2.out").is_file())
        self.assertTrue((self.dir / "D2_tests" / "1.in").is_file())
        self.assertFalse((self.dir / "D2_tests" / "2.in").exists())

    def test_invalid_create_commands(self):
        for args in (["samples", "0"], ["samples", "x"], ["samples"], ["foo", "3"], ["3"]):
            r = run_cprun(["a.cc", *args], self.dir)
            self.assertEqual(r.returncode, 2, args)

    def test_plain_run_checks_all_numbered_tests(self):
        for i, (inp, out) in enumerate([("1 2", "3"), ("5 5", "10"), ("0 0", "0")], 1):
            self.write(f"a_tests/{i}.in", inp + "\n")
            self.write(f"a_tests/{i}.out", out + "\n")
        r = run_cprun(["a.cc"], self.dir)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(b"3 / 3 tests passed", r.stdout)
        self.assertRegex(r.stdout, rb"\[TEST 2\] PASSED +\d\.\d{3}s +a_tests/2\.in")
        self.assertFalse((self.dir / "a.in").exists())  # no single-test files are created

    def test_old_style_numbered_files_still_work(self):
        self.write("a1.in", "1 2\n")
        self.write("a1.out", "3\n")
        r = run_cprun(["a.cc"], self.dir)
        self.assertIn(b"1 / 1 tests passed", r.stdout)

    def test_plain_run_reports_wrong_answer(self):
        self.write("a1.in", "1 2\n")
        self.write("a1.out", "3\n")
        self.write("a2.in", "5 5\n")
        self.write("a2.out", "11\n")
        r = run_cprun(["a.cc"], self.dir)
        self.assertEqual(r.returncode, 1)
        self.assertIn(b"[TEST 2] FAILED", r.stdout)
        self.assertIn(b"Expected: 11\nReceived: 10", r.stdout)

    def test_empty_tests_are_skipped(self):
        run_cprun(["a.cc", "samples", "3"], self.dir)
        r = run_cprun(["a.cc"], self.dir)
        self.assertEqual(r.returncode, 2)
        self.assertIn(b"all tests are empty", r.stderr)
        self.write("a_tests/1.in", "2 3\n")
        self.write("a_tests/1.out", "5\n")
        r = run_cprun(["a.cc"], self.dir)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(b"Skipping 2 empty test(s): a_tests/2.in, a_tests/3.in", r.stderr)
        self.assertIn(b"1 / 1 tests passed", r.stdout)

    def test_blank_expected_output_is_not_checked(self):
        self.write("a1.in", "2 3\n")
        self.write("a1.out", "")
        r = run_cprun(["a.cc"], self.dir)
        self.assertEqual(r.returncode, 0)
        self.assertIn(b"NOT CHECKED", r.stdout)

    def test_main_pair_and_numbered_tests_together(self):
        self.write("a.in", "1 1\n")
        self.write("a.out", "2\n")
        self.write("a1.in", "2 2\n")
        self.write("a1.out", "4\n")
        r = run_cprun(["a.cc"], self.dir)
        self.assertIn(b"2 / 2 tests passed", r.stdout)


@requires_gxx
class HandModeTest(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.write("A.cc", SUM_PROGRAM)

    def test_hand_runs_with_terminal_input_and_creates_no_files(self):
        r = run_cprun(["A.cc", "hand"], self.dir, stdin=b"4 5\n")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, b"9\n")
        self.assertIn(b"Program finished.", r.stderr)
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), [".cprun", "A.cc"])

    def test_hand_ignores_test_files(self):
        self.write("A_tests/1.in", "1 1\n")
        self.write("A_tests/1.out", "999\n")
        r = run_cprun(["A.cc", "hand"], self.dir, stdin=b"2 2\n")
        self.assertEqual((r.returncode, r.stdout), (0, b"4\n"))

    def test_hand_runtime_error_and_timeout(self):
        self.write("S.cc", "int main(){return 5;}")
        r = run_cprun(["S.cc", "hand"], self.dir)
        self.assertEqual(r.returncode, 1)
        self.assertIn(b"Exit code: 5", r.stderr)
        self.write("L.cc", "int main(){volatile long x=0;for(;;)x++;}")
        r = run_cprun(["L.cc", "hand", "--timeout=0.5"], self.dir, timeout=30)
        self.assertEqual(r.returncode, 4)

    def test_hand_requires_existing_source(self):
        r = run_cprun(["X.cc", "hand"], self.dir)
        self.assertEqual(r.returncode, 2)
        self.assertFalse((self.dir / "X.cc").exists())

    def test_hand_conflicts(self):
        for args in (["--samples"], ["--watch"], ["--stdin"]):
            self.assertEqual(run_cprun(["A.cc", "hand", *args], self.dir).returncode, 2, args)


@requires_gxx
class StdinModeTest(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.write("D.cc", SUM_PROGRAM)

    def test_stdin_passthrough(self):
        r = run_cprun(["D.cc", "--stdin"], self.dir, stdin=b"5 10\n")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout, b"15\n")
        self.assertFalse((self.dir / "D.in").exists())
        self.assertFalse((self.dir / "D.out").exists())



@requires_gxx
class SamplesModeTest(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.write("D.cc", SUM_PROGRAM)

    def test_all_pass(self):
        self.write("D.samples", "=== TEST 1 ===\nINPUT\n10 20\nOUTPUT\n30\n\n=== TEST 2 ===\nINPUT\n100 200\nOUTPUT\n300\n")
        r = run_cprun(["D.cc", "--samples"], self.dir)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertRegex(r.stdout, rb"\[TEST 1\] PASSED    \d\.\d{3}s")
        self.assertRegex(r.stdout, rb"\[TEST 2\] PASSED    \d\.\d{3}s")
        self.assertIn(b"ALL TESTS PASSED", r.stdout)
        self.assertIn(b"2 / 2 tests passed", r.stdout)
        self.assertFalse((self.dir / "D.out").exists())  # samples mode does not create D.in/D.out

    def test_failure_report(self):
        self.write("D.samples", "INPUT\n1 1\nOUTPUT\n2\nINPUT\n2 2\nOUTPUT\n5\nINPUT\n3 3\nOUTPUT\n6 6\n")
        r = run_cprun(["D.cc", "-s"], self.dir)
        self.assertEqual(r.returncode, 1)
        out = r.stdout.decode()
        self.assertIn("[TEST 2] FAILED", out)
        self.assertIn("Mismatch at token 1 (line 1):\nExpected: 5\nReceived: 4", out)
        self.assertIn("Expected token 2: 6\nReceived: <missing>", out)
        self.assertIn("Passed: 1 / 3", out)
        self.assertIn("Failed: 2 / 3", out)

    def test_extra_tokens_report(self):
        self.write("D.samples", "INPUT\n1 1\nOUTPUT\n\n")
        r = run_cprun(["D.cc", "-s"], self.dir)
        self.assertEqual(r.returncode, 1)
        self.assertIn(b"Extra token at position 1:\n2", r.stdout)

    def test_main_in_out_pair_is_a_sample(self):
        self.write("D.in", "1 2\n")
        self.write("D.out", "3\n")
        r = run_cprun(["D.cc", "--samples"], self.dir)
        self.assertEqual(r.returncode, 0)
        self.assertIn(b"1 / 1 tests passed", r.stdout)

    def test_numbered_pairs(self):
        self.write("D1.in", "1 2\n")
        self.write("D1.out", "3\n")
        self.write("D2.in", "2 2\n")
        self.write("D2.out", "4\n")
        r = run_cprun(["D.cc", "--samples"], self.dir)
        self.assertEqual(r.returncode, 0)
        self.assertIn(b"2 / 2 tests passed", r.stdout)

    def test_runtime_error_and_timeout_in_samples(self):
        self.write("R.cc", "#include <iostream>\nint main(){int n;std::cin>>n;if(n==1)return 3;if(n==2)for(;;);"
                           "std::cout<<n;}")
        self.write("R.samples", "INPUT\n1\nOUTPUT\n1\nINPUT\n2\nOUTPUT\n2\nINPUT\n3\nOUTPUT\n3\n")
        r = run_cprun(["R.cc", "--samples", "--timeout=0.5"], self.dir, timeout=30)
        self.assertEqual(r.returncode, 1)
        self.assertIn(b"[TEST 1] RUNTIME ERROR", r.stdout)
        self.assertIn(b"[TEST 2] TIME LIMIT EXCEEDED", r.stdout)
        self.assertIn(b"[TEST 3] PASSED", r.stdout)

    def test_eps(self):
        self.write("F.cc", '#include <cstdio>\nint main(){printf("%.9f\\n", 1.0/3);}')
        self.write("F.samples", "INPUT\n\nOUTPUT\n0.333333\n")
        self.assertEqual(run_cprun(["F.cc", "-s"], self.dir).returncode, 1)
        self.assertEqual(run_cprun(["F.cc", "-s", "--eps=1e-6"], self.dir).returncode, 0)

    def test_no_samples(self):
        r = run_cprun(["D.cc", "--samples"], self.dir)
        self.assertEqual(r.returncode, 2)
        self.assertIn(b"no sample tests found", r.stderr)
        self.assertIn(b"D.samples", r.stderr)

    def test_cf_falls_back_to_local_samples(self):
        # The contest id cannot be detected, so --cf fails and local samples are used.
        self.write("D.samples", "INPUT\n1 2\nOUTPUT\n3\n")
        r = run_cprun(["D.cc", "--cf"], self.dir)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(b"[WARNING]", r.stderr)
        self.assertIn(b"1 / 1 tests passed", r.stdout)

    def test_cf_cache_is_used_offline(self):
        url = "https://codeforces.com/contest/1846/problem/D"
        (self.dir / ".cprun").mkdir()
        self.write(".cprun/D.cf.samples", f"# source: {url}\n\n=== TEST 1 ===\nINPUT\n4 5\nOUTPUT\n9\n")
        r = run_cprun(["D.cc", "--cf-url", url], self.dir)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(b"Using cached Codeforces samples", r.stderr)

    def test_invalid_cf_url(self):
        r = run_cprun(["D.cc", "--cf-url", "https://example.com/x"], self.dir)
        self.assertEqual(r.returncode, 2)
        self.assertIn(b"not a Codeforces problem URL", r.stderr)


if __name__ == "__main__":
    unittest.main()
