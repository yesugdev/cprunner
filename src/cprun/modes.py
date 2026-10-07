"""The run modes: normal (D.in -> D.out), samples, stdin, and watch."""

from __future__ import annotations

import re
import shlex
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from . import codeforces
from .compare import compare
from .compiler import BuildSettings, Builder, ensure_build_dir
from .config import Config
from .errors import CprunError, ExitCode, ExitRequest
from .interactive import read_user_input, save_file
from .paths import ProblemPaths
from .runner import IS_WINDOWS, SIGNAL_HINTS, RunResult, run_program
from .samples import NO_SAMPLES_HELP, Sample, discover_local_samples, format_samples, read_sample_file
from .term import Console, format_time, truncate_lines

DETAIL_LINES = 30  # lines shown per Expected/Received block in sample mode
TOKEN_WIDTH = 80


@dataclass
class Context:
    console: Console
    paths: ProblemPaths
    config: Config
    settings: BuildSettings
    timeout: float
    eps: Optional[float] = None
    cf: bool = False
    cf_url: Optional[str] = None
    cf_refresh: bool = False

    @property
    def output_limit(self) -> int:
        return self.config.output_limit_mb << 20

    def run(self, executable: Path, **kwargs) -> RunResult:
        return run_program(executable, timeout=self.timeout, cwd=self.paths.directory,
                           output_limit=self.output_limit, **kwargs)


# -- compilation ---------------------------------------------------------------

def ensure_compiled(ctx: Context) -> Path:
    c, p, s = ctx.console, ctx.paths, ctx.settings
    builder = Builder(p, s)
    if s.debug:
        c.info(c.style("DEBUG MODE", "magenta", "bold"))
    if builder.is_up_to_date():
        c.info(f"{p.name} unchanged.")
        c.info("Using cached executable.")
        return builder.executable

    c.info(f"Compiling {p.name} with {s.standard_label}...")
    c.verbose("Command: " + " ".join(shlex.quote(x) for x in builder.display_command()))
    result = builder.build(color=c.color_err)
    if not result.ok:
        c.alert("Compilation failed.")
        c.line()
        diagnostics = result.diagnostics.rstrip("\n")
        c.line(diagnostics if diagnostics else "(the compiler produced no error message)")
        raise ExitRequest(ExitCode.COMPILE)
    c.success("Compilation successful.")
    c.verbose(f"Compile time: {format_time(result.elapsed)}")
    if result.diagnostics.strip() and not c.quiet:
        c.warning("Compiler warnings:")
        c.line(result.diagnostics.rstrip("\n"))
    return builder.executable


# -- shared reporting ----------------------------------------------------------

def failure_description(result: RunResult, ctx: Context) -> Optional[Tuple[str, List[str], int]]:
    """``(title, detail_lines, exit_code)`` for a failed run, or None if it succeeded."""
    if result.timed_out:
        return "TIME LIMIT EXCEEDED", [f"Limit: {ctx.timeout:.2f} seconds"], ExitCode.TIMEOUT
    if result.output_limit_exceeded:
        return ("OUTPUT LIMIT EXCEEDED",
                [f"The program wrote more than {ctx.config.output_limit_mb} MB. Check for an infinite loop."],
                ExitCode.FAILURE)
    if result.runtime_error:
        lines = [f"Exit code: {result.exit_status_text}"]
        name = result.signal_name
        if name:
            hint = SIGNAL_HINTS.get(name)
            label = "Exception" if result.windows_status is not None else "Signal"
            lines.append(f"{label}: {name}" + (f" ({hint})" if hint else ""))
        elif IS_WINDOWS and result.returncode == 3:
            lines.append("(on Windows, exit code 3 usually means abort(): a failed assert or uncaught exception)")
        return "RUNTIME ERROR", lines, ExitCode.FAILURE
    return None


def _decode(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


def show_program_output(ctx: Context, data: bytes, full_output_hint: str) -> None:
    c = ctx.console
    if not data:
        c.line(c.style("(no output)", "dim"))
        return
    limit = ctx.config.display_lines if c.out_is_tty else 0
    if limit:
        lines = data.split(b"\n")
        if lines[-1] == b"":
            lines.pop()
        if len(lines) > limit:
            c.write_bytes(b"\n".join(lines[:limit]) + b"\n")
            c.line(c.style(f"... {len(lines) - limit} more lines not shown ({full_output_hint})", "dim"))
            return
    c.write_bytes(data)
    if c.out_is_tty and not data.endswith(b"\n"):
        c.write_bytes(b"\n")


def report_run(ctx: Context, result: RunResult, expected: Optional[bytes] = None,
               expected_name: str = "", save_actual: bool = False) -> int:
    """Show the run result. When ``expected`` is given (non-blank), compare the
    program's stdout with it and print ACCEPTED or WRONG ANSWER."""
    c, p = ctx.console, ctx.paths
    failure = failure_description(result, ctx)

    actual_path = p.build_dir / f"{p.stem}.actual"
    if save_actual:
        try:
            ensure_build_dir(p.build_dir)
            save_file(actual_path, result.stdout, p.display(actual_path))
        except CprunError:
            save_actual = False

    c.blank()
    c.heading("Output:")
    hint = f"see {p.display(actual_path)} for the full output" if save_actual else "output truncated"
    show_program_output(ctx, result.stdout, hint)

    if result.stderr:
        c.line()
        c.line(c.style("stderr:", "yellow", "bold"))
        text, hidden = truncate_lines(_decode(result.stderr), ctx.config.display_lines)
        c.line(text)
        if hidden:
            c.line(c.style(f"... {hidden} more lines of stderr not shown", "dim"))

    code = ExitCode.OK
    if failure:
        title, lines, code = failure
        c.line()
        c.alert(title)
        c.line()
        for ln in lines:
            c.line(ln)
    elif expected is not None and expected.strip():
        cmp = compare(expected, result.stdout, ctx.eps)
        c.line()
        if cmp.ok:
            c.line(f"{c.tag()} {c.style('ACCEPTED', 'green', 'bold')}  output matches {expected_name}")
        else:
            code = ExitCode.FAILURE
            c.line(f"{c.tag()} {c.style('WRONG ANSWER', 'red', 'bold')}  output differs from {expected_name}")
            _report_mismatch(c, expected, result.stdout, cmp, stream="err")
    elif expected is not None:
        c.line()
        c.warning(f"{expected_name} is empty: there is no expected output to compare with.")
        c.line(f"Write the correct answer in {expected_name} and run again to check your solution.")

    c.blank()
    if save_actual:
        c.verbose(f"Program output saved to {p.display(actual_path)}")
    timing = f"Time: {format_time(result.elapsed)}"
    if result.timed_out:
        timing = f"Time: >{format_time(ctx.timeout)}"
    c.info(timing)
    return code


# -- normal mode: D.in -> program -> compare with D.out ------------------------

def _read_bytes(path: Path, display: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as e:
        raise CprunError(f"cannot read {display}.", f"Reason: {e.strerror}", code=ExitCode.SYSTEM)


def run_normal(ctx: Context, force_input: bool = False, require_input: bool = False) -> int:
    c, p = ctx.console, ctx.paths
    in_name, out_name = p.display(p.input), p.display(p.output)

    if force_input:
        c.info("Direct input mode")
        c.blank()
        data = read_user_input(c)
        save_file(p.input, data, in_name)
        _warn_if_empty(c, data, in_name)
        c.info(f"Input saved to {in_name}")

    if require_input and not p.input.exists():
        raise CprunError(
            f"{in_name} does not exist.",
            f"Use:\n\n    cprun {p.display(p.source)}\n\nto create {in_name} and {out_name}.",
            code=ExitCode.USAGE,
        )

    created = ensure_io_files(p)

    if in_name in created:
        c.info(f"Created {' and '.join(created)}.")
        c.blank()
        c.line(f"Write the input data in      {in_name}")
        c.line(f"Write the expected output in {out_name}")
        c.line()
        c.line("Then run again to check your solution:")
        c.line()
        c.line(f"    cprun {p.display(p.source)}")
        return ExitCode.USAGE
    if created:
        c.info(f"Created {out_name}.")

    input_data = _read_bytes(p.input, in_name)
    expected = _read_bytes(p.output, out_name)
    c.info(f"Input: {in_name}   Expected output: {out_name}")
    _warn_if_empty(c, input_data, in_name)

    exe = ensure_compiled(ctx)
    c.blank()
    c.info(f"Running {p.name}...")
    result = ctx.run(exe, stdin_path=p.input)
    return report_run(ctx, result, expected, out_name, save_actual=True)


def _warn_if_empty(c: Console, data: bytes, name: str) -> None:
    if not data.strip():
        c.warning(f"{name} is empty.")


# -- creating a new source file from the template --------------------------------

DEFAULT_TEMPLATE = """#include <bits/stdc++.h>
using namespace std;

int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    return 0;
}
"""


def default_template_path() -> Path:
    from .config import global_config_path

    return global_config_path().parent / "template.cpp"


def create_source(console: Console, paths: ProblemPaths, template: Optional[str]) -> None:
    """Create a missing source file from the user's template (or the built-in one)."""
    candidate = Path(template) if template else default_template_path()
    if template or candidate.is_file():
        try:
            data = candidate.read_bytes()
        except OSError as e:
            raise CprunError(f"cannot read template {candidate}.", f"Reason: {e.strerror}",
                             "Fix the 'template' setting in your configuration.", code=ExitCode.SYSTEM)
        origin = f"template {candidate}"
    else:
        data, origin = DEFAULT_TEMPLATE.encode(), "the default template"
    save_file(paths.source, data, paths.display(paths.source))
    console.info(f"Created {paths.display(paths.source)} from {origin}")


def ensure_io_files(paths: ProblemPaths) -> List[str]:
    """Create empty D.in / D.out if missing. Returns the names of created files."""
    created = []
    for path in (paths.input, paths.output):
        name = paths.display(path)
        if not path.exists():
            save_file(path, b"", name)
            created.append(name)
        elif not path.is_file():
            raise CprunError(f"{name} exists but is not a regular file.", code=ExitCode.USAGE)
    return created


def start_new_problem(console: Console, paths: ProblemPaths, template: Optional[str]) -> int:
    """``cprun A.cc`` for a file that doesn't exist yet: create A.cc, A.in, A.out."""
    from .samples import has_multiple_tests

    p = paths
    create_source(console, p, template)
    with_io = not has_multiple_tests(p)
    if with_io:
        created = ensure_io_files(p)
        if created:
            console.info(f"Created {' and '.join(created)}")
    console.blank()
    console.line(f"Write your solution in       {p.display(p.source)}")
    if with_io:
        console.line(f"Write the input data in      {p.display(p.input)}")
        console.line(f"Write the expected output in {p.display(p.output)}")
    console.line()
    console.line("Then check it with:")
    console.line()
    console.line(f"    cprun {p.display(p.source)}")
    return ExitCode.OK


# -- creating numbered test files: cprun D.cc samples 3 ---------------------------

MAX_CREATE = 1000


def create_test_files(console: Console, paths: ProblemPaths, count: int) -> int:
    c, p = console, paths
    if not 1 <= count <= MAX_CREATE:
        raise CprunError(f"invalid number of tests: {count}", f"Use a number from 1 to {MAX_CREATE}.",
                         code=ExitCode.USAGE)
    folder = p.tests_dir
    folder_name = p.display(folder)
    try:
        folder.mkdir(exist_ok=True)
    except OSError as e:
        raise CprunError(f"cannot create folder {folder_name}.", f"Reason: {e.strerror}",
                         "Check that you have write permission in this directory.", code=ExitCode.SYSTEM)
    if not folder.is_dir():
        raise CprunError(f"{folder_name} exists but is not a folder.", code=ExitCode.USAGE)
    created, kept = [], []
    for i in range(1, count + 1):
        for ext in (".in", ".out"):
            path = folder / f"{i}{ext}"
            if path.exists():
                kept.append(path.name)
            else:
                save_file(path, b"", p.display(path))
                created.append(path.name)
    if created:
        c.info(f"Created {len(created)} file(s) in {folder_name}/: {' '.join(created)}")
    if kept:
        c.info(f"Kept existing file(s) in {folder_name}/: {' '.join(kept)}")
    c.blank()
    if count == 1:
        c.line(f"Write the input data in {folder_name}/1.in and the expected output in {folder_name}/1.out.")
    else:
        c.line(f"Write the input data in      {folder_name}/1.in ... {folder_name}/{count}.in")
        c.line(f"Write the expected output in {folder_name}/1.out ... {folder_name}/{count}.out")
    c.line()
    c.line("Then check all tests with:")
    c.line()
    c.line(f"    cprun {p.display(p.source)}")
    return ExitCode.OK


# -- hand mode: compile and run attached to the terminal -------------------------

def run_hand(ctx: Context, timeout: Optional[float] = None) -> int:
    """Run the program with the terminal as its stdin/stdout: type input by hand
    and see the output immediately. No files are read or written."""
    import subprocess

    c, p = ctx.console, ctx.paths
    # Start the program silently, like ./a.out; compile errors are still shown.
    was_quiet = c.quiet
    c.configure(quiet=True)
    try:
        exe = ensure_compiled(ctx)
    finally:
        c.configure(quiet=was_quiet)

    start = time.perf_counter()
    try:
        proc = subprocess.Popen([str(exe)], cwd=str(p.directory))
    except OSError as e:
        raise CprunError(f"cannot execute {exe}.", f"Reason: {e.strerror}", code=ExitCode.SYSTEM)
    interrupted = timed_out = False
    while True:
        try:
            if timeout is None:
                proc.wait()
            else:
                remaining = timeout - (time.perf_counter() - start)
                proc.wait(max(remaining, 0))
            break
        except KeyboardInterrupt:
            interrupted = True  # the program receives Ctrl+C too; wait for it to exit
        except subprocess.TimeoutExpired:
            timed_out = True
            proc.kill()
            proc.wait()
            break
    elapsed = time.perf_counter() - start

    c.line()
    if interrupted and proc.returncode not in (None, 0):
        c.info("Program stopped with Ctrl+C.")
        return ExitCode.INTERRUPTED
    result = RunResult(b"", b"", proc.returncode, elapsed, timed_out=timed_out)
    failure = failure_description(result, ctx) if timed_out or result.runtime_error else None
    if failure:
        title, lines, code = failure
        c.alert(title)
        c.line()
        for ln in lines:
            c.line(ln)
        c.blank()
    else:
        code = ExitCode.OK
        c.success("Program finished.")
    c.info(f"Time: {format_time(elapsed)} (including the time spent typing)")
    return code


# -- stdin mode ----------------------------------------------------------------

def run_stdin(ctx: Context) -> int:
    c, p = ctx.console, ctx.paths
    exe = ensure_compiled(ctx)
    c.blank()
    data = read_user_input(c)
    c.info(f"Running {p.name}...")
    result = ctx.run(exe, stdin_data=data)
    return report_run(ctx, result)


# -- samples mode --------------------------------------------------------------

def _load_codeforces_samples(ctx: Context) -> List[Sample]:
    c, p = ctx.console, ctx.paths
    if ctx.cf_url:
        url, how = codeforces.validate_url(ctx.cf_url), "from --cf-url"
    else:
        url, how = codeforces.detect_url(p, ctx.config.cf_contest)
    cache = codeforces.cache_path(p)
    marker = f"# source: {url}"
    if cache.is_file() and not ctx.cf_refresh:
        try:
            first_line = cache.read_text(errors="replace").split("\n", 1)[0]
        except OSError:
            first_line = ""
        if first_line == marker:
            samples = read_sample_file(cache, p.display(cache))
            if samples:
                c.info(f"Using cached Codeforces samples for {url}")
                c.verbose(f"Cache: {p.display(cache)} (use --cf-refresh to download again)")
                return samples

    c.info(f"Downloading samples from {url}")
    c.verbose(f"Problem URL detected {how}")
    samples = codeforces.fetch_samples(url)
    c.info(f"Downloaded {len(samples)} sample test(s).")
    try:
        ensure_build_dir(p.build_dir)
        cache.write_text(format_samples(samples, comment=f"source: {url}"))
    except (OSError, CprunError):
        c.warning("could not cache the downloaded samples.")
    return samples


def collect_samples(ctx: Context) -> List[Sample]:
    c, p = ctx.console, ctx.paths
    if ctx.cf or ctx.cf_url or ctx.cf_refresh:
        try:
            return _load_codeforces_samples(ctx)
        except CprunError as e:
            local, origins = discover_local_samples(p)
            if not local:
                raise
            c.warning(e.message)
            for block in e.blocks:
                c.line(block)
            c.warning(f"Falling back to local samples: {', '.join(origins)}")
            return local

    local, origins = discover_local_samples(p)
    if not local:
        raise CprunError(
            f"no sample tests found for {p.name}.",
            NO_SAMPLES_HELP.format(name=p.display(p.source), stem=p.stem),
            code=ExitCode.USAGE,
        )
    c.info(f"Found {len(local)} test(s) in {', '.join(origins)}")
    return local


def _short_token(token: bytes) -> str:
    text = _decode(token)
    return text if len(text) <= TOKEN_WIDTH else text[:TOKEN_WIDTH] + "..."


def _block(c: Console, title: str, data: bytes, stream: str = "out") -> None:
    c.line(c.style(title, "bold", stream=stream), stream)
    if not data.strip():
        c.line(c.style("<empty>", "dim", stream=stream), stream)
        return
    text, hidden = truncate_lines(_decode(data).replace("\r", ""), DETAIL_LINES, 200)
    c.line(text, stream)
    if hidden:
        c.line(c.style(f"... {hidden} more lines", "dim", stream=stream), stream)


def _report_mismatch(c: Console, expected: bytes, received: bytes, cmp, stream: str = "out") -> None:
    out = stream
    c.line("", out)
    if cmp.kind == "mismatch":
        c.line(f"Mismatch at token {cmp.position} (line {cmp.received.line}):", out)
        c.line(f"Expected: {c.style(_short_token(cmp.expected.text), 'green', stream=out)}", out)
        c.line(f"Received: {c.style(_short_token(cmp.received.text), 'red', stream=out)}", out)
    elif cmp.kind == "missing":
        c.line(f"Expected token {cmp.position}: {c.style(_short_token(cmp.expected.text), 'green', stream=out)}", out)
        c.line(f"Received: {c.style('<missing>', 'red', stream=out)}", out)
        c.line("", out)
        c.line(f"Expected: {cmp.expected_count} tokens", out)
        c.line(f"Received: {cmp.received_count} tokens", out)
    else:
        c.line(f"Expected: {cmp.expected_count} tokens", out)
        c.line(f"Received: {cmp.received_count} tokens", out)
        c.line("", out)
        c.line(f"Extra token at position {cmp.position}:", out)
        c.line(c.style(_short_token(cmp.received.text), "red", stream=out), out)
    c.line("", out)
    _block(c, "Expected:", expected, out)
    c.line("", out)
    _block(c, "Received:", received, out)


def run_samples(ctx: Context) -> int:
    c = ctx.console
    out = "out"
    samples = collect_samples(ctx)
    empty = [s for s in samples if s.empty]
    samples = [s for s in samples if not s.empty]
    if empty:
        names = ", ".join(s.origin for s in empty)
        c.warning(f"Skipping {len(empty)} empty test(s): {names}")
    if not samples:
        raise CprunError(
            "all tests are empty.",
            f"Write the input in {ctx.paths.tests_dir.name}/1.in, 2.in, ... and the expected output in "
            f"{ctx.paths.tests_dir.name}/1.out, 2.out, ..., then run again.",
            code=ExitCode.USAGE,
        )
    exe = ensure_compiled(ctx)
    if not c.quiet:
        c.line("", out)

    passed = failed = unchecked = 0
    total_time = 0.0
    last_had_details = False
    for i, sample in enumerate(samples, 1):
        result = ctx.run(exe, stdin_data=sample.input)
        total_time += result.elapsed
        failure = failure_description(result, ctx)
        cmp = None
        if failure:
            status, color = failure[0], "red"
        elif sample.expected is None:
            status, color = "NOT CHECKED", "yellow"
        else:
            cmp = compare(sample.expected, result.stdout, ctx.eps)
            status, color = ("PASSED", "green") if cmp.ok else ("FAILED", "red")

        elapsed = f">{format_time(ctx.timeout)}" if result.timed_out else format_time(result.elapsed)
        label = c.style(f"[TEST {i}]", "bold", stream=out)
        origin = c.style(sample.origin, "dim", stream=out)
        c.line(f"{label} {c.style(f'{status:<9}', color, stream=out)} {elapsed:<8} {origin}", out)

        if failure:
            failed += 1
            c.line("", out)
            for ln in failure[1]:
                c.line(ln, out)
        elif cmp is None:
            unchecked += 1
            c.line("", out)
            _block(c, "Received:", result.stdout)
        elif cmp.ok:
            passed += 1
        else:
            failed += 1
            _report_mismatch(c, sample.expected, result.stdout, cmp)

        show_input = c.verbose_enabled and (failure or (cmp is not None and not cmp.ok))
        if show_input:
            c.line("", out)
            _block(c, "Input:", sample.input)
        if result.stderr and (failure or c.verbose_enabled or (cmp is not None and not cmp.ok)):
            c.line("", out)
            c.line(c.style("stderr:", "yellow", "bold", stream=out), out)
            text, hidden = truncate_lines(_decode(result.stderr), DETAIL_LINES, 200)
            c.line(text, out)
        last_had_details = bool(failure or cmp is None or not cmp.ok)
        if last_had_details:
            c.line("", out)

    total = len(samples)
    checked = total - unchecked
    if failed == 0:
        bar = "=" * 32
        c.line("", out)
        c.line(c.style(bar, "green", stream=out), out)
        c.line(c.style("ALL TESTS PASSED", "green", "bold", stream=out), out)
        c.line(c.style(bar, "green", stream=out), out)
        c.line("", out)
        c.line(f"{passed} / {checked} tests passed", out)
        if unchecked:
            c.line(f"{unchecked} test(s) not checked (no expected output)", out)
        c.line(f"Total time: {format_time(total_time)}", out)
        return ExitCode.OK

    bar = "-" * 32
    if not last_had_details:
        c.line("", out)
    c.line(bar, out)
    c.line(c.style("CPRUN RESULT", "bold", stream=out), out)
    c.line(bar, out)
    c.line("", out)
    c.line(c.style(f"Passed: {passed} / {total}", "green", stream=out), out)
    c.line(c.style(f"Failed: {failed} / {total}", "red", stream=out), out)
    if unchecked:
        c.line(f"Not checked: {unchecked} / {total}", out)
    c.line(f"Time: {format_time(total_time)}", out)
    c.line(bar, out)
    return ExitCode.FAILURE


# -- watch mode ----------------------------------------------------------------

_SAMPLE_SUFFIXES = (".samples", ".sample", ".in", ".out", ".ans", ".txt")
_NESTED_SAMPLE_RE = re.compile(r"^\d+\.(in|out|ans)$")  # samples/D/1.in


def run_watch(ctx: Context, samples_mode: bool, force_input: bool = False) -> int:
    from .watch import watch_loop

    c, p = ctx.console, ctx.paths

    def relevant(name: str) -> bool:
        if name == p.name:
            return True
        if samples_mode:
            if name == p.stem or _NESTED_SAMPLE_RE.match(name):
                return True
            return name.startswith(p.stem) and name.endswith(_SAMPLE_SUFFIXES)
        return name in (p.input.name, p.output.name)

    def run_once(first: bool) -> None:
        try:
            if samples_mode:
                run_samples(ctx)
            else:
                run_normal(ctx, force_input=first and force_input, require_input=not first)
        except ExitRequest:
            pass
        except CprunError as e:
            if e.code == ExitCode.INTERRUPTED:
                raise KeyboardInterrupt
            c.show_error(e.message, e.blocks)

    def waiting() -> None:
        c.line()
        c.info(f"Watching {p.name}... (press Ctrl+C to stop)")

    def on_change(changed: List[str]) -> None:
        c.line()
        c.line(c.style("-" * 32 + time.strftime(" %H:%M:%S"), "dim"))
        for path in changed:
            name = Path(path).name
            verb = "modified" if Path(path).exists() else "removed"
            c.line(f"{c.style('[CHANGE]', 'yellow', 'bold')} {name} {verb}.")
        if not p.source.exists():
            c.warning(f"{p.name} is missing; waiting for it to be saved again.")
            waiting()
            return
        c.line()
        run_once(False)
        waiting()

    dirs = [p.directory]
    if samples_mode and p.tests_dir.is_dir():
        dirs.append(p.tests_dir)
    sample_dir = p.directory / "samples"
    if samples_mode and sample_dir.is_dir():
        dirs.append(sample_dir)
        nested = sample_dir / p.stem
        if nested.is_dir():
            dirs.append(nested)

    try:
        run_once(True)
        waiting()
        watch_loop(dirs, relevant, on_change)
    except KeyboardInterrupt:
        c.line()
        c.info("Stopped watching.")
    return ExitCode.OK
