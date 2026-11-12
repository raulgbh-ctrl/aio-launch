"""Play on another screen: Sunshine on the gaming PC, Moonlight on the TV, laptop or Deck.

- This PC hosts (Sunshine): add_to_sunshine() puts "Cornerplay (TV mode)" and your favourite
  games into Sunshine's app list (~/.config/sunshine/apps.json), so Moonlight anywhere in the
  house can start them. Entries Cornerplay made before are replaced, everything else is kept.
- This PC plays (Moonlight): play_on_host() wakes the gaming PC (Wake-on-LAN, when its network
  card's MAC address is set) and starts Moonlight streaming that PC's Cornerplay TV mode.
In the Flatpak, Sunshine's file and Moonlight are on the host: reached through flatpak-spawn.
"""
import json
import os
import re
import shlex
import socket
import subprocess
from pathlib import Path

from . import host

TV_APP = "Cornerplay (TV mode)"
MARK = "cornerplay"   # entries whose command runs Cornerplay are Cornerplay's own
MOONLIGHT_FLATPAK = "com.moonlight_stream.Moonlight"


# --- Wake-on-LAN -------------------------------------------------------------------------
def mac_bytes(mac: str) -> bytes:
    digits = re.sub(r"[^0-9a-fA-F]", "", mac or "")
    if len(digits) != 12:
        raise ValueError("a MAC address has 12 hex digits, like 3c:7c:3f:12:34:56")
    return bytes.fromhex(digits)


def magic_packet(mac: str) -> bytes:
    return b"\xff" * 6 + mac_bytes(mac) * 16


def wake(mac: str, broadcast: str = "255.255.255.255"):
    """Send the Wake-on-LAN magic packet (UDP 9, and 7 for older cards)."""
    packet = magic_packet(mac)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        for port in (9, 7):
            s.sendto(packet, (broadcast, port))


# --- Moonlight (this PC plays) -----------------------------------------------------------------
def moonlight() -> list:
    """The command that runs Moonlight, or [] when it is not installed."""
    for name in ("moonlight", "moonlight-qt"):
        exe = host.which(name)
        if exe:
            return [exe]
    try:
        r = subprocess.run(host.argv(["flatpak", "info", MOONLIGHT_FLATPAK]), capture_output=True, timeout=10)
        if r.returncode == 0:
            return ["flatpak", "run", MOONLIGHT_FLATPAK]
    except (OSError, subprocess.TimeoutExpired):
        pass
    return []


def stream_argv(pc: str, app: str = TV_APP) -> list:
    exe = moonlight()
    if not exe:
        raise RuntimeError("Moonlight is not installed (Flathub: com.moonlight_stream.Moonlight)")
    if not pc or not re.fullmatch(r"[A-Za-z0-9.:\-\[\]_]+", pc):
        raise RuntimeError("the gaming PC's name or address looks wrong")
    return host.argv(exe + ["stream", pc, app])


# --- Sunshine (this PC hosts) --------------------------------------------------------------------
HOST_FILE = "${XDG_CONFIG_HOME:-$HOME/.config}/sunshine/apps.json"   # as the host's shell spells it


def sunshine_file() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "sunshine" / "apps.json"


def _read() -> str | None:
    if not host.IN_FLATPAK:
        try:
            return sunshine_file().read_text()
        except OSError:
            return None
    r = subprocess.run(host.argv(["sh", "-c", f'cat "{HOST_FILE}" 2>/dev/null']), capture_output=True, text=True, timeout=15)
    return r.stdout if r.returncode == 0 else None


def _write(text: str):
    if not host.IN_FLATPAK:
        f = sunshine_file()
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".json.tmp")
        tmp.write_text(text)
        tmp.replace(f)
        return
    script = f'f="{HOST_FILE}"; mkdir -p "$(dirname "$f")" && printf "%s" "$1" > "$f.tmp" && mv "$f.tmp" "$f"'
    subprocess.run(host.argv(["sh", "-c", script, "sh", text]), check=True, timeout=15)


def _launcher() -> list:
    if host.IN_FLATPAK:
        return ["flatpak", "run", host.APP_ID]
    import shutil
    exe = shutil.which("cornerplay") or str(Path.home() / ".local/bin/cornerplay")
    return [exe]


def _ours(app: dict) -> bool:
    cmds = " ".join([str(app.get("cmd") or "")] + [str(c) for c in app.get("detached") or []])
    return MARK in cmds.lower() and (app.get("name") == TV_APP or "--play" in cmds or "--tv" in cmds)


def sunshine_apps(existing: dict, games: list, icon: str = "") -> dict:
    """Sunshine's apps.json with Cornerplay's entries replaced: TV mode, then games
    [{"key", "title"}]. Detached: Cornerplay hands over to a copy already running."""
    data = dict(existing) if isinstance(existing, dict) else {}
    apps = [a for a in (data.get("apps") or []) if isinstance(a, dict) and not _ours(a)]
    run = " ".join(shlex.quote(a) for a in _launcher())
    tv = {"name": TV_APP, "detached": [f"setsid {run} --tv"], "auto-detach": "true"}
    if icon:
        tv["image-path"] = icon
    ours = [tv]
    for g in games[:30]:
        ours.append({"name": g["title"][:60], "cmd": f"{run} --play {shlex.quote(g['key'])}", "auto-detach": "true"})
    data.setdefault("env", {"PATH": "$(PATH):$(HOME)/.local/bin"})
    data["apps"] = apps + ours
    return data


def add_to_sunshine(games: list, icon: str = "") -> int:
    """Write Cornerplay's entries into Sunshine's app list; returns how many. Sunshine reads the
    file when it starts (or when an app is saved in its web page)."""
    text = _read()
    try:
        existing = json.loads(text) if text and text.strip() else {}
    except ValueError:
        raise RuntimeError("Sunshine's apps.json is not valid JSON; left as it is")
    data = sunshine_apps(existing, games, icon)
    _write(json.dumps(data, indent=2))
    return 1 + min(len(games), 30)
