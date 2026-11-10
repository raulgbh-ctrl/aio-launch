"""Find the current desktop wallpaper on common Linux desktops and derive two colours from it."""
import configparser
import glob
import os
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlparse

from .config import HOME, read_json

IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".jxl", ".avif")


def _out(argv):
    if not shutil.which(argv[0]):
        return ""
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=3).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _uri(value):
    value = value.strip().strip("'\"")
    if value.startswith("file://"):
        value = unquote(urlparse(value).path)
    return os.path.expanduser(value)


def _ok(path):
    return bool(path) and os.path.isfile(path) and path.lower().endswith(IMAGE_EXT)


def _candidates():
    """Yield (source, path) guesses, most specific first."""
    # Ryoku
    state = read_json(HOME / ".local/state/ryoku/stage-walls.json") or {}
    yield "Ryoku", state.get("current", "")
    # swww / awww
    for tool in ("swww", "awww"):
        for m in re.finditer(r"image: (.+)$", _out([tool, "query"]), re.M):
            yield tool, m.group(1)
    # hyprpaper
    for line in _out(["hyprctl", "hyprpaper", "listactive"]).splitlines():
        if "=" in line:
            yield "hyprpaper", line.split("=", 1)[1]
    conf = HOME / ".config/hypr/hyprpaper.conf"
    if conf.is_file():
        for line in conf.read_text(errors="ignore").splitlines():
            if line.strip().startswith(("wallpaper", "path")) and "=" in line:
                yield "hyprpaper", line.split("=", 1)[1].split(",")[-1]
    # waypaper, wpaperd, nitrogen, feh
    wp = configparser.ConfigParser()
    if wp.read(HOME / ".config/waypaper/config.ini"):
        yield "waypaper", wp.get("Settings", "wallpaper", fallback="")
    for f in glob.glob(str(HOME / ".config/nitrogen/bg-saved.cfg")):
        for line in Path(f).read_text(errors="ignore").splitlines():
            if line.startswith("file="):
                yield "nitrogen", line[5:]
    fehbg = HOME / ".fehbg"
    if fehbg.is_file():
        for m in re.finditer(r"'([^']+)'", fehbg.read_text(errors="ignore")):
            yield "feh", m.group(1)
    # swaybg (from its command line)
    for pid in _out(["pgrep", "-x", "swaybg"]).split():
        try:
            args = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
            for i, a in enumerate(args):
                if a in (b"-i", b"--image") and i + 1 < len(args):
                    yield "swaybg", args[i + 1].decode()
        except OSError:
            pass
    # KDE Plasma
    plasma = HOME / ".config/plasma-org.kde.plasma.desktop-appletsrc"
    if plasma.is_file():
        for m in re.finditer(r"^Image=(.+)$", plasma.read_text(errors="ignore"), re.M):
            yield "KDE", _uri(m.group(1))
    # GNOME, Cinnamon, MATE, Budgie
    dark = "dark" in _out(["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"])
    keys = ["picture-uri-dark", "picture-uri"] if dark else ["picture-uri", "picture-uri-dark"]
    for schema in ("org.gnome.desktop.background", "org.cinnamon.desktop.background"):
        for key in keys:
            yield "GNOME", _uri(_out(["gsettings", "get", schema, key]))
    yield "MATE", _uri(_out(["gsettings", "get", "org.mate.background", "picture-filename"]))
    # Xfce
    for prop in _out(["xfconf-query", "-c", "xfce4-desktop", "-l"]).splitlines():
        if prop.endswith("last-image"):
            yield "Xfce", _out(["xfconf-query", "-c", "xfce4-desktop", "-p", prop])


def watch_paths():
    """Files and folders that change when the wallpaper changes, on the common desktops."""
    paths = [HOME / ".local/state/ryoku/stage-walls.json", HOME / ".config/dconf/user",
             HOME / ".config/plasma-org.kde.plasma.desktop-appletsrc", HOME / ".config/hypr/hyprpaper.conf",
             HOME / ".config/waypaper/config.ini", HOME / ".config/nitrogen/bg-saved.cfg", HOME / ".fehbg",
             HOME / ".config/xfce4/xfconf/xfce-perchannel-xml/xfce4-desktop.xml"]
    out = []
    for p in paths:
        if p.exists():
            out.append(str(p))
        if p.parent.is_dir():
            out.append(str(p.parent))  # editors often replace the file, which drops a file watch
    return sorted(set(out))


def find():
    """Return (source, absolute path) of the current wallpaper, or ("", "")."""
    for source, path in _candidates():
        path = _uri(path or "")
        if _ok(path):
            return source, os.path.realpath(path)
    return "", ""


def colours(path):
    """(background, accent) hex colours picked from the image, or None."""
    from PySide6.QtGui import QColor, QImage
    img = QImage(path)
    if img.isNull():
        return None
    img = img.scaled(64, 64)
    buckets = {}
    total = [0.0, 0.0, 0.0]
    n = 0
    for y in range(img.height()):
        for x in range(img.width()):
            c = QColor(img.pixel(x, y))
            r, g, b = c.red(), c.green(), c.blue()
            total[0] += r
            total[1] += g
            total[2] += b
            n += 1
            h, s, v, _ = c.getHsv()
            if s < 70 or v < 70 or h < 0:
                continue
            key = h // 15
            weight = (s / 255) * (v / 255)
            hue_sum, count, sat, val = buckets.get(key, (0.0, 0.0, 0.0, 0.0))
            buckets[key] = (hue_sum + h * weight, count + weight, sat + s * weight, val + v * weight)
    if not n:
        return None
    avg = QColor(int(total[0] / n), int(total[1] / n), int(total[2] / n))
    if buckets:
        hue_sum, count, sat, val = max(buckets.values(), key=lambda b: b[1])
        hue = int(hue_sum / count) % 360
        sat = int(min(255, max(110, sat / count)))
    else:
        hue, sat = max(avg.hsvHue(), 0), 40
    accent = QColor.fromHsl(hue, min(sat, 200), 190)
    bg_hue = hue if buckets else max(avg.hsvHue(), 0)
    background = QColor.fromHsl(bg_hue, min(60, sat // 3), 22)
    return background.name(), accent.name()
