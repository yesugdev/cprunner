# cprun

`cprun` is a fast local runner for competitive programming in C++. It compiles,
runs, tests and re-runs your solution with as little typing as possible.

```bash
cprun D.cc
```

The first run creates empty `D.in` and `D.out`. Write the test input in `D.in`
and the correct answer in `D.out`. From then on, `cprun D.cc` compiles your
solution, runs it on `D.in`, compares its output with `D.out`, and tells you
**ACCEPTED** or **WRONG ANSWER**.

- No setup per problem: `D.in` and `D.out` are created for you.
- Sample tests with token-based comparison and clear mismatch reports.
- Compilation cache: unchanged solutions start instantly.
- Time limit, runtime error and signal detection (SIGSEGV, SIGFPE, ...).
- Watch mode that re-runs on every save.
- Optional download of Codeforces samples.
- No dependencies besides Python 3.8+ and g++. Plain-text output, no emoji.

---

## Contents

- [Installation](#installation)
- [Quick start](#quick-start)
- [How D.cc, D.in and D.out work](#how-dcc-din-and-dout-work)
- [New problems: automatic source file](#new-problems-automatic-source-file)
- [Multiple tests](#multiple-tests)
- [Running by hand](#running-by-hand)
- [Interactive input](#interactive-input)
- [Sample testing](#sample-testing)
- [Codeforces samples](#codeforces-samples)
- [Debug mode](#debug-mode)
- [Watch mode](#watch-mode)
- [Piping input with --stdin](#piping-input-with---stdin)
- [C++ standards](#c-standards)
- [Timeout](#timeout)
- [Compilation cache](#compilation-cache)
- [Configuration](#configuration)
- [All options](#all-options)
- [Exit codes](#exit-codes)
- [Troubleshooting](#troubleshooting)
- [Development](#development)

---

## Installation

Requirements: Linux (Ubuntu is the main target), Python 3.8 or newer, and g++.
For Windows, see [Windows](#windows) below.

```bash
git clone <repository> cprun
cd cprun
./install.sh
```

This installs:

```text
~/.local/bin/cprun          the command
~/.local/share/cprun/       the program files
```

Check it:

```bash
cprun --version
```

If your shell says `cprun: command not found`, `~/.local/bin` is not on your
`PATH`. Add this line to `~/.bashrc` (Bash) or `~/.zshrc` (Zsh):

```bash
export PATH="$HOME/.local/bin:$PATH"
```

and open a new terminal.

If g++ is missing:

```bash
sudo apt install g++          # Ubuntu/Debian
sudo dnf install gcc-c++      # Fedora
sudo pacman -S gcc            # Arch
```

To install somewhere else, set a prefix: `CPRUN_PREFIX=/opt/cprun ./install.sh`.

### Windows

1. Run **`cprun-setup-1.0.0.exe`**. No administrator rights are needed, and
   Python is included, so you don't have to install it.
2. Open a **new** terminal (cmd, PowerShell or Windows Terminal):

   ```bat
   cprun --version
   cprun A.cc
   ```

`cprun` needs **g++** (MinGW-w64) to compile solutions. The installer warns you
if it can't find it. To install it:

```bat
winget install BrechtSanders.WinLibs.POSIX.UCRT
```

or install [MSYS2](https://www.msys2.org), run
`pacman -S mingw-w64-ucrt-x86_64-gcc`, and add `C:\msys64\ucrt64\bin` to PATH.

Differences from Linux:

- To end typed input, press **Ctrl+Z, then Enter** instead of Ctrl+D.
- Programs are linked with `-static` (no "libstdc++-6.dll not found" errors) and
  get a 256 MB stack (`-Wl,--stack,268435456`), so deep recursion works.
- Crashes are reported with the Windows exception code, e.g.
  `Exit code: 3221225477 (0xC0000005)` /
  `Exception: ACCESS_VIOLATION`.
- The configuration file is `%APPDATA%\cprun\config.toml` and the template is
  `%APPDATA%\cprun\template.cpp`.
- Watch mode checks for changes every 0.3 s (Linux uses inotify).

Install location: `%LOCALAPPDATA%\Programs\cprun`. The installer adds it to
your user PATH and registers cprun in **Settings > Apps**. Uninstall it there,
or with `cprun --uninstall`. Your contest files are never touched.

#### Building the Windows installer (on Linux)

```bash
sudo apt install nsis mingw-w64
./windows/build.sh        # -> dist/cprun-setup-<version>.exe
```

The build downloads the official Windows embeddable Python from python.org,
pinned by version and SHA-256. It also compiles a small `cprun.exe` launcher
(`windows/launcher.c`) and packs everything with NSIS (`windows/cprun.nsi`).

### Uninstall

```bash
cprun --uninstall
# or, from the repository:
./uninstall.sh
```

This removes only `~/.local/bin/cprun` and `~/.local/share/cprun/`. Your
configuration and your contest files (`.cc`, `.in`, `.out`) are never touched.

---

## Quick start

```text
~/Contests/Codeforces/Round-724/
├── A.cc
├── B.cc
└── D.cc
```

```bash
cd ~/Contests/Codeforces/Round-724
cprun D.cc
```

First run creates the files:

```text
$ cprun D.cc
[CPRUN] Created D.in and D.out.

Write the input data in      D.in
Write the expected output in D.out

Then run again to check your solution:

    cprun D.cc
```

Put the test in them, for example `D.in` = `10 20` and `D.out` = `30`, then:

```text
$ cprun D.cc
[CPRUN] Input: D.in   Expected output: D.out
[CPRUN] Compiling D.cc with C++17...
[CPRUN] Compilation successful.

[CPRUN] Running D.cc...

Output:
30

[CPRUN] ACCEPTED  output matches D.out

[CPRUN] Time: 0.002s
```

If the answer is wrong:

```text
[CPRUN] WRONG ANSWER  output differs from D.out

Mismatch at token 1 (line 1):
Expected: 31
Received: 30
```

Other commands:

```bash
cprun D.cc samples 3  # create D_tests/1.in 1.out ... 3.in 3.out; then `cprun D.cc` checks them all
cprun D.cc hand       # just compile and run; type the input by hand
cprun D.cc            # run with D.in, compare with D.out
cprun D.cc --input    # type new input (replaces D.in)
cprun D.cc --samples  # check the sample tests
cprun D.cc --debug    # debug build with warnings
cprun D.cc --watch    # re-run on every save
```

---

## How D.cc, D.in and D.out work

For a source file, `cprun` removes the extension (`.cc`, `.cpp` or `.cxx`) and
uses the same name for input and output, in the same directory:

| Source         | Input          | Output          |
|----------------|----------------|-----------------|
| `D.cc`         | `D.in`         | `D.out`         |
| `solution.cpp` | `solution.in`  | `solution.out`  |
| `A.cxx`        | `A.in`         | `A.out`         |
| `round/B.cc`   | `round/B.in`   | `round/B.out`   |

```text
D.cc  -> compile -> run with D.in -> compare output with D.out -> ACCEPTED / WRONG ANSWER
```

- **D.in** is the input data. **D.out** is the expected (correct) output.
  You write both. `cprun` creates them empty when they're missing and
  **never overwrites them**.
- The comparison is token based, the same as in [sample testing](#comparison):
  extra spaces, blank lines and CRLF don't matter.
- If `D.out` is empty, the program still runs and its output is shown, but
  there is nothing to compare, so no verdict is printed.
- Your program's actual output is shown in the terminal and saved to
  `.cprun/D.actual`, so you can diff it with `D.out`.
- **stderr** is shown in the terminal under `stderr:` but is not compared, so
  `cerr` debug prints don't affect the verdict.
- Runtime errors and time limits are reported instead of a verdict.
- Compiled programs go to `.cprun/` (see [Compilation cache](#compilation-cache)),
  never into your contest directory.

The extension is required: `cprun D` is an error, so it is always clear which
file is meant.

The program runs with the source directory as its working directory, so
`freopen("input.txt", "r", stdin)` finds files next to the source.

---

## New problems: automatic source file

If the source file doesn't exist yet, `cprun` creates it from a template:

```text
$ cprun A.cc
[CPRUN] Created A.cc from the default template
[CPRUN] Created A.in and A.out

Write your solution in       A.cc
Write the input data in      A.in
Write the expected output in A.out
```

`cprun A.cc samples 5` creates `A.cc` too, together with `A_tests/1.in` ... `A_tests/5.out`.
`cprun A.cc --watch` creates it and starts watching right away.

The default template:

```cpp
#include <bits/stdc++.h>
using namespace std;

int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    return 0;
}
```

To use your own, save it as `~/.config/cprun/template.cpp`, or set
`template = "~/cp/template.cpp"` in the configuration.

- An existing source file is never replaced.
- `cprun A.cpp` does not create a new file when `A.cc` already exists. It asks
  whether you meant `A.cc`.
- `hand`, `--samples`, `--stdin` and `--input` still require an existing
  source file.

## Multiple tests

To check several tests, create them with `samples N`. They go into their own
folder, `A_tests/`, so the contest directory stays clean:

```text
$ cprun A.cc samples 3
[CPRUN] Created 6 file(s) in A_tests/: 1.in 1.out 2.in 2.out 3.in 3.out

Write the input data in      A_tests/1.in ... A_tests/3.in
Write the expected output in A_tests/1.out ... A_tests/3.out

Then check all tests with:

    cprun A.cc
```

```text
Round-724/
├── A.cc
├── A_tests/
│   ├── 1.in
│   ├── 1.out
│   ├── 2.in
│   ├── 2.out
│   ├── 3.in
│   └── 3.out
├── B.cc
└── B_tests/
```

Fill them in, then run plain `cprun A.cc`. When a test folder (or a `.samples`
file) exists, `cprun A.cc` checks **all** tests automatically. You don't need
`--samples`:

```text
$ cprun A.cc
[CPRUN] Found 3 test(s) in A_tests/
[CPRUN] Compiling A.cc with C++17...
[CPRUN] Compilation successful.

[TEST 1] PASSED    0.001s   A_tests/1.in
[TEST 2] FAILED    0.001s   A_tests/2.in

Mismatch at token 1 (line 1):
Expected: 11
Received: 10
...
[TEST 3] PASSED    0.001s   A_tests/3.in

--------------------------------
CPRUN RESULT
--------------------------------

Passed: 2 / 3
Failed: 1 / 3
```

- `cprun A.cc samples 5` later adds `4` and `5`. Existing files are never
  overwritten.
- Tests whose `.in` and `.out` are both still empty are skipped, so unfilled
  files are not counted as failures.
- A test with input but an empty `.out` runs and shows its output as
  `NOT CHECKED`.
- If `A.in` / `A.out` also exist, they are checked together with the folder's
  tests.
- Numbered files directly in the contest directory (`A1.in`, `A1.out`, ...)
  are still found too.
- `cprun A.cc --watch` re-checks all tests whenever the code or a test file is
  saved.

## Running by hand

```bash
cprun A.cc hand
```

Compiles and runs the program connected directly to your terminal. You type
the input and see the output immediately, like running `./a.out` yourself:

```text
$ cprun A.cc hand
5
double: 10
21
double: 42

[CPRUN] Program finished.
[CPRUN] Time: 2.355s (including the time spent typing)
```

- The program starts right away, with no status messages. Compile errors are
  still shown. Ctrl+D ends the input, Ctrl+C stops the program.
- No files are read or written: `A.in`, `A.out` and `A_tests/` are ignored.
- There is no time limit, since you are typing. Add `--timeout=2` if you want one.
- This is useful for interactive problems and quick experiments.
- Runtime errors are still reported, with the exit code and signal.
- `--debug` and `--std=...` work as usual.

## Interactive input

Instead of editing `D.in`, you can type the input in the terminal with
`--input`. It replaces `D.in`, and `cprun` reads until you press **Ctrl+D**:

```text
Enter input.
Press Ctrl+D when finished:

3
10 20 30
```

Tips:

- Press Ctrl+D at the start of an empty line. In the middle of a line, press it
  twice.
- Ctrl+C cancels without changing `D.in`.
- A missing final newline is added automatically.
- You can also pipe or redirect: `cprun D.cc --input < test.txt` saves
  `test.txt` as `D.in` and runs it.

---

## Sample testing

```bash
cprun D.cc --samples       # or: cprun D.cc -s
```

Sample mode runs **several** tests at once. It finds all sample tests (including
the `D.in` + `D.out` pair), runs each one, and compares the output.

### Sample files

`D.samples` is the main format:

```text
=== TEST 1 ===
INPUT
10 20
OUTPUT
30

=== TEST 2 ===
INPUT
100 200
OUTPUT
300
```

- `=== TEST n ===` headers are optional: an `INPUT` line after a complete test
  starts a new one.
- `INPUT` / `OUTPUT` are case-insensitive and may end with a colon.
- Lines starting with `#` *between* tests are comments. Inside a section,
  everything is data.
- A test without an `OUTPUT` section runs and its output is shown, but it isn't
  checked.

`cprun` looks for samples in all of these places and runs everything it finds:

```text
D.in + D.out          (unless both are empty)
D_tests/1.in + D_tests/1.out, ...       (created by `cprun D.cc samples N`)
D.samples
D.sample
samples/D
samples/D.txt
samples/D.samples
D1.in + D1.out, D2.in + D2.out, ...    (also D_1.in, D-1.in, and .ans instead of .out)
samples/D/1.in + samples/D/1.out, ...
```

Numbered files run in natural order (`D2` before `D10`). An empty `.out`
file means "not filled in": the test runs but is not checked, and a pair with
both files empty is skipped. If a source file `D1.cc` exists, `D1.in` belongs
to that problem and is not used as a sample of `D`. This matters for problems
like D1/D2.

### Comparison

Output is compared token by token, like most judges' checkers. These are
ignored:

- leading and trailing whitespace
- repeated spaces, tabs vs spaces, line breaks between tokens
- trailing empty lines
- CRLF vs LF

So expected `1 2 3` equals received `1    2\n3`, but `1 2 4` fails.

For floating-point answers ("absolute or relative error at most 1e-6"):

```bash
cprun D.cc --samples --eps=1e-6
```

### Output

```text
$ cprun D.cc --samples

[CPRUN] Found 3 sample test(s) in D.samples
[CPRUN] Compiling D.cc with C++17...
[CPRUN] Compilation successful.

[TEST 1] PASSED    0.002s
[TEST 2] PASSED    0.003s
[TEST 3] FAILED    0.002s

Mismatch at token 2 (line 1):
Expected: YES
Received: NO

Expected:
NO YES

Received:
NO NO

--------------------------------
CPRUN RESULT
--------------------------------

Passed: 2 / 3
Failed: 1 / 3
Time: 0.007s
--------------------------------
```

Other failure reports:

```text
Expected token 7: 42
Received: <missing>
```

```text
Expected: 10 tokens
Received: 12 tokens

Extra token at position 11:
123
```

A test can also show `RUNTIME ERROR` (with the exit code, signal and stderr) or
`TIME LIMIT EXCEEDED`.

When everything passes:

```text
================================
ALL TESTS PASSED
================================

3 / 3 tests passed
Total time: 0.007s
```

---

## Codeforces samples

Internet access is never needed for normal use. When you want it, `cprun` can
download samples straight from the problem page:

```bash
cprun D.cc --cf-url https://codeforces.com/contest/1846/problem/D
cprun D.cc --cf                  # detect the problem automatically
cprun D.cc --cf --cf-refresh     # download again, ignoring the cache
```

`--cf` and `--cf-url` imply `--samples`. The problem letter comes from the file
name (`D.cc` → D, `D2.cc` → D2), and the contest id comes from the first match
among:

1. the file name itself: `1846D.cc`
2. `cf_contest = 1846` in a `cprun.toml` in the contest directory
3. the directory name: `1846/`, `contest-1846/`, `cf1846/`, `Round-1846/`
   (the source directory or its parent)

Downloaded samples are cached in `.cprun/D.cf.samples`, so later runs work
offline. If the download fails (no network, or Codeforces blocking automated
requests), `cprun` prints the reason and falls back to your local sample files
if there are any.

---

## Debug mode

```bash
cprun D.cc --debug       # or -d
```

Compiles with `-g -O0 -Wall -Wextra` and prints `[CPRUN] DEBUG MODE`. Compiler
warnings are shown after a successful compile. Debug and normal builds are
cached separately (`.cprun/D-debug` and `.cprun/D`), so switching between them
doesn't force a rebuild each time.

To catch out-of-bounds access and undefined behaviour, add sanitizers in your
configuration:

```toml
debug_flags = ["-g", "-O0", "-Wall", "-Wextra", "-fsanitize=address,undefined", "-D_GLIBCXX_DEBUG"]
```

When a program crashes, `cprun` explains the signal:

```text
[CPRUN] RUNTIME ERROR

Exit code: 139
Signal: SIGSEGV (invalid memory access: out-of-bounds index, null/dangling pointer, or stack overflow)
```

The stack size limit is raised to 1 GB (`stack_mb`), so deep recursion
behaves like it does on most judges instead of crashing locally.

---

## Watch mode

```bash
cprun D.cc --watch               # re-run with D.in on every change
cprun D.cc --samples --watch     # re-check samples on every change
```

```text
[CPRUN] Watching D.cc... (press Ctrl+C to stop)

-------------------------------- 14:03:12
[CHANGE] D.cc modified.

[CPRUN] Using existing D.in
[CPRUN] Compiling D.cc with C++17...
[CPRUN] Compilation successful.

[CPRUN] Running D.cc...

Output:
42
```

Watch mode re-runs (and re-checks against `D.out`) when `D.cc`, `D.in` or `D.out` change (in sample mode: the sample
files). It uses Linux inotify, so it doesn't poll while idle, and works with
editors that save by replacing the file (Vim, VS Code, JetBrains). Compile
errors and failures don't stop watching. Press Ctrl+C to quit.

---

## Piping input with --stdin

```bash
echo "5 10" | cprun D.cc --stdin
cat test.in | cprun D.cc --stdin
cprun D.cc --stdin < big_test.txt | sort | head
```

The program reads `cprun`'s own stdin. `D.in` and `D.out` are not used, and no
verdict is printed.

All `[CPRUN]` status messages go to **stderr**, so stdout contains only the
program's output. That makes `cprun` safe to use in pipelines.

---

## C++ standards

```bash
cprun D.cc --std=c++17     # default
cprun D.cc --std=c++20
cprun D.cc --std=c++23
cprun D.cc --std=gnu++20
```

Short forms work too: `--std=20`, `--std=cpp20`. The default can be changed
with `standard` in the configuration. The command-line option always wins.

## Timeout

The default time limit is 2 seconds per run (per test in sample mode):

```bash
cprun D.cc --timeout=5
cprun D.cc --timeout=500ms
```

```text
[CPRUN] TIME LIMIT EXCEEDED

Limit: 5.00 seconds
```

The program and anything it started are killed, so an infinite loop can't hang
`cprun`. A program that prints endlessly is stopped at 256 MB of output
(`output_limit_mb`). Time is wall-clock time, measured with a high-resolution
timer and shown as seconds with millisecond precision (`0.003s`, `1.203s`).

## Compilation cache

Executables live in `.cprun/` next to the source:

```text
Round-724/
├── D.cc
├── D.in
├── D.out
└── .cprun/
    ├── .gitignore     (ignores everything; .cprun never ends up in git)
    ├── D              release build
    ├── D.meta         cache key
    └── D-debug        debug build
```

A rebuild happens only when something relevant changes:

- the source content (SHA-256, not just the modification time)
- local headers it includes, such as `#include "debug.h"`
- the compiler (path and binary)
- the C++ standard, flags, or debug/release mode

```text
[CPRUN] D.cc unchanged.
[CPRUN] Using cached executable.
```

To force a rebuild, delete `.cprun/`. It is safe to delete at any
time.

---

## Configuration

All settings are optional. They are read from:

1. `~/.config/cprun/config.toml`: global (respects `$XDG_CONFIG_HOME`; `$CPRUN_CONFIG` overrides the path)
2. `cprun.toml` in the source directory or the nearest parent directory: per contest
3. command-line options, which always win

```toml
compiler = "g++"
standard = "c++17"
timeout = 2
optimization = "-O2"
color = true

flags = ["-DLOCAL"]                           # extra flags for every build
debug_flags = ["-g", "-O0", "-Wall", "-Wextra"]
stack_mb = 1024                               # 0 = keep the system default
output_limit_mb = 256
display_lines = 200                           # terminal output lines shown (0 = all)
eps = 1e-6                                    # numeric tolerance for samples
cf_contest = 1846                             # for --cf
template = "~/cp/template.cpp"                # for new source files
```

| Key               | Default                       | Meaning                                         |
|-------------------|-------------------------------|-------------------------------------------------|
| `compiler`        | `"g++"`                       | C++ compiler command                            |
| `standard`        | `"c++17"`                     | Default C++ standard                            |
| `timeout`         | `2`                           | Time limit in seconds                           |
| `optimization`    | `"-O2"`                       | Optimization flag for normal builds             |
| `flags`           | `[]`                          | Extra flags for all builds (list or string)     |
| `debug_flags`     | `["-g","-O0","-Wall","-Wextra"]` | Flags for `--debug` builds                   |
| `color`           | `true`                        | `false` disables colors                         |
| `stack_mb`        | `1024`                        | Stack limit for your program                    |
| `output_limit_mb` | `256`                         | Kill programs that print more than this         |
| `display_lines`   | `200`                         | Max lines of output printed to the terminal; `D.out` always has everything |
| `eps`             | none                          | Default `--eps` for sample comparison           |
| `cf_contest`      | none                          | Codeforces contest id for `--cf`                |
| `template`        | `~/.config/cprun/template.cpp` if it exists, else built-in | Template for new source files |

A commented example is in [`examples/config.toml`](examples/config.toml).

Colors are used only when the output is a terminal. They are also disabled by
`color = false` in the configuration or the `NO_COLOR` environment variable.

---

## All options

```text
cprun <source> [options]

  (none)            Compile, run with D.in, compare with D.out (creates both if missing);
                    if numbered tests / D.samples exist: check all tests
  samples N         Create empty test files D_tests/1.in 1.out ... N.in N.out
  hand              Compile and run in the terminal; type the input by hand
  -i, --input       Type new input (replaces D.in), then run
  -s, --samples     Run sample tests and compare outputs
      --stdin       Pass cprun's stdin to the program
  -w, --watch       Re-run on changes
  -d, --debug       Debug build: -g -O0 -Wall -Wextra
      --std=STD     C++ standard (default c++17)
      --timeout=SEC Time limit (default 2)
      --eps=EPS     Numeric tolerance for sample comparison
      --cf          Download Codeforces samples (detect problem)
      --cf-url=URL  Download Codeforces samples from URL
      --cf-refresh  Ignore the Codeforces sample cache
  -h, --help        Help
  -V, --version     Version
      --uninstall   Remove cprun
```

---

## Exit codes

| Code | Meaning                                                   |
|------|-----------------------------------------------------------|
| 0    | Accepted (all samples passed), or no D.out to compare     |
| 1    | Wrong answer, runtime error, output limit, failed sample  |
| 2    | Invalid arguments, missing source / samples, D.in just created |
| 3    | Compilation failed                                        |
| 4    | Time limit exceeded                                       |
| 5    | Configuration or system error (e.g. g++ not found)        |
| 130  | Interrupted with Ctrl+C                                   |

```bash
cprun D.cc --samples && echo "ready to submit"
```

---

## Troubleshooting

**`cprun: command not found`**: add `export PATH="$HOME/.local/bin:$PATH"` to
`~/.bashrc` or `~/.zshrc` and open a new terminal.

**`[CPRUN] Error: g++ was not found.`**: install it with
`sudo apt install g++`, or point `cprun` to another compiler with
`compiler = "clang++"` in the configuration.

**No ACCEPTED / WRONG ANSWER line.** `D.out` is empty. Write the correct answer
in it.

**`D.in` contains the wrong test.** Edit the file, or run `cprun D.cc --input`.

**Works locally, crashes with SIGSEGV on the judge.** Often an out-of-bounds
access that happens to work locally. Run `cprun D.cc --debug` with sanitizers
enabled (see [Debug mode](#debug-mode)).

**`--cf` cannot download samples.** Codeforces sometimes blocks automated
requests (HTTP 403) or needs a login for gym problems. Copy the samples into
`D.samples` and use `--samples`.

**`--std=c++23` fails to compile.** Older g++ versions don't support the newest
standards. Check `g++ --version`.

**Colors look wrong in a log file.** Colors are disabled automatically when
output is not a terminal. Use `NO_COLOR=1` or `color = false` to force them off.

**Something looks like a bug in cprun.** For an "internal error", `CPRUN_DEBUG=1 cprun ...` prints the full traceback.

**Clearing the cache.** `rm -rf .cprun` is always safe.

---

## Examples

`examples/` contains a ready-to-run problem:

```bash
cd examples
cprun D.cc              # creates D.in and D.out
echo "10 20" > D.in
echo "30" > D.out
cprun D.cc              # ACCEPTED
cprun D.cc --samples    # 2 / 2 tests passed
```

---

## Development

```text
cprun/
├── install.sh / uninstall.sh
├── run_tests.sh
├── bin/cprun               run from the checkout without installing
├── src/cprun/
│   ├── cli.py              argument parsing, help, top-level error handling
│   ├── modes.py            normal / samples / stdin / watch workflows
│   ├── paths.py            source validation, D.in / D.out / .cprun names
│   ├── compiler.py         compilation, cache keys, header dependency tracking
│   ├── runner.py           process execution, timeout, signals, output limit
│   ├── compare.py          token-based output comparison
│   ├── samples.py          sample file parser and discovery
│   ├── codeforces.py       Codeforces sample download
│   ├── interactive.py      typed input (--input), atomic file writes
│   ├── watch.py            inotify file watching
│   ├── config.py           configuration loading and validation
│   ├── minitoml.py         TOML fallback for Python < 3.11
│   ├── term.py             colors and terminal output
│   ├── install_info.py     cprun --uninstall
│   └── winsetup.py         Windows installer helper (user PATH)
├── windows/
│   ├── build.sh            builds dist/cprun-setup-<version>.exe
│   ├── cprun.nsi           NSIS installer script
│   └── launcher.c          cprun.exe launcher
├── tests/
└── examples/
```

Run the tests (needs g++ for the end-to-end tests):

```bash
./run_tests.sh
./run_tests.sh -k samples            # only matching tests
./run_tests.sh tests.test_compare    # one module
```

Run without installing: `./bin/cprun D.cc`.

## License

MIT. See [LICENSE](LICENSE).
# cprunner
