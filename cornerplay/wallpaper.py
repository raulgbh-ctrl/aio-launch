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


def _ini(path):
    """Read a KDE config file into {section: {key: value}}. Section names keep KDE's inner brackets."""
    sections, cur = {}, None
    try:
        text = Path(path).read_text(errors="ignore")
    except OSError:
        return sections
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("[") and line.endswith("]"):
            cur = sections.setdefault(line[1:-1], {})
        elif cur is not None and "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            cur[k.strip()] = v.strip()
    return sections


def _kde_dark():
    glob_ = _ini(HOME / ".config/kdeglobals")
    if "dark" in glob_.get("General", {}).get("ColorScheme", "").lower():
        return True
    bg = glob_.get("Colors:Window", {}).get("BackgroundNormal", "")
    try:
        r, g, b = (int(x) for x in bg.split(",")[:3])
        return (r * 299 + g * 587 + b * 114) / 1000 < 128
    except ValueError:
        return False


def _kde_package(value):
    """A KDE wallpaper may be a package folder (or just its name); pick its biggest image."""
    value = _uri(value).rstrip("/")
    if os.path.isfile(value):
        return value
    dirs = [value] if os.path.isabs(value) else [
        str(HOME / ".local/share/wallpapers" / value), f"/usr/local/share/wallpapers/{value}",
        f"/usr/share/wallpapers/{value}"]
    for d in dirs:
        if not os.path.isdir(d):
            continue
        subs = ["contents/images_dark", "contents/images"] if _kde_dark() else ["contents/images"]
        for sub in subs + ["contents/images", "."]:
            files = [f for f in glob.glob(os.path.join(d, sub, "*")) if _ok(f)]
            if files:
                def size(f):
                    m = re.match(r"(\d+)x(\d+)", os.path.basename(f))
                    return (int(m.group(1)) * int(m.group(2)) if m else 0, os.path.getsize(f))
                return max(files, key=size)
    return ""


def _kde_default():
    """The wallpaper Plasma shows when the user never picked one: the look-and-feel's default."""
    lnf = _ini(HOME / ".config/kdeglobals").get("KDE", {}).get("LookAndFeelPackage", "org.kde.breeze.desktop")
    for base in (HOME / ".local/share", Path("/usr/local/share"), Path("/usr/share")):
        image = _ini(base / "plasma/look-and-feel" / lnf / "contents/defaults").get("Wallpaper", {}).get("Image")
        if image:
            return image
    return "Next"


def _kde():
    """Yield the wallpaper of the desktop the user is looking at, best match first."""
    conf = _ini(HOME / ".config/plasma-org.kde.plasma.desktop-appletsrc")
    if not conf:
        return
    activity = _ini(HOME / ".config/kactivitymanagerdrc").get("main", {}).get("currentActivity", "")
    desktops = []
    for name, keys in conf.items():
        m = re.fullmatch(r"Containments\]\[(\d+)", name)
        if not m:
            continue
        plugin = keys.get("wallpaperplugin", "")
        if not plugin:
            continue  # panels have no wallpaper
        general = conf.get(f"{name}][Wallpaper][{plugin}][General", {})
        image = general.get("Image", "")
        if plugin != "org.kde.image":
            continue  # slideshow, colour, maps etc.: no single image to read
        rank = (keys.get("activityId", "") == activity if activity else True,
                keys.get("lastScreen", "") == "0", -int(m.group(1)))
        desktops.append((rank, image or _kde_default()))
    for _, image in sorted(desktops, reverse=True):
        yield "KDE", _kde_package(image)


def _candidates():
    """Yield (source, path) guesses, most specific first."""
    on_kde = "KDE" in os.environ.get("XDG_CURRENT_DESKTOP", "").upper()
    if on_kde:
        yield from _kde()
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
    # KDE Plasma (first on a KDE session, so a stray GNOME setting can't win there)
    if not on_kde:
        yield from _kde()
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
             HOME / ".config/plasma-org.kde.plasma.desktop-appletsrc", HOME / ".config/kactivitymanagerdrc",
             HOME / ".config/hypr/hyprpaper.conf",
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


def backdrop(path, width=480):
    """A small, soft, muted copy of the wallpaper for behind the window, made once and cached.
    Blurring it ahead of time costs a few milliseconds here instead of a full-window GPU blur
    (and its buffers, ~65 MB) for as long as the window is open."""
    from PySide6.QtCore import QSize, Qt
    from PySide6.QtGui import QColor, QImage, QImageReader
    from .config import CACHE_DIR
    try:
        st = os.stat(path)
    except OSError:
        return ""
    import hashlib
    tag = hashlib.sha1(f"{path}|{st.st_mtime_ns}|{st.st_size}|{width}".encode()).hexdigest()[:16]
    out = CACHE_DIR / f"backdrop-{tag}.jpg"
    if out.exists():
        return str(out)
    reader = QImageReader(path)
    size = reader.size()
    if size.isValid() and size.width() > 0:  # JPEG decodes straight at a small size: fast
        reader.setScaledSize(QSize(256, max(1, round(256 * size.height() / size.width()))))
    img = reader.read()
    if img.isNull():
        return ""
    h = max(1, round(width * img.height() / img.width()))
    # Shrinking hard then growing back smoothly, twice, is a cheap, even blur. The colours are
    # muted while it is tiny (the window's own palette carries the colour), so it stays quick.
    img = img.scaled(24, max(1, round(24 * h / width)), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    img = img.scaled(width, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    img = img.scaled(48, max(1, round(48 * h / width)), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    img = img.convertToFormat(QImage.Format_RGB32)
    for y in range(img.height()):
        for x in range(img.width()):
            c = QColor(img.pixel(x, y))
            g = (c.red() * 30 + c.green() * 59 + c.blue() * 11) // 100
            img.setPixel(x, y, QColor((c.red() + 3 * g) // 4, (c.green() + 3 * g) // 4, (c.blue() + 3 * g) // 4).rgb())
    img = img.scaled(width, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    for old in CACHE_DIR.glob("backdrop-*.jpg"):  # one at a time is enough
        try:
            old.unlink()
        except OSError:
            pass
    img.save(str(out), "JPG", 88)
    return str(out)

