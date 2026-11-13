"""Prism Launcher: your Minecraft instances as games.

Every instance in Prism Launcher (installed, or Prism Launcher from Flathub) is a game in
Cornerplay: its name, the Minecraft version and mod loader (Fabric, Forge, NeoForge, Quilt), how
many mods it has, and the time Prism counted for it. Play starts the instance through Prism
(`prismlauncher --launch <instance>`), which signs in, downloads what is missing and keeps
counting the time; making, modding and removing instances stays in Prism ("Open in Prism").

Where Prism keeps them: ~/.local/share/PrismLauncher/instances, or the Flatpak's
~/.var/app/org.prismlauncher.PrismLauncher/data/PrismLauncher/instances, or the folder set in
Prism's settings (InstanceDir in prismlauncher.cfg).
"""
import configparser
import json
import os
from pathlib import Path

from .. import host
from ..config import HOME
from ..runner import StoreError
from .base import Command, Game, Store

FLATPAK_ID = "org.prismlauncher.PrismLauncher"
LOADERS = {"net.fabricmc.fabric-loader": "Fabric", "net.minecraftforge": "Forge", "net.neoforged": "NeoForge",
           "org.quiltmc.quilt-loader": "Quilt", "com.mumfrey.liteloader": "LiteLoader"}


def data_dirs():
    """Prism's data folders on this PC: [(folder, "native" | "flatpak")]."""
    xdg = Path(os.environ.get("XDG_DATA_HOME") or HOME / ".local/share")
    out = []
    for d, kind in ((xdg / "PrismLauncher", "native"), (HOME / ".var/app" / FLATPAK_ID / "data/PrismLauncher", "flatpak")):
        if d.is_dir():
            out.append((d, kind))
    return out


def _ini(path):
    """An instance.cfg / prismlauncher.cfg as a dict (they may lack a [General] header)."""
    try:
        text = Path(path).read_text(errors="replace")
    except OSError:
        return {}
    if not text.lstrip().startswith("["):
        text = "[General]\n" + text
    cp = configparser.ConfigParser(interpolation=None, strict=False)
    try:
        cp.read_string(text)
    except configparser.Error:
        return {}
    return {k: v.strip().strip('"') for k, v in (cp["General"].items() if cp.has_section("General") else [])}


def instances_dir(data):
    folder = _ini(data / "prismlauncher.cfg").get("instancedir") or "instances"
    p = Path(os.path.expanduser(folder))
    return p if p.is_absolute() else data / p


def _int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def read_instance(folder):
    """One instance: {"id", "name", "version", "loader", "mods", "seconds", "last", "icon", "group"}, or None."""
    cfg = _ini(folder / "instance.cfg")
    if not cfg:
        return None
    version, loader = "", ""
    try:
        pack = json.loads((folder / "mmc-pack.json").read_text())
        for c in pack.get("components") or []:
            uid = c.get("uid", "")
            if uid == "net.minecraft":
                version = str(c.get("version") or "")
            elif uid in LOADERS:
                loader = LOADERS[uid]
    except (OSError, ValueError, AttributeError):
        pass
    mods = 0
    for game_dir in (".minecraft", "minecraft"):
        md = folder / game_dir / "mods"
        if md.is_dir():
            mods = sum(1 for f in md.iterdir() if f.name.endswith(".jar"))  # .jar.disabled: turned off in Prism
            break
    return {"id": folder.name, "name": cfg.get("name") or folder.name, "version": version, "loader": loader,
            "mods": mods, "seconds": _int(cfg.get("totaltimeplayed")), "last": _int(cfg.get("lastlaunchtime")) // 1000,
            "icon": cfg.get("iconkey") or "", "notes": cfg.get("notes", "")[:500]}


def scan():
    """[(instance, data folder, kind)] for every instance of every Prism on this PC."""
    out = []
    for data, kind in data_dirs():
        root = instances_dir(data)
        if not root.is_dir():
            continue
        for d in sorted(root.iterdir()):
            if d.is_dir() and not d.name.startswith(".") and d.name != "_LAUNCHER_TEMP":
                inst = read_instance(d)
                if inst:
                    out.append((inst, data, kind))
    return out


def prism_argv(kind):
    if kind == "flatpak":
        return host.argv(["flatpak", "run", FLATPAK_ID]) if host.which("flatpak") else None
    exe = host.which("prismlauncher") or host.which("PrismLauncher")
    return host.argv([exe]) if exe else None


class Prism(Store):
    id = "prism"
    name = "Prism Launcher"
    color = "#4ea064"
    tile = "#2f7a46"
    login_kind = "none"
    in_accounts = False
    external_installs = True

    def problem(self):
        if data_dirs() and not any(prism_argv(k) for _d, k in data_dirs()):
            return "Prism Launcher's folder is here but the program is not (sudo pacman -S prismlauncher, or Flathub)"
        return ""

    def logged_in(self):
        return bool(data_dirs())

    def account(self):
        return ""

    def fetch(self):
        games = []
        for inst, data, kind in scan():
            icon = data / "icons" / f"{inst['icon']}.png"
            g = Game(store=self.id, id=inst["id"], title=inst["name"], installed=True,
                     install_path=str(instances_dir(data) / inst["id"]),
                     cover_fallback=icon.as_uri() if inst["icon"] and icon.is_file() else "")
            what = " ".join(x for x in ("Minecraft " + inst["version"] if inst["version"] else "Minecraft", inst["loader"]) if x)
            g.extra.update(art_title="Minecraft", kind=kind, mc_version=inst["version"], loader=inst["loader"],
                           mods=inst["mods"], platform="linux", description=what + (f", {inst['mods']} mods" if inst["mods"] else ""),
                           steam_playtime=inst["seconds"], steam_last_played=inst["last"])
            games.append(g)
        return games

    def install(self, game):
        raise StoreError("Make new Minecraft instances in Prism Launcher; Cornerplay lists them by itself")

    def uninstall(self, game):
        raise StoreError("Remove instances in Prism Launcher (Delete), so its own records stay right")

    def launch(self, game):
        argv = prism_argv(game.extra.get("kind", "native"))
        if not argv:
            raise StoreError(self.problem() or "Prism Launcher is not installed")
        return Command([*argv, "--launch", game.id])

    def open_instance(self, game):
        """Prism's window, with the instance's folder in it (mods, worlds, resource packs)."""
        argv = prism_argv(game.extra.get("kind", "native"))
        if not argv:
            raise StoreError(self.problem() or "Prism Launcher is not installed")
        return Command([*argv, "--show", game.id])
