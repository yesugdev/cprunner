import time
import unittest

from tests.helpers import TempDirTestCase, requires_gxx

from cprun import runner
from cprun.runner import SIGNAL_HINTS, RunResult, run_program


@requires_gxx
class RunProgramTest(TempDirTestCase):
    def test_captures_stdout_and_stderr_separately(self):
        exe = self.compile("p.cc", '#include <cstdio>\nint main(){puts("out");fputs("err\\n",stderr);}')
        r = run_program(exe, timeout=5)
        self.assertTrue(r.ok)
        self.assertEqual(r.stdout, b"out\n")
        self.assertEqual(r.stderr, b"err\n")
        self.assertEqual(r.returncode, 0)
        self.assertGreater(r.elapsed, 0)

    def test_stdin_from_file(self):
        exe = self.compile("sum.cc", "#include <iostream>\nint main(){long a,b;std::cin>>a>>b;std::cout<<a+b;}")
        inp = self.write("sum.in", "10 20\n")
        self.assertEqual(run_program(exe, stdin_path=inp, timeout=5).stdout, b"30")

    def test_large_stdin_and_stdout_through_pipes(self):
        exe = self.compile("cat.cc", "#include <cstdio>\nint main(){int c;while((c=getchar())!=EOF)putchar(c);}")
        data = b"0123456789abcdef\n" * 200000  # 3.4 MB, larger than pipe buffers
        r = run_program(exe, stdin_data=data, timeout=10)
        self.assertTrue(r.ok)
        self.assertEqual(r.stdout, data)

    def test_no_stdin_reads_eof(self):
        exe = self.compile("e.cc", '#include <cstdio>\nint main(){int x; puts(scanf("%d",&x)==EOF?"eof":"data");}')
        self.assertEqual(run_program(exe, timeout=5).stdout, b"eof\n")

    def test_timeout_kills_program(self):
        exe = self.compile("loop.cc", "int main(){volatile long x=0;for(;;)x++;}")
        start = time.perf_counter()
        r = run_program(exe, timeout=0.3)
        self.assertLess(time.perf_counter() - start, 3)
        self.assertTrue(r.timed_out)
        self.assertFalse(r.ok)

    def test_timeout_when_program_closes_output_but_keeps_running(self):
        exe = self.compile("c.cc", "#include <unistd.h>\nint main(){close(1);close(2);volatile long x=0;for(;;)x++;}")
        r = run_program(exe, timeout=0.3)
        self.assertTrue(r.timed_out)

    def test_runtime_error_signal(self):
        exe = self.compile("seg.cc", "int main(){volatile int*p=nullptr;*p=1;}")
        r = run_program(exe, timeout=5)
        self.assertTrue(r.runtime_error)
        self.assertEqual(r.signal_name, "SIGSEGV")
        self.assertEqual(r.exit_status, 139)

    def test_abort_signal(self):
        exe = self.compile("ab.cc", "#include <cassert>\nint main(){assert(1==2);}")
        r = run_program(exe, timeout=5)
        self.assertEqual(r.signal_name, "SIGABRT")
        self.assertIn(b"Assertion", r.stderr)

    def test_nonzero_exit_code(self):
        exe = self.compile("x.cc", "int main(){return 3;}")
        r = run_program(exe, timeout=5)
        self.assertTrue(r.runtime_error)
        self.assertEqual(r.exit_status, 3)
        self.assertIsNone(r.signal_name)

    def test_output_limit(self):
        exe = self.compile("spam.cc", "#include <cstdio>\nint main(){for(;;)puts(\"spam spam spam\");}")
        r = run_program(exe, timeout=5, output_limit=1 << 20)
        self.assertTrue(r.output_limit_exceeded)
        self.assertFalse(r.ok)



@requires_gxx
class ThreadedRunProgramTest(RunProgramTest):
    """The same tests through the thread-based runner that Windows uses."""

    def setUp(self):
        super().setUp()
        self._old = runner.USE_THREADS
        runner.USE_THREADS = True

    def tearDown(self):
        runner.USE_THREADS = self._old
        super().tearDown()


class WindowsExitCodeTest(unittest.TestCase):
    def test_access_violation(self):
        for code in (0xC0000005, -1073741819):  # unsigned and signed forms
            r = RunResult(b"", b"", code, 0.1)
            self.assertTrue(r.runtime_error)
            self.assertEqual(r.signal_name, "ACCESS_VIOLATION")
            self.assertEqual(r.exit_status_text, "3221225477 (0xC0000005)")
            self.assertIn("ACCESS_VIOLATION", SIGNAL_HINTS)

    def test_stack_overflow_and_unknown_status(self):
        self.assertEqual(RunResult(b"", b"", 0xC00000FD, 0).signal_name, "STACK_OVERFLOW")
        self.assertEqual(RunResult(b"", b"", 0xC0001234, 0).signal_name, "0xC0001234")

    def test_posix_signals_are_not_windows_statuses(self):
        r = RunResult(b"", b"", -11, 0)
        self.assertIsNone(r.windows_status)
        self.assertEqual(r.signal_name, "SIGSEGV")
        self.assertEqual(r.exit_status_text, "139")

    def test_ordinary_exit_codes_are_not_windows_statuses(self):
        r = RunResult(b"", b"", 3, 0)
        self.assertIsNone(r.windows_status)
        self.assertIsNone(r.signal_name)
        self.assertEqual(r.exit_status_text, "3")


if __name__ == "__main__":
    unittest.main()
