from cornerplay import patchnotes


def test_plain_bbcode():
    text = ("[p]Hotfix for a smoother run.[/p][p][/p][h2]BASE GAME[/h2][p]Fixes[/p]"
            "[list][*][p]Fixed the shop.[/p][*][p]Fixed &amp; tidied menus.[/p][/list]"
            "[img]{STEAM_CLAN_IMAGE}/x.png[/img][p][url=https://x]Discord[/url][/p]")
    assert patchnotes.plain(text) == ("Hotfix for a smoother run.\n\nBASE GAME\nFixes\n"
                                      "• Fixed the shop.\n• Fixed & tidied menus.\n\nDiscord")


def test_plain_cut():
    assert len(patchnotes.plain("word " * 2000)) <= patchnotes.MAX_TEXT + 1


def test_fetch(monkeypatch):
    class R:
        def raise_for_status(self): pass
        def json(self):
            return {"appnews": {"newsitems": [
                {"gid": "1", "title": "Spring sale", "date": 100, "contents": "[p]Cheap![/p]"},
                {"gid": "2", "title": "Update 1.2", "date": 200, "contents": "", "tags": []},
                {"gid": "3", "title": "Big news", "date": 150, "contents": "", "tags": ["patchnotes"]}]}}
    monkeypatch.setattr(patchnotes.requests, "get", lambda *a, **k: R())
    notes = patchnotes.fetch("42")
    assert [n["title"] for n in notes] == ["Update 1.2", "Big news", "Spring sale"]
    assert [n["patch"] for n in notes] == [True, True, False]
    assert notes[0]["url"] == "https://store.steampowered.com/news/app/42/view/2"
