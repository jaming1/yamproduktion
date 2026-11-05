"""Seite „Kreativmethoden“ (K2): Sitzungen mit Brainstorming-Board, Methode 6-3-5 oder Mindmap.

Die drei Ansichten liegen in eigenen Dateien (kreativ_board, kreativ_635, kreativ_mindmap); diese Seite
verwaltet die Sitzungen und übernimmt gute Beiträge als Idee (P1) oder als Lösungsweg im Konzept (P3).
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMenu, QPushButton, QSpinBox, QStackedWidget, QVBoxLayout, QWidget,
)

from .. import kreativ
from ..modell import Projekt, ProjektFehler
from .konzept_seiten import _combo, _mit_panel
from .kreativ_635 import Formular635Ansicht
from .kreativ_board import BoardAnsicht
from .kreativ_mindmap import MindmapAnsicht
from .rueckverfolgung import RueckverfolgungPanel
from .seiten import karte, titel


class KreativSeite(QWidget):
    meldung = Signal(str, bool)
    geaendert = Signal()
    gehe_zu_objekt = Signal(str, int)

    def __init__(self):
        super().__init__()
        self.projekt: Projekt | None = None
        self.sitzung: dict | None = None
        self._laedt = False

        inhalt = QWidget()
        lay = QVBoxLayout(inhalt)
        lay.setContentsMargins(32, 20, 24, 12)
        lay.addWidget(titel("Kreativmethoden",
                            "Ideen sammeln mit Brainstorming, 6-3-5 oder Mindmap. Gute Beiträge werden mit einem "
                            "Klick zur Idee oder zum Lösungsweg im Konzept. Alles wird sofort gespeichert."))

        # --- Sitzung wählen / anlegen
        reihe = QHBoxLayout()
        reihe.addWidget(QLabel("Sitzung:"))
        self.sitzung_wahl = _combo(24)
        self.sitzung_wahl.currentIndexChanged.connect(self._sitzung_gewaehlt)
        reihe.addWidget(self.sitzung_wahl, 1)
        self.neu = QPushButton("+  Neue Sitzung")
        self.neu.setObjectName("Haupt")
        self.neu.setToolTip("Methode wählen und neue Sitzung anlegen")
        menue = QMenu(self.neu)
        for schluessel, (name, text) in kreativ.METHODEN.items():
            a = menue.addAction(name)
            a.setToolTip(text)
            a.triggered.connect(lambda _=False, m=schluessel: self.neue_sitzung(m))
        menue.setToolTipsVisible(True)
        self.neu.setMenu(menue)
        reihe.addWidget(self.neu)
        self.loeschen = QPushButton("Löschen")
        self.loeschen.clicked.connect(self._sitzung_loeschen)
        reihe.addWidget(self.loeschen)
        lay.addLayout(reihe)

        # --- Angaben zur Sitzung
        self.kopf, kl = karte()
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        oben = QHBoxLayout()
        self.titel_feld = QLineEdit()
        self.titel_feld.setPlaceholderText("Name der Sitzung")
        self.titel_feld.editingFinished.connect(lambda: self._feld_speichern("titel"))
        oben.addWidget(self.titel_feld, 1)
        oben.addWidget(QLabel("zur Idee:"))
        self.idee_wahl = _combo(18)
        self.idee_wahl.currentIndexChanged.connect(self._idee_geaendert)
        oben.addWidget(self.idee_wahl, 1)
        self.teiln_label = QLabel("Teilnehmende:")
        oben.addWidget(self.teiln_label)
        self.teilnehmer = QSpinBox()
        self.teilnehmer.setRange(*kreativ.TEILNEHMER_635)
        self.teilnehmer.setToolTip("Nur änderbar, solange noch kein Feld ausgefüllt ist")
        self.teilnehmer.editingFinished.connect(self._teilnehmer_geaendert)
        oben.addWidget(self.teilnehmer)
        form.addRow("Titel", oben)
        self.frage = QLineEdit()
        self.frage.setPlaceholderText("Leitfrage, z. B. „Wie schützt sich die Anlage selbst vor Sturm?“")
        self.frage.editingFinished.connect(lambda: self._feld_speichern("frage"))
        form.addRow("Leitfrage", self.frage)
        form.setContentsMargins(0, 0, 0, 0)
        kl.setContentsMargins(14, 10, 14, 10)
        kl.addLayout(form)
        lay.addWidget(self.kopf)

        # --- Arbeitsfläche der Methode
        self.ansichten = {"brainstorming": BoardAnsicht(), "635": Formular635Ansicht(), "mindmap": MindmapAnsicht()}
        self.stapel = QStackedWidget()
        self.leer_hinweis = QLabel("Noch keine Sitzung. Auf „+ Neue Sitzung“ klicken und eine Methode wählen:\n\n"
                                   + "\n".join(f"•  {n}: {b}" for n, b in kreativ.METHODEN.values()))
        self.leer_hinweis.setWordWrap(True)
        self.leer_hinweis.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.stapel.addWidget(self.leer_hinweis)
        for a in self.ansichten.values():
            self.stapel.addWidget(a)
            a.meldung.connect(self.meldung)
            a.geaendert.connect(self._ansicht_geaendert)
            a.auswahl_geaendert.connect(self._auswahl_zeigen)
        lay.addWidget(self.stapel, 1)

        # --- Übernehmen
        self.auswahl_text = QLabel("Kein Beitrag ausgewählt.")
        self.auswahl_text.setObjectName("Klein")
        self.auswahl_text.setMinimumWidth(120)
        lay.addWidget(self.auswahl_text)
        self.unten = QWidget()
        unten = QHBoxLayout(self.unten)
        unten.setContentsMargins(0, 0, 0, 0)
        self.als_idee = QPushButton("Als Idee übernehmen")
        self.als_idee.setToolTip("Legt eine neue Idee mit diesem Text an (Seite „Ideen & TRIZ“)")
        self.als_idee.clicked.connect(lambda: self.als_idee_uebernehmen())
        unten.addWidget(self.als_idee)
        unten.addWidget(QLabel("Lösungsweg für:"))
        self.funktion_wahl = _combo(16)
        unten.addWidget(self.funktion_wahl)
        self.als_loesung = QPushButton("Übernehmen")
        self.als_loesung.setToolTip("Fügt den Text als Lösungsweg der Teilfunktion in den morphologischen Kasten ein")
        self.als_loesung.clicked.connect(lambda: self.als_loesung_uebernehmen())
        unten.addWidget(self.als_loesung)
        unten.addStretch()
        lay.addWidget(self.unten)

        self.panel = RueckverfolgungPanel()
        self.panel.gehe_zu.connect(self.gehe_zu_objekt)
        aussen = QVBoxLayout(self)
        aussen.setContentsMargins(0, 0, 0, 0)
        aussen.addWidget(_mit_panel(inhalt, self.panel))
        self._zustand()

    # ---------- Laden ----------
    def setze_projekt(self, projekt: Projekt):
        self.projekt = projekt
        self.sitzung = None
        self.laden()

    def laden(self, auswahl: int | None = None):
        if not self.projekt:
            return
        self._laedt = True
        sitzungen = self.projekt.kreativ_sitzungen()
        ziel = auswahl or (self.sitzung or {}).get("id") or (sitzungen[-1]["id"] if sitzungen else None)
        self.sitzung_wahl.clear()
        for s in sitzungen:
            self.sitzung_wahl.addItem(f"{s['nr']}  {s['titel']}  ·  {kreativ.methode_name(s['methode'])}", s["id"])
        if not sitzungen:
            self.sitzung_wahl.addItem("– noch keine Sitzung –", None)
        self.sitzung_wahl.setCurrentIndex(max(0, self.sitzung_wahl.findData(ziel)))
        self.idee_wahl.clear()
        self.idee_wahl.addItem("– keine –", None)
        for i in self.projekt.liste("idee"):
            self.idee_wahl.addItem(f"{i['nr']}  {i['titel'] or '(ohne Titel)'}", i["id"])
        self.funktion_wahl.clear()
        for f in self.projekt.teilfunktionen():
            self.funktion_wahl.addItem(f"{f['nr']}  {f['name']}", f["id"])
        if not self.funktion_wahl.count():
            self.funktion_wahl.addItem("– erst Funktionen anlegen –", None)
        self._laedt = False
        self._sitzung_gewaehlt()

    def _sitzung_gewaehlt(self, *_):
        if self._laedt or not self.projekt:
            return
        sid = self.sitzung_wahl.currentData()
        self.sitzung = self.projekt.objekt("kreativ", sid) if sid else None
        s = self.sitzung
        self._laedt = True
        self.titel_feld.setText(s["titel"] if s else "")
        self.frage.setText(s["frage"] if s else "")
        self.idee_wahl.setCurrentIndex(max(0, self.idee_wahl.findData(s["idee_id"] if s else None)))
        self.teilnehmer.setValue(s["teilnehmer"] if s else 6)
        self._laedt = False
        for methode, a in self.ansichten.items():
            a.setze(self.projekt, s if s and s["methode"] == methode else None)
        if s:
            self.stapel.setCurrentWidget(self.ansichten[s["methode"]])
            name, text = kreativ.METHODEN[s["methode"]]
            self.sitzung_wahl.setToolTip(f"{name}: {text}")
            self._zeige("kreativ", s["id"])
        else:
            self.stapel.setCurrentWidget(self.leer_hinweis)
            self.panel.leer()
        self._zustand()

    def _zustand(self):
        s = self.sitzung
        self.kopf.setVisible(s is not None)
        self.unten.setVisible(s is not None)
        self.auswahl_text.setVisible(s is not None)
        self.loeschen.setEnabled(s is not None)
        ist_635 = bool(s and s["methode"] == "635")
        self.teiln_label.setVisible(ist_635)
        self.teilnehmer.setVisible(ist_635)
        if ist_635:
            self.teilnehmer.setEnabled(not self.projekt.kreativ_eintraege(s["id"]))
        self._auswahl_zeigen()

    def _zeige(self, typ: str, id_: int):
        o = self.projekt.objekt(typ, id_)
        self.panel.zeigen(self.projekt, typ, id_, o["nr"], o["titel"], o["status"], o["version"])

    def aktuelle_ansicht(self):
        return self.ansichten[self.sitzung["methode"]] if self.sitzung else None

    def _gewaehlter_beitrag(self) -> dict | None:
        a = self.aktuelle_ansicht()
        eid = a.ausgewaehlt() if a else None
        if not eid:
            return None
        try:
            return self.projekt.kreativ_eintrag(eid)
        except ProjektFehler:
            return None

    def _auswahl_zeigen(self):
        e = self._gewaehlter_beitrag() if self.projekt else None
        if e:
            text = e["text"] if len(e["text"]) <= 70 else e["text"][:67] + " …"
            zusatz = []
            if e["idee_id"]:
                try:
                    zusatz.append(f"ist {self.projekt.objekt('idee', e['idee_id'])['nr']}")
                except ProjektFehler:
                    pass
            if e["loesung_id"]:
                zusatz.append("im Konzept")
            self.auswahl_text.setText(f"Ausgewählt: „{text}“" + (f"  ({', '.join(zusatz)})" if zusatz else ""))
        else:
            self.auswahl_text.setText("Beitrag auswählen, um ihn zu übernehmen.")
        self.als_idee.setEnabled(e is not None)
        self.als_loesung.setEnabled(e is not None and self.funktion_wahl.currentData() is not None)

    def auswaehlen(self, typ: str, id_: int):
        if typ == "kreativ":
            self.laden(id_)

    # ---------- Bearbeiten ----------
    def neue_sitzung(self, methode: str = "brainstorming", titel_: str = "", frage: str = "") -> dict:
        try:
            s = self.projekt.kreativ_neu(methode, titel_, frage)
        except ProjektFehler as exc:
            self.meldung.emit(str(exc), True)
            raise
        self.sitzung = s
        self.laden(s["id"])
        if not frage:
            self.frage.setFocus()
        self.meldung.emit(f"{s['nr']} {s['titel']} angelegt.", False)
        self.geaendert.emit()
        return s

    def _sitzung_loeschen(self):
        if not self.sitzung:
            return
        from PySide6.QtWidgets import QMessageBox
        anzahl = len(self.projekt.kreativ_eintraege(self.sitzung["id"]))
        if anzahl and QMessageBox.question(
                self, "Sitzung löschen",
                f"{self.sitzung['nr']} mit {anzahl} Beiträgen löschen? Übernommene Ideen bleiben erhalten.") \
                != QMessageBox.Yes:
            return
        nr = self.sitzung["nr"]
        self.projekt.objekt_loeschen("kreativ", self.sitzung["id"])
        self.sitzung = None
        self.laden()
        self.meldung.emit(f"{nr} gelöscht.", False)
        self.geaendert.emit()

    def _feld_speichern(self, feld: str):
        if self._laedt or not self.sitzung:
            return
        w = self.titel_feld if feld == "titel" else self.frage
        wert = w.text().strip()
        if feld == "titel" and not wert:
            w.setText(self.sitzung["titel"])
            return
        if wert == self.sitzung[feld]:
            return
        self.sitzung = self.projekt.objekt_aendern("kreativ", self.sitzung["id"], **{feld: wert})
        self._nach_aenderung(neu_laden=feld == "titel")
        if feld == "frage":
            self.aktuelle_ansicht().setze(self.projekt, self.sitzung)   # Mindmap zeigt die Leitfrage in der Mitte

    def _idee_geaendert(self, *_):
        if self._laedt or not self.sitzung:
            return
        neu, alt = self.idee_wahl.currentData(), self.sitzung["idee_id"]
        if neu == alt:
            return
        try:
            self.sitzung = self.projekt.kreativ_idee_setzen(self.sitzung["id"], neu)
        except ProjektFehler as exc:
            self.meldung.emit(str(exc), True)
            self._sitzung_gewaehlt()
            return
        self._nach_aenderung()

    def _teilnehmer_geaendert(self):
        if self._laedt or not self.sitzung or self.sitzung["methode"] != "635":
            return
        if self.teilnehmer.value() == self.sitzung["teilnehmer"]:
            return
        self.sitzung = self.projekt.objekt_aendern("kreativ", self.sitzung["id"], teilnehmer=self.teilnehmer.value())
        self.ansichten["635"].setze(self.projekt, self.sitzung)
        self._nach_aenderung()

    def _nach_aenderung(self, neu_laden: bool = False):
        if neu_laden:
            self.laden(self.sitzung["id"])
        else:
            self._zeige("kreativ", self.sitzung["id"])
        self.meldung.emit("Gespeichert.", False)
        self.geaendert.emit()

    def _ansicht_geaendert(self):
        self._zustand()
        self.geaendert.emit()

    # ---------- Übernehmen ----------
    def als_idee_uebernehmen(self) -> dict | None:
        e = self._gewaehlter_beitrag()
        if not e:
            self.meldung.emit("Bitte zuerst einen Beitrag auswählen.", True)
            return None
        try:
            i = self.projekt.kreativ_als_idee(e["id"])
        except ProjektFehler as exc:
            self.meldung.emit(str(exc), True)
            return None
        self.laden(self.sitzung["id"])
        self.meldung.emit(f"Als {i['nr']} übernommen – zu finden unter „Ideen & TRIZ“.", False)
        self.geaendert.emit()
        return i

    def als_loesung_uebernehmen(self) -> int | None:
        e = self._gewaehlter_beitrag()
        fid = self.funktion_wahl.currentData()
        if not e or not fid:
            self.meldung.emit("Bitte einen Beitrag und eine Teilfunktion wählen.", True)
            return None
        try:
            lid = self.projekt.kreativ_als_loesung(e["id"], fid)
        except ProjektFehler as exc:
            self.meldung.emit(str(exc), True)
            return None
        self._auswahl_zeigen()
        self._zeige("kreativ", self.sitzung["id"])
        self.meldung.emit(f"Als Lösungsweg für {self.funktion_wahl.currentText().strip()} übernommen "
                          "(Seite „Konzept“).", False)
        self.geaendert.emit()
        return lid
