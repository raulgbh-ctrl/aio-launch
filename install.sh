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
have() { command -v "$1" >/dev/null 2>&1; }
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

sys_install() {  # sys_install "what it is for" pkg...
    what=$1; shift
    case $PM in
        pacman)  cmd="sudo pacman -S --needed $([ "$YES" = 1 ] && echo --noconfirm) $*" ;;
        apt-get) cmd="sudo apt-get install -y $*" ;;
        dnf)     cmd="sudo dnf install -y $*" ;;
        zypper)  cmd="sudo zypper install -y $*" ;;
        *)       note "$what: install it with your package manager ($*)."; return 1 ;;
    esac
    if [ "${IMMUTABLE:-0}" = 1 ]; then
        note "$what: not installable on this read-only system; skipped."
        return 1
    fi
    if [ "$SYSTEM" = 1 ] && have sudo && ask "Install $what now? ($cmd)"; then
        $cmd && return 0
        note "That did not work; you can run it yourself later: $cmd"
        return 1
    fi
    note "$what is missing. To add it later: $cmd"
    return 1
}

# ---------------------------------------------------------------- Python side
banner
say "Checking Python libraries"
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

PYTHON=python3
if [ "$FORCE_VENV" = 0 ] && uses_system_python; then
    note "Using the system's PySide6 (Qt 6) and requests."
    rm -rf "$LIB/venv"
else
    if [ "$FORCE_VENV" = 0 ] && [ "$PM" = pacman ] && [ "$SYSTEM" = 1 ]; then
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
        "$LIB/venv/bin/python" -m pip install --quiet "PySide6-Essentials>=6.6" requests pyyaml \
            || die "Could not download PySide6. Check your internet connection and run this again."
        PYTHON=$LIB/venv/bin/python
    fi
fi

# ---------------------------------------------------------------- files
# Save backups read where games keep their saves from a YAML list (the private environment has it).
if [ "$PYTHON" = python3 ] && ! python3 -c "import yaml" >/dev/null 2>&1; then
    case $PM in
        pacman)  sys_install "PyYAML (for save backups)" python-yaml || true ;;
        apt-get) sys_install "PyYAML (for save backups)" python3-yaml || true ;;
        dnf)     sys_install "PyYAML (for save backups)" python3-pyyaml || true ;;
        zypper)  sys_install "PyYAML (for save backups)" python3-PyYAML || true ;;
        *) note "Optional: install PyYAML so save backups work." ;;
    esac
fi

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

# ---------------------------------------------------------------- optional pieces
say "Checking the things games need"
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

flatpak_steam() {
    have flatpak || return 1
    cmd="flatpak install --user -y flathub com.valvesoftware.Steam"
    ask "Install Steam from Flathub for your user? ($cmd)" || { note "Skipped. To add Steam later: $cmd"; return 0; }
    flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo \
        && $cmd && return 0
    note "That did not work; you can run it yourself later: $cmd"
}

if have steam || [ -d "$HOME/.var/app/com.valvesoftware.Steam" ]; then
    note "Steam: found"
else
    case $PM in
        pacman)  sys_install "Steam" steam || {
                     pacman -Si steam >/dev/null 2>&1 || note "pacman cannot find 'steam': enable the [multilib] repository in /etc/pacman.conf, run 'sudo pacman -Syu', then run this installer again."
                 } ;;
        apt-get) sys_install "Steam" steam-installer || flatpak_steam || true ;;
        *) flatpak_steam || note "Steam is not installed. Get it from your distribution, or install Flatpak and run this again." ;;
    esac
fi
if have umu-run || [ -x "$DATA/bin/umu-run" ]; then
    note "umu-launcher (Proton for non-Steam games): found"
else
    got=1
    [ "$PM" = pacman ] && [ "$SYSTEM" = 1 ] && sys_install "umu-launcher (runs Windows games through Proton)" umu-launcher && got=0
    if [ "$got" != 0 ]; then
        if ask "Download a portable umu-launcher into $DATA/bin instead (no root needed)?"; then
            if version=$(fetch_umu 2>/dev/null); then
                note "umu-launcher $version installed to $DATA/bin/umu-run"
            else
                note "Download failed. Epic, GOG, Amazon and Battle.net games need umu-launcher:"
                note "https://github.com/Open-Wine-Components/umu-launcher/releases"
            fi
        else
            note "Skipped. Epic, GOG, Amazon and Battle.net games will not start without umu-launcher."
        fi
    fi
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

# Qt from pip (the private environment) needs this small library on X11 sessions; desktops
# that ship their own Qt 6 have it, minimal Debian/Fedora installs sometimes do not.
if [ "$PYTHON" != python3 ] && [ "${XDG_SESSION_TYPE:-}" != wayland ] \
   && ! ls /usr/lib/libxcb-cursor.so.0 /usr/lib64/libxcb-cursor.so.0 /usr/lib/*/libxcb-cursor.so.0 >/dev/null 2>&1; then
    case $PM in
        pacman)  sys_install "the X11 cursor library Qt needs" xcb-util-cursor || true ;;
        apt-get) sys_install "the X11 cursor library Qt needs" libxcb-cursor0 || true ;;
        dnf)     sys_install "the X11 cursor library Qt needs" xcb-util-cursor || true ;;
        zypper)  sys_install "the X11 cursor library Qt needs" libxcb-cursor0 || true ;;
        *) note "If Cornerplay does not open on X11, install your distribution's libxcb-cursor package." ;;
    esac
fi

# Built-in sign-in window (Qt's web engine). Optional: without it, sign-in opens the normal browser.
if ! "$PYTHON" -c 'import PySide6.QtWebEngineQuick' >/dev/null 2>&1; then
    if [ "$PYTHON" = python3 ]; then
        case $PM in
            pacman)  sys_install "the built-in sign-in window (Qt web engine)" qt6-webengine || true ;;
            apt-get) sys_install "the built-in sign-in window (Qt web engine)" python3-pyside6.qtwebenginequick || true ;;
            dnf)     sys_install "the built-in sign-in window (Qt web engine)" python3-pyside6 qt6-qtwebengine || true ;;
            zypper)  sys_install "the built-in sign-in window (Qt web engine)" python3-pyside6 qt6-webengine || true ;;
            *) note "Optional: install Qt's web engine for the built-in sign-in window." ;;
        esac
    elif ask "Add the built-in sign-in window? It also links a Blizzard account to list your Battle.net games (downloads about 150 MB more)"; then
        # PySide6 6.12+ ships the web engine as its own package; older ones keep it in Addons.
        v=$("$PYTHON" -c 'import PySide6; print(PySide6.__version__)')
        "$PYTHON" -m pip install --quiet "PySide6-Addons==$v" >/dev/null 2>&1
        "$PYTHON" -c 'import PySide6.QtWebEngineQuick' >/dev/null 2>&1 \
            || "$PYTHON" -m pip install --quiet "PySide6-WebEngine==$v.*" >/dev/null 2>&1
        if "$PYTHON" -c 'import PySide6.QtWebEngineQuick' >/dev/null 2>&1; then
            note "Built-in sign-in window: added"
        else
            note "Could not add it; sign-in will use your browser instead."
        fi
    else
        note "Skipped. Sign-in will open your normal browser and ask you to paste a code; Blizzard account linking needs it."
    fi
else
    note "Built-in sign-in window: available"
fi

say "Store backends for Epic, GOG and Amazon"
if [ "$(uname -m)" != x86_64 ]; then
    note "Skipped: prebuilt backends are only fetched for x86_64 here."
elif ask "Download legendary, gogdl and nile from their GitHub releases into $DATA/bin?"; then
    "$BIN/cornerplay" --fetch-backends | sed 's/^/    /' || note "Download failed; run 'cornerplay --fetch-backends' later."
else
    note "Skipped. Run 'cornerplay --fetch-backends' whenever you want them."
fi

# ---------------------------------------------------------------- Steam / Game Mode
if ls "$HOME"/.local/share/Steam/userdata/[0-9]* "$HOME"/.var/app/com.valvesoftware.Steam/.local/share/Steam/userdata/[0-9]* >/dev/null 2>&1; then
    say "Steam library"
    if ask "Add Cornerplay itself to Steam so it shows in Game Mode? (Steam closes and reopens if it is open)"; then
        "$BIN/cornerplay" --add-to-steam | sed 's/^/    /' || note "Not added; use Settings > Library later."
    else
        note "Skipped. You can do it later in Settings > Library."
    fi
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
