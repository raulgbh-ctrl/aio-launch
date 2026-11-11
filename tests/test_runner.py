from cornerplay import runner
from cornerplay.config import settings


def test_parse_env():
    assert runner.parse_env('DXVK_HUD=fps "PATH_X=a b" bad-key=1 noequals') == {"DXVK_HUD": "fps", "PATH_X": "a b"}
    assert runner.parse_env('unbalanced "quote A=1') == {"A": "1"}
    assert runner.parse_env("") == {}


def test_game_overrides_beat_settings():
    settings.data["env"] = "A=1 B=2"
    try:
        with runner.using({"env": "B=3", "perf": "battery"}):
            assert runner.user_env() == {"A": "1", "B": "3"}
            assert runner.opt("perf") == "battery"
        assert runner.opt("perf") == settings.get("perf")
    finally:
        settings.data["env"] = ""


def test_perf_profiles():
    settings.data["shader_cache"] = False
    try:
        with runner.using({"perf": "battery"}):
            env = runner.perf_env("epic", "x")
        assert env["DXVK_FRAME_RATE"] == "30" and env["WINE_FULLSCREEN_FSR"] == "1"
        assert "fps_limit=30" in env["MANGOHUD_CONFIG"]
        with runner.using({"perf": "quality"}):
            assert runner.perf_env("epic", "x") == {}
        with runner.using({"perf": "none"}):
            assert runner.perf_env("epic", "x") == {}
    finally:
        settings.data["shader_cache"] = True


def test_prefix_path_is_safe():
    p = runner.prefix_path("gog", "../../etc/passwd x")
    assert "/prefixes/gog-.._.._etc_passwd_x" in p
