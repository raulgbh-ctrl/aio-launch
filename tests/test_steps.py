import time

from cornerplay import steps


def test_before_runs_in_order_and_reports_failures(tmp_path, monkeypatch):
    monkeypatch.setattr(steps, "LOG_DIR", tmp_path / "logs")
    out = tmp_path / "out.txt"
    failed = steps.before("gog:1", f"# a note\necho one >> {out}\nfalse\necho two >> {out}\nsleep 5 &")
    assert out.read_text().split() == ["one", "two"]
    assert failed == ["false"]


def test_after_runs_in_background(tmp_path, monkeypatch):
    monkeypatch.setattr(steps, "LOG_DIR", tmp_path / "logs")
    out = tmp_path / "after.txt"
    steps.after("gog:1", f"echo a >> {out}\necho b >> {out}")
    for _ in range(50):
        if out.exists() and out.read_text().split() == ["a", "b"]:
            break
        time.sleep(0.05)
    assert out.read_text().split() == ["a", "b"]


def test_presets_are_added_once():
    t = steps.add_preset("discord &", "discord &")
    assert t == "discord &"
    assert steps.add_preset("", "powerprofilesctl set performance") == "powerprofilesctl set performance"
