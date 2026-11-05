"""Gemeinsame Rechenseite für jede Berechnungsart (Rotor, Ertrag, Lasten, Antrieb …).

Die Seite wird aus der Beschreibung im Berechnungsmodul (FELDER, Quellen) aufgebaut, damit jede neue
Berechnung ohne eigene Oberfläche auskommt.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QFrame, QGridLayout, QHBoxLayout,
    QHeaderView, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..berechnungen import ARTEN, einheit_normal, wert_aus_ergebnis
from ..berechnungen.basis import Feld, formatiere
from ..einheiten import EinheitFehler, umrechnen
from ..modell import NEU_PRUEFEN, Projekt
from ..pdf import protokoll_erstellen
from .seiten import karte, leeren, scrollbar, titel


def projektwerte(projekt: Projekt | None, modul, felder: dict[str, Feld]) -> dict[str, tuple]:
    """Feld → (Wert, Quelle, Nummer) für alle Felder, die das Projekt liefern kann (Anforderungen und
    neueste gespeicherte Berechnung je Art). Gemeinsam für Rechenseite und Bauteilseite."""
    gefunden = {}
    if not projekt:
        return gefunden
    for attr, suchwort in modul.FELD_SUCHBEGRIFFE.items():
        a = projekt.anforderung_suchen(suchwort)
        if not a or a.zielwert is None:
            continue
        ziel = felder[attr].einheit
        try:
            wert = umrechnen(a.zielwert, a.einheit or ziel, ziel) if ziel else a.zielwert
        except EinheitFehler:
            continue
        gefunden[attr] = (wert, a.id, a.nr)
    alle = projekt.berechnungen()       # neueste zuerst
    for attr, (typ, symbol) in getattr(modul, "BERECHNUNGS_QUELLEN", {}).items():
        b = next((b for b in alle if b.typ == typ), None)
        if not b:
            continue
        treffer = wert_aus_ergebnis(b.ergebnis, symbol)
        if not treffer:
            continue
        wert, einheit = treffer
        ziel = felder[attr].einheit
        try:
            if einheit and ziel and einheit != ziel:
                wert = umrechnen(wert, einheit, ziel)
        except EinheitFehler:
            continue
        gefunden[attr] = (wert, ("berechnung", b.id), b.nr + (" ⚠" if b.status == NEU_PRUEFEN else ""))
    return gefunden


# ---------------------------------------------------------------- Diagramm
class Diagramm(QWidget):
    """Einfaches Liniendiagramm mit optionalen Balken (zweite Achse), ohne Zusatzbibliothek."""

    def __init__(self):
        super().__init__()
        self.daten: dict | None = None
        self.setMinimumHeight(260)

    def setze(self, daten: dict | None):
        self.daten = daten
        self.setVisible(bool(daten))
        self.update()

    def paintEvent(self, _):
        d = self.daten
        if not d or not d.get("x"):
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pal = self.palette()
        text = pal.color(pal.ColorRole.WindowText)
        linie = QColor(text)
        linie.setAlpha(60)
        akzent = pal.color(pal.ColorRole.Highlight)
        balken_farbe = QColor(text)
        balken_farbe.setAlpha(40)

        links, rechts, oben, unten = 56, 56 if d.get("balken") else 16, 28, 36
        flaeche = QRectF(links, oben, self.width() - links - rechts, self.height() - oben - unten)
        xs, ys = d["x"], d["y"]
        x_max = max(xs) or 1
        y_max = max(ys) * 1.1 or 1

        def px(x):
            return flaeche.left() + x / x_max * flaeche.width()

        def py(y, maximum=y_max):
            return flaeche.bottom() - y / maximum * flaeche.height()

        p.setPen(QPen(text))
        p.drawText(QRectF(links, 4, flaeche.width(), 20), Qt.AlignLeft, d.get("titel", ""))
        # Raster und Achsen
        p.setPen(QPen(linie, 1))
        for i in range(6):
            y = flaeche.top() + i * flaeche.height() / 5
            p.drawLine(QPointF(flaeche.left(), y), QPointF(flaeche.right(), y))
        p.setPen(QPen(text))
        for i in range(6):
            wert = y_max * (5 - i) / 5
            y = flaeche.top() + i * flaeche.height() / 5
            p.drawText(QRectF(0, y - 8, links - 6, 16), Qt.AlignRight | Qt.AlignVCenter, formatiere(wert, 2))
        schritt = 5 if x_max > 12 else 1
        x = 0
        while x <= x_max + 1e-9:
            p.drawText(QRectF(px(x) - 20, flaeche.bottom() + 4, 40, 16), Qt.AlignCenter, formatiere(x, 3))
            x += schritt
        p.drawText(QRectF(flaeche.left(), self.height() - 16, flaeche.width(), 16), Qt.AlignCenter, d.get("x_name", ""))
        p.save()
        p.translate(12, flaeche.center().y())
        p.rotate(-90)
        p.drawText(QRectF(-80, -10, 160, 20), Qt.AlignCenter, d.get("y_name", ""))
        p.restore()

        # Balken (z. B. Stunden je Windklasse) auf eigener Achse rechts
        balken = d.get("balken")
        if balken:
            b_max = max(balken) * 1.1 or 1
            breite = flaeche.width() / x_max * 0.7
            for i, b in enumerate(balken, 1):
                rect = QRectF(px(i) - breite / 2, py(b, b_max), breite, flaeche.bottom() - py(b, b_max))
                p.fillRect(rect, balken_farbe)
            p.setPen(QPen(text))
            for i in range(6):
                wert = b_max * (5 - i) / 5
                y = flaeche.top() + i * flaeche.height() / 5
                p.drawText(QRectF(flaeche.right() + 4, y - 8, rechts - 4, 16), Qt.AlignLeft | Qt.AlignVCenter,
                           formatiere(wert, 2))
            p.drawText(QRectF(flaeche.right() - 160, 4, 160, 20), Qt.AlignRight, "▮ " + d.get("balken_name", ""))

        pfad = QPainterPath()
        for i, (x, y) in enumerate(zip(xs, ys)):
            punkt = QPointF(px(x), py(y))
            if i == 0:
                pfad.moveTo(punkt)
            else:
                pfad.lineTo(punkt)
        p.setPen(QPen(akzent, 2.5))
        p.drawPath(pfad)
        p.end()


# ---------------------------------------------------------------- Rechenseite
class RechenSeite(QWidget):
    meldung = Signal(str, bool)
    gespeichert = Signal()

    def __init__(self, typ: str):
        super().__init__()
        self.typ = typ
        self.art = ARTEN[typ]
        self.modul = self.art["modul"]
        self.projekt: Projekt | None = None
        self.ergebnis = None
        self._genau: dict[str, float] = {}     # exakte übernommene Werte (Feld zeigt gerundet)

        inhalt = QWidget()
        lay = QVBoxLayout(inhalt)
        lay.setContentsMargins(32, 24, 32, 24)
        lay.addWidget(titel(self.modul.KURZ, self.modul.BESCHREIBUNG))

        oben = QHBoxLayout()
        oben.setSpacing(16)
        eingabe_box, el = karte()
        k = QLabel("Eingaben")
        k.setObjectName("Abschnitt")
        el.addWidget(k)
        form = QFormLayout()
        form.setVerticalSpacing(8)
        self.eingaben: dict[str, QDoubleSpinBox | QComboBox] = {}
        self.felder: dict[str, Feld] = {}
        standard = self.art["eingaben"]()
        for feld in self.modul.FELDER:
            self.felder[feld.attr] = feld
            if feld.auswahl:
                w = QComboBox()
                w.addItems(list(feld.auswahl))
                w.setCurrentText(getattr(standard, feld.attr))
                w.currentIndexChanged.connect(self.berechnen)
            else:
                w = QDoubleSpinBox()
                w.setRange(feld.minimum, feld.maximum)
                w.setSingleStep(feld.schritt)
                w.setDecimals(feld.stellen)
                w.setValue(getattr(standard, feld.attr))
                if feld.anzeige_einheit:
                    w.setSuffix(f"  {feld.anzeige_einheit}")
                w.setMinimumWidth(150)
                w.valueChanged.connect(self.berechnen)
            w.setToolTip(feld.tipp)
            self.eingaben[feld.attr] = w
            name = QLabel(feld.name)
            name.setToolTip(feld.tipp)
            name.setWordWrap(True)
            form.addRow(name, w)
        el.addLayout(form)
        self.uebernehmen = QPushButton("Werte aus dem Projekt übernehmen")
        self.uebernehmen.setToolTip("Aus Anforderungen und gespeicherten Berechnungen – dabei entsteht die "
                                    "Verknüpfung für die Rückverfolgung")
        self.uebernehmen.clicked.connect(self.aus_anforderungen)
        el.addWidget(self.uebernehmen)
        self.verknuepft = QLabel()
        self.verknuepft.setObjectName("Klein")
        self.verknuepft.setWordWrap(True)
        el.addWidget(self.verknuepft)
        el.addStretch()
        oben.addWidget(eingabe_box, 2)

        ergebnis_box, rl = karte()
        k = QLabel("Ergebnis")
        k.setObjectName("Abschnitt")
        rl.addWidget(k)
        self.gross = QLabel("–")
        self.gross.setObjectName("Gross")
        rl.addWidget(self.gross)
        self.gross_text = QLabel()
        self.gross_text.setObjectName("Klein")
        rl.addWidget(self.gross_text)
        self.ergebnis_raster = QGridLayout()
        self.ergebnis_raster.setHorizontalSpacing(24)
        self.ergebnis_raster.setVerticalSpacing(6)
        rl.addLayout(self.ergebnis_raster)
        self.pruef_box = QVBoxLayout()
        rl.addLayout(self.pruef_box)
        self.unbelegt = QLabel()
        self.unbelegt.setObjectName("StatusWarnung")
        self.unbelegt.setWordWrap(True)
        rl.addWidget(self.unbelegt)
        self.speichern = QPushButton("Protokoll speichern (PDF)")
        self.speichern.setObjectName("Haupt")
        self.speichern.setToolTip("Speichert die Berechnung im Projekt und erzeugt das PDF-Protokoll (⌘S)")
        self.speichern.setShortcut("Ctrl+S")
        self.speichern.clicked.connect(lambda: self.protokoll_speichern())
        rl.addWidget(self.speichern, 0, Qt.AlignLeft)
        rl.addStretch()
        oben.addWidget(ergebnis_box, 3)
        lay.addLayout(oben)

        self.diagramm_box, dl = karte()
        self.diagramm = Diagramm()
        dl.addWidget(self.diagramm)
        lay.addWidget(self.diagramm_box)

        self.tabellen_box, self.tabellen_lay = karte()
        lay.addWidget(self.tabellen_box)

        weg_box, wl = karte()
        k = QLabel("Rechenweg")
        k.setObjectName("Abschnitt")
        wl.addWidget(k)
        self.rechenweg = QLabel()
        self.rechenweg.setWordWrap(True)
        self.rechenweg.setTextInteractionFlags(Qt.TextSelectableByMouse)
        wl.addWidget(self.rechenweg)
        self.quellen = QLabel()
        self.quellen.setObjectName("Klein")
        self.quellen.setWordWrap(True)
        self.quellen.setTextInteractionFlags(Qt.TextSelectableByMouse)
        wl.addWidget(self.quellen)
        lay.addWidget(weg_box)
        lay.addStretch()

        aussen = QVBoxLayout(self)
        aussen.setContentsMargins(0, 0, 0, 0)
        aussen.addWidget(scrollbar(inhalt))
        self.berechnen()

    # ---------- Projekt ----------
    def setze_projekt(self, projekt: Projekt):
        self.projekt = projekt
        self._verknuepfung_zeigen()

    def werte(self):
        werte = {}
        for attr, w in self.eingaben.items():
            if isinstance(w, QComboBox):
                werte[attr] = w.currentText()
                continue
            v = w.value()
            genau = self._genau.get(attr)
            if genau is not None and abs(genau - v) <= 0.51 * 10 ** -w.decimals():
                v = genau
            werte[attr] = v
        return self.art["eingaben"](**werte)

    def _passt(self, attr: str, wert: float) -> bool:
        w = self.eingaben[attr]
        return abs(wert - w.value()) <= max(0.51 * 10 ** -w.decimals(), 1e-6 * abs(wert))

    def _projektwerte(self) -> dict[str, tuple]:
        return projektwerte(self.projekt, self.modul, self.felder)

    def quellen_ermitteln(self) -> dict:
        """Welche Eingaben stammen aus dem Projekt? Nur wenn der Wert übereinstimmt, wird verknüpft –
        so entsteht keine falsche Rückverfolgung bei Handeingaben."""
        return {attr: quelle for attr, (wert, quelle, _) in self._projektwerte().items() if self._passt(attr, wert)}

    def _verknuepfung_zeigen(self):
        werte = self._projektwerte()
        teile = [f"{self.felder[a].name} ← {nr}" for a, (w, _, nr) in werte.items() if self._passt(a, w)]
        self.verknuepft.setText(("Verknüpft: " + " · ".join(teile)) if teile else
                                "Noch keine Werte aus dem Projekt übernommen.")

    def aus_anforderungen(self):
        if not self.projekt:
            return
        werte = self._projektwerte()
        if not werte:
            self.meldung.emit("Im Projekt gibt es noch keine passenden Anforderungen oder Berechnungen.", True)
            return
        self._genau.clear()
        for attr, (wert, _, _) in werte.items():
            w = self.eingaben[attr]
            w.blockSignals(True)
            w.setValue(wert)
            w.blockSignals(False)
            self._genau[attr] = wert
        self.berechnen()
        nummern = sorted({nr for _, _, nr in werte.values()})
        warnung = any("⚠" in n for n in nummern)
        self.meldung.emit(f"{len(werte)} Werte übernommen aus {', '.join(nummern)}."
                          + (" Achtung: eine Quelle muss neu berechnet werden." if warnung else ""), warnung)

    # ---------- Rechnen ----------
    def berechnen(self):
        leeren(self.pruef_box)
        leeren(self.ergebnis_raster)
        leeren(self.tabellen_lay)
        try:
            self.ergebnis = self.art["berechne"](self.werte())
        except ValueError as exc:
            self.ergebnis = None
            self.gross.setText("–")
            hinweis = QLabel(str(exc))
            hinweis.setObjectName("Fehler")
            hinweis.setWordWrap(True)
            self.pruef_box.addWidget(hinweis)
            self.speichern.setEnabled(False)
            self.unbelegt.hide()
            self.diagramm_box.hide()
            self.tabellen_box.hide()
            return
        e = self.ergebnis
        h = e.ergebnis(self.modul.HAUPT)
        self.gross.setText(f"{formatiere(h.wert)} {h.einheit}")
        self.gross_text.setText(h.name)
        for i, g in enumerate(e.ergebnisse):
            name = QLabel(f"{g.name} ({g.symbol})")
            name.setWordWrap(True)
            wert = QLabel(f"<b>{formatiere(g.wert)}</b> {g.einheit}")
            wert.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.ergebnis_raster.addWidget(name, i, 0)
            self.ergebnis_raster.addWidget(wert, i, 1)
        for p in e.pruefungen:
            zeichen = "✓" if p.erfuellt else "✗"
            lbl = QLabel(f"{zeichen}  {p.titel}: {p.bedingung}" + (f" – {p.hinweis}" if p.hinweis else ""))
            lbl.setObjectName("Ok" if p.erfuellt else "Fehler")
            lbl.setWordWrap(True)
            self.pruef_box.addWidget(lbl)
        self.unbelegt.setVisible(bool(e.unbelegt))
        self.unbelegt.setText("⚠ Unbelegt – vor dem Bau mit der Quelle prüfen:<br>• " + "<br>• ".join(e.unbelegt))

        self.diagramm_box.setVisible(bool(e.diagramm))
        self.diagramm.setze(e.diagramm)
        self.tabellen_box.setVisible(bool(e.tabellen))
        for t in e.tabellen:
            k = QLabel(t["titel"])
            k.setObjectName("Unterabschnitt")
            self.tabellen_lay.addWidget(k)
            self.tabellen_lay.addWidget(self._tabelle(t))

        zeilen = []
        for i, s in enumerate(e.schritte, 1):
            zeilen.append(f"<p><b>{i}. {s.titel}</b><br>{s.formel}<br>{s.einsetzen}<br>"
                          f"→ <b>{s.ergebnis.symbol} = {formatiere(s.ergebnis.wert)} {s.ergebnis.einheit}</b></p>")
        self.rechenweg.setText("".join(zeilen))
        self.quellen.setText("<b>Quellen:</b><br>• " + "<br>• ".join(e.quellen) +
                             "<br><b>Hinweise:</b><br>• " + "<br>• ".join(e.hinweise))
        self.speichern.setEnabled(True)
        if self.projekt:
            self._verknuepfung_zeigen()

    def _tabelle(self, t: dict) -> QTableWidget:
        tab = QTableWidget(len(t["zeilen"]), len(t["spalten"]))
        tab.setHorizontalHeaderLabels(t["spalten"])
        tab.verticalHeader().setVisible(False)
        tab.setEditTriggers(QAbstractItemView.NoEditTriggers)
        tab.setSelectionMode(QAbstractItemView.NoSelection)
        tab.setAlternatingRowColors(True)
        tab.verticalHeader().setDefaultSectionSize(30)
        tab.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        tab.horizontalHeader().setStretchLastSection(True)
        for z, zeile in enumerate(t["zeilen"]):
            for s, wert in enumerate(zeile):
                text = formatiere(wert) if isinstance(wert, (int, float)) and not isinstance(wert, bool) else str(wert)
                item = QTableWidgetItem(text)
                if isinstance(wert, (int, float)):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if wert == "unbelegt":
                    item.setText("⚠ unbelegt")
                tab.setItem(z, s, item)
        hoehe = max(tab.horizontalHeader().sizeHint().height(), 32) + 30 * len(t["zeilen"]) + 4
        tab.setFixedHeight(hoehe)
        return tab

    def protokoll_speichern(self, ziel: str | None = None):
        if not self.ergebnis or not self.projekt:
            return None
        daten = self.ergebnis.als_dict()
        quellen = self.quellen_ermitteln()
        eintrag = self.projekt.berechnung_speichern(daten, self.werte().__dict__, quellen)
        if ziel is None:
            vorschlag = self.projekt.pfad.parent / f"{eintrag.nr}_{self.modul.KURZ.replace(' ', '_')}.pdf"
            ziel, _ = QFileDialog.getSaveFileName(self, "Protokoll speichern", str(vorschlag), "PDF (*.pdf)")
            if not ziel:
                self.meldung.emit(f"Berechnung {eintrag.nr} im Projekt gespeichert (ohne PDF).", False)
                self.gespeichert.emit()
                return None
        try:
            pfad = protokoll_erstellen(daten, ziel, self.projekt.name, eintrag.nr)
            self.projekt.dokument_merken("protokoll", pfad, eintrag.nr)
        except OSError as exc:
            self.meldung.emit(f"PDF konnte nicht gespeichert werden: {exc}. Anderen Ordner wählen?", True)
            return None
        nummern = sorted({b.nr for b in self.projekt.haengt_ab_von("berechnung", eintrag.id)})
        zusatz = f" Verknüpft mit {', '.join(nummern)}." if nummern else " Ohne Verknüpfung (Werte von Hand)."
        self.meldung.emit(f"Berechnung {eintrag.nr} gespeichert, Protokoll: {Path(pfad).name}.{zusatz}", False)
        self.gespeichert.emit()
        return pfad


def RotorSeite() -> RechenSeite:   # noqa: N802  (Name bleibt für bestehende Aufrufer)
    return RechenSeite("rotorauslegung")


__all__ = ["Diagramm", "RechenSeite", "RotorSeite", "einheit_normal"]
