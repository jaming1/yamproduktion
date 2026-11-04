"""Seite „Kosten & Anfragen“: Kalkulation je Baugruppe, Kostensätze, Anfrageliste für Fremdfertigung (MS9)."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton, QSpinBox,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..berechnungen.basis import formatiere


def euro(x: float) -> str:
    return f"{x:,.2f}".replace(",", " ").replace(".", ",")
from ..fertigung import arbeitsplan as A
from ..modell import Projekt, ProjektFehler
from .seiten import karte, scrollbar, titel


def _zahl(text: str) -> float | None:
    try:
        return float(text.replace("€", "").replace(" ", "").replace(",", ".").strip())
    except ValueError:
        return None


def _tabelle(spalten: list[str], hoehe: int = 180) -> QTableWidget:
    t = QTableWidget(0, len(spalten))
    t.setHorizontalHeaderLabels(spalten)
    t.verticalHeader().hide()
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    t.horizontalHeader().setStretchLastSection(True)
    t.setMinimumHeight(hoehe)
    return t


def _fest(text: str) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setFlags(item.flags() & ~item.flags().ItemIsEditable)
    return item


class KostenSeite(QWidget):
    meldung = Signal(str, bool)
    arbeitsplan_oeffnen = Signal(int)          # teil_id

    def __init__(self):
        super().__init__()
        self.projekt: Projekt | None = None
        self.zeilen: list = []
        self.summe = 0.0
        self.fehlend: list = []
        self._fuellt = False

        inhalt = QWidget()
        lay = QVBoxLayout(inhalt)
        lay.setContentsMargins(32, 24, 32, 24)
        lay.addWidget(titel("Kosten & Anfragen", "Herstellkosten einer Baugruppe aus Arbeitsplänen und Zukaufpreisen; "
                                                 "Anfrageliste für alle fremd gefertigten Teile."))
        # ---- Kalkulation
        k, kl = karte()
        zeile = QHBoxLayout()
        t = QLabel("Kalkulation")
        t.setObjectName("Abschnitt")
        zeile.addWidget(t)
        self.baugruppe = QComboBox()
        self.baugruppe.setAccessibleName("Baugruppe")
        self.baugruppe.setMinimumContentsLength(22)
        self.baugruppe.activated.connect(lambda _: self.rechnen())
        zeile.addWidget(self.baugruppe, 1)
        zeile.addWidget(QLabel("Anzahl"))
        self.anzahl = QSpinBox()
        self.anzahl.setRange(1, 10000)
        self.anzahl.valueChanged.connect(lambda _: self.rechnen())
        zeile.addWidget(self.anzahl)
        self.pdf_knopf = QPushButton("Kalkulation PDF …")
        self.pdf_knopf.clicked.connect(lambda: self.kalkulation_pdf())
        zeile.addWidget(self.pdf_knopf)
        kl.addLayout(zeile)
        self.tabelle = _tabelle(["Pos", "Menge", "Benennung", "Sachnummer", "Art", "Einzel €", "Gesamt €", "Hinweis"],
                                220)
        self.tabelle.cellChanged.connect(self._preis_in_tabelle)
        self.tabelle.cellDoubleClicked.connect(self._zeile_doppelklick)
        kl.addWidget(self.tabelle)
        tipp = QLabel("Zukaufpreise direkt in der Spalte „Einzel €“ eintragen. Doppelklick auf ein Bauteil öffnet "
                      "seinen Arbeitsplan.")
        tipp.setObjectName("Klein")
        kl.addWidget(tipp)
        self.summe_text = QLabel()
        self.summe_text.setWordWrap(True)
        kl.addWidget(self.summe_text)
        lay.addWidget(k)

        # ---- Kostensätze
        k, kl = karte()
        t = QLabel("Kostensätze des Projekts")
        t.setObjectName("Abschnitt")
        kl.addWidget(t)
        zeile = QHBoxLayout()
        self.stunden = _tabelle(["Maschine / Platz", "€ je Stunde"], 290)
        self.stunden.cellChanged.connect(lambda z, s: self._satz_geaendert("stundensaetze", self.stunden, z, s))
        zeile.addWidget(self.stunden)
        self.material = _tabelle(["Werkstoffgruppe", "€ je kg Rohteil"], 290)
        self.material.cellChanged.connect(lambda z, s: self._satz_geaendert("materialpreise", self.material, z, s))
        zeile.addWidget(self.material)
        kl.addLayout(zeile)
        h = QLabel(A.SCHAETZ_HINWEIS)
        h.setObjectName("Klein")
        h.setWordWrap(True)
        kl.addWidget(h)
        lay.addWidget(k)

        # ---- Anfrageliste
        k, kl = karte()
        zeile = QHBoxLayout()
        t = QLabel("Anfrageliste Fremdfertigung")
        t.setObjectName("Abschnitt")
        zeile.addWidget(t)
        zeile.addStretch()
        zeile.addWidget(QLabel("Anfragender"))
        self.absender = QLineEdit()
        self.absender.setPlaceholderText("Name, Telefon, E-Mail")
        zeile.addWidget(self.absender, 1)
        self.anfrage_knopf = QPushButton("Anfrage PDF …")
        self.anfrage_knopf.setObjectName("Haupt")
        self.anfrage_knopf.clicked.connect(lambda: self.anfrage_pdf())
        zeile.addWidget(self.anfrage_knopf)
        kl.addLayout(zeile)
        self.anfragen = _tabelle(["Zeichnung", "Benennung", "Werkstoff", "Rohteil", "Bearbeitung", "Menge"], 140)
        self.anfragen.setEditTriggers(QAbstractItemView.NoEditTriggers)
        kl.addWidget(self.anfragen)
        self.anfrage_hinweis = QLabel()
        self.anfrage_hinweis.setObjectName("Klein")
        self.anfrage_hinweis.setWordWrap(True)
        kl.addWidget(self.anfrage_hinweis)
        lay.addWidget(k)
        lay.addStretch()

        aussen = QVBoxLayout(self)
        aussen.setContentsMargins(0, 0, 0, 0)
        aussen.addWidget(scrollbar(inhalt))

    # ================================================================ Laden
    def setze_projekt(self, projekt: Projekt):
        self.projekt = projekt
        self.laden()

    def laden(self):
        if not self.projekt:
            return
        gid = self.baugruppe.currentData()
        self.baugruppe.clear()
        for g in self.projekt.baugruppen():
            self.baugruppe.addItem(f"{g['nr']} {g['name']}", g["id"])
        if gid is not None:
            self.baugruppe.setCurrentIndex(max(0, self.baugruppe.findData(gid)))
        self._saetze_fuellen()
        self.rechnen()
        self._anfragen_fuellen()

    def _saetze_fuellen(self):
        s = self.projekt.kostensaetze()
        self._fuellt = True
        for tab, daten in ((self.stunden, s["stundensaetze"]), (self.material, s["materialpreise"])):
            tab.setRowCount(len(daten))
            for i, (name, wert) in enumerate(daten.items()):
                tab.setItem(i, 0, _fest(name))
                tab.setItem(i, 1, QTableWidgetItem(euro(wert)))
        self._fuellt = False

    def _satz_geaendert(self, art: str, tab: QTableWidget, z: int, s: int):
        if self._fuellt or s != 1:
            return
        wert = _zahl(tab.item(z, 1).text())
        if wert is None or wert < 0:
            self.meldung.emit("Bitte eine Zahl ≥ 0 eingeben.", True)
            self._saetze_fuellen()
            return
        self.setze_satz(art, tab.item(z, 0).text(), wert)

    def setze_satz(self, art: str, name: str, wert: float | None):
        s = self.projekt.kostensaetze()
        if wert is None:
            s[art].pop(name, None)
        else:
            s[art][name] = wert
        self.projekt.kostensaetze_speichern(s)
        self.rechnen()

    # ================================================================ Kalkulation
    def rechnen(self):
        gid = self.baugruppe.currentData()
        self.pdf_knopf.setEnabled(gid is not None)
        if not self.projekt or gid is None:
            self.tabelle.setRowCount(0)
            self.summe_text.setText("Zuerst eine Baugruppe speichern (Seite „Baugruppen“).")
            return
        try:
            self.zeilen, self.summe, self.fehlend, _ = self.projekt.kalkulation_baugruppe(gid, self.anzahl.value())
        except ProjektFehler as exc:
            self.summe_text.setText(f"⚠ {exc}")
            return
        self._fuellt = True
        self.tabelle.setRowCount(len(self.zeilen))
        for i, z in enumerate(self.zeilen):
            werte = [str(z.pos), str(z.menge), z.benennung, z.sachnummer, z.art,
                     "" if z.einzel is None else euro(z.einzel),
                     "–" if z.gesamt is None else euro(z.gesamt), z.hinweis]
            for j, w in enumerate(werte):
                self.tabelle.setItem(i, j, QTableWidgetItem(w) if (j == 5 and z.art == "Zukauf") else _fest(w))
        self._fuellt = False
        anteile = {}
        for z in self.zeilen:
            if z.gesamt is not None:
                anteile[z.art] = anteile.get(z.art, 0) + z.gesamt * self.anzahl.value()
        text = " · ".join(f"{a} {euro(w)} €" for a, w in anteile.items())
        n = self.anzahl.value()
        self.summe_text.setText(
            f"<b>Herstellkosten {euro(self.summe)} €</b>" + (f" für {n} Baugruppen" if n > 1 else " je Baugruppe")
            + (f" ({text})" if text else "")
            + (f"<br>⚠ Ohne Preis, nicht in der Summe: {', '.join(self.fehlend)}" if self.fehlend else ""))

    def _preis_in_tabelle(self, z: int, s: int):
        if self._fuellt or s != 5 or not 0 <= z < len(self.zeilen):
            return
        text = self.tabelle.item(z, 5).text()
        self.zukaufpreis(self.zeilen[z].sachnummer, _zahl(text) if text.strip() else None)

    def zukaufpreis(self, norm: str, preis: float | None):
        self.setze_satz("zukauf", norm, preis)

    def _zeile_doppelklick(self, z: int, _s: int):
        if 0 <= z < len(self.zeilen) and self.zeilen[z].art in ("Eigen", "Fremd", "–"):
            t = next((t for t in self.projekt.teile() if t["nr"] == self.zeilen[z].sachnummer), None)
            if t:
                self.arbeitsplan_oeffnen.emit(t["id"])

    # ================================================================ Anfragen & PDF
    def _anfragen_fuellen(self):
        e = self.projekt.anfrage_eintraege()
        self.anfragen.setRowCount(len(e))
        for i, a in enumerate(e):
            for j, w in enumerate((a["nr"], a["benennung"], a["werkstoff"].split(" · ")[0], a["rohteil"],
                                   a["verfahren"], str(a["menge"]))):
                self.anfragen.setItem(i, j, QTableWidgetItem(w))
        self.anfrage_knopf.setEnabled(bool(e))
        self.anfrage_hinweis.setText(
            "Teile erscheinen hier, wenn ihr Arbeitsplan auf „Fremdfertigung“ steht. Der Anfrage die Zeichnungen "
            "(Seite „Zeichnungen“, PDF/DXF) und STEP-Dateien beilegen." if not e else
            f"{len(e)} Teil(e) für die Anfrage. Zeichnungen (PDF/DXF) und STEP-Dateien beilegen; Angebotspreise danach "
            "im Arbeitsplan unter „Angebot €/Stück“ eintragen.")

    def _ziel(self, titel_: str, name: str) -> str | None:
        ziel, _ = QFileDialog.getSaveFileName(self, titel_, str(self.projekt.pfad.parent / name), "PDF (*.pdf)")
        return ziel or None

    def kalkulation_pdf(self, ziel: str | None = None) -> Path | None:
        gid = self.baugruppe.currentData()
        if gid is None:
            return None
        g = self.projekt.baugruppe(gid)
        ziel = ziel or self._ziel("Kalkulation speichern", f"Kalkulation_{g['nr']}.pdf")
        if not ziel:
            return None
        from ..pdf import kalkulation_erstellen
        pfad = kalkulation_erstellen(g["name"], g["nr"], self.zeilen, self.summe, self.fehlend, self.anzahl.value(),
                                     ziel, self.projekt.name)
        self.meldung.emit(f"Kalkulation gespeichert: {Path(pfad).name}", False)
        return Path(pfad)

    def anfrage_pdf(self, ziel: str | None = None) -> Path | None:
        e = self.projekt.anfrage_eintraege()
        if not e:
            return None
        ziel = ziel or self._ziel("Anfrage speichern", "Anfrage_Fremdfertigung.pdf")
        if not ziel:
            return None
        from ..pdf import anfrageliste_erstellen
        pfad = anfrageliste_erstellen(e, ziel, self.projekt.name, self.absender.text().strip())
        self.meldung.emit(f"Anfrageliste gespeichert: {Path(pfad).name}", False)
        return Path(pfad)
