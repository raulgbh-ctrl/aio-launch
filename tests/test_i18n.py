from pathlib import Path

import pytest

from cornerplay.config import LANGUAGES

I18N = Path(__file__).resolve().parent.parent / "cornerplay" / "i18n"


@pytest.mark.parametrize("lang", [c for c in LANGUAGES if c != "en"])
def test_every_language_ships_and_loads(lang):
    QtCore = pytest.importorskip("PySide6.QtCore")
    assert (I18N / f"cornerplay_{lang}.qm").is_file()
    tr = QtCore.QTranslator()
    assert tr.load(str(I18N / f"cornerplay_{lang}.qm"))
    assert tr.translate("Main", "Settings") not in ("", "Settings")
