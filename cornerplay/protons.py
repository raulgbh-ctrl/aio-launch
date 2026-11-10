"""Every Proton build on the PC, wherever it was installed.

Looks in Steam (native, Flatpak, Snap; every Steam library's steamapps/common for Valve's
builds; compatibilitytools.d, where ProtonUp-Qt / ProtonPlus / Cornerplay put GE-Proton),
Heroic and Lutris (native and Flatpak), umu-launcher, system packages, and the folders in
STEAM_EXTRA_COMPAT_TOOLS_PATHS. A folder counts as a Proton build when it has a `proton`
script in it.

Each build carries `valve` (the name Steam uses for its own builds, like "proton_9") and
`tool` (the name in its compatibilitytool.vdf, which Steam needs to load a custom build);
steamcompat decides which of them a particular Steam installation can use.
"""
import glob
import os
import re

from . import vdf
from .config import HOME

FLATPAK = HOME / ".var/app"
STEAM_ROOTS = [HOME / ".local/share/Steam", HOME / ".steam/steam", HOME / ".steam/root",
               HOME / ".steam/debian-installation", FLATPAK / "com.valvesoftware.Steam/.local/share/Steam",
               FLATPAK / "com.valvesoftware.Steam/data/Steam", HOME / "snap/steam/common/.local/share/Steam"]
# Folders Steam reads compatibility tools from, besides <steam root>/compatibilitytools.d.
SYSTEM_TOOLS = ["/usr/share/steam/compatibilitytools.d", "/usr/local/share/steam/compatibilitytools.d"]
OTHER = [  # (glob, source label)
    (HOME / ".config/heroic/tools/proton/*", "Heroic"),
    (FLATPAK / "com.heroicgameslauncher.hgl/config/heroic/tools/proton/*", "Heroic"),
    (HOME / ".local/share/lutris/runners/proton/*", "Lutris"),
    (FLATPAK / "net.lutris.Lutris/data/lutris/runners/proton/*", "Lutris"),
    (HOME / ".local/share/umu/compatibilitytools/*", "umu"),
    (HOME / ".local/share/bottles/runners/*", "Bottles"),
    ("/opt/proton*", "system"), ("/usr/lib/proton*", "system"),
]
# Valve's folder names in steamapps/common -> the tool name Steam's per-game setting uses.
VALVE_NAMES = [(r"^Proton - Experimental$", "proton_experimental"), (r"^Proton Hotfix$", "proton_hotfix"),
               (r"^Proton (\d+)\.(\d+)", None)]


def _valve_name(folder):
    for pattern, name in VALVE_NAMES:
        m = re.match(pattern, folder)
        if m:
            if name:
                return name
            major, minor = m.group(1), m.group(2)
            return f"proton_{major}" if int(major) >= 7 else f"proton_{major}{minor}"  # proton_63 for 6.3
    return ""


def _manifest(path):
    """(tool name, display name) from compatibilitytool.vdf, or ("", "")."""
    tools = (vdf.load(os.path.join(path, "compatibilitytool.vdf")).get("compatibilitytools") or {}).get("compat_tools") or {}
    for name, info in tools.items():
        if isinstance(info, dict):
            return name, info.get("display_name") or name
    return "", ""


def steam_roots():
    seen, out = set(), []
    for r in STEAM_ROOTS:
        real = os.path.realpath(r)
        if real not in seen and (os.path.isdir(os.path.join(real, "steamapps")) or os.path.isdir(os.path.join(real, "compatibilitytools.d"))):
            seen.add(real)
            out.append(real)
    return out


def _steam_libraries(root):
    libs = {root}
    folders = vdf.load(os.path.join(root, "steamapps", "libraryfolders.vdf")).get("libraryfolders", {})
    for entry in folders.values():
        if isinstance(entry, dict) and entry.get("path"):
            libs.add(os.path.realpath(entry["path"]))
    return sorted(libs)


def system_tool_dirs():
    """Folders every Steam installation reads custom tools from (besides its own)."""
    return SYSTEM_TOOLS + [p for p in os.environ.get("STEAM_EXTRA_COMPAT_TOOLS_PATHS", "").split(":") if p]


def find():
    """[{"path", "label", "source", "valve", "tool"}], newest-looking first per source."""
    found, seen = [], set()

    def add(path, source, _steam_visible=False):
        real = os.path.realpath(path)
        if real in seen or not os.path.isfile(os.path.join(real, "proton")):
            return
        seen.add(real)
        folder = os.path.basename(real.rstrip("/"))
        tool, display = _manifest(real)
        found.append({"path": real, "label": (display or folder).replace("-x86_64", ""), "source": source,
                      "valve": _valve_name(folder) if source == "Steam" else "", "tool": tool})

    for root in steam_roots():
        flatpak = "/.var/app/" in root
        for lib in _steam_libraries(root):  # Valve's own builds
            for p in sorted(glob.glob(os.path.join(lib, "steamapps", "common", "Proton*")), reverse=True):
                add(p, "Steam", True)
        for p in sorted(glob.glob(os.path.join(root, "compatibilitytools.d", "*")), reverse=True):
            add(p, "Steam Flatpak" if flatpak else "Steam custom", True)
    for d in system_tool_dirs():
        for p in sorted(glob.glob(os.path.join(d, "*")), reverse=True):
            add(p, "system", True)
    for pattern, source in OTHER:
        for p in sorted(glob.glob(str(pattern)), reverse=True):
            add(p, source, False)
    return found
