"""Every QML file compiles (the same as `python -m cornerplay --check`)."""
import os

import pytest

pytest.importorskip("PySide6")


def test_qml_compiles():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from cornerplay.__main__ import check_qml
    assert not check_qml()
