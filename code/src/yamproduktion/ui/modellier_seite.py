"""Seite „Modellieren“: freie Teile aus Skizzen und Features, gesteuert über eine Parameter-Tabelle (MS7)."""
from __future__ import annotations

import copy
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QFormLayout, QGridLayout, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton, QStackedWidget, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from ..berechnungen.basis import formatiere
from ..cad import geometrie, modellierer as M, skizze as S
from ..cad.vorlagen import WERKSTOFFE, dichte
from ..modell import NEU_PRUEFEN, Projekt, ProjektFehler
from .ansicht3d import ANSICHTEN, Ansicht3D
from .seiten import karte, scrollbar, titel
from .skizzen_editor import SkizzenEditor

EBENEN_TEXT = {"XY": "XY · Normale z", "XZ": "XZ · Normale −y", "YZ": "YZ · Normale x"}
OP_TEXT = {"neu": "Neuer Körper", "hinzufügen": "Hinzufügen", "abziehen": "Abziehen"}

# Eigenschaften je Feature-Art: (Schlüssel, Beschriftung, Art, Auswahl/Standard, Tipp)
EIGENSCHAFTEN = {
    "skizze": [("ebene", "Ebene", "wahl", EBENEN_TEXT, ""),
               ("versatz", "Versatz der Ebene", "formel", "0", "Abstand der Skizzenebene vom Ursprung entlang der Normalen, mm")],
    "extrusion": [("skizze", "Skizze", "skizze", None, ""),
                  ("hoehe", "Höhe", "formel", "10", "mm, Formel erlaubt, z. B. t oder 2*b"),
                  ("umkehren", "Richtung umkehren", "bool", False, "Gegen die Normale der Skizzenebene"),
                  ("symmetrisch", "Symmetrisch zur Ebene", "bool", False, "Je die Hälfte nach beiden Seiten"),
                  ("operation", "Operation", "wahl", OP_TEXT, "")],
    "rotation": [("skizze", "Skizze", "skizze", None, ""),
                 ("achse", "Drehachse", "wahl", {"x": "Waagerechte Skizzenachse", "y": "Senkrechte Skizzenachse"}, ""),
                 ("winkel", "Winkel", "formel", "360", "Grad"),
                 ("operation", "Operation", "wahl", OP_TEXT, "")],
    "bohrung": [("ebene", "Ebene", "wahl", EBENEN_TEXT, "Bohrt gegen die Normale der Ebene ins Teil"),
                ("versatz", "Versatz der Ebene", "formel", "0", "mm – meist die Oberfläche, z. B. t"),
                ("x", "Lage waagerecht", "formel", "0", "mm in der Ebene"),
                ("y", "Lage senkrecht", "formel", "0", "mm in der Ebene"),
                ("d", "Durchmesser", "formel", "10", "mm"),
                ("tiefe", "Tiefe", "formel", "durch", "„durch“ = durch das ganze Teil, sonst mm")],
    "fase": [("groesse", "Fasenbreite", "formel", "1", "mm (45°)"),
             ("kanten", "Kanten", "wahl", M.KANTENWAHL, "")],
    "verrundung": [("groesse", "Radius", "formel", "2", "mm"),
                   ("kanten", "Kanten", "wahl", M.KANTENWAHL, "")],
    "muster": [("feature", "Feature", "feature", None, "Bohrung, Extrusion … das vervielfacht wird"),
               ("muster", "Art", "wahl", {"kreis": "Kreismuster", "linear": "Reihe (linear)"}, ""),
               ("anzahl", "Anzahl", "formel", "4", "Exemplare einschließlich des ersten"),
               ("achse", "Drehachse (Kreis)", "wahl", {"z": "z", "x": "x", "y": "y"}, "Durch den Ursprung"),
               ("winkel", "Gesamtwinkel (Kreis)", "formel", "360", "360° = gleichmäßig rundum"),
               ("richtung", "Richtung (Reihe)", "wahl", {"x": "x", "y": "y", "z": "z"}, ""),
               ("abstand", "Abstand (Reihe)", "formel", "20", "mm von Exemplar zu Exemplar")],
    "import": [("datei", "Datei", "text", "", "Name der eingelesenen STEP-Datei"),
               ("operation", "Operation", "wahl", OP_TEXT, "")],
}


class ModellierSeite(QWidget):
    meldung = Signal(str, bool)
    gespeichert = Signal()

    def __init__(self):
        super().__init__()
        self.projekt: Projekt | None = None
        self.definition = M.leer()
        self.ergebnis: M.Ergebnis | None = None
        self.teil_id: int | None = None
        self.skizzen_feature: int | None = None     # Index der Skizze, die gerade bearbeitet wird
        self._fuellt = False

        inhalt = QWidget()
        lay = QVBoxLayout(inhalt)
        lay.setContentsMargins(32, 24, 32, 24)
        lay.addWidget(titel("Modellieren", "Freie Teile aus Skizzen und Features. Maße als Parameter oder Formeln – "
                                           "auch direkt aus den Berechnungen mit ber(\"welle\", \"d\")."))
        oben = QHBoxLayout()
        oben.setSpacing(16)

        # ---- links: Feature-Baum und Eigenschaften
        links, ll = karte()
        links.setMaximumWidth(370)
        k = QLabel("Feature-Baum")
        k.setObjectName("Abschnitt")
        ll.addWidget(k)
        self.baum = QListWidget()
        self.baum.setAccessibleName("Feature-Baum")
        self.baum.setMinimumHeight(170)
        self.baum.currentRowChanged.connect(self._feature_gewaehlt)
        self.baum.itemDoubleClicked.connect(lambda _: self.skizze_bearbeiten())
        ll.addWidget(self.baum)
        raster = QGridLayout()
        raster.setSpacing(4)
        self.neu_knopf: dict[str, QPushButton] = {}
        for i, (art, text) in enumerate(M.ARTEN.items()):
            b = QPushButton("+ " + ("Import" if art == "import" else text))
            b.setObjectName("Skizze")
            b.setToolTip(f"{text} hinzufügen")
            b.clicked.connect(lambda _=False, a=art: self.feature_neu(a) if a != "import" else self.step_importieren())
            raster.addWidget(b, i // 3, i % 3)
            self.neu_knopf[art] = b
        ll.addLayout(raster)
        reihe = QHBoxLayout()
        for text, tipp, fn in (("↑", "Nach oben", lambda: self.verschieben(-1)),
                               ("↓", "Nach unten", lambda: self.verschieben(1)),
                               ("Löschen", "Feature löschen", lambda: self.feature_loeschen())):
            b = QPushButton(text)
            b.setObjectName("Skizze")
            b.setToolTip(tipp)
            b.clicked.connect(fn)
            reihe.addWidget(b)
        reihe.addStretch()
        ll.addLayout(reihe)
        self.eigen_titel = QLabel("Eigenschaften")
        self.eigen_titel.setObjectName("Unterabschnitt")
        ll.addWidget(self.eigen_titel)
        self.eigen_lay = QFormLayout()
        self.eigen_lay.setVerticalSpacing(8)
        ll.addLayout(self.eigen_lay)
        self.skizze_knopf = QPushButton("Skizze bearbeiten")
        self.skizze_knopf.clicked.connect(lambda: self.skizze_bearbeiten())
        ll.addWidget(self.skizze_knopf)
        ll.addStretch()
        oben.addWidget(links, 2)

        # ---- rechts: 3D-Ansicht oder Skizzen-Editor
        rechts, rl = karte()
        self.stapel = QStackedWidget()
        ansicht_box = QWidget()
        al = QVBoxLayout(ansicht_box)
        al.setContentsMargins(0, 0, 0, 0)
        leiste = QHBoxLayout()
        for name in ANSICHTEN:
            b = QPushButton(name)
            b.setObjectName("Werkzeug")
            b.clicked.connect(lambda _=False, n=name: self.ansicht.ansicht(n))
            leiste.addWidget(b)
        leiste.addStretch()
        al.addLayout(leiste)
        self.ansicht = Ansicht3D()
        self.ansicht.setMinimumHeight(440)
        self.ansicht.hinweis = "Mit „+ Skizze“ beginnen, dann extrudieren oder drehen."
        al.addWidget(self.ansicht, 1)
        self.stapel.addWidget(ansicht_box)
        self.editor = SkizzenEditor()
        self.editor.setMinimumHeight(500)
        self.editor.fertig.connect(self.skizze_fertig)
        self.editor.geaendert.connect(self._skizze_geaendert)
        self.editor.meldung.connect(self.meldung.emit)
        self.stapel.addWidget(self.editor)
        self.fehler = QLabel()
        self.fehler.setObjectName("Fehler")
        self.fehler.setWordWrap(True)
        self.fehler.hide()
        rl.addWidget(self.fehler)
        rl.addWidget(self.stapel, 1)
        self.kennwerte = QLabel()
        self.kennwerte.setWordWrap(True)
        rl.addWidget(self.kennwerte)
        zeile = QHBoxLayout()
        zeile.addWidget(QLabel("Name"))
        self.name = QLineEdit("Freies Teil")
        zeile.addWidget(self.name, 1)
        zeile.addWidget(QLabel("Werkstoff"))
        self.werkstoff = QComboBox()
        self.werkstoff.addItems(WERKSTOFFE)
        self.werkstoff.setCurrentText(next((w for w in WERKSTOFFE if w.startswith("S355J2")), WERKSTOFFE[0]))
        self.werkstoff.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.werkstoff.setMinimumContentsLength(16)
        self.werkstoff.currentIndexChanged.connect(lambda _: self._kennwerte())
        zeile.addWidget(self.werkstoff, 1)
        rl.addLayout(zeile)
        knoepfe = QHBoxLayout()
        self.speichern = QPushButton("Als Bauteil speichern")
        self.speichern.setObjectName("Haupt")
        self.speichern.setShortcut("Ctrl+S")
        self.speichern.setToolTip("Speichert Parameter und Feature-Baum im Projekt (⌘S)")
        self.speichern.clicked.connect(lambda: self.teil_speichern())
        knoepfe.addWidget(self.speichern)
        self.step_knopf = QPushButton("STEP exportieren …")
        self.step_knopf.clicked.connect(lambda: self.exportieren())
        knoepfe.addWidget(self.step_knopf)
        b = QPushButton("Neues Teil")
        b.clicked.connect(lambda: self.neu())
        knoepfe.addWidget(b)
        knoepfe.addStretch()
        rl.addLayout(knoepfe)
        oben.addWidget(rechts, 3)
        lay.addLayout(oben, 1)

        # ---- unten: Parameter-Tabelle
        unten, ul = karte()
        k = QLabel("Parameter")
        k.setObjectName("Abschnitt")
        ul.addWidget(k)
        tipp = QLabel("Formeln mit + − * / ** ( ), sqrt, sin/cos/tan (Grad), min, max, round · "
                      "Werte aus gespeicherten Berechnungen: ber(\"welle\", \"d\") – Längen in mm.")
        tipp.setObjectName("Klein")
        tipp.setWordWrap(True)
        ul.addWidget(tipp)
        self.tabelle = QTableWidget(0, 4)
        self.tabelle.setHorizontalHeaderLabels(["Name", "Formel", "Wert", "Kommentar"])
        self.tabelle.verticalHeader().hide()
        self.tabelle.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.tabelle.horizontalHeader().setStretchLastSection(True)
        self.tabelle.setColumnWidth(0, 120)
        self.tabelle.setColumnWidth(1, 300)
        self.tabelle.setColumnWidth(2, 120)
        self.tabelle.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabelle.itemChanged.connect(self._parameter_geaendert)
        ul.addWidget(self.tabelle)
        reihe = QHBoxLayout()
        b = QPushButton("+ Parameter")
        b.clicked.connect(lambda: self.parameter_neu())
        reihe.addWidget(b)
        b = QPushButton("Parameter löschen")
        b.clicked.connect(self._parameter_loeschen)
        reihe.addWidget(b)
        self.bezuege = QLabel()
        self.bezuege.setObjectName("Klein")
        self.bezuege.setWordWrap(True)
        reihe.addWidget(self.bezuege, 1)
        ul.addLayout(reihe)
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
        self.bauen()

    def _ber(self):
        if not self.projekt:
            return None, {}
        return self.projekt.ber_funktion()

    # ================================================================ Bauen
    def bauen(self):
        ber, quellen = self._ber()
        self.ergebnis = M.bauen(self.definition, ber)
        self._quellen = quellen
        self._baum_fuellen()
        self._tabelle_fuellen()
        r = self.ergebnis
        if r.fehler:
            self.fehler.setText("⚠ " + r.fehler)
            self.fehler.show()
        else:
            self.fehler.hide()
        if r.form is not None:
            self.ansicht.setze_netz(geometrie.netz(r.form), anpassen=True)
        else:
            self.ansicht.setze_netz(None)
        self.speichern.setEnabled(r.ok)
        self.step_knopf.setEnabled(r.form is not None)
        self._kennwerte()
        nummern = []
        if self.projekt:
            for _, (_, bid) in sorted(quellen.items()):
                b = self.projekt.berechnung(bid)
                text = b.nr + (" ⚠ neu prüfen" if b.status == NEU_PRUEFEN else "")
                if text not in nummern:
                    nummern.append(text)
        self.bezuege.setText(("Werte aus " + ", ".join(nummern)) if nummern else "")
        return r

    def _kennwerte(self):
        r = self.ergebnis
        if not r or r.form is None:
            self.kennwerte.setText("")
            return
        e = geometrie.eigenschaften(r.form)
        masse = e.masse(dichte(self.werkstoff.currentText()))
        koerper = M.anzahl_koerper(r.form)
        self.kennwerte.setText(
            f"<b>Masse {formatiere(masse)} kg</b> · Volumen {formatiere(e.volumen / 1000)} cm³ · "
            f"Abmessungen {formatiere(e.groesse[0])} × {formatiere(e.groesse[1])} × {formatiere(e.groesse[2])} mm"
            + (f" · {koerper} getrennte Körper" if koerper > 1 else ""))

    # ================================================================ Feature-Baum
    def _baum_fuellen(self):
        zeile = self.baum.currentRow()
        self.baum.blockSignals(True)
        self.baum.clear()
        schritte = {s.name: s for s in (self.ergebnis.schritte if self.ergebnis else [])}
        for f in self.definition["features"]:
            s = schritte.get(f["name"])
            zeichen = "✓" if s and s.ok else ("⚠" if s else "○")
            text = f"{zeichen}  {f['name']}  ·  {M.ARTEN[f['art']]}"
            if f["art"] in ("extrusion", "rotation", "import") and f.get("operation") == "abziehen":
                text += " (abziehen)"
            item = QListWidgetItem(text)
            if s and not s.ok:
                item.setToolTip(s.meldung)
            self.baum.addItem(item)
        self.baum.blockSignals(False)
        n = len(self.definition["features"])
        self.baum.setCurrentRow(min(zeile, n - 1) if zeile >= 0 else n - 1)
        self._eigenschaften_zeigen()

    def _feature_gewaehlt(self, _):
        self._eigenschaften_zeigen()

    @property
    def gewaehlt(self) -> dict | None:
        z = self.baum.currentRow()
        f = self.definition["features"]
        return f[z] if 0 <= z < len(f) else None

    def feature_neu(self, art: str, **werte) -> dict:
        f = {"art": art, "name": M.naechster_name(self.definition, art)}
        for schluessel, _, typ, standard, _ in EIGENSCHAFTEN[art]:
            if typ == "wahl":
                f[schluessel] = next(iter(standard))
            elif typ in ("formel", "text"):
                f[schluessel] = standard
            elif typ == "bool":
                f[schluessel] = bool(standard)
            elif typ == "skizze":
                skizzen = self._namen("skizze")
                f[schluessel] = skizzen[-1] if skizzen else ""
            elif typ == "feature":
                ziele = [x["name"] for x in self.definition["features"] if x["art"] not in ("skizze", "fase", "verrundung")]
                f[schluessel] = ziele[-1] if ziele else ""
        if art == "skizze":
            f["skizze"] = S.leer()
        if art in ("extrusion", "rotation") and self.ergebnis and self.ergebnis.form is not None:
            f["operation"] = "hinzufügen"
        f.update(werte)
        self.definition["features"].append(f)
        self.bauen()
        self.baum.setCurrentRow(len(self.definition["features"]) - 1)
        if art == "skizze" and not werte.get("skizze"):
            self.skizze_bearbeiten()
        return f

    def _namen(self, art: str, bis: int | None = None) -> list[str]:
        f = self.definition["features"][:bis] if bis is not None else self.definition["features"]
        return [x["name"] for x in f if x["art"] == art]

    def verschieben(self, richtung: int):
        z = self.baum.currentRow()
        f = self.definition["features"]
        if not 0 <= z + richtung < len(f) or z < 0:
            return
        f[z], f[z + richtung] = f[z + richtung], f[z]
        self.bauen()
        self.baum.setCurrentRow(z + richtung)

    def feature_loeschen(self):
        f = self.gewaehlt
        if f is None:
            return
        benutzt = [x["name"] for x in self.definition["features"]
                   if f["name"] in (x.get("skizze") if isinstance(x.get("skizze"), str) else None, x.get("feature"))]
        self.definition["features"].remove(f)
        self.bauen()
        if benutzt:
            self.meldung.emit(f"{f['name']} gelöscht – {', '.join(benutzt)} brauchte es und muss angepasst werden.", True)

    # ---------- Eigenschaften ----------
    def _eigenschaften_zeigen(self):
        while self.eigen_lay.rowCount():
            self.eigen_lay.removeRow(0)
        self.eigenschaft: dict[str, QWidget] = {}
        f = self.gewaehlt
        self.skizze_knopf.setVisible(bool(f and f["art"] == "skizze"))
        if f is None:
            self.eigen_titel.setText("Eigenschaften")
            return
        self.eigen_titel.setText(f"Eigenschaften · {f['name']}")
        index = self.definition["features"].index(f)
        for schluessel, text, typ, wahl, tipp in EIGENSCHAFTEN[f["art"]]:
            if typ == "wahl" or typ in ("skizze", "feature"):
                w = QComboBox()
                if typ == "wahl":
                    for k, t in wahl.items():
                        w.addItem(t, k)
                elif typ == "skizze":
                    for n in self._namen("skizze", index):
                        w.addItem(n, n)
                else:
                    for x in self.definition["features"][:index]:
                        if x["art"] not in ("skizze", "fase", "verrundung"):
                            w.addItem(x["name"], x["name"])
                i = w.findData(f.get(schluessel))
                w.setCurrentIndex(max(i, 0))
                w.currentIndexChanged.connect(lambda _=0, s=schluessel, w=w: self.setze_eigenschaft(s, w.currentData()))
            elif typ == "bool":
                w = QCheckBox()
                w.setChecked(bool(f.get(schluessel)))
                w.toggled.connect(lambda an, s=schluessel: self.setze_eigenschaft(s, an))
            else:
                w = QLineEdit(str(f.get(schluessel, "")))
                w.setReadOnly(typ == "text")
                w.editingFinished.connect(lambda s=schluessel, w=w: self.setze_eigenschaft(s, w.text().strip()))
            w.setToolTip(tipp)
            label = QLabel(text)
            label.setToolTip(tipp)
            self.eigen_lay.addRow(label, w)
            self.eigenschaft[schluessel] = w

    def setze_eigenschaft(self, schluessel: str, wert):
        f = self.gewaehlt
        if f is None:
            return
        if schluessel in ("ebene", "versatz") and f["art"] == "skizze":
            f["skizze"][schluessel] = wert
        if f.get(schluessel) == wert and f["art"] != "skizze":
            return
        f[schluessel] = wert
        self.bauen()

    # ================================================================ Skizzen
    def skizze_bearbeiten(self, index: int | None = None):
        if index is None:
            index = self.baum.currentRow()
        f = self.definition["features"]
        if not 0 <= index < len(f) or f[index]["art"] != "skizze":
            return
        self.skizzen_feature = index
        self.editor.setze(f[index]["skizze"], self.ergebnis.werte if self.ergebnis else {}, self._ber()[0])
        self.stapel.setCurrentWidget(self.editor)

    def _skizze_geaendert(self):
        if self.skizzen_feature is not None:
            self.definition["features"][self.skizzen_feature]["skizze"] = copy.deepcopy(self.editor.skizze)

    def skizze_fertig(self):
        self._skizze_geaendert()
        index = self.skizzen_feature
        self.skizzen_feature = None
        self.stapel.setCurrentIndex(0)
        self.bauen()
        if index is not None:
            self.baum.setCurrentRow(index)
            f = self.definition["features"]
            if index == len(f) - 1:
                self.meldung.emit("Skizze fertig. Mit „+ Extrusion“ oder „+ Rotation“ wird daraus ein Körper.", False)

    # ================================================================ Parameter
    def _tabelle_fuellen(self):
        self._fuellt = True
        zeilen = self.definition["parameter"]
        self.tabelle.setRowCount(len(zeilen))
        werte = self.ergebnis.werte if self.ergebnis else {}
        for z, p in enumerate(zeilen):
            for s, text in enumerate((p["name"], str(p["formel"]),
                                      formatiere(werte[p["name"]]) if p["name"] in werte else "–",
                                      p.get("kommentar", ""))):
                item = QTableWidgetItem(text)
                if s == 2:
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.tabelle.setItem(z, s, item)
        hoehe = self.tabelle.horizontalHeader().height() + 6 + sum(self.tabelle.rowHeight(z) for z in range(len(zeilen)))
        self.tabelle.setFixedHeight(min(max(hoehe, 70), 320))
        self._fuellt = False

    def parameter_neu(self, name: str | None = None, formel: str = "10", kommentar: str = ""):
        vorhanden = {p["name"] for p in self.definition["parameter"]}
        if name is None:
            i = 1
            while f"p{i}" in vorhanden:
                i += 1
            name = f"p{i}"
        self.definition["parameter"].append({"name": name, "formel": formel, "kommentar": kommentar})
        self.bauen()

    def setze_parameter(self, name: str, formel: str):
        for p in self.definition["parameter"]:
            if p["name"] == name:
                p["formel"] = formel
        self.bauen()

    def _parameter_geaendert(self, item: QTableWidgetItem):
        if self._fuellt:
            return
        z, s = item.row(), item.column()
        p = self.definition["parameter"][z]
        schluessel = {0: "name", 1: "formel", 3: "kommentar"}.get(s)
        if not schluessel:
            return
        p[schluessel] = item.text().strip()
        if schluessel != "kommentar":
            self.bauen()

    def _parameter_loeschen(self):
        z = self.tabelle.currentRow()
        if 0 <= z < len(self.definition["parameter"]):
            del self.definition["parameter"][z]
            self.bauen()

    # ================================================================ Import / Export / Speichern
    def step_importieren(self, pfad: str | None = None):
        if pfad is None:
            pfad, _ = QFileDialog.getOpenFileName(self, "STEP importieren", str(Path.home()), "STEP (*.step *.stp)")
            if not pfad:
                return None
        try:
            text = Path(pfad).read_text(encoding="utf-8", errors="replace")
            geometrie.step_lesen(pfad)
        except (OSError, geometrie.GeometrieFehler) as exc:
            self.meldung.emit(f"STEP-Import fehlgeschlagen: {exc}", True)
            return None
        op = "hinzufügen" if self.definition["features"] else "neu"
        f = self.feature_neu("import", datei=Path(pfad).name, step=text, operation=op)
        self.meldung.emit(f"{Path(pfad).name} eingelesen ({len(text) // 1024} KB) – als Feature {f['name']}.", False)
        return f

    def exportieren(self, ziel: str | None = None) -> Path | None:
        if not self.ergebnis or self.ergebnis.form is None:
            return None
        name = self.name.text().strip() or "Teil"
        if ziel is None:
            ordner = self.projekt.pfad.parent if self.projekt else Path.home()
            ziel, _ = QFileDialog.getSaveFileName(self, "STEP exportieren", str(ordner / f"{name}.step"),
                                                  "STEP (*.step *.stp)")
            if not ziel:
                return None
        try:
            pfad = geometrie.step_schreiben(self.ergebnis.form, ziel, name)
        except (OSError, geometrie.GeometrieFehler) as exc:
            self.meldung.emit(f"Export fehlgeschlagen: {exc}", True)
            return None
        self.meldung.emit(f"STEP-Datei gespeichert: {Path(pfad).name}", False)
        return Path(pfad)

    def teil_speichern(self) -> dict | None:
        if self.stapel.currentWidget() is self.editor:
            self.skizze_fertig()
        r = self.bauen()
        if not self.projekt or not r.ok:
            return None
        e = geometrie.eigenschaften(r.form)
        werkstoff = self.werkstoff.currentText()
        parameter = {"definition": copy.deepcopy(self.definition), "werkstoff": werkstoff}
        try:
            t = self.projekt.teil_speichern("frei", self.name.text().strip() or "Freies Teil", parameter,
                                            e.masse(dichte(werkstoff)), e.volumen, dict(self._quellen),
                                            teil_id=self.teil_id)
        except ProjektFehler as exc:
            self.meldung.emit(str(exc), True)
            return None
        self.teil_id = t["id"]
        nummern = sorted({b.nr for b in self.projekt.haengt_ab_von("teil", t["id"])})
        self.meldung.emit(f"Bauteil {t['nr']} „{t['name']}“ gespeichert (Version {t['version']})."
                          + (f" Maße aus {', '.join(nummern)}." if nummern else ""), False)
        self.gespeichert.emit()
        return t

    def neu(self):
        self.definition = M.leer()
        self.teil_id = None
        self.name.setText("Freies Teil")
        self.skizzen_feature = None
        self.stapel.setCurrentIndex(0)
        self.bauen()

    def teil_laden(self, teil_id: int):
        if not self.projekt:
            return
        t = self.projekt.teil(teil_id)
        self.definition = copy.deepcopy(t["parameter"]["definition"])
        self.werkstoff.setCurrentText(t["parameter"].get("werkstoff", self.werkstoff.currentText()))
        self.name.setText(t["name"])
        self.teil_id = teil_id
        self.skizzen_feature = None
        self.stapel.setCurrentIndex(0)
        self.bauen()
        self.meldung.emit(f"{t['nr']} „{t['name']}“ geöffnet (Version {t['version']}).", False)
