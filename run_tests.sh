#!/usr/bin/env bash
# Run the cprun test suite.
#   ./run_tests.sh                 all tests
#   ./run_tests.sh -k timeout      only tests whose name matches "timeout"
#   ./run_tests.sh tests.test_compare
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"

if [ $# -gt 0 ] && [[ "$1" != -* ]]; then
    exec python3 -m unittest -v "$@"
fi
exec python3 -m unittest discover -s tests -t . -v "$@"
