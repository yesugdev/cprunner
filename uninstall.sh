#!/usr/bin/env bash
# Remove cprun installed by install.sh. Only cprun's own files are removed:
# your configuration (~/.config/cprun) and contest files (.cc, .in, .out,
# .cprun/ build caches) are never touched.
#
#   ./uninstall.sh
#   CPRUN_PREFIX=/opt/cprun ./uninstall.sh
set -euo pipefail

PREFIX="${CPRUN_PREFIX:-$HOME/.local}"
LAUNCHER="$PREFIX/bin/cprun"
SHARE_DIR="$PREFIX/share/cprun"
MARKER="# cprun-launcher"

say()  { printf '[CPRUN] %s\n' "$*"; }
warn() { printf '[WARNING] %s\n' "$*"; }

removed=0

if [ -f "$LAUNCHER" ]; then
    if grep -q "$MARKER" "$LAUNCHER" 2>/dev/null; then
        rm -f "$LAUNCHER"
        say "Removed $LAUNCHER"
        removed=1
    else
        warn "$LAUNCHER was not installed by cprun; left untouched."
    fi
fi

if [ -d "$SHARE_DIR" ]; then
    if [ -f "$SHARE_DIR/install-manifest.txt" ]; then
        rm -rf "$SHARE_DIR"
        say "Removed $SHARE_DIR"
        removed=1
    else
        warn "$SHARE_DIR has no install manifest; left untouched."
    fi
fi

if [ "$removed" -eq 0 ]; then
    say "cprun is not installed in $PREFIX. Nothing to remove."
    exit 0
fi

say "Uninstallation complete."
echo
echo "Your configuration (~/.config/cprun) and contest files (.cc, .in, .out) were not touched."
