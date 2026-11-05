"""Seite „Abnahme Version 1“ (MS15): die 11 Abnahmekriterien mit Nachweisen, Lücken und Sprung zur Stelle."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QHBoxLayout, QInputDialog, QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget,
)

from .. import abnahme as A
from ..modell import Projekt
from .betrieb_seiten import _knopf
from .seiten import karte, scrollbar, titel

ZEICHEN = {A.ERFUELLT: "●  erfüllt", A.OFFEN: "●  offen", A.BESTAETIGEN: "●  bestätigen"}
FARBE = {A.ERFUELLT: "#2E9F43", A.OFFEN: "#D63A33", A.BESTAETIGEN: "#D9A21B"}


def _klein(text: str = "") -> QLabel:
    l_ = QLabel(text)
    l_.setObjectName("Klein")
    l_.setWordWrap(True)
    return l_


class AbnahmeSeite(QWidget):
    meldung = Signal(str, bool)
    gespeichert = Signal()
    gehe_zu = Signal(str)
    exportieren = Signal()

    def __init__(self, buecher_zaehlen: Callable[[], int] | None = None):
        super().__init__()
        self.projekt: Projekt | None = None
        self.buecher_zaehlen = buecher_zaehlen or (lambda: 0)
        self.kriterien: list[A.Kriterium] = []
        self.karten: dict[int, QFrame] = {}

        inhalt = QWidget()
        self.lay = QVBoxLayout(inhalt)
        self.lay.setContentsMargins(32, 24, 32, 24)
        self.lay.addWidget(titel("Abnahme Version 1", "Die App ist fertig, wenn die Windkraftanlage vollständig "
                                                      "in ihr entwickelt ist – 11 Kriterien aus dem Lastenheft."))
        kopf, kl = karte()
        zeile = QHBoxLayout()
        self.stand = QLabel("")
        self.stand.setObjectName("Abschnitt")
        zeile.addWidget(self.stand, 1)
        zeile.addWidget(_knopf("Neu prüfen", self.laden))
        zeile.addWidget(_knopf("Abnahmeprotokoll (PDF) …", lambda: self.pdf(), True))
        zeile.addWidget(_knopf("Projekt exportieren …", self.exportieren.emit,
                               tipp="Ganzes Projekt als ZIP-Archiv, ohne Buchscans"))
        kl.addLayout(zeile)
        self.balken = QProgressBar()
        self.balken.setRange(0, 11)
        self.balken.setTextVisible(False)
        self.balken.setFixedHeight(10)
        kl.addWidget(self.balken)
        kl.addWidget(_klein("Grün: erfüllt · Rot: es fehlt noch etwas (mit Sprung zur Stelle) · Gelb: nur du kannst "
                            "es bestätigen. Erzeugte PDFs merkt sich das Projekt automatisch."))
        self.lay.addWidget(kopf)
        self.liste = QVBoxLayout()
        self.liste.setSpacing(10)
        self.lay.addLayout(self.liste)
        self.lay.addStretch(1)
        aussen = QVBoxLayout(self)
        aussen.setContentsMargins(0, 0, 0, 0)
        flaeche = scrollbar(inhalt)
        flaeche.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        aussen.addWidget(flaeche)

    def setze_projekt(self, projekt: Projekt | None):
        self.projekt = projekt

    def laden(self):
        if not self.projekt:
            return
        self.kriterien = A.pruefen(self.projekt, self.buecher_zaehlen())
        while self.liste.count():
            w = self.liste.takeAt(0).widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        self.karten = {}
        for k in self.kriterien:
            box = self._karte(k)
            self.karten[k.nr] = box
            self.liste.addWidget(box)
        erfuellt, gesamt = A.zusammenfassung(self.kriterien)
        self.balken.setValue(erfuellt)
        self.stand.setText(f"{erfuellt} von {gesamt} Kriterien erfüllt"
                           + (" – Version 1 ist abgenommen." if erfuellt == gesamt else ""))

    def _karte(self, k: A.Kriterium) -> QFrame:
        box, bl = karte()
        kopf = QHBoxLayout()
        name = QLabel(f"{k.nr}.  {k.titel}")
        name.setObjectName("Abschnitt")
        name.setWordWrap(True)
        kopf.addWidget(name, 1)
        ampel = QLabel(ZEICHEN[k.stand])
        ampel.setStyleSheet(f"color: {FARBE[k.stand]}; font-weight: 600;")
        kopf.addWidget(ampel)
        bl.addLayout(kopf)
        if k.nachweise:
            bl.addWidget(_klein("<br>".join(f"✓ {n}" for n in k.nachweise)))
        if k.fehlt:
            l_ = _klein("<br>".join(f"• {f}" for f in k.fehlt[:12])
                        + (f"<br>… und {len(k.fehlt) - 12} weitere" if len(k.fehlt) > 12 else ""))
            l_.setStyleSheet(f"color: {FARBE[A.OFFEN]};")
            bl.addWidget(l_)
        knoepfe = QHBoxLayout()
        knoepfe.addStretch(1)
        if k.von_hand:
            if k.bestaetigt:
                knoepfe.addWidget(_knopf("Bestätigung zurücknehmen", lambda n=k.nr: self.bestaetigen(n, False)))
            else:
                b = _knopf("Bestätigen …", lambda n=k.nr: self.bestaetigen(n, True), not k.fehlt)
                b.setEnabled(not k.fehlt)
                knoepfe.addWidget(b)
        if k.fehlt or k.von_hand:
            knoepfe.addWidget(_knopf("Öffnen", lambda s=k.seite: self.gehe_zu.emit(s),
                                     tipp="Zur Seite, auf der das erledigt wird"))
        bl.addLayout(knoepfe)
        return box

    def bestaetigen(self, nr: int, ja: bool, notiz: str | None = None):
        if not self.projekt:
            return
        if ja and notiz is None:
            frage = {10: "Welche Fachfrage hast du gestellt, und welche Seite wurde gefunden?",
                     11: "Kurze Notiz zum Probelauf (macOS-Version, Datum, Auffälligkeiten):"}.get(nr, "Notiz:")
            notiz, ok = QInputDialog.getText(self, f"Kriterium {nr} bestätigen", frage)
            if not ok:
                return
        self.projekt.abnahme_bestaetigen(nr, ja, notiz or "")
        self.meldung.emit(f"Kriterium {nr} " + ("bestätigt." if ja else "zurückgenommen."), False)
        self.gespeichert.emit()
        self.laden()

    def pdf(self, ziel: str | None = None) -> Path | None:
        if not self.projekt:
            return None
        if ziel is None:
            ziel, _ = QFileDialog.getSaveFileName(self, "Abnahmeprotokoll speichern",
                                                  str(self.projekt.pfad.parent / "Abnahme_Version_1.pdf"),
                                                  "PDF (*.pdf)")
            if not ziel:
                return None
        from ..pdf import abnahme_v1_erstellen
        self.laden()
        pfad = abnahme_v1_erstellen(self.kriterien, ziel, self.projekt.name)
        self.projekt.dokument_merken("abnahme_v1", pfad)
        self.meldung.emit(f"Abnahmeprotokoll gespeichert: {Path(pfad).name}", False)
        return Path(pfad)
