#!/bin/sh
# Cornerplay installer for Linux. Installs for the current user only (no root needed
# for Cornerplay itself); system packages are optional and asked about first.
#
#   ./install.sh              install or update
#   ./install.sh --uninstall  remove Cornerplay (keeps settings, sign-ins and games)
#   ./install.sh --purge      remove Cornerplay and its settings/cache (never your games)
#
# Options: --yes (no questions, say yes)   --no-system (never call sudo)
#          --venv (always use a private Python environment)
#          --dev  (run from this folder instead of copying it; for development)
set -eu

SRC=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PREFIX=${PREFIX:-$HOME/.local}
LIB=$PREFIX/lib/cornerplay
BIN=$PREFIX/bin
APPS=$PREFIX/share/applications
ICONS=$PREFIX/share/icons/hicolor/scalable/apps
CONFIG=${XDG_CONFIG_HOME:-$HOME/.config}/cornerplay
DATA=${XDG_DATA_HOME:-$HOME/.local/share}/cornerplay
CACHE=${XDG_CACHE_HOME:-$HOME/.cache}/cornerplay

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

# The amber of the icon (256-colour terminals; plain text where colour is off).
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then AMBER='\033[38;5;214m'; BOLD='\033[1m'; OFF='\033[0m'; else AMBER=''; BOLD=''; OFF=''; fi
say()  { printf "${AMBER}${BOLD}==>${OFF} %s\n" "$*"; }
banner() { printf "\n  ${BOLD}Corner${OFF}${AMBER}${BOLD}play${OFF}  your cosy corner for every game you own\n\n"; }
note() { printf '    %s\n' "$*"; }
die()  { printf '\033[31merror:\033[0m %s\n' "$*" >&2; exit 1; }
# CORNERPLAY_PRETEND_MISSING="steam umu-run sdl ...": treat those as not installed (for testing).
have() { case " ${CORNERPLAY_PRETEND_MISSING:-} " in *" $1 "*) return 1 ;; esac; command -v "$1" >/dev/null 2>&1; }
missing_sdl() {
    case " ${CORNERPLAY_PRETEND_MISSING:-} " in *" sdl "*) return 0 ;; esac
    ! python3 -c 'import ctypes.util, sys; sys.exit(0 if ctypes.util.find_library("SDL2") else 1)' 2>/dev/null \
        && [ ! -e /usr/lib/libSDL2-2.0.so.0 ] && [ ! -e /usr/lib64/libSDL2-2.0.so.0 ] && [ ! -e /usr/lib/x86_64-linux-gnu/libSDL2-2.0.so.0 ]
}
ask() {  # ask "question" -> 0 for yes
    [ "$YES" = 1 ] && return 0
    [ -t 0 ] || return 1
    printf '    %s [Y/n] ' "$1"; read -r reply
    case $reply in ""|y|Y|yes|Yes) return 0 ;; *) return 1 ;; esac
}

# ---------------------------------------------------------------- uninstall
if [ "$MODE" != install ]; then
    say "Removing Cornerplay"
    rm -rf "$LIB"
    rm -f "$BIN/cornerplay" "$APPS/cornerplay.desktop" "$ICONS/cornerplay.svg" "$PREFIX"/share/icons/hicolor/*/apps/cornerplay.png
    rm -f "$BIN/aiolaunch"  # the old name's forwarding command
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
[ "$(uname -s)" = Linux ] || die "Cornerplay only runs on Linux."
[ -f "$SRC/cornerplay/__main__.py" ] || die "Run this from the Cornerplay folder (cornerplay/__main__.py not found next to install.sh)."
have python3 || die "python3 is required. Install it with your package manager and run this again."
python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' \
    || die "Python 3.10 or newer is required (found $(python3 -V 2>&1))."

# Immutable systems (SteamOS on the Steam Deck, Fedora Silverblue/Bazzite, …) keep system files
# read-only: never try the package manager there, install everything into the home folder.
IMMUTABLE=0
OS_ID=$(sed -n 's/^ID=//p' /etc/os-release 2>/dev/null | tr -d '"')
case $OS_ID in steamos|bazzite|silverblue|kinoite|aurora|bluefin|chimeraos) IMMUTABLE=1 ;; esac
[ -e /run/ostree-booted ] && IMMUTABLE=1
[ "${AIOLAUNCH_IMMUTABLE:-}" = 1 ] && IMMUTABLE=1   # for testing
if [ "$IMMUTABLE" = 1 ]; then
    SYSTEM=0
    note "This system's files are read-only (${OS_ID:-immutable}), so everything goes into your home folder."
fi

PM=
for candidate in pacman apt-get dnf zypper; do
    if have "$candidate"; then PM=$candidate; break; fi
done

pkg_for() {  # pkg_for <thing>: this distribution's package for it ("" when unknown)
    case "$1:$PM" in
        pyside:pacman) echo "pyside6 python-requests" ;;
        yaml:pacman) echo python-yaml ;;      yaml:apt-get) echo python3-yaml ;;
        yaml:dnf) echo python3-pyyaml ;;      yaml:zypper) echo python3-PyYAML ;;
        steam:pacman) echo steam ;;           steam:apt-get) echo steam-installer ;;
        umu:pacman) echo umu-launcher ;;
        sdl:pacman) echo sdl2-compat ;;       sdl:apt-get) echo libsdl2-2.0-0 ;;
        sdl:dnf) echo SDL2 ;;                 sdl:zypper) echo libSDL2-2_0-0 ;;
        xcb:pacman) echo xcb-util-cursor ;;   xcb:apt-get) echo libxcb-cursor0 ;;
        xcb:dnf) echo xcb-util-cursor ;;      xcb:zypper) echo libxcb-cursor0 ;;
        web:pacman) echo qt6-webengine ;;     web:apt-get) echo python3-pyside6.qtwebenginequick ;;
        web:dnf) echo "python3-pyside6 qt6-qtwebengine" ;;  web:zypper) echo "python3-pyside6 qt6-webengine" ;;
        *) echo "" ;;
    esac
}
pm_cmd() {  # the install command for these packages
    case $PM in
        pacman)  echo "sudo pacman -S --needed --noconfirm $*" ;;
        apt-get) echo "sudo apt-get install -y $*" ;;
        dnf)     echo "sudo dnf install -y $*" ;;
        zypper)  echo "sudo zypper install -y $*" ;;
    esac
}

# ---------------------------------------------------------------- what is needed
# Everything is worked out first and asked about once (Enter = all of it); system packages go
# in one package-manager call, so there is one password prompt.
banner
say "Looking at this PC"
uses_system_python() {
    probe=$(mktemp "${TMPDIR:-/tmp}/cornerplay-probe.XXXXXX.qml") || return 1
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

CAN_SUDO=0
[ "$SYSTEM" = 1 ] && [ -n "$PM" ] && have sudo && CAN_SUDO=1
PKGS=""; PKG_WHAT=""
want_pkg() {  # want_pkg <thing> "what it is for": queue the system package, if there is one
    p=$(pkg_for "$1")
    [ -n "$p" ] || return 1
    [ "$CAN_SUDO" = 1 ] || return 1
    PKGS="$PKGS $p"; PKG_WHAT="${PKG_WHAT:+$PKG_WHAT, }$2"
    return 0
}

SYSTEM_PY=0
[ "$FORCE_VENV" = 0 ] && uses_system_python && SYSTEM_PY=1
if [ "$SYSTEM_PY" = 0 ] && [ "$FORCE_VENV" = 0 ] && [ "$PM" = pacman ]; then
    want_pkg pyside "Qt for Python" && SYSTEM_PY=2   # 2: the system's, once installed
fi
if [ "$SYSTEM_PY" != 0 ] && ! python3 -c "import yaml" >/dev/null 2>&1; then
    want_pkg yaml "save backups" || true
fi

STEAM_FLATPAK=0
if ! have steam && [ ! -d "$HOME/.var/app/com.valvesoftware.Steam" ]; then
    want_pkg steam "Steam" || { have flatpak && STEAM_FLATPAK=1; }
fi

UMU_PORTABLE=0
if ! have umu-run && [ ! -x "$DATA/bin/umu-run" ]; then
    want_pkg umu "Proton for non-Steam games" || UMU_PORTABLE=1
fi

# Controller support is never optional: the system's SDL2 when it has one (or can get one),
# otherwise a private copy (`cornerplay --fetch-sdl`, no root).
if missing_sdl; then
    want_pkg sdl "controllers" || true
fi

if [ "$SYSTEM_PY" = 0 ] && [ "${XDG_SESSION_TYPE:-}" != wayland ] \
   && ! ls /usr/lib/libxcb-cursor.so.0 /usr/lib64/libxcb-cursor.so.0 /usr/lib/*/libxcb-cursor.so.0 >/dev/null 2>&1; then
    want_pkg xcb "Qt on X11" || true
fi

WEB_PIP=0
if [ "$SYSTEM_PY" = 1 ] && ! python3 -c 'import PySide6.QtWebEngineQuick' >/dev/null 2>&1; then
    want_pkg web "the built-in sign-in window" || true
elif [ "$SYSTEM_PY" = 2 ]; then
    want_pkg web "the built-in sign-in window" || true
elif [ "$SYSTEM_PY" = 0 ]; then
    WEB_PIP=1   # checked again once the private environment exists
fi

BACKENDS=0
[ "$(uname -m)" = x86_64 ] && BACKENDS=1
TO_STEAM=0
ls "$HOME"/.local/share/Steam/userdata/[0-9]* "$HOME"/.var/app/com.valvesoftware.Steam/.local/share/Steam/userdata/[0-9]* >/dev/null 2>&1 && TO_STEAM=1

# ---------------------------------------------------------------- one question
PKGS=$(echo $PKGS)  # tidy spaces
say "Cornerplay will set up"
[ "$SYSTEM_PY" = 0 ] && note "* Qt for Python in a private environment (about 200 MB)"
[ -n "$PKGS" ] && note "* System packages for $PKG_WHAT: $PKGS  (one password prompt)"
[ "$STEAM_FLATPAK" = 1 ] && note "* Steam from Flathub, for your user"
[ "$UMU_PORTABLE" = 1 ] && note "* umu-launcher (Proton for non-Steam games), portable, in $DATA/bin"
note "* Controller support (SDL2)"
[ "$WEB_PIP" = 1 ] && note "* The built-in sign-in window (about 150 MB)"
[ "$BACKENDS" = 1 ] && note "* Store tools for Epic, GOG and Amazon (legendary, gogdl, nile)"
[ "$TO_STEAM" = 1 ] && note "* Cornerplay in Steam, for Game Mode (Steam restarts if it is open)"
echo

ALL=0; ONE_BY_ONE=0
if ask "Go ahead with all of this?"; then
    ALL=1
elif ask "Choose one by one instead?"; then
    ONE_BY_ONE=1
else
    note "Only Cornerplay itself is installed; the rest can be added later (Health check in the app)."
fi
want() {  # want "question": yes when the answer above was "all", else ask (one by one) or no
    [ "$ALL" = 1 ] && return 0
    [ "$ONE_BY_ONE" = 1 ] && ask "$1" && return 0
    return 1
}

# ---------------------------------------------------------------- system packages
if [ -n "$PKGS" ] && want "Install the system packages ($PKGS)?"; then
    say "Installing system packages"
    cmd=$(pm_cmd $PKGS)
    if ! $cmd; then
        # One package can fail (on Arch, Steam needs the multilib repository): the others still go in.
        note "Some did not install; trying them one at a time."
        for p in $PKGS; do $(pm_cmd "$p") >/dev/null 2>&1 || note "Not installed: $p"; done
        if [ "$PM" = pacman ] && echo " $PKGS " | grep -q " steam " && ! pacman -Si steam >/dev/null 2>&1; then
            note "pacman cannot find 'steam': enable [multilib] in /etc/pacman.conf, run 'sudo pacman -Syu', then this installer again."
        fi
    fi
elif [ -n "$PKGS" ]; then
    note "Skipped. To add them later: $(pm_cmd $PKGS)"
fi

# ---------------------------------------------------------------- Python
PYTHON=python3
if [ "$FORCE_VENV" = 0 ] && uses_system_python; then
    note "Using the system's PySide6 (Qt 6) and requests."
    rm -rf "$LIB/venv"
else
    say "Setting up a private Python environment (downloads Qt, roughly 200 MB)"
    mkdir -p "$LIB"
    if ! python3 -m venv "$LIB/venv" 2>/dev/null; then
        if [ "$PM" = apt-get ] && [ "$CAN_SUDO" = 1 ]; then
            $(pm_cmd python3-venv) && python3 -m venv "$LIB/venv" || die "Could not create a Python environment (python3 -m venv failed)."
        else
            die "Could not create a Python environment (python3 -m venv failed)."
        fi
    fi
    "$LIB/venv/bin/python" -m pip install --quiet --upgrade pip
    "$LIB/venv/bin/python" -m pip install --quiet "PySide6-Essentials>=6.6" requests pyyaml \
        || die "Could not download PySide6. Check your internet connection and run this again."
    PYTHON=$LIB/venv/bin/python
    WEB_PIP=1   # the system's Qt did not come in after all: offer the sign-in window here
fi

# ---------------------------------------------------------------- files
say "Installing Cornerplay into $PREFIX"
mkdir -p "$LIB" "$BIN" "$APPS" "$ICONS"
if [ "$DEV" = 1 ]; then
    CODE=$SRC
    rm -rf "$LIB/cornerplay"
    note "Development mode: running straight from $SRC"
else
    CODE=$LIB
    rm -rf "$LIB/cornerplay"
    cp -R "$SRC/cornerplay" "$LIB/cornerplay"
    find "$LIB/cornerplay" -name __pycache__ -type d -prune -exec rm -rf {} +
    cp "$SRC/install.sh" "$LIB/install.sh"
fi

cat > "$BIN/cornerplay" <<EOF
#!/bin/sh
# Cornerplay launcher, written by install.sh
PYTHONPATH="$CODE\${PYTHONPATH:+:\$PYTHONPATH}" exec "$PYTHON" -m cornerplay "\$@"
EOF
chmod +x "$BIN/cornerplay"

# The app used to be called AIO Launch: take its place. Its menu entry, icons and copy
# go; `aiolaunch` stays as a command that forwards here, because games added to Steam
# before the rename run `aiolaunch --play ...`.
if [ -e "$BIN/aiolaunch" ] || [ -e "$APPS/aiolaunch.desktop" ] || [ -d "$PREFIX/lib/aiolaunch" ]; then
    rm -rf "$PREFIX/lib/aiolaunch"
    rm -f "$APPS/aiolaunch.desktop" "$ICONS/aiolaunch.svg" "$PREFIX"/share/icons/hicolor/*/apps/aiolaunch.png
    cat > "$BIN/aiolaunch" <<EOF
#!/bin/sh
# AIO Launch is now Cornerplay; this keeps older Steam shortcuts working.
exec "$BIN/cornerplay" "\$@"
EOF
    chmod +x "$BIN/aiolaunch"
    note "AIO Launch is now Cornerplay. Your settings and games come along."
fi

# The icon goes into the icon theme under its name, as SVG and as PNGs: Steam's
# "Add a Non-Steam Game" list and some panels do not draw SVG icons.
mkdir -p "$ICONS"
cp "$SRC/cornerplay/cornerplay.svg" "$ICONS/cornerplay.svg"
for png in "$SRC"/cornerplay/icons/app/cornerplay-*.png; do
    size=${png##*-}; size=${size%.png}
    mkdir -p "$PREFIX/share/icons/hicolor/${size}x${size}/apps"
    cp "$png" "$PREFIX/share/icons/hicolor/${size}x${size}/apps/cornerplay.png"
done
cat > "$APPS/cornerplay.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Cornerplay
GenericName=Game Library
Comment=Your cosy corner for every game you own: Steam, Epic, GOG, Amazon and Battle.net in one place
Exec=$BIN/cornerplay
Icon=cornerplay
Categories=Game;
Keywords=games;steam;epic;gog;amazon;battle.net;launcher;
StartupWMClass=cornerplay
Actions=tv;

[Desktop Action tv]
Name=TV mode
Exec=$BIN/cornerplay --tv
EOF
have update-desktop-database && update-desktop-database "$APPS" >/dev/null 2>&1 || true
have gtk-update-icon-cache && gtk-update-icon-cache -q -t "$PREFIX/share/icons/hicolor" >/dev/null 2>&1 || true
# KDE (the Steam Deck's desktop) keeps its own menu and icon cache.
have kbuildsycoca6 && kbuildsycoca6 >/dev/null 2>&1 || { have kbuildsycoca5 && kbuildsycoca5 >/dev/null 2>&1; } || true

# ---------------------------------------------------------------- the rest
fetch_umu() {  # portable umu-launcher (one Python zipapp) into Cornerplay's own bin folder
    mkdir -p "$DATA/bin"
    python3 - "$DATA/bin/umu-run" <<'EOF'
import io, json, os, sys, tarfile, urllib.request
dest = sys.argv[1]
api = "https://api.github.com/repos/Open-Wine-Components/umu-launcher/releases/latest"
req = urllib.request.Request(api, headers={"User-Agent": "cornerplay-installer"})
release = json.load(urllib.request.urlopen(req, timeout=30))
asset = next(a for a in release["assets"] if a["name"].endswith("-zipapp.tar"))
data = urllib.request.urlopen(asset["browser_download_url"], timeout=120).read()
digest = asset.get("digest") or ""
if digest.startswith("sha256:"):  # GitHub's checksum of the published file
    import hashlib
    if hashlib.sha256(data).hexdigest() != digest.split(":", 1)[1]:
        sys.exit("umu-launcher download was damaged or changed (checksum mismatch)")
with tarfile.open(fileobj=io.BytesIO(data)) as tar:
    member = next(m for m in tar.getmembers() if m.isfile() and os.path.basename(m.name) == "umu-run")
    payload = tar.extractfile(member).read()
with open(dest + ".part", "wb") as f:
    f.write(payload)
os.chmod(dest + ".part", 0o755)
os.replace(dest + ".part", dest)
print(release["tag_name"])
EOF
}


if [ "$STEAM_FLATPAK" = 1 ] && want "Install Steam from Flathub for your user?"; then
    flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo \
        && flatpak install --user -y flathub com.valvesoftware.Steam \
        || note "Steam did not install; try later: flatpak install --user flathub com.valvesoftware.Steam"
fi

if [ "$UMU_PORTABLE" = 1 ] && ! have umu-run && want "Download a portable umu-launcher into $DATA/bin?"; then
    if version=$(fetch_umu 2>/dev/null); then
        note "umu-launcher $version installed to $DATA/bin/umu-run"
    else
        note "umu-launcher did not download; Epic, GOG, Amazon and Battle.net games need it:"
        note "https://github.com/Open-Wine-Components/umu-launcher/releases"
    fi
fi

# Controller support: always, no question (the system's SDL2, else a private copy).
"$BIN/cornerplay" --fetch-sdl | sed 's/^/    /' || note "Controllers: SDL2 could not be set up; the app tries again when it starts."

if [ "$WEB_PIP" = 1 ] && ! "$PYTHON" -c 'import PySide6.QtWebEngineQuick' >/dev/null 2>&1 \
   && want "Add the built-in sign-in window (about 150 MB)?"; then
    # PySide6 6.12+ ships the web engine as its own package; older ones keep it in Addons.
    v=$("$PYTHON" -c 'import PySide6; print(PySide6.__version__)')
    "$PYTHON" -m pip install --quiet "PySide6-Addons==$v" >/dev/null 2>&1
    "$PYTHON" -c 'import PySide6.QtWebEngineQuick' >/dev/null 2>&1 \
        || "$PYTHON" -m pip install --quiet "PySide6-WebEngine==$v.*" >/dev/null 2>&1
    "$PYTHON" -c 'import PySide6.QtWebEngineQuick' >/dev/null 2>&1 \
        && note "Built-in sign-in window: added" || note "Could not add it; sign-in will use your browser instead."
fi

if [ "$BACKENDS" = 1 ] && want "Download legendary, gogdl and nile (Epic, GOG and Amazon) into $DATA/bin?"; then
    say "Store tools for Epic, GOG and Amazon"
    "$BIN/cornerplay" --fetch-backends | sed 's/^/    /' || note "Download failed; run 'cornerplay --fetch-backends' later."
fi

if [ "$TO_STEAM" = 1 ] && want "Add Cornerplay to Steam for Game Mode? (Steam closes and reopens if it is open)"; then
    "$BIN/cornerplay" --add-to-steam | sed 's/^/    /' || note "Not added; use Settings > Library later."
    note "To put your installed games into Steam with their artwork: Settings > Library > Add games to Steam."
fi

# ---------------------------------------------------------------- done
say "Cornerplay is installed"
"$BIN/cornerplay" --status | sed 's/^/    /' || true
echo
note "Start it from your app menu, or run: cornerplay        (TV mode: cornerplay --tv)"
case ":$PATH:" in
    *":$BIN:"*) ;;
    *) note "Note: $BIN is not on your PATH. Add it, or start Cornerplay from the app menu." ;;
esac
note "To remove it later: sh $( [ "$DEV" = 1 ] && echo "$SRC" || echo "$LIB" )/install.sh --uninstall"
