"""Seiten „Inbetriebnahme“ und „Wartung“ (MS11): Checkliste Soll/Ist, Leistungskurve, Abnahme, Wartungsplan,
Rückmeldung in die nächste Version."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..berechnungen.basis import formatiere
from ..betrieb import inbetriebnahme as IB, wartung as W
from ..modell import NEU_PRUEFEN, Projekt, ProjektFehler
from .seiten import karte, scrollbar, titel

GRUEN, ROT = QColor(46, 160, 67, 70), QColor(218, 54, 51, 80)


def _item(text: str, editierbar: bool = False) -> QTableWidgetItem:
    it = QTableWidgetItem(text)
    it.setToolTip(text)
    if not editierbar:
        it.setFlags(it.flags() & ~Qt.ItemIsEditable)
    return it


def _spalten(tabelle: QTableWidget, breiten: list[int], dehnen: int):
    kopf = tabelle.horizontalHeader()
    kopf.setSectionResizeMode(QHeaderView.Interactive)
    for i, b in enumerate(breiten):
        tabelle.setColumnWidth(i, b)
    kopf.setSectionResizeMode(dehnen, QHeaderView.Stretch)
    kopf.setMinimumSectionSize(40)


def _knopf(text: str, fn, haupt: bool = False, tipp: str = "") -> QPushButton:
    b = QPushButton(text)
    if haupt:
        b.setObjectName("Haupt")
    if tipp:
        b.setToolTip(tipp)
    b.clicked.connect(lambda: fn())
    return b


class Kurve(QWidget):
    """Kleines Diagramm: berechnete Leistungskurve (Linie) und Messpunkte."""

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(220)
        self.soll: dict | None = None
        self.punkte: list = []

    def setze(self, soll, punkte):
        self.soll, self.punkte = soll, punkte
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        text = self.palette().windowText().color()
        r = self.rect().adjusted(44, 12, -12, -30)
        xs = list((self.soll or {}).get("x", [])) + [m.v for m in self.punkte]
        ys = list((self.soll or {}).get("y", [])) + [m.p for m in self.punkte]
        if not xs:
            p.setPen(text)
            p.drawText(self.rect(), Qt.AlignCenter, "Keine Leistungskurve – zuerst die Ertragsberechnung speichern.")
            return
        x_max, y_max = max(max(xs), 1.0), max(max(ys), 0.1) * 1.1

        def pt(x, y):
            return QPointF(r.left() + x / x_max * r.width(), r.bottom() - y / y_max * r.height())

        p.setPen(QPen(text, 1))
        p.drawLine(r.bottomLeft(), r.bottomRight())
        p.drawLine(r.bottomLeft(), r.topLeft())
        for i in range(0, int(x_max) + 1, 5):
            p.drawText(pt(i, 0) + QPointF(-4, 16), str(i))
        for k in range(5):
            y = y_max * k / 4
            p.drawText(QPointF(4, pt(0, y).y() + 4), formatiere(y, 2))
        p.drawText(QPointF(r.right() - 120, r.bottom() + 26), "v in m/s")
        p.drawText(QPointF(4, 10), "P in kW")
        if self.soll and self.soll.get("x"):
            p.setPen(QPen(QColor(31, 111, 181), 2))
            pts = [pt(x, y) for x, y in zip(self.soll["x"], self.soll["y"])]
            for a, b in zip(pts, pts[1:]):
                p.drawLine(a, b)
        for m in self.punkte:
            farbe = QColor(217, 130, 43) if m.ok is not False else QColor(218, 54, 51)
            p.setPen(QPen(farbe, 1))
            p.setBrush(farbe)
            p.drawEllipse(pt(m.v, m.p), 4.5, 4.5)


# ==================================================================== Inbetriebnahme
SPALTEN_IB = ["Nr", "Gruppe", "Prüfpunkt", "Soll", "Ist", "Ergebnis", "Bemerkung", "Quelle"]


class InbetriebnahmeSeite(QWidget):
    meldung = Signal(str, bool)
    gespeichert = Signal()

    def __init__(self):
        super().__init__()
        self.projekt: Projekt | None = None
        self.iid: int | None = None
        self.daten: dict | None = None
        self._fuellt = False
        inhalt = QWidget()
        lay = QVBoxLayout(inhalt)
        lay.setContentsMargins(32, 24, 32, 24)
        lay.addWidget(titel("Inbetriebnahme", "Checkliste mit Soll- und Ist-Werten (mechanisch, elektrisch, "
                                              "Sicherheitsfunktionen, Messungen). Sollwerte kommen aus den Berechnungen "
                                              "und Montageplänen. Daraus entstehen Mess- und Abnahmeprotokoll."))
        k, kl = karte()
        z = QHBoxLayout()
        self.wahl = QComboBox()
        self.wahl.setAccessibleName("Inbetriebnahme")
        self.wahl.setMinimumContentsLength(22)
        self.wahl.activated.connect(lambda _: self.laden_id(self.wahl.currentData()))
        z.addWidget(self.wahl, 2)
        z.addWidget(_knopf("Neue Checkliste", self.neu,
                           tipp="Vorlage Kleinwindanlage: Prüfpunkte mit Sollwerten aus dem aktuellen Projektstand"))
        self.speichern = _knopf("Speichern", self.speichern_, haupt=True)
        self.speichern.setShortcut("Ctrl+S")
        z.addWidget(self.speichern)
        z.addWidget(_knopf("Abnahmeprotokoll …", lambda: self.pdf("abnahme")))
        z.addWidget(_knopf("Messprotokoll …", lambda: self.pdf("messung")))
        kl.addLayout(z)
        z = QHBoxLayout()
        for name, attr, breite in (("Datum", "datum", 110), ("Ort", "ort", 180), ("Prüfer", "pruefer", 180)):
            z.addWidget(QLabel(name))
            feld = QLineEdit()
            feld.setMaximumWidth(breite * 2)
            feld.setMinimumWidth(80)
            feld.editingFinished.connect(lambda a=attr, w=feld: self._kopf(a, w.text().strip()))
            setattr(self, f"f_{attr}", feld)
            z.addWidget(feld, 1)
        kl.addLayout(z)
        self.status = QLabel()
        self.status.setObjectName("Klein")
        self.status.setWordWrap(True)
        kl.addWidget(self.status)
        self.urteil = QLabel()
        self.urteil.setWordWrap(True)
        kl.addWidget(self.urteil)
        lay.addWidget(k)

        k, kl = karte()
        z = QHBoxLayout()
        t = QLabel("Prüfpunkte")
        t.setObjectName("Abschnitt")
        z.addWidget(t)
        z.addStretch()
        erkl = QLabel("Ist: Messwert oder „i. O.“ / „n. i. O.“")
        erkl.setObjectName("Klein")
        z.addWidget(erkl)
        z.addWidget(_knopf("+ Prüfpunkt", lambda: self.punkt_neu()))
        z.addWidget(_knopf("Löschen", lambda: self.punkt_loeschen()))
        kl.addLayout(z)
        self.tabelle = QTableWidget(0, len(SPALTEN_IB))
        self.tabelle.setHorizontalHeaderLabels(SPALTEN_IB)
        self.tabelle.verticalHeader().hide()
        self.tabelle.setSelectionBehavior(QAbstractItemView.SelectRows)
        _spalten(self.tabelle, [48, 128, 0, 130, 70, 92, 150, 96], 2)
        self.tabelle.setWordWrap(False)
        self.tabelle.setMinimumHeight(420)
        self.tabelle.itemChanged.connect(self._zelle)
        kl.addWidget(self.tabelle)
        hinweis = QLabel(IB.HINWEIS)
        hinweis.setObjectName("Klein")
        hinweis.setWordWrap(True)
        kl.addWidget(hinweis)
        lay.addWidget(k)

        unten = QHBoxLayout()
        k, kl = karte()
        z = QHBoxLayout()
        t = QLabel("Leistungskurve messen")
        t.setObjectName("Abschnitt")
        z.addWidget(t)
        z.addStretch()
        z.addWidget(_knopf("+ Messpunkt", lambda: self.messpunkt_neu()))
        z.addWidget(_knopf("Löschen", lambda: self.messpunkt_loeschen()))
        kl.addLayout(z)
        self.messung = QTableWidget(0, 5)
        self.messung.setHorizontalHeaderLabels(["v m/s", "P gemessen kW", "P Rechnung kW", "Abweichung", "Ergebnis"])
        self.messung.verticalHeader().hide()
        self.messung.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.messung.setMinimumHeight(200)
        self.messung.itemChanged.connect(self._mess_zelle)
        kl.addWidget(self.messung)
        self.kurve = Kurve()
        kl.addWidget(self.kurve)
        unten.addWidget(k, 3)
        k, kl = karte()
        t = QLabel("Rückmeldung in die nächste Version")
        t.setObjectName("Abschnitt")
        kl.addWidget(t)
        erkl = QLabel("Mängel und Erfahrungen werden zu Ideen in Phase P1 – dort für die nächste Version bewerten.")
        erkl.setObjectName("Klein")
        erkl.setWordWrap(True)
        kl.addWidget(erkl)
        kl.addWidget(_knopf("Alle Mängel (n. i. O.) übernehmen", lambda: self.maengel_uebernehmen()))
        self.erfahrung = QLineEdit()
        self.erfahrung.setPlaceholderText("Erfahrung oder Verbesserung, z. B. „Bremse quietscht bei Kälte“")
        kl.addWidget(self.erfahrung)
        kl.addWidget(_knopf("Als Idee übernehmen", lambda: self.erfahrung_uebernehmen()))
        self.rueck = QLabel()
        self.rueck.setObjectName("Klein")
        self.rueck.setWordWrap(True)
        kl.addWidget(self.rueck)
        kl.addStretch()
        unten.addWidget(k, 2)
        lay.addLayout(unten)
        aussen = QVBoxLayout(self)
        aussen.setContentsMargins(0, 0, 0, 0)
        aussen.addWidget(scrollbar(inhalt))

    # ---------- Laden ----------
    def setze_projekt(self, projekt: Projekt):
        self.projekt = projekt
        self.iid = None
        self.laden()

    def laden(self):
        if not self.projekt:
            return
        liste = self.projekt.inbetriebnahmen()
        self._fuellt = True
        self.wahl.clear()
        for o in liste:
            zeichen = " ⚠" if o["status"] == NEU_PRUEFEN else (" ✓" if IB.auswerten(o["daten"])["abgenommen"] else "")
            self.wahl.addItem(f"{o['nr']} {o['name']}{zeichen}", o["id"])
        self._fuellt = False
        if not liste:
            self.iid, self.daten = None, None
            self.status.setText("Noch keine Checkliste – mit „Neue Checkliste“ aus der Vorlage anlegen.")
            self._anzeigen()
            return
        self.laden_id(self.iid if self.iid in [o["id"] for o in liste] else liste[-1]["id"])

    def laden_id(self, iid: int | None):
        if iid is None:
            return
        o = self.projekt.inbetriebnahme(iid)
        self.iid, self.daten = iid, o["daten"]
        self.wahl.setCurrentIndex(max(0, self.wahl.findData(iid)))
        text = f"{o['nr']} · Version {o['version']} · {o['status']}"
        if o["status"] == NEU_PRUEFEN:
            text += " – eine Berechnung oder ein Montageplan hat sich geändert: Sollwerte prüfen (neue Checkliste anlegen)."
        self.status.setText(text)
        self._anzeigen()

    def neu(self) -> dict:
        o = self.projekt.inbetriebnahme_neu("Inbetriebnahme Kleinwindanlage")
        self.iid = o["id"]
        self.laden()
        self.meldung.emit(f"Checkliste {o['nr']} mit {len(o['daten']['punkte'])} Prüfpunkten angelegt.", False)
        return o

    # ---------- Bearbeiten ----------
    def _kopf(self, attr, wert):
        if self.daten is not None and not self._fuellt:
            self.daten[attr] = wert

    def _zelle(self, item: QTableWidgetItem):
        if self._fuellt or self.daten is None:
            return
        p = self.daten["punkte"][item.row()]
        feld = {2: "text", 4: "ist", 6: "bemerkung"}.get(item.column())
        if feld:
            p[feld] = item.text().strip()
            self._anzeigen(behalten=True)

    def setze_ist(self, zeile: int, text: str):
        self.tabelle.item(zeile, 4).setText(text)

    def punkt_neu(self, text: str = "Neuer Prüfpunkt", gruppe: str = "Mechanisch", **soll) -> dict | None:
        if self.daten is None:
            return None
        p = IB._punkt(0, gruppe, text, soll.get("min"), soll.get("max"), soll.get("einheit", ""),
                      soll.get("soll_text", ""))
        p["id"] = IB.naechste_id(self.daten)
        self.daten["punkte"].append(p)
        self._anzeigen()
        self.tabelle.setCurrentCell(self.tabelle.rowCount() - 1, 2)
        return p

    def punkt_loeschen(self, zeile: int | None = None):
        i = self.tabelle.currentRow() if zeile is None else zeile
        if self.daten is not None and 0 <= i < len(self.daten["punkte"]):
            self.daten["punkte"].pop(i)
            self._anzeigen()

    def messpunkt_neu(self, v: float | None = None, p: float | None = None):
        if self.daten is None:
            return
        letzte = max((m["v"] for m in self.daten["messung"]), default=3.0)
        self.daten["messung"].append({"v": letzte + 1 if v is None else v, "p": 0.0 if p is None else p})
        self._anzeigen(behalten=True)

    def messpunkt_loeschen(self, zeile: int | None = None):
        i = self.messung.currentRow() if zeile is None else zeile
        if self.daten is not None and 0 <= i < len(self.daten["messung"]):
            self.daten["messung"].sort(key=lambda m: m["v"])
            self.daten["messung"].pop(i)
            self._anzeigen(behalten=True)

    def _mess_zelle(self, item: QTableWidgetItem):
        if self._fuellt or self.daten is None or item.column() > 1:
            return
        self.daten["messung"].sort(key=lambda m: m["v"])
        x = IB.zahl(item.text())
        if x is not None:
            self.daten["messung"][item.row()]["vp"[item.column()]] = x
        self._anzeigen(behalten=True)

    # ---------- Rückmeldung (S14) ----------
    def maengel_uebernehmen(self) -> list[dict]:
        if self.daten is None:
            return []
        nr = self.projekt.inbetriebnahme(self.iid)["nr"]
        neu = []
        for p in IB.maengel(self.daten):
            if p.get("idee"):
                continue
            idee = self.projekt.rueckmeldung(
                f"Mangel bei der Inbetriebnahme: {p['text']}",
                f"Soll {IB.soll_text(p)}, Ist {p['ist']}" + (f" – {p['bemerkung']}" if p.get("bemerkung") else ""),
                f"{nr} {p['id']}")
            p["idee"] = idee["nr"]
            neu.append(idee)
        self.speichern_(melden=False)
        self.rueck.setText(f"{len(neu)} Mängel als Ideen übernommen: " + ", ".join(i["nr"] for i in neu) if neu
                           else "Keine neuen Mängel (n. i. O.) zum Übernehmen.")
        self.gespeichert.emit()
        return neu

    def erfahrung_uebernehmen(self) -> dict | None:
        try:
            nr = self.projekt.inbetriebnahme(self.iid)["nr"] if self.iid else "Betrieb"
            idee = self.projekt.rueckmeldung(self.erfahrung.text(), "", nr)
        except ProjektFehler as exc:
            self.meldung.emit(str(exc), True)
            return None
        self.erfahrung.clear()
        self.rueck.setText(f"Als Idee {idee['nr']} „{idee['titel']}“ übernommen (Seite „Ideen & TRIZ“).")
        self.gespeichert.emit()
        return idee

    # ---------- Anzeige ----------
    def _anzeigen(self, behalten: bool = False):
        zeile = self.tabelle.currentRow()
        self._fuellt = True
        d = self.daten
        for attr in ("datum", "ort", "pruefer"):
            getattr(self, f"f_{attr}").setText((d or {}).get(attr, ""))
        punkte = (d or {}).get("punkte", [])
        a = IB.auswerten(d) if d else None
        self.tabelle.setRowCount(len(punkte))
        for i, p in enumerate(punkte):
            erg = IB.ergebnis(p)
            werte = [p["id"], p["gruppe"], p["text"], IB.soll_text(p), p.get("ist", ""), erg,
                     p.get("bemerkung", "") + (f" → Idee {p['idee']}" if p.get("idee") else ""), p.get("quelle", "")]
            for j, w in enumerate(werte):
                it = _item(str(w), editierbar=j in (2, 4, 6) and not p["text"].startswith("Leistungskurve gemessen"))
                if j == 5 and erg != IB.OFFEN:
                    it.setBackground(GRUEN if erg == IB.IO else ROT)
                self.tabelle.setItem(i, j, it)
        mp = a["messpunkte"] if a else []
        self.messung.setRowCount(len(mp))
        for i, m in enumerate(mp):
            werte = [formatiere(m.v), formatiere(m.p), "–" if m.soll is None else formatiere(m.soll),
                     "–" if m.abweichung is None else f"{formatiere(m.abweichung * 100, 3)} %",
                     "–" if m.ok is None else (IB.IO if m.ok else IB.NIO)]
            for j, w in enumerate(werte):
                it = _item(w, editierbar=j < 2)
                if j == 4 and m.ok is not None:
                    it.setBackground(GRUEN if m.ok else ROT)
                self.messung.setItem(i, j, it)
        self.kurve.setze((d or {}).get("soll_kurve"), mp)
        if a:
            self.urteil.setText(("<b>✓ Abnahme möglich</b> – alle Punkte in Ordnung." if a["abgenommen"] else
                                 f"<b>{a['io']} von {a['gesamt']} in Ordnung</b> · {a['nio']} nicht in Ordnung · "
                                 f"{a['offen']} offen"))
        else:
            self.urteil.setText("")
        self._fuellt = False
        if behalten and 0 <= zeile < self.tabelle.rowCount():
            self.tabelle.setCurrentCell(zeile, 4)

    # ---------- Speichern, PDF ----------
    def speichern_(self, melden: bool = True) -> dict | None:
        if self.iid is None or self.daten is None:
            return None
        o = self.projekt.inbetriebnahme_speichern(self.iid, self.daten)
        self.status.setText(f"{o['nr']} · Version {o['version']} · {o['status']}")
        if melden:
            self.meldung.emit(f"Checkliste {o['nr']} gespeichert.", False)
            self.gespeichert.emit()
        return o

    def pdf(self, art: str, ziel: str | None = None) -> Path | None:
        if self.iid is None:
            return None
        o = self.projekt.inbetriebnahme(self.iid)
        o["daten"] = self.daten
        name = {"abnahme": "Abnahmeprotokoll", "messung": "Messprotokoll"}[art]
        if ziel is None:
            ziel, _ = QFileDialog.getSaveFileName(self, f"{name} speichern", f"{name}_{o['nr']}.pdf", "PDF (*.pdf)")
            if not ziel:
                return None
        from ..pdf import abnahmeprotokoll_erstellen, messprotokoll_erstellen
        fn = abnahmeprotokoll_erstellen if art == "abnahme" else messprotokoll_erstellen
        pfad = fn(o, ziel, self.projekt.name)
        self.projekt.dokument_merken("abnahmeprotokoll" if art == "abnahme" else "messprotokoll", pfad, o["nr"])
        self.meldung.emit(f"{name} gespeichert: {Path(pfad).name}", False)
        return Path(pfad)


# ==================================================================== Wartung
SPALTEN_W = ["Bauteil", "Tätigkeit", "Intervall", "Erstes", "Verschleiß", "Zuletzt", "Fällig", "Quelle"]


class WartungSeite(QWidget):
    meldung = Signal(str, bool)
    gespeichert = Signal()

    def __init__(self):
        super().__init__()
        self.projekt: Projekt | None = None
        self.wid: int | None = None
        self.daten: dict | None = None
        self.heute = date.today()
        self._fuellt = False
        inhalt = QWidget()
        lay = QVBoxLayout(inhalt)
        lay.setContentsMargins(32, 24, 32, 24)
        lay.addWidget(titel("Wartung", "Wartungsplan mit Intervallen, Verschleißteilen und Fälligkeiten. Lagertausch "
                                       "aus der Lebensdauer der Lagerberechnung."))
        k, kl = karte()
        z = QHBoxLayout()
        self.wahl = QComboBox()
        self.wahl.setMinimumContentsLength(22)
        self.wahl.activated.connect(lambda _: self.laden_id(self.wahl.currentData()))
        z.addWidget(self.wahl, 2)
        z.addWidget(_knopf("Neuer Wartungsplan", self.neu, tipp="Vorlage Kleinwindanlage, Lagertausch aus L10h"))
        self.speichern = _knopf("Speichern", self.speichern_, haupt=True)
        self.speichern.setShortcut("Ctrl+S")
        z.addWidget(self.speichern)
        z.addWidget(_knopf("PDF …", lambda: self.pdf()))
        kl.addLayout(z)
        z = QHBoxLayout()
        z.addWidget(QLabel("In Betrieb seit"))
        self.start = QLineEdit()
        self.start.setPlaceholderText("TT.MM.JJJJ")
        self.start.setMaximumWidth(160)
        self.start.editingFinished.connect(self._start)
        z.addWidget(self.start)
        z.addStretch()
        z.addWidget(_knopf("Gewählten Punkt heute erledigt", lambda: self.erledigt()))
        z.addWidget(_knopf("+ Punkt", lambda: self.punkt_neu()))
        z.addWidget(_knopf("Löschen", lambda: self.punkt_loeschen()))
        kl.addLayout(z)
        self.status = QLabel()
        self.status.setObjectName("Klein")
        self.status.setWordWrap(True)
        kl.addWidget(self.status)
        self.tabelle = QTableWidget(0, len(SPALTEN_W))
        self.tabelle.setHorizontalHeaderLabels(SPALTEN_W)
        self.tabelle.verticalHeader().hide()
        self.tabelle.setSelectionBehavior(QAbstractItemView.SelectRows)
        _spalten(self.tabelle, [190, 0, 88, 70, 104, 96, 96, 140], 1)
        self.tabelle.setMinimumHeight(430)
        self.tabelle.itemChanged.connect(self._zelle)
        kl.addWidget(self.tabelle)
        self.zusammenfassung = QLabel()
        self.zusammenfassung.setWordWrap(True)
        kl.addWidget(self.zusammenfassung)
        hinweis = QLabel(W.HINWEIS)
        hinweis.setObjectName("Klein")
        hinweis.setWordWrap(True)
        kl.addWidget(hinweis)
        lay.addWidget(k)
        lay.addStretch()
        aussen = QVBoxLayout(self)
        aussen.setContentsMargins(0, 0, 0, 0)
        aussen.addWidget(scrollbar(inhalt))

    def setze_projekt(self, projekt: Projekt):
        self.projekt = projekt
        self.wid = None
        self.laden()

    def laden(self):
        if not self.projekt:
            return
        liste = self.projekt.wartungsplaene()
        self.wahl.clear()
        for o in liste:
            self.wahl.addItem(f"{o['nr']} {o['name']}" + (" ⚠" if o["status"] == NEU_PRUEFEN else ""), o["id"])
        if not liste:
            self.wid, self.daten = None, None
            self.status.setText("Noch kein Wartungsplan – mit „Neuer Wartungsplan“ aus der Vorlage anlegen.")
            self._anzeigen()
            return
        self.laden_id(self.wid if self.wid in [o["id"] for o in liste] else liste[-1]["id"])

    def laden_id(self, wid):
        if wid is None:
            return
        o = self.projekt.wartungsplan(wid)
        self.wid, self.daten = wid, o["daten"]
        self.wahl.setCurrentIndex(max(0, self.wahl.findData(wid)))
        text = f"{o['nr']} · Version {o['version']} · {o['status']}"
        if o["status"] == NEU_PRUEFEN:
            text += " – die Lager- oder Ertragsberechnung hat sich geändert: Intervalle prüfen."
        self.status.setText(text)
        self._anzeigen()

    def neu(self) -> dict:
        o = self.projekt.wartungsplan_neu("Wartungsplan Kleinwindanlage")
        self.wid = o["id"]
        self.laden()
        self.meldung.emit(f"Wartungsplan {o['nr']} angelegt.", False)
        return o

    def _start(self):
        if self.daten is None or self._fuellt:
            return
        d = W.lesen(self.start.text())
        if d is None and self.start.text().strip():
            self.meldung.emit("Datum bitte als TT.MM.JJJJ eingeben.", True)
            return
        self.daten["start"] = d.isoformat() if d else ""
        self._anzeigen()

    def _zelle(self, item: QTableWidgetItem):
        if self._fuellt or self.daten is None:
            return
        p = self.daten["punkte"][item.row()]
        j, t = item.column(), item.text().strip()
        if j in (0, 1):
            p[("bauteil", "taetigkeit")[j]] = t
        elif j in (2, 3):
            x = IB.zahl(t)
            p[("intervall", "erstes")[j - 2]] = int(x) if x and x > 0 else None
        elif j == 4:
            p["verschleiss"] = t.lower() in ("ja", "x", "●", "✓")
        elif j == 5:
            d = W.lesen(t)
            p["zuletzt"] = d.isoformat() if d else ""
        self._anzeigen()

    def erledigt(self, zeile: int | None = None):
        i = self.tabelle.currentRow() if zeile is None else zeile
        if self.daten is not None and 0 <= i < len(self.daten["punkte"]):
            self.daten["punkte"][i]["zuletzt"] = self.heute.isoformat()
            self._anzeigen()

    def punkt_neu(self, bauteil: str = "Neues Bauteil", taetigkeit: str = "", intervall: int = 12) -> dict | None:
        if self.daten is None:
            return None
        p = W._p(0, bauteil, taetigkeit, intervall, quelle="von Hand")
        p["id"] = W.naechste_id(self.daten)
        self.daten["punkte"].append(p)
        self._anzeigen()
        return p

    def punkt_loeschen(self, zeile: int | None = None):
        i = self.tabelle.currentRow() if zeile is None else zeile
        if self.daten is not None and 0 <= i < len(self.daten["punkte"]):
            self.daten["punkte"].pop(i)
            self._anzeigen()

    def _anzeigen(self):
        zeile = self.tabelle.currentRow()
        self._fuellt = True
        d = self.daten or {}
        self.start.setText(W.anzeigen(W.lesen(d.get("start", ""))))
        punkte = d.get("punkte", [])
        self.tabelle.setRowCount(len(punkte))
        for i, p in enumerate(punkte):
            f_ = W.faellig(p, d.get("start", ""))
            werte = [p["bauteil"], p["taetigkeit"], str(p.get("intervall") or ""), str(p.get("erstes") or ""),
                     "ja" if p.get("verschleiss") else "", W.anzeigen(W.lesen(p.get("zuletzt", ""))),
                     W.anzeigen(f_), p.get("quelle", "")]
            for j, w in enumerate(werte):
                it = _item(w, editierbar=j <= 5)
                if j == 6 and f_ and f_ <= self.heute:
                    it.setBackground(ROT)
                self.tabelle.setItem(i, j, it)
        if self.daten:
            faellig = W.faellige(self.daten, self.heute)
            vt = W.verschleissteile(self.daten)
            self.zusammenfassung.setText(
                (f"<b>{len(faellig)} fällig</b>: " + ", ".join(p["bauteil"] for p in faellig) if faellig
                 else "<b>Nichts fällig.</b>") + f" · Verschleißteile: {', '.join(p['bauteil'] for p in vt)}")
        else:
            self.zusammenfassung.setText("")
        self._fuellt = False
        if 0 <= zeile < self.tabelle.rowCount():
            self.tabelle.selectRow(zeile)

    def speichern_(self) -> dict | None:
        if self.wid is None or self.daten is None:
            return None
        o = self.projekt.wartungsplan_speichern(self.wid, self.daten)
        self.status.setText(f"{o['nr']} · Version {o['version']} · {o['status']}")
        self.meldung.emit(f"Wartungsplan {o['nr']} gespeichert.", False)
        self.gespeichert.emit()
        return o

    def pdf(self, ziel: str | None = None) -> Path | None:
        if self.wid is None:
            return None
        o = self.projekt.wartungsplan(self.wid)
        o["daten"] = self.daten
        if ziel is None:
            ziel, _ = QFileDialog.getSaveFileName(self, "Wartungsplan speichern", f"Wartungsplan_{o['nr']}.pdf",
                                                  "PDF (*.pdf)")
            if not ziel:
                return None
        from ..pdf import wartungsplan_erstellen
        pfad = wartungsplan_erstellen(o, ziel, self.projekt.name, self.heute)
        self.meldung.emit(f"Wartungsplan gespeichert: {Path(pfad).name}", False)
        return Path(pfad)
