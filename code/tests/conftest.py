import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QLocale  # noqa: E402

QLocale.setDefault(QLocale(QLocale.German, QLocale.Germany))

import pytest  # noqa: E402
from PySide6.QtWidgets import QMessageBox  # noqa: E402


@pytest.fixture(autouse=True)
def keine_dialoge(monkeypatch):
    """Modale Dialoge würden Tests anhalten – im Test sofort beantworten."""
    meldungen = []
    for name in ("information", "warning", "critical"):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda *a, **k: meldungen.append(a) or QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    return meldungen
