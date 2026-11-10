"""Bring games that are already on disk into Cornerplay, instead of downloading them again.

- a folder: GOG games inside it (goggame-<id>.info or a Linux version's gameinfo) are found
  from then on (the folder joins library_dirs)
- an Epic or Amazon game's folder: `legendary import` / `nile import` with the game chosen
- Heroic's installs: read its installed lists and import each game (native and Flatpak Heroic)
"""
import glob
import json
import os

from .config import HOME, read_json, settings
from .stores.base import run

HEROIC_DIRS = [HOME / ".config/heroic", HOME / ".var/app/com.heroicgameslauncher.hgl/config/heroic"]


def gog_in(folder):
    """GOG game folders in folder (itself, or one level down): [(game id, path)]."""
    found = []
    for pattern, linux in (("goggame-*.info", False), ("gameinfo", True)):
        for base in (folder, os.path.join(folder, "*")):
            for f in glob.glob(os.path.join(base, pattern)):
                try:
                    if linux:
                        lines = open(f, errors="replace").read().splitlines()
                        gid = lines[4].strip() if len(lines) >= 5 else ""
                    else:
                        info = json.load(open(f))
                        gid = str(info.get("gameId", ""))
                        if gid != str(info.get("rootGameId", gid)):
                            continue  # a DLC's info file
                except (OSError, ValueError):
                    continue
                if gid.isdigit():
                    found.append((gid, os.path.dirname(f)))
    return list(dict(found).items())


def add_library_dir(path):
    dirs = [d for d in settings.get("library_dirs") or [] if isinstance(d, str)]
    if path not in dirs:
        settings.set("library_dirs", dirs + [path])


def import_gog(folder):
    """Returns how many GOG games were found (their parent folders now get scanned)."""
    games = gog_in(folder)
    for _gid, path in games:
        add_library_dir(os.path.dirname(path))
    return len(games)


def import_epic(legendary, app_name, folder):
    r = run([legendary, "import", app_name, folder, "--disable-check"], timeout=300)
    return r.returncode == 0, (r.stderr or r.stdout or "").strip().splitlines()[-1:] or [""]


def import_amazon(nile, gid, folder):
    r = run([nile, "import", gid, "--path", folder], timeout=300)
    return r.returncode == 0, (r.stderr or r.stdout or "").strip().splitlines()[-1:] or [""]


def heroic_installs():
    """What Heroic installed: [{"store", "id", "title", "path"}] (Epic, GOG, Amazon)."""
    out = []
    for base in HEROIC_DIRS:
        epic = read_json(base / "legendaryConfig/legendary/installed.json") or {}
        for app, e in epic.items() if isinstance(epic, dict) else []:
            if isinstance(e, dict) and e.get("install_path") and not e.get("is_dlc"):
                out.append({"store": "epic", "id": app, "title": e.get("title", app), "path": e["install_path"]})
        gog = (read_json(base / "gog_store/installed.json") or {}).get("installed") or []
        for e in gog:
            if isinstance(e, dict) and e.get("install_path") and e.get("appName"):
                out.append({"store": "gog", "id": str(e["appName"]), "title": e.get("title", ""), "path": e["install_path"]})
        amazon = read_json(base / "nile_config/nile/installed.json") or []
        for e in amazon if isinstance(amazon, list) else []:
            if isinstance(e, dict) and e.get("path") and e.get("id"):
                out.append({"store": "amazon", "id": e["id"], "title": e.get("title", ""), "path": e["path"]})
    return [g for g in out if os.path.isdir(g["path"])]
