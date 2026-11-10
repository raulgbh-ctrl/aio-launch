"""Is there a newer Cornerplay? Asks GitHub for the latest release, at most once a day.

Only installed copies are offered an update; a copy that runs from a git checkout
(development) is updated with git instead.
"""
import os
import time
from pathlib import Path

from . import __version__
from .net import requests

from .config import CACHE_DIR, read_json, write_json

REPO = "raulgbh-ctrl/cornerplay"
FILE = CACHE_DIR / "update_check.json"
TTL = 86400


def from_source():
    return (Path(__file__).resolve().parent.parent / ".git").exists()


def _ver(tag):
    parts = []
    for p in tag.lstrip("v").split("."):
        num = "".join(ch for ch in p if ch.isdigit())
        parts.append(int(num) if num else 0)
    return tuple(parts + [0] * (3 - len(parts)))


def latest(force=False):
    """{"version", "url", "notes", "asset"} of the newest release when it is newer than this one, else {}."""
    cached = read_json(FILE) or {}
    if force or time.time() - cached.get("t", 0) > TTL:
        try:
            r = requests.get(f"https://api.github.com/repos/{REPO}/releases/latest", timeout=15,
                             headers={"Accept": "application/vnd.github+json"})
            r.raise_for_status()
            rel = r.json()
            asset = next((a["browser_download_url"] for a in rel.get("assets") or []
                          if a.get("name", "").endswith(".run")), "")
            cached = {"t": time.time(), "tag": rel.get("tag_name", ""), "url": rel.get("html_url", ""),
                      "notes": (rel.get("body") or "")[:1500], "asset": asset}
            write_json(FILE, cached)
        except Exception:
            return {}
    tag = cached.get("tag", "")
    if not tag or _ver(tag) <= _ver(__version__) or not cached.get("asset"):
        return {}
    return {"version": tag.lstrip("v"), "url": cached["url"], "notes": cached["notes"], "asset": cached["asset"]}


def download(asset):
    """Fetch the installer; returns its path."""
    path = CACHE_DIR / os.path.basename(asset)
    with requests.get(asset, timeout=120, stream=True) as r:
        r.raise_for_status()
        with open(path, "wb") as f:
            for chunk in r.iter_content(1 << 16):
                f.write(chunk)
    return path
