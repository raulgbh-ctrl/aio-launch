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


# Anti-cheat for Proton: Steam's free "Proton EasyAntiCheat Runtime" and "Proton BattlEye
# Runtime" tools. Steam points Proton at them for its own games; for the others Cornerplay does
# the same (Proton adds /v2/lib64 and /v1/lib64/wine to these folders itself). A game still only
# runs when its developer turned on anti-cheat support for Linux.
ANTICHEAT_RUNTIMES = {"PROTON_EAC_RUNTIME": ("Proton EasyAntiCheat Runtime", "1826330"),
                      "PROTON_BATTLEYE_RUNTIME": ("Proton BattlEye Runtime", "1161040")}


def anticheat_runtimes() -> dict:
    """{"PROTON_EAC_RUNTIME": folder, ...} for the runtimes installed in any Steam library."""
    from . import protons
    found = {}
    for root in protons.steam_roots():
        try:
            libs = protons._steam_libraries(root)
        except Exception:
            libs = [root]
        for lib in libs:
            for var, (folder, _appid) in ANTICHEAT_RUNTIMES.items():
                d = os.path.join(lib, "steamapps", "common", folder)
                if var not in found and os.path.isdir(d):
                    found[var] = d
    return found


def wine_env(store: str, game_id: str, umu_id: str = "umu-default") -> dict:
    """Environment for umu-run / wine for one game."""
    env = {"WINEPREFIX": prefix_path(store, game_id, create=True)}
    env.update(anticheat_runtimes())
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
    if opt("perf_log") and shutil.which("mangohud"):
        from . import perf
        hud += perf.hud_options(store, game_id, visible=bool(opt("mangohud") or opt("show_fps")))
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
    if settings.get("shader_warmup"):
        from . import shaders
        env.update(shaders.record_env(store, game_id))
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


GAMESCOPE_MODES = ("fullscreen", "fsr")
FSR_SCALE = 2 / 3  # FSR "Quality": the game draws at two thirds of the screen's size


def _in_gamescope() -> bool:
    """Already inside gamescope (Steam Deck Game Mode, a gamescope session): no need to nest it."""
    return os.environ.get("XDG_CURRENT_DESKTOP", "").lower() == "gamescope" or bool(os.environ.get("GAMESCOPE_WAYLAND_DISPLAY"))


def gamescope_argv(mangoapp: bool = False) -> list:
    """`gamescope ... --` for the current game, or [] when it is off, missing, or already around us.
    fullscreen: the game gets a full-screen window at the screen's resolution (fixes games that
    pick the wrong size or fight the desktop over full screen); fsr: it draws at two thirds of
    that and gamescope upscales with AMD FSR."""
    mode = opt("gamescope") or ""
    if mode not in GAMESCOPE_MODES or _in_gamescope():
        return []
    exe = shutil.which("gamescope")
    if not exe:
        return []
    argv = [exe, "-f"]
    size = settings.get("screen_size") or []
    if len(size) == 2 and all(isinstance(v, int) and v > 0 for v in size):
        w, h = size
        argv += ["-W", str(w), "-H", str(h)]
        if mode == "fsr":
            argv += ["-w", str(int(w * FSR_SCALE) // 2 * 2), "-h", str(int(h * FSR_SCALE) // 2 * 2)]
        else:
            argv += ["-w", str(w), "-h", str(h)]
    if mode == "fsr":
        argv += ["-F", "fsr"]
    if opt("gamescope_hdr"):
        argv.append("--hdr-enabled")
    if mangoapp:
        argv.append("--mangoapp")
    return [*argv, "--"]


def _wants_hud() -> bool:
    return bool(opt("mangohud") or opt("show_fps") or (opt("perf_log") and shutil.which("mangohud"))
                or (PROFILES.get(opt("perf") or "") or {}).get("fps"))


def extras(gamescope: bool = True) -> list:
    """Optional wrappers the user switched on in Settings, outermost first. Under gamescope the
    overlay is gamescope's own --mangoapp (MangoHud inside gamescope draws in the wrong place).
    gamescope=False for launchers that stay open (the Battle.net app)."""
    out = gamescope_argv(mangoapp=_wants_hud() and bool(shutil.which("mangoapp"))) if gamescope else []
    if opt("gamemode") and shutil.which("gamemoderun"):
        out.append("gamemoderun")
    if _wants_hud() and "--mangoapp" not in out and shutil.which("mangohud"):
        out.append("mangohud")
    return out


def wrapper_argv(gamescope: bool = True) -> list:
    """argv prefix that runs a Windows executable."""
    _, path = compat()
    return [*extras(gamescope), path]


def wrapper_string() -> str:
    """Same as wrapper_argv, as one shell-quoted string for --wrapper flags."""
    return shlex.join(wrapper_argv())
