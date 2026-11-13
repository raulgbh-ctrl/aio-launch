"""Is there a newer Cornerplay? Asks GitHub for the latest release, at most once a day.

Only installed copies are offered an update; a copy that runs from a git checkout
(development) is updated with git instead. A Flatpak installed from Flathub is updated by
Flatpak itself; one installed from the .flatpak file on GitHub has nothing to update it, so it
is offered the new .flatpak file the same way the .run copy is offered the new installer.
"""
import os
import time
from pathlib import Path

from . import __version__, host
from .net import download_checked, requests

from .config import CACHE_DIR, read_json, write_json

REPO = "raulgbh-ctrl/cornerplay"
FILE = CACHE_DIR / "update_check.json"
TTL = 6 * 3600       # a known newer release is asked about again after 6 hours
RECHECK = 3600       # no newer release known yet: ask again after an hour


def from_source():
    return (Path(__file__).resolve().parent.parent / ".git").exists()


ROOT = Path(__file__).resolve().parent.parent


def _git(*args, timeout=30):
    import subprocess
    r = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout.strip()


def git_latest():
    """A git checkout: {"version", "behind", "dirty", "branch", "kind": "git", "url"} when the branch
    it follows has newer commits, else {}. Fetches first (call off the main thread)."""
    try:
        code, upstream = _git("rev-parse", "--abbrev-ref", "@{u}")
        if code or not upstream:
            return {}
        if _git("fetch", "--quiet", upstream.split("/", 1)[0], timeout=60)[0]:
            return {}
        code, behind = _git("rev-list", "--count", "HEAD..@{u}")
        if code or not behind.isdigit() or int(behind) == 0:
            return {}
        version = __version__
        code, init = _git("show", "@{u}:cornerplay/__init__.py")
        for line in init.splitlines() if not code else []:
            if line.startswith("__version__"):
                version = line.split("=", 1)[1].strip().strip('"')
        dirty = bool(_git("status", "--porcelain", "--untracked-files=no")[1])
        return {"version": version, "behind": int(behind), "dirty": dirty, "branch": upstream, "kind": "git",
                "url": f"https://github.com/{REPO}/commits/{upstream.split('/', 1)[-1]}"}
    except (OSError, ValueError, __import__("subprocess").TimeoutExpired):
        return {}


def git_pull_argv():
    return ["git", "-C", str(ROOT), "pull", "--ff-only", "--quiet"]


def mode():
    """How this copy gets new versions: "git", "package" (pacman / Flatpak) or "self" (the .run)."""
    if from_source():
        return "git"
    if managed() and not (host.IN_FLATPAK and flatpak_bundle()):
        return "package"
    return "self"


def managed():
    """Installed by a package manager (the AUR package lives in /usr/lib) or Flatpak: that is
    what updates it. Installing the .run on top would leave a second copy shadowing it."""
    here = str(Path(__file__).resolve())
    return here.startswith(("/usr/", "/app/", "/opt/"))


_bundle = None


def flatpak_bundle():
    """{"installation": "user"/"system"} when this is a Flatpak installed from a .flatpak file
    (its remote is not Flathub, so `flatpak update` never finds a new version), else {}.
    Asks the host's flatpak, so call it off the main thread."""
    global _bundle
    if _bundle is None:
        _bundle = {}
        if host.IN_FLATPAK:
            import subprocess
            try:
                out = subprocess.run(host.argv(["flatpak", "info", host.APP_ID]), capture_output=True,
                                     text=True, timeout=15).stdout
            except (OSError, subprocess.TimeoutExpired):
                out = ""
            info = {}
            for line in out.splitlines():
                key, sep, value = line.partition(":")
                if sep:
                    info[key.strip().lower()] = value.strip()
            origin, where = info.get("origin", ""), info.get("installation", "")
            if origin and "flathub" not in origin.lower() and where in ("user", "system"):
                _bundle = {"installation": where}
    return _bundle


def offered():
    """Can this copy be updated from GitHub's releases: the .run copy or a .flatpak bundle."""
    if from_source():
        return False
    return not managed() or (host.IN_FLATPAK and bool(flatpak_bundle()))


ASSET_PREFIX = f"https://github.com/{REPO}/releases/download/"


def _ver(tag):
    parts = []
    for p in tag.lstrip("v").split("."):
        num = "".join(ch for ch in p if ch.isdigit())
        parts.append(int(num) if num else 0)
    return tuple(parts + [0] * (3 - len(parts)))


def latest(force=False):
    """{"version", "url", "notes", "asset"} of the newest release when it is newer than this one, {}
    when there is none, None when GitHub could not be asked (keep what was offered before)."""
    bundle = host.IN_FLATPAK and flatpak_bundle()
    if managed() and not bundle:
        return {}  # pacman / Flathub (Discover, GNOME Software, `flatpak update`) keep it current
    suffix = ".flatpak" if bundle else ".run"
    cached = read_json(FILE) or {}
    if cached.get("suffix", ".run") != suffix:
        cached = {}  # an earlier check looked for the other kind of file
    age = time.time() - cached.get("t", 0)
    known_newer = bool(cached.get("tag")) and _ver(cached["tag"]) > _ver(__version__)
    # What was cached says "nothing newer": a release may have come out since, so ask sooner.
    if force or age > TTL or (not known_newer and age > RECHECK):
        try:
            r = requests.get(f"https://api.github.com/repos/{REPO}/releases/latest", timeout=15,
                             headers={"Accept": "application/vnd.github+json"})
            r.raise_for_status()
            rel = r.json()
            run = next((a for a in rel.get("assets") or [] if a.get("name", "").endswith(suffix)), {})
            digest = run.get("digest") or ""
            cached = {"t": time.time(), "tag": rel.get("tag_name", ""), "url": rel.get("html_url", ""),
                      "notes": (rel.get("body") or "")[:1500], "asset": run.get("browser_download_url", ""),
                      "sha256": digest.split(":", 1)[1] if digest.startswith("sha256:") else "", "suffix": suffix}
            write_json(FILE, cached)
        except Exception:
            return None
    tag = cached.get("tag", "")
    if not tag or _ver(tag) <= _ver(__version__) or not cached.get("asset"):
        return {}
    if not cached["asset"].startswith(ASSET_PREFIX):
        return {}
    return {"version": tag.lstrip("v"), "url": cached["url"], "notes": cached["notes"], "asset": cached["asset"],
            "sha256": cached.get("sha256", ""), "kind": "flatpak" if bundle else "run"}


def download(asset, sha256=""):
    """Fetch the installer and check it is the file GitHub published (its SHA-256, which GitHub
    lists for each release file). Only this project's own release downloads are fetched."""
    if not asset.startswith(ASSET_PREFIX) or "/" in asset[len(ASSET_PREFIX):].split("/", 1)[-1]:
        raise RuntimeError("Not a Cornerplay release download")
    path = CACHE_DIR / os.path.basename(asset)
    download_checked(asset, path, sha256, mode=0o600)
    return path


def install_flatpak_argv(path):
    """The host command that installs a downloaded .flatpak over this one. The file sits in the
    sandbox's cache, which is ~/.var/app/<id>/cache on the host too, so the host can read it."""
    where = (flatpak_bundle() or {}).get("installation", "user")
    return host.argv(["flatpak", "install", f"--{where}", "--noninteractive", "-y", "--bundle", str(path)])
