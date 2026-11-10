"""Which Proton a Steam game runs with: Steam's own per-game "compatibility tool" setting.

Steam keeps it in config/config.vdf (InstallConfigStore > Software > Valve > Steam >
CompatToolMapping > <appid>). Steam rewrites that file when it exits, so it is only
changed while Steam is closed (AIO Launch closes and reopens Steam around the change).
A copy of the file is kept as config.vdf.aiolaunch-backup before each change.
"""
import os
import shutil

from . import vdf

# Valve's Proton builds, by the internal name Steam uses. Steam downloads one the first time
# a game is set to it.
VALVE = [("proton_experimental", "Proton Experimental"), ("proton_10", "Proton 10.0"),
         ("proton_9", "Proton 9.0"), ("proton_hotfix", "Proton Hotfix"), ("proton_8", "Proton 8.0")]
PATH = ("InstallConfigStore", "Software", "Valve", "Steam", "CompatToolMapping")


def _node(d, key, create=False):
    """Child dict by key, matching case like Steam does (it writes "valve" and "Valve")."""
    for k, v in d.items():
        if k.lower() == key.lower() and isinstance(v, dict):
            return v
    if create:
        d[key] = {}
        return d[key]
    return None


def _mapping(conf, create=False):
    node = conf
    for key in PATH:
        node = _node(node, key, create)
        if node is None:
            return None
    return node


def _visible(root):
    """Real paths of the builds this Steam installation loads by itself."""
    from . import protons
    dirs = [os.path.join(root, "compatibilitytools.d")] + protons.system_tool_dirs()
    out = set()
    for d in dirs:
        try:
            out |= {os.path.realpath(os.path.join(d, n)) for n in os.listdir(d)}
        except OSError:
            pass
    return out


def choices(root):
    """[{"label", "value"}] for a Steam game's Proton picker; "" leaves it to Steam.

    Valve's builds are always offered (Steam downloads them when needed). Every other Proton
    build on the PC is offered too: by its tool name when this Steam already loads it, or as
    "link:<path>" when it lives elsewhere (Heroic, Lutris, ...) and needs linking into
    compatibilitytools.d first. Builds without a compatibilitytool.vdf cannot be loaded by Steam.
    """
    from . import protons
    found = protons.find()
    have = {p["valve"] for p in found if p["valve"]}
    out = [{"label": "Steam's choice (set in Steam)", "value": ""}]
    out += [{"label": label + ("  ·  installed" if name in have else ""), "value": name} for name, label in VALVE]
    names = {c["value"] for c in out}
    visible = _visible(root)
    for p in found:
        if p["valve"]:
            if p["valve"] not in names:  # an older Valve build that is installed
                out.append({"label": p["label"] + "  ·  installed", "value": p["valve"]})
                names.add(p["valve"])
            continue
        if not p["tool"] or p["tool"] in names:
            continue
        if p["path"] in visible:
            out.append({"label": f"{p['label']}  ·  {p['source']}", "value": p["tool"]})
        else:
            out.append({"label": f"{p['label']}  ·  {p['source']} (linked into Steam when chosen)",
                        "value": "link:" + p["path"]})
        names.add(p["tool"])
    return out


def current(root, appid):
    """The tool name set for this game in Steam, or "" for Steam's default."""
    mapping = _mapping(vdf.load(os.path.join(root, "config", "config.vdf"))) or {}
    entry = mapping.get(str(appid)) or {}
    return entry.get("name", "") if isinstance(entry, dict) else ""


def set_tool(root, appid, name):
    """Set (or with name "" remove) the game's compatibility tool. Steam must be closed."""
    path = os.path.join(root, "config", "config.vdf")
    if not os.path.isfile(path):
        raise RuntimeError("Steam has not been set up on this PC yet (start it and sign in once)")
    conf = vdf.load(path)
    if not conf:
        raise RuntimeError("Could not read Steam's config.vdf")
    if name.startswith("link:"):  # a build from Heroic, Lutris, ...: make it visible to Steam
        src = name[5:]
        from . import protons
        tool = protons._manifest(src)[0]
        if not tool:
            raise RuntimeError("That Proton build has no compatibilitytool.vdf, so Steam cannot load it")
        dest = os.path.join(root, "compatibilitytools.d", os.path.basename(src.rstrip("/")))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        if not os.path.exists(dest):
            os.symlink(src, dest)
        name = tool
    mapping = _mapping(conf, create=True)
    if name:
        mapping[str(appid)] = {"name": name, "config": "", "priority": "250"}
    else:
        mapping.pop(str(appid), None)
    shutil.copy2(path, path + ".aiolaunch-backup")
    tmp = path + ".aiolaunch-tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(vdf.dumps(conf))
    os.replace(tmp, path)
