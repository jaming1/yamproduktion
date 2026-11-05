"""Seiten „Aufgaben & Zeitplan“ und „Kosten Plan/Ist“ (MS13): Aufgaben, Meilensteine, Gantt, Fortschritt je Phase,
Kostenübersicht."""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPalette, QPen, QPolygonF
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFileDialog, QGridLayout, QHBoxLayout, QLabel, QProgressBar, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..betrieb.wartung import anzeigen, lesen
from ..modell import OBJEKTE, PHASEN, Projekt, ProjektFehler
from ..planung import kosten as K, zeitplan as Z
from .betrieb_seiten import _item, _knopf
from .kosten_seite import euro
from .qualitaet_seiten import AMPEL, _Auswahl, _klein, _kopf_breiten, _tabelle
from .seiten import karte, scrollbar, titel

FARBE_STAND = {"offen": QColor(120, 140, 170), "in Arbeit": QColor(37, 110, 200), "erledigt": QColor(46, 160, 67)}
ROT = QColor(218, 54, 51)


# ================================================================ Gantt
class Gantt(QWidget):
    """Zeitplan als Balken je Aufgabe, Raute je Meilenstein, rote Linie = heute (S17)."""
    ZEILE, KOPF, LINKS = 24, 40, 300

    def __init__(self):
        super().__init__()
        self.aufgaben: list[dict] = []
        self.heute = date.today()
        self.setMinimumHeight(120)

    def setze(self, aufgaben: list[dict], heute: date | None = None):
        self.aufgaben = [a for a in aufgaben if Z.zeitraum(a)[1]]
        self.heute = heute or self.heute
        self.setMinimumHeight(self.KOPF + self.ZEILE * max(len(self.aufgaben), 1) + 12)
        self.update()

    def _bereich(self) -> tuple[date, date]:
        z = Z.gesamt_zeitraum(self.aufgaben) or (self.heute, self.heute + timedelta(days=30))
        a = min(z[0], self.heute) - timedelta(days=3)
        b = max(z[1], self.heute) + timedelta(days=7)
        return a, b

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        text = self.palette().windowText().color()
        gitter = QColor(text)
        gitter.setAlpha(40)
        breite = self.width() - self.LINKS - 12
        if not self.aufgaben:
            p.setPen(text)
            p.drawText(self.rect(), Qt.AlignCenter, "Noch keine Aufgaben mit Termin.")
            return
        a, b = self._bereich()
        tage = max((b - a).days, 1)

        def x(d: date) -> float:
            return self.LINKS + (d - a).days / tage * breite

        unten = self.KOPF + self.ZEILE * len(self.aufgaben)
        # Monate oben, Wochen als Gitter
        d = date(a.year, a.month, 1)
        p.setFont(self.font())
        while d <= b:
            if d >= a:
                p.setPen(QPen(gitter, 1))
                p.drawLine(QPointF(x(d), 18), QPointF(x(d), unten))
                p.setPen(text)
                p.drawText(QPointF(x(d) + 4, 16), d.strftime("%m.%Y"))
            d = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
        wochen = a + timedelta(days=(7 - a.weekday()) % 7)
        stift = QPen(gitter, 1, Qt.DotLine)
        while wochen <= b and tage < 400:
            p.setPen(stift)
            p.drawLine(QPointF(x(wochen), 24), QPointF(x(wochen), unten))
            wochen += timedelta(days=7)
        fm = p.fontMetrics()
        for i, auf in enumerate(self.aufgaben):
            y = self.KOPF + i * self.ZEILE
            if i % 2 == 0:
                p.fillRect(QRectF(0, y, self.width(), self.ZEILE), QColor(text.red(), text.green(), text.blue(), 12))
            p.setPen(text)
            name = f"{auf['phase'] or '–'}  {auf['titel']}"
            p.drawText(QRectF(6, y, self.LINKS - 12, self.ZEILE), Qt.AlignVCenter | Qt.AlignLeft,
                       fm.elidedText(name, Qt.ElideRight, self.LINKS - 12))
            beginn, ende = Z.zeitraum(auf)
            farbe = FARBE_STAND.get(auf.get("stand"), FARBE_STAND["offen"])
            zu_spaet = Z.verzug(auf, self.heute) > 0
            if auf.get("meilenstein"):
                m, h = x(ende), self.ZEILE / 2 - 4
                raute = QPolygonF([QPointF(m, y + 4), QPointF(m + h, y + self.ZEILE / 2), QPointF(m, y + self.ZEILE - 4),
                                   QPointF(m - h, y + self.ZEILE / 2)])
                p.setPen(QPen(ROT if zu_spaet else farbe.darker(130), 2 if zu_spaet else 1))
                p.setBrush(farbe)
                p.drawPolygon(raute)
                p.setPen(text)
                p.drawText(QPointF(m + h + 4, y + self.ZEILE / 2 + fm.ascent() / 2 - 1), anzeigen(ende)[:5])
            else:
                r = QRectF(x(beginn), y + 5, max(x(ende + timedelta(days=1)) - x(beginn), 3), self.ZEILE - 10)
                p.setPen(QPen(ROT, 2) if zu_spaet else Qt.NoPen)
                p.setBrush(QBrush(farbe))
                p.drawRoundedRect(r, 3, 3)
        if a <= self.heute <= b:
            p.setPen(QPen(ROT, 1.5, Qt.DashLine))
            p.drawLine(QPointF(x(self.heute), 20), QPointF(x(self.heute), unten))
            p.drawText(QPointF(x(self.heute) + 3, 32), "heute")

    def als_png(self, breite: int = 1600) -> bytes:
        """Bild für das PDF, immer hell."""
        w = Gantt()
        pal = QPalette()
        pal.setColor(QPalette.Window, QColor(255, 255, 255))
        pal.setColor(QPalette.WindowText, QColor(30, 30, 30))
        w.setPalette(pal)
        w.setAutoFillBackground(True)
        w.setze(self.aufgaben, self.heute)
        w.resize(breite, w.minimumHeight())
        daten = QByteArray()
        puffer = QBuffer(daten)
        puffer.open(QIODevice.WriteOnly)
        w.grab().save(puffer, "PNG")
        w.deleteLater()
        return bytes(daten)


# ================================================================ Aufgaben & Zeitplan
SPALTEN_A = [("nr", "Nr", 92), ("titel", "Aufgabe", 0), ("phase", "Phase", 60), ("verantwortlich", "Wer", 80),
             ("start", "Start", 100), ("termin", "Termin", 100), ("stand", "Stand", 90),
             ("kosten_plan", "Plan €", 84), ("kosten_ist", "Ist €", 84), ("objekt", "Objekt", 70),
             ("notiz", "Notiz", 110)]


def _objekt_nr(projekt: Projekt, a: dict) -> str:
    if a.get("objekt_typ") and a.get("objekt_id"):
        try:
            return projekt.objekt(a["objekt_typ"], a["objekt_id"])["nr"]
        except (ProjektFehler, TypeError, KeyError):
            return "?"
    return ""


def _objekt_suchen(projekt: Projekt, nr: str) -> tuple[str, int] | None:
    praefix = nr.split("-")[0].upper()
    for typ, info in OBJEKTE.items():
        if info[0] == praefix:
            z = projekt._db.execute(f"SELECT id FROM {typ} WHERE nr=?", (nr.upper(),)).fetchone()
            if z:
                return typ, z[0]
    if praefix == "A":
        a = next((x for x in projekt.anforderungen() if x.nr == nr.upper()), None)
        if a:
            return "anforderung", a.id
    if praefix == "B":
        b = next((x for x in projekt.berechnungen() if x.nr == nr.upper()), None)
        if b:
            return "berechnung", b.id
    return None


class AufgabenSeite(QWidget):
    meldung = Signal(str, bool)
    gespeichert = Signal()
    gehe_zu_objekt = Signal(str, int)

    def __init__(self):
        super().__init__()
        self.projekt: Projekt | None = None
        self.liste: list[dict] = []
        self.heute = date.today()
        self._fuellt = False
        inhalt = QWidget()
        lay = QVBoxLayout(inhalt)
        lay.setContentsMargins(32, 24, 32, 24)
        lay.addWidget(titel("Aufgaben & Zeitplan", "Aufgaben und Meilensteine mit Verantwortlichem, Termin, Stand und "
                                                   "Phase; Zeitplan als Gantt und Fortschritt je Phase."))
        # Fortschritt je Phase (M49)
        k, kl = karte()
        a_ = QLabel("Fortschritt je Phase")
        a_.setObjectName("Abschnitt")
        kl.addWidget(a_)
        raster = QGridLayout()
        raster.setHorizontalSpacing(16)
        self.balken: dict[str, QProgressBar] = {}
        for i, (nr, name) in enumerate(PHASEN):
            zelle = QVBoxLayout()
            zelle.addWidget(_klein(f"{nr} {name}"))
            b = QProgressBar()
            b.setRange(0, 100)
            b.setTextVisible(True)
            b.setFormat("%p %")
            self.balken[nr] = b
            zelle.addWidget(b)
            raster.addLayout(zelle, i // 3, i % 3)
        kl.addLayout(raster)
        self.meilensteine = QLabel()
        self.meilensteine.setWordWrap(True)
        kl.addWidget(self.meilensteine)
        lay.addWidget(k)
        # Tabelle (M48)
        k, kl = karte()
        z = QHBoxLayout()
        self.filter = QComboBox()
        self.filter.addItem("Alle Phasen", "")
        for nr, name in PHASEN:
            self.filter.addItem(f"{nr} {name}", nr)
        self.filter.setMinimumContentsLength(14)
        self.filter.currentIndexChanged.connect(lambda _: self._anzeigen())
        z.addWidget(self.filter)
        z.addStretch()
        self.vorlage = _knopf("Vorlage", lambda: self.aus_vorlage(),
                              tipp="Aufgaben und Meilensteine der Kleinwindanlage ab heute (Dauern sind Schätzwerte)")
        z.addWidget(self.vorlage)
        z.addWidget(_knopf("+ Aufgabe", lambda: self.neu()))
        z.addWidget(_knopf("+ Meilenstein", lambda: self.neu(meilenstein=True)))
        z.addWidget(_knopf("Zum Objekt", lambda: self.zum_objekt()))
        z.addWidget(_knopf("Löschen", lambda: self.loeschen()))
        z.addWidget(_knopf("PDF …", lambda: self.pdf(), tipp="Zeitplan mit Gantt und Aufgabenliste als PDF"))
        kl.addLayout(z)
        self.tabelle = _tabelle([t for _, t, _ in SPALTEN_A])
        self.tabelle.setMinimumHeight(300)
        _kopf_breiten(self.tabelle, [b for _, _, b in SPALTEN_A], 1)
        self.tabelle.setItemDelegateForColumn(2, _Auswahl(tuple(nr for nr, _ in PHASEN), self.tabelle))
        self.tabelle.setItemDelegateForColumn(6, _Auswahl(Z.STAENDE, self.tabelle))
        self.tabelle.itemChanged.connect(self._zelle)
        kl.addWidget(self.tabelle)
        self.zusammenfassung = QLabel()
        self.zusammenfassung.setWordWrap(True)
        kl.addWidget(self.zusammenfassung)
        lay.addWidget(k)
        # Gantt (S17)
        k, kl = karte()
        a_ = QLabel("Zeitplan")
        a_.setObjectName("Abschnitt")
        kl.addWidget(a_)
        self.gantt = Gantt()
        kl.addWidget(self.gantt)
        kl.addWidget(_klein("Balken grau = offen, blau = in Arbeit, grün = erledigt; rot umrandet = Termin überschritten; "
                            "◆ = Meilenstein. " + Z.HINWEIS))
        lay.addWidget(k)
        lay.addStretch()
        aussen = QVBoxLayout(self)
        aussen.setContentsMargins(0, 0, 0, 0)
        aussen.addWidget(scrollbar(inhalt))

    def setze_projekt(self, projekt: Projekt):
        self.projekt = projekt
        self.laden()

    def laden(self):
        if not self.projekt:
            return
        self.liste = self.projekt.aufgaben()
        self._anzeigen()

    def aus_vorlage(self, start: str = "") -> list[dict]:
        if self.projekt.aufgaben():
            self.meldung.emit("Es gibt schon Aufgaben – die Vorlage wird nur in ein leeres Projekt übernommen.", True)
            return []
        neu = self.projekt.zeitplan_vorlage(start or self.heute.isoformat())
        self.laden()
        self.meldung.emit(f"{len(neu)} Aufgaben und Meilensteine aus der Vorlage angelegt (Dauern geschätzt).", False)
        self.gespeichert.emit()
        return neu

    def _sichtbar(self) -> list[dict]:
        f = self.filter.currentData()
        return [a for a in self.liste if not f or a["phase"] == f]

    def neu(self, titel_: str = "", meilenstein: bool = False, **felder) -> dict | None:
        if not self.projekt:
            return None
        phase = self.filter.currentData() or felder.pop("phase", "")
        termin = felder.pop("termin", (self.heute + timedelta(days=14)).isoformat())
        start = "" if meilenstein else felder.pop("start", self.heute.isoformat())
        a = self.projekt.aufgabe_neu(titel_ or ("Neuer Meilenstein" if meilenstein else "Neue Aufgabe"),
                                     phase=phase, start=start, termin=termin, meilenstein=int(meilenstein), **felder)
        self.laden()
        zeile = next(i for i, x in enumerate(self._sichtbar()) if x["id"] == a["id"])
        self.tabelle.selectRow(zeile)
        self.gespeichert.emit()
        return a

    def _gewaehlt(self, zeile: int | None = None) -> dict | None:
        i = self.tabelle.currentRow() if zeile is None else zeile
        s = self._sichtbar()
        return s[i] if 0 <= i < len(s) else None

    def loeschen(self, zeile: int | None = None):
        a = self._gewaehlt(zeile)
        if a:
            self.projekt.objekt_loeschen("aufgabe", a["id"])
            self.laden()
            self.meldung.emit(f"{a['nr']} gelöscht.", False)
            self.gespeichert.emit()

    def zum_objekt(self):
        a = self._gewaehlt()
        if a and a.get("objekt_typ") and a.get("objekt_id"):
            self.gehe_zu_objekt.emit(a["objekt_typ"], a["objekt_id"])
        else:
            self.meldung.emit("Die gewählte Aufgabe ist mit keinem Objekt verknüpft (Spalte Objekt, z. B. T-001).",
                              True)

    def setze(self, zeile: int, key: str, wert: str):
        j = next(i for i, (k, _, _) in enumerate(SPALTEN_A) if k == key)
        self.tabelle.item(zeile, j).setText(wert)

    def _zelle(self, item: QTableWidgetItem):
        if self._fuellt:
            return
        a = self._gewaehlt(item.row())
        key, t = SPALTEN_A[item.column()][0], item.text().strip()
        try:
            if key in ("kosten_plan", "kosten_ist"):
                x = K.zahl(t)
                if t and x is None:
                    raise ProjektFehler("Kosten bitte als Zahl in Euro eingeben.")
                felder = {key: x}
            elif key == "objekt":
                ziel = _objekt_suchen(self.projekt, t) if t else ("", None)
                if ziel is None:
                    raise ProjektFehler(f"Objekt {t} gibt es nicht.")
                felder = {"objekt_typ": ziel[0], "objekt_id": ziel[1]}
            elif key == "start" and a["meilenstein"]:
                felder = {}
            else:
                felder = {key: t}
            if felder:
                self.projekt.aufgabe_aendern(a["id"], **felder)
                self.gespeichert.emit()
        except ProjektFehler as exc:
            self.meldung.emit(str(exc), True)
        self.laden()

    def _anzeigen(self):
        zeile = self.tabelle.currentRow()
        self._fuellt = True
        sichtbar = self._sichtbar()
        self.vorlage.setEnabled(bool(self.projekt) and not self.liste)
        self.tabelle.setRowCount(len(sichtbar))
        for i, a in enumerate(sichtbar):
            zu_spaet = Z.verzug(a, self.heute)
            werte = {"nr": a["nr"] + (" ◆" if a["meilenstein"] else ""), "titel": a["titel"], "phase": a["phase"],
                     "verantwortlich": a["verantwortlich"], "start": "" if a["meilenstein"] else anzeigen(lesen(a["start"])),
                     "termin": anzeigen(lesen(a["termin"])), "stand": a["stand"],
                     "kosten_plan": euro(a["kosten_plan"]) if a["kosten_plan"] is not None else "",
                     "kosten_ist": euro(a["kosten_ist"]) if a["kosten_ist"] is not None else "",
                     "objekt": _objekt_nr(self.projekt, a), "notiz": a["notiz"]}
            for j, (k, _, _) in enumerate(SPALTEN_A):
                it = _item(werte[k], editierbar=k != "nr" and not (k == "start" and a["meilenstein"]))
                if k == "termin" and zu_spaet:
                    it.setBackground(AMPEL["rot"])
                    it.setToolTip(f"{zu_spaet} Tage überfällig")
                if k == "stand":
                    it.setBackground({"erledigt": AMPEL["gruen"], "in Arbeit": AMPEL["gelb"]}.get(a["stand"],
                                                                                                 AMPEL["grau"]))
                self.tabelle.setItem(i, j, it)
        self._fuellt = False
        if 0 <= zeile < self.tabelle.rowCount():
            self.tabelle.selectRow(zeile)
        self.gantt.setze(sichtbar, self.heute)
        if not self.projekt:
            return
        for nr, b in self.balken.items():
            f = self.projekt.phase_fortschritt(nr)
            b.setValue(f["prozent"])
            b.setToolTip(f"{f['erledigt']} von {f['gesamt']} erledigt / geprüft")
        offen = [a for a in self.liste if a["stand"] != "erledigt"]
        spaet = [a for a in offen if Z.verzug(a, self.heute)]
        self.zusammenfassung.setText(
            f"<b>{len(self.liste)} Einträge</b> · {len(offen)} offen · "
            + (f"<span style='color:#d13b2f'><b>{len(spaet)} überfällig</b></span>" if spaet else "nichts überfällig"))
        ms = [a for a in self.liste if a["meilenstein"]]
        naechster = next((a for a in sorted(ms, key=lambda a: a["termin"]) if a["stand"] != "erledigt"), None)
        erreicht = sum(a["stand"] == "erledigt" for a in ms)
        self.meilensteine.setText(
            f"Meilensteine: {erreicht} von {len(ms)} erreicht"
            + (f" · nächster: <b>{naechster['titel']}</b> am {anzeigen(lesen(naechster['termin']))}" if naechster else ""))

    def pdf(self, ziel: str | None = None) -> Path | None:
        if not self.projekt:
            return None
        if ziel is None:
            ziel, _ = QFileDialog.getSaveFileName(self, "Zeitplan speichern",
                                                  str(self.projekt.pfad.parent / f"Zeitplan_{self.projekt.name}.pdf"),
                                                  "PDF (*.pdf)")
            if not ziel:
                return None
        from ..pdf import zeitplan_erstellen
        fortschritt = [(nr, name, self.projekt.phase_fortschritt(nr)["prozent"]) for nr, name in PHASEN]
        g = Gantt()
        g.setze(self.liste, self.heute)
        pfad = zeitplan_erstellen(self.liste, g.als_png(), fortschritt, ziel, self.projekt.name, self.heute,
                                  {a["id"]: _objekt_nr(self.projekt, a) for a in self.liste})
        g.deleteLater()
        self.meldung.emit(f"Zeitplan gespeichert: {Path(pfad).name}", False)
        return Path(pfad)


# ================================================================ Kosten Plan/Ist (S18)
SPALTEN_K = [("id", "Nr", 56), ("kostenart", "Kostenart", 190), ("text", "Posten", 0), ("plan", "Plan €", 110),
             ("ist", "Ist €", 110), ("quelle", "Quelle", 230)]


class BudgetSeite(QWidget):
    meldung = Signal(str, bool)
    gespeichert = Signal()

    def __init__(self):
        super().__init__()
        self.projekt: Projekt | None = None
        self.posten: list[dict] = []
        self._fuellt = False
        inhalt = QWidget()
        lay = QVBoxLayout(inhalt)
        lay.setContentsMargins(32, 24, 32, 24)
        lay.addWidget(titel("Kosten Plan/Ist", "Geplante und tatsächliche Kosten des Produkts je Kostenart – Plan aus "
                                               "der Kalkulation, Ist aus den Rechnungen."))
        k, kl = karte()
        a_ = QLabel("Übersicht")
        a_.setObjectName("Abschnitt")
        kl.addWidget(a_)
        self.uebersicht = _tabelle(["Kostenart", "Plan", "Ist", "Abweichung", "Ist/Plan"])
        self.uebersicht.setMinimumHeight(240)
        _kopf_breiten(self.uebersicht, [0, 140, 140, 140, 110], 0)
        self.uebersicht.setEditTriggers(QAbstractItemView.NoEditTriggers)
        kl.addWidget(self.uebersicht)
        lay.addWidget(k)
        k, kl = karte()
        z = QHBoxLayout()
        a_ = QLabel("Posten")
        a_.setObjectName("Abschnitt")
        z.addWidget(a_)
        z.addStretch()
        z.addWidget(_knopf("Plan aus Kalkulation", lambda: self.aus_kalkulation(),
                           tipp="Herstellkosten je Baugruppe (Bauteile, Zukaufteile) aus „Kosten & Anfragen“"))
        z.addWidget(_knopf("+ Posten", lambda: self.neu()))
        z.addWidget(_knopf("Löschen", lambda: self.loeschen()))
        z.addWidget(_knopf("PDF …", lambda: self.pdf()))
        kl.addLayout(z)
        self.tabelle = _tabelle([t for _, t, _ in SPALTEN_K])
        self.tabelle.setMinimumHeight(300)
        _kopf_breiten(self.tabelle, [b or 200 for _, _, b in SPALTEN_K], 2)
        self.tabelle.setItemDelegateForColumn(1, _Auswahl(K.KOSTENARTEN, self.tabelle))
        self.tabelle.itemChanged.connect(self._zelle)
        kl.addWidget(self.tabelle)
        kl.addWidget(_klein("Kosten der Aufgaben (Spalten Plan €/Ist € auf „Aufgaben & Zeitplan“) zählen als eigene "
                            "Kostenart „Aufgaben“. " + K.HINWEIS))
        lay.addWidget(k)
        lay.addStretch()
        aussen = QVBoxLayout(self)
        aussen.setContentsMargins(0, 0, 0, 0)
        aussen.addWidget(scrollbar(inhalt))

    def setze_projekt(self, projekt: Projekt):
        self.projekt = projekt
        self.laden()

    def laden(self):
        if not self.projekt:
            return
        self.posten = self.projekt.kosten_posten()
        self._anzeigen()

    def _speichern(self):
        self.projekt.kosten_speichern(self.posten)
        self.gespeichert.emit()

    def aus_kalkulation(self) -> int:
        try:
            self.posten, n = self.projekt.kosten_aus_kalkulation()
        except ProjektFehler as exc:
            self.meldung.emit(str(exc), True)
            return 0
        self._anzeigen()
        self.meldung.emit(f"{n} Plan-Posten aus der Kalkulation übernommen." if n else
                          "Keine Baugruppe mit Kalkulation gefunden.", not n)
        return n

    def neu(self, kostenart: str = "Sonstiges", text: str = "Neuer Posten", plan=None, ist=None) -> dict:
        p = K.posten_neu(self.posten, kostenart, text, plan, ist)
        self._speichern()
        self._anzeigen()
        self.tabelle.selectRow(len(self.posten) - 1)
        return p

    def loeschen(self, zeile: int | None = None):
        i = self.tabelle.currentRow() if zeile is None else zeile
        if 0 <= i < len(self.posten):
            self.posten.pop(i)
            self._speichern()
            self._anzeigen()

    def setze(self, zeile: int, key: str, wert: str):
        j = next(i for i, (k, _, _) in enumerate(SPALTEN_K) if k == key)
        self.tabelle.item(zeile, j).setText(wert)

    def _zelle(self, item: QTableWidgetItem):
        if self._fuellt:
            return
        p = self.posten[item.row()]
        key, t = SPALTEN_K[item.column()][0], item.text().strip()
        if key in ("plan", "ist"):
            x = K.zahl(t)
            if t and x is None:
                self.meldung.emit("Betrag bitte als Zahl in Euro eingeben.", True)
            else:
                p[key] = x
        else:
            p[key] = t
        self._speichern()
        self._anzeigen()

    def _anzeigen(self):
        self._fuellt = True
        self.tabelle.setRowCount(len(self.posten))
        for i, p in enumerate(self.posten):
            for j, (k, _, _) in enumerate(SPALTEN_K):
                w = p.get(k)
                text = euro(w) if k in ("plan", "ist") and w is not None else ("" if w is None else str(w))
                it = _item(text, editierbar=k != "id")
                if k in ("plan", "ist"):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.tabelle.setItem(i, j, it)
        self._fuellt = False
        if not self.projekt:
            return
        zeilen = self.projekt.kosten_uebersicht(self.posten)
        self.uebersicht.setRowCount(len(zeilen))
        for i, z in enumerate(zeilen):
            werte = [z["kostenart"], euro(z["plan"]), euro(z["ist"]), ("+" if z["abweichung"] > 0 else "")
                     + euro(z["abweichung"]), f"{z['anteil'] * 100:.0f} %" if z["anteil"] is not None else "–"]
            for j, w in enumerate(werte):
                it = _item(w)
                if j:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if j == 3 and z["ueber"]:
                    it.setBackground(AMPEL["rot"])
                if z["kostenart"] == "Summe":
                    f = it.font()
                    f.setBold(True)
                    it.setFont(f)
                self.uebersicht.setItem(i, j, it)

    def pdf(self, ziel: str | None = None) -> Path | None:
        if not self.projekt:
            return None
        if ziel is None:
            ziel, _ = QFileDialog.getSaveFileName(self, "Kostenübersicht speichern",
                                                  str(self.projekt.pfad.parent / "Kosten_Plan_Ist.pdf"), "PDF (*.pdf)")
            if not ziel:
                return None
        from ..pdf import kostenuebersicht_erstellen
        pfad = kostenuebersicht_erstellen(self.posten, self.projekt.kosten_uebersicht(self.posten),
                                          self.projekt.aufgaben(), ziel, self.projekt.name)
        self.meldung.emit(f"Kostenübersicht gespeichert: {Path(pfad).name}", False)
        return Path(pfad)
