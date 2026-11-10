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


def custom_tools(root):
    """Tools in compatibilitytools.d (GE-Proton and the like): [(name, display name)]."""
    out = []
    base = os.path.join(root, "compatibilitytools.d")
    try:
        folders = sorted(os.listdir(base), reverse=True)
    except OSError:
        return out
    for folder in folders:
        manifest = vdf.load(os.path.join(base, folder, "compatibilitytool.vdf"))
        tools = (manifest.get("compatibilitytools") or {}).get("compat_tools") or {}
        for name, info in tools.items():
            if isinstance(info, dict):
                out.append((name, info.get("display_name") or name))
    return out


def choices(root):
    """[{"label", "value"}] for a Steam game's Proton picker; "" leaves it to Steam."""
    out = [{"label": "Steam's choice (set in Steam)", "value": ""}]
    out += [{"label": label, "value": name} for name, label in VALVE]
    out += [{"label": f"{label}  ·  custom", "value": name} for name, label in custom_tools(root)]
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
