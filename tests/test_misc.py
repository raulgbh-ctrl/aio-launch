from cornerplay import covers, updates
from cornerplay.config import GameOptions, read_json
from cornerplay.stores.base import Game


def test_norm_matches_editions_across_stores():
    assert covers.norm("The Witcher® 3: Wild Hunt – Game of the Year Edition") == covers.norm("The Witcher 3: Wild Hunt")
    assert covers.norm("Mount & Blade") == covers.norm("Mount and Blade")
    assert covers.norm("Portal 2") != covers.norm("Portal")


def test_version_compare():
    assert updates._ver("v0.10.0") > updates._ver("0.9.9")
    assert updates._ver("1.0") == (1, 0, 0)
    assert updates._ver("0.8.0-rc1") == (0, 8, 1)


def test_game_roundtrip():
    g = Game("gog", "123", "Gwent", installed=True, extra={"dlc": 2})
    assert Game.from_dict(dict(g.to_dict(), unknown_field=1)) == g
    assert g.key == "gog:123"


def test_game_options_drop_defaults(tmp_path, monkeypatch):
    opts = GameOptions()
    opts.path = tmp_path / "games.json"
    opts.data = {}
    opts.set("epic:a", "proton", "/x")
    opts.set("epic:a", "bogus", 1)  # unknown keys are ignored
    assert read_json(opts.path) == {"epic:a": {"proton": "/x"}}
    opts.set("epic:a", "proton", "default")
    assert read_json(opts.path) == {}


def test_steam_shortcut_keys_from_either_install():
    from cornerplay.steamshortcut import play_key
    assert play_key({"LaunchOptions": '--play "epic:Fortnite"'}) == "epic:Fortnite"
    assert play_key({"LaunchOptions": 'run io.github.raulgbh_ctrl.Cornerplay --play "gog:123"'}) == "gog:123"
    assert play_key({"LaunchOptions": "--tv"}) == ""
    assert play_key({"LaunchOptions": "run org.other.App --play x"}) == ""


def test_host_outside_flatpak():
    from cornerplay import host
    assert not host.IN_FLATPAK
    assert host.argv(["steam"]) == ["steam"]


def test_one_store_list_everywhere():
    """--play (Steam shortcuts) must know every store Steam shortcuts are made for."""
    from cornerplay.stores import all_stores
    from cornerplay.steamgames import eligible
    from cornerplay.stores.base import Game
    ids = [s.id for s in all_stores()]
    assert {"steam", "epic", "gog", "amazon", "battlenet", "itch", "retro", "custom"} == set(ids)
    for sid in ids:
        if sid != "steam":
            assert eligible(Game(sid, "1", "X", installed=True))


def test_sharp_screens_get_steams_double_size_art(monkeypatch):
    from cornerplay import covers
    from cornerplay.config import settings
    monkeypatch.setitem(settings.data, "screen_size", [1920, 1080])
    monkeypatch.setitem(settings.data, "screen_dpr", 1.0)
    assert not covers.hi_res()
    monkeypatch.setitem(settings.data, "screen_size", [2560, 1440])
    assert covers.hi_res()
    monkeypatch.setitem(settings.data, "screen_size", [1920, 1200])
    monkeypatch.setitem(settings.data, "screen_dpr", 1.5)
    assert covers.hi_res()


def test_auto_scale_from_last_start(monkeypatch):
    from cornerplay import __main__ as m
    from cornerplay.config import settings
    monkeypatch.delenv("HYPRLAND_INSTANCE_SIGNATURE", raising=False)
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setitem(settings.data, "screen_size", [3840, 2160])
    monkeypatch.setitem(settings.data, "screen_dpr", 1.0)
    assert m.auto_scale() == 2.0          # a 4K TV the desktop leaves at 100 %
    monkeypatch.setitem(settings.data, "screen_dpr", 2.0)
    assert m.auto_scale() == 1.0          # the desktop scales it already
    monkeypatch.setitem(settings.data, "screen_size", [2560, 1440])
    monkeypatch.setitem(settings.data, "screen_dpr", 1.0)
    assert m.auto_scale() == 1.0          # 1440p at 100 % is meant to look like that


def test_steam_running_only_counts_steams_reaper():
    from cornerplay.steamrun import _from_cmdlines
    lines = ["/home/u/.local/share/Steam/ubuntu12_32/reaper SteamLaunch AppId=1145360 -- /x/proton waitforexitandrun",
             "reaper SteamLaunch AppId=220 --",
             "/usr/bin/zsh -c pgrep -f 'reaper SteamLaunch AppId=999 '",   # only mentions it
             "vim notes about SteamLaunch AppId=5",
             "/s/reaper SteamLaunch AppId=0 --"]
    assert _from_cmdlines(lines) == {"1145360", "220"}


def test_stats_weeks_and_year():
    from datetime import datetime
    from cornerplay import statsdata
    now = datetime(2026, 11, 12, 20, 0).timestamp()  # a Thursday
    mon = datetime(2026, 11, 9, 10, 0).timestamp()
    log = [["gog:1", mon, mon + 3600], ["steam:2", mon - 7 * 86400, mon - 7 * 86400 + 1800],
           ["epic:3", datetime(2025, 12, 31, 23, 0).timestamp(), datetime(2026, 1, 1, 1, 0).timestamp()]]
    weeks = statsdata.weekly(log, now, weeks=2)
    assert [w["hours"] for w in weeks] == [0.5, 1.0] and weeks[-1]["label"] == "9 Nov"
    titles = {"gog:1": "Gwent", "steam:2": "Gwent", "epic:3": "Hades"}.get
    y = statsdata.year_summary(log, 2026, titles, {"gog:1": now})
    assert y["games"] == 2 and y["top"][0]["title"] == "Gwent" and y["top"][0]["hours"] == 1.5
    assert y["hours"] == 2.5 and y["months"][0] == 1.0  # only the part of the session inside the year
    assert y["newGames"] == ["Gwent"] and y["finished"] == ["Gwent"]
    assert statsdata.backlog({"want": 3, "finished": 1}) == {"total": 4, "done": 1, "percent": 25}


def test_throttle_steers_towards_the_limit():
    import os
    from cornerplay import throttle
    assert os.getpid() in throttle.tree(os.getpid())
    t = throttle.Throttle.__new__(throttle.Throttle)  # no timer: only the steering
    t.share, t.limit = 1.0, (lambda: 10.0)
    for _ in range(12):
        t.reported(50.0 * t.share)  # a tool that does 50 at full speed
    assert abs(50.0 * t.share - 10.0) < 0.5


def test_screenshots_from_steam_and_from_play_sessions(tmp_path, monkeypatch):
    import os
    from cornerplay import screenshots
    shots = tmp_path / "Screenshots"
    shots.mkdir()
    for name, t in (("during.png", 1000), ("before.png", 500), ("notes.txt", 1000), ("late.jpg", 2025)):
        (shots / name).write_bytes(b"x")
        os.utime(shots / name, (t, t))
    steam = tmp_path / "userdata/42/760/remote/730/screenshots"
    steam.mkdir(parents=True)
    (steam / "20261010_1.jpg").write_bytes(b"x")
    os.utime(steam / "20261010_1.jpg", (3000, 3000))
    monkeypatch.setattr(screenshots, "folders", lambda: [shots])
    sessions = [["steam:730", 900, 2000], ["gog:1", 400, 600]]
    rows = screenshots.for_game({"steam:730"}, sessions, screenshots.steam_folder(tmp_path, 42, "730"))
    assert [(os.path.basename(r["path"]), r["source"]) for r in rows] == \
        [("20261010_1.jpg", "steam"), ("late.jpg", "session"), ("during.png", "session")]


def test_couch_local_multiplayer(monkeypatch):
    from cornerplay import couch
    monkeypatch.setattr(couch, "_apps", {"620": {"cat": [1, 2, 9, 24, 39]}, "730": {"cat": [1, 49]}})
    assert couch.local("620") and not couch.local("730") and not couch.local("") and not couch.local("999")


def test_light_and_dark_follow_the_desktop_or_the_clock(monkeypatch):
    from cornerplay import theme
    from cornerplay.config import settings
    monkeypatch.setitem(settings.data, "theme_auto", "system")
    monkeypatch.setitem(settings.data, "theme_light", "Mint")
    monkeypatch.setitem(settings.data, "theme_dark", "Ocean")
    assert theme.auto_mode(True) == "Ocean" and theme.auto_mode(False) == "Mint"
    assert theme.auto_mode(None) == ""                    # no preference from the desktop: as chosen
    assert theme.current(True)["background"].lower() == "#0f1620"
    monkeypatch.setitem(settings.data, "theme_auto", "")
    assert theme.auto_mode(True) == ""
    assert theme.sunset_dark(20) and theme.sunset_dark(3) and not theme.sunset_dark(12)


def test_stream_wake_on_lan_and_sunshine_list(tmp_path, monkeypatch):
    import pytest
    from cornerplay import stream
    p = stream.magic_packet("3C-7C-3F-12-34-56")
    assert p[:6] == b"\xff" * 6 and p[6:12] == bytes.fromhex("3c7c3f123456") and len(p) == 102
    with pytest.raises(ValueError):
        stream.magic_packet("not a mac")
    monkeypatch.setattr(stream, "_launcher", lambda: ["/usr/bin/cornerplay"])
    old = {"apps": [{"name": "Desktop"}, {"name": "Stale", "cmd": "/old/cornerplay --play gog:1"},
                    {"name": "Mine", "cmd": "/usr/bin/other-launcher"}]}
    data = stream.sunshine_apps(old, [{"key": "steam:620", "title": "Portal 2"}], "/i.png")
    names = [a["name"] for a in data["apps"]]
    assert names == ["Desktop", "Mine", "Cornerplay (TV mode)", "Portal 2"]   # ours replaced, theirs kept
    assert data["apps"][2]["detached"] == ["setsid /usr/bin/cornerplay --tv"]
    assert data["apps"][3]["cmd"] == "/usr/bin/cornerplay --play steam:620"
    monkeypatch.setattr(stream, "moonlight", lambda: ["moonlight"])
    with pytest.raises(RuntimeError):
        stream.stream_argv("pc; rm -rf ~")                                    # never a shell
    assert stream.stream_argv("gaming-pc")[-3:] == ["stream", "gaming-pc", "Cornerplay (TV mode)"]


def test_streaks():
    from datetime import datetime
    from cornerplay import statsdata
    day = lambda d, h=20: datetime(2026, 11, d, h).timestamp()
    log = [["a", day(1), day(1) + 3600], ["a", day(2), day(2) + 1800], ["b", day(3), day(3) + 900],
           ["a", day(5), day(5) + 120],                       # 2 minutes: does not count
           ["a", day(8), day(8) + 3600], ["a", day(9), day(9) + 3600]]
    assert statsdata.streaks(log, now=day(10, 12)) == {"current": 2, "longest": 3}
    assert statsdata.streaks(log, now=day(12, 12))["current"] == 0      # missed a day: broken
    late = [["a", datetime(2026, 11, 3, 23, 30).timestamp(), datetime(2026, 11, 4, 0, 40).timestamp()]]
    assert statsdata.streaks(late, now=day(4, 12)) == {"current": 2, "longest": 2}  # past midnight
    assert statsdata.streaks([], now=day(4)) == {"current": 0, "longest": 0}


def test_screenshot_library(tmp_path, monkeypatch):
    import os
    from cornerplay import screenshots
    pics = tmp_path / "pics"
    pics.mkdir()
    remote = tmp_path / "remote" / "1245620" / "screenshots"
    remote.mkdir(parents=True)
    def pic(folder, name, t):
        f = folder / name
        f.write_bytes(b"x")
        os.utime(f, (t, t))
    pic(pics, "a.png", 1000)      # during the Celeste session
    pic(pics, "b.png", 5000)      # during nothing
    pic(pics, "c.png", 2050)      # Hades
    pic(remote, "s1.jpg", 3000)   # Steam's own
    monkeypatch.setattr(screenshots, "folders", lambda: [pics])
    sessions = [["epic:celeste", 900, 1100], ["gog:hades", 2000, 2100]]
    titles = {"epic:celeste": "Celeste", "gog:hades": "Hades", "steam:1245620": "Elden Ring"}
    out = screenshots.library(sessions, tmp_path / "remote", titles.get)
    assert [g["title"] for g in out] == ["Elden Ring", "Hades", "Celeste"]
    assert [g["count"] for g in out] == [1, 1, 1]
    assert out[2]["shots"][0]["path"].endswith("a.png")


def test_journal():
    from datetime import datetime
    from cornerplay import statsdata
    ts = lambda m, d, h=20: datetime(2026, m, d, h).timestamp()
    log = [["a", ts(9, 3), ts(9, 3) + 7200], ["a", ts(10, 1), ts(10, 1) + 3600], ["b", ts(10, 5), ts(10, 5) + 1800],
           ["a2", ts(10, 6), ts(10, 6) + 1800]]   # the same game on another store
    titles = {"a": "Alpha", "a2": "Alpha", "b": "Beta"}
    out = statsdata.journal(log, titles.get, {"b": ts(10, 20)})
    assert [m["label"] for m in out] == ["October 2026", "September 2026"]
    oct_ = out[0]
    assert oct_["hours"] == 2.0 and [g["title"] for g in oct_["games"]] == ["Alpha", "Beta"]
    assert oct_["games"][0]["sessions"] == 2 and not oct_["games"][0]["first"]
    assert oct_["games"][1]["first"] and oct_["games"][1]["finished"] and oct_["started"] == 1
    assert out[1]["games"][0]["first"]
