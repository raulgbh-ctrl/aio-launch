"""Running Windows games: Proton through umu-launcher, plain Wine as fallback."""
import os
import re
import shlex
import shutil

from contextlib import contextmanager

from .config import CACHE_DIR, find_tool, settings

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
    env.update(perf_env(store, game_id))
    env.update(user_env())
    return env


# Performance profiles: a frame cap (DXVK and VKD3D-Proton cap it themselves; MangoHud too when
# it runs) and AMD FSR upscaling when a game runs full screen below the screen's resolution.
PROFILES = {
    "battery": {"fps": 30, "fsr": True},
    "balanced": {"fps": 60, "fsr": True},
    "quality": {"fps": 0, "fsr": False},
}


def perf_env(store: str, game_id: str) -> dict:
    env = {}
    prof = PROFILES.get(opt("perf") or "")  # "none" (a game set to No change) matches nothing
    if prof:
        if prof["fps"]:
            env["DXVK_FRAME_RATE"] = str(prof["fps"])
            env["VKD3D_FRAME_RATE"] = str(prof["fps"])
        if prof["fsr"]:
            env["WINE_FULLSCREEN_FSR"] = "1"
    hud = []
    if opt("show_fps"):
        hud += ["fps_only=1"]
    if prof and prof["fps"]:
        hud += [f"fps_limit={prof['fps']}"]
    if hud:
        env["MANGOHUD_CONFIG"] = ",".join(hud)
    if settings.get("shader_cache"):
        # One lasting cache folder per game: shaders compiled once stay compiled, also after a
        # reinstall or an update, so only the very first run stutters. (Steam ships ready-made
        # caches for its own games; for other stores this is the next best thing.)
        cache = os.path.join(str(CACHE_DIR / "shaders"), f"{store}_{game_id}")
        os.makedirs(cache, exist_ok=True)
        env.update({"DXVK_STATE_CACHE_PATH": cache, "VKD3D_SHADER_CACHE_PATH": cache,
                    "MESA_SHADER_CACHE_MAX_SIZE": "10G", "__GL_SHADER_DISK_CACHE_SIZE": "10737418240",
                    "__GL_SHADER_DISK_CACHE_SKIP_CLEANUP": "1"})
    return env


# Vulkan: DXVK and VKD3D (how Proton draws Windows games) need the GPU's Vulkan driver.
_VENDORS = {"0x8086": ("Intel", "intel", "vulkan-intel lib32-vulkan-intel"),
            "0x1002": ("AMD", "radeon", "vulkan-radeon lib32-vulkan-radeon"),
            "0x10de": ("NVIDIA", "nvidia", "nvidia-utils lib32-nvidia-utils")}


def _vulkan_gpus() -> int:
    """How many GPUs Vulkan can use right now (-1: Vulkan itself is missing). A GPU that is
    switched off (a laptop's second GPU) or has no driver does not count."""
    import ctypes
    try:
        vk = ctypes.CDLL("libvulkan.so.1")
    except OSError:
        return -1

    class AppInfo(ctypes.Structure):
        _fields_ = [("sType", ctypes.c_int), ("pNext", ctypes.c_void_p), ("name", ctypes.c_char_p),
                    ("version", ctypes.c_uint32), ("engine", ctypes.c_char_p), ("engineVersion", ctypes.c_uint32),
                    ("apiVersion", ctypes.c_uint32)]

    class CreateInfo(ctypes.Structure):
        _fields_ = [("sType", ctypes.c_int), ("pNext", ctypes.c_void_p), ("flags", ctypes.c_uint32),
                    ("app", ctypes.POINTER(AppInfo)), ("layers", ctypes.c_uint32), ("layerNames", ctypes.c_void_p),
                    ("exts", ctypes.c_uint32), ("extNames", ctypes.c_void_p)]
    app = AppInfo(0, None, b"cornerplay", 1, b"cornerplay", 1, (1 << 22) | (1 << 12))
    info = CreateInfo(1, None, 0, ctypes.pointer(app), 0, None, 0, None)
    inst = ctypes.c_void_p()
    if vk.vkCreateInstance(ctypes.byref(info), None, ctypes.byref(inst)) != 0:
        return 0
    count = ctypes.c_uint32(0)
    ok = vk.vkEnumeratePhysicalDevices(inst, ctypes.byref(count), None) == 0
    vk.vkDestroyInstance(inst, None)
    return count.value if ok else 0


_vulkan_cache = None


def vulkan_problem() -> str:
    """"" when Vulkan has a GPU to draw with, else what is wrong and what to install."""
    global _vulkan_cache
    if _vulkan_cache is not None:
        return _vulkan_cache
    import glob
    msg = ""
    if _vulkan_gpus() <= 0:
        # Name the driver for a GPU whose Vulkan driver is not installed (the one that is on).
        icds = " ".join(os.path.basename(p).lower() for d in ("/usr/share/vulkan/icd.d", "/etc/vulkan/icd.d",
                                                                 os.path.expanduser("~/.local/share/vulkan/icd.d"))
                        for p in glob.glob(os.path.join(d, "*.json")))
        vendors = set()
        for f in glob.glob("/sys/class/drm/card*/device/vendor"):
            try:
                vendors.add(open(f).read().strip())
            except OSError:
                pass
        missing = [_VENDORS[v] for v in sorted(vendors) if v in _VENDORS and _VENDORS[v][1] not in icds]
        fix = (f"Install the {missing[0][0]} Vulkan driver: sudo pacman -S {missing[0][2]}" if missing
               else "Check that your GPU's Vulkan driver is installed and the GPU is switched on.")
        msg = "Vulkan has no GPU to draw with, so Windows games and the Battle.net app will crash. " + fix
    _vulkan_cache = msg
    return msg


def forget_vulkan_check():
    global _vulkan_cache
    _vulkan_cache = None


def extras() -> list:
    """Optional wrappers the user switched on in Settings."""
    out = []
    if opt("gamemode") and shutil.which("gamemoderun"):
        out.append("gamemoderun")
    if (opt("mangohud") or opt("show_fps") or (PROFILES.get(opt("perf") or "") or {}).get("fps")) \
            and shutil.which("mangohud"):
        out.append("mangohud")
    return out


def wrapper_argv() -> list:
    """argv prefix that runs a Windows executable."""
    _, path = compat()
    return [*extras(), path]


def wrapper_string() -> str:
    """Same as wrapper_argv, as one shell-quoted string for --wrapper flags."""
    return shlex.join(wrapper_argv())
