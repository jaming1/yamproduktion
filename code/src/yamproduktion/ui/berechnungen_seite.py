"""Liste aller gespeicherten Berechnungen mit Status, Rückverfolgung und „Neu berechnen“."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QFileDialog, QHBoxLayout, QHeaderView, QMessageBox, QPushButton, QSplitter,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..berechnungen import ARTEN
from ..berechnungen.basis import formatiere
from ..modell import NEU_PRUEFEN, Projekt, ProjektFehler
from ..pdf import protokoll_erstellen
from .rueckverfolgung import RueckverfolgungPanel, status_text
from .seiten import titel


class BerechnungenSeite(QWidget):
    meldung = Signal(str, bool)
    geaendert = Signal()
    neue_berechnung = Signal(str)   # Berechnungsart
    gehe_zu_objekt = Signal(str, int)

    SPALTEN = ["Nr", "Berechnung", "Hauptergebnis", "Prüfungen", "Status"]

    def __init__(self):
        super().__init__()
        self.projekt: Projekt | None = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 24, 32, 24)
        lay.addWidget(titel("Berechnungen",
                            "Alle gespeicherten Berechnungen des Produkts. Ändert sich eine Anforderung oder eine Berechnung, "
                            "aus der Werte stammen, steht hier „⚠ neu prüfen“ – mit einem Klick wird mit den neuen "
                            "Werten gerechnet, in der richtigen Reihenfolge."))
        reihe = QHBoxLayout()
        self.neu_rechnen = QPushButton("Neu berechnen")
        self.neu_rechnen.setObjectName("Haupt")
        self.neu_rechnen.setToolTip("Mit den aktuellen Werten der verknüpften Anforderungen neu rechnen")
        self.neu_rechnen.clicked.connect(self.ausgewaehlte_neu_rechnen)
        self.alle_neu = QPushButton("Alle markierten neu berechnen")
        self.alle_neu.clicked.connect(self.alle_neu_rechnen)
        self.geprueft = QPushButton("Als geprüft markieren")
        self.geprueft.clicked.connect(lambda: self._status("geprüft"))
        self.pdf = QPushButton("PDF erzeugen …")
        self.pdf.clicked.connect(self.pdf_erzeugen)
        self.neu = QPushButton("Rechenseite öffnen")
        self.neu.setToolTip("Die Rechenseite zur ausgewählten Berechnung öffnen (ohne Auswahl: Rotorauslegung)")
        self.neu.clicked.connect(self._rechenseite)
        for k in (self.neu_rechnen, self.alle_neu, self.geprueft, self.pdf):
            reihe.addWidget(k)
        reihe.addStretch()
        reihe.addWidget(self.neu)
        lay.addLayout(reihe)

        self.tabelle = QTableWidget(0, len(self.SPALTEN))
        self.tabelle.setHorizontalHeaderLabels(self.SPALTEN)
        self.tabelle.verticalHeader().setVisible(False)
        self.tabelle.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabelle.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabelle.setAlternatingRowColors(True)
        self.tabelle.verticalHeader().setDefaultSectionSize(40)
        self.tabelle.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        for spalte, breite in ((0, 70), (2, 140), (3, 120), (4, 130)):
            self.tabelle.setColumnWidth(spalte, breite)
        self.tabelle.currentCellChanged.connect(lambda *_: self._auswahl_geaendert())

        self.panel = RueckverfolgungPanel()
        self.panel.gehe_zu.connect(self.gehe_zu_objekt)
        teiler = QSplitter(Qt.Horizontal)
        teiler.addWidget(self.tabelle)
        teiler.addWidget(self.panel)
        teiler.setStretchFactor(0, 1)
        teiler.setChildrenCollapsible(False)
        teiler.setSizes([1000, 340])
        lay.addWidget(teiler, 1)
        self._knoepfe()

    def _rechenseite(self):
        bid = self._aktuelle_id()
        typ = self.projekt.berechnung(bid).typ if (bid and self.projekt) else "rotorauslegung"
        self.neue_berechnung.emit(typ)

    def setze_projekt(self, projekt: Projekt):
        self.projekt = projekt
        self.laden()

    def _aktuelle_id(self) -> int | None:
        zeile = self.tabelle.currentRow()
        item = self.tabelle.item(zeile, 0) if zeile >= 0 else None
        return item.data(Qt.UserRole) if item else None

    def laden(self, auswahl_id: int | None = None):
        if not self.projekt:
            return
        if auswahl_id is None:
            auswahl_id = self._aktuelle_id()
        self.tabelle.blockSignals(True)
        liste = self.projekt.berechnungen()
        self.tabelle.setRowCount(len(liste))
        neue_zeile = 0 if liste else -1
        for zeile, b in enumerate(liste):
            if b.id == auswahl_id:
                neue_zeile = zeile
            haupt = ARTEN.get(b.typ, {}).get("hauptergebnis")
            g = next((x for x in b.ergebnis["ergebnisse"] if x["symbol"] == haupt),
                     b.ergebnis["ergebnisse"][0] if b.ergebnis["ergebnisse"] and not haupt else None)
            werte = [
                b.nr, b.titel,
                f"{g['symbol']} = {formatiere(g['wert'])} {g['einheit']}" if g else "–",
                "✓ erfüllt" if b.erfuellt else "✗ nicht erfüllt",
                status_text(b.status),
            ]
            for spalte, wert in enumerate(werte):
                item = QTableWidgetItem(wert)
                item.setData(Qt.UserRole, b.id)
                if spalte == 4 and b.status == NEU_PRUEFEN:
                    schrift = item.font()
                    schrift.setBold(True)
                    item.setFont(schrift)
                self.tabelle.setItem(zeile, spalte, item)
        self.tabelle.blockSignals(False)
        if neue_zeile >= 0:
            self.tabelle.setCurrentCell(neue_zeile, 0)
        self._auswahl_geaendert()

    def auswaehlen(self, id_: int):
        self.laden(auswahl_id=id_)

    def _auswahl_geaendert(self):
        self._knoepfe()
        id_ = self._aktuelle_id()
        if not self.projekt or id_ is None:
            self.panel.leer()
            return
        b = self.projekt.berechnung(id_)
        self.panel.zeigen(self.projekt, "berechnung", b.id, b.nr, b.titel, b.status, b.version)

    def _knoepfe(self):
        b = self.projekt.berechnung(self._aktuelle_id()) if self.projekt and self._aktuelle_id() else None
        self.neu_rechnen.setEnabled(bool(b))
        self.neu_rechnen.setObjectName("Haupt" if b and b.status == NEU_PRUEFEN else "")
        self.neu_rechnen.style().unpolish(self.neu_rechnen)
        self.neu_rechnen.style().polish(self.neu_rechnen)
        self.geprueft.setEnabled(bool(b) and b.status not in (NEU_PRUEFEN, "geprüft", "freigegeben"))
        self.pdf.setEnabled(bool(b))
        self.alle_neu.setVisible(bool(self.projekt and self.projekt.neu_zu_pruefen()))

    def ausgewaehlte_neu_rechnen(self):
        id_ = self._aktuelle_id()
        if not self.projekt or id_ is None:
            return
        try:
            b = self.projekt.berechnung_neu_rechnen(id_)
            text = self.projekt.verlauf("berechnung", id_)[0].text
            self.meldung.emit(f"{b.nr}: {text}", False)
        except ProjektFehler as exc:
            QMessageBox.warning(self, "Neu berechnen nicht möglich", str(exc))
            self.meldung.emit(str(exc), True)
        self.laden(auswahl_id=id_)
        self.geaendert.emit()

    def alle_neu_rechnen(self):
        if not self.projekt:
            return
        fertig, fehler = [], []
        ids = [b.id for b in self.projekt.neu_zu_pruefen() if b.typ == "berechnung"]
        for bid in self.projekt.berechnungen_in_reihenfolge(ids):
            try:
                fertig.append(self.projekt.berechnung_neu_rechnen(bid).nr)
            except ProjektFehler as exc:
                fehler.append(str(exc))
        if fehler:
            QMessageBox.warning(self, "Nicht alles konnte neu berechnet werden", "\n".join(fehler))
        self.meldung.emit(f"Neu berechnet: {', '.join(fertig) or '–'}", bool(fehler))
        self.laden()
        self.geaendert.emit()

    def _status(self, status: str):
        id_ = self._aktuelle_id()
        if not self.projekt or id_ is None:
            return
        try:
            self.projekt.status_setzen("berechnung", id_, status)
            self.meldung.emit(f"Status auf „{status}“ gesetzt.", False)
        except ProjektFehler as exc:
            self.meldung.emit(str(exc), True)
        self.laden(auswahl_id=id_)
        self.geaendert.emit()

    def pdf_erzeugen(self, ziel: str | None = None):
        id_ = self._aktuelle_id()
        if not self.projekt or id_ is None:
            return None
        b = self.projekt.berechnung(id_)
        if b.status == NEU_PRUEFEN and ziel is None:
            antwort = QMessageBox.question(self, "Veraltete Berechnung",
                                           f"{b.nr} ist als „neu prüfen“ markiert. Trotzdem das alte Protokoll erzeugen?")
            if antwort != QMessageBox.Yes:
                return None
        if ziel is None:
            vorschlag = self.projekt.pfad.parent / f"{b.nr}_v{b.version}.pdf"
            ziel, _ = QFileDialog.getSaveFileName(self, "Protokoll speichern", str(vorschlag), "PDF (*.pdf)")
            if not ziel:
                return None
        pfad = protokoll_erstellen(b.ergebnis, ziel, self.projekt.name, f"{b.nr} (Version {b.version})")
        self.meldung.emit(f"Protokoll gespeichert: {Path(pfad).name}", False)
        return pfad
