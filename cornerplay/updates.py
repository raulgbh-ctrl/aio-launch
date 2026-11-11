"""Is there a newer Cornerplay? Asks GitHub for the latest release, at most once a day.

Only installed copies are offered an update; a copy that runs from a git checkout
(development) is updated with git instead.
"""
import os
import time
from pathlib import Path

from . import __version__
from .net import download_checked, requests

from .config import CACHE_DIR, read_json, write_json

REPO = "raulgbh-ctrl/cornerplay"
FILE = CACHE_DIR / "update_check.json"
TTL = 86400


def from_source():
    return (Path(__file__).resolve().parent.parent / ".git").exists()


def managed():
    """Installed by a package manager (the AUR package lives in /usr/lib) or Flatpak: that is
    what updates it. Installing the .run on top would leave a second copy shadowing it."""
    here = str(Path(__file__).resolve())
    return here.startswith(("/usr/", "/app/", "/opt/"))


ASSET_PREFIX = f"https://github.com/{REPO}/releases/download/"


def _ver(tag):
    parts = []
    for p in tag.lstrip("v").split("."):
        num = "".join(ch for ch in p if ch.isdigit())
        parts.append(int(num) if num else 0)
    return tuple(parts + [0] * (3 - len(parts)))


def latest(force=False):
    """{"version", "url", "notes", "asset"} of the newest release when it is newer than this one, else {}."""
    if managed():
        return {}  # pacman / Flatpak (Discover, GNOME Software, `flatpak update`) keep it current
    cached = read_json(FILE) or {}
    if force or time.time() - cached.get("t", 0) > TTL:
        try:
            r = requests.get(f"https://api.github.com/repos/{REPO}/releases/latest", timeout=15,
                             headers={"Accept": "application/vnd.github+json"})
            r.raise_for_status()
            rel = r.json()
            run = next((a for a in rel.get("assets") or [] if a.get("name", "").endswith(".run")), {})
            digest = run.get("digest") or ""
            cached = {"t": time.time(), "tag": rel.get("tag_name", ""), "url": rel.get("html_url", ""),
                      "notes": (rel.get("body") or "")[:1500], "asset": run.get("browser_download_url", ""),
                      "sha256": digest.split(":", 1)[1] if digest.startswith("sha256:") else ""}
            write_json(FILE, cached)
        except Exception:
            return {}
    tag = cached.get("tag", "")
    if not tag or _ver(tag) <= _ver(__version__) or not cached.get("asset"):
        return {}
    if not cached["asset"].startswith(ASSET_PREFIX):
        return {}
    return {"version": tag.lstrip("v"), "url": cached["url"], "notes": cached["notes"], "asset": cached["asset"],
            "sha256": cached.get("sha256", "")}


def download(asset, sha256=""):
    """Fetch the installer and check it is the file GitHub published (its SHA-256, which GitHub
    lists for each release file). Only this project's own release downloads are fetched."""
    if not asset.startswith(ASSET_PREFIX) or "/" in asset[len(ASSET_PREFIX):].split("/", 1)[-1]:
        raise RuntimeError("Not a Cornerplay release download")
    path = CACHE_DIR / os.path.basename(asset)
    download_checked(asset, path, sha256, mode=0o600)
    return path
