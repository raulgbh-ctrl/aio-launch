from cornerplay import timetobeat
from cornerplay.config import settings


def test_hours_and_label():
    assert timetobeat.hours(0) == 0
    assert timetobeat.hours(5 * 3600 + 1000) == 5.5
    assert timetobeat.hours(42 * 3600 + 1000) == 42
    assert timetobeat.label({"main": 5.5, "extra": 0, "full": 42}) == "Main 5.5 h  ·  100% 42 h"
    assert timetobeat.label({}) == ""


def test_not_asked_without_a_key(monkeypatch):
    monkeypatch.setitem(settings.data, "igdb_client_id", "")
    assert timetobeat.fetch("Hades") is None


def test_fetch(monkeypatch):
    monkeypatch.setitem(settings.data, "igdb_client_id", "id")
    monkeypatch.setitem(settings.data, "igdb_client_secret", "secret")
    calls = []

    def query(endpoint, body):
        calls.append(endpoint)
        if endpoint == "external_games":
            return []  # not matched through Steam: by title then
        if endpoint == "games":
            return [{"id": 2, "name": "Hades II"}, {"id": 1, "name": "Hades"}]
        assert "game_id = 1;" in body
        return [{"hastily": 20 * 3600, "normally": 45 * 3600, "completely": 95 * 3600}]
    monkeypatch.setattr(timetobeat, "_query", query)
    assert timetobeat.fetch("Hades", appid="1145360") == {"main": 20, "extra": 45, "full": 95}
    assert calls == ["external_games", "games", "game_time_to_beats"]


def test_no_exact_title_match_shows_nothing(monkeypatch):
    monkeypatch.setitem(settings.data, "igdb_client_id", "id")
    monkeypatch.setitem(settings.data, "igdb_client_secret", "secret")
    monkeypatch.setattr(timetobeat, "_query", lambda e, b: [{"id": 2, "name": "Hades II"}] if e == "games" else [])
    assert timetobeat.fetch("Hades") == {}
