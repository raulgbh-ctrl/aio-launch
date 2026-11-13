from pathlib import Path

from PySide6.QtCore import QCoreApplication, QTranslator

from cornerplay import toastsi18n


def test_toasts_translate_with_their_parts():
    app = QCoreApplication.instance() or QCoreApplication([])
    tr = QTranslator()
    assert tr.load(str(Path(toastsi18n.__file__).parent / "i18n" / "cornerplay_ro.qm"))
    app.installTranslator(tr)
    try:
        assert toastsi18n.translate("Could not start Elden Ring: no Vulkan driver") == \
            "Nu am putut porni Elden Ring: no Vulkan driver"
        assert toastsi18n.translate("Saves of Hades backed up") == "Salvările Hades au fost copiate"
        assert toastsi18n.translate("Demo mode: Steam is not changed") == "Mod demo: Steam nu e modificat"
        assert toastsi18n.translate("something nobody wrote") == "something nobody wrote"
    finally:
        app.removeTranslator(tr)


def test_templates_are_current():
    """tools/toast_templates.py was run after the last toast changed."""
    import subprocess
    import sys
    root = Path(toastsi18n.__file__).parent.parent
    before = (root / "cornerplay/toastsi18n.py").read_text()
    subprocess.run([sys.executable, str(root / "tools/toast_templates.py")], check=True, capture_output=True)
    assert (root / "cornerplay/toastsi18n.py").read_text() == before
