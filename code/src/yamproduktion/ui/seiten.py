"""Die Seiten des Hauptfensters."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal, QStandardPaths
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog,
    QFormLayout, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
    QProgressBar, QPushButton, QScrollArea, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..berechnungen.basis import formatiere
from ..einheiten import EinheitFehler, umrechnen, zahl_lesen
from ..modell import (ARTEN_ANFORDERUNG, DATEIENDUNG, NEU_PRUEFEN, PRIORITAETEN, STATUS, Projekt,
                      ProjektFehler)
from .rueckverfolgung import RueckverfolgungPanel

PHASEN_INFO = {
    "P1": ("Ideen und TRIZ", "jetzt"),
    "P2": ("Anforderungen, Eigenschaften, Funktionen", "jetzt"),
    "P3": ("Morphologischer Kasten und Nutzwertanalyse", "jetzt"),
    "P4": ("Rotor, Antrieb, Getriebe, Welle …", "jetzt"),
    "P5": ("Bauteile, Baugruppen, Zeichnungen", "MS6–MS8"),
    "P6": ("Arbeitspläne und Kosten", "MS9"),
    "P7": ("Montageplan und Montageplatte", "MS10"),
    "P8": ("Checklisten und Abnahme", "MS11"),
    "P9": ("Wartung und Rückmeldung", "MS11"),
}


def leeren(layout) -> None:
    """Alle Widgets sofort aus einem Layout entfernen (ohne kurzzeitiges Überlappen)."""
    while layout.count():
        eintrag = layout.takeAt(0)
        w = eintrag.widget()
        if w:
            w.hide()
            w.setParent(None)
            w.deleteLater()
        elif eintrag.layout():
            leeren(eintrag.layout())


def titel(text: str, untertitel: str = "") -> QWidget:
    box = QWidget()
    lay = QVBoxLayout(box)
    lay.setContentsMargins(0, 0, 0, 8)
    t = QLabel(text)
    t.setObjectName("Titel")
    lay.addWidget(t)
    if untertitel:
        u = QLabel(untertitel)
        u.setObjectName("Untertitel")
        u.setWordWrap(True)
        lay.addWidget(u)
    return box


def karte() -> tuple[QFrame, QVBoxLayout]:
    rahmen = QFrame()
    rahmen.setObjectName("Karte")
    lay = QVBoxLayout(rahmen)
    lay.setContentsMargins(20, 16, 20, 16)
    lay.setSpacing(10)
    return rahmen, lay


def scrollbar(inhalt: QWidget) -> QScrollArea:
    s = QScrollArea()
    s.setWidgetResizable(True)
    s.setWidget(inhalt)
    s.setFrameShape(QFrame.NoFrame)
    return s


# ---------------------------------------------------------------- Neues Projekt
class NeuesProjektDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Neues Projekt anlegen")
        self.setMinimumWidth(560)
        lay = QVBoxLayout(self)
        lay.addWidget(titel("Neues Projekt", "Ein Projekt enthält ein Produkt mit allen Phasen von der Idee bis zur Inbetriebnahme."))

        form = QFormLayout()
        self.name = QLineEdit("Kleinwindanlage KWA-5")
        self.produkt = QLineEdit("Mini-Windkraftanlage 5 kW")
        self.beispiel = QCheckBox("Typische Anforderungen einer Kleinwindanlage vorab eintragen")
        self.beispiel.setChecked(True)
        ordner = Path(QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)) / "YamProduktion"
        self.ordner = QLineEdit(str(ordner))
        aendern = QPushButton("Ändern …")
        aendern.clicked.connect(self._ordner_waehlen)
        ordner_zeile = QHBoxLayout()
        ordner_zeile.addWidget(self.ordner, 1)
        ordner_zeile.addWidget(aendern)
        form.addRow("Projektname", self.name)
        form.addRow("Produkt", self.produkt)
        form.addRow("Speicherort", ordner_zeile)
        form.addRow("", self.beispiel)
        lay.addLayout(form)

        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        knoepfe.button(QDialogButtonBox.Ok).setText("Projekt anlegen")
        knoepfe.button(QDialogButtonBox.Ok).setObjectName("Haupt")
        knoepfe.button(QDialogButtonBox.Cancel).setText("Abbrechen")
        knoepfe.accepted.connect(self.accept)
        knoepfe.rejected.connect(self.reject)
        lay.addWidget(knoepfe)

    def _ordner_waehlen(self):
        ordner = QFileDialog.getExistingDirectory(self, "Speicherort wählen", self.ordner.text())
        if ordner:
            self.ordner.setText(ordner)

    def pfad(self) -> Path:
        dateiname = "".join(c if c.isalnum() or c in "-_ " else "_" for c in self.name.text()).strip() or "Projekt"
        return Path(self.ordner.text()) / f"{dateiname}{DATEIENDUNG}"


# ---------------------------------------------------------------- Willkommen
class WillkommenSeite(QWidget):
    neu_angefordert = Signal()
    oeffnen_angefordert = Signal()

    def __init__(self):
        super().__init__()
        aussen = QVBoxLayout(self)
        aussen.setAlignment(Qt.AlignCenter)
        box, lay = karte()
        box.setMaximumWidth(620)
        lay.addWidget(titel("Willkommen bei YamProduktion",
                            "Entwickle dein Produkt von der Idee über Berechnung und Konstruktion "
                            "bis zur Inbetriebnahme – alles an einem Ort."))
        neu = QPushButton("Neues Projekt anlegen")
        neu.setObjectName("Haupt")
        neu.clicked.connect(self.neu_angefordert)
        oeffnen = QPushButton("Vorhandenes Projekt öffnen …")
        oeffnen.clicked.connect(self.oeffnen_angefordert)
        reihe = QHBoxLayout()
        reihe.addWidget(neu)
        reihe.addWidget(oeffnen)
        reihe.addStretch()
        lay.addLayout(reihe)
        tipp = QLabel("Tipp: ⌘N legt ein neues Projekt an, ⌘O öffnet eines, ⌘B blendet die Seitenleiste ein und aus.")
        tipp.setObjectName("Klein")
        tipp.setWordWrap(True)
        lay.addWidget(tipp)
        aussen.addWidget(box)


# ---------------------------------------------------------------- Übersicht
class UebersichtSeite(QWidget):
    gehe_zu = Signal(str)          # Navigationsschlüssel
    gehe_zu_objekt = Signal(str, int)
    meldung = Signal(str, bool)

    PHASE_ZIEL = {"P1": "ideen", "P2": "anforderungen", "P3": "konzept", "P4": "berechnungen", "P5": "bauteile",
                  "P6": "arbeitsplaene", "P7": "montage", "P8": "inbetriebnahme", "P9": "wartung"}

    def __init__(self):
        super().__init__()
        self.projekt: Projekt | None = None
        inhalt = QWidget()
        self.lay = QVBoxLayout(inhalt)
        self.lay.setContentsMargins(32, 24, 32, 24)
        self.kopf = titel("")
        self.lay.addWidget(self.kopf)
        kz = QHBoxLayout()
        self.kennzahlen = QLabel()
        self.kennzahlen.setObjectName("Untertitel")
        self.kennzahlen.setWordWrap(True)
        kz.addWidget(self.kennzahlen, 1)
        self.lastenheft_knopf = QPushButton("Produkt-Lastenheft (PDF) …")
        self.lastenheft_knopf.setToolTip("Ideen, Anforderungen, Eigenschaften, Funktionen und Konzept als PDF")
        self.lastenheft_knopf.clicked.connect(lambda: self.lastenheft_speichern())
        kz.addWidget(self.lastenheft_knopf)
        self.lay.addLayout(kz)

        # Hinweis „neu prüfen“
        self.warnung = QFrame()
        self.warnung.setObjectName("Warnung")
        wl = QHBoxLayout(self.warnung)
        wl.setContentsMargins(16, 12, 16, 12)
        self.warnung_text = QLabel()
        self.warnung_text.setWordWrap(True)
        wl.addWidget(self.warnung_text, 1)
        self.warnung_knopf = QPushButton("Ansehen")
        self.warnung_knopf.clicked.connect(self._erstes_offenes)
        wl.addWidget(self.warnung_knopf)
        self.lay.addWidget(self.warnung)

        a = QLabel("Phasen des Produkts")
        a.setObjectName("Abschnitt")
        self.lay.addWidget(a)
        self.raster = QGridLayout()
        self.raster.setSpacing(12)
        self.lay.addLayout(self.raster)
        self.lay.addStretch()
        aussen = QVBoxLayout(self)
        aussen.setContentsMargins(0, 0, 0, 0)
        aussen.addWidget(scrollbar(inhalt))

    def setze_projekt(self, projekt: Projekt):
        self.projekt = projekt
        self.aktualisieren()

    def aktualisieren(self):
        if not self.projekt:
            return
        p = self.projekt
        self.kopf.findChild(QLabel, "Titel").setText(p.name)
        self.kennzahlen.setText(
            f"Produkt: {p.produkt or '–'}  ·  {len(p.liste('idee'))} Ideen  ·  {len(p.anforderungen())} Anforderungen  ·  "
            f"{len(p.liste('funktion'))} Funktionen  ·  {len(p.liste('variante'))} Varianten  ·  "
            f"{len(p.berechnungen())} Berechnungen  ·  Datei: {p.pfad.name}")
        offen = p.neu_zu_pruefen()
        self.warnung.setVisible(bool(offen))
        if offen:
            liste = ", ".join(f"{b.nr} {b.titel}" for b in offen[:4]) + (" …" if len(offen) > 4 else "")
            self.warnung_text.setText(f"<b>⚠ {len(offen)} {'Objekt muss' if len(offen) == 1 else 'Objekte müssen'} "
                                      f"neu geprüft werden</b><br>{liste}")
        leeren(self.raster)
        for i, ph in enumerate(p.phasen()):
            self.raster.addWidget(self._phasenkarte(ph), i // 3, i % 3)

    def _erstes_offenes(self):
        offen = self.projekt.neu_zu_pruefen() if self.projekt else []
        if offen:
            self.gehe_zu_objekt.emit(offen[0].typ, offen[0].id)

    def lastenheft_speichern(self, ziel: str | None = None):
        if not self.projekt:
            return None
        if not ziel:
            start = str(self.projekt.pfad.parent / f"Produkt-Lastenheft_{self.projekt.name}.pdf")
            ziel, _ = QFileDialog.getSaveFileName(self, "Produkt-Lastenheft speichern", start, "PDF (*.pdf)")
            if not ziel:
                return None
        from ..pdf import lastenheft_erstellen
        pfad = lastenheft_erstellen(self.projekt, ziel)
        self.meldung.emit(f"Produkt-Lastenheft gespeichert: {Path(pfad).name}", False)
        return pfad

    def _phasenkarte(self, ph) -> QFrame:
        box, bl = karte()
        kopf = QHBoxLayout()
        kopf.addWidget(QLabel(f"<b>{ph.nr} · {ph.name}</b>"), 1)
        marke = QLabel({"offen": "○ offen", "in Arbeit": "◐ in Arbeit", "freigegeben": "● freigegeben"}[ph.status])
        marke.setObjectName({"offen": "MarkeGrau", "in Arbeit": "MarkeBlau", "freigegeben": "MarkeGruen"}[ph.status])
        kopf.addWidget(marke)
        bl.addLayout(kopf)
        was = QLabel(PHASEN_INFO[ph.nr][0])
        was.setObjectName("Klein")
        was.setWordWrap(True)
        bl.addWidget(was)
        f = self.projekt.phase_fortschritt(ph.nr)
        balken = QProgressBar()
        balken.setRange(0, 100)
        balken.setValue(f["prozent"])
        balken.setFormat(f"%p % · {f['erledigt']} von {f['gesamt']}")
        balken.setToolTip("Erledigte Aufgaben und geprüfte/freigegebene Objekte der Phase")
        bl.addWidget(balken)
        if ph.status == "freigegeben":
            datum = ph.freigegeben.replace("T", " ")[:16]
            d = QLabel(f"Freigegeben am {datum}")
            d.setObjectName("Klein")
            bl.addWidget(d)
        reihe = QHBoxLayout()
        ziel = self.PHASE_ZIEL.get(ph.nr)
        if ziel:
            oeffnen = QPushButton("Öffnen")
            oeffnen.clicked.connect(lambda _=False, z=ziel: self.gehe_zu.emit(z))
            reihe.addWidget(oeffnen)
            if ph.status != "freigegeben":
                hindernisse = self.projekt.phase_hindernisse(ph.nr)
                frei = QPushButton("Phase freigeben")
                frei.setObjectName("Haupt" if not hindernisse else "")
                frei.setToolTip("Bereit zur Freigabe" if not hindernisse else "Noch offen:\n• " + "\n• ".join(hindernisse))
                frei.clicked.connect(lambda _=False, n=ph.nr: self._freigeben(n))
                reihe.addWidget(frei)
        else:
            s = QLabel(f"kommt in {PHASEN_INFO[ph.nr][1]}")
            s.setObjectName("Klein")
            reihe.addWidget(s)
        reihe.addStretch()
        bl.addLayout(reihe)
        return box

    def _freigeben(self, nr: str):
        try:
            ph = self.projekt.phase_freigeben(nr)
            self.meldung.emit(f"Phase {nr} {ph.name} freigegeben.", False)
        except ProjektFehler as exc:
            QMessageBox.information(self, "Noch nicht freigabefähig", str(exc))
            self.meldung.emit(f"Phase {nr} ist noch nicht freigabefähig.", True)
        self.aktualisieren()


# ---------------------------------------------------------------- Anforderungen
class AnforderungenSeite(QWidget):
    meldung = Signal(str, bool)   # Text, ist_fehler
    geaendert = Signal()
    gehe_zu_objekt = Signal(str, int)

    SPALTEN = ["Nr", "Beschreibung", "Zielwert", "Einheit", "Art", "Priorität", "Status"]
    SP_NR, SP_TEXT, SP_WERT, SP_EINHEIT, SP_ART, SP_PRIO, SP_STATUS = range(7)

    def __init__(self):
        super().__init__()
        self.projekt: Projekt | None = None
        self._laedt = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 24, 32, 24)
        lay.addWidget(titel("Anforderungen & Eigenschaften",
                            "Was muss das Produkt können, welche Eigenschaften hat es? Jede Zeile mit Zielwert und "
                            "Einheit. Änderungen werden sofort gespeichert; abhängige Berechnungen werden markiert."))
        reihe = QHBoxLayout()
        self.neu = QPushButton("+  Neue Anforderung")
        self.neu.setObjectName("Haupt")
        self.neu.clicked.connect(self.neue_anforderung)
        self.loeschen = QPushButton("Ausgewählte löschen")
        self.loeschen.clicked.connect(self.auswahl_loeschen)
        self.details_knopf = QPushButton("Rückverfolgung ausblenden")
        self.details_knopf.clicked.connect(self._details_umschalten)
        reihe.addWidget(self.neu)
        reihe.addWidget(self.loeschen)
        reihe.addStretch()
        reihe.addWidget(self.details_knopf)
        lay.addLayout(reihe)

        self.tabelle = QTableWidget(0, len(self.SPALTEN))
        self.tabelle.setHorizontalHeaderLabels(self.SPALTEN)
        self.tabelle.verticalHeader().setVisible(False)
        self.tabelle.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabelle.setAlternatingRowColors(True)
        kopf = self.tabelle.horizontalHeader()
        kopf.setSectionResizeMode(self.SP_TEXT, QHeaderView.Stretch)
        for spalte, breite in ((self.SP_NR, 70), (self.SP_ART, 140), (self.SP_WERT, 80), (self.SP_EINHEIT, 70),
                               (self.SP_PRIO, 85), (self.SP_STATUS, 135)):
            self.tabelle.setColumnWidth(spalte, breite)
        self.tabelle.verticalHeader().setDefaultSectionSize(40)
        self.tabelle.cellChanged.connect(self._zelle_geaendert)
        self.tabelle.currentCellChanged.connect(lambda *_: self._details_zeigen())

        self.panel = RueckverfolgungPanel()
        self.panel.gehe_zu.connect(self.gehe_zu_objekt)
        teiler = QSplitter(Qt.Horizontal)
        teiler.addWidget(self.tabelle)
        teiler.addWidget(self.panel)
        teiler.setStretchFactor(0, 1)
        teiler.setChildrenCollapsible(False)
        teiler.setSizes([1000, 340])
        lay.addWidget(teiler, 1)

    def setze_projekt(self, projekt: Projekt):
        self.projekt = projekt
        self.laden()

    def _details_umschalten(self):
        sichtbar = not self.panel.isVisible()
        self.panel.setVisible(sichtbar)
        self.details_knopf.setText("Rückverfolgung ausblenden" if sichtbar else "Rückverfolgung einblenden")

    def _combo(self, werte, aktuell, rueckruf) -> QComboBox:
        combo = QComboBox()
        combo.addItems(list(werte))
        if aktuell not in werte:
            combo.addItem(aktuell)
        combo.setCurrentText(aktuell)
        combo.currentTextChanged.connect(rueckruf)
        return combo

    def laden(self, auswahl_id: int | None = None):
        if not self.projekt:
            return
        self._laedt = True
        if auswahl_id is None:
            auswahl_id = self._aktuelle_id()
        liste = self.projekt.anforderungen()
        # alte Auswahlfelder sofort verstecken (sonst kurz sichtbar, bis Qt sie löscht)
        for z in range(self.tabelle.rowCount()):
            for sp in range(self.tabelle.columnCount()):
                w = self.tabelle.cellWidget(z, sp)
                if w:
                    w.hide()
        self.tabelle.setRowCount(len(liste))
        neue_zeile = -1
        for zeile, a in enumerate(liste):
            if a.id == auswahl_id:
                neue_zeile = zeile
            texte = {
                self.SP_NR: a.nr, self.SP_TEXT: a.text,
                self.SP_WERT: "" if a.zielwert is None else f"{a.zielwert:g}".replace(".", ","),
                self.SP_EINHEIT: a.einheit,
            }
            for spalte, wert in texte.items():
                item = QTableWidgetItem(wert)
                item.setData(Qt.UserRole, a.id)
                if spalte == self.SP_NR:
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                if spalte == self.SP_WERT:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.tabelle.setItem(zeile, spalte, item)
            self.tabelle.setCellWidget(zeile, self.SP_ART, self._combo(
                ARTEN_ANFORDERUNG, a.art, lambda t, i=a.id: self._feld_geaendert(i, art=t)))
            self.tabelle.setCellWidget(zeile, self.SP_PRIO, self._combo(
                PRIORITAETEN, a.prioritaet, lambda t, i=a.id: self._feld_geaendert(i, prioritaet=t)))
            status = self._combo(STATUS, a.status, lambda t, i=a.id: self._status_geaendert(i, t))
            if a.status == NEU_PRUEFEN:
                status.setObjectName("StatusWarnung")
            self.tabelle.setCellWidget(zeile, self.SP_STATUS, status)
        self._laedt = False
        if neue_zeile >= 0:
            self.tabelle.setCurrentCell(neue_zeile, self.SP_TEXT)
        self._details_zeigen()

    def _aktuelle_id(self) -> int | None:
        item = self.tabelle.item(self.tabelle.currentRow(), self.SP_NR) if self.tabelle.currentRow() >= 0 else None
        return item.data(Qt.UserRole) if item else None

    def auswaehlen(self, id_: int):
        self.laden(auswahl_id=id_)

    def _details_zeigen(self):
        if self._laedt or not self.projekt:
            return
        id_ = self._aktuelle_id()
        if id_ is None:
            self.panel.leer()
            return
        try:
            a = self.projekt.anforderung(id_)
        except ProjektFehler:
            self.panel.leer()
            return
        self.panel.zeigen(self.projekt, "anforderung", a.id, a.nr, a.text, a.status, a.version)

    def neue_anforderung(self):
        if not self.projekt:
            return
        a = self.projekt.anforderung_neu("Neue Anforderung")
        self.laden(auswahl_id=a.id)
        zeile = self.tabelle.currentRow()
        self.tabelle.editItem(self.tabelle.item(zeile, self.SP_TEXT))
        self.meldung.emit(f"{a.nr} angelegt – Text eingeben und mit Enter bestätigen.", False)
        self.geaendert.emit()

    def auswahl_loeschen(self):
        zeilen = sorted({i.row() for i in self.tabelle.selectedIndexes()})
        if not zeilen or not self.projekt:
            self.meldung.emit("Bitte zuerst eine Zeile auswählen.", True)
            return
        ids = [self.tabelle.item(z, self.SP_NR).data(Qt.UserRole) for z in zeilen]
        nrs = [self.tabelle.item(z, self.SP_NR).text() for z in zeilen]
        betroffen = {b.nr for i in ids for b in self.projekt.wirkt_auf("anforderung", i, rekursiv=True)}
        frage = f"{', '.join(nrs)} wirklich löschen?"
        if betroffen:
            frage += f"\n\nDavon hängen ab: {', '.join(sorted(betroffen))}. Diese werden als „neu prüfen“ markiert."
        if QMessageBox.question(self, "Löschen?", frage) != QMessageBox.Yes:
            return
        for i in ids:
            self.projekt.anforderung_loeschen(i)
        self.laden()
        self.meldung.emit(f"{', '.join(nrs)} gelöscht.", False)
        self.geaendert.emit()

    def _feld_geaendert(self, id_: int, **feld):
        if self._laedt or not self.projekt:
            return
        try:
            a = self.projekt.anforderung_aendern(id_, **feld)
            self.meldung.emit(f"{a.nr} gespeichert (Version {a.version}).", False)
        except ProjektFehler as exc:
            self.meldung.emit(str(exc), True)
        self.laden(auswahl_id=id_)
        self.geaendert.emit()

    def _status_geaendert(self, id_: int, status: str):
        if self._laedt or not self.projekt or status == NEU_PRUEFEN:
            return
        try:
            self.projekt.status_setzen("anforderung", id_, status)
            self.meldung.emit(f"Status auf „{status}“ gesetzt.", False)
        except ProjektFehler as exc:
            self.meldung.emit(str(exc), True)
        self.laden(auswahl_id=id_)
        self.geaendert.emit()

    def _zelle_geaendert(self, zeile: int, spalte: int):
        if self._laedt or not self.projekt:
            return
        item = self.tabelle.item(zeile, spalte)
        id_ = item.data(Qt.UserRole)
        text = item.text().strip()
        try:
            if spalte == self.SP_TEXT:
                a = self.projekt.anforderung_aendern(id_, text=text)
            elif spalte == self.SP_WERT:
                a = self.projekt.anforderung_aendern(id_, zielwert=zahl_lesen(text))
            elif spalte == self.SP_EINHEIT:
                a = self.projekt.anforderung_aendern(id_, einheit=text)
            else:
                return
            betroffen = [b for b in self.projekt.wirkt_auf("anforderung", id_, rekursiv=True)
                         if b.status == NEU_PRUEFEN]
            zusatz = f" Neu prüfen: {', '.join(b.nr for b in betroffen)}." if betroffen and spalte != self.SP_TEXT else ""
            self.meldung.emit(f"{a.nr} gespeichert (Version {a.version}).{zusatz}", False)
            self.geaendert.emit()
        except ValueError as exc:
            hinweis = str(exc) if isinstance(exc, EinheitFehler) else \
                f"„{text}“ ist keine Zahl. Bitte z. B. 5 oder 5,5 eingeben."
            self.meldung.emit(hinweis, True)
        except ProjektFehler as exc:
            self.meldung.emit(str(exc), True)
        self.laden(auswahl_id=id_)
