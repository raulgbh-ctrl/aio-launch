"""Games and apps added by hand: any Windows program (runs through Proton, in its own prefix)
or Linux program. Kept in ~/.config/cornerplay/custom_games.json. Removing one only takes it
out of Cornerplay; its files stay where they are."""
import os
import shlex
import uuid

from ..config import CONFIG_DIR, read_json, write_json
from ..runner import StoreError, extras, perf_env, user_env, wine_env, wrapper_argv
from .base import Command, Game, Store

FILE = CONFIG_DIR / "custom_games.json"
WINDOWS_EXT = (".exe", ".msi", ".bat", ".lnk")


def _is_program(path):
    """A Linux binary (ELF) or a script (#!), and allowed to run. A file merely marked executable
    (installers often mark everything) is not enough."""
    if not os.access(path, os.X_OK):
        return False
    try:
        with open(path, "rb") as f:
            head = f.read(4)
    except OSError:
        return False
    return head == b"\x7fELF" or head[:2] == b"#!"


def entries():
    data = read_json(FILE) or []
    return [e for e in data if isinstance(e, dict) and e.get("id") and e.get("exe")]


def add(exe, title="", args=""):
    exe = os.path.expanduser(exe.strip())
    if not os.path.isfile(exe):
        raise StoreError("That file does not exist")
    kind = "windows" if exe.lower().endswith(WINDOWS_EXT) else "linux"
    if kind == "linux" and not _is_program(exe):
        raise StoreError("That file is not a program: pick the game's executable, start script or AppImage")
    if not title.strip():
        stem = os.path.splitext(os.path.basename(exe))[0]
        parent = os.path.basename(os.path.dirname(exe))
        # "Game/Game.exe" or "Some Game/bin/launcher" -> the folder name reads better than "launcher"
        title = parent if stem.lower() in ("game", "launcher", "start", "run", "play", "bin") or len(stem) < 3 else stem
    entry = {"id": uuid.uuid4().hex[:10], "title": title.strip()[:80], "exe": exe, "args": args.strip(), "kind": kind}
    data = entries() + [entry]
    write_json(FILE, data)
    return entry


def remove(gid):
    write_json(FILE, [e for e in entries() if e["id"] != gid])


class Custom(Store):
    id = "custom"
    name = "Other games"
    color = "#9aa0a6"
    login_kind = "none"
    in_accounts = False

    def problem(self):
        return ""

    def logged_in(self):
        return True

    def account(self):
        return ""

    def fetch(self):
        games = []
        for e in entries():
            g = Game(store=self.id, id=e["id"], title=e["title"], installed=os.path.exists(e["exe"]),
                     install_path=os.path.dirname(e["exe"]))
            g.extra.update(kind=e.get("kind", "windows"), exe=e["exe"], platform="linux" if e.get("kind") == "linux" else "windows")
            games.append(g)
        return games

    def install(self, game):
        raise StoreError("This game was added by hand: its files are already on this PC")

    def uninstall(self, game):
        remove(game.id)  # out of the library; the files stay
        return None

    def launch(self, game):
        e = next((x for x in entries() if x["id"] == game.id), None)
        if not e or not os.path.exists(e["exe"]):
            raise StoreError("The program is not there any more; remove the game and add it again")
        args = shlex.split(e.get("args") or "")
        cwd = os.path.dirname(e["exe"])
        if e.get("kind") == "linux":
            env = {k: v for k, v in perf_env(self.id, game.id).items() if k == "MANGOHUD_CONFIG"}
            env.update(user_env())
            return Command([*extras(), e["exe"], *args], env=env, cwd=cwd)
        return Command([*wrapper_argv(), e["exe"], *args], env=wine_env(self.id, game.id), cwd=cwd)
