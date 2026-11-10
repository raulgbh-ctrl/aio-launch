"""Running Windows games: Proton through umu-launcher, plain Wine as fallback."""
import os
import re
import shlex
import shutil

from contextlib import contextmanager

from .config import HOME, find_tool, settings

_overrides: dict = {}


@contextmanager
def using(overrides: dict):
    """Apply one game's overrides to everything built inside the block."""
    global _overrides
    old, _overrides = _overrides, overrides or {}
    try:
        yield
    finally:
        _overrides = old


def opt(name):
    """A setting, unless the current game overrides it."""
    return _overrides[name] if name in _overrides else settings.get(name)


def parse_env(text: str) -> dict:
    out = {}
    try:
        parts = shlex.split(text or "")
    except ValueError:
        parts = (text or "").split()
    for part in parts:
        k, sep, v = part.partition("=")
        if sep and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", k):
            out[k] = v
    return out


def user_env() -> dict:
    """Global extra environment, then the current game's on top."""
    env = parse_env(settings.get("env"))
    env.update(parse_env(_overrides.get("env", "")))
    return env


def proton_versions() -> list:
    """Every Proton build umu can use: [{"label", "value"}], value is a PROTONPATH.
    The builds come from protons.find(): Steam, Heroic, Lutris, umu, system, wherever they are."""
    from . import protons
    out = [{"label": "GE-Proton, always the latest (updates itself)", "value": "GE-Proton"},
           {"label": "UMU-Proton (umu-launcher's own build)", "value": ""}]
    out += [{"label": f"{p['label']}  ·  {p['source']}", "value": p["path"]} for p in protons.find()]
    return out


class StoreError(Exception):
    """A user-facing problem (missing tool, not signed in, ...)."""


def compat():
    """Return ("umu", path) or ("wine", path); raise if neither exists."""
    umu = find_tool("umu-run")
    if umu:
        return "umu", umu
    wine = shutil.which("wine")
    if wine:
        return "wine", wine
    raise StoreError("umu-launcher is not installed (sudo pacman -S umu-launcher)")


def prefix_path(store: str, game_id: str, create: bool = False) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", f"{store}-{game_id}")
    p = settings.games_dir / "prefixes" / safe
    if create:
        p.mkdir(parents=True, exist_ok=True)
    return str(p)


def wine_env(store: str, game_id: str, umu_id: str = "umu-default") -> dict:
    """Environment for umu-run / wine for one game."""
    env = {"WINEPREFIX": prefix_path(store, game_id, create=True)}
    kind, _ = compat()
    if kind == "umu":
        env["GAMEID"] = umu_id
        env["STORE"] = {"epic": "egs", "gog": "gog", "amazon": "amazon", "battlenet": "battlenet"}.get(store, "none")
        proton = (opt("proton") or "").strip()
        if proton:
            env["PROTONPATH"] = os.path.expanduser(proton)
    env.update(user_env())
    return env


def extras() -> list:
    """Optional wrappers the user switched on in Settings."""
    out = []
    if opt("gamemode") and shutil.which("gamemoderun"):
        out.append("gamemoderun")
    if opt("mangohud") and shutil.which("mangohud"):
        out.append("mangohud")
    return out


def wrapper_argv() -> list:
    """argv prefix that runs a Windows executable."""
    _, path = compat()
    return [*extras(), path]


def wrapper_string() -> str:
    """Same as wrapper_argv, as one shell-quoted string for --wrapper flags."""
    return shlex.join(wrapper_argv())
