"""`requests`, imported on first use.

Importing requests (and urllib3) costs ~0.1 s, and only background downloads need
it, so modules take it from here instead of importing it at startup.
"""


class _LazyRequests:
    def __getattr__(self, name):
        import requests
        return getattr(requests, name)


requests = _LazyRequests()


# ---------------------------------------------------------------- safety helpers
import re as _re

_SECRET_QUERY = _re.compile(r"(?i)([?&](?:key|api_key|apikey|token|access_token|refresh_token|code|client_secret|secret|password)=)[^&\s'\"]+")
_BEARER = _re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+")


def redact(text) -> str:
    """An error message without the secrets that URLs and headers carry (API keys in query
    strings, bearer tokens): requests puts the full URL into its errors, and those reach toasts."""
    return _BEARER.sub(r"\1•••", _SECRET_QUERY.sub(r"\1•••", str(text)))


GITHUB_API = "https://api.github.com/repos/{}/releases/latest"


def github_asset(repo, match):
    """(tag, download url, sha256 or "") of the newest release's asset whose name match(name)
    accepts. GitHub publishes each asset's SHA-256 ("digest"), so downloads can be checked."""
    r = requests.get(GITHUB_API.format(repo), timeout=20, headers={"Accept": "application/vnd.github+json"})
    r.raise_for_status()
    rel = r.json()
    for a in rel.get("assets") or []:
        if match(a.get("name", "")):
            digest = a.get("digest") or ""
            return rel.get("tag_name", ""), a["browser_download_url"], digest.split(":", 1)[1] if digest.startswith("sha256:") else ""
    raise RuntimeError(f"No matching download in {repo}'s latest release")


def download_checked(url, dest, sha256="", mode=0o644, progress=None):
    """Download url to dest (atomically). With sha256, a mismatch deletes the file and raises."""
    import hashlib
    import os
    tmp = f"{dest}.part"
    digest = hashlib.sha256()
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        total = int(r.headers.get("Content-Length", 0)) or None
        done = 0
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
                digest.update(chunk)
                done += len(chunk)
                if progress and total:
                    progress(done * 100 / total)
    if sha256 and digest.hexdigest() != sha256.lower():
        os.unlink(tmp)
        raise RuntimeError(f"The download from {url} was damaged or changed (checksum mismatch)")
    os.chmod(tmp, mode)
    os.replace(tmp, dest)
    return str(dest)
