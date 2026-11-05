"""Seite „Baugruppen“: Bauteile und Normteile einbauen, ausrichten, Masse & Schwerpunkt, Stückliste (MS8)."""
from __future__ import annotations

import copy
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..berechnungen.basis import formatiere
from ..cad import baugruppe as BG, geometrie, normteile
from ..modell import NEU_PRUEFEN, Projekt, ProjektFehler
from .ansicht3d import ANSICHTEN, Ansicht3D
from .seiten import karte, leeren, scrollbar, titel

FREI = "frei (x, y, z)"
LAGE_FELDER = [("x", "x"), ("y", "y"), ("z", "z"), ("rx", "Drehung um x (°)"), ("ry", "Drehung um y (°)"),
               ("rz", "Drehung um z (°)")]


class BaugruppenSeite(QWidget):
    meldung = Signal(str, bool)
    gespeichert = Signal()
    zeichnung_oeffnen = Signal(str, int)        # ("baugruppe", id)

    def __init__(self):
        super().__init__()
        self.projekt: Projekt | None = None
        self.definition = BG.leer()
        self.ergebnis: BG.Ergebnis | None = None
        self.baugruppe_id: int | None = None
        self._fuellt = False

        inhalt = QWidget()
        lay = QVBoxLayout(inhalt)
        lay.setContentsMargins(32, 24, 32, 24)
        lay.addWidget(titel("Baugruppen", "Bauteile und Normteile zusammenbauen: koaxial ausrichten, auf Lochkreise "
                                          "verteilen. Masse, Schwerpunkt und Stückliste entstehen automatisch."))
        oben = QHBoxLayout()
        oben.setSpacing(16)

        # ---- links: Einbauten und Eigenschaften
        links, ll = karte()
        links.setMaximumWidth(380)
        zeile = QHBoxLayout()
        self.auswahl = QComboBox()
        self.auswahl.setAccessibleName("Gespeicherte Baugruppe")
        self.auswahl.activated.connect(self._auswahl_gewaehlt)
        zeile.addWidget(self.auswahl, 1)
        b = QPushButton("Neu")
        b.setObjectName("Skizze")
        b.clicked.connect(lambda: self.neu())
        zeile.addWidget(b)
        ll.addLayout(zeile)
        k = QLabel("Einbauten")
        k.setObjectName("Abschnitt")
        ll.addWidget(k)
        self.liste = QListWidget()
        self.liste.setAccessibleName("Einbauten")
        self.liste.setMinimumHeight(160)
        self.liste.currentRowChanged.connect(self._einbau_gewaehlt)
        ll.addWidget(self.liste)
        self.teil_wahl = QComboBox()
        self.teil_wahl.setAccessibleName("Bauteil zum Einbauen")
        zeile = QHBoxLayout()
        zeile.addWidget(self.teil_wahl, 1)
        b = QPushButton("+ Bauteil")
        b.setObjectName("Skizze")
        b.clicked.connect(lambda: self.teil_einbauen())
        zeile.addWidget(b)
        ll.addLayout(zeile)
        self.norm_wahl = QComboBox()
        self.norm_wahl.setEditable(True)
        self.norm_wahl.setAccessibleName("Normteil")
        self.norm_wahl.setToolTip("Aus der Liste wählen oder eintippen, z. B. ISO 4762 M16x50, 6216, 22218 E")
        for gruppe, namen in normteile.katalog().items():
            self.norm_wahl.addItems(namen)
        zeile = QHBoxLayout()
        zeile.addWidget(self.norm_wahl, 1)
        b = QPushButton("+ Normteil")
        b.setObjectName("Skizze")
        b.clicked.connect(lambda: self.normteil_einbauen())
        zeile.addWidget(b)
        ll.addLayout(zeile)
        b = QPushButton("Einbau löschen")
        b.setObjectName("Skizze")
        b.clicked.connect(lambda: self.einbau_loeschen())
        ll.addWidget(b)
        self.eigen_titel = QLabel("Lage")
        self.eigen_titel.setObjectName("Unterabschnitt")
        ll.addWidget(self.eigen_titel)
        self.eigen_lay = QFormLayout()
        self.eigen_lay.setVerticalSpacing(6)
        ll.addLayout(self.eigen_lay)
        ll.addStretch()
        oben.addWidget(links, 2)

        # ---- rechts: 3D, Kennwerte, Speichern
        rechts, rl = karte()
        leiste = QHBoxLayout()
        for name in ANSICHTEN:
            b = QPushButton(name)
            b.setObjectName("Werkzeug")
            b.clicked.connect(lambda _=False, n=name: self.ansicht.ansicht(n))
            leiste.addWidget(b)
        leiste.addStretch()
        rl.addLayout(leiste)
        self.fehler = QLabel()
        self.fehler.setObjectName("Fehler")
        self.fehler.setWordWrap(True)
        self.fehler.hide()
        rl.addWidget(self.fehler)
        self.ansicht = Ansicht3D()
        self.ansicht.setMinimumHeight(420)
        self.ansicht.hinweis = "Mit „+ Bauteil“ oder „+ Normteil“ beginnen."
        rl.addWidget(self.ansicht, 1)
        self.kennwerte = QLabel()
        self.kennwerte.setWordWrap(True)
        rl.addWidget(self.kennwerte)
        zeile = QHBoxLayout()
        zeile.addWidget(QLabel("Name"))
        self.name = QLineEdit("Baugruppe")
        zeile.addWidget(self.name, 1)
        rl.addLayout(zeile)
        knoepfe = QHBoxLayout()
        self.speichern = QPushButton("Baugruppe speichern")
        self.speichern.setObjectName("Haupt")
        self.speichern.setShortcut("Ctrl+S")
        self.speichern.clicked.connect(lambda: self.baugruppe_speichern())
        knoepfe.addWidget(self.speichern)
        self.zeichnung_knopf = QPushButton("Zeichnung …")
        self.zeichnung_knopf.setToolTip("Gespeicherte Baugruppe als Zeichnung mit Stückliste öffnen")
        self.zeichnung_knopf.clicked.connect(self._zeichnung)
        knoepfe.addWidget(self.zeichnung_knopf)
        self.step_knopf = QPushButton("STEP …")
        self.step_knopf.clicked.connect(lambda: self.step_exportieren())
        knoepfe.addWidget(self.step_knopf)
        knoepfe.addStretch()
        rl.addLayout(knoepfe)
        oben.addWidget(rechts, 3)
        lay.addLayout(oben, 1)

        # ---- unten: Stückliste
        unten, ul = karte()
        kopf = QHBoxLayout()
        k = QLabel("Stückliste")
        k.setObjectName("Abschnitt")
        kopf.addWidget(k)
        kopf.addStretch()
        b = QPushButton("CSV …")
        b.setToolTip("Für Excel/Numbers (Semikolon, Dezimalkomma)")
        b.clicked.connect(lambda: self.stueckliste_exportieren(art="csv"))
        kopf.addWidget(b)
        b = QPushButton("PDF …")
        b.clicked.connect(lambda: self.stueckliste_exportieren(art="pdf"))
        kopf.addWidget(b)
        ul.addLayout(kopf)
        self.tabelle = QTableWidget(0, 7)
        self.tabelle.setHorizontalHeaderLabels(["Pos", "Menge", "Benennung", "Sachnummer / Norm", "Werkstoff",
                                                "Einzel kg", "Gesamt kg"])
        self.tabelle.verticalHeader().hide()
        self.tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabelle.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tabelle.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.tabelle.setMinimumHeight(170)
        ul.addWidget(self.tabelle)
        self.hinweis = QLabel()
        self.hinweis.setObjectName("Klein")
        self.hinweis.setWordWrap(True)
        ul.addWidget(self.hinweis)
        lay.addWidget(unten)

        aussen = QVBoxLayout(self)
        aussen.setContentsMargins(0, 0, 0, 0)
        aussen.addWidget(scrollbar(inhalt))
        self.neu()

    # ================================================================ Projekt
    def setze_projekt(self, projekt: Projekt):
        self.projekt = projekt
        self.neu()

    def laden(self):
        self._listen_fuellen()
        self.bauen()

    def _listen_fuellen(self):
        self.teil_wahl.clear()
        self.auswahl.clear()
        self.auswahl.addItem("Neue Baugruppe", None)
        if not self.projekt:
            return
        for t in self.projekt.teile():
            self.teil_wahl.addItem(f"{t['nr']} {t['name']}", t["id"])
        for g in self.projekt.baugruppen():
            self.auswahl.addItem(f"{g['nr']} {g['name']}" + (" ⚠" if g["status"] == NEU_PRUEFEN else ""), g["id"])
        if self.baugruppe_id is not None:
            i = self.auswahl.findData(self.baugruppe_id)
            self.auswahl.setCurrentIndex(max(i, 0))

    def _auswahl_gewaehlt(self, i: int):
        gid = self.auswahl.itemData(i)
        if gid is None:
            self.neu()
        else:
            self.baugruppe_laden(gid)

    def neu(self):
        self.definition = BG.leer()
        self.baugruppe_id = None
        self.name.setText("Baugruppe")
        self._listen_fuellen()
        self.bauen()

    def baugruppe_laden(self, gid: int):
        g = self.projekt.baugruppe(gid)
        self.baugruppe_id = gid
        self.definition = copy.deepcopy(g["definition"])
        self.name.setText(g["name"])
        self._listen_fuellen()
        self.bauen()

    # ================================================================ Einbauten
    def teil_einbauen(self, teil_id: int | None = None, **angaben) -> dict | None:
        teil_id = teil_id if teil_id is not None else self.teil_wahl.currentData()
        if teil_id is None:
            self.meldung.emit("Es gibt noch kein Bauteil – zuerst unter „Bauteile (3D)“ oder „Modellieren“ anlegen.",
                              True)
            return None
        t = self.projekt.teil(teil_id)
        return self._einbau_neu({"art": "teil", "teil_id": teil_id, "name": t["name"]}, angaben)

    def normteil_einbauen(self, norm: str | None = None, **angaben) -> dict | None:
        norm = (norm or self.norm_wahl.currentText()).strip()
        try:
            n = normteile.erzeugen(norm)
        except geometrie.GeometrieFehler as exc:
            self.meldung.emit(str(exc), True)
            return None
        return self._einbau_neu({"art": "normteil", "norm": n.norm, "name": n.benennung}, angaben)

    def _einbau_neu(self, e: dict, angaben: dict) -> dict:
        e["id"] = BG.naechste_id(self.definition)
        vorhanden = self.definition["einbauten"]
        e["lage"] = {k: "0" for k, _ in LAGE_FELDER}
        if vorhanden and "lage" not in angaben:
            e["bezug"] = {"ziel": vorhanden[0]["id"], "abstand": "0", "umdrehen": False}   # meist koaxial
        for k, v in angaben.items():
            if k in ("bezug", "kreis", "lage"):
                e[k] = {**e.get(k, {}), **v}
            else:
                e[k] = v
        vorhanden.append(e)
        self.bauen()
        self.liste.setCurrentRow(len(vorhanden) - 1)
        return e

    def einbau_loeschen(self, zeile: int | None = None):
        zeile = self.liste.currentRow() if zeile is None else zeile
        if not 0 <= zeile < len(self.definition["einbauten"]):
            return
        weg = self.definition["einbauten"].pop(zeile)
        for e in self.definition["einbauten"]:      # Bezüge auf den gelöschten Einbau lösen, Lage bleibt 0
            if e.get("bezug", {}).get("ziel") == weg["id"]:
                e.pop("bezug")
        self.bauen()

    def setze(self, gruppe: str | None, schluessel: str, wert):
        """Eigenschaft des gewählten Einbaus ändern (gruppe: None, "lage", "bezug", "kreis")."""
        zeile = self.liste.currentRow()
        if not 0 <= zeile < len(self.definition["einbauten"]):
            return
        e = self.definition["einbauten"][zeile]
        if gruppe is None:
            e[schluessel] = wert
        elif gruppe == "bezug" and schluessel == "ziel" and not wert:
            e.pop("bezug", None)
        else:
            e.setdefault(gruppe, {})[schluessel] = wert
        self.bauen(eigenschaften=gruppe == "bezug" and schluessel == "ziel")

    # ================================================================ Bauen
    def bauen(self, eigenschaften: bool = True):
        if not self.projekt:
            self.ergebnis = BG.Ergebnis()
        else:
            self.ergebnis = self.projekt.baugruppe_bauen(self.definition)
        r = self.ergebnis
        zeile = self.liste.currentRow()
        self._fuellt = True
        self.liste.clear()
        for e in self.definition["einbauten"]:
            text = f"{e['id']}  {e.get('name') or ''}"
            if e.get("art") == "normteil":
                text += f"  ({e['norm']})"
            n = (e.get("kreis") or {}).get("anzahl")
            if n:
                text += f"  × {n}"
            if e["id"] in r.meldungen:
                text = "⚠ " + text
            QListWidgetItem(text, self.liste).setToolTip(r.meldungen.get(e["id"], ""))
        self._fuellt = False
        if 0 <= zeile < self.liste.count():
            self.liste.setCurrentRow(zeile)
        elif eigenschaften:
            self._eigenschaften()
        self.fehler.setText("⚠ " + r.fehler if r.fehler else "")
        self.fehler.setVisible(bool(r.fehler))
        if r.exemplare:
            self.ansicht.setze_netz(geometrie.netz(r.gesamtform()), anpassen=True)
        else:
            self.ansicht.setze_netz(None)
        sx, sy, sz = r.schwerpunkt
        self.kennwerte.setText(
            (f"<b>Masse {formatiere(r.masse)} kg</b> · Schwerpunkt x {formatiere(sx)}, y {formatiere(sy)}, "
             f"z {formatiere(sz)} mm · {len(r.exemplare)} Teile") if r.exemplare else "")
        self.speichern.setEnabled(bool(self.projekt) and r.ok and bool(self.definition["einbauten"]))
        self.step_knopf.setEnabled(bool(r.exemplare))
        self.zeichnung_knopf.setEnabled(self.baugruppe_id is not None)
        self._stueckliste()
        return r

    def _stueckliste(self):
        r = self.ergebnis
        self.tabelle.setRowCount(len(r.stueckliste))
        for i, p in enumerate(r.stueckliste):
            for j, wert in enumerate((p.pos, p.menge, p.benennung, p.sachnummer, p.werkstoff,
                                      "–" if p.einzelmasse is None else formatiere(p.einzelmasse),
                                      "–" if p.gesamtmasse is None else formatiere(p.gesamtmasse))):
                self.tabelle.setItem(i, j, QTableWidgetItem(str(wert)))
        teile = []
        if r.ohne_masse:
            teile.append("Ohne Masse (fehlt in der Summe): " + ", ".join(r.ohne_masse) + ".")
        if any(p.art == "Normteil" for p in r.stueckliste):
            teile.append("Normteile: Maße aus dem Tabellenbuch, nicht geprüft – vor Bestellung mit dem Katalog "
                         "abgleichen; Lagermassen genähert.")
        self.hinweis.setText(" ".join(teile))

    # ================================================================ Eigenschaften
    def _einbau_gewaehlt(self, _zeile: int):
        if not self._fuellt:
            self._eigenschaften()

    def _eigenschaften(self):
        leeren(self.eigen_lay)
        zeile = self.liste.currentRow()
        if not 0 <= zeile < len(self.definition["einbauten"]):
            self.eigen_titel.setText("Lage")
            return
        e = self.definition["einbauten"][zeile]
        self.eigen_titel.setText(f"{e['id']} – Lage")

        def feld(gruppe, schluessel, standard="0", tipp=""):
            w = QLineEdit(str((e.get(gruppe) or {}).get(schluessel, standard) if gruppe else e.get(schluessel, standard)))
            w.setToolTip(tipp or "mm bzw. Grad, Formel erlaubt")
            w.editingFinished.connect(lambda g=gruppe, s=schluessel, w=w: self.setze(g, s, w.text().strip()))
            return w

        self.eigen_lay.addRow("Name", feld(None, "name", ""))
        ziel = QComboBox()
        ziel.addItem(FREI, "")
        for andere in self.definition["einbauten"]:
            if andere["id"] != e["id"]:
                ziel.addItem(f"{andere['id']} {andere.get('name', '')}", andere["id"])
        aktuell = (e.get("bezug") or {}).get("ziel", "")
        ziel.setCurrentIndex(max(ziel.findData(aktuell), 0))
        ziel.currentIndexChanged.connect(lambda _: self.setze("bezug", "ziel", ziel.currentData()))
        ziel.setToolTip("Koaxial zur Achse dieses Einbaus ausrichten oder frei platzieren")
        self.eigen_lay.addRow("Koaxial zu", ziel)
        if aktuell:
            self.eigen_lay.addRow("Abstand entlang Achse", feld("bezug", "abstand", "0",
                                                                "mm entlang der Achse des Bezugsteils"))
            um = QCheckBox("umdrehen")
            um.setChecked(bool(e["bezug"].get("umdrehen")))
            um.toggled.connect(lambda v: self.setze("bezug", "umdrehen", v))
            self.eigen_lay.addRow("", um)
            self.eigen_lay.addRow("Drehung um Achse (°)", feld("lage", "rz"))
        else:
            for k, text in LAGE_FELDER:
                self.eigen_lay.addRow(text, feld("lage", k))
        self.eigen_lay.addRow("Lochkreis: Anzahl", feld("kreis", "anzahl", "", "leer = ein Teil; z. B. 8"))
        self.eigen_lay.addRow("Lochkreis: Radius", feld("kreis", "radius", "", "mm, z. B. d_LK / 2"))

    # ================================================================ Speichern & Export
    def baugruppe_speichern(self) -> dict | None:
        r = self.bauen(eigenschaften=False)
        if not r.ok or not self.definition["einbauten"]:
            self.meldung.emit("Die Baugruppe hat noch Fehler – so nicht speicherbar.", True)
            return None
        try:
            g = self.projekt.baugruppe_speichern(self.name.text().strip() or "Baugruppe", self.definition, r.masse,
                                                 self.baugruppe_id)
        except ProjektFehler as exc:
            self.meldung.emit(str(exc), True)
            return None
        self.baugruppe_id = g["id"]
        self._listen_fuellen()
        self.zeichnung_knopf.setEnabled(True)
        self.meldung.emit(f"{g['nr']} „{g['name']}“ gespeichert (Version {g['version']}).", False)
        self.gespeichert.emit()
        return g

    def _zeichnung(self):
        if self.baugruppe_id is not None:
            self.zeichnung_oeffnen.emit("baugruppe", self.baugruppe_id)

    def _ziel(self, titel_: str, endung: str, filter_: str) -> str | None:
        ordner = self.projekt.pfad.parent if self.projekt else Path.home()
        ziel, _ = QFileDialog.getSaveFileName(self, titel_, str(ordner / f"{self.name.text().strip()}{endung}"), filter_)
        return ziel or None

    def stueckliste_exportieren(self, ziel: str | None = None, art: str = "csv") -> Path | None:
        r = self.ergebnis
        if not r or not r.stueckliste:
            return None
        ziel = ziel or self._ziel("Stückliste speichern", f"_Stueckliste.{art}",
                                  "CSV (*.csv)" if art == "csv" else "PDF (*.pdf)")
        if not ziel:
            return None
        try:
            if art == "csv":
                Path(ziel).write_text(BG.stueckliste_csv(r.stueckliste), encoding="utf-8-sig")
            else:
                from ..pdf import stueckliste_erstellen
                nr = self.projekt.baugruppe(self.baugruppe_id)["nr"] if self.baugruppe_id else ""
                stueckliste_erstellen(r, ziel, self.name.text(), nr, self.projekt.name)
        except OSError as exc:
            self.meldung.emit(f"Speichern fehlgeschlagen: {exc}", True)
            return None
        self.projekt.dokument_merken("stueckliste", ziel, self.name.text().strip())
        self.meldung.emit(f"Stückliste gespeichert: {Path(ziel).name}", False)
        return Path(ziel)

    def step_exportieren(self, ziel: str | None = None) -> Path | None:
        r = self.ergebnis
        if not r or not r.exemplare:
            return None
        ziel = ziel or self._ziel("STEP exportieren", ".step", "STEP (*.step *.stp)")
        if not ziel:
            return None
        try:
            pfad = geometrie.step_schreiben(r.gesamtform(), ziel, self.name.text().strip() or "Baugruppe")
        except (OSError, geometrie.GeometrieFehler) as exc:
            self.meldung.emit(f"Export fehlgeschlagen: {exc}", True)
            return None
        self.meldung.emit(f"STEP-Datei gespeichert: {Path(pfad).name}", False)
        return Path(pfad)
