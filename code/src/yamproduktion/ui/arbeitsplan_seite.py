"""Seite „Arbeitspläne“: Rohteil, Arbeitsgänge mit Schnittdaten und Zeiten, Eigen-/Fremdfertigung, Stückkosten (MS9)."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..berechnungen.basis import formatiere


def euro(x: float) -> str:
    return f"{x:,.2f}".replace(",", " ").replace(".", ",")
from ..fertigung import arbeitsplan as A
from ..fertigung.schnittdaten import HINWEIS as SCHNITT_HINWEIS
from ..modell import NEU_PRUEFEN, Projekt, ProjektFehler
from .seiten import karte, leeren, scrollbar, titel

ROHTEIL_ARTEN = ("Rundstahl", "Flachstahl", "Blech", "Guss", "Laminat")
ROHTEIL_FELDER = {"Rundstahl": ("d", "l"), "Flachstahl": ("h", "b", "l"), "Blech": ("h", "b", "l"),
                  "Guss": ("d", "l"), "Laminat": ()}
FELD_TEXT = {"d": "Ø d", "l": "Länge l", "b": "Breite b", "h": "Dicke h"}
PARAM_TEXT = {"flaeche": "Querschnitt mm²", "umfang": "Schnittlänge mm", "dicke": "Dicke mm", "d": "Ø mm",
              "seiten": "Seiten", "weg": "Fräsweg mm", "tiefe": "Tiefe mm", "d_fraeser": "Fräser-Ø mm",
              "anzahl": "Anzahl", "abschnitte": "Abschnitte (Ø von, Ø bis, Länge; …)"}
SPALTEN = ["AG", "Arbeitsgang", "Beschreibung", "Maschine", "t_r min", "t_h min", "t_e min", "€ je Stück"]


def _zahl(text: str) -> float | None:
    try:
        return float(text.replace(" ", "").replace(",", ".").strip())
    except ValueError:
        return None


class ArbeitsplanSeite(QWidget):
    meldung = Signal(str, bool)
    gespeichert = Signal()

    def __init__(self):
        super().__init__()
        self.projekt: Projekt | None = None
        self.teil_id: int | None = None
        self.plan: dict | None = None
        self.kalk: A.Kalkulation | None = None
        self._fuellt = False

        inhalt = QWidget()
        lay = QVBoxLayout(inhalt)
        lay.setContentsMargins(32, 24, 32, 24)
        lay.addWidget(titel("Arbeitspläne", "Je Bauteil: Rohteil, Arbeitsgänge mit Schnittdaten und Zeiten, Eigen- oder "
                                            "Fremdfertigung und Stückkosten. Der Vorschlag kommt aus der 3D-Geometrie."))
        # ---- Kopf: Teil, Vorschlag, Speichern
        k, kl = karte()
        zeile = QHBoxLayout()
        self.teil_wahl = QComboBox()
        self.teil_wahl.setAccessibleName("Bauteil")
        self.teil_wahl.setMinimumContentsLength(24)
        self.teil_wahl.activated.connect(lambda _: self.teil_laden(self.teil_wahl.currentData()))
        zeile.addWidget(self.teil_wahl, 2)
        b = QPushButton("Vorschlag aus der Geometrie")
        b.setToolTip("Rohteil und Arbeitsgänge neu aus dem 3D-Teil ableiten (ersetzt den aktuellen Plan)")
        b.clicked.connect(lambda: self.vorschlag())
        zeile.addWidget(b)
        self.speichern = QPushButton("Arbeitsplan speichern")
        self.speichern.setObjectName("Haupt")
        self.speichern.setShortcut("Ctrl+S")
        self.speichern.clicked.connect(lambda: self.plan_speichern())
        zeile.addWidget(self.speichern)
        self.pdf_knopf = QPushButton("PDF …")
        self.pdf_knopf.clicked.connect(lambda: self.pdf())
        zeile.addWidget(self.pdf_knopf)
        kl.addLayout(zeile)
        self.status = QLabel()
        self.status.setObjectName("Klein")
        self.status.setWordWrap(True)
        kl.addWidget(self.status)

        # ---- Rohteil und Fertigung
        zeile = QHBoxLayout()
        zeile.setSpacing(24)
        links = QFormLayout()
        self.roh_art = QComboBox()
        self.roh_art.addItems(ROHTEIL_ARTEN)
        self.roh_art.activated.connect(lambda _: self._roh_art_geaendert())
        links.addRow("Rohteil", self.roh_art)
        self.roh_box = QHBoxLayout()
        links.addRow("Maße (mm)", self.roh_box)
        self.roh_text = QLabel()
        self.roh_text.setWordWrap(True)
        links.addRow("", self.roh_text)
        zeile.addLayout(links, 3)
        rechts = QFormLayout()
        self.fertigung = QComboBox()
        self.fertigung.addItem("Eigenfertigung", "eigen")
        self.fertigung.addItem("Fremdfertigung", "fremd")
        self.fertigung.activated.connect(lambda _: self._setze_plan("fertigung", self.fertigung.currentData()))
        rechts.addRow("Fertigung", self.fertigung)
        self.losgroesse = QSpinBox()
        self.losgroesse.setRange(1, 10000)
        self.losgroesse.valueChanged.connect(lambda v: self._setze_plan("losgroesse", v))
        rechts.addRow("Losgröße", self.losgroesse)
        self.preis_fremd = QLineEdit()
        self.preis_fremd.setPlaceholderText("leer = Schätzung")
        self.preis_fremd.setToolTip("Preis je Stück aus dem Angebot des Fertigers (€)")
        self.preis_fremd.editingFinished.connect(
            lambda: self._setze_plan("preis_fremd", _zahl(self.preis_fremd.text())))
        rechts.addRow("Angebot €/Stück", self.preis_fremd)
        zeile.addLayout(rechts, 2)
        kl.addLayout(zeile)
        lay.addWidget(k)

        # ---- Arbeitsgänge
        k, kl = karte()
        kopf = QHBoxLayout()
        t = QLabel("Arbeitsgänge")
        t.setObjectName("Abschnitt")
        kopf.addWidget(t)
        kopf.addStretch()
        self.neu_art = QComboBox()
        for art, (text, _, _) in A.ARTEN.items():
            self.neu_art.addItem(text, art)
        kopf.addWidget(self.neu_art)
        b = QPushButton("+ Arbeitsgang")
        b.clicked.connect(lambda: self.gang_neu())
        kopf.addWidget(b)
        b = QPushButton("Löschen")
        b.clicked.connect(lambda: self.gang_loeschen())
        kopf.addWidget(b)
        kl.addLayout(kopf)
        self.tabelle = QTableWidget(0, len(SPALTEN))
        self.tabelle.setHorizontalHeaderLabels(SPALTEN)
        self.tabelle.verticalHeader().hide()
        self.tabelle.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabelle.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tabelle.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.tabelle.setMinimumHeight(230)
        self.tabelle.itemChanged.connect(self._zelle_geaendert)
        self.tabelle.currentCellChanged.connect(lambda *_: self._details())
        kl.addWidget(self.tabelle)
        tipp = QLabel("Beschreibung, Maschine, t_r und t_e sind änderbar. t_e leer lassen = aus den Schnittdaten "
                      "berechnen.")
        tipp.setObjectName("Klein")
        kl.addWidget(tipp)
        unten = QHBoxLayout()
        unten.setSpacing(24)
        self.param_lay = QFormLayout()
        unten.addLayout(self.param_lay, 2)
        self.rechenweg = QLabel()
        self.rechenweg.setObjectName("Klein")
        self.rechenweg.setWordWrap(True)
        unten.addWidget(self.rechenweg, 3)
        kl.addLayout(unten)
        lay.addWidget(k)

        # ---- Kosten
        k, kl = karte()
        self.kosten = QLabel()
        self.kosten.setWordWrap(True)
        kl.addWidget(self.kosten)
        self.hinweis = QLabel(SCHNITT_HINWEIS + " " + A.SCHAETZ_HINWEIS)
        self.hinweis.setObjectName("Klein")
        self.hinweis.setWordWrap(True)
        kl.addWidget(self.hinweis)
        lay.addWidget(k)
        lay.addStretch()

        aussen = QVBoxLayout(self)
        aussen.setContentsMargins(0, 0, 0, 0)
        aussen.addWidget(scrollbar(inhalt))
        self._anzeigen()

    # ================================================================ Projekt
    def setze_projekt(self, projekt: Projekt):
        self.projekt = projekt
        self.teil_id = None
        self.plan = None
        self.laden()

    def laden(self):
        self.teil_wahl.clear()
        if not self.projekt:
            return
        for t in self.projekt.teile():
            ap = self.projekt.arbeitsplan_von_teil(t["id"])
            zeichen = "" if ap is None else (" ⚠" if ap["status"] == NEU_PRUEFEN else " ✓")
            self.teil_wahl.addItem(f"{t['nr']} {t['name']}{zeichen}", t["id"])
        if self.teil_id is None and self.teil_wahl.count():
            self.teil_laden(self.teil_wahl.itemData(0))
        elif self.teil_id is not None:
            self.teil_wahl.setCurrentIndex(max(0, self.teil_wahl.findData(self.teil_id)))
            self._anzeigen()

    def teil_laden(self, teil_id: int | None):
        if teil_id is None:
            return
        self.teil_id = teil_id
        self.teil_wahl.setCurrentIndex(max(0, self.teil_wahl.findData(teil_id)))
        ap = self.projekt.arbeitsplan_von_teil(teil_id)
        if ap is None:
            self.vorschlag(melden=False)
            return
        self.plan = ap["daten"]
        self._anzeigen()

    def vorschlag(self, melden: bool = True):
        if self.teil_id is None:
            return
        try:
            self.plan = self.projekt.arbeitsplan_vorschlag(self.teil_id)
        except (ProjektFehler, ValueError) as exc:
            self.plan = None
            self.meldung.emit(f"Kein Vorschlag möglich: {exc}", True)
        else:
            if melden:
                self.meldung.emit("Arbeitsplan aus der Geometrie vorgeschlagen – bitte prüfen und speichern.", False)
        self._anzeigen()

    # ================================================================ Ändern
    def _setze_plan(self, schluessel, wert):
        if self._fuellt or self.plan is None:
            return
        self.plan[schluessel] = wert
        self._anzeigen()

    def _roh_art_geaendert(self):
        if self.plan is None:
            return
        roh = self.plan["rohteil"]
        roh["art"] = self.roh_art.currentText()
        for f in ROHTEIL_FELDER[roh["art"]]:
            roh.setdefault(f, 100.0)
        self._anzeigen()

    def setze_rohteil(self, feld: str, wert: float):
        if self.plan is not None and wert is not None and wert > 0:
            self.plan["rohteil"][feld] = wert
            self._anzeigen()

    def gang_neu(self, art: str | None = None, **felder) -> dict | None:
        if self.plan is None:
            return None
        art = art or self.neu_art.currentData()
        text, maschine, tr = A.ARTEN[art]
        nr = max((v["nr"] for v in self.plan["vorgaenge"]), default=0) + 10
        v = {"nr": nr, "art": art, "text": text, "maschine": maschine, "tr": tr, "p": {}, "te": None}
        if art in ("manuell", "schweissen", "laminieren", "guss"):
            v["te"] = 10.0
        v.update(felder)
        self.plan["vorgaenge"].append(v)
        self._anzeigen()
        self.tabelle.setCurrentCell(len(self.plan["vorgaenge"]) - 1, 2)
        return v

    def gang_loeschen(self, zeile: int | None = None):
        zeile = self.tabelle.currentRow() if zeile is None else zeile
        if self.plan and 0 <= zeile < len(self.plan["vorgaenge"]):
            self.plan["vorgaenge"].pop(zeile)
            self._anzeigen()

    def setze_gang(self, zeile: int, schluessel: str, wert):
        v = self.plan["vorgaenge"][zeile]
        if schluessel in ("text", "maschine", "tr", "te", "nr"):
            v[schluessel] = wert
        else:
            v.setdefault("p", {})[schluessel] = wert
        self._anzeigen()

    def _zelle_geaendert(self, item: QTableWidgetItem):
        if self._fuellt or self.plan is None:
            return
        z, s = item.row(), item.column()
        text = item.text()
        if s == 0 and _zahl(text) is not None:
            self.setze_gang(z, "nr", int(_zahl(text)))
        elif s == 2:
            self.setze_gang(z, "text", text)
        elif s == 3:
            self.setze_gang(z, "maschine", text.strip())
        elif s == 4:
            self.setze_gang(z, "tr", _zahl(text) or 0.0)
        elif s == 6:
            self.setze_gang(z, "te", _zahl(text) if text.strip() else None)
        else:
            self._anzeigen()

    # ================================================================ Anzeigen
    def _anzeigen(self):
        hat = self.plan is not None and self.projekt is not None and self.teil_id is not None
        for w in (self.speichern, self.pdf_knopf, self.roh_art, self.fertigung, self.losgroesse, self.preis_fremd):
            w.setEnabled(hat)
        if not hat:
            self.tabelle.setRowCount(0)
            self.kosten.setText("Zuerst ein Bauteil anlegen (Bauteile 3D oder Modellieren)." if self.projekt else "")
            self.status.setText("")
            return
        p = self.plan
        try:
            self.kalk = self.projekt.kalkulation_teil(self.teil_id, p)
        except ProjektFehler as exc:
            self.kalk = None
            self.kosten.setText(f"⚠ {exc}")
            return
        k = self.kalk
        self._fuellt = True
        roh = p["rohteil"]
        self.roh_art.setCurrentText(roh.get("art", "Rundstahl"))
        leeren(self.roh_box)
        for f in ROHTEIL_FELDER.get(roh.get("art"), ()):
            self.roh_box.addWidget(QLabel(FELD_TEXT[f]))
            e = QLineEdit(formatiere(float(roh.get(f, 0))))
            e.setMaximumWidth(90)
            e.setAccessibleName(FELD_TEXT[f])
            e.editingFinished.connect(lambda f=f, e=e: self.setze_rohteil(f, _zahl(e.text())))
            self.roh_box.addWidget(e)
        self.roh_box.addStretch()
        self.roh_text.setText(f"{k.rohteil_text} · {formatiere(k.rohteil_masse)} kg")
        self.fertigung.setCurrentIndex(self.fertigung.findData(p.get("fertigung", "eigen")))
        self.losgroesse.setValue(int(p.get("losgroesse") or 1))
        self.preis_fremd.setText("" if p.get("preis_fremd") in (None, "") else euro(p["preis_fremd"]))
        self.preis_fremd.setEnabled(p.get("fertigung") == "fremd")
        saetze = self.projekt.kostensaetze()["stundensaetze"]
        zeile = self.tabelle.currentRow()
        self.tabelle.setRowCount(len(k.gaenge))
        for i, g in enumerate(k.gaenge):
            kosten = (g.tr / k.losgroesse + g.te) / 60 * saetze.get(g.maschine, 0)
            werte = [str(g.nr), A.ARTEN.get(g.art, (g.art,))[0], g.text, g.maschine, formatiere(g.tr),
                     "–" if g.th is None else formatiere(g.th),
                     (formatiere(g.te) + (" ✎" if g.von_hand else "")) if g.te else "–", euro(kosten)]
            for j, w in enumerate(werte):
                item = QTableWidgetItem(w)
                if j in (1, 5, 7):
                    item.setFlags(item.flags() & ~item.flags().ItemIsEditable)
                if g.fehler:
                    item.setToolTip(g.fehler)
                self.tabelle.setItem(i, j, item)
        if 0 <= zeile < len(k.gaenge):
            self.tabelle.setCurrentCell(zeile, max(0, self.tabelle.currentColumn()))
        self._fuellt = False
        self._details()
        art_text = "Fremdfertigung" if k.fremd else "Eigenfertigung"
        fremd = ""
        if k.fremd:
            fremd = " (Schätzung: Eigenkosten + 25 %, Angebot einholen)" if k.fremd_geschaetzt else " (laut Angebot)"
        self.kosten.setText(
            f"<b>Stückkosten {euro(k.stueck)} €</b>{fremd} · {art_text} · Material {euro(k.material)} € · "
            f"Fertigung {euro(k.fertigung)} € · Stückzeit {formatiere(k.te_summe)} min · Rüstzeit "
            f"{formatiere(k.tr_summe)} min je Los · Los ({k.losgroesse} Stück) {euro(k.los)} €"
            + ("<br>⚠ " + "<br>⚠ ".join(k.fehler) if k.fehler else ""))
        ap = self.projekt.arbeitsplan_von_teil(self.teil_id)
        if ap is None:
            self.status.setText("Noch nicht gespeichert – Vorschlag aus der Geometrie.")
        else:
            self.status.setText(f"{ap['nr']} · Version {ap['version']} · {ap['status']}"
                                + (" – das Bauteil wurde geändert, bitte prüfen und neu speichern."
                                   if ap["status"] == NEU_PRUEFEN else ""))

    def _details(self):
        leeren(self.param_lay)
        z = self.tabelle.currentRow()
        if self.plan is None or not 0 <= z < len(self.plan["vorgaenge"]) or self.kalk is None:
            self.rechenweg.setText("")
            return
        v = self.plan["vorgaenge"][z]
        g = self.kalk.gaenge[z]
        for schluessel, wert in v.get("p", {}).items():
            if schluessel == "schlichten":
                continue
            if schluessel == "abschnitte":
                text = "; ".join(" ".join(formatiere(x) for x in a) for a in wert)
            else:
                text = formatiere(float(wert))
            e = QLineEdit(text)
            if schluessel == "abschnitte":
                e.setMinimumWidth(300)
            e.editingFinished.connect(lambda s=schluessel, e=e, z=z: self._param(z, s, e.text()))
            self.param_lay.addRow(PARAM_TEXT.get(schluessel, schluessel), e)
        weg = "<br>".join(g.rechenweg) if g.rechenweg else ("Zeit von Hand eingetragen." if g.von_hand else "")
        self.rechenweg.setText(f"<b>Rechenweg AG {g.nr}</b><br>{weg}" + (f"<br>⚠ {g.fehler}" if g.fehler else ""))

    def _param(self, zeile: int, schluessel: str, text: str):
        if schluessel == "abschnitte":
            try:
                wert = [[float(x.replace(",", ".")) for x in teil.split()] for teil in text.split(";") if teil.strip()]
                assert all(len(a) == 3 for a in wert)
            except (ValueError, AssertionError):
                self.meldung.emit("Abschnitte bitte als „Ø von  Ø bis  Länge; …“ eingeben.", True)
                return
        else:
            wert = _zahl(text)
            if wert is None:
                return
        self.setze_gang(zeile, schluessel, wert)

    # ================================================================ Speichern
    def plan_speichern(self) -> dict | None:
        if self.plan is None:
            return None
        ap = self.projekt.arbeitsplan_speichern(self.teil_id, self.plan)
        self.meldung.emit(f"{ap['nr']} gespeichert – Stückkosten {euro(ap['kosten'] or 0)} €.", False)
        self.laden()
        self.gespeichert.emit()
        return ap

    def pdf(self, ziel: str | None = None) -> Path | None:
        if self.plan is None or self.kalk is None:
            return None
        t = self.projekt.teil(self.teil_id)
        if ziel is None:
            ziel, _ = QFileDialog.getSaveFileName(self, "Arbeitsplan speichern",
                                                  str(self.projekt.pfad.parent / f"Arbeitsplan_{t['nr']}.pdf"),
                                                  "PDF (*.pdf)")
            if not ziel:
                return None
        from ..pdf import arbeitsplan_erstellen
        try:
            pfad = arbeitsplan_erstellen(t, self.plan, self.kalk, ziel, self.projekt.name)
        except OSError as exc:
            self.meldung.emit(f"Speichern fehlgeschlagen: {exc}", True)
            return None
        self.meldung.emit(f"Arbeitsplan gespeichert: {Path(pfad).name}", False)
        return Path(pfad)
