"""Werkstoffdatenbank zum Nachschlagen (M26)."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QHeaderView, QLabel, QLineEdit, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .. import werkstoffe
from ..berechnungen.basis import formatiere
from .seiten import titel


class WerkstoffSeite(QWidget):
    meldung = Signal(str, bool)
    SPALTEN = [("name", "Werkstoff"), ("zustand", "Zustand"), ("re", "Re / Rp0,2\nMPa"), ("rm", "Rm\nMPa"),
               ("e", "E-Modul\nGPa"), ("dichte", "Dichte\nkg/m³"), ("a", "A\n%"), ("norm", "Norm"),
               ("beleg", "Beleg"), ("verwendung", "Verwendung")]

    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 24, 32, 24)
        lay.addWidget(titel("Werkstoffe", "Festigkeitswerte, E-Modul und Dichte gängiger Werkstoffe. "
                                          "Die Festigkeitsnachweise ab Meilenstein 5 greifen darauf zu."))
        self.suche = QLineEdit()
        self.suche.setPlaceholderText("Suchen: Name, Werkstoffnummer, Gruppe oder Verwendung (z. B. „Welle“)")
        self.suche.textChanged.connect(self.laden)
        lay.addWidget(self.suche)
        self.tabelle = QTableWidget(0, len(self.SPALTEN))
        self.tabelle.setHorizontalHeaderLabels([s for _, s in self.SPALTEN])
        self.tabelle.verticalHeader().setVisible(False)
        self.tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabelle.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabelle.setAlternatingRowColors(True)
        self.tabelle.verticalHeader().setDefaultSectionSize(34)
        kopf = self.tabelle.horizontalHeader()
        kopf.setMinimumHeight(48)
        kopf.setSectionResizeMode(QHeaderView.ResizeToContents)
        kopf.setStretchLastSection(True)
        lay.addWidget(self.tabelle, 1)
        h = QLabel("⚠ " + werkstoffe.hinweis())
        h.setObjectName("Klein")
        h.setWordWrap(True)
        lay.addWidget(h)
        self.laden()

    def setze_projekt(self, _projekt):
        pass

    def laden(self, *_):
        liste = werkstoffe.suchen(self.suche.text())
        self.tabelle.setRowCount(len(liste))
        for z, w in enumerate(liste):
            for s, (feld, _) in enumerate(self.SPALTEN):
                wert = w[feld]
                if isinstance(wert, (int, float)):
                    text = "–" if wert == 0 else formatiere(wert)
                else:
                    text = str(wert)
                if feld == "beleg" and wert != "Norm, ungeprüft":
                    text = "⚠ " + text
                item = QTableWidgetItem(text)
                item.setToolTip(f"{w['name']} ({w['nr']}), {w['gruppe']}")
                if isinstance(wert, (int, float)):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.tabelle.setItem(z, s, item)
