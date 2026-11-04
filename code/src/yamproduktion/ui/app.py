"""Programmstart."""
from __future__ import annotations

import sys
import traceback

from PySide6.QtCore import QLocale, QSettings
from PySide6.QtWidgets import QApplication, QMessageBox

from .. import APP_NAME
from . import thema
from .hauptfenster import Hauptfenster


def _unerwarteter_fehler(typ, wert, tb):
    """Kein kommentarloser Absturz: Fehler verständlich anzeigen (N8)."""
    text = "".join(traceback.format_exception(typ, wert, tb))
    print(text, file=sys.stderr)
    if QApplication.instance():
        QMessageBox.critical(None, "Unerwarteter Fehler",
                             "Da ist etwas schiefgelaufen. Deine Daten sind gespeichert.\n\n"
                             f"{wert}\n\nBitte diese Meldung an Claude weitergeben.")


def main() -> int:
    sys.excepthook = _unerwarteter_fehler
    QLocale.setDefault(QLocale(QLocale.German, QLocale.Germany))  # Komma als Dezimaltrenner
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("YamProduktion")
    einst = QSettings()
    thema.anwenden(app, einst.value("thema", "auto"))
    fenster = Hauptfenster(einst)
    fenster.showMaximized()
    fenster.letztes_projekt_oeffnen()
    return app.exec()
