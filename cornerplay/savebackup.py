"""Save backups: zip a game's saves before it starts, keep the last few, put one back on demand.

Where a game keeps its saves comes from Ludusavi's open manifest (github.com/mtkennerly/
ludusavi-manifest), downloaded once a week and boiled down to a small index. Paths like
<winAppData> point into the game's Proton prefix for Windows games (Cornerplay's own prefixes,
or Steam's compatdata), and into your home for Linux versions.

Backups: ~/.local/share/cornerplay/backups/<game>/<date>.zip, each with a list of where every
file came from. Restoring first backs up what is there now, so a restore can be undone too.
"""
import glob
import hashlib
import json
import os
import re
import time
import zipfile

from .config import CACHE_DIR, DATA_DIR, HOME, read_json, settings, write_json
from .net import requests

MANIFEST_URL = "https://raw.githubusercontent.com/mtkennerly/ludusavi-manifest/master/data/manifest.yaml"
INDEX = CACHE_DIR / "save_index.json"
BACKUPS = DATA_DIR / "backups"
INDEX_TTL = 7 * 86400


def _norm(title):
    t = title.lower().replace("™", "").replace("®", "").replace("&", "and")
    return re.sub(r"[^a-z0-9]+", "", t)


# --- the manifest, boiled down -----------------------------------------------------------
_index = None


def build_index():
    """Download the manifest and keep only what Cornerplay needs: per game its save paths
    (with the OS each is for) and its Steam id. Needs PyYAML. Returns an error or ""."""
    try:
        import yaml
    except ImportError:
        return "Save backups need PyYAML (python-yaml)"
    try:
        r = requests.get(MANIFEST_URL, timeout=120)
        r.raise_for_status()
    except requests.RequestException as e:
        return f"Could not download the save locations: {e}"
    loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
    data = yaml.load(r.content, Loader=loader) or {}
    games, steam = {}, {}
    for name, entry in data.items():
        if not isinstance(entry, dict):
            continue
        files = []
        for path, info in (entry.get("files") or {}).items():
            info = info or {}
            tags = info.get("tags") or []
            if tags and "save" not in tags and "config" not in tags:
                continue
            oses = sorted({w.get("os") for w in info.get("when") or [] if isinstance(w, dict) and w.get("os")})
            files.append([path, oses])
        if files:
            games[_norm(name)] = {"name": name, "files": files}
            sid = (entry.get("steam") or {}).get("id")
            if sid:
                steam[str(sid)] = _norm(name)
    write_json(INDEX, {"t": time.time(), "games": games, "steam": steam})
    global _index
    _index = None
    return ""


def index():
    global _index
    if _index is None:
        _index = read_json(INDEX) or {}
    return _index


def index_is_old():
    return time.time() - (index().get("t") or 0) > INDEX_TTL


def entry_for(game, appid=None):
    idx = index()
    if appid and str(appid) in (idx.get("steam") or {}):
        return idx["games"].get(idx["steam"][str(appid)])
    return (idx.get("games") or {}).get(_norm(game.title))


# --- where the paths point -----------------------------------------------------------------
def _steam_prefix(appid):
    from .stores.steam import Steam
    s = Steam()
    for lib in s.library_dirs():
        p = os.path.join(lib, "steamapps", "compatdata", str(appid), "pfx")
        if os.path.isdir(p):
            return p
    return ""


def prefix_for(game, appid=None):
    """The Windows world a game runs in: its Proton prefix (drive_c lives inside)."""
    if game.store == "steam":
        return _steam_prefix(game.id)
    if game.store == "battlenet":
        return ""
    from .runner import prefix_path
    return prefix_path(game.store, game.id)


def paths_for(game, appid=None):
    """Existing save files and folders for a game: [path]."""
    e = entry_for(game, appid)
    if not e:
        return []
    native = game.extra.get("platform") == "linux" or (game.store == "custom" and game.extra.get("kind") == "linux")
    out = []
    if native:
        home = str(HOME)
        xdg_data = os.environ.get("XDG_DATA_HOME", os.path.join(home, ".local/share"))
        xdg_config = os.environ.get("XDG_CONFIG_HOME", os.path.join(home, ".config"))
        subs = {"<home>": home, "<xdgData>": xdg_data, "<xdgConfig>": xdg_config,
                "<base>": game.install_path or "", "<root>": os.path.dirname(game.install_path or ""),
                "<game>": os.path.basename(game.install_path or ""), "<osUserName>": os.environ.get("USER", "")}
        wanted = ("linux",)
    else:
        pfx = prefix_for(game, appid)
        if not pfx or not os.path.isdir(pfx):
            return []
        user = os.path.join(pfx, "drive_c", "users", "steamuser")
        subs = {"<home>": user, "<winAppData>": os.path.join(user, "AppData/Roaming"),
                "<winLocalAppData>": os.path.join(user, "AppData/Local"),
                "<winLocalAppDataLow>": os.path.join(user, "AppData/LocalLow"),
                "<winDocuments>": os.path.join(user, "Documents"),
                "<winPublic>": os.path.join(pfx, "drive_c", "users", "Public"),
                "<winProgramData>": os.path.join(pfx, "drive_c", "ProgramData"),
                "<winDir>": os.path.join(pfx, "drive_c", "windows"),
                "<base>": game.install_path or "", "<root>": os.path.dirname(game.install_path or ""),
                "<game>": os.path.basename(game.install_path or ""), "<osUserName>": "steamuser"}
        wanted = ("windows",)
    for path, oses in e["files"]:
        if oses and not any(o in wanted for o in oses):
            continue
        if "<storeUserId>" in path or "<storeGameId>" in path:
            path = path.replace("<storeUserId>", "*").replace("<storeGameId>", "*")
        if any(k in path and not v for k, v in subs.items()):
            continue
        for k, v in subs.items():
            path = path.replace(k, v)
        if "<" in path:
            continue  # a placeholder we do not know
        for hit in glob.glob(path, recursive=True):
            out.append(hit)
    return sorted(set(out))


def _files(paths):
    """Every file under the given files and folders."""
    for p in paths:
        if os.path.isfile(p):
            yield p
        elif os.path.isdir(p):
            for root, _d, fs in os.walk(p):
                for f in fs:
                    yield os.path.join(root, f)


def _folder(game):
    return BACKUPS / re.sub(r"[^A-Za-z0-9_.-]", "_", game.key)


# --- back up and restore ---------------------------------------------------------------------
def backup(game, appid=None, reason="before playing"):
    """Zip the game's saves. Returns the backup's name, "" when there is nothing (or nothing
    changed since the last one)."""
    files = list(_files(paths_for(game, appid)))
    if not files:
        return ""
    stamp = hashlib.sha1("".join(f"{f}{os.path.getsize(f)}{os.path.getmtime(f)}" for f in sorted(files)).encode()).hexdigest()
    folder = _folder(game)
    folder.mkdir(parents=True, exist_ok=True)
    last = read_json(folder / "last.json") or {}
    if last.get("stamp") == stamp and reason == "before playing":
        return ""
    name = time.strftime("%Y-%m-%d_%H-%M-%S") + ".zip"
    with zipfile.ZipFile(folder / name, "w", zipfile.ZIP_DEFLATED) as z:
        where = {}
        for i, f in enumerate(files):
            arc = f"files/{i}/{os.path.basename(f)}"
            z.write(f, arc)
            where[arc] = f
        z.writestr("cornerplay-saves.json", json.dumps({"game": game.title, "key": game.key, "made": time.time(),
                                                        "reason": reason, "files": where}))
    write_json(folder / "last.json", {"stamp": stamp, "name": name})
    keep = max(1, int(settings.get("backup_keep") or 5))
    zips = sorted(folder.glob("*.zip"))
    for old in zips[:-keep]:
        old.unlink()
    return name


def backups(game):
    """[{name, made, reason, files, size}] newest first."""
    out = []
    for z in sorted(_folder(game).glob("*.zip"), reverse=True):
        try:
            with zipfile.ZipFile(z) as f:
                meta = json.loads(f.read("cornerplay-saves.json"))
        except (OSError, KeyError, ValueError, zipfile.BadZipFile):
            continue
        out.append({"name": z.name, "made": meta.get("made", 0), "reason": meta.get("reason", ""),
                    "files": len(meta.get("files") or {}), "size": z.stat().st_size})
    return out


def restore(game, name, appid=None):
    """Put a backup's files back where they came from (after backing up what is there now)."""
    path = _folder(game) / name
    with zipfile.ZipFile(path) as z:
        meta = json.loads(z.read("cornerplay-saves.json"))
        contents = {arc: z.read(arc) for arc in meta.get("files") or {}}
    backup(game, appid, reason="before restoring " + name.removesuffix(".zip"))
    for arc, target in (meta.get("files") or {}).items():
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as f:
            f.write(contents[arc])
    return len(contents)


def folder_of(game):
    return str(_folder(game))
