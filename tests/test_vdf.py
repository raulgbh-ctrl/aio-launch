from cornerplay import vdf


def test_loads_nested_and_comments():
    text = '''
    // a comment
    "AppState"
    {
        "appid"   "570"
        "name"    "Dota \\"2\\""
        "UserConfig" { "language" "english" }
    }
    '''
    d = vdf.loads(text)
    assert d["AppState"]["appid"] == "570"
    assert d["AppState"]["name"] == 'Dota "2"'
    assert d["AppState"]["UserConfig"] == {"language": "english"}


def test_roundtrip():
    obj = {"root": {"a": "1", "path": "C:\\Games\\x", "child": {"q": 'say "hi"'}, "empty": {}}}
    assert vdf.loads(vdf.dumps(obj)) == obj


def test_unbalanced_braces_do_not_crash():
    assert vdf.loads('"a" { "b" "c" } } }') == {"a": {"b": "c"}}


def test_load_missing_file(tmp_path):
    assert vdf.load(tmp_path / "nope.vdf") == {}
