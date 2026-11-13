import time

from cornerplay import updates


class Resp:
    def __init__(self, tag):
        self.tag = tag

    def raise_for_status(self):
        pass

    def json(self):
        return {"tag_name": self.tag, "html_url": "u", "body": "",
                "assets": [{"name": "cornerplay.run", "browser_download_url": updates.ASSET_PREFIX + self.tag + "/cornerplay.run"}]}


def test_cached_nothing_newer_is_asked_again_within_hours(tmp_path, monkeypatch):
    monkeypatch.setattr(updates, "FILE", tmp_path / "u.json")
    monkeypatch.setattr(updates, "managed", lambda: False)
    monkeypatch.setattr(updates, "__version__", "0.11.0")
    calls = []
    monkeypatch.setattr(updates.requests, "get", lambda *a, **k: calls.append(1) or Resp(tag))
    tag = "v0.11.0"
    assert updates.latest() == {}
    # a release comes out; two hours later the "nothing newer" answer is not trusted any more
    tag = "v0.12.0"
    data = updates.read_json(updates.FILE)
    data["t"] = time.time() - 2 * 3600
    updates.write_json(updates.FILE, data)
    assert updates.latest()["version"] == "0.12.0"
    assert len(calls) == 2


def test_failed_check_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(updates, "FILE", tmp_path / "u.json")
    monkeypatch.setattr(updates, "managed", lambda: False)

    def boom(*a, **k):
        raise OSError("offline")
    monkeypatch.setattr(updates.requests, "get", boom)
    assert updates.latest() is None
