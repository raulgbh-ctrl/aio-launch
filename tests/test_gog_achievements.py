import json
import zlib

from cornerplay import achievements
from cornerplay.config import CACHE_DIR, write_json


class Store:
    def logged_in(self): return True
    def _creds(self): return {"refresh_token": "user-refresh"}


class Resp:
    def __init__(self, data=None, content=b"", status=200):
        self._data, self.content, self.status_code, self.ok = data, content, status, status < 400
    def json(self): return self._data
    def raise_for_status(self): pass


def test_gog_achievements(monkeypatch):
    write_json(CACHE_DIR / "gog_user.json", {"galaxyUserId": "4242"})
    write_json(achievements.GOG_CLIENTS, {})
    calls = []

    def get(url, params=None, headers=None, timeout=None):
        calls.append((url, params, headers))
        if url.endswith("/builds"):
            return Resp({"items": [{"link": "https://cdn/meta"}]})
        if url == "https://cdn/meta":
            return Resp(content=zlib.compress(json.dumps({"clientId": "c1", "clientSecret": "s1"}).encode()))
        if url == "https://auth.gog.com/token":
            assert params["client_id"] == "c1" and params["without_new_session"] == "1"
            return Resp({"access_token": "game-token"})
        assert url == "https://gameplay.gog.com/clients/c1/users/4242/achievements"
        assert headers["Authorization"] == "Bearer game-token"
        return Resp({"items": [{"date_unlocked": "2026-01-01"}, {"date_unlocked": None}, {"date_unlocked": None}]})
    monkeypatch.setattr(achievements.requests, "get", get, raising=False)
    assert achievements.gog_fetch(Store(), "123") == {"done": 1, "total": 3}
    assert achievements.cached("gog:123")["total"] == 3
    assert achievements.progress("gog:123") == 1 / 3
