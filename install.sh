#!/usr/bin/env bash
# Install cprun for the current user.
#
#   ./install.sh                      installs to ~/.local/bin/cprun
#   CPRUN_PREFIX=/opt/cprun ./install.sh   installs to /opt/cprun/bin/cprun
#
# Files installed:
#   $PREFIX/bin/cprun              small launcher script
#   $PREFIX/share/cprun/           the cprun Python package + install manifest
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="${CPRUN_PREFIX:-$HOME/.local}"
BIN_DIR="$PREFIX/bin"
SHARE_DIR="$PREFIX/share/cprun"
LAUNCHER="$BIN_DIR/cprun"
MARKER="# cprun-launcher"

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    C_TAG=$'\033[36m'; C_ERR=$'\033[1;31m'; C_WARN=$'\033[1;33m'; C_OK=$'\033[32m'; C_RESET=$'\033[0m'
else
    C_TAG=""; C_ERR=""; C_WARN=""; C_OK=""; C_RESET=""
fi
say()  { printf '%s[CPRUN]%s %s\n' "$C_TAG" "$C_RESET" "$*"; }
warn() { printf '%s[WARNING]%s %s\n' "$C_WARN" "$C_RESET" "$*"; }
fail() { printf '%s[CPRUN] Error:%s %s\n' "$C_ERR" "$C_RESET" "$1" >&2; shift; for b in "$@"; do printf '\n%s\n' "$b" >&2; done; exit 5; }

say "Installing..."

# 1. Dependencies -------------------------------------------------------------
if ! command -v python3 >/dev/null 2>&1; then
    fail "python3 was not found." "Install Python 3:

Ubuntu/Debian:
    sudo apt install python3

Fedora:
    sudo dnf install python3

Arch:
    sudo pacman -S python"
fi
PYTHON="$(command -v python3)"
if ! "$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)'; then
    fail "Python 3.8 or newer is required (found $("$PYTHON" --version 2>&1))."
fi

if [ ! -f "$REPO_DIR/src/cprun/cli.py" ]; then
    fail "cannot find the cprun sources in $REPO_DIR/src/cprun." "Run install.sh from the cprun repository."
fi

if ! command -v g++ >/dev/null 2>&1; then
    warn "g++ was not found. cprun is installed, but needs a C++ compiler to run solutions."
    cat <<'EOF'

Install GCC:

Ubuntu/Debian:
    sudo apt install g++

Fedora:
    sudo dnf install gcc-c++

Arch:
    sudo pacman -S gcc

EOF
fi

# 2. Copy files ---------------------------------------------------------------
if [ -e "$LAUNCHER" ] && ! grep -q "$MARKER" "$LAUNCHER" 2>/dev/null; then
    fail "$LAUNCHER already exists and was not installed by cprun." "Remove or rename it, then run ./install.sh again."
fi

mkdir -p "$BIN_DIR" "$SHARE_DIR" || fail "cannot create $BIN_DIR or $SHARE_DIR." "Check that you have write permission."
rm -rf "$SHARE_DIR/cprun"
cp -R "$REPO_DIR/src/cprun" "$SHARE_DIR/cprun"
find "$SHARE_DIR/cprun" -name '__pycache__' -type d -prune -exec rm -rf {} +
"$PYTHON" -m compileall -q "$SHARE_DIR/cprun" >/dev/null 2>&1 || true  # faster startup

VERSION="$("$PYTHON" -c 'import sys; sys.path.insert(0, sys.argv[1]); import cprun; print(cprun.__version__)' "$SHARE_DIR")"
SHARE_LITERAL="$("$PYTHON" -c 'import sys; print(repr(sys.argv[1]))' "$SHARE_DIR")"

# 3. Launcher -------------------------------------------------------------------
TMP_LAUNCHER="$LAUNCHER.tmp.$$"
cat > "$TMP_LAUNCHER" <<EOF
#!$PYTHON -I
$MARKER (installed by install.sh; remove with: cprun --uninstall)
import sys
sys.path.insert(0, $SHARE_LITERAL)
from cprun.cli import main
sys.exit(main())
EOF
chmod 755 "$TMP_LAUNCHER"
mv -f "$TMP_LAUNCHER" "$LAUNCHER"

cat > "$SHARE_DIR/install-manifest.txt" <<EOF
version=$VERSION
launcher=$LAUNCHER
share=$SHARE_DIR
EOF

# 4. Verify -----------------------------------------------------------------------
if ! "$LAUNCHER" --version >/dev/null 2>&1; then
    fail "the installed cprun does not start." "Try running: $LAUNCHER --version"
fi
say "Installed cprun $VERSION to $LAUNCHER"
printf '%s[CPRUN] Installation successful.%s\n' "$C_OK" "$C_RESET"

# 5. PATH check -----------------------------------------------------------------
echo
echo "Run:"
echo
echo "    cprun D.cc"
echo

case ":$PATH:" in
    *":$BIN_DIR:"*)
        FOUND="$(command -v cprun 2>/dev/null || true)"
        if [ -n "$FOUND" ] && [ "$FOUND" != "$LAUNCHER" ]; then
            warn "another cprun at $FOUND comes first in your PATH."
        fi
        ;;
    *)
        case "$(basename "${SHELL:-bash}")" in
            zsh) RC="~/.zshrc" ;;
            bash) RC="~/.bashrc" ;;
            *) RC="~/.profile" ;;
        esac
        if [ "$BIN_DIR" = "$HOME/.local/bin" ]; then
            EXPORT_LINE='export PATH="$HOME/.local/bin:$PATH"'
        else
            EXPORT_LINE="export PATH=\"$BIN_DIR:\$PATH\""
        fi
        echo "$BIN_DIR is not in your PATH. If cprun is not found, add:"
        echo
        echo "    $EXPORT_LINE"
        echo
        echo "to $RC, then open a new terminal (or run: source $RC)."
        ;;
esac
