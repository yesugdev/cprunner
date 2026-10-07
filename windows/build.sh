#!/usr/bin/env bash
# Build the Windows installer (dist/cprun-setup-<version>.exe) on Linux.
#
# Requirements (Ubuntu/Debian):
#     sudo apt install nsis mingw-w64 curl unzip
#
# Tool locations can be overridden:
#     MINGW_CC=/path/to/x86_64-w64-mingw32-gcc MAKENSIS=/path/to/makensis ./windows/build.sh
#
# The installer bundles the official Windows "embeddable" Python from
# python.org, so users don't need to install Python. They need g++ (MinGW-w64)
# to compile solutions; the installer checks for it.
set -euo pipefail

PYTHON_VERSION="3.14.8"
PYTHON_SHA256="a93abe456ab01bd96d7a085b3cdb6566b3063f4241360d114142fbdb07f0a310"
PYTHON_ZIP="python-${PYTHON_VERSION}-embed-amd64.zip"
PYTHON_URL="https://www.python.org/ftp/python/${PYTHON_VERSION}/${PYTHON_ZIP}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WIN="$ROOT/windows"
CACHE="$WIN/.cache"
STAGE="$WIN/build/stage"
DIST="$ROOT/dist"
MINGW_CC="${MINGW_CC:-x86_64-w64-mingw32-gcc}"
MAKENSIS="${MAKENSIS:-makensis}"

say()  { printf '[BUILD] %s\n' "$*"; }
fail() { printf '[BUILD] Error: %s\n' "$*" >&2; exit 1; }

command -v "$MINGW_CC" >/dev/null 2>&1 || fail "$MINGW_CC not found. Install it: sudo apt install mingw-w64"
command -v "$MAKENSIS" >/dev/null 2>&1 || fail "$MAKENSIS not found. Install it: sudo apt install nsis"
command -v unzip >/dev/null 2>&1 || fail "unzip not found. Install it: sudo apt install unzip"

VERSION="$(python3 -c 'import sys; sys.path.insert(0, sys.argv[1]); import cprun; print(cprun.__version__)' "$ROOT/src")"
say "cprun $VERSION, bundled Python $PYTHON_VERSION"

# 1. Embeddable Python (downloaded once, verified by SHA-256) -------------------
mkdir -p "$CACHE"
if [ ! -f "$CACHE/$PYTHON_ZIP" ]; then
    say "Downloading $PYTHON_URL"
    curl -fsSL -o "$CACHE/$PYTHON_ZIP.part" "$PYTHON_URL"
    mv "$CACHE/$PYTHON_ZIP.part" "$CACHE/$PYTHON_ZIP"
fi
echo "$PYTHON_SHA256  $CACHE/$PYTHON_ZIP" | sha256sum -c --quiet - \
    || fail "checksum mismatch for $PYTHON_ZIP (delete $CACHE and try again)"

# 2. Stage the files ------------------------------------------------------------
rm -rf "$STAGE"
mkdir -p "$STAGE/python" "$STAGE/lib" "$STAGE/examples"
unzip -q "$CACHE/$PYTHON_ZIP" -d "$STAGE/python"

# Let the embedded Python find the cprun package in ..\lib
PTH="$(ls "$STAGE"/python/python3*._pth)"
printf '..\\lib\r\n' >> "$PTH"

cp -R "$ROOT/src/cprun" "$STAGE/lib/cprun"
find "$STAGE/lib" -name '__pycache__' -type d -prune -exec rm -rf {} +
# Pre-compile for faster startup when the local Python has the same version.
EMBED_MINOR="${PYTHON_VERSION%.*}"
if [ "$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')" = "$EMBED_MINOR" ]; then
    python3 -m compileall -q "$STAGE/lib" >/dev/null
fi

cp "$ROOT/LICENSE" "$STAGE/LICENSE.txt"
cp "$ROOT/README.md" "$STAGE/README.md"
cp "$ROOT/examples/D.cc" "$ROOT/examples/D.samples" "$STAGE/examples/"
cp "$ROOT/examples/config.toml" "$STAGE/examples/config.toml"

# 3. Launcher -------------------------------------------------------------------
say "Compiling cprun.exe"
"$MINGW_CC" -municode -O2 -s -Wall -Wextra -o "$STAGE/cprun.exe" "$WIN/launcher.c"

# 4. Installer ------------------------------------------------------------------
mkdir -p "$DIST"
OUTFILE="$DIST/cprun-setup-$VERSION.exe"
say "Building installer"
"$MAKENSIS" -V2 -INPUTCHARSET UTF8 \
    -DVERSION="$VERSION" -DSTAGE="$STAGE" -DOUTFILE="$OUTFILE" \
    "$WIN/cprun.nsi"

say "Done: $OUTFILE ($(du -h "$OUTFILE" | cut -f1))"
