"""Health check: is everything a game needs in place? One row per check, with a fix.

Each row: {"id", "name", "ok": True/False/None (None = not needed here), "detail", "fix": {...}}
fix kinds: {"kind": "command", "command": "sudo pacman -S ..."}  (shown, copied; never run as root)
           {"kind": "action", "action": "<app slot name>", "arg": "...", "label": "..."}
"""
import os

from . import host, runner, storage
from .config import find_tool, settings
from .runner import StoreError


def _pm_install(pkgs):
    if host.which("pacman"):
        return f"sudo pacman -S --needed {pkgs}"
    if host.which("apt-get"):
        return f"sudo apt-get install {pkgs}"
    if host.which("dnf"):
        return f"sudo dnf install {pkgs}"
    return pkgs


def checks(stores, gamepad_available=True):
    rows = []

    def add(cid, name, ok, detail, fix=None):
        rows.append({"id": cid, "name": name, "ok": ok, "detail": detail, "fix": fix or {}})

    # Graphics: Vulkan with a GPU that is on
    gpus = runner._vulkan_gpus()
    vk = runner.vulkan_problem()
    if gpus > 0:
        add("vulkan", "Graphics (Vulkan)", True, f"{gpus} GPU{'s' if gpus > 1 else ''} ready for Windows games")
    else:
        cmd = vk.split("sudo ", 1)[1] if "sudo " in vk else ""
        add("vulkan", "Graphics (Vulkan)", False, vk.split(". Install")[0] + ".",
            {"kind": "command", "command": "sudo " + cmd} if cmd else {})

    # Flatpak: Proton runs 32-bit code and needs Flatpak's 32-bit runtime and graphics drivers.
    # Installed from Flathub they come along by themselves; from a .flatpak file they may not.
    if host.IN_FLATPAK:
        missing = [ext for ext, probe in (("org.freedesktop.Platform.Compat.i386", "/app/lib/i386-linux-gnu/ld-linux.so.2"),
                                          ("org.freedesktop.Platform.GL32.default", "/app/lib/i386-linux-gnu/GL/default/lib"))
                   if not os.path.exists(probe)]
        add("flatpak32", "32-bit support (Flatpak)", not missing,
            "Installed" if not missing else "Missing: Windows games and Battle.net will not start",
            {} if not missing else {"kind": "command", "command": "flatpak install --user flathub "
                                    + " ".join(f"{e}//{host.FLATPAK_BASE}" for e in missing)})

    # Proton runner
    try:
        kind, path = runner.compat()
        add("umu", "Proton runner (umu-launcher)", True, f"{os.path.basename(path)} found" + ("" if kind == "umu" else " (plain Wine)"))
    except StoreError as e:
        add("umu", "Proton runner (umu-launcher)", False, str(e),
            {"kind": "command", "command": _pm_install("umu-launcher")})

    # Proton version
    versions = runner.proton_versions()
    add("proton", "Proton versions", bool(versions), f"{len(versions)} available" if versions else "None found",
        {} if versions else {"kind": "action", "action": "downloadGe", "label": "Get GE-Proton"})

    # Store tools
    for tool, store in (("legendary", "Epic"), ("gogdl", "GOG"), ("nile", "Amazon")):
        found = find_tool(tool)
        add(f"tool-{tool}", f"{store} tool ({tool})", bool(found), "Installed" if found else "Missing",
            {} if found else {"kind": "action", "action": "fetchBackends", "label": "Download"})

    # RetroArch, when there are ROM folders
    from .stores import retro
    if retro.rom_dirs():
        argv, folders = retro.retroarch()
        systems = sorted({sid for sid, _ in retro.scan()})
        no_core = [retro.SYSTEM_NAMES[s] for s in systems if argv and not retro.find_core(s, folders)]
        add("retroarch", "RetroArch (retro games)", bool(argv) and not no_core,
            ("Missing" if not argv else f"No core yet for: {', '.join(no_core)} (RetroArch > Online Updater > Core Downloader)"
             if no_core else f"Ready for {len(systems)} system{'s' if len(systems) != 1 else ''}"),
            {} if argv else {"kind": "command", "command": _pm_install("retroarch")})

    # Steam client
    steam = stores.get("steam")
    has_steam = bool(steam and steam.client())
    add("steam", "Steam", has_steam, "Installed" if has_steam else "Not installed",
        {} if has_steam else {"kind": "command", "command": _pm_install("steam")})

    # Sign-ins
    for sid in ("steam", "epic", "gog", "amazon", "battlenet", "humble"):
        s = stores.get(sid)
        if not s:
            continue
        try:
            logged = s.logged_in()
        except Exception:
            logged = False
        add(f"signin-{sid}", f"{s.name} sign-in", logged if logged else None,
            "Connected" if logged else "Not connected (only needed if you use it)",
            {} if logged else {"kind": "action", "action": "loginBegin", "arg": sid, "label": "Sign in"})

    # Disk space where games go
    games_dir = str(settings.games_dir)
    probe = games_dir if os.path.isdir(games_dir) else os.path.expanduser("~")
    d = storage.drive(probe)
    if d:
        pct = d["free"] * 100 / max(1, d["total"])
        add("disk", "Space for games", pct >= 10,
            f"{storage.nice(d['free'])} free on {d['label']} ({pct:.0f}%)",
            {} if pct >= 10 else {"kind": "action", "action": "openStorage", "label": "Free up space"})

    # Save backups read where games keep saves from a YAML manifest
    if settings.get("save_backups"):
        try:
            import yaml  # noqa: F401
            add("yaml", "Save backups", True, "Ready (save locations for 20,000+ games)")
        except ImportError:
            add("yaml", "Save backups", False, "Needs PyYAML to read where games keep their saves",
                {"kind": "command", "command": _pm_install("python-yaml")})

    # Built-in sign-in window, controllers
    from PySide6.QtCore import QLibraryInfo
    from pathlib import Path
    qml = Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.QmlImportsPath))
    web = (qml / "QtWebEngine" / "qmldir").is_file()
    add("webengine", "Built-in sign-in window", web if web else None,
        "Available" if web else "Missing: sign-ins open your browser instead",
        {} if web else {"kind": "command", "command": _pm_install("qt6-webengine")})
    from . import sdl
    add("sdl", "Controller support (SDL2)", True if gamepad_available else False,
        "Ready" if gamepad_available else
        ("Being set up (downloading a private SDL2)" if sdl.can_fetch() else "SDL2 missing: controllers do nothing"),
        {} if gamepad_available or sdl.can_fetch() else {"kind": "command", "command": _pm_install("sdl2-compat")})
    return rows
