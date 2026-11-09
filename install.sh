#!/bin/sh
# Kura installer for Linux. Installs for the current user only (no root needed
# for Kura itself); system packages are optional and asked about first.
#
#   ./install.sh              install or update
#   ./install.sh --uninstall  remove Kura (keeps settings, sign-ins and games)
#   ./install.sh --purge      remove Kura and its settings/cache (never your games)
#
# Options: --yes (no questions, say yes)   --no-system (never call sudo)
#          --venv (always use a private Python environment)
#          --dev  (run from this folder instead of copying it; for development)
set -eu

SRC=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PREFIX=${PREFIX:-$HOME/.local}
LIB=$PREFIX/lib/kura
BIN=$PREFIX/bin
APPS=$PREFIX/share/applications
ICONS=$PREFIX/share/icons/hicolor/scalable/apps
CONFIG=${XDG_CONFIG_HOME:-$HOME/.config}/kura
DATA=${XDG_DATA_HOME:-$HOME/.local/share}/kura
CACHE=${XDG_CACHE_HOME:-$HOME/.cache}/kura

MODE=install; YES=0; SYSTEM=1; FORCE_VENV=0; DEV=0
for arg in "$@"; do
    case $arg in
        --uninstall) MODE=uninstall ;;
        --purge) MODE=purge ;;
        --yes|-y) YES=1 ;;
        --no-system) SYSTEM=0 ;;
        --venv) FORCE_VENV=1 ;;
        --dev) DEV=1 ;;
        -h|--help) sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "Unknown option: $arg (try --help)" >&2; exit 2 ;;
    esac
done

say()  { printf '\033[1m==>\033[0m %s\n' "$*"; }
note() { printf '    %s\n' "$*"; }
die()  { printf '\033[31merror:\033[0m %s\n' "$*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }
ask() {  # ask "question" -> 0 for yes
    [ "$YES" = 1 ] && return 0
    [ -t 0 ] || return 1
    printf '    %s [Y/n] ' "$1"; read -r reply
    case $reply in ""|y|Y|yes|Yes) return 0 ;; *) return 1 ;; esac
}

# ---------------------------------------------------------------- uninstall
if [ "$MODE" != install ]; then
    say "Removing Kura"
    rm -rf "$LIB"
    rm -f "$BIN/kura" "$APPS/kura.desktop" "$ICONS/kura.svg"
    have update-desktop-database && update-desktop-database "$APPS" >/dev/null 2>&1 || true
    if [ "$MODE" = purge ]; then
        rm -rf "$CONFIG" "$DATA" "$CACHE"
        note "Settings, store backends and cache removed."
    else
        note "Kept: $CONFIG (settings, GOG sign-in), $DATA (store backends)."
    fi
    note "Not touched: your games folder, and Epic/Amazon sign-ins in ~/.config/legendary and ~/.config/nile."
    exit 0
fi

# ---------------------------------------------------------------- checks
[ "$(uname -s)" = Linux ] || die "Kura only runs on Linux."
[ -f "$SRC/kura/__main__.py" ] || die "Run this from the Kura folder (kura/__main__.py not found next to install.sh)."
have python3 || die "python3 is required. Install it with your package manager and run this again."
python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' \
    || die "Python 3.10 or newer is required (found $(python3 -V 2>&1))."

PM=
for candidate in pacman apt-get dnf zypper; do
    if have "$candidate"; then PM=$candidate; break; fi
done

sys_install() {  # sys_install "what it is for" pkg...
    what=$1; shift
    case $PM in
        pacman)  cmd="sudo pacman -S --needed $*" ;;
        apt-get) cmd="sudo apt-get install -y $*" ;;
        dnf)     cmd="sudo dnf install -y $*" ;;
        zypper)  cmd="sudo zypper install -y $*" ;;
        *)       note "$what: install it with your package manager ($*)."; return 1 ;;
    esac
    if [ "$SYSTEM" = 1 ] && have sudo && ask "Install $what now? ($cmd)"; then
        $cmd && return 0
        note "That did not work; you can run it yourself later: $cmd"
        return 1
    fi
    note "$what is missing. To add it later: $cmd"
    return 1
}

# ---------------------------------------------------------------- Python side
say "Checking Python libraries"
uses_system_python() {
    probe=$(mktemp "${TMPDIR:-/tmp}/kura-probe.XXXXXX.qml") || return 1
    printf 'import QtQuick\nimport QtQuick.Controls.Basic\nimport QtQuick.Layouts\nimport QtQuick.Dialogs\nimport QtQuick.Effects\nItem {}\n' > "$probe"
    QT_QPA_PLATFORM=offscreen python3 - "$probe" <<'EOF' >/dev/null 2>&1
import sys
import requests
from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtNetwork import QNetworkDiskCache
from PySide6.QtQml import QQmlComponent, QQmlEngine
import PySide6.QtQuick
app = QGuiApplication([])
engine = QQmlEngine()
component = QQmlComponent(engine, QUrl.fromLocalFile(sys.argv[1]))
ok = component.isReady()
del component, engine
sys.exit(0 if ok else 1)
EOF
    result=$?
    rm -f "$probe"
    return $result
}

PYTHON=python3
if [ "$FORCE_VENV" = 0 ] && uses_system_python; then
    note "Using the system's PySide6 (Qt 6) and requests."
    rm -rf "$LIB/venv"
else
    if [ "$FORCE_VENV" = 0 ] && [ "$PM" = pacman ]; then
        sys_install "Qt for Python" pyside6 python-requests || true
    fi
    if [ "$FORCE_VENV" = 0 ] && uses_system_python; then
        note "Using the system's PySide6 (Qt 6) and requests."
    else
        say "Setting up a private Python environment (downloads Qt, roughly 200 MB)"
        mkdir -p "$LIB"
        if ! python3 -m venv "$LIB/venv" 2>/dev/null; then
            [ "$PM" = apt-get ] && sys_install "Python's venv module" python3-venv && python3 -m venv "$LIB/venv" \
                || die "Could not create a Python environment (python3 -m venv failed)."
        fi
        "$LIB/venv/bin/python" -m pip install --quiet --upgrade pip
        "$LIB/venv/bin/python" -m pip install --quiet "PySide6-Essentials>=6.6" requests \
            || die "Could not download PySide6. Check your internet connection and run this again."
        PYTHON=$LIB/venv/bin/python
    fi
fi

# ---------------------------------------------------------------- files
say "Installing Kura into $PREFIX"
mkdir -p "$LIB" "$BIN" "$APPS" "$ICONS"
if [ "$DEV" = 1 ]; then
    CODE=$SRC
    rm -rf "$LIB/kura"
    note "Development mode: running straight from $SRC"
else
    CODE=$LIB
    rm -rf "$LIB/kura"
    cp -R "$SRC/kura" "$LIB/kura"
    find "$LIB/kura" -name __pycache__ -type d -prune -exec rm -rf {} +
    cp "$SRC/install.sh" "$LIB/install.sh"
fi

cat > "$BIN/kura" <<EOF
#!/bin/sh
# Kura launcher, written by install.sh
PYTHONPATH="$CODE\${PYTHONPATH:+:\$PYTHONPATH}" exec "$PYTHON" -m kura "\$@"
EOF
chmod +x "$BIN/kura"

cp "$SRC/kura/kura.svg" "$ICONS/kura.svg"
cat > "$APPS/kura.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Kura
GenericName=Game Library
Comment=One library for Steam, Epic, GOG, Amazon and Battle.net
Exec=$BIN/kura
Icon=kura
Categories=Game;
Keywords=games;steam;epic;gog;amazon;battle.net;launcher;
StartupWMClass=kura
Actions=tv;

[Desktop Action tv]
Name=TV mode
Exec=$BIN/kura --tv
EOF
have update-desktop-database && update-desktop-database "$APPS" >/dev/null 2>&1 || true
have gtk-update-icon-cache && gtk-update-icon-cache -q "$PREFIX/share/icons/hicolor" >/dev/null 2>&1 || true

# ---------------------------------------------------------------- optional pieces
say "Checking the things games need"
if have steam || [ -d "$HOME/.var/app/com.valvesoftware.Steam" ]; then
    note "Steam: found"
else
    case $PM in
        pacman) sys_install "Steam" steam || true ;;
        apt-get) sys_install "Steam" steam-installer || true ;;
        *) note "Steam is not installed. Get it from your distribution or Flathub (com.valvesoftware.Steam)." ;;
    esac
fi
if have umu-run; then
    note "umu-launcher (Proton for non-Steam games): found"
else
    case $PM in
        pacman) sys_install "umu-launcher (runs Windows games through Proton)" umu-launcher || true ;;
        *) note "umu-launcher is not installed; Epic, GOG, Amazon and Battle.net games need it."
           note "See https://github.com/Open-Wine-Components/umu-launcher/releases for packages." ;;
    esac
fi
if python3 -c 'import ctypes, ctypes.util, sys; sys.exit(0 if ctypes.util.find_library("SDL2") else 1)' 2>/dev/null \
   || [ -e /usr/lib/libSDL2-2.0.so.0 ] || [ -e /usr/lib64/libSDL2-2.0.so.0 ] || [ -e /usr/lib/x86_64-linux-gnu/libSDL2-2.0.so.0 ]; then
    note "SDL2 (controller support): found"
else
    case $PM in
        pacman)  sys_install "SDL2 (controller support)" sdl2-compat || true ;;
        apt-get) sys_install "SDL2 (controller support)" libsdl2-2.0-0 || true ;;
        dnf)     sys_install "SDL2 (controller support)" SDL2 || true ;;
        zypper)  sys_install "SDL2 (controller support)" libSDL2-2_0-0 || true ;;
        *) note "SDL2 is not installed; controllers will not work until it is." ;;
    esac
fi

say "Store backends for Epic, GOG and Amazon"
if [ "$(uname -m)" != x86_64 ]; then
    note "Skipped: prebuilt backends are only fetched for x86_64 here."
elif ask "Download legendary, gogdl and nile from their GitHub releases into $DATA/bin?"; then
    "$BIN/kura" --fetch-backends | sed 's/^/    /' || note "Download failed; run 'kura --fetch-backends' later."
else
    note "Skipped. Run 'kura --fetch-backends' whenever you want them."
fi

# ---------------------------------------------------------------- done
say "Kura is installed"
"$BIN/kura" --status | sed 's/^/    /' || true
echo
note "Start it from your app menu, or run: kura        (TV mode: kura --tv)"
case ":$PATH:" in
    *":$BIN:"*) ;;
    *) note "Note: $BIN is not on your PATH. Add it, or start Kura from the app menu." ;;
esac
note "To remove it later: sh $( [ "$DEV" = 1 ] && echo "$SRC" || echo "$LIB" )/install.sh --uninstall"
