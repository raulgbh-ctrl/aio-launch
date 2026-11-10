"""Add Cornerplay to Steam as a non-Steam game, with its own artwork, so it shows up
in Steam's library, Big Picture and the Steam Deck's Game Mode (gamescope).

Steam keeps non-Steam games in userdata/<account>/config/shortcuts.vdf (binary
KeyValues) and their pictures in userdata/<account>/config/grid/. Steam rewrites
shortcuts.vdf when it exits, so changes are only safe while Steam is closed.
"""
import os
import shlex
import shutil
import struct
import subprocess
import time
import zlib
from pathlib import Path

from .config import HOME

NAME = "Cornerplay"
ROOTS = [HOME / ".local/share/Steam", HOME / ".steam/steam", HOME / ".steam/root",
         HOME / ".var/app/com.valvesoftware.Steam/.local/share/Steam",
         HOME / ".var/app/com.valvesoftware.Steam/data/Steam"]


# ---------------------------------------------------------------- binary KeyValues
def _cstr(buf, i):
    end = buf.index(b"\0", i)
    return buf[i:end].decode("utf-8", "replace"), end + 1


def _read_map(buf, i):
    out = {}
    while True:
        kind = buf[i]
        i += 1
        if kind == 0x08:
            return out, i
        key, i = _cstr(buf, i)
        if kind == 0x00:
            out[key], i = _read_map(buf, i)
        elif kind == 0x01:
            out[key], i = _cstr(buf, i)
        elif kind == 0x02:
            out[key] = struct.unpack_from("<i", buf, i)[0]
            i += 4
        elif kind == 0x07:
            out[key] = struct.unpack_from("<Q", buf, i)[0]
            i += 8
        else:
            raise ValueError(f"unknown value type {kind:#x} in shortcuts.vdf")


def loads(buf: bytes) -> dict:
    if not buf:
        return {"shortcuts": {}}
    data, _ = _read_map(buf, 0)
    return data


def _write_map(d: dict) -> bytes:
    out = bytearray()
    for key, val in d.items():
        k = key.encode() + b"\0"
        if isinstance(val, dict):
            out += b"\x00" + k + _write_map(val)
        elif isinstance(val, bool) or isinstance(val, int):
            out += b"\x02" + k + struct.pack("<i", int(val) if -2**31 <= int(val) < 2**31 else int(val) - 2**32)
        else:
            out += b"\x01" + k + str(val).encode() + b"\0"
    return bytes(out) + b"\x08"


def dumps(data: dict) -> bytes:
    return _write_map(data) + b"\x08"


# ---------------------------------------------------------------- Steam layout
def steam_root():
    for r in ROOTS:
        if (r / "userdata").is_dir():
            return r.resolve()
    return None


def accounts():
    """userdata folders of the Steam accounts that have signed in on this PC."""
    root = steam_root()
    if not root:
        return []
    return [p for p in sorted((root / "userdata").iterdir())
            if p.is_dir() and p.name.isdigit() and p.name != "0"]


def steam_running():
    try:
        return subprocess.run(["pgrep", "-x", "steam"], capture_output=True).returncode == 0
    except OSError:
        return False


def in_game_mode():
    return os.environ.get("XDG_CURRENT_DESKTOP", "").lower() == "gamescope" or bool(os.environ.get("GAMESCOPE_WAYLAND_DISPLAY"))


def shortcut_id(exe: str, name: str) -> int:
    """Steam's id for a non-Steam game (also names its artwork files)."""
    return (zlib.crc32((exe + name).encode()) & 0xFFFFFFFF) | 0x80000000


def launcher_path():
    """The installed `cornerplay` command (falls back to running the module)."""
    local = HOME / ".local/bin/cornerplay"
    if local.exists():
        return str(local)
    return shutil.which("cornerplay")


OLD_NAMES = ("AIO Launch", "Kura")  # the app's earlier names: an old entry is updated, not doubled


def _find(shortcuts: dict, exe: str):
    old_exes = {str(HOME / ".local/bin/aiolaunch"), str(HOME / ".local/bin/kura")}
    for idx, sc in shortcuts.items():
        name = sc.get("AppName", sc.get("appname"))
        target = sc.get("Exe", sc.get("exe", "")).strip('"')
        launch = str(sc.get("LaunchOptions", ""))
        if (name == NAME or target == exe or name in OLD_NAMES or target in old_exes) and not launch.startswith("--play "):
            return idx
    return None


def status():
    """{"accounts": n, "added": n, "steam": bool, "running": bool, "gameMode": bool}"""
    exe = launcher_path() or ""
    accts = accounts()
    added = 0
    for acct in accts:
        f = acct / "config/shortcuts.vdf"
        try:
            if _find(loads(f.read_bytes()).get("shortcuts", {}), exe) is not None:
                added += 1
        except (OSError, ValueError):
            pass
    return {"accounts": len(accts), "added": added, "steam": steam_root() is not None,
            "running": steam_running(), "gameMode": in_game_mode()}


# ---------------------------------------------------------------- artwork
def make_artwork(folder: Path, sid: int, theme: dict):
    """Draw original artwork in the app's colours: grid (portrait + wide), hero, logo, icon."""
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QColor, QFont, QImage, QLinearGradient, QPainter, QPainterPath, QRadialGradient

    bg = QColor(theme.get("background", "#141218"))
    accent = QColor(theme.get("primary", "#d2bcfd"))
    second = QColor(theme.get("tertiary", theme.get("secondary", "#f0b7c6")))
    light = QColor(theme.get("onSurface", "#e7e0e8"))

    from PySide6.QtSvg import QSvgRenderer
    icon_svg = QSvgRenderer(str(Path(__file__).parent / "cornerplay.svg"))

    def mark(p, x, y, size):
        """The app icon (cornerplay.svg), the same one the desktop shows."""
        icon_svg.render(p, QRectF(x, y, size, size))

    def backdrop(p, w, h):
        g = QLinearGradient(0, 0, w, h)
        g.setColorAt(0, bg.lighter(135))
        g.setColorAt(1, bg.darker(160))
        p.fillRect(0, 0, w, h, g)
        for cx, cy, r, col in ((0.18, 0.22, 0.65, accent), (0.88, 0.85, 0.7, second)):
            glow = QRadialGradient(w * cx, h * cy, max(w, h) * r)
            c = QColor(col)
            c.setAlpha(70)
            glow.setColorAt(0, c)
            c.setAlpha(0)
            glow.setColorAt(1, c)
            p.fillRect(0, 0, w, h, glow)
        # a faint field of cover-shaped tiles
        tile_w = max(w, h) / 9
        p.setPen(Qt.NoPen)
        for row in range(-1, int(h / (tile_w * 1.4)) + 2):
            for col in range(-1, int(w / (tile_w * 1.15)) + 2):
                c = QColor(light)
                c.setAlpha(10 + ((row * 7 + col * 3) % 4) * 4)
                path = QPainterPath()
                path.addRoundedRect(QRectF(col * tile_w * 1.15 + (row % 2) * tile_w * 0.5,
                                           row * tile_w * 1.4, tile_w, tile_w * 1.3), tile_w * 0.12, tile_w * 0.12)
                p.fillPath(path, c)

    def word(p, rect, size, align=Qt.AlignCenter):
        f = QFont()
        f.setPixelSize(int(size))
        f.setWeight(QFont.Bold)
        p.setFont(f)
        p.setPen(light)
        p.drawText(rect, align, NAME)

    def canvas(w, h, transparent=False):
        img = QImage(w, h, QImage.Format_ARGB32_Premultiplied)
        img.fill(Qt.transparent if transparent else bg)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        return img, p

    folder.mkdir(parents=True, exist_ok=True)
    files = {}

    img, p = canvas(600, 900)                      # library grid, portrait
    backdrop(p, 600, 900)
    mark(p, 150, 230, 300)
    word(p, QRectF(0, 560, 600, 120), 64)
    p.end()
    files["portrait"] = folder / f"{sid}p.png"
    img.save(str(files["portrait"]))

    img, p = canvas(920, 430)                      # wide grid / recent games
    backdrop(p, 920, 430)
    mark(p, 70, 95, 240)
    word(p, QRectF(330, 0, 560, 430), 72, Qt.AlignVCenter | Qt.AlignLeft)
    p.end()
    files["wide"] = folder / f"{sid}.png"
    img.save(str(files["wide"]))

    img, p = canvas(1920, 620)                     # hero: the big background on the game page
    backdrop(p, 1920, 620)
    p.end()
    files["hero"] = folder / f"{sid}_hero.png"
    img.save(str(files["hero"]))

    img, p = canvas(1280, 360, transparent=True)   # logo drawn over the hero
    mark(p, 40, 30, 300)
    word(p, QRectF(360, 0, 920, 360), 120, Qt.AlignVCenter | Qt.AlignLeft)
    p.end()
    files["logo"] = folder / f"{sid}_logo.png"
    img.save(str(files["logo"]))

    img, p = canvas(256, 256, transparent=True)    # icon
    mark(p, 0, 0, 256)
    p.end()
    files["icon"] = folder / f"{sid}_icon.png"
    img.save(str(files["icon"]))
    return files


# ---------------------------------------------------------------- add / remove
def add(theme: dict, launch_options="--tv"):
    """Add or update the shortcut and artwork for every Steam account. Steam must be closed.
    Returns the number of accounts updated."""
    exe = launcher_path()
    if not exe:
        raise RuntimeError("Could not find the installed cornerplay command")
    if steam_running():
        raise RuntimeError("Steam is running; close it first")
    accts = accounts()
    if not accts:
        raise RuntimeError("Sign in to Steam once first, so it has an account folder to add to")
    sid = shortcut_id(f'"{exe}"', NAME)
    signed = sid - 2**32
    for acct in accts:
        cfg = acct / "config"
        cfg.mkdir(parents=True, exist_ok=True)
        f = cfg / "shortcuts.vdf"
        try:
            data = loads(f.read_bytes()) if f.exists() else {"shortcuts": {}}
        except ValueError:
            continue  # never overwrite a file we could not read
        shortcuts = data.setdefault("shortcuts", {})
        art = make_artwork(cfg / "grid", sid, theme)
        idx = _find(shortcuts, exe)
        if idx is None:
            idx = str(max([int(k) for k in shortcuts if k.isdigit()] + [-1]) + 1)
        old = shortcuts.get(idx, {})
        shortcuts[idx] = {
            "appid": signed,
            "AppName": NAME,
            "Exe": f'"{exe}"',
            "StartDir": f'"{os.path.dirname(exe)}"',
            "icon": str(art["icon"]),
            "ShortcutPath": "",
            "LaunchOptions": launch_options,
            "IsHidden": 0,
            "AllowDesktopConfig": 1,
            "AllowOverlay": 1,
            "OpenVR": 0,
            "Devkit": 0,
            "DevkitGameID": "",
            "DevkitOverrideAppID": 0,
            "LastPlayTime": old.get("LastPlayTime", 0),
            "FlatpakAppID": "",
            "tags": {"0": "Launchers"},
        }
        if f.exists():
            shutil.copy2(f, cfg / "shortcuts.vdf.cornerplay-backup")
        tmp = cfg / "shortcuts.vdf.tmp"
        tmp.write_bytes(dumps(data))
        os.replace(tmp, f)
    return len(accts)


def close_steam(timeout=40):
    """Ask Steam to quit and wait for it. Returns True when it is closed."""
    if not steam_running():
        return True
    from .stores.steam import Steam
    client = Steam().client()
    if client:
        subprocess.run([*client, "-shutdown"], capture_output=True, timeout=30)
    end = time.time() + timeout
    while time.time() < end:
        if not steam_running():
            time.sleep(1)  # let it finish writing its files
            return True
        time.sleep(0.5)
    return False


def start_steam():
    from .stores.steam import Steam
    client = Steam().client()
    if client:
        subprocess.Popen(client, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def add_with_restart(theme: dict):
    """Close Steam if needed, add the shortcut, then start Steam again if it was open."""
    if in_game_mode():
        raise RuntimeError("Switch to Desktop Mode to add Cornerplay to Steam")
    was_running = steam_running()
    if was_running and not close_steam():
        raise RuntimeError("Steam did not close; quit it yourself and try again")
    try:
        return add(theme)
    finally:
        if was_running:
            start_steam()
