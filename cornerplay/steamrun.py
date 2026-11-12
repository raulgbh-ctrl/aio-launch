"""Which Steam games are running right now.

Steam starts every game through its "reaper" helper: `reaper SteamLaunch AppId=<id> -- ...`.
Finding those processes tells which games run, however they were started (from Cornerplay,
from Steam, from Game Mode). In the Flatpak the host's processes are not visible, so the
host's pgrep is asked instead.
"""
import os
import re
import subprocess

from . import host

# Only Steam's reaper itself: its command line starts with the reaper (a path to it, or the
# name). Anything else that merely mentions these words (a terminal, an editor) never counts.
_APPID = re.compile(r"^\S*\breaper\s+SteamLaunch\s+AppId=(\d+)(?:\s|$)")


def _from_cmdlines(lines):
    out = set()
    for line in lines:
        m = _APPID.search(line)
        if m and m.group(1) != "0":
            out.add(m.group(1))
    return out


def running() -> set:
    """App ids of the Steam games running now (empty when none, or when it cannot be told)."""
    if host.IN_FLATPAK:
        try:
            r = subprocess.run(host.argv(["pgrep", "-af", "SteamLaunch"]), capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            return set()
        return _from_cmdlines(line.split(" ", 1)[-1] for line in r.stdout.splitlines())  # "<pid> <cmdline>"
    lines = []
    try:
        pids = [p for p in os.listdir("/proc") if p.isdigit()]
    except OSError:
        return set()
    for pid in pids:
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                raw = f.read(4096)
        except OSError:
            continue
        if b"SteamLaunch" in raw:
            lines.append(raw.replace(b"\0", b" ").decode("utf-8", "replace"))
    return _from_cmdlines(lines)


_QUIT = r'''
tree() { for c in $(pgrep -P "$1"); do tree "$c"; done; kill -"$2" "$1" 2>/dev/null; }
found=1
for r in $(pgrep -f "^[^ ]*reaper SteamLaunch AppId=$1( |\$)"); do tree "$r" "$2"; found=0; done
exit $found
'''


def quit(appid: str, force: bool = False) -> bool:
    """Close a running Steam game: its whole process tree under Steam's reaper, deepest first
    (SIGTERM asks, SIGKILL ends it now). False when it was not found."""
    if not str(appid).isdigit():
        return False
    sig = "KILL" if force else "TERM"
    try:
        r = subprocess.run(host.argv(["sh", "-c", _QUIT, "sh", str(appid), sig]), capture_output=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0
