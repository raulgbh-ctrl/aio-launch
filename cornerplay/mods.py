"""Mods: find, install, switch on and off, and keep profiles of mods for supported games.

Where mods come from:
- Thunderstore (thunderstore.io) for Unity games modded with BepInEx (Valheim, Lethal Company,
  Risk of Rain 2...): open search and downloads; a mod's dependencies (BepInEx itself first)
  come with it.
- Nexus Mods for Stardew Valley (SMAPI), Skyrim Special Edition and Fallout 4 (the Data folder
  and plugins.txt) and Cyberpunk 2077 (the game folder). Searching needs nothing; downloading
  needs your free Nexus API key. Premium accounts download straight away; free accounts press
  "Mod Manager Download" on the mod's Nexus page, which hands Cornerplay an nxm:// link.

How mods are kept: every mod is unpacked once into its own folder under
~/.local/share/cornerplay/mods/<game>/mods/<mod>/, laid out as it goes into the game folder.
"Deploying" copies (hard-links when it can) the enabled mods of the active profile into the game
folder, later ones winning; game files a mod replaced are kept aside and put back when it is
switched off. Cornerplay notes every file it placed, so switching off removes exactly those.
Nothing is written outside the game's folder, except Bethesda games' plugins.txt in the prefix.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import xml.etree.ElementTree as ET
import zipfile

from .config import DATA_DIR, CONFIG_DIR, read_json, write_json, write_private
from .net import requests

ROOT = DATA_DIR / "mods"
NEXUS_KEY_FILE = CONFIG_DIR / "nexus_auth.json"
TS = "https://thunderstore.io"
NEXUS_API = "https://api.nexusmods.com"
UA = {"User-Agent": "Cornerplay (Linux game launcher)"}
_lock = threading.RLock()

# Games Cornerplay can mod, matched to the library by title (covers.norm) or Steam app id.
# kind: bepinex | smapi | bethesda | cyberpunk
GAMES = {
    "valheim": {"name": "Valheim", "appid": "892970", "source": "thunderstore", "community": "valheim"},
    "lethalcompany": {"name": "Lethal Company", "appid": "1966720", "source": "thunderstore", "community": "lethal-company"},
    "riskofrain2": {"name": "Risk of Rain 2", "appid": "632360", "source": "thunderstore", "community": "riskofrain2"},
    "contentwarning": {"name": "Content Warning", "appid": "2881650", "source": "thunderstore", "community": "content-warning"},
    "dysonsphereprogram": {"name": "Dyson Sphere Program", "appid": "1366540", "source": "thunderstore", "community": "dyson-sphere-program"},
    "repo": {"name": "R.E.P.O.", "appid": "3241660", "source": "thunderstore", "community": "repo"},
    "peak": {"name": "PEAK", "appid": "3527290", "source": "thunderstore", "community": "peak"},
    "rounds": {"name": "ROUNDS", "appid": "1557740", "source": "thunderstore", "community": "rounds"},
    "gtfo": {"name": "GTFO", "appid": "493520", "source": "thunderstore", "community": "gtfo"},
    "inscryption": {"name": "Inscryption", "appid": "1092790", "source": "thunderstore", "community": "inscryption"},
    "sunkenland": {"name": "Sunkenland", "appid": "2080690", "source": "thunderstore", "community": "sunkenland"},
    "straftat": {"name": "STRAFTAT", "appid": "2386720", "source": "thunderstore", "community": "straftat"},
    "ultrakill": {"name": "ULTRAKILL", "appid": "1229490", "source": "thunderstore", "community": "ultrakill"},
    "bombrushcyberfunk": {"name": "Bomb Rush Cyberfunk", "appid": "1353230", "source": "thunderstore", "community": "bomb-rush-cyberfunk"},
    "cultofthelamb": {"name": "Cult of the Lamb", "appid": "1313140", "source": "thunderstore", "community": "cult-of-the-lamb"},
    "outward": {"name": "Outward", "appid": "794260", "source": "thunderstore", "community": "outward", "aliases": ["outwarddefinitiveedition"]},
    "subnautica": {"name": "Subnautica", "appid": "264710", "source": "thunderstore", "community": "subnautica"},
    "stardewvalley": {"name": "Stardew Valley", "appid": "413150", "source": "nexus", "domain": "stardewvalley", "kind": "smapi"},
    "skyrimspecialedition": {"name": "Skyrim Special Edition", "appid": "489830", "source": "nexus",
                             "domain": "skyrimspecialedition", "kind": "bethesda", "appdata": "Skyrim Special Edition",
                             "aliases": ["elderscrollsvskyrimspecial", "elderscrollsvskyrimanniversary", "skyrimanniversary"]},
    "fallout4": {"name": "Fallout 4", "appid": "377160", "source": "nexus", "domain": "fallout4", "kind": "bethesda",
                 "appdata": "Fallout4"},
    "cyberpunk2077": {"name": "Cyberpunk 2077", "appid": "1091500", "source": "nexus", "domain": "cyberpunk2077", "kind": "cyberpunk"},
}
for _g in GAMES.values():
    _g.setdefault("kind", "bepinex")
_BY_APPID = {g["appid"]: gid for gid, g in GAMES.items()}
_BY_DOMAIN = {g["domain"]: gid for gid, g in GAMES.items() if g.get("domain")}
SKIP_TOP = {"manifest.json", "icon.png", "readme.md", "changelog.md", "license", "license.txt", "license.md"}


class ModError(Exception):
    pass


# --- which game ---------------------------------------------------------------------
def game_for(title, appid=""):
    """The GAMES id for a library game, or ""."""
    if appid and str(appid) in _BY_APPID:
        return _BY_APPID[str(appid)]
    from .covers import norm
    n = norm(title or "")
    for gid, g in GAMES.items():
        if n == gid or n in g.get("aliases", []):
            return gid
    return ""


def game_by_domain(domain):
    return _BY_DOMAIN.get(domain or "", "")


# --- state ----------------------------------------------------------------------------
def _dir(gid):
    return ROOT / gid


def load(gid):
    s = read_json(_dir(gid) / "state.json") or {}
    s.setdefault("mods", {})          # mid -> {name, version, source, author, icon, url, deps, auto, size}
    s.setdefault("profiles", {"Default": []})  # name -> [mid, ...] enabled, in load order
    s.setdefault("profile", "Default")
    s.setdefault("deployed", [])      # paths placed in the game folder (relative)
    s.setdefault("replaced", [])      # of those, the ones that were game files (kept in backup/)
    s.setdefault("game_dir", "")
    s.setdefault("plugins", [])       # Bethesda: plugin files Cornerplay put in plugins.txt
    if s["profile"] not in s["profiles"]:
        s["profiles"][s["profile"]] = []
    return s


def save(gid, s):
    os.makedirs(_dir(gid), exist_ok=True)
    write_json(_dir(gid) / "state.json", s)


def _safe(name):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._") or "mod"


def _staging(gid, mid):
    return _dir(gid) / "mods" / _safe(mid)


def enabled(s):
    return list(s["profiles"].get(s["profile"], []))


# --- downloads and archives -------------------------------------------------------------
def _download(url, dest, progress=None, headers=None):
    with requests.get(url, stream=True, timeout=60, headers={**UA, **(headers or {})}) as r:
        r.raise_for_status()
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
                done += len(chunk)
                if progress and total:
                    progress(done / total)


def _safe_member(root, name):
    target = os.path.realpath(os.path.join(root, name))
    return target if target == os.path.realpath(root) or target.startswith(os.path.realpath(root) + os.sep) else None


def extract(archive, dest):
    """Unpack a .zip (Python), or .7z / .rar / .tar (bsdtar, else 7z / unrar) into dest, never outside it."""
    os.makedirs(dest, exist_ok=True)
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as z:
            for info in z.infolist():
                name = info.filename.replace("\\", "/")
                if not _safe_member(dest, name):
                    continue
                target = os.path.join(dest, name)
                if name.endswith("/"):
                    os.makedirs(target, exist_ok=True)
                    continue
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with z.open(info) as src, open(target, "wb") as out:
                    shutil.copyfileobj(src, out)
        return
    tools = []
    if shutil.which("bsdtar"):
        tools.append(["bsdtar", "-xf", archive, "-C", dest])
    if shutil.which("7z"):
        tools.append(["7z", "x", "-y", f"-o{dest}", archive])
    if shutil.which("unrar") and archive.lower().endswith(".rar"):
        tools.append(["unrar", "x", "-o+", archive, dest + "/"])
    for argv in tools:
        if subprocess.run(argv, capture_output=True).returncode == 0:
            break
    else:
        raise ModError("Could not unpack this mod's archive (install bsdtar or 7z)" if not tools
                       else "Could not unpack this mod's archive")
    for base, dirs, files in os.walk(dest):  # anything that escaped through a link: gone
        for f in dirs + files:
            p = os.path.join(base, f)
            if os.path.islink(p) and not _safe_member(dest, os.readlink(p) if os.path.isabs(os.readlink(p)) else os.path.join(base, os.readlink(p))):
                os.unlink(p)


def _entries(path):
    try:
        return sorted(os.listdir(path))
    except OSError:
        return []


def _unwrap(raw, keep=lambda names: False):
    """Into the single folder an archive is wrapped in (when it holds only that)."""
    while True:
        names = [n for n in _entries(raw) if n.lower() not in SKIP_TOP]
        if len(names) == 1 and os.path.isdir(os.path.join(raw, names[0])) and not keep(names):
            raw = os.path.join(raw, names[0])
        else:
            return raw


def _ci(base, rel):
    """rel inside base, matching names without regard to case (Windows mods, Linux files)."""
    path = base
    for part in [p for p in rel.replace("\\", "/").split("/") if p and p != "."]:
        found = next((n for n in _entries(path) if n.lower() == part.lower()), None)
        if found is None:
            return None
        path = os.path.join(path, found)
    return path


def _put(src, dest_root, rel):
    """Copy a file or folder from src to dest_root/rel."""
    if not _safe_member(dest_root, rel or "."):
        raise ModError("A mod tried to place files outside its folder")
    target = os.path.join(dest_root, rel) if rel else dest_root
    if os.path.isdir(src):
        for base, _dirs, files in os.walk(src):
            for f in files:
                sub = os.path.relpath(os.path.join(base, f), src)
                os.makedirs(os.path.dirname(os.path.join(target, sub)), exist_ok=True)
                shutil.copy2(os.path.join(base, f), os.path.join(target, sub))
    elif os.path.isfile(src):
        os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
        shutil.copy2(src, target)


# --- laying a mod out as it goes into the game folder ------------------------------------
def layout_bepinex(raw, out, package):
    """Thunderstore's BepInEx layout (as r2modman does it)."""
    names = _entries(raw)
    low = {n.lower(): n for n in names}
    if "bepinex" not in low and "winhttp.dll" not in low and "doorstop_config.ini" not in low:
        inner = [n for n in names if os.path.isdir(os.path.join(raw, n)) and
                 {"bepinex", "winhttp.dll", "doorstop_config.ini"} & {x.lower() for x in _entries(os.path.join(raw, n))}]
        if inner and package.split("-")[-1].lower().startswith("bepinex"):
            raw, names = os.path.join(raw, inner[0]), _entries(os.path.join(raw, inner[0]))  # the loader pack itself
            low = {n.lower(): n for n in names}
    loader = "winhttp.dll" in low or "doorstop_config.ini" in low
    for n in names:
        src, lname = os.path.join(raw, n), n.lower()
        if lname in SKIP_TOP:
            continue
        if loader or lname == "bepinex":
            _put(src, out, n)  # the loader, or a mod already laid out from the game folder
        elif lname in ("plugins", "patchers", "monomod"):
            _put(src, out, f"BepInEx/{lname}/{package}")
        elif lname in ("config", "core"):
            _put(src, out, f"BepInEx/{lname}")
        else:
            _put(src, out, f"BepInEx/plugins/{package}/{n}")


def layout_smapi(raw, out):
    """SMAPI mods: every folder holding a manifest.json goes into Mods/."""
    found = []
    for base, dirs, files in os.walk(raw):
        if any(f.lower() == "manifest.json" for f in files):
            found.append(base)
            dirs[:] = []
    if not found:
        raise ModError("This doesn't look like a SMAPI mod (no manifest.json)")
    for base in found:
        name = os.path.basename(base) if os.path.realpath(base) != os.path.realpath(raw) else "mod"
        _put(base, out, f"Mods/{name}")


def _fomod_flags_ok(node, flags):
    if node is None:
        return True
    op = (node.get("operator") or "And").lower()
    results = []
    for dep in list(node):
        tag = dep.tag.lower()
        if tag == "flagdependency":
            results.append(flags.get(dep.get("flag")) == dep.get("value"))
        elif tag == "dependencies":
            results.append(_fomod_flags_ok(dep, flags))
        else:
            results.append(True)  # file and game version checks: assume met
    return any(results) if op == "or" else all(results)


def _fomod_copy(root, files_node, data_out):
    if files_node is None:
        return
    for item in list(files_node):
        src = _ci(root, item.get("source") or "")
        dest = (item.get("destination") or ("" if item.tag.lower() == "folder" else os.path.basename((item.get("source") or "").replace("\\", "/")))).replace("\\", "/").strip("/")
        if src:
            _put(src, data_out, dest)


def layout_fomod(raw, data_out):
    """A FOMOD installer, with its recommended (else first) choices: required files, each
    step's picks and the conditional files their flags turn on. Returns the picks' names."""
    conf = _ci(raw, "fomod/ModuleConfig.xml")
    xml = open(conf, "rb").read()
    xml = re.sub(rb'\sxmlns(:\w+)?="[^"]*"', b"", xml)
    xml = re.sub(rb"\s\w+:noNamespaceSchemaLocation=\"[^\"]*\"", b"", xml)
    doc = ET.fromstring(xml)
    ci = {e.tag.lower(): e for e in doc}

    def child(node, name):
        return next((c for c in node if c.tag.lower() == name.lower()), None) if node is not None else None

    def kids(node):
        return list(node) if node is not None else []

    _fomod_copy(raw, ci.get("requiredinstallfiles"), data_out)
    flags, picked = {}, []
    for step in kids(ci.get("installsteps")):
        for group in kids(child(step, "optionalFileGroups")):
            plugins = kids(child(group, "plugins"))
            gtype = (group.get("type") or "SelectAny")

            def kind(p):
                td = child(p, "typeDescriptor")
                t = child(td, "type")
                if t is not None:
                    return t.get("name") or "Optional"
                dt = child(td, "dependencyType")
                return (child(dt, "defaultType").get("name") if child(dt, "defaultType") is not None else "Optional")
            chosen = [p for p in plugins if kind(p) in ("Required", "Recommended")]
            if gtype == "SelectAll":
                chosen = plugins
            elif not chosen and gtype in ("SelectExactlyOne", "SelectAtLeastOne"):
                chosen = [p for p in plugins if kind(p) != "NotUsable"][:1]
            elif gtype in ("SelectExactlyOne", "SelectAtMostOne"):
                chosen = chosen[:1]
            for p in chosen:
                picked.append(p.get("name") or "")
                _fomod_copy(raw, child(p, "files"), data_out)
                for flag in kids(child(p, "conditionFlags")):
                    flags[flag.get("name")] = (flag.text or "").strip()
    for pattern in kids(child(ci.get("conditionalfileinstalls"), "patterns")):
        if _fomod_flags_ok(child(pattern, "dependencies"), flags):
            _fomod_copy(raw, child(pattern, "files"), data_out)
    return picked


DATA_DIRS = {"meshes", "textures", "scripts", "interface", "sound", "music", "seq", "skse", "f4se", "materials",
             "strings", "video", "shadersfx", "lodsettings", "grass", "calientetools", "nemesis_engine", "mcm", "tools"}


def layout_bethesda(raw, out):
    """Skyrim / Fallout 4: into Data/ (unless the archive already has a Data folder, or is a
    script extender for the game folder); a FOMOD installer runs with its recommended choices."""
    raw = _unwrap(raw, keep=lambda names: names[0].lower() in DATA_DIRS | {"data", "fomod"})
    if _ci(raw, "fomod/ModuleConfig.xml"):
        os.makedirs(os.path.join(out, "Data"), exist_ok=True)
        return layout_fomod(raw, os.path.join(out, "Data"))
    names = _entries(raw)
    if any(n.lower() == "data" for n in names):
        for n in names:
            if n.lower() == "data":
                _put(os.path.join(raw, n), out, "Data")
            elif n.lower() not in SKIP_TOP:
                _put(os.path.join(raw, n), out, n)  # a script extender's loader and dlls
        return []
    if any(n.lower().endswith("_loader.exe") for n in names):
        for n in names:
            _put(os.path.join(raw, n), out, n)
        return []
    for n in names:
        if n.lower() not in SKIP_TOP and not n.lower().endswith((".txt", ".pdf", ".jpg", ".png")):
            _put(os.path.join(raw, n), out, f"Data/{n}")
    return []


CP_TOP = {"archive", "bin", "r6", "red4ext", "engine", "mods"}


def layout_cyberpunk(raw, out):
    """Cyberpunk 2077: archives laid out from the game folder (archive/, bin/, r6/, red4ext/,
    mods/); bare .archive files go to archive/pc/mod."""
    raw = _unwrap(raw, keep=lambda names: names[0].lower() in CP_TOP)
    names = _entries(raw)
    if any(n.lower() in CP_TOP for n in names):
        for n in names:
            if n.lower() in CP_TOP:
                _put(os.path.join(raw, n), out, n)
        return
    loose = [n for n in names if n.lower().endswith((".archive", ".xl"))]
    if not loose:
        raise ModError("Cornerplay can't tell where this mod's files go")
    for n in loose:
        _put(os.path.join(raw, n), out, f"archive/pc/mod/{n}")


# --- installing --------------------------------------------------------------------------
def install_archive(gid, mid, archive, meta, progress=None):
    """Unpack archive into the mod's own folder (laid out for the game) and record it."""
    g = GAMES[gid]
    with tempfile.TemporaryDirectory(prefix="cpmod-") as tmp:
        raw = os.path.join(tmp, "raw")
        extract(archive, raw)
        out = os.path.join(tmp, "out")
        os.makedirs(out)
        picks = []
        if g["kind"] == "bepinex":
            layout_bepinex(_unwrap(raw), out, meta.get("package") or mid)
        elif g["kind"] == "smapi":
            layout_smapi(raw, out)
        elif g["kind"] == "bethesda":
            picks = layout_bethesda(raw, out) or []
        else:
            layout_cyberpunk(raw, out)
        if not any(files for _b, _d, files in os.walk(out)):
            raise ModError("This mod has no files Cornerplay knows where to put")
        dest = _staging(gid, mid)
        with _lock:
            shutil.rmtree(dest, ignore_errors=True)
            os.makedirs(dest.parent, exist_ok=True)
            shutil.move(out, dest)
            s = load(gid)
            old = s["mods"].get(mid) or {}
            size = sum(os.path.getsize(os.path.join(b, f)) for b, _d, fs in os.walk(dest) for f in fs)
            s["mods"][mid] = {**old, **meta, "size": size, "installed": int(time.time()),
                              "options": picks, "auto": bool(meta.get("auto")) and old.get("auto", True)}
            on = s["profiles"].setdefault(s["profile"], [])
            if mid not in on:
                on.append(mid)
            save(gid, s)


# Thunderstore ---------------------------------------------------------------------------
def ts_search(gid, query="", page=1):
    """[{id, name, author, description, icon, downloads, url, version?}] most downloaded first."""
    g = GAMES[gid]
    r = requests.get(f"{TS}/api/cyberstorm/listing/{g['community']}/", timeout=30, headers=UA,
                     params={"q": query, "ordering": "most-downloaded", "page_size": 30, "page": page,
                             "deprecated": "false", "nsfw": "false"})
    r.raise_for_status()
    out = []
    for p in r.json().get("results") or []:
        full = f"{p['namespace']}-{p['name']}"
        if p["name"].lower().startswith("r2modman"):
            continue
        out.append({"id": "ts:" + full, "name": p["name"].replace("_", " "), "author": p["namespace"],
                    "description": p.get("description") or "", "icon": p.get("icon_url") or "",
                    "downloads": int(p.get("download_count") or 0),
                    "url": f"{TS}/c/{g['community']}/p/{p['namespace']}/{p['name']}/"})
    return out


def ts_package(full):
    """Latest version of a Thunderstore package: {version, download, deps: [full names], description, icon}."""
    ns, name = full.split("-", 1)
    r = requests.get(f"{TS}/api/experimental/package/{ns}/{name}/", timeout=30, headers=UA)
    if r.status_code == 404:
        raise ModError(f"{full} is no longer on Thunderstore")
    r.raise_for_status()
    latest = r.json()["latest"]
    return {"version": latest["version_number"], "download": latest["download_url"],
            "deps": ["-".join(d.split("-")[:2]) for d in latest.get("dependencies") or []],
            "description": latest.get("description") or "", "icon": latest.get("icon") or ""}


def ts_install(gid, full, progress=None, auto=False, seen=None):
    """Install a Thunderstore package and, first, whatever it depends on (once each)."""
    seen = set() if seen is None else seen
    if full in seen:
        return
    seen.add(full)
    pkg = ts_package(full)
    mid = "ts:" + full
    s = load(gid)
    for dep in pkg["deps"]:
        if "ts:" + dep not in s["mods"]:
            ts_install(gid, dep, progress, auto=True, seen=seen)
        else:  # already installed: make sure the active profile uses it
            with _lock:
                s2 = load(gid)
                on = s2["profiles"][s2["profile"]]
                if "ts:" + dep not in on:
                    on.insert(0, "ts:" + dep)
                save(gid, s2)
    have = s["mods"].get(mid)
    if have and have.get("version") == pkg["version"] and _staging(gid, mid).is_dir():
        return
    ns, name = full.split("-", 1)
    with tempfile.TemporaryDirectory(prefix="cpdl-") as tmp:
        path = os.path.join(tmp, "mod.zip")
        _download(pkg["download"], path, progress)
        install_archive(gid, mid, path, {"name": name.replace("_", " "), "author": ns, "version": pkg["version"],
                                         "source": "thunderstore", "icon": pkg["icon"], "package": full,
                                         "deps": ["ts:" + d for d in pkg["deps"]],
                                         "url": f"{TS}/c/{GAMES[gid]['community']}/p/{ns}/{name}/", "auto": auto})


# Nexus ------------------------------------------------------------------------------------
def nexus_key():
    return (read_json(NEXUS_KEY_FILE) or {}).get("key", "")


def nexus_account():
    return read_json(NEXUS_KEY_FILE) or {}


def nexus_set_key(key):
    """Check the key with Nexus and keep it (readable only by you). Returns {name, premium}."""
    key = (key or "").strip()
    if not key:
        NEXUS_KEY_FILE.unlink(missing_ok=True)
        return {}
    r = requests.get(f"{NEXUS_API}/v1/users/validate.json", headers={**UA, "apikey": key}, timeout=30)
    if r.status_code in (401, 403):
        raise ModError("Nexus Mods did not accept this API key")
    r.raise_for_status()
    d = r.json()
    info = {"key": key, "name": d.get("name") or "", "premium": bool(d.get("is_premium"))}
    write_private(NEXUS_KEY_FILE, json.dumps(info))
    return {"name": info["name"], "premium": info["premium"]}


def _nexus(path, params=None):
    key = nexus_key()
    if not key:
        raise ModError("Add your Nexus Mods API key first")
    r = requests.get(f"{NEXUS_API}{path}", params=params, headers={**UA, "apikey": key}, timeout=30)
    if r.status_code in (401, 403):
        raise ModError("Nexus Mods refused: a free account downloads with the website's "
                       "“Mod Manager Download” button" if "download_link" in path else "Nexus Mods did not accept your API key")
    if r.status_code == 404:
        raise ModError("Nexus Mods doesn't have that mod or file any more")
    r.raise_for_status()
    return r.json()


def nexus_search(gid, query="", page=1):
    """Mods by name (most downloaded first), or the most downloaded ones; no key needed."""
    g = GAMES[gid]
    filt = {"gameDomainName": [{"value": g["domain"]}]}
    if query:
        filt["name"] = [{"value": query, "op": "WILDCARD"}]
    q = ("query($f: ModsFilter, $o: Int) { mods(filter: $f, sort: {downloads: {direction: DESC}}, count: 30, offset: $o) "
         "{ nodes { modId name summary downloads pictureUrl version author adultContent } } }")
    r = requests.post(f"{NEXUS_API}/v2/graphql", json={"query": q, "variables": {"f": filt, "o": (page - 1) * 30}},
                      headers=UA, timeout=30)
    r.raise_for_status()
    nodes = ((r.json().get("data") or {}).get("mods") or {}).get("nodes") or []
    return [{"id": f"nx:{n['modId']}", "name": n.get("name") or "", "author": n.get("author") or "",
             "description": re.sub(r"<[^>]+>", "", n.get("summary") or ""), "icon": n.get("pictureUrl") or "",
             "downloads": int(n.get("downloads") or 0), "version": n.get("version") or "",
             "url": f"https://www.nexusmods.com/{g['domain']}/mods/{n['modId']}"}
            for n in nodes if not n.get("adultContent")]


def nexus_files_url(gid, mod_id):
    return f"https://www.nexusmods.com/{GAMES[gid]['domain']}/mods/{mod_id}?tab=files"


def nexus_main_file(gid, mod_id):
    """The newest main file of a mod: {file_id, version, name}."""
    files = _nexus(f"/v1/games/{GAMES[gid]['domain']}/mods/{mod_id}/files.json").get("files") or []
    main = [f for f in files if f.get("category_name") == "MAIN"] or [f for f in files if f.get("category_name") not in ("OLD_VERSION", "ARCHIVED", "DELETED")]
    if not main:
        raise ModError("This mod has no file to download")
    f = max(main, key=lambda f: f.get("uploaded_timestamp") or 0)
    return {"file_id": f["file_id"], "version": f.get("version") or f.get("mod_version") or "", "name": f.get("name") or ""}


def nexus_install(gid, mod_id, file_id=None, key=None, expires=None, progress=None):
    """Download one Nexus file and install it. Without key/expires (from an nxm:// link) this
    needs a Premium account; ModError tells a free account to use the website's button."""
    domain = GAMES[gid]["domain"]
    mod = _nexus(f"/v1/games/{domain}/mods/{mod_id}.json")
    if file_id is None:
        f = nexus_main_file(gid, mod_id)
        file_id, version = f["file_id"], f["version"]
    else:
        info = _nexus(f"/v1/games/{domain}/mods/{mod_id}/files/{file_id}.json")
        version = info.get("version") or info.get("mod_version") or ""
    params = {"key": key, "expires": expires} if key and expires else None
    links = _nexus(f"/v1/games/{domain}/mods/{mod_id}/files/{file_id}/download_link.json", params)
    if not links:
        raise ModError("Nexus Mods gave no download link")
    url = links[0]["URI"]
    ext = os.path.splitext(url.split("?")[0])[1] or ".zip"
    with tempfile.TemporaryDirectory(prefix="cpdl-") as tmp:
        path = os.path.join(tmp, "mod" + ext)
        _download(url, path, progress)
        install_archive(gid, f"nx:{mod_id}", path, {
            "name": mod.get("name") or f"Mod {mod_id}", "author": mod.get("author") or "", "version": version,
            "source": "nexus", "icon": mod.get("picture_url") or "", "file_id": file_id, "deps": [],
            "url": f"https://www.nexusmods.com/{domain}/mods/{mod_id}", "auto": False})
    return mod.get("name") or ""


NXM = re.compile(r"^nxm://(?P<domain>[a-z0-9]+)/mods/(?P<mod>\d+)/files/(?P<file>\d+)\?(?P<q>.*)$", re.I)


def parse_nxm(url):
    """nxm://<game>/mods/<mod>/files/<file>?key=..&expires=..: {gid, mod, file, key, expires}."""
    m = NXM.match((url or "").strip())
    if not m:
        raise ModError("Not a Nexus Mods download link")
    q = dict(p.split("=", 1) for p in m.group("q").split("&") if "=" in p)
    gid = game_by_domain(m.group("domain").lower())
    if not gid:
        raise ModError(f"Cornerplay doesn't manage mods for this game ({m.group('domain')}) yet")
    return {"gid": gid, "mod": int(m.group("mod")), "file": int(m.group("file")),
            "key": q.get("key"), "expires": q.get("expires")}


# --- updates -------------------------------------------------------------------------------
def updates(gid):
    """{mid: newer version} for installed mods (Thunderstore always; Nexus with an API key)."""
    out = {}
    s = load(gid)
    nexus_ids = []
    for mid, m in s["mods"].items():
        try:
            if m.get("source") == "thunderstore":
                v = ts_package(m["package"])["version"]
                if v != m.get("version"):
                    out[mid] = v
            elif m.get("source") == "nexus":
                nexus_ids.append(mid)
        except Exception:
            continue
    if nexus_ids and nexus_key():
        for mid in nexus_ids:
            try:
                f = nexus_main_file(gid, int(mid.split(":")[1]))
                if f["file_id"] != s["mods"][mid].get("file_id") and f["version"] != s["mods"][mid].get("version"):
                    out[mid] = f["version"] or "new"
            except Exception:
                continue
    return out


# --- profiles ------------------------------------------------------------------------------
def set_enabled(gid, mid, on):
    """Switch a mod on or off in the active profile (switching one on brings its dependencies)."""
    with _lock:
        s = load(gid)
        lst = s["profiles"].setdefault(s["profile"], [])
        if on:
            for dep in s["mods"].get(mid, {}).get("deps") or []:
                if dep in s["mods"] and dep not in lst:
                    lst.insert(0, dep)
            if mid not in lst:
                lst.append(mid)
        elif mid in lst:
            lst.remove(mid)
        save(gid, s)


def needed_by(s, mid):
    """Enabled mods that depend on mid."""
    return [s["mods"][m]["name"] for m in enabled(s) if mid in (s["mods"].get(m, {}).get("deps") or [])]


def uninstall(gid, mid):
    with _lock:
        s = load(gid)
        s["mods"].pop(mid, None)
        for lst in s["profiles"].values():
            if mid in lst:
                lst.remove(mid)
        save(gid, s)
        shutil.rmtree(_staging(gid, mid), ignore_errors=True)


def new_profile(gid, name, copy=True):
    name = (name or "").strip()[:40]
    if not name:
        raise ModError("Give the profile a name")
    with _lock:
        s = load(gid)
        if name in s["profiles"]:
            raise ModError("There is a profile with that name already")
        s["profiles"][name] = list(enabled(s)) if copy else []
        s["profile"] = name
        save(gid, s)


def use_profile(gid, name):
    with _lock:
        s = load(gid)
        if name in s["profiles"]:
            s["profile"] = name
            save(gid, s)


def delete_profile(gid, name):
    with _lock:
        s = load(gid)
        if name in s["profiles"] and len(s["profiles"]) > 1:
            del s["profiles"][name]
            if s["profile"] == name:
                s["profile"] = next(iter(s["profiles"]))
            save(gid, s)


# --- deploying -----------------------------------------------------------------------------
def _same_file(a, b):
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def undeploy(gid, s=None):
    """Take every file Cornerplay placed out of the game folder and put back what they replaced."""
    with _lock:
        s = s or load(gid)
        game = s.get("game_dir") or ""
        backup = _dir(gid) / "backup"
        if game and os.path.isdir(game):
            replaced = set(s.get("replaced") or [])
            dirs = set()
            for rel in sorted(s.get("deployed") or [], key=len, reverse=True):
                p = _safe_member(game, rel)
                if not p:
                    continue
                try:
                    os.unlink(p)
                except OSError:
                    pass
                if rel in replaced and (backup / rel).is_file():
                    os.makedirs(os.path.dirname(p), exist_ok=True)
                    shutil.move(str(backup / rel), p)
                d = os.path.dirname(rel)
                while d:
                    dirs.add(d)
                    d = os.path.dirname(d)
            for d in sorted(dirs, key=len, reverse=True):  # folders the mods made, now empty
                try:
                    os.rmdir(os.path.join(game, d))
                except OSError:
                    pass
        s["deployed"], s["replaced"] = [], []
        save(gid, s)
        return s


def deploy(gid, game_dir, prefix=""):
    """Make the game folder match the active profile. Returns the number of files placed."""
    if not game_dir or not os.path.isdir(game_dir):
        raise ModError("Install the game first: its folder wasn't found")
    with _lock:
        s = load(gid)
        if s.get("game_dir") and os.path.realpath(s["game_dir"]) != os.path.realpath(game_dir):
            undeploy(gid, s)  # the game moved: clean the old place first
        s = undeploy(gid, load(gid))
        s["game_dir"] = game_dir
        plan = {}
        for mid in enabled(s):
            src = _staging(gid, mid)
            for base, _dirs, files in os.walk(src):
                for f in files:
                    full = os.path.join(base, f)
                    plan[os.path.relpath(full, src)] = full  # later mods win
        backup = _dir(gid) / "backup"
        deployed, replaced = [], []
        try:
            for rel, src in plan.items():
                target = _safe_member(game_dir, rel)
                if not target:
                    continue
                existing = _ci(game_dir, rel)  # a game file under another case counts too
                if existing and os.path.isfile(existing):
                    target = existing
                    rel = os.path.relpath(existing, game_dir)
                    os.makedirs(os.path.dirname(backup / rel), exist_ok=True)
                    shutil.move(existing, backup / rel)
                    replaced.append(rel)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                try:
                    os.link(src, target)
                except OSError:
                    shutil.copy2(src, target)
                deployed.append(rel)
        finally:
            s["deployed"], s["replaced"] = deployed, replaced
            save(gid, s)
        if GAMES[gid]["kind"] == "bethesda":
            write_plugins(gid, s, prefix)
        return len(deployed)


PLUGIN_EXT = (".esp", ".esm", ".esl")


def plugins_txt(gid, prefix):
    g = GAMES[gid]
    if not prefix or not g.get("appdata"):
        return ""
    return os.path.join(prefix, "drive_c", "users", "steamuser", "AppData", "Local", g["appdata"], "plugins.txt")


def write_plugins(gid, s, prefix):
    """Bethesda games: the enabled mods' plugins listed (and switched on, '*') in plugins.txt;
    lines for other plugins (Creation Club, your own) stay as they were."""
    path = plugins_txt(gid, prefix)
    if not path:
        return
    mine = []
    for mid in enabled(s):
        data = _ci(str(_staging(gid, mid)), "Data")
        for n in _entries(data) if data else []:
            if n.lower().endswith(PLUGIN_EXT) and n not in mine:
                mine.append(n)
    ours = {p.lower() for p in (s.get("plugins") or [])} | {p.lower() for p in mine}
    lines = []
    if os.path.isfile(path):
        for line in open(path, encoding="utf-8", errors="replace").read().splitlines():
            if line.strip().lstrip("*").lower() not in ours:
                lines.append(line)
    lines += ["*" + p for p in mine]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\r\n") as f:
        f.write("\n".join(lines) + ("\n" if lines else ""))
    with _lock:
        s2 = load(gid)
        s2["plugins"] = mine
        save(gid, s2)


# --- what a game needs before mods work ------------------------------------------------------
def setup_notes(gid, game_dir, proton):
    """[{text, copy?, url?}]: what to do once so the game loads its mods."""
    g, notes = GAMES[gid], []
    if g["kind"] == "bepinex":
        if proton:
            notes.append({"text": "Mods load through BepInEx. Under Proton, add this to the game's launch options in Steam "
                                  "(Properties › General), once:", "copy": 'WINEDLLOVERRIDES="winhttp=n,b" %command%'})
        else:
            script = "start_game_bepinex.sh" if game_dir and _ci(game_dir, "start_game_bepinex.sh") else "run_bepinex.sh"
            notes.append({"text": "Mods load through BepInEx. For the Linux version, set the game's launch options in Steam to:",
                          "copy": f"./{script} %command%"})
    elif g["kind"] == "smapi":
        has = game_dir and any(_ci(game_dir, n) for n in ("StardewModdingAPI", "StardewModdingAPI.exe", "StardewModdingAPI.dll"))
        if not has:
            notes.append({"text": "Stardew Valley mods need SMAPI, the mod loader. Install it once from smapi.io "
                                  "(its installer sets up Steam for you).", "url": "https://smapi.io"})
    elif g["kind"] == "bethesda":
        notes.append({"text": "Many mods also need the script extender (SKSE for Skyrim, F4SE for Fallout 4); "
                              "their pages say so. Plugins are switched on in plugins.txt for you."})
    elif g["kind"] == "cyberpunk":
        notes.append({"text": "Many Cyberpunk mods need Cyber Engine Tweaks, RED4ext or ArchiveXL first: install those like any other mod. "
                              "Under Proton, CET also needs this launch option in Steam:", "copy": 'WINEDLLOVERRIDES="winmm,version=n,b" %command%'})
    return notes


def needs_proton(game_dir):
    """Windows build in the folder (so BepInEx loads through winhttp.dll under Proton)?"""
    return bool(game_dir) and any(n.lower().endswith(".exe") and "unitycrashhandler" not in n.lower()
                                  for n in _entries(game_dir))


def summary(gid):
    """For the game page: {installed, enabled, profile}."""
    s = load(gid)
    return {"installed": len(s["mods"]), "enabled": len([m for m in enabled(s) if m in s["mods"]]), "profile": s["profile"]}
