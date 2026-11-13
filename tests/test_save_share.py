import os
import time

from cornerplay import personal, savebackup
from cornerplay.stores.base import Game


def test_share_between_two_pcs(tmp_path, monkeypatch):
    sync = tmp_path / "sync"
    game = Game(store="humble", id="celeste", title="Celeste")
    home_a, home_b = tmp_path / "a", tmp_path / "b"
    save_rel = ".local/share/Celeste/Saves/0.celeste"

    def be(pc, home):
        monkeypatch.setattr(savebackup, "HOME", home)
        monkeypatch.setattr(savebackup, "BACKUPS", tmp_path / f"backups-{pc}")
        monkeypatch.setattr(savebackup, "prefix_for", lambda g, appid=None: "")
        monkeypatch.setattr(savebackup, "paths_for", lambda g, appid=None: [str(home / ".local/share/Celeste/Saves")])
        monkeypatch.setattr(personal, "machine", lambda: pc)
        monkeypatch.setattr(personal, "sync_root", lambda: sync)

    # PC A plays and shares its save
    be("pc-a", home_a)
    f = home_a / save_rel
    f.parent.mkdir(parents=True)
    f.write_text("chapter 7")
    assert savebackup.share(game)
    assert (sync / "saves" / "humble_celeste" / "pc-a.zip").is_file()

    # PC B has an older save of its own: A's is newer, and taking it puts it in B's home
    be("pc-b", home_b)
    g = home_b / save_rel
    g.parent.mkdir(parents=True)
    g.write_text("chapter 2")
    old = time.time() - 3600
    os.utime(g, (old, old))
    newer = savebackup.newer_elsewhere(game)
    assert newer and newer["machine"] == "pc-a"
    assert savebackup.take(game, newer["path"]) == 1
    assert g.read_text() == "chapter 7"
    assert savebackup.newer_elsewhere(game) is None     # in step now
    assert any("before restoring" in b["reason"] for b in savebackup.backups(game))  # B's old save kept
