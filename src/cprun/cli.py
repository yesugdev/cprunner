"""Command-line interface."""

from __future__ import annotations

import argparse
import math
import os
import sys
from typing import List, Optional

from . import __version__
from .compiler import VALID_STANDARDS_TEXT, make_build_settings, normalize_standard
from .config import load_config
from .errors import CprunError, ExitCode, ExitRequest, UsageError
from .paths import resolve_source
from .term import Console

USAGE = """Usage:
    cprun <source>

Examples:
    cprun D.cc
    cprun D.cpp
    cprun D.cc samples 3
    cprun D.cc hand
    cprun D.cc --samples
    cprun D.cc --input

Run 'cprun --help' for all options.
"""

HELP = f"""cprun {__version__} - local runner for competitive programming

Usage:
    cprun <source> [options]

Modes:
    cprun D.cc              Compile, run with D.in and compare the output with
                            D.out (the expected answer): ACCEPTED / WRONG ANSWER.
                            Creates empty D.in and D.out on the first run.
                            If D_tests/ (or D.samples, D1.in/D1.out, ...)
                            exists, checks all tests instead.
    cprun D.cc samples N    Create empty tests D_tests/1.in 1.out ... N.in N.out.
                            A missing D.cc is created from the template
                            (~/.config/cprun/template.cpp or a built-in one).
    cprun D.cc hand         Compile and run in the terminal: type the input by
                            hand and see the output directly (no files, no
                            time limit unless --timeout is given).
    -i, --input             Type new input (replaces D.in), then run.
    -s, --samples           Check all tests (D.in/D.out, D_tests/, D.samples, ...).
        --stdin             Pass cprun's own stdin to the program (for pipelines).
    -w, --watch             Re-run whenever D.cc (or D.in / sample files) change.

Options:
        --std=STD           C++ standard: c++11 c++14 c++17 c++20 c++23 gnu++17 ...
                            (default: c++17)
        --timeout=SEC       Time limit per run in seconds (default: 2).
    -d, --debug             Debug build: -g -O0 -Wall -Wextra.
        --eps=EPS           Accept numbers within absolute/relative error EPS
                            when comparing sample output.
        --cf                Download samples from Codeforces (implies --samples).
        --cf-url=URL        Codeforces problem URL to download samples from.
        --cf-refresh        Download Codeforces samples again (ignore the cache).
    -h, --help              Show this help.
    -V, --version           Show the version.
        --uninstall         Remove cprun (installed by install.sh).

Files for D.cc (all in the same directory):
    D.in                    Input data (you write it).
    D.out                   Expected output (you write it); never overwritten.
    D_tests/                Numbered tests: 1.in + 1.out, 2.in + 2.out, ...
    D.samples               Sample tests (also D.sample, samples/D, samples/D.txt,
                            D1.in + D1.out, D2.in + D2.out, ...).
    .cprun/                 Compiled executables, cache, and D.actual (your
                            program's last output). Safe to delete.

Exit codes:
    0 success                       3 compilation error
    1 runtime error / wrong answer  4 time limit exceeded
    2 invalid usage                 5 configuration or system error

Configuration: ~/.config/cprun/config.toml and cprun.toml in the contest
directory. See the README for all settings.
"""


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise UsageError(f"invalid arguments: {message}.", "Run 'cprun --help' for usage.")


def build_parser() -> argparse.ArgumentParser:
    p = _Parser(prog="cprun", add_help=False, allow_abbrev=False)
    p.add_argument("source", nargs="?")
    p.add_argument("command", nargs="*")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("-i", "--input", action="store_true")
    mode.add_argument("-s", "--samples", action="store_true")
    mode.add_argument("--stdin", action="store_true")
    p.add_argument("-w", "--watch", action="store_true")
    p.add_argument("-d", "--debug", action="store_true")
    p.add_argument("--std", metavar="STD")
    p.add_argument("--timeout", metavar="SEC")
    p.add_argument("--eps", metavar="EPS")
    p.add_argument("--cf", action="store_true")
    p.add_argument("--cf-url", metavar="URL")
    p.add_argument("--cf-refresh", action="store_true")
    p.add_argument("-h", "--help", action="store_true")
    p.add_argument("-V", "--version", action="store_true")
    p.add_argument("--uninstall", action="store_true")
    return p


def parse_args(argv: Optional[List[str]]):
    # Intermixed parsing allows `cprun D.cc --debug samples 3`.
    return build_parser().parse_intermixed_args(argv)


CREATE_WORDS = ("samples", "sample", "tests", "test")


HAND_WORDS = ("hand",)


def parse_create_command(args) -> Optional[int]:
    """``cprun D.cc samples 3`` (or ``cprun D.cc --samples 3``) -> 3."""
    words = list(args.command)
    if not words or is_hand_command(args):
        return None
    if len(words) == 2 and words[0].lower() in CREATE_WORDS:
        number = words[1]
    elif len(words) == 1 and args.samples:
        number = words[0]
    else:
        raise UsageError(f"unexpected argument: {' '.join(words)}",
                         "Commands:\n\n    cprun D.cc samples 3    create test files\n"
                         "    cprun D.cc hand         compile and run, typing the input by hand",
                         "Run 'cprun --help' for usage.")
    if not number.isdigit() or int(number) < 1:
        raise UsageError(f"invalid number of tests: {number}", "Example:\n\n    cprun D.cc samples 3")
    return int(number)


def is_hand_command(args) -> bool:
    words = [w.lower() for w in args.command]
    return len(words) == 1 and words[0] in HAND_WORDS


def parse_timeout(value: str) -> float:
    v = value.strip().lower()
    scale = 1.0
    if v.endswith("ms"):
        v, scale = v[:-2], 0.001
    elif v.endswith("s"):
        v = v[:-1]
    try:
        seconds = float(v) * scale
    except ValueError:
        seconds = -1.0
    if not math.isfinite(seconds) or seconds <= 0:
        raise UsageError(f"invalid timeout: {value}", "Use a positive number of seconds, e.g. --timeout=5")
    return seconds


def parse_eps(value: str) -> float:
    try:
        eps = float(value)
    except ValueError:
        eps = -1.0
    if not math.isfinite(eps) or eps <= 0:
        raise UsageError(f"invalid --eps value: {value}", "Use a small positive number, e.g. --eps=1e-6")
    return eps


def _validate_combinations(args) -> None:
    cf_requested = args.cf or args.cf_url or args.cf_refresh
    if cf_requested and (args.input or args.stdin):
        raise UsageError("--cf, --cf-url and --cf-refresh can only be used with --samples.")
    if args.watch and args.stdin:
        raise UsageError("--watch cannot be used with --stdin.", "Watch mode reads its input from the .in file.")


def run(argv: Optional[List[str]], console: Console) -> int:
    from .modes import (Context, create_source, create_test_files, run_hand, run_normal, run_samples, run_stdin,
                        run_watch, start_new_problem)
    from .samples import has_multiple_tests
    from .runner import disable_core_dumps, disable_crash_dialogs, raise_stack_limit

    args = parse_args(argv)
    if args.help:
        console.write(HELP, "out")
        return ExitCode.OK
    if args.version:
        console.line(f"cprun {__version__}", "out")
        return ExitCode.OK
    if args.uninstall:
        from .install_info import uninstall

        return uninstall(console)
    if not args.source:
        console.write(USAGE)
        return ExitCode.USAGE

    hand = is_hand_command(args)
    if hand and (args.input or args.samples or args.stdin or args.watch
                 or args.cf or args.cf_url or args.cf_refresh):
        raise UsageError("'hand' runs the program in the terminal and cannot be combined with other modes.")
    create_count = parse_create_command(args)
    _validate_combinations(args)
    if create_count is not None and (args.input or args.stdin or args.watch or args.cf or args.cf_url):
        raise UsageError("'samples N' only creates test files and cannot be combined with other modes.")
    # A missing source is created from the template for `cprun A.cc`,
    # `cprun A.cc samples N` and `cprun A.cc --watch`; other modes need an existing file.
    can_create = not (hand or args.input or args.stdin or args.cf or args.cf_url or args.cf_refresh
                      or (args.samples and create_count is None))
    paths = resolve_source(args.source, must_exist=not can_create)
    config = load_config(paths.directory)
    console.configure(color=config.color)
    for warning in config.warnings:
        console.warning(warning)

    if not paths.source.exists():
        if create_count is not None:
            create_source(console, paths, config.template)
            return create_test_files(console, paths, create_count)
        if not args.watch:
            return start_new_problem(console, paths, config.template)
        create_source(console, paths, config.template)
    elif create_count is not None:
        return create_test_files(console, paths, create_count)

    if args.std:
        try:
            standard = normalize_standard(args.std)
        except ValueError:
            raise UsageError(f"unsupported C++ standard: {args.std}", f"Supported: {VALID_STANDARDS_TEXT}")
    else:
        standard = config.standard
    timeout = parse_timeout(args.timeout) if args.timeout is not None else config.timeout
    eps = parse_eps(args.eps) if args.eps is not None else config.eps
    settings = make_build_settings(config.compiler, standard, args.debug, config.optimization,
                                   config.flags, config.debug_flags)

    ctx = Context(
        console=console, paths=paths, config=config, settings=settings, timeout=timeout,
        eps=eps, cf=args.cf, cf_url=args.cf_url, cf_refresh=args.cf_refresh,
    )
    samples_mode = bool(args.samples or args.cf or args.cf_url or args.cf_refresh)
    if not (samples_mode or args.input or args.stdin) and has_multiple_tests(paths):
        samples_mode = True  # D1.in/D1.out, D.samples, ... exist: check every test
    raise_stack_limit(config.stack_mb)
    disable_core_dumps()
    disable_crash_dialogs()

    if hand:
        return run_hand(ctx, timeout if args.timeout is not None else None)
    if args.watch:
        return run_watch(ctx, samples_mode, force_input=args.input)
    if samples_mode:
        return run_samples(ctx)
    if args.stdin:
        return run_stdin(ctx)
    return run_normal(ctx, force_input=args.input)


def main(argv: Optional[List[str]] = None) -> int:
    console = Console()
    try:
        return run(argv, console)
    except ExitRequest as e:
        return e.code
    except CprunError as e:
        console.show_error(e.message, e.blocks)
        return e.code
    except KeyboardInterrupt:
        console.line()
        console.info("Interrupted.")
        return ExitCode.INTERRUPTED
    except BrokenPipeError:
        # stdout was closed early (e.g. piped into `head`); silence the flush at exit.
        try:
            devnull = os.open(os.devnull, os.O_WRONLY)
            os.dup2(devnull, sys.stdout.fileno())
        except OSError:
            pass
        return ExitCode.FAILURE
    except Exception as e:  # never show a raw traceback to users
        if os.environ.get("CPRUN_DEBUG"):
            raise
        console.show_error(
            f"internal error: {type(e).__name__}: {e}",
            ["This is a bug in cprun. Re-run with CPRUN_DEBUG=1 to see the full traceback."],
        )
        return ExitCode.SYSTEM
