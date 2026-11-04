"""Seite „Bauteile (3D)“: Vorlagen-Teile aus Berechnungswerten erzeugen, ansehen, schneiden, exportieren (MS6)."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QPushButton, QSlider, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..berechnungen.basis import formatiere
from ..cad import geometrie
from ..cad.vorlagen import VORLAGEN, dichte, durchgangsloch
from ..modell import NEU_PRUEFEN, Projekt, ProjektFehler
from .ansicht3d import ANSICHTEN, Ansicht3D
from .rechen_seite import projektwerte
from .seiten import karte, scrollbar, titel


class BauteilSeite(QWidget):
    meldung = Signal(str, bool)
    gespeichert = Signal()
    frei_oeffnen = Signal(int)      # freies Teil → Seite „Modellieren“

    def __init__(self):
        super().__init__()
        self.projekt: Projekt | None = None
        self.form = None              # aktuelle Geometrie (OCP)
        self.eigen = None             # Eigenschaften der aktuellen Geometrie
        self.teil_id: int | None = None
        self._genau: dict[str, float] = {}
        self._baut = False

        inhalt = QWidget()
        lay = QVBoxLayout(inhalt)
        lay.setContentsMargins(32, 24, 32, 24)
        lay.addWidget(titel("Bauteile (3D)", "Vorlagen-Teile, deren Maße direkt aus den Berechnungen kommen. "
                                             "Ändert sich eine Berechnung, wird das Teil „neu prüfen“."))
        oben = QHBoxLayout()
        oben.setSpacing(16)

        # ---- links: Vorlage und Parameter
        links, ll = karte()
        links.setMaximumWidth(460)
        kopf = QHBoxLayout()
        k = QLabel("Vorlage")
        k.setObjectName("Abschnitt")
        kopf.addWidget(k)
        self.vorlage = QComboBox()
        for v in VORLAGEN.values():
            self.vorlage.addItem(v.TITEL, v.TYP)
        self.vorlage.setAccessibleName("Vorlage wählen")
        self.vorlage.currentIndexChanged.connect(self._vorlage_gewechselt)
        kopf.addWidget(self.vorlage, 1)
        ll.addLayout(kopf)
        self.beschreibung = QLabel()
        self.beschreibung.setObjectName("Klein")
        self.beschreibung.setWordWrap(True)
        ll.addWidget(self.beschreibung)
        name_zeile = QHBoxLayout()
        name_zeile.addWidget(QLabel("Name"))
        self.name = QLineEdit()
        self.name.setPlaceholderText("z. B. Hauptwelle")
        name_zeile.addWidget(self.name, 1)
        ll.addLayout(name_zeile)
        self.form_lay = QFormLayout()
        self.form_lay.setVerticalSpacing(8)
        ll.addLayout(self.form_lay)
        self.uebernehmen = QPushButton("Werte aus dem Projekt übernehmen")
        self.uebernehmen.setToolTip("Maße aus den gespeicherten Berechnungen – dabei entsteht die Verknüpfung")
        self.uebernehmen.clicked.connect(self.aus_projekt)
        ll.addWidget(self.uebernehmen)
        self.verknuepft = QLabel()
        self.verknuepft.setObjectName("Klein")
        self.verknuepft.setWordWrap(True)
        ll.addWidget(self.verknuepft)
        ll.addStretch()
        oben.addWidget(links, 2)

        # ---- rechts: 3D-Ansicht
        rechts, rl = karte()
        leiste = QHBoxLayout()
        for name in ANSICHTEN:
            b = QPushButton(name)
            b.setObjectName("Werkzeug")
            b.setToolTip(f"Ansicht {name}")
            b.clicked.connect(lambda _=False, n=name: self.ansicht.ansicht(n))
            leiste.addWidget(b)
        leiste.addSpacing(12)
        self.schnitt = QCheckBox("Schnitt")
        self.schnitt.setToolTip("Halbschnitt durch die Teileachse – Schnittfläche orange")
        self.schnitt.toggled.connect(self._anzeigen)
        leiste.addWidget(self.schnitt)
        self.schnitt_pos = QSlider(Qt.Horizontal)
        self.schnitt_pos.setRange(-100, 100)
        self.schnitt_pos.setValue(0)
        self.schnitt_pos.setToolTip("Lage der Schnittebene")
        self.schnitt_pos.setAccessibleName("Lage der Schnittebene")
        self.schnitt_pos.sliderReleased.connect(self._anzeigen)
        self.schnitt_pos.valueChanged.connect(lambda _: None if self.schnitt_pos.isSliderDown() else self._anzeigen())
        leiste.addWidget(self.schnitt_pos, 1)
        rl.addLayout(leiste)
        self.ansicht = Ansicht3D()
        self.ansicht.setMinimumHeight(420)
        self.ansicht.geaendert.connect(lambda: self._anzeigen() if self.schnitt.isChecked() else None)
        rl.addWidget(self.ansicht, 1)
        self.kennwerte = QLabel()
        self.kennwerte.setWordWrap(True)
        rl.addWidget(self.kennwerte)
        self.fehler = QLabel()
        self.fehler.setObjectName("StatusWarnung")
        self.fehler.setWordWrap(True)
        self.fehler.hide()
        rl.addWidget(self.fehler)
        knoepfe = QHBoxLayout()
        self.speichern = QPushButton("Als Bauteil speichern")
        self.speichern.setObjectName("Haupt")
        self.speichern.setShortcut("Ctrl+S")
        self.speichern.setToolTip("Speichert das Teil mit seinen Parametern im Projekt (⌘S)")
        self.speichern.clicked.connect(lambda: self.teil_speichern())
        knoepfe.addWidget(self.speichern)
        self.step_knopf = QPushButton("STEP exportieren …")
        self.step_knopf.clicked.connect(lambda: self.exportieren("step"))
        knoepfe.addWidget(self.step_knopf)
        self.stl_knopf = QPushButton("STL exportieren …")
        self.stl_knopf.setToolTip("Für 3D-Druck (Dreiecksnetz)")
        self.stl_knopf.clicked.connect(lambda: self.exportieren("stl"))
        knoepfe.addWidget(self.stl_knopf)
        knoepfe.addStretch()
        rl.addLayout(knoepfe)
        oben.addWidget(rechts, 3)
        lay.addLayout(oben, 1)

        # ---- unten: gespeicherte Teile
        unten, ul = karte()
        k = QLabel("Bauteile im Projekt")
        k.setObjectName("Abschnitt")
        ul.addWidget(k)
        self.tabelle = QTableWidget(0, 6)
        self.tabelle.setHorizontalHeaderLabels(["Nr", "Name", "Vorlage", "Masse", "Version", "Status"])
        self.tabelle.verticalHeader().hide()
        self.tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabelle.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabelle.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tabelle.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tabelle.horizontalHeader().setStretchLastSection(True)
        self.tabelle.setMaximumHeight(170)
        self.tabelle.itemDoubleClicked.connect(lambda _: self.teil_laden(self._gewaehlte_id()))
        ul.addWidget(self.tabelle)
        tk = QHBoxLayout()
        b = QPushButton("Öffnen")
        b.clicked.connect(lambda: self.teil_laden(self._gewaehlte_id()))
        tk.addWidget(b)
        self.neu_knopf = QPushButton("Neu erzeugen (Werte aus Berechnungen)")
        self.neu_knopf.setToolTip("Für Teile mit „neu prüfen“: übernimmt die geänderten Berechnungswerte")
        self.neu_knopf.clicked.connect(lambda: self.neu_erzeugen(self._gewaehlte_id()))
        tk.addWidget(self.neu_knopf)
        tk.addStretch()
        ul.addLayout(tk)
        lay.addWidget(unten)
        aussen = QVBoxLayout(self)
        aussen.setContentsMargins(0, 0, 0, 0)
        aussen.addWidget(scrollbar(inhalt))

        self.eingaben: dict[str, QDoubleSpinBox | QComboBox] = {}
        self._vorlage_gewechselt()

    # ---------- Vorlage / Parameter ----------
    @property
    def modul(self):
        return VORLAGEN[self.vorlage.currentData()]

    @property
    def felder(self):
        return {f.attr: f for f in self.modul.FELDER}

    def _vorlage_gewechselt(self):
        while self.form_lay.rowCount():
            self.form_lay.removeRow(0)
        self.eingaben = {}
        self._genau = {}
        self.teil_id = None
        v = self.modul
        self.beschreibung.setText(v.BESCHREIBUNG)
        self.name.setText(v.KURZ)
        standard = v.Eingaben()
        for feld in v.FELDER:
            if feld.auswahl:
                w = QComboBox()
                w.addItems(list(feld.auswahl))
                w.setCurrentText(getattr(standard, feld.attr))
                w.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
                w.setMinimumContentsLength(14)
                w.currentIndexChanged.connect(self.erzeugen)
            else:
                w = QDoubleSpinBox()
                w.setRange(feld.minimum, feld.maximum)
                w.setSingleStep(feld.schritt)
                w.setDecimals(feld.stellen)
                w.setValue(getattr(standard, feld.attr))
                if feld.anzeige_einheit:
                    w.setSuffix(f"  {feld.anzeige_einheit}")
                w.setKeyboardTracking(False)
                w.valueChanged.connect(self.erzeugen)
            w.setToolTip(feld.tipp)
            name = QLabel(feld.name)
            name.setToolTip(feld.tipp)
            name.setWordWrap(True)
            self.form_lay.addRow(name, w)
            self.eingaben[feld.attr] = w
        self.erzeugen()
        self._verknuepfung_zeigen()

    def werte(self) -> dict:
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
        return werte

    def _setze_werte(self, werte: dict):
        self._baut = True
        for attr, wert in werte.items():
            w = self.eingaben.get(attr)
            if w is None:
                continue
            w.blockSignals(True)
            if isinstance(w, QComboBox):
                w.setCurrentText(str(wert))
            else:
                w.setValue(float(wert))
                self._genau[attr] = float(wert)
            w.blockSignals(False)
        self._baut = False

    # ---------- Projekt ----------
    def setze_projekt(self, projekt: Projekt):
        self.projekt = projekt
        self.teil_id = None
        self.laden()

    def laden(self):
        self._tabelle_fuellen()
        self._verknuepfung_zeigen()

    def _projektwerte(self):
        return projektwerte(self.projekt, self.modul, self.felder)

    def _passt(self, attr: str, wert: float) -> bool:
        w = self.eingaben[attr]
        return abs(wert - w.value()) <= max(0.51 * 10 ** -w.decimals(), 1e-6 * abs(wert))

    def quellen_ermitteln(self) -> dict:
        return {a: q for a, (w, q, _) in self._projektwerte().items() if self._passt(a, w)}

    def _verknuepfung_zeigen(self):
        if not self.projekt:
            self.verknuepft.setText("")
            return
        werte = self._projektwerte()
        teile = [f"{self.felder[a].name} ← {nr}" for a, (w, _, nr) in werte.items() if self._passt(a, w)]
        if teile:
            self.verknuepft.setText("Verknüpft: " + " · ".join(teile))
        elif werte:
            self.verknuepft.setText("Das Projekt kann " + str(len(werte)) + " Werte liefern – „Werte übernehmen“.")
        else:
            quellen = sorted({t for t, _ in self.modul.BERECHNUNGS_QUELLEN.values()})
            self.verknuepft.setText("Noch keine passende Berechnung gespeichert (" + ", ".join(quellen) + ").")

    def aus_projekt(self):
        if not self.projekt:
            return
        werte = self._projektwerte()
        if not werte:
            self.meldung.emit("Im Projekt gibt es noch keine passende gespeicherte Berechnung.", True)
            return
        self._genau.clear()
        self._setze_werte({a: w for a, (w, _, _) in werte.items()})
        self.erzeugen()
        nummern = sorted({nr for _, _, nr in werte.values()})
        warnung = any("⚠" in n for n in nummern)
        self.meldung.emit(f"{len(werte)} Maße übernommen aus {', '.join(nummern)}."
                          + (" Achtung: eine Quelle muss neu berechnet werden." if warnung else ""), warnung)

    # ---------- Geometrie ----------
    def erzeugen(self):
        if self._baut:
            return
        v = self.modul
        try:
            self.form = v.erzeuge(v.Eingaben(**self.werte()))
            self.eigen = geometrie.eigenschaften(self.form)
        except (ValueError, TypeError) as exc:
            self.form = self.eigen = None
            self.fehler.setText(f"⚠ {exc}")
            self.fehler.show()
            self.kennwerte.setText("")
            self.ansicht.hinweis = "Mit diesen Maßen lässt sich das Teil nicht bauen."
            self.ansicht.setze_netz(None)
            for b in (self.speichern, self.step_knopf, self.stl_knopf):
                b.setEnabled(False)
            self._verknuepfung_zeigen()
            return
        self.fehler.hide()
        for b in (self.speichern, self.step_knopf, self.stl_knopf):
            b.setEnabled(True)
        e = self.eigen
        werte = self.werte()
        masse = e.masse(dichte(werte["werkstoff"]))
        zusatz = ""
        if v.TYP == "flansch":
            zusatz = f" · Durchgangsloch {formatiere(durchgangsloch(werte['d_schraube']))} mm (ISO 273 mittel)"
        self.kennwerte.setText(
            f"<b>Masse {formatiere(masse)} kg</b> · Volumen {formatiere(e.volumen / 1000)} cm³ · "
            f"Abmessungen {formatiere(e.groesse[0])} × {formatiere(e.groesse[1])} × {formatiere(e.groesse[2])} mm"
            + zusatz)
        self._anzeigen(anpassen=True)
        self._verknuepfung_zeigen()

    def masse(self) -> float | None:
        if not self.eigen:
            return None
        return self.eigen.masse(dichte(self.werte()["werkstoff"]))

    def _anzeigen(self, *_, anpassen: bool = False):
        if self.form is None:
            return
        if self.schnitt.isChecked():
            e = self.eigen
            # Schnitt längs durch die Teileachse; entfernt wird die Hälfte, die zum Betrachter zeigt
            blick = self.ansicht.blickrichtung()
            i = 0 if abs(blick[0]) > abs(blick[1]) else 1
            pos = e.schwerpunkt[i] + self.schnitt_pos.value() / 100 * e.groesse[i] / 2
            form = geometrie.schneiden(self.form, "xy"[i], pos, behalte_plus=blick[i] < 0)
            self.ansicht.setze_netz(geometrie.netz(form), i, pos, anpassen=anpassen)
        else:
            self.ansicht.setze_netz(geometrie.netz(self.form), anpassen=anpassen)

    # ---------- Speichern / Export ----------
    def teil_speichern(self) -> dict | None:
        if not self.projekt or self.form is None:
            return None
        name = self.name.text().strip() or self.modul.KURZ
        try:
            t = self.projekt.teil_speichern(self.modul.TYP, name, self.werte(), self.masse(), self.eigen.volumen,
                                            self.quellen_ermitteln(), teil_id=self.teil_id)
        except ProjektFehler as exc:
            self.meldung.emit(str(exc), True)
            return None
        self.teil_id = t["id"]
        nummern = sorted({b.nr for b in self.projekt.haengt_ab_von("teil", t["id"])})
        self.meldung.emit(f"Bauteil {t['nr']} „{t['name']}“ gespeichert (Version {t['version']})."
                          + (f" Maße aus {', '.join(nummern)}." if nummern else " Ohne Verknüpfung (Maße von Hand)."),
                          False)
        self._tabelle_fuellen()
        self.gespeichert.emit()
        return t

    def exportieren(self, art: str, ziel: str | None = None) -> Path | None:
        if self.form is None:
            return None
        if ziel is None:
            ordner = self.projekt.pfad.parent if self.projekt else Path.home()
            vorschlag = ordner / f"{self.name.text().strip() or self.modul.KURZ}.{art}"
            filter_ = "STEP (*.step *.stp)" if art == "step" else "STL (*.stl)"
            ziel, _ = QFileDialog.getSaveFileName(self, f"{art.upper()} exportieren", str(vorschlag), filter_)
            if not ziel:
                return None
        try:
            if art == "step":
                pfad = geometrie.step_schreiben(self.form, ziel, self.name.text().strip() or self.modul.KURZ)
            else:
                pfad = geometrie.stl_schreiben(self.form, ziel)
        except (OSError, geometrie.GeometrieFehler) as exc:
            self.meldung.emit(f"Export fehlgeschlagen: {exc}", True)
            return None
        self.meldung.emit(f"{art.upper()}-Datei gespeichert: {Path(pfad).name}", False)
        return Path(pfad)

    # ---------- Liste ----------
    def _tabelle_fuellen(self):
        teile = self.projekt.teile() if self.projekt else []
        self.tabelle.setRowCount(len(teile))
        for z, t in enumerate(teile):
            vorlage = VORLAGEN.get(t["vorlage"])
            art = vorlage.KURZ if vorlage else ("Frei modelliert" if t["vorlage"] == "frei" else t["vorlage"])
            werte = [t["nr"], t["name"], art,
                     f"{formatiere(t['masse'])} kg" if t["masse"] is not None else "–", str(t["version"]),
                     ("⚠ " if t["status"] == NEU_PRUEFEN else "") + t["status"]]
            for s, text in enumerate(werte):
                item = QTableWidgetItem(text)
                item.setData(Qt.UserRole, t["id"])
                self.tabelle.setItem(z, s, item)
        hoehe = self.tabelle.horizontalHeader().height() + 4 + sum(self.tabelle.rowHeight(z) for z in range(len(teile)))
        self.tabelle.setFixedHeight(min(max(hoehe, 60), 200))

    def _gewaehlte_id(self) -> int | None:
        z = self.tabelle.currentRow()
        item = self.tabelle.item(z, 0) if z >= 0 else None
        return item.data(Qt.UserRole) if item else None

    def teil_laden(self, teil_id: int | None):
        if not self.projekt or teil_id is None:
            return
        t = self.projekt.teil(teil_id)
        if t["vorlage"] == "frei":
            self.frei_oeffnen.emit(teil_id)
            return
        i = self.vorlage.findData(t["vorlage"])
        self.vorlage.blockSignals(True)
        self.vorlage.setCurrentIndex(i)
        self.vorlage.blockSignals(False)
        self._vorlage_gewechselt()
        self._setze_werte(t["parameter"])
        self.name.setText(t["name"])
        self.teil_id = teil_id
        self.erzeugen()
        self.meldung.emit(f"{t['nr']} „{t['name']}“ geöffnet (Version {t['version']}).", False)

    def neu_erzeugen(self, teil_id: int | None):
        if not self.projekt or teil_id is None:
            return
        try:
            t = self.projekt.teil_neu_erzeugen(teil_id)
        except ProjektFehler as exc:
            self.meldung.emit(str(exc), True)
            return
        self._tabelle_fuellen()
        if t["vorlage"] != "frei":
            self.teil_laden(t["id"])
        self.meldung.emit(f"{t['nr']} mit den aktuellen Berechnungswerten neu erzeugt (Version {t['version']}).", False)
