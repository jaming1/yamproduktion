"""Seite „Bibliothek“ (MS14): Bücher importieren, durchsuchen, fragen, Seite ansehen, Formel übernehmen."""
from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, QSize, Qt, QThread, Signal
from PySide6.QtGui import QColor, QPainter, QPixmap, QTextCharFormat
from PySide6.QtPdf import QPdfDocument
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMessageBox, QPushButton, QScrollArea, QSpinBox, QSplitter, QTableWidget,
    QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

from ..berechnungen import formel as F
from ..berechnungen.basis import formatiere
from ..modell import Projekt, ProjektFehler
from ..wissen import texterkennung as T
from ..wissen.bibliothek import HINWEIS_FRAGE, STANDARD_ORDNER, Bibliothek, BibliothekFehler, Treffer
from .betrieb_seiten import _knopf
from .seiten import karte, titel

BILDER = "*.png *.jpg *.jpeg *.tif *.tiff"


def _klein(text: str = "") -> QLabel:
    l_ = QLabel(text)
    l_.setObjectName("Klein")
    l_.setWordWrap(True)
    return l_


class _Import(QObject):
    """Import im Hintergrund – eine Texterkennung kann je Seite Sekunden dauern."""
    fortschritt = Signal(str)
    fertig = Signal(object, str)          # Buch oder None, Fehlertext

    def __init__(self, ordner: Path, quelle, titel_: str):
        super().__init__()
        self.ordner, self.quelle, self.titel = ordner, quelle, titel_

    def laufen(self):
        bib = Bibliothek(self.ordner)                 # eigene Verbindung im eigenen Thread
        try:
            buch = bib.importieren(self.quelle, self.titel, fortschritt=self.fortschritt.emit)
            self.fertig.emit(buch, "")
        except (BibliothekFehler, OSError, ValueError) as exc:
            self.fertig.emit(None, str(exc))
        finally:
            bib.schliessen()


class FormelDialog(QDialog):
    """S20: Formel aus der Buchstelle übernehmen, Werte einsetzen, als Berechnung speichern."""

    def __init__(self, projekt: Projekt, formel_text: str, quelle: str, parent=None):
        super().__init__(parent)
        self.projekt = projekt
        self.gespeichert = None
        self.setWindowTitle("Formel als Berechnung übernehmen")
        self.resize(620, 560)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit()
        self.name.setPlaceholderText("z. B. Biegemoment Rotorwelle")
        self.formel = QLineEdit(formel_text)
        self.formel.setPlaceholderText("z. B. M_b = F · l / 4")
        self.quelle = QLineEdit(quelle)
        self.einheit = QLineEdit()
        self.einheit.setPlaceholderText("leer = wie berechnet, z. B. N·m oder N/mm²")
        form.addRow("Bezeichnung", self.name)
        form.addRow("Formel", self.formel)
        form.addRow("Quelle", self.quelle)
        form.addRow("Ergebnis in", self.einheit)
        lay.addLayout(form)
        lay.addWidget(_klein("Erlaubt: + − · / ^, Klammern, sqrt, sin, cos, tan, exp, ln, log10, π. "
                             "Werte mit Einheit eintragen – Pint rechnet die Einheiten mit und meldet Unstimmiges."))
        self.werte = QTableWidget(0, 3)
        self.werte.setHorizontalHeaderLabels(["Größe", "Wert", "Einheit"])
        self.werte.verticalHeader().hide()
        self.werte.horizontalHeader().setStretchLastSection(True)
        self.werte.setColumnWidth(0, 120)
        self.werte.setColumnWidth(1, 140)
        lay.addWidget(self.werte, 1)
        self.vorschau = QLabel("")
        self.vorschau.setWordWrap(True)
        self.vorschau.setObjectName("Abschnitt")
        lay.addWidget(self.vorschau)
        lay.addWidget(_klein(F.HINWEIS))
        knoepfe = QDialogButtonBox()
        self.rechnen = knoepfe.addButton("Rechnen", QDialogButtonBox.ActionRole)
        self.speichern = knoepfe.addButton("Als Berechnung speichern", QDialogButtonBox.AcceptRole)
        self.speichern.setObjectName("Haupt")
        knoepfe.addButton("Abbrechen", QDialogButtonBox.RejectRole)
        self.rechnen.clicked.connect(self.berechnen)
        self.speichern.clicked.connect(self._speichern)
        knoepfe.rejected.connect(self.reject)
        lay.addWidget(knoepfe)
        self.formel.textChanged.connect(self._variablen)
        self._variablen()

    def _variablen(self):
        alt = {self.werte.item(z, 0).text(): (self.werte.item(z, 1).text() if self.werte.item(z, 1) else "",
                                               self.werte.item(z, 2).text() if self.werte.item(z, 2) else "")
               for z in range(self.werte.rowCount()) if self.werte.item(z, 0)}
        try:
            namen = F.variablen(self.formel.text())
            self.vorschau.setText("")
        except F.FormelFehler as exc:
            self.vorschau.setText(f"⚠ {exc}")
            return
        self.werte.setRowCount(len(namen))
        for z, n in enumerate(namen):
            kopf = QTableWidgetItem(n)
            kopf.setFlags(kopf.flags() & ~Qt.ItemIsEditable)
            self.werte.setItem(z, 0, kopf)
            w, e = alt.get(n, ("", ""))
            self.werte.setItem(z, 1, QTableWidgetItem(w))
            self.werte.setItem(z, 2, QTableWidgetItem(e))

    def eingaben(self) -> F.FormelEingaben:
        werte = {}
        for z in range(self.werte.rowCount()):
            n = self.werte.item(z, 0).text()
            w = (self.werte.item(z, 1).text() if self.werte.item(z, 1) else "").strip().replace(",", ".")
            e = (self.werte.item(z, 2).text() if self.werte.item(z, 2) else "").strip()
            try:
                werte[n] = [float(w) if w else None, e]
            except ValueError:
                raise F.FormelFehler(f"„{w}“ bei {n} ist keine Zahl.")
        return F.FormelEingaben(self.formel.text().strip(), werte, self.einheit.text().strip(),
                                self.name.text().strip(), self.quelle.text().strip())

    def berechnen(self) -> bool:
        try:
            erg = F.berechne(self.eingaben())
        except F.FormelFehler as exc:
            self.vorschau.setText(f"⚠ {exc}")
            return False
        g = erg.ergebnisse[0]
        self.vorschau.setText(f"{erg.schritte[0].einsetzen}\n= {formatiere(g.wert)} {g.einheit}")
        return True

    def _speichern(self):
        if not self.berechnen():
            return
        try:
            self.gespeichert = self.projekt.formel_speichern(self.eingaben())
        except ProjektFehler as exc:
            self.vorschau.setText(f"⚠ {exc}")
            return
        self.accept()


def formel_aus_text(text: str) -> str:
    """Erste Zeile der Auswahl, die wie eine Gleichung aussieht."""
    for zeile in text.splitlines():
        if "=" in zeile and re.search(r"[A-Za-zα-ωΑ-Ω]", zeile.split("=")[0]):
            return zeile.strip().rstrip(".,;")
    return text.strip().splitlines()[0] if text.strip() else ""


class WissenSeite(QWidget):
    meldung = Signal(str, bool)
    gespeichert = Signal()

    def __init__(self, einstellungen: QSettings | None = None):
        super().__init__()
        self.einst = einstellungen or QSettings()
        self.projekt: Projekt | None = None
        self.bib: Bibliothek | None = None
        self.synchron = False              # Tests: Import ohne Hintergrund-Thread
        self._thread = None
        self._buch = None
        self._nr = 1
        self._suchwoerter: list[str] = []
        self.dok = QPdfDocument(self)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 24, 32, 24)
        lay.addWidget(titel("Bibliothek", "Eigene Fachbücher durchsuchen und Formeln mit Quelle übernehmen. "
                                          "Die Scans bleiben auf diesem Mac und werden nie exportiert."))
        teiler = QSplitter(Qt.Horizontal)
        lay.addWidget(teiler, 1)

        # ---- links: Bücher
        links, ll = karte()
        k = QLabel("Bücher")
        k.setObjectName("Abschnitt")
        ll.addWidget(k)
        self.buecher = QListWidget()
        self.buecher.setWordWrap(True)
        self.buecher.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.buecher.currentRowChanged.connect(self._buch_gewaehlt)
        ll.addWidget(self.buecher, 1)
        zeile = QHBoxLayout()
        zeile.addWidget(_knopf("PDF …", self._pdf_waehlen, True, "Gescanntes Buch als PDF hinzufügen"))
        zeile.addWidget(_knopf("Bilder …", self._bilder_waehlen, tipp="Fotos/Scans einzelner Seiten als ein Buch"))
        ll.addLayout(zeile)
        form = QFormLayout()
        self.titel_feld = QLineEdit()
        self.titel_feld.editingFinished.connect(self._buch_aendern)
        self.versatz = QSpinBox()
        self.versatz.setRange(-50, 500)
        self.versatz.setToolTip("PDF-Seite minus gedruckte Seitenzahl, z. B. 12, wenn S. 1 auf PDF-Seite 13 steht")
        self.versatz.editingFinished.connect(self._buch_aendern)
        form.addRow("Titel", self.titel_feld)
        form.addRow("Seitenversatz", self.versatz)
        ll.addLayout(form)
        self.buch_info = _klein()
        ll.addWidget(self.buch_info)
        ll.addWidget(_knopf("Buch entfernen", self._buch_loeschen))
        self.ordner_info = _klein()
        ll.addWidget(self.ordner_info)
        ll.addWidget(_knopf("Ordner wählen …", self._ordner_waehlen))
        self.ocr_info = _klein()
        ll.addWidget(self.ocr_info)
        self.fortschritt = _klein()
        ll.addWidget(self.fortschritt)
        links.setMinimumWidth(300)
        teiler.addWidget(links)

        # ---- Mitte: Suche und Fragen
        mitte, ml = karte()
        self.suche = QLineEdit()
        self.suche.setPlaceholderText("Suchwörter oder eine Frage, z. B. „Wie berechne ich die Lagerlebensdauer?“")
        self.suche.returnPressed.connect(self.suchen)
        ml.addWidget(self.suche)
        zeile = QHBoxLayout()
        zeile.addWidget(_knopf("Suchen", self.suchen, True, "Alle Wörter auf einer Seite; „…“ für Wortgruppen"))
        zeile.addWidget(_knopf("Fragen", self.fragen, tipp="Stichwörter aus der Frage, die besten Fundstellen"))
        self.nur_buch = QComboBox()
        self.nur_buch.setToolTip("Nur in einem Buch suchen")
        zeile.addStretch(1)
        ml.addLayout(zeile)
        ml.addWidget(self.nur_buch)
        self.antwort = _klein()
        ml.addWidget(self.antwort)
        self.treffer = QListWidget()
        self.treffer.setWordWrap(True)
        self.treffer.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.treffer.currentRowChanged.connect(self._treffer_gewaehlt)
        ml.addWidget(self.treffer, 1)
        mitte.setMinimumWidth(320)
        teiler.addWidget(mitte)

        # ---- rechts: Seite
        rechts, rl = karte()
        kopf = QHBoxLayout()
        self.zurueck = _knopf("◀", lambda: self.seite_zeigen(self._nr - 1), tipp="Vorherige Seite")
        self.vor = _knopf("▶", lambda: self.seite_zeigen(self._nr + 1), tipp="Nächste Seite")
        self.seiten_info = QLabel("")
        self.seiten_info.setWordWrap(True)
        self.zoom = QComboBox()
        self.zoom.addItems(["75 %", "100 %", "150 %", "200 %"])
        self.zoom.setCurrentIndex(1)
        self.zoom.currentIndexChanged.connect(lambda _i: self.seite_zeigen(self._nr))
        for w in (self.zurueck, self.vor):
            w.setFixedWidth(40)
        kopf.addWidget(self.zurueck)
        kopf.addWidget(self.vor)
        kopf.addWidget(self.seiten_info, 1)
        kopf.addWidget(self.zoom)
        rl.addLayout(kopf)
        self.bild = QLabel("Noch keine Seite gewählt.")
        self.bild.setAlignment(Qt.AlignCenter)
        self.flaeche = flaeche = QScrollArea()
        flaeche.setWidget(self.bild)
        flaeche.setWidgetResizable(True)
        rl.addWidget(flaeche, 3)
        rl.addWidget(_klein("Erkannter Text – markieren und als Berechnung übernehmen:"))
        self.text = QTextEdit()
        self.text.setReadOnly(True)
        rl.addWidget(self.text, 1)
        self.uebernehmen = _knopf("Als Berechnung übernehmen …", self.formel_uebernehmen, True,
                                  "Formel aus der markierten Stelle; Buch, Kapitel und Seite werden Quelle")
        rl.addWidget(self.uebernehmen)
        rechts.setMinimumWidth(380)
        teiler.addWidget(rechts)
        teiler.setSizes([300, 400, 560])

    # ---------- Grundfunktionen
    def setze_projekt(self, projekt: Projekt | None):
        self.projekt = projekt

    def ordner(self) -> Path:
        return Path(self.einst.value("bibliothek_ordner", str(STANDARD_ORDNER)))

    def laden(self):
        if self.bib is None or self.bib.ordner != self.ordner():
            if self.bib:
                self.bib.schliessen()
            try:
                self.bib = Bibliothek(self.ordner())
            except (OSError, Exception) as exc:
                self.meldung.emit(f"Bibliothek nicht lesbar: {exc}", True)
                return
        self.ordner_info.setText(f"Ordner: {self.bib.ordner}")
        art = T.verfuegbar()
        self.ocr_info.setText(f"Texterkennung: {art} (Deutsch + Englisch)" if art
                              else "Texterkennung nicht installiert – Scans ohne Text sind nicht durchsuchbar. "
                                   + T.INSTALLIEREN)
        gewaehlt = self._buch.id if self._buch else None
        self.buecher.blockSignals(True)
        self.buecher.clear()
        self.nur_buch.clear()
        self.nur_buch.addItem("in allen Büchern", None)
        zeile = 0
        for i, b in enumerate(self.bib.buecher()):
            it = QListWidgetItem(f"{b.titel}\n{b.seiten} Seiten · {b.erkannt}")
            it.setData(Qt.UserRole, b.id)
            self.buecher.addItem(it)
            self.nur_buch.addItem(b.titel, b.id)
            if b.id == gewaehlt:
                zeile = i
        self.buecher.blockSignals(False)
        if self.buecher.count():
            self.buecher.setCurrentRow(zeile)
            self._buch_gewaehlt(zeile)
        else:
            self._buch = None
            self.buch_info.setText("Noch kein Buch. Ein gescanntes Buch als PDF hinzufügen.")
        self.uebernehmen.setEnabled(self._buch is not None)

    # ---------- Bücher
    def _pdf_waehlen(self):
        pfad, _ = QFileDialog.getOpenFileName(self, "Buch hinzufügen", str(Path.home()), "PDF (*.pdf)")
        if pfad:
            self.importieren(pfad)

    def _bilder_waehlen(self):
        pfade, _ = QFileDialog.getOpenFileNames(self, "Seiten-Scans als ein Buch", str(Path.home()),
                                                f"Bilder ({BILDER})")
        if pfade:
            self.importieren(pfade)

    def importieren(self, quelle, titel_: str = ""):
        if self.bib is None:
            self.laden()
        if self._thread:
            self.meldung.emit("Ein Import läuft noch – bitte warten.", True)
            return
        arbeit = _Import(self.bib.ordner, quelle, titel_)
        arbeit.fortschritt.connect(self.fortschritt.setText)
        arbeit.fertig.connect(self._import_fertig)
        if self.synchron:
            arbeit.laufen()
            return
        self._thread = QThread(self)
        self._arbeit = arbeit
        arbeit.moveToThread(self._thread)
        self._thread.started.connect(arbeit.laufen)
        arbeit.fertig.connect(self._thread.quit)
        self._thread.finished.connect(self._thread_ende)
        self.fortschritt.setText("Buch wird übernommen …")
        self._thread.start()

    def _thread_ende(self):
        self._thread.deleteLater()
        self._thread = None

    def _import_fertig(self, buch, fehler: str):
        if fehler:
            self.fortschritt.setText("")
            self.meldung.emit(fehler, True)
            return
        self._buch = buch
        self.laden()
        leer = self.bib.ohne_text(buch.id)
        text = f"„{buch.titel}“ übernommen: {buch.seiten} Seiten ({buch.erkannt})."
        if leer:
            text += f" {leer} Seiten ohne lesbaren Text."
        self.fortschritt.setText(text)
        self.meldung.emit(text, bool(leer))
        self.seite_zeigen(1)

    def _buch_gewaehlt(self, zeile: int):
        it = self.buecher.item(zeile) if zeile >= 0 else None
        if not it or not self.bib:
            return
        self._buch = self.bib.buch(it.data(Qt.UserRole))
        self.titel_feld.setText(self._buch.titel)
        self.titel_feld.setCursorPosition(0)
        self.versatz.setValue(self._buch.versatz)
        leer = self.bib.ohne_text(self._buch.id)
        self.buch_info.setText(f"{self._buch.kurz} · {self._buch.seiten} Seiten · Text: {self._buch.erkannt}"
                               + (f" · {leer} Seiten ohne Text" if leer else ""))
        self.dok.load(str(self.bib.pfad(self._buch)))
        self.uebernehmen.setEnabled(True)
        if not self.treffer.count():
            self.seite_zeigen(1)

    def _buch_aendern(self):
        if self._buch:
            self._buch = self.bib.aendern(self._buch.id, titel=self.titel_feld.text(), versatz=self.versatz.value())
            it = self.buecher.currentItem()
            if it:
                it.setText(f"{self._buch.titel}\n{self._buch.seiten} Seiten · {self._buch.erkannt}")
            self.seite_zeigen(self._nr)

    def _buch_loeschen(self):
        if not self._buch:
            return
        frage = QMessageBox.question(self, "Buch entfernen",
                                     f"„{self._buch.titel}“ aus der Bibliothek entfernen? "
                                     "Die Kopie im Bibliotheksordner wird gelöscht, das Original bleibt.")
        if frage != QMessageBox.Yes:
            return
        self.dok.close()
        self.bib.loeschen(self._buch.id)
        self._buch = None
        self.treffer.clear()
        self.laden()

    def _ordner_waehlen(self):
        pfad = QFileDialog.getExistingDirectory(self, "Ordner für die Bibliothek", str(self.ordner()))
        if pfad:
            self.einst.setValue("bibliothek_ordner", pfad)
            self._buch = None
            self.laden()

    # ---------- Suche und Fragen
    def _treffer_zeigen(self, liste: list[Treffer]):
        self.treffer.clear()
        for t in liste:
            it = QListWidgetItem()
            it.setData(Qt.UserRole, (t.buch.id, t.nr))
            label = QLabel(f"<b>{t.fundstelle}</b><br>{t.ausschnitt}")
            label.setWordWrap(True)
            label.setTextFormat(Qt.RichText)
            label.setContentsMargins(6, 4, 6, 4)
            it.setSizeHint(QSize(100, label.sizeHint().height() + 24))
            it.setToolTip(re.sub(r"</?b>", "", t.ausschnitt))
            self.treffer.addItem(it)
            self.treffer.setItemWidget(it, label)
        if liste:
            self.treffer.setCurrentRow(0)

    def suchen(self):
        if not self.bib:
            self.laden()
        text = self.suche.text().strip()
        if not text:
            return
        try:
            liste = self.bib.suchen(text, buch_id=self.nur_buch.currentData())
        except BibliothekFehler as exc:
            self.meldung.emit(str(exc), True)
            return
        self._suchwoerter = re.findall(r"[\wÄÖÜäöüß]+", text)
        self.antwort.setText((f"{len(liste)} Seiten gefunden." if len(liste) > 1 else "1 Seite gefunden.") if liste else "Nichts gefunden. Weniger oder "
                             "andere Wörter versuchen – oder „Fragen“, dann zählt jedes Wort.")
        self._treffer_zeigen(liste)

    def fragen(self):
        if not self.bib:
            self.laden()
        text = self.suche.text().strip()
        if not text:
            return
        woerter, liste = self.bib.frage(text)
        self._suchwoerter = woerter
        if not liste:
            self.antwort.setText("Keine passende Stelle in den Büchern gefunden.")
        else:
            orte = "; ".join(t.fundstelle for t in liste[:3])
            self.antwort.setText(f"<b>{HINWEIS_FRAGE}</b><br>Gesucht nach: {', '.join(woerter)}. "
                                 f"Am ehesten steht es hier: {orte}.")
        self._treffer_zeigen(liste)

    def _treffer_gewaehlt(self, zeile: int):
        it = self.treffer.item(zeile) if zeile >= 0 else None
        if not it:
            return
        buch_id, nr = it.data(Qt.UserRole)
        if not self._buch or self._buch.id != buch_id:
            for i in range(self.buecher.count()):
                if self.buecher.item(i).data(Qt.UserRole) == buch_id:
                    self.buecher.blockSignals(True)
                    self.buecher.setCurrentRow(i)
                    self.buecher.blockSignals(False)
                    self._buch_gewaehlt(i)
        self.seite_zeigen(nr)

    # ---------- Seite
    def seite_zeigen(self, nr: int):
        if not self._buch or not self.bib:
            return
        nr = max(1, min(nr, self._buch.seiten))
        self._nr = nr
        text, kapitel = self.bib.seitentext(self._buch.id, nr)
        s = self._buch.buchseite(nr)
        self.seiten_info.setText(f"S. {s}" + (f" (PDF {nr})" if s != nr else "") + f" von {self._buch.seiten}"
                                 + (f" · {kapitel}" if kapitel else ""))
        self.zurueck.setEnabled(nr > 1)
        self.vor.setEnabled(nr < self._buch.seiten)
        faktor = [0.75, 1.0, 1.5, 2.0][self.zoom.currentIndex()]
        if self.dok.pageCount() >= nr:
            gr = self.dok.pagePointSize(nr - 1)
            breite = int(max(300, self.flaeche.viewport().width() - 30) * faktor)
            bild = self.dok.render(nr - 1, QSize(breite, int(gr.height() / gr.width() * breite)))
            papier = QPixmap(bild.size())               # Buchseite immer auf weißem Papier, auch im Dunkelmodus
            papier.fill(QColor("white"))
            maler = QPainter(papier)
            maler.drawImage(0, 0, bild)
            maler.end()
            self.bild.setPixmap(papier)
        self.text.setPlainText(text or "(Auf dieser Seite wurde kein Text erkannt.)")
        self._hervorheben()

    def _hervorheben(self):
        auswahl = []
        fmt = QTextCharFormat()
        fmt.setBackground(QColor(230, 170, 30, 110))
        for w in self._suchwoerter:
            dok = self.text.document()
            c = dok.find(w)
            while not c.isNull():
                sel = QTextEdit.ExtraSelection()
                sel.cursor, sel.format = c, fmt
                auswahl.append(sel)
                c = dok.find(w, c)
        self.text.setExtraSelections(auswahl)

    def fundstelle(self) -> str:
        if not self._buch:
            return ""
        _, kapitel = self.bib.seitentext(self._buch.id, self._nr)
        teile = [self._buch.titel + (f" ({self._buch.autor})" if self._buch.autor else ""), kapitel,
                 f"S. {self._buch.buchseite(self._nr)}"]
        return ", ".join(t for t in teile if t)

    def formel_dialog(self) -> FormelDialog | None:
        if not self.projekt:
            self.meldung.emit("Zuerst ein Projekt öffnen – die Berechnung wird dort gespeichert.", True)
            return None
        markiert = self.text.textCursor().selectedText().replace(" ", "\n")
        return FormelDialog(self.projekt, formel_aus_text(markiert), self.fundstelle(), self)

    def formel_uebernehmen(self):
        dlg = self.formel_dialog()
        if dlg and dlg.exec() == QDialog.Accepted and dlg.gespeichert:
            b = dlg.gespeichert
            self.meldung.emit(f"{b.nr} „{b.titel}“ gespeichert – Quelle: {self.fundstelle()}.", False)
            self.gespeichert.emit()
