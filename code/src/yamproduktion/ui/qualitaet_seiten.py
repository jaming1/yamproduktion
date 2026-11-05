"""Seiten „Qualität & Sicherheit“ (MS12): Prüfpläne, FMEA, Abweichungen, Risikobeurteilung, Normen,
Technische Dokumentation."""
from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QStyledItemDelegate,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..betrieb import inbetriebnahme as IB, wartung as W
from ..modell import NEU_PRUEFEN, Projekt, ProjektFehler
from ..qualitaet import pruefplan as PP, tabellen as Q
from .betrieb_seiten import _item, _knopf, _spalten
from .seiten import karte, scrollbar, titel

AMPEL = {Q.GRUEN: QColor(46, 160, 67, 70), Q.GELB: QColor(230, 170, 30, 80), Q.ROT: QColor(218, 54, 51, 80),
         Q.GRAU: QColor(128, 128, 128, 40)}
ERG_FARBE = {IB.IO: AMPEL[Q.GRUEN], IB.NIO: AMPEL[Q.ROT]}


def _klein(text: str = "") -> QLabel:
    l_ = QLabel(text)
    l_.setObjectName("Klein")
    l_.setWordWrap(True)
    return l_


def _tabelle(spalten: list[str]) -> QTableWidget:
    t = QTableWidget(0, len(spalten))
    t.setHorizontalHeaderLabels(spalten)
    t.verticalHeader().hide()
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setWordWrap(True)
    t.setMinimumHeight(430)
    return t


def _kopf_breiten(t: QTableWidget, breiten: list[int], dehnen: int):
    """Spaltenbreiten so, dass die Überschrift nie abgeschnitten wird."""
    fm = t.horizontalHeader().fontMetrics()
    breiten = [max(b, fm.horizontalAdvance(t.horizontalHeaderItem(i).text()) + 30) if b else 0
               for i, b in enumerate(breiten)]
    _spalten(t, breiten, dehnen)


class _Auswahl(QStyledItemDelegate):
    """Auswahlliste in einer Tabellenzelle (Bewertung 1–10, Status, Lebensphase …)."""

    def __init__(self, wahl: tuple, parent=None):
        super().__init__(parent)
        self.wahl = wahl

    def createEditor(self, parent, option, index):
        c = QComboBox(parent)
        c.addItems([w or "–" for w in self.wahl])
        return c

    def setEditorData(self, editor, index):
        text = index.data() or ""
        i = editor.findText(text or "–")
        editor.setCurrentIndex(max(i, 0))

    def setModelData(self, editor, model, index):
        text = editor.currentText()
        model.setData(index, "" if text == "–" else text)


# ================================================================ FMEA, Risiko, Normen, Abweichungen
class TabellenSeite(QWidget):
    meldung = Signal(str, bool)
    gespeichert = Signal()

    UNTERTITEL = {
        "fmea": "Konstruktions- und Prozess-FMEA: Fehlerart, Folge, Ursache, Bewertung B·A·E, Maßnahme und "
                "Neubewertung. Vorlage Kleinwindanlage mit Nachweisen aus den Berechnungen.",
        "risiko": "Risikobeurteilung nach EN ISO 12100 für die Maschinenverordnung (EU) 2023/1230: Gefährdung, "
                  "Risiko, Schutzmaßnahme, Restrisiko.",
        "normen": "Relevante Normen und Regeln für das Produkt mit Status und Nachweis im Projekt.",
        "abweichung": "Abweichungen und Fehler mit Ursache, Maßnahme und Prüfung der Wirksamkeit.",
    }

    def __init__(self, typ: str):
        super().__init__()
        self.typ = typ
        self.art = Q.ART[typ]
        self.projekt: Projekt | None = None
        self.did: int | None = None
        self.daten: dict | None = None
        self._fuellt = False
        inhalt = QWidget()
        lay = QVBoxLayout(inhalt)
        lay.setContentsMargins(32, 24, 32, 24)
        lay.addWidget(titel(self.art.titel, self.UNTERTITEL[typ]))
        k, kl = karte()
        z = QHBoxLayout()
        self.wahl = QComboBox()
        self.wahl.setMinimumContentsLength(22)
        self.wahl.activated.connect(lambda _: self.laden_id(self.wahl.currentData()))
        z.addWidget(self.wahl, 2)
        if typ == "fmea":
            for unterart in self.art.arten:
                z.addWidget(_knopf(f"Neue {unterart}", lambda u=unterart: self.neu(u),
                                   tipp="Vorlage Kleinwindanlage mit Nachweisen aus dem Projekt"))
        else:
            z.addWidget(_knopf("Neu" if typ == "abweichung" else "Neu aus Vorlage", lambda: self.neu(),
                               tipp="" if typ == "abweichung" else "Vorlage Kleinwindanlage"))
        self.speichern = _knopf("Speichern", self.speichern_, haupt=True)
        self.speichern.setShortcut("Ctrl+S")
        z.addWidget(self.speichern)
        z.addWidget(_knopf("PDF …", lambda: self.pdf()))
        kl.addLayout(z)
        if typ == "risiko":
            form = QFormLayout()
            self.grenzen = {}
            for key, text in (("verwendung", "Bestimmungsgemäße Verwendung"),
                              ("fehlanwendung", "Vorhersehbare Fehlanwendung"), ("lebensdauer", "Lebensdauer")):
                e = QLineEdit()
                e.editingFinished.connect(lambda key=key, e=e: self._grenze(key, e.text()))
                self.grenzen[key] = e
                form.addRow(text, e)
            kl.addLayout(form)
        z = QHBoxLayout()
        self.status = _klein()
        z.addWidget(self.status, 1)
        if typ == "normen":
            z.addWidget(_knopf("Nachweise abgleichen", lambda: self.abgleichen(),
                               tipp="Neue Berechnungen, Risikobeurteilung, Prüfpläne als Nachweis eintragen"))
        if typ == "abweichung":
            z.addWidget(_knopf("n. i. O. übernehmen", lambda: self.uebernehmen(),
                               tipp="Fehler aus Prüfplänen und Inbetriebnahme übernehmen"))
        z.addWidget(_knopf("+ Zeile", lambda: self.zeile_neu()))
        z.addWidget(_knopf("Löschen", lambda: self.zeile_loeschen()))
        kl.addLayout(z)
        sp = self.art.spalten
        self.tabelle = _tabelle([s.titel for s in sp])
        for i, s in enumerate(sp):
            if s.tipp:
                self.tabelle.horizontalHeaderItem(i).setToolTip(s.tipp)
            if s.art == "wahl":
                self.tabelle.setItemDelegateForColumn(i, _Auswahl(s.wahl, self.tabelle))
        dehnen = next(i for i, s in enumerate(sp) if s.breite == 0)
        _kopf_breiten(self.tabelle, [s.breite or 120 for s in sp], dehnen)
        self.tabelle.horizontalHeader().setStretchLastSection(True)
        self.tabelle.itemChanged.connect(self._zelle)
        kl.addWidget(self.tabelle)
        self.zusammenfassung = QLabel()
        self.zusammenfassung.setWordWrap(True)
        kl.addWidget(self.zusammenfassung)
        kl.addWidget(_klein(self.art.hinweis))
        lay.addWidget(k)
        lay.addStretch()
        aussen = QVBoxLayout(self)
        aussen.setContentsMargins(0, 0, 0, 0)
        aussen.addWidget(scrollbar(inhalt))

    # ---------- Laden
    def setze_projekt(self, projekt: Projekt):
        self.projekt = projekt
        self.did = None
        self.laden()

    def laden(self):
        if not self.projekt:
            return
        liste = self.projekt.qdoks(self.typ)
        self.wahl.clear()
        for o in liste:
            self.wahl.addItem(f"{o['nr']} {o['name']}" + (" ⚠" if o["status"] == NEU_PRUEFEN else ""), o["id"])
        if not liste:
            self.did, self.daten = None, None
            self.status.setText("Noch nichts angelegt – oben eine neue Liste anlegen.")
            self._anzeigen()
            return
        self.laden_id(self.did if self.did in [o["id"] for o in liste] else liste[-1]["id"])

    def laden_id(self, did):
        if did is None:
            return
        o = self.projekt.qdok(self.typ, did)
        self.did, self.daten = did, o["daten"]
        self.wahl.setCurrentIndex(max(0, self.wahl.findData(did)))
        text = f"{o['nr']} · Version {o['version']} · {o['status']}"
        if o["status"] == NEU_PRUEFEN:
            text += " – eine Berechnung, auf die sich die Liste stützt, hat sich geändert: Bewertung prüfen."
        self.status.setText(text)
        self._anzeigen()

    def neu(self, unterart: str = "") -> dict:
        o = self.projekt.qdok_neu(self.typ, unterart)
        self.did = o["id"]
        self.laden()
        self.meldung.emit(f"{o['name']} {o['nr']} angelegt.", False)
        return o

    # ---------- Bearbeiten
    def _grenze(self, key: str, text: str):
        if self.daten is not None and not self._fuellt:
            self.daten.setdefault("grenzen", {})[key] = text.strip()

    def _zelle(self, item: QTableWidgetItem):
        if self._fuellt or self.daten is None:
            return
        s = self.art.spalten[item.column()]
        if s.art == "berechnet" or s.key == "id":
            return
        self.daten["zeilen"][item.row()][s.key] = item.text().strip()
        self._anzeigen()

    def setze(self, zeile: int, key: str, wert: str):
        """Wert setzen wie in der Tabelle (für Tests und Tastatur)."""
        j = next(i for i, s in enumerate(self.art.spalten) if s.key == key)
        self.tabelle.item(zeile, j).setText(wert)

    def zeile_neu(self, **werte) -> dict | None:
        if self.daten is None:
            return None
        z = Q.neue_zeile(self.art, self.daten, **werte)
        if self.typ == "abweichung" and not z.get("datum"):
            from datetime import date
            z["datum"] = W.anzeigen(date.today())
        self.daten["zeilen"].append(z)
        self._anzeigen()
        self.tabelle.selectRow(len(self.daten["zeilen"]) - 1)
        return z

    def zeile_loeschen(self, zeile: int | None = None):
        i = self.tabelle.currentRow() if zeile is None else zeile
        if self.daten is not None and 0 <= i < len(self.daten["zeilen"]):
            self.daten["zeilen"].pop(i)
            self._anzeigen()

    def abgleichen(self) -> int:
        if self.did is None:
            return 0
        self.speichern_(melden=False)
        o, n = self.projekt.normen_abgleichen(self.did)
        self.laden_id(self.did)
        self.meldung.emit(f"{n} Normen mit neuen Nachweisen ergänzt." if n else "Keine neuen Nachweise.", False)
        return n

    def uebernehmen(self) -> int:
        if self.did is None:
            return 0
        self.speichern_(melden=False)
        o, n = self.projekt.abweichungen_uebernehmen(self.did)
        self.laden_id(self.did)
        self.meldung.emit(f"{n} Abweichung(en) aus Prüfplänen und Inbetriebnahme übernommen." if n
                          else "Keine neuen n. i. O.-Punkte gefunden.", False)
        return n

    # ---------- Anzeige
    def _anzeigen(self):
        zeile = self.tabelle.currentRow()
        self._fuellt = True
        d = self.daten or {}
        if self.typ == "risiko":
            for key, e in self.grenzen.items():
                e.setText(d.get("grenzen", {}).get(key, ""))
                e.setEnabled(self.daten is not None)
        zeilen = d.get("zeilen", [])
        sp = self.art.spalten
        self.tabelle.setRowCount(len(zeilen))
        for i, z in enumerate(zeilen):
            text, ampel = self.art.bewerten(z)
            for j, s in enumerate(sp):
                wert = s.fn(z) if s.fn else str(z.get(s.key, "") or "")
                if s.key == "datum" or s.key == "termin":
                    wert = W.anzeigen(W.lesen(wert)) or wert
                it = _item(wert, editierbar=s.art != "berechnet" and s.key != "id")
                if s.key in ("bewertung", "id"):
                    it.setBackground(AMPEL[ampel])
                    if s.key == "id":
                        it.setToolTip(text)
                if s.art in ("zahl", "wahl") and len(s.wahl) and len(s.wahl[-1]) <= 2:
                    it.setTextAlignment(Qt.AlignCenter)
                self.tabelle.setItem(i, j, it)
        self.tabelle.resizeRowsToContents()
        if self.daten is not None:
            n = Q.zaehlen(self.art, self.daten)
            self.zusammenfassung.setText(
                f"<b>{len(zeilen)} Einträge</b> · <span style='color:#d13b2f'>rot {n[Q.ROT]}</span> · "
                f"<span style='color:#c08a00'>gelb {n[Q.GELB]}</span> · "
                f"<span style='color:#2e9a43'>grün {n[Q.GRUEN]}</span>")
        else:
            self.zusammenfassung.setText("")
        self._fuellt = False
        if 0 <= zeile < self.tabelle.rowCount():
            self.tabelle.selectRow(zeile)

    def speichern_(self, melden: bool = True) -> dict | None:
        if self.did is None or self.daten is None:
            return None
        o = self.projekt.qdok_speichern(self.typ, self.did, self.daten)
        self.status.setText(f"{o['nr']} · Version {o['version']} · {o['status']}")
        if melden:
            self.meldung.emit(f"{o['name']} {o['nr']} gespeichert.", False)
        self.gespeichert.emit()
        return o

    def pdf(self, ziel: str | None = None) -> Path | None:
        if self.did is None:
            return None
        o = self.projekt.qdok(self.typ, self.did)
        o["daten"] = self.daten
        if ziel is None:
            ziel, _ = QFileDialog.getSaveFileName(self, f"{self.art.titel} speichern",
                                                  f"{self.art.titel.replace(' ', '_')}_{o['nr']}.pdf", "PDF (*.pdf)")
            if not ziel:
                return None
        from ..pdf import qdok_erstellen
        pfad = qdok_erstellen(self.typ, o, ziel, self.projekt.name)
        self.meldung.emit(f"{self.art.titel} gespeichert: {Path(pfad).name}", False)
        return Path(pfad)


# ================================================================ Prüfpläne
SPALTEN_P = ["Nr", "Merkmal", "Toleranz", "Grenzmaße mm", "Prüfmittel", "Umfang", "Ist", "Ergebnis", "Bemerkung"]


class PruefplanSeite(QWidget):
    meldung = Signal(str, bool)
    gespeichert = Signal()

    def __init__(self):
        super().__init__()
        self.projekt: Projekt | None = None
        self.teil_id: int | None = None
        self.pid: int | None = None
        self.daten: dict | None = None
        self._fuellt = False
        inhalt = QWidget()
        lay = QVBoxLayout(inhalt)
        lay.setContentsMargins(32, 24, 32, 24)
        lay.addWidget(titel("Prüfpläne", "Prüfmerkmale aus der Zeichnung mit Grenzmaßen (ISO 286, ISO 2768-m), "
                                         "Prüfmittel und Prüfprotokoll je Bauteil."))
        k, kl = karte()
        z = QHBoxLayout()
        self.wahl = QComboBox()
        self.wahl.setMinimumContentsLength(24)
        self.wahl.activated.connect(lambda _: self.teil_laden(self.wahl.currentData()))
        z.addWidget(self.wahl, 2)
        self.erzeugen = _knopf("Aus Zeichnung erzeugen", lambda: self.aus_zeichnung(),
                               tipp="Maße und Passmaße der Zeichnung als Prüfmerkmale übernehmen")
        z.addWidget(self.erzeugen)
        self.speichern = _knopf("Speichern", self.speichern_, haupt=True)
        self.speichern.setShortcut("Ctrl+S")
        z.addWidget(self.speichern)
        z.addWidget(_knopf("Prüfprotokoll PDF …", lambda: self.pdf()))
        kl.addLayout(z)
        z = QHBoxLayout()
        self.felder = {}
        for key, text, platz in (("datum", "Datum", "TT.MM.JJJJ"), ("pruefer", "Prüfer", ""), ("los", "Los / Charge", "")):
            z.addWidget(QLabel(text))
            e = QLineEdit()
            e.setPlaceholderText(platz)
            e.setMaximumWidth(170)
            e.editingFinished.connect(lambda key=key, e=e: self._kopf(key, e.text()))
            self.felder[key] = e
            z.addWidget(e)
        z.addStretch()
        z.addWidget(_knopf("+ Merkmal", lambda: self.merkmal_neu()))
        z.addWidget(_knopf("Löschen", lambda: self.merkmal_loeschen()))
        kl.addLayout(z)
        self.status = _klein()
        kl.addWidget(self.status)
        self.tabelle = _tabelle(SPALTEN_P)
        _kopf_breiten(self.tabelle, [52, 90, 100, 150, 175, 110, 76, 80, 0], 8)
        self.tabelle.itemChanged.connect(self._zelle)
        kl.addWidget(self.tabelle)
        self.zusammenfassung = QLabel()
        self.zusammenfassung.setWordWrap(True)
        kl.addWidget(self.zusammenfassung)
        kl.addWidget(_klein(PP.HINWEIS + " Passmaße (z. B. „Ø80 k6“) werden auf der Seite Zeichnungen eingetragen."))
        lay.addWidget(k)
        lay.addStretch()
        aussen = QVBoxLayout(self)
        aussen.setContentsMargins(0, 0, 0, 0)
        aussen.addWidget(scrollbar(inhalt))

    def setze_projekt(self, projekt: Projekt):
        self.projekt = projekt
        self.teil_id = None
        self.laden()

    def laden(self):
        if not self.projekt:
            return
        teile = [t for t in self.projekt.teile() if t["vorlage"] != "montageplatte"]
        self.wahl.clear()
        for t in teile:
            pp = self.projekt.pruefplan_von_teil(t["id"])
            zeichen = "" if not pp else (" ⚠" if pp["status"] == NEU_PRUEFEN else " ✓")
            self.wahl.addItem(f"{t['nr']} {t['name']}{zeichen}", t["id"])
        if not teile:
            self.teil_id, self.pid, self.daten = None, None, None
            self.status.setText("Noch keine Bauteile – zuerst unter Konstruktion ein Bauteil anlegen.")
            self._anzeigen()
            return
        ids = [t["id"] for t in teile]
        self.teil_laden(self.teil_id if self.teil_id in ids else ids[0])

    def teil_laden(self, teil_id):
        if teil_id is None:
            return
        self.teil_id = teil_id
        self.wahl.setCurrentIndex(max(0, self.wahl.findData(teil_id)))
        pp = self.projekt.pruefplan_von_teil(teil_id)
        self.pid, self.daten = (pp["id"], pp["daten"]) if pp else (None, None)
        self.erzeugen.setText("Aus Zeichnung aktualisieren" if pp else "Aus Zeichnung erzeugen")
        if pp:
            text = f"{pp['nr']} · Version {pp['version']} · {pp['status']} · Zeichnung {pp['daten'].get('zeichnung')}"
            if pp["status"] == NEU_PRUEFEN:
                text += " – das Bauteil hat sich geändert: „Aus Zeichnung aktualisieren“."
        else:
            text = "Noch kein Prüfplan für dieses Bauteil – „Aus Zeichnung erzeugen“."
        self.status.setText(text)
        self._anzeigen()

    def aus_zeichnung(self) -> dict | None:
        if self.teil_id is None:
            return None
        try:
            if self.pid is None:
                pp = self.projekt.pruefplan_neu(self.teil_id)
                text = f"Prüfplan {pp['nr']} mit {len(pp['daten']['merkmale'])} Merkmalen angelegt."
            else:
                if self.daten is not None:
                    self.projekt.pruefplan_speichern(self.pid, self.daten)
                pp, neu, weg = self.projekt.pruefplan_aktualisieren(self.pid)
                text = f"Prüfplan {pp['nr']} aktualisiert: {neu} neu, {weg} entfallen, Ist-Werte behalten."
        except ProjektFehler as exc:
            self.meldung.emit(str(exc), True)
            return None
        self.laden()
        self.meldung.emit(text, False)
        self.gespeichert.emit()
        return pp

    def _kopf(self, key: str, text: str):
        if self.daten is None or self._fuellt:
            return
        if key == "datum":
            d = W.lesen(text)
            if d is None and text.strip():
                self.meldung.emit("Datum bitte als TT.MM.JJJJ eingeben.", True)
                return
            text = d.isoformat() if d else ""
        self.daten[key] = text.strip()

    def _zelle(self, item: QTableWidgetItem):
        if self._fuellt or self.daten is None:
            return
        m = self.daten["merkmale"][item.row()]
        j, t = item.column(), item.text().strip()
        if j == 1:
            m["merkmal"] = t
        elif j == 2:
            m["toleranz"] = t
        elif j == 3:
            zahlen = [float(x.replace(",", ".")) for x in re.findall(r"-?\d+(?:[.,]\d+)?", t)]
            if len(zahlen) == 2:
                m["min"], m["max"] = min(zahlen), max(zahlen)
            elif not t:
                m["min"] = m["max"] = None
            else:
                self.meldung.emit("Grenzmaße bitte als „min … max“ eingeben, z. B. 80,002 … 80,021.", True)
        elif j == 4:
            m["pruefmittel"] = t
        elif j == 5:
            m["umfang"] = t
        elif j == 6:
            m["ist"] = t
            m["ergebnis"] = IB.OFFEN
            if m.get("min") is None:      # ohne Grenzmaße zählt die Eingabe „i. O.“ / „n. i. O.“
                m["ergebnis"] = IB.ergebnis({"min": None, "max": None, "ist": t})
        elif j == 8:
            m["bemerkung"] = t
        self._anzeigen()

    def setze_ist(self, zeile: int, text: str):
        self.tabelle.item(zeile, 6).setText(text)

    def merkmal_neu(self, merkmal: str = "Neues Merkmal") -> dict | None:
        if self.daten is None:
            return None
        m = PP.merkmal_aus_text(merkmal) or {"merkmal": merkmal, "art": "Sonstiges", "nenn": None,
                                              "toleranz": "", "min": None, "max": None, "innen": False,
                                              "pruefmittel": "Sichtprüfung", "umfang": "100 %", "ist": "",
                                              "ergebnis": IB.OFFEN, "quelle": "von Hand", "bemerkung": ""}
        m["id"] = PP.naechste_id(self.daten)
        self.daten["merkmale"].append(m)
        self._anzeigen()
        return m

    def merkmal_loeschen(self, zeile: int | None = None):
        i = self.tabelle.currentRow() if zeile is None else zeile
        if self.daten is not None and 0 <= i < len(self.daten["merkmale"]):
            self.daten["merkmale"].pop(i)
            self._anzeigen()

    def _anzeigen(self):
        zeile = self.tabelle.currentRow()
        self._fuellt = True
        d = self.daten or {}
        for key, e in self.felder.items():
            wert = d.get(key, "")
            e.setText(W.anzeigen(W.lesen(wert)) if key == "datum" else wert)
            e.setEnabled(self.daten is not None)
        merkmale = d.get("merkmale", [])
        self.tabelle.setRowCount(len(merkmale))
        for i, m in enumerate(merkmale):
            erg = PP.ergebnis(m)
            werte = [m["id"], m["merkmal"], m["toleranz"], PP.grenz_text(m), m["pruefmittel"], m["umfang"],
                     m.get("ist", ""), erg, m.get("bemerkung", "")]
            for j, w in enumerate(werte):
                it = _item(w, editierbar=j not in (0, 7))
                if j == 7 and erg in ERG_FARBE:
                    it.setBackground(ERG_FARBE[erg])
                if j == 3 and m.get("min") is None:
                    it.setToolTip(m.get("quelle", ""))
                self.tabelle.setItem(i, j, it)
        if self.daten is not None:
            a = PP.auswerten(self.daten)
            z = a["zahlen"]
            gesamt = {IB.IO: "<b style='color:#2e9a43'>Bauteil i. O.</b>",
                      IB.NIO: f"<b style='color:#d13b2f'>Bauteil n. i. O.</b> ({z[IB.NIO]} außerhalb)",
                      IB.OFFEN: f"<b>Prüfung offen</b> ({z[IB.OFFEN]} ohne Ist-Wert)"}[a["gesamt"]]
            mittel = ", ".join(f"{n} ({k})" for n, k in PP.pruefmittelliste(self.daten))
            self.zusammenfassung.setText(f"{gesamt} · {z[IB.IO]} von {len(merkmale)} i. O. · Prüfmittel: {mittel}")
        else:
            self.zusammenfassung.setText("")
        self._fuellt = False
        if 0 <= zeile < self.tabelle.rowCount():
            self.tabelle.selectRow(zeile)

    def speichern_(self) -> dict | None:
        if self.pid is None or self.daten is None:
            return None
        o = self.projekt.pruefplan_speichern(self.pid, self.daten)
        self.status.setText(f"{o['nr']} · Version {o['version']} · {o['status']}")
        i = self.wahl.findData(self.teil_id)
        self.wahl.setItemText(i, self.wahl.itemText(i).rstrip(" ⚠✓") + " ✓")
        self.meldung.emit(f"Prüfplan {o['nr']} gespeichert.", False)
        self.gespeichert.emit()
        return o

    def pdf(self, ziel: str | None = None) -> Path | None:
        if self.pid is None:
            return None
        o = self.projekt.pruefplan(self.pid)
        o["daten"] = self.daten
        if ziel is None:
            ziel, _ = QFileDialog.getSaveFileName(self, "Prüfprotokoll speichern", f"Pruefprotokoll_{o['nr']}.pdf",
                                                  "PDF (*.pdf)")
            if not ziel:
                return None
        from ..pdf import pruefprotokoll_erstellen
        pfad = pruefprotokoll_erstellen(o, ziel, self.projekt.name, self.projekt.teil(self.teil_id)["name"])
        self.meldung.emit(f"Prüfprotokoll gespeichert: {Path(pfad).name}", False)
        return Path(pfad)


# ================================================================ Technische Dokumentation
class DokuSeite(QWidget):
    meldung = Signal(str, bool)

    def __init__(self):
        super().__init__()
        self.projekt: Projekt | None = None
        self.letztes: Path | None = None
        inhalt = QWidget()
        lay = QVBoxLayout(inhalt)
        lay.setContentsMargins(32, 24, 32, 24)
        lay.addWidget(titel("Technische Dokumentation", "Alle Unterlagen des Produkts als ein PDF mit Inhaltsverzeichnis "
                                                        "und Lesezeichen: Lastenheft, Normen, Risikobeurteilung, FMEA, "
                                                        "Berechnungen, Zeichnungen, Stücklisten, Prüfpläne, Anleitungen."))
        k, kl = karte()
        z = QHBoxLayout()
        z.addWidget(QLabel("Ersteller"))
        self.ersteller = QLineEdit()
        self.ersteller.setMaximumWidth(220)
        z.addWidget(self.ersteller)
        z.addStretch()
        z.addWidget(_knopf("Übersicht aktualisieren", lambda: self.laden()))
        z.addWidget(_knopf("PDF-Paket erstellen …", lambda: self.erstellen(), haupt=True))
        kl.addLayout(z)
        self.tabelle = _tabelle(["Kapitel", "Dokumente", "Inhalt"])
        _kopf_breiten(self.tabelle, [220, 100, 0], 2)
        self.tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabelle.setMinimumHeight(400)
        kl.addWidget(self.tabelle)
        self.zusammenfassung = QLabel()
        self.zusammenfassung.setWordWrap(True)
        kl.addWidget(self.zusammenfassung)
        kl.addWidget(_klein("Montageanleitungen werden mit den 3D-Bildern erzeugt; das dauert je Baugruppe einige "
                            "Sekunden. Kapitel ohne Inhalt stehen rot im Inhaltsverzeichnis des PDF. Das Paket ersetzt "
                            "keine Prüfung durch eine Fachperson."))
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
        from ..qualitaet import dokumentation as D
        plan = D.kapitel_planen(self.projekt)
        self.tabelle.setRowCount(len(plan))
        fehlt = []
        for i, (kapitel, punkte, leer) in enumerate(plan):
            self.tabelle.setItem(i, 0, _item(kapitel))
            self.tabelle.setItem(i, 1, _item(str(len(punkte)) if punkte else "–"))
            it = _item(", ".join(t for t, _ in punkte) if punkte else leer)
            if not punkte:
                it.setBackground(AMPEL[Q.ROT])
                fehlt.append(kapitel)
            self.tabelle.setItem(i, 2, it)
        self.tabelle.resizeRowsToContents()
        self.zusammenfassung.setText(
            f"<b>{len(plan) - len(fehlt)} von {len(plan)} Kapiteln vorhanden.</b>"
            + (f" Es fehlen: {', '.join(fehlt)}." if fehlt else ""))

    def erstellen(self, ziel: str | None = None) -> Path | None:
        if not self.projekt:
            return None
        if ziel is None:
            ziel, _ = QFileDialog.getSaveFileName(self, "Technische Dokumentation speichern",
                                                  str(self.projekt.pfad.parent /
                                                      f"Technische_Dokumentation_{self.projekt.name}.pdf"),
                                                  "PDF (*.pdf)")
            if not ziel:
                return None
        from PySide6.QtWidgets import QApplication
        from ..qualitaet import dokumentation as D
        from .montage_seite import anleitung_pdf

        def fortschritt(text):
            self.zusammenfassung.setText(f"Erstelle … {text}")
            QApplication.processEvents()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            pfad, inhalt = D.erstellen(self.projekt, ziel, self.ersteller.text().strip(), fortschritt,
                                       lambda p, mp, z: anleitung_pdf(p, mp["baugruppe_id"], mp["daten"], z))
        finally:
            QApplication.restoreOverrideCursor()
        self.letztes = Path(pfad)
        self.projekt.dokument_merken("technische_doku", pfad)
        self.laden()
        fehlt = [k for k, s, _ in inhalt if s is None]
        from pypdf import PdfReader
        seiten = len(PdfReader(str(pfad)).pages)
        self.meldung.emit(f"Technische Dokumentation gespeichert: {Path(pfad).name} ({seiten} Seiten)"
                          + (f" – es fehlen {len(fehlt)} Kapitel." if fehlt else "."), False)
        return Path(pfad)
