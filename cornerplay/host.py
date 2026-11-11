"""Running as a Flatpak: the sandbox has its own processes and programs, so what belongs to the
host (the Steam client, `pgrep` for it) is reached through `flatpak-spawn --host`. Outside a
Flatpak every helper here is a no-op."""
import os
import shutil
import subprocess

APP_ID = "io.github.raulgbh_ctrl.Cornerplay"
FLATPAK_ID = os.environ.get("FLATPAK_ID", "") if os.path.exists("/.flatpak-info") else ""
IN_FLATPAK = bool(FLATPAK_ID)
BUNDLED_BIN = "/app/lib/cornerplay/backends"  # legendary, gogdl, nile and umu-run shipped in the Flatpak

_which: dict = {}


def argv(cmd) -> list:
    """A command line that runs on the host."""
    return ["flatpak-spawn", "--host", *cmd] if IN_FLATPAK else list(cmd)


def which(name: str) -> str | None:
    """shutil.which, on the host. Remembered per run (asking the host costs a process)."""
    if not IN_FLATPAK:
        return shutil.which(name)
    if name not in _which:
        try:
            r = subprocess.run(argv(["sh", "-c", 'command -v "$1"', "sh", name]),
                               capture_output=True, text=True, timeout=10)
            _which[name] = r.stdout.strip() or None
        except (OSError, subprocess.TimeoutExpired):
            return None
    return _which[name]
