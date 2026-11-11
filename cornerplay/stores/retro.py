"""Retro games: ROMs in your folders, played through RetroArch.

Point Cornerplay at one or more ROM folders (Settings > Library). Each ROM becomes a game
with box art from the libretro thumbnail server (matched by the ROM's name, as No-Intro and
Redump name them), playtime, favourites and TV mode like the rest. The system comes from the
file type, or from the folder's name for types several systems share (.iso, .chd, .zip).
It runs in RetroArch (installed, or RetroArch from Flathub) with the first core it has for
that system, full screen.
"""
import hashlib
import os
import re
from pathlib import Path

from .. import host
from ..config import HOME, XDG_CONFIG, settings
from ..runner import StoreError
from .base import Command, Game, Store

# system id: (libretro thumbnail folder, cores in order of preference, file types, folder-name hints)
SYSTEMS = {
    "nes": ("Nintendo - Nintendo Entertainment System", ["mesen", "nestopia", "fceumm"], (".nes", ".fds", ".unf"), ("nes", "famicom")),
    "snes": ("Nintendo - Super Nintendo Entertainment System", ["snes9x", "bsnes", "bsnes_hd_beta"], (".sfc", ".smc"), ("snes", "superfamicom", "sfc")),
    "gb": ("Nintendo - Game Boy", ["gambatte", "sameboy", "mgba"], (".gb",), ("gb", "gameboy")),
    "gbc": ("Nintendo - Game Boy Color", ["gambatte", "sameboy", "mgba"], (".gbc",), ("gbc", "gameboycolor")),
    "gba": ("Nintendo - Game Boy Advance", ["mgba", "vba_next", "vbam"], (".gba",), ("gba", "gameboyadvance")),
    "n64": ("Nintendo - Nintendo 64", ["mupen64plus_next", "parallel_n64"], (".n64", ".z64", ".v64"), ("n64", "nintendo64")),
    "nds": ("Nintendo - Nintendo DS", ["melonds", "melondsds", "desmume"], (".nds",), ("nds", "ds")),
    "md": ("Sega - Mega Drive - Genesis", ["genesis_plus_gx", "picodrive"], (".md", ".gen", ".smd"), ("genesis", "megadrive", "md")),
    "sms": ("Sega - Master System - Mark III", ["genesis_plus_gx", "picodrive"], (".sms",), ("mastersystem", "sms")),
    "gg": ("Sega - Game Gear", ["genesis_plus_gx"], (".gg",), ("gamegear", "gg")),
    "psx": ("Sony - PlayStation", ["swanstation", "mednafen_psx_hw", "mednafen_psx", "pcsx_rearmed"], (".cue", ".pbp", ".m3u"), ("psx", "ps1", "playstation")),
    "psp": ("Sony - PlayStation Portable", ["ppsspp"], (".cso",), ("psp",)),
    "pce": ("NEC - PC Engine - TurboGrafx 16", ["mednafen_pce_fast", "mednafen_pce"], (".pce",), ("pce", "pcengine", "turbografx", "tg16")),
    "a2600": ("Atari - 2600", ["stella", "stella2014"], (".a26",), ("atari2600", "2600")),
    "dc": ("Sega - Dreamcast", ["flycast"], (".gdi", ".cdi"), ("dreamcast", "dc")),
    "arcade": ("FBNeo - Arcade Games", ["fbneo", "mame2003_plus", "mame"], (), ("arcade", "fbneo", "mame")),
}
SHARED = (".iso", ".chd", ".zip", ".7z", ".bin")  # many systems use these: the folder's name decides
SYSTEM_NAMES = {"nes": "NES", "snes": "SNES", "gb": "Game Boy", "gbc": "Game Boy Color", "gba": "Game Boy Advance",
                "n64": "Nintendo 64", "nds": "Nintendo DS", "md": "Mega Drive / Genesis", "sms": "Master System",
                "gg": "Game Gear", "psx": "PlayStation", "psp": "PSP", "pce": "PC Engine", "a2600": "Atari 2600",
                "dc": "Dreamcast", "arcade": "Arcade"}
FLATPAK_ID = "org.libretro.RetroArch"


def rom_dirs():
    return [Path(os.path.expanduser(d)) for d in (settings.get("rom_dirs") or []) if str(d).strip()]


def _hint(path, root):
    """The system a ROM's folders name ("ROMs/snes/...", "PlayStation"), or ""."""
    parts = [re.sub(r"[^a-z0-9]", "", p.lower()) for p in Path(os.path.relpath(path.parent, root)).parts]
    for part in reversed(parts):
        for sid, (_, _, _, hints) in SYSTEMS.items():
            if part in hints:
                return sid
    return ""


def system_of(path, root):
    ext = path.suffix.lower()
    hint = _hint(path, root)
    if ext in SHARED:
        return hint if hint and (ext != ".zip" or hint == "arcade" or hint in ("nes", "snes", "gb", "gbc", "gba", "md", "sms", "gg", "pce", "a2600")) else ""
    for sid, (_, _, exts, _) in SYSTEMS.items():
        if ext in exts:
            return sid
    return ""


def display_title(stem):
    """'Super Metroid (Japan, USA) (En,Ja)' -> 'Super Metroid'."""
    t = re.sub(r"\s*[\(\[][^\)\]]*[\)\]]", "", stem).strip()
    return t or stem


def thumbnail(sid, stem):
    folder = SYSTEMS[sid][0]
    name = re.sub(r'[&*/:`<>?\\|"]', "_", stem)
    from urllib.parse import quote
    return f"https://thumbnails.libretro.com/{quote(folder)}/Named_Boxarts/{quote(name)}.png"


def scan():
    """[(system, path)] for every ROM in the ROM folders; multi-disc games once (their .m3u)."""
    out = []
    for root in rom_dirs():
        if not root.is_dir():
            continue
        for base, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            have_m3u = any(f.lower().endswith(".m3u") for f in files)
            for f in sorted(files):
                p = Path(base) / f
                if have_m3u and p.suffix.lower() in (".cue", ".chd", ".pbp"):
                    continue  # the discs of a game listed by its .m3u
                sid = system_of(p, root)
                if sid:
                    out.append((sid, p))
    return out


def retroarch():
    """(argv prefix, cores folders) for the RetroArch on this PC, or (None, []). From inside
    Cornerplay's Flatpak, RetroArch is a program on the host and is started there."""
    exe = host.which("retroarch")
    if exe:
        config = HOME / ".config" if host.IN_FLATPAK else XDG_CONFIG
        return host.argv([exe]), [config / "retroarch/cores", Path("/usr/lib/libretro"), Path("/usr/lib64/libretro"),
                                  Path("/usr/lib/x86_64-linux-gnu/libretro"), Path("/app/lib/libretro")]
    if host.which("flatpak") and (HOME / ".var/app" / FLATPAK_ID).is_dir():
        return host.argv(["flatpak", "run", FLATPAK_ID]), [HOME / ".var/app" / FLATPAK_ID / "config/retroarch/cores"]
    return None, []


def _exists(path):
    if os.path.isfile(path):
        return True
    if host.IN_FLATPAK:  # /usr/lib/libretro on the host is out of the sandbox's sight
        import subprocess
        try:
            return subprocess.run(host.argv(["test", "-f", str(path)]), timeout=5).returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False
    return False


def find_core(sid, folders):
    for core in SYSTEMS[sid][1]:
        for d in folders:
            p = Path(d) / f"{core}_libretro.so"
            if _exists(p):
                return str(p)
    return ""


class Retro(Store):
    id = "retro"
    name = "Retro games"
    color = "#8e7cc3"
    tile = "#6a5aa3"
    login_kind = "none"
    in_accounts = False

    def problem(self):
        if not rom_dirs():
            return ""
        return "" if retroarch()[0] else "RetroArch is not installed (sudo pacman -S retroarch, or RetroArch from Flathub)"

    def logged_in(self):
        return True

    def account(self):
        return ""

    def fetch(self):
        games = []
        for sid, path in scan():
            gid = sid + "-" + hashlib.sha1(str(path).encode()).hexdigest()[:12]
            g = Game(store=self.id, id=gid, title=display_title(path.stem), cover=thumbnail(sid, path.stem),
                     installed=True, install_path=str(path.parent))
            g.extra.update(rom=str(path), system=sid, systemName=SYSTEM_NAMES[sid], platform="linux")
            games.append(g)
        return games

    def install(self, game):
        raise StoreError("Retro games are your own ROM files: they are already on this PC")

    def uninstall(self, game):
        raise StoreError("Cornerplay does not delete ROMs; remove the file yourself if you want it gone")

    def launch(self, game):
        rom = game.extra.get("rom", "")
        if not rom or not os.path.isfile(rom):
            raise StoreError("The ROM is not there any more")
        argv, folders = retroarch()
        if not argv:
            raise StoreError(self.problem() or "RetroArch is not installed")
        sid = game.extra.get("system", "")
        core = find_core(sid, folders)
        if not core:
            wanted = ", ".join(SYSTEMS[sid][1][:2])
            raise StoreError(f"RetroArch has no core for {SYSTEM_NAMES.get(sid, sid)} yet: install one ({wanted}) "
                             "from RetroArch's Online Updater > Core Downloader, or your package manager")
        return Command([*argv, "-f", "-L", core, rom], cwd=os.path.dirname(rom))
