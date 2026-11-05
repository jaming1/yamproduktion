"""Seite „Kollision & Schwerpunkt“: gespeicherte Baugruppe auf Überschneidungen und zu knappes Spiel prüfen,
Masse, Schwerpunkt und Massenträgheit anzeigen (Lastenheft K4).

Die Rechnung steckt in `cad/kollision.py`; hier nur Auswahl, Anzeige und das Festhalten gewollter Überdeckungen
(„Ausnahmen“ mit Begründung, je Paar von Einbauten).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PySide6.QtCore import QLocale, QPointF, Qt, Signal
from PySide6.QtGui import QColor, QKeySequence, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDoubleSpinBox, QFileDialog, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..berechnungen.basis import formatiere
from ..cad import kollision as K
from ..modell import NEU_PRUEFEN, Projekt
from ..montage import szene as SZ
from . import thema
from .ansicht3d import ANSICHTEN, Ansicht3D, _drehung
from .seiten import karte, scrollbar, titel

LEER_TEXT = "Noch keine Baugruppe – zuerst unter „Baugruppen“ eine anlegen und speichern."
ERKLAERUNG = (
    "Befunde sind Hinweise, keine Urteile. <b>Durchdringung</b>: zwei Teile nehmen denselben Raum ein. "
    "<b>Spiel zu klein</b>: die Teile sind sich näher als der Mindestabstand. <b>Berührung</b> ist oft gewollt, "
    "z. B. ein Lager auf der Welle. Vereinfachte Schrauben ohne Bohrung im Gegenstück erscheinen als Durchdringung "
    "– solche gewollten Fälle mit „Als gewollt vermerken …“ und einer kurzen Begründung festhalten; sie zählen "
    "dann nicht mehr als Fehler. Ein Vermerk gilt für alle Exemplare eines Lochkreises.")
SPALTEN = ["Art", "Teil A", "Teil B", "Überschneidung\nmm³", "Abstand\nmm", "Gewollt?"]
MASSE_SPALTEN = ["Einbau", "Benennung", "Menge", "Masse kg", "Anteil"]


def _mm(wert: float) -> str:
    """Länge in mm lesbar: Rundungsreste (1e-7) als 0 statt „< 0,0001“."""
    w = round(float(wert), 2)
    return formatiere(0.0 if w == 0 else w)


class SchwerpunktAnsicht(Ansicht3D):
    """3D-Ansicht mit eingezeichnetem Schwerpunkt (Kreis mit Kreuz und „S“)."""

    def __init__(self):
        super().__init__()
        self.schwerpunkt: np.ndarray | None = None
        self.setAccessibleName("3D-Ansicht der Baugruppe mit Schwerpunkt")

    def setze_schwerpunkt(self, punkt) -> None:
        self.schwerpunkt = None if punkt is None else np.asarray(punkt, dtype=float)
        self.update()

    def schwerpunkt_bild(self) -> QPointF | None:
        """Lage des Schwerpunkts auf dem Bildschirm (gleiche Projektion wie Ansicht3D.paintEvent)."""
        if self.netz is None or self.schwerpunkt is None:
            return None
        q = (self.schwerpunkt - self._mitte) @ _drehung(self.azimut, self.elevation).T
        massstab = self._passend * self.zoom
        return QPointF(self.width() / 2 + self.verschiebung[0] + q[0] * massstab,
                       self.height() / 2 + self.verschiebung[1] - q[1] * massstab)

    def paintEvent(self, ev):
        super().paintEvent(ev)
        punkt = self.schwerpunkt_bild()
        if punkt is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = 11.0
        dunkel = self.palette().window().color().lightness() < 128
        rand = QColor(255, 255, 255) if dunkel else QColor(20, 24, 30)
        farbe = QColor(214, 40, 120)                     # magenta: hebt sich von Blau/Grau und Orange ab
        p.setPen(QPen(rand, 5))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(punkt, r, r)
        p.setPen(QPen(farbe, 2.5))
        p.drawEllipse(punkt, r, r)
        for dx, dy in ((r + 6, 0), (0, r + 6)):
            p.drawLine(QPointF(punkt.x() - dx, punkt.y() - dy), QPointF(punkt.x() + dx, punkt.y() + dy))
        schrift = p.font()
        schrift.setPixelSize(18)
        schrift.setBold(True)
        p.setFont(schrift)
        text_pos = QPointF(punkt.x() + r + 6, punkt.y() - r - 4)
        p.setPen(QPen(rand, 1))
        for ox, oy in ((-1, 0), (1, 0), (0, -1), (0, 1)):      # Umriss, damit „S“ auf jedem Grund lesbar ist
            p.drawText(text_pos + QPointF(ox, oy), "S")
        p.setPen(farbe)
        p.drawText(text_pos, "S")
        p.end()


class KollisionSeite(QWidget):
    meldung = Signal(str, bool)

    def __init__(self):
        super().__init__()
        self.projekt: Projekt | None = None
        self.baugruppe_id: int | None = None
        self.ergebnis = None
        self.pruefung: K.Pruefung | None = None
        self.massen: K.Massen | None = None
        self.szene: SZ.Szene | None = None
        self._fuellt = False

        inhalt = QWidget()
        lay = QVBoxLayout(inhalt)
        lay.setContentsMargins(32, 24, 32, 24)
        lay.setSpacing(14)
        lay.addWidget(titel("Kollision & Schwerpunkt",
                            "Prüft eine gespeicherte Baugruppe: Wo überschneiden sich Teile, wo ist zu wenig Platz? "
                            "Dazu Masse, Schwerpunkt und Massenträgheit."))

        # ---- Leiste: Auswahl, Mindestabstand, Prüfen
        leiste, ll = karte()
        zeile = QHBoxLayout()
        zeile.setSpacing(12)
        zeile.addWidget(QLabel("Baugruppe"))
        self.auswahl = QComboBox()
        self.auswahl.setAccessibleName("Gespeicherte Baugruppe")
        self.auswahl.setMinimumWidth(320)
        self.auswahl.activated.connect(lambda i: self.waehle(self.auswahl.itemData(i)))
        zeile.addWidget(self.auswahl, 1)
        zeile.addSpacing(12)
        zeile.addWidget(QLabel("Mindestabstand (mm)"))
        self.mindestabstand = QDoubleSpinBox()
        self.mindestabstand.setLocale(QLocale(QLocale.German, QLocale.Germany))
        self.mindestabstand.setRange(0.0, 1000.0)
        self.mindestabstand.setDecimals(2)
        self.mindestabstand.setSingleStep(0.5)
        self.mindestabstand.setMinimumWidth(110)
        self.mindestabstand.setAccessibleName("Mindestabstand in Millimetern")
        self.mindestabstand.setToolTip("Teile, die sich näher kommen als dieser Abstand, werden als „Spiel zu klein“ "
                                       "gemeldet. 0 = nur Überschneidungen und Berührungen melden. "
                                       "Wird je Baugruppe gemerkt.")
        self.mindestabstand.editingFinished.connect(self._abstand_merken)
        zeile.addWidget(self.mindestabstand)
        zeile.addSpacing(12)
        self.pruefen_knopf = QPushButton("Prüfen")
        self.pruefen_knopf.setObjectName("Haupt")
        self.pruefen_knopf.setShortcut(QKeySequence(Qt.Key_F5))
        self.pruefen_knopf.setToolTip("Baugruppe neu aufbauen und alle Teilepaare prüfen (F5)")
        self.pruefen_knopf.clicked.connect(lambda: self.pruefen())
        zeile.addWidget(self.pruefen_knopf)
        ll.addLayout(zeile)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setAccessibleName("Ergebnis der Prüfung")
        ll.addWidget(self.status)
        lay.addWidget(leiste)

        # ---- Leerer Zustand
        self.leer, el = karte()
        h = QLabel(LEER_TEXT)
        h.setWordWrap(True)
        h.setObjectName("Abschnitt")
        el.addWidget(h)
        h = QLabel("Hier wird dann geprüft, ob sich Teile überschneiden oder zu nah kommen, und wo der Schwerpunkt "
                   "der Baugruppe liegt.")
        h.setWordWrap(True)
        h.setObjectName("Untertitel")
        el.addWidget(h)
        lay.addWidget(self.leer)

        # ---- Hauptbereich: oben Befunde und 3D, unten Masse & Schwerpunkt
        self.haupt = QWidget()
        hv = QVBoxLayout(self.haupt)
        hv.setContentsMargins(0, 0, 0, 0)
        hv.setSpacing(16)
        hl = QHBoxLayout()
        hl.setSpacing(16)

        befunde, bl = karte()
        k = QLabel("Befunde")
        k.setObjectName("Abschnitt")
        bl.addWidget(k)
        self.tabelle = QTableWidget(0, len(SPALTEN))
        self.tabelle.setHorizontalHeaderLabels(SPALTEN)
        self.tabelle.setAccessibleName("Befunde der Kollisionsprüfung")
        self.tabelle.verticalHeader().hide()
        self.tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabelle.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabelle.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tabelle.setWordWrap(False)
        self.tabelle.setTextElideMode(Qt.ElideRight)
        kopf = self.tabelle.horizontalHeader()
        kopf.setSectionResizeMode(QHeaderView.ResizeToContents)
        kopf.setStretchLastSection(True)
        kopf.setMinimumSectionSize(60)
        self.tabelle.horizontalHeaderItem(3).setToolTip("Rauminhalt, den sich die zwei Teile teilen (nur bei "
                                                        "Durchdringung)")
        self.tabelle.horizontalHeaderItem(4).setToolTip("Kürzester Abstand zwischen den zwei Teilen")
        self.tabelle.horizontalHeaderItem(5).setToolTip("„offen“ = zählt als Fehler; ✓ = als gewollt vermerkt, "
                                                        "mit Begründung")
        self.tabelle.setMinimumHeight(340)
        self.tabelle.itemSelectionChanged.connect(self._befund_gewaehlt)
        bl.addWidget(self.tabelle, 1)
        self.detail = QLabel()
        self.detail.setWordWrap(True)
        self.detail.setAccessibleName("Gewählter Befund")
        bl.addWidget(self.detail)
        knoepfe = QHBoxLayout()
        self.ausnahme_knopf = QPushButton("Als gewollt vermerken …")
        self.ausnahme_knopf.setToolTip("Diese Überschneidung ist beabsichtigt (z. B. Presspassung, vereinfachte "
                                       "Schraube) – mit Begründung festhalten")
        self.ausnahme_knopf.clicked.connect(lambda: self.ausnahme_setzen())
        knoepfe.addWidget(self.ausnahme_knopf)
        self.aufheben_knopf = QPushButton("Ausnahme aufheben")
        self.aufheben_knopf.setToolTip("Vermerk löschen – der Befund zählt wieder als Fehler")
        self.aufheben_knopf.clicked.connect(lambda: self.ausnahme_aufheben())
        knoepfe.addWidget(self.aufheben_knopf)
        knoepfe.addStretch()
        self.bericht_knopf = QPushButton("Bericht (PDF) …")
        self.bericht_knopf.setToolTip("Befunde, Ausnahmen, Masse und Schwerpunkt als Prüfbericht speichern")
        self.bericht_knopf.clicked.connect(lambda: self.bericht_speichern())
        knoepfe.addWidget(self.bericht_knopf)
        bl.addLayout(knoepfe)
        erkl = QLabel(ERKLAERUNG)
        erkl.setObjectName("Klein")
        erkl.setWordWrap(True)
        bl.addWidget(erkl)
        hl.addWidget(befunde, 5)

        bild, il = karte()
        leiste3d = QHBoxLayout()
        for name in ANSICHTEN:
            b = QPushButton(name)
            b.setObjectName("Werkzeug")
            b.clicked.connect(lambda _=False, n=name: self.ansicht.ansicht(n))
            leiste3d.addWidget(b)
        leiste3d.addStretch()
        il.addLayout(leiste3d)
        self.ansicht = SchwerpunktAnsicht()
        self.ansicht.setMinimumSize(320, 300)
        self.ansicht.hinweis = "Baugruppe wählen und „Prüfen“ drücken."
        il.addWidget(self.ansicht, 1)
        self.legende = QLabel("Orange: Teile mit offenem Befund – ein Klick auf einen Befund zeigt nur dessen zwei "
                              "Teile. S: Schwerpunkt. Drehen mit der Maus, Doppelklick zeigt alles.")
        self.legende.setObjectName("Klein")
        self.legende.setWordWrap(True)
        il.addWidget(self.legende)
        hl.addWidget(bild, 3)
        hv.addLayout(hl, 1)

        masse, ml = karte()
        k = QLabel("Masse & Schwerpunkt")
        k.setObjectName("Abschnitt")
        ml.addWidget(k)
        ml_zeile = QHBoxLayout()
        ml_zeile.setSpacing(24)
        links = QVBoxLayout()
        self.kennwerte = QLabel()
        self.kennwerte.setWordWrap(True)
        self.kennwerte.setTextFormat(Qt.RichText)
        self.kennwerte.setAccessibleName("Masse, Schwerpunkt und Trägheitsmomente")
        self.kennwerte.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        links.addWidget(self.kennwerte)
        self.masse_hinweis = QLabel()
        self.masse_hinweis.setObjectName("Klein")
        self.masse_hinweis.setWordWrap(True)
        links.addWidget(self.masse_hinweis)
        links.addStretch()
        ml_zeile.addLayout(links, 2)
        self.masse_tabelle = QTableWidget(0, len(MASSE_SPALTEN))
        self.masse_tabelle.setHorizontalHeaderLabels(MASSE_SPALTEN)
        self.masse_tabelle.setAccessibleName("Masse je Einbau")
        self.masse_tabelle.verticalHeader().hide()
        self.masse_tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.masse_tabelle.setSelectionMode(QAbstractItemView.NoSelection)
        self.masse_tabelle.setWordWrap(False)
        kopf = self.masse_tabelle.horizontalHeader()
        kopf.setSectionResizeMode(QHeaderView.ResizeToContents)
        kopf.setSectionResizeMode(1, QHeaderView.Stretch)
        self.masse_tabelle.setMinimumHeight(220)
        ml_zeile.addWidget(self.masse_tabelle, 3)
        ml.addLayout(ml_zeile)
        hv.addWidget(masse)
        lay.addWidget(self.haupt, 1)
        lay.addStretch(0)            # nimmt nur Platz, wenn der Hauptbereich ausgeblendet ist (leerer Zustand)

        aussen = QVBoxLayout(self)
        aussen.setContentsMargins(0, 0, 0, 0)
        aussen.addWidget(scrollbar(inhalt))
        self._anzeigen()

    # ================================================================ Projekt und Auswahl
    def setze_projekt(self, projekt: Projekt | None):
        self.projekt = projekt
        self.baugruppe_id = None
        self._zuruecksetzen()
        self.laden()

    def laden(self):
        """Liste der Baugruppen neu füllen; eine schon geprüfte Baugruppe wird mit dem aktuellen Stand neu geprüft."""
        gruppen = []
        if self.projekt:
            try:
                gruppen = self.projekt.baugruppen()
            except Exception as exc:          # kaputte Datei o. Ä. – Seite bleibt bedienbar
                self.meldung.emit(f"Baugruppen konnten nicht gelesen werden: {exc}", True)
        self._fuellt = True
        self.auswahl.clear()
        for g in gruppen:
            self.auswahl.addItem(f"{g['nr']} {g['name']}" + ("  ⚠ neu prüfen" if g["status"] == NEU_PRUEFEN else ""),
                                 g["id"])
        self._fuellt = False
        ids = [g["id"] for g in gruppen]
        geprueft = self.pruefung is not None
        if self.baugruppe_id not in ids:
            self.baugruppe_id = None
            self._zuruecksetzen()
            geprueft = False
        ziel = self.baugruppe_id if self.baugruppe_id is not None else (ids[0] if ids else None)
        if ziel is not None:
            self.waehle(ziel, pruefen=geprueft)
        else:
            self._anzeigen()

    def waehle(self, baugruppe_id: int | None, pruefen: bool = False):
        """Baugruppe auswählen (Mindestabstand wird geladen). Mit `pruefen` gleich prüfen."""
        if baugruppe_id is None or not self.projekt:
            return
        i = self.auswahl.findData(baugruppe_id)
        if i < 0:
            self.meldung.emit("Diese Baugruppe gibt es nicht mehr.", True)
            return
        if baugruppe_id != self.baugruppe_id:
            self._zuruecksetzen()
        self.baugruppe_id = baugruppe_id
        self.auswahl.setCurrentIndex(i)
        self.mindestabstand.blockSignals(True)
        self.mindestabstand.setValue(self.projekt.kollision_mindestabstand(baugruppe_id))
        self.mindestabstand.blockSignals(False)
        if pruefen:
            self.pruefen()
        else:
            self._anzeigen()

    def _abstand_merken(self):
        if self.projekt and self.baugruppe_id is not None:
            wert = self.mindestabstand.value()
            if abs(wert - self.projekt.kollision_mindestabstand(self.baugruppe_id)) > 1e-9:
                self.projekt.kollision_mindestabstand_setzen(self.baugruppe_id, wert)
                if self.pruefung is not None:
                    self._status("Mindestabstand geändert – mit „Prüfen“ (F5) neu prüfen.", fehler=None)

    def _zuruecksetzen(self):
        self.ergebnis = self.pruefung = self.massen = self.szene = None
        self.ansicht.setze_netz(None)
        self.ansicht.setze_schwerpunkt(None)

    # ================================================================ Prüfen
    def pruefen(self) -> K.Pruefung | None:
        if not self.projekt or self.baugruppe_id is None:
            self.meldung.emit(LEER_TEXT, True)
            return None
        self._abstand_merken()
        try:
            erg, pr, m = self.projekt.kollision_pruefen(self.baugruppe_id, self.mindestabstand.value())
        except Exception as exc:                      # Geometrie- oder Projektfehler: verständlich melden
            self._zuruecksetzen()
            self._anzeigen()
            text = f"Die Baugruppe ließ sich nicht prüfen: {exc}"
            self._status(text, fehler=True)
            self.meldung.emit(text, True)
            return None
        self.ergebnis, self.pruefung, self.massen = erg, pr, m
        try:
            self.szene = SZ.aufbauen(erg) if erg.exemplare else None
        except Exception:                             # Anzeige ist Beiwerk – Prüfung bleibt gültig
            self.szene = None
        if self.szene is not None:
            self.ansicht.setze_netz(self.szene.netz(), anpassen=True, gruppen=self.szene.gruppen(pr.betroffene()))
            self.ansicht.setze_schwerpunkt(m.schwerpunkt if m.masse else None)
        else:
            self.ansicht.hinweis = "Keine Teile zum Anzeigen."
            self.ansicht.setze_netz(None)
            self.ansicht.setze_schwerpunkt(None)
        self._anzeigen()
        self.meldung.emit(f"Prüfung fertig: {pr.zusammenfassung()}", not pr.ok)
        return pr

    def bericht_speichern(self, ziel: str | None = None) -> Path | None:
        """Prüfbericht als PDF (Befunde mit Begründungen, Masse, Schwerpunkt, Trägheit)."""
        if self.pruefung is None or self.massen is None or self.baugruppe_id is None:
            self.meldung.emit("Zuerst prüfen (F5), dann den Bericht speichern.", True)
            return None
        g = self.projekt.baugruppe(self.baugruppe_id)
        if not ziel:
            ziel, _ = QFileDialog.getSaveFileName(self, "Prüfbericht speichern",
                                                  str(self.projekt.pfad.parent / f"{g['name']}_Kollision.pdf"),
                                                  "PDF (*.pdf)")
        if not ziel:
            return None
        try:
            from ..pdf import kollisionsbericht_erstellen
            pfad = kollisionsbericht_erstellen(self.pruefung, self.massen, ziel, g["name"], g["nr"], self.projekt.name)
        except OSError as exc:
            self.meldung.emit(f"Speichern fehlgeschlagen: {exc}", True)
            return None
        self.projekt.dokument_merken("kollisionsbericht", str(pfad), g["name"])
        self.meldung.emit(f"Prüfbericht gespeichert: {pfad.name}", False)
        return pfad

    # ================================================================ Ausnahmen
    def _befund(self, zeile: int | None) -> K.Befund | None:
        if self.pruefung is None:
            return None
        zeile = self.tabelle.currentRow() if zeile is None else zeile
        if not 0 <= zeile < len(self.pruefung.befunde):
            self.meldung.emit("Bitte zuerst einen Befund in der Tabelle anklicken.", True)
            return None
        return self.pruefung.befunde[zeile]

    def ausnahme_setzen(self, zeile: int | None = None, begruendung: str | None = None) -> bool:
        """Befund als gewollt vermerken. Ohne `begruendung` wird danach gefragt."""
        b = self._befund(zeile)
        if b is None:
            return False
        if begruendung is None:
            text, ok = QInputDialog.getText(
                self, "Als gewollt vermerken",
                f"Warum ist die {b.art} von\n{b.name_a} und {b.name_b}\nin Ordnung?\n"
                "(z. B. „Presspassung“ oder „Schraube vereinfacht, Bohrung fehlt“)", text=b.ausnahme)
            if not ok:
                return False
            begruendung = text
        if not begruendung.strip():
            self.meldung.emit("Bitte eine kurze Begründung angeben – sonst wird nichts vermerkt.", True)
            return False
        return self._ausnahme_speichern(b, begruendung.strip(), zeile)

    def ausnahme_aufheben(self, zeile: int | None = None) -> bool:
        b = self._befund(zeile)
        if b is None:
            return False
        if not b.ausnahme:
            self.meldung.emit("Dieser Befund ist nicht als gewollt vermerkt.", False)
            return False
        return self._ausnahme_speichern(b, "", zeile)

    def _ausnahme_speichern(self, b: K.Befund, begruendung: str, zeile: int | None) -> bool:
        zeile = self.tabelle.currentRow() if zeile is None else zeile
        try:
            self.projekt.kollision_ausnahme_setzen(self.baugruppe_id, b.einbau_a, b.einbau_b, begruendung)
            ausnahmen = self.projekt.kollision_ausnahmen(self.baugruppe_id)
        except Exception as exc:
            self.meldung.emit(f"Vermerk nicht gespeichert: {exc}", True)
            return False
        # Gilt für das ganze Paar von Einbauten (z. B. alle Schrauben eines Lochkreises); Reihenfolge der Tabelle
        # bleibt, damit die eben bearbeitete Zeile nicht wegspringt. Beim nächsten „Prüfen“ wird neu sortiert.
        for x in self.pruefung.befunde:
            x.ausnahme = ausnahmen.get(x.paar, "")
        self._anzeigen()
        if 0 <= zeile < self.tabelle.rowCount():
            self.tabelle.selectRow(zeile)
        self.meldung.emit((f"Als gewollt vermerkt: {b.name_a} / {b.name_b}." if begruendung else
                           f"Ausnahme aufgehoben: {b.name_a} / {b.name_b}."), False)
        return True

    # ================================================================ Anzeige
    def _farben(self) -> dict:
        dunkel = self.palette().window().color().lightness() < 128
        return thema.FARBEN["dunkel" if dunkel else "hell"]

    def _status(self, text: str, fehler: bool | None):
        self.status.setText(text)
        self.status.setObjectName({True: "Fehler", False: "Ok", None: "Untertitel"}[fehler])
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        self.status.setVisible(bool(text))

    def _anzeigen(self):
        hat_gruppen = self.auswahl.count() > 0
        self.leer.setVisible(not hat_gruppen)
        self.haupt.setVisible(hat_gruppen)
        self.auswahl.setEnabled(hat_gruppen)
        self.mindestabstand.setEnabled(hat_gruppen)
        self.pruefen_knopf.setEnabled(hat_gruppen)
        self.bericht_knopf.setEnabled(self.pruefung is not None and self.massen is not None)
        pr = self.pruefung
        if not hat_gruppen:
            self._status("", None)
        elif pr is None:
            self._status("Noch nicht geprüft – auf „Prüfen“ drücken (Taste F5).", None)
        else:
            text = pr.zusammenfassung()
            if self.ergebnis is not None and self.ergebnis.fehler:
                text += f" – Achtung, die Baugruppe hat Fehler: {self.ergebnis.fehler}"
            if pr.ok:
                text = "✓ " + text
            else:
                n = pr.fehler_anzahl
                text = f"⚠ {n} offene{'r' if n == 1 else ''} Befund{'' if n == 1 else 'e'}: " + text \
                    if not pr.fehler else "⚠ " + text
            text += f"  ({pr.paare_gesamt} Teilepaare, {pr.paare_geprueft} davon genau geprüft)"
            self._status(text, fehler=not pr.ok or bool(self.ergebnis and self.ergebnis.fehler))
        self._befunde_fuellen()
        self._massen_fuellen()

    @staticmethod
    def _hoehe_passend(tabelle: QTableWidget, max_zeilen: int):
        """Tabelle so hoch, dass bis zu `max_zeilen` Zeilen ohne Rollbalken sichtbar sind."""
        zeile = tabelle.verticalHeader().defaultSectionSize()
        n = min(max(tabelle.rowCount(), 3), max_zeilen)
        tabelle.setFixedHeight(tabelle.horizontalHeader().sizeHint().height() + n * zeile + 2 * tabelle.frameWidth()
                                 + 2)

    def _befunde_fuellen(self):
        pr = self.pruefung
        befunde = pr.befunde if pr else []
        f = self._farben()
        fehler_farbe, grau = QColor(f["fehler"]), QColor(f["text2"])
        self._fuellt = True
        self.tabelle.clearSelection()
        self.tabelle.setRowCount(len(befunde))
        for i, b in enumerate(befunde):
            werte = (b.art, b.name_a, b.name_b,
                     formatiere(b.volumen) if b.art == K.DURCHDRINGUNG else "–",
                     _mm(b.abstand) if b.art == K.SPIEL else ("0" if b.art == K.BERUEHRUNG else "–"),
                     f"✓ {b.ausnahme}" if b.ausnahme else ("offen" if b.ist_fehler else "–"))
            for j, wert in enumerate(werte):
                item = QTableWidgetItem(str(wert))
                if j in (3, 4):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if b.ist_fehler and j in (0, 5):
                    item.setForeground(fehler_farbe)
                    schrift = item.font()
                    schrift.setBold(True)
                    item.setFont(schrift)
                elif b.ausnahme or b.art == K.BERUEHRUNG:
                    item.setForeground(grau)
                if j == 5 and b.ausnahme:
                    item.setToolTip(b.ausnahme)
                self.tabelle.setItem(i, j, item)
        self._fuellt = False
        self.ausnahme_knopf.setEnabled(bool(befunde))
        self.aufheben_knopf.setEnabled(any(b.ausnahme for b in befunde))
        self._befund_gewaehlt()

    def _befund_gewaehlt(self):
        """Klick auf einen Befund: nur dessen zwei Teile orange und Einzelheiten darunter; sonst alle Teile mit
        offenem Befund."""
        if self._fuellt:
            return
        b = None
        if self.pruefung is not None:
            zeilen = self.tabelle.selectionModel().selectedRows()
            if zeilen and zeilen[0].row() < len(self.pruefung.befunde):
                b = self.pruefung.befunde[zeilen[0].row()]
        if b is None:
            self.detail.setText("Einen Befund anklicken, um ihn in der 3D-Ansicht zu sehen." if self.pruefung and
                                self.pruefung.befunde else "")
        else:
            x, y, z = b.ort
            mass = (f"{formatiere(b.volumen)} mm³ Überschneidung" if b.art == K.DURCHDRINGUNG else
                    f"{_mm(b.abstand)} mm Abstand" if b.art == K.SPIEL else "liegen aneinander")
            ort = f"x\u00a0{_mm(x)} · y\u00a0{_mm(y)} · z\u00a0{_mm(z)}\u00a0mm"
            text = f"<b>{b.art}</b>: {b.name_a} und {b.name_b} – {mass}, bei {ort}."
            if b.ausnahme:
                text += f"<br>Als gewollt vermerkt: „{b.ausnahme}“"
            self.detail.setText(text)
        self.detail.setVisible(bool(self.detail.text()))
        if self.szene is None or self.pruefung is None:
            return
        markiert = [b.a, b.b] if b is not None else self.pruefung.betroffene()
        self.ansicht.gruppen = self.szene.gruppen(markiert)
        self.ansicht.update()

    def markierte(self) -> list[int]:
        """Exemplare, die gerade orange hervorgehoben sind (für Tests und Prüfung der Anzeige)."""
        if self.szene is None or self.ansicht.gruppen is None:
            return []
        return sorted({int(e) for e, g in zip(self.szene.ex_tri, self.ansicht.gruppen) if g == SZ.GRUPPE_NEU})

    def _massen_fuellen(self):
        m = self.massen
        if m is None:
            self.kennwerte.setText("Nach dem Prüfen stehen hier Gesamtmasse, Schwerpunkt und Trägheitsmomente.")
            self.masse_tabelle.setRowCount(0)
            self.masse_hinweis.setText("")
            return
        if m.masse:
            sx, sy, sz = m.schwerpunkt
            j = [formatiere(w * 1e-6) for w in m.haupt]
            self.kennwerte.setText(
                f"<p style='margin:0'><span style='font-size:20px; font-weight:600'>Gesamtmasse "
                f"{formatiere(m.masse)} kg</span></p>"
                f"<p style='margin:6px 0 0 0'>Schwerpunkt S: x {_mm(sx)} · y {_mm(sy)} · z {_mm(sz)} mm</p>"
                f"<p style='margin:6px 0 0 0'>Hauptträgheitsmomente: {j[0]} · {j[1]} · {j[2]} kg·m²</p>"
                f"<p style='margin:4px 0 0 0; font-size:14px; color:{self._farben()['text2']}'>"
                "Trägheitsmoment = wie schwer sich die Baugruppe in Drehung versetzen lässt – je Hauptachse "
                "durch den Schwerpunkt S, kleinster Wert zuerst (bei Wellen meist die Drehachse).</p>")
        else:
            self.kennwerte.setText("Keine Masse bekannt – bei den Teilen fehlt der Werkstoff bzw. die Masse.")
        self.masse_tabelle.setRowCount(len(m.je_einbau))
        self._hoehe_passend(self.masse_tabelle, 8)
        for i, z in enumerate(m.je_einbau):
            werte = (z.einbau, z.name, str(z.menge), "fehlt" if z.masse is None else formatiere(z.masse),
                     "–" if z.masse is None else f"{formatiere(round(z.anteil * 100, 1))} %")
            for j, wert in enumerate(werte):
                item = QTableWidgetItem(wert)
                if j in (2, 3, 4):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.masse_tabelle.setItem(i, j, item)
        self.masse_hinweis.setText(
            ("Ohne Masse (fehlt in Summe und Schwerpunkt): " + ", ".join(m.ohne_masse) + ".") if m.ohne_masse else
            "Annahme: jedes Teil durchgehend aus einem Werkstoff (gleichmäßige Dichte).")
