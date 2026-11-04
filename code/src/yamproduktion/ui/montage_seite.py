"""Seite „Montage“ (MS10): Montageplan je Baugruppe, Montageplatte, Explosionsdarstellung, Montageanleitung (PDF)."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QPlainTextEdit, QPushButton, QSlider, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..berechnungen.basis import formatiere
from ..cad import vorlagen
from ..modell import NEU_PRUEFEN, Projekt, ProjektFehler
from ..montage import montageplan as M, szene as SZ
from .ansicht3d import ANSICHTEN, Ansicht3D
from .seiten import karte, scrollbar, titel


def _zahl(text: str) -> float | None:
    try:
        return float(text.replace(" ", "").replace(",", ".").strip())
    except ValueError:
        return None


def szene_bilder(szene: SZ.Szene, plan: dict, explosion, groesse=(1000, 560)) -> dict:
    """PNG-Bilder für die Anleitung: Explosionsdarstellung und je Schritt der Montagezustand (neue Teile farbig).
    Immer mit hellem Hintergrund, unabhängig vom Thema der Oberfläche."""
    w = Ansicht3D()
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(255, 255, 255))
    pal.setColor(QPalette.WindowText, QColor(30, 30, 30))
    w.setPalette(pal)
    w.resize(*groesse)

    def png() -> bytes:
        daten = QByteArray()
        puffer = QBuffer(daten)
        puffer.open(QIODevice.WriteOnly)
        w.grab().save(puffer, "PNG")
        return bytes(daten)

    bilder = {}
    ohne_vorrichtung = [i != szene.vorrichtung for i in range(szene.anzahl)]
    w.setze_netz(szene.netz(explosion, ohne_vorrichtung), anpassen=True)
    bilder["explosion"] = png()
    w.setze_netz(szene.netz(), anpassen=True)              # Rahmen: ganze Baugruppe mit Vorrichtung
    for s in plan.get("schritte", []):
        sichtbar, neu = SZ.schritt_ansicht(szene, plan, s["nr"])
        w.setze_netz(szene.netz(None, sichtbar), anpassen=False, gruppen=szene.gruppen(neu, sichtbar))
        bilder[s["nr"]] = png()
    w.deleteLater()
    return bilder


class MontageSeite(QWidget):
    meldung = Signal(str, bool)
    gespeichert = Signal()

    def __init__(self):
        super().__init__()
        self.projekt: Projekt | None = None
        self.gid: int | None = None
        self.definition: dict = {}
        self.plan: dict | None = None
        self.erg = None
        self.szene: SZ.Szene | None = None
        self.explosion_basis = None
        self._fuellt = False

        inhalt = QWidget()
        lay = QVBoxLayout(inhalt)
        lay.setContentsMargins(32, 24, 32, 24)
        lay.addWidget(titel("Montage", "Je Baugruppe: Montageschritte mit Teilen, Werkzeugen, Anzugsmomenten und "
                                       "Prüfschritten, die Montageplatte als Vorrichtung, Explosionsdarstellung und "
                                       "die Montageanleitung als PDF mit Bildern aus dem CAD."))
        # ---- Kopf
        k, kl = karte()
        zeile = QHBoxLayout()
        self.gruppe_wahl = QComboBox()
        self.gruppe_wahl.setAccessibleName("Baugruppe")
        self.gruppe_wahl.setMinimumContentsLength(24)
        self.gruppe_wahl.activated.connect(lambda _: self.baugruppe_laden(self.gruppe_wahl.currentData()))
        zeile.addWidget(self.gruppe_wahl, 2)
        b = QPushButton("Vorschlag aus der Baugruppe")
        b.setToolTip("Reihenfolge, Werkzeuge, Anzugsmomente und Prüfschritte neu vorschlagen (ersetzt den Plan)")
        b.clicked.connect(lambda: self.vorschlag())
        zeile.addWidget(b)
        self.speichern = QPushButton("Montageplan speichern")
        self.speichern.setObjectName("Haupt")
        self.speichern.setShortcut("Ctrl+S")
        self.speichern.clicked.connect(lambda: self.plan_speichern())
        zeile.addWidget(self.speichern)
        self.pdf_knopf = QPushButton("Anleitung als PDF …")
        self.pdf_knopf.clicked.connect(lambda: self.pdf())
        zeile.addWidget(self.pdf_knopf)
        kl.addLayout(zeile)
        self.status = QLabel()
        self.status.setObjectName("Klein")
        self.status.setWordWrap(True)
        kl.addWidget(self.status)
        zeile = QHBoxLayout()
        zeile.addWidget(QLabel("Vorrichtung"))
        self.vorrichtung = QComboBox()
        self.vorrichtung.setAccessibleName("Montagevorrichtung")
        self.vorrichtung.activated.connect(lambda _: self.vorrichtung_setzen(self.vorrichtung.currentData()))
        zeile.addWidget(self.vorrichtung, 2)
        b = QPushButton("Montageplatte aus der Baugruppe erzeugen")
        b.setToolTip("Auflagen an der längsten freien Stelle des Grundteils, Achshöhe nach dem größten Radius. "
                     "Das Teil erscheint unter „Bauteile (3D)“ und ist dort änderbar.")
        b.clicked.connect(lambda: self.montageplatte_erzeugen())
        zeile.addWidget(b)
        zeile.addStretch()
        kl.addLayout(zeile)
        self.aufnahme = QLabel()
        self.aufnahme.setObjectName("Klein")
        self.aufnahme.setWordWrap(True)
        kl.addWidget(self.aufnahme)
        lay.addWidget(k)

        oben = QHBoxLayout()
        oben.setSpacing(16)
        # ---- links: Schritte
        links, ll = karte()
        kopf = QHBoxLayout()
        t = QLabel("Montageschritte")
        t.setObjectName("Abschnitt")
        kopf.addWidget(t)
        kopf.addStretch()
        for text, tipp, fn in (("↑", "Schritt nach oben", lambda: self.schritt_schieben(-1)),
                               ("↓", "Schritt nach unten", lambda: self.schritt_schieben(1)),
                               ("+ Schritt", "Neuen Schritt nach dem gewählten einfügen", lambda: self.schritt_neu()),
                               ("Löschen", "Gewählten Schritt löschen", lambda: self.schritt_loeschen())):
            b = QPushButton(text)
            b.setToolTip(tipp)
            b.clicked.connect(fn)
            kopf.addWidget(b)
        ll.addLayout(kopf)
        self.liste = QListWidget()
        self.liste.setAccessibleName("Montageschritte")
        self.liste.setMinimumHeight(190)
        self.liste.currentRowChanged.connect(lambda _: self._details())
        ll.addWidget(self.liste)
        form = QFormLayout()
        self.f_titel = QLineEdit()
        self.f_titel.editingFinished.connect(lambda: self._setze("titel", self.f_titel.text().strip()))
        form.addRow("Titel", self.f_titel)
        self.f_text = QPlainTextEdit()
        self.f_text.setFixedHeight(84)
        self.f_text.textChanged.connect(lambda: self._setze("text", self.f_text.toPlainText(), liste=False))
        form.addRow("Tätigkeit", self.f_text)
        self.f_teile = QLabel()
        self.f_teile.setWordWrap(True)
        form.addRow("Teile", self.f_teile)
        self.f_werkzeuge = QPlainTextEdit()
        self.f_werkzeuge.setFixedHeight(64)
        self.f_werkzeuge.setPlaceholderText("ein Werkzeug je Zeile")
        self.f_werkzeuge.textChanged.connect(lambda: self._setze("werkzeuge", self._zeilen(self.f_werkzeuge), False))
        form.addRow("Werkzeuge", self.f_werkzeuge)
        self.f_momente = QTableWidget(0, 3)
        self.f_momente.setHorizontalHeaderLabels(["Verbindung", "M_A N·m", "Quelle"])
        self.f_momente.verticalHeader().hide()
        self.f_momente.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.f_momente.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.f_momente.setFixedHeight(70)
        self.f_momente.itemChanged.connect(self._moment_geaendert)
        form.addRow("Anzugsmomente", self.f_momente)
        self.f_pruefung = QPlainTextEdit()
        self.f_pruefung.setFixedHeight(76)
        self.f_pruefung.setPlaceholderText("ein Prüfschritt je Zeile")
        self.f_pruefung.textChanged.connect(lambda: self._setze("pruefung", self._zeilen(self.f_pruefung), False))
        form.addRow("Prüfschritte", self.f_pruefung)
        self.f_zeit = QDoubleSpinBox()
        self.f_zeit.setRange(0, 10000)
        self.f_zeit.setDecimals(1)
        self.f_zeit.setSuffix(" min")
        self.f_zeit.valueChanged.connect(lambda v: self._setze("zeit", float(v)))
        form.addRow("Zeit (Schätzwert)", self.f_zeit)
        ll.addLayout(form)
        self.meldungen = QLabel()
        self.meldungen.setObjectName("Klein")
        self.meldungen.setWordWrap(True)
        ll.addWidget(self.meldungen)
        oben.addWidget(links, 3)

        # ---- rechts: 3D
        rechts, rl = karte()
        leiste = QHBoxLayout()
        for name in ANSICHTEN:
            b = QPushButton(name)
            b.setObjectName("Werkzeug")
            b.clicked.connect(lambda _=False, n=name: self.ansicht.ansicht(n))
            leiste.addWidget(b)
        leiste.addStretch()
        self.nur_bis = QCheckBox("Zustand nach dem Schritt")
        self.nur_bis.setToolTip("Nur die bis zum gewählten Schritt eingebauten Teile zeigen, neue farbig")
        self.nur_bis.setChecked(True)
        self.nur_bis.toggled.connect(lambda _: self._ansicht_aktualisieren(anpassen=False))
        leiste.addWidget(self.nur_bis)
        rl.addLayout(leiste)
        self.ansicht = Ansicht3D()
        self.ansicht.setFixedHeight(480)
        self.ansicht.hinweis = "Zuerst eine Baugruppe speichern."
        rl.addWidget(self.ansicht)
        zeile = QHBoxLayout()
        zeile.addWidget(QLabel("Explosion"))
        self.explosion = QSlider(Qt.Horizontal)
        self.explosion.setRange(0, 150)
        self.explosion.setAccessibleName("Explosionsabstand in Prozent")
        self.explosion.valueChanged.connect(lambda _: self._ansicht_aktualisieren(anpassen=True))
        zeile.addWidget(self.explosion, 1)
        self.explosion_text = QLabel("0 %")
        self.explosion_text.setMinimumWidth(44)
        zeile.addWidget(self.explosion_text)
        rl.addLayout(zeile)
        self.summe = QLabel()
        self.summe.setWordWrap(True)
        rl.addWidget(self.summe)
        rl.addStretch(1)
        oben.addWidget(rechts, 4)
        lay.addLayout(oben, 1)
        hinweis = QLabel(M.HINWEIS)
        hinweis.setObjectName("Klein")
        hinweis.setWordWrap(True)
        lay.addWidget(hinweis)

        aussen = QVBoxLayout(self)
        aussen.setContentsMargins(0, 0, 0, 0)
        aussen.addWidget(scrollbar(inhalt))

    # ---------- Projekt ----------
    def setze_projekt(self, projekt: Projekt):
        self.projekt = projekt
        self.gid = None
        self.plan = None
        self.laden()

    def laden(self):
        if not self.projekt:
            return
        self._fuellt = True
        self.gruppe_wahl.clear()
        for g in self.projekt.baugruppen():
            mp = self.projekt.montageplan_von_baugruppe(g["id"])
            zeichen = "" if mp is None else (" ⚠" if mp["status"] == NEU_PRUEFEN else " ✓")
            self.gruppe_wahl.addItem(f"{g['nr']} {g['name']}{zeichen}", g["id"])
        self._vorrichtungen_fuellen()
        self._fuellt = False
        if self.gruppe_wahl.count() == 0:
            self.gid, self.plan, self.szene = None, None, None
            self.status.setText("Noch keine Baugruppe – zuerst unter „Baugruppen“ eine anlegen und speichern.")
            self.liste.clear()
            self.ansicht.setze_netz(None)
            return
        gid = self.gid if self.gid is not None and self.gruppe_wahl.findData(self.gid) >= 0 else \
            self.gruppe_wahl.itemData(0)
        self.baugruppe_laden(gid)

    def _vorrichtungen_fuellen(self):
        self.vorrichtung.clear()
        self.vorrichtung.addItem("ohne Vorrichtung", None)
        for t in self.projekt.montageplatten():
            self.vorrichtung.addItem(f"{t['nr']} {t['name']}", t["id"])

    def baugruppe_laden(self, gid: int | None):
        if gid is None or not self.projekt:
            return
        self.gid = gid
        self.gruppe_wahl.setCurrentIndex(max(0, self.gruppe_wahl.findData(gid)))
        g = self.projekt.baugruppe(gid)
        self.definition = g["definition"]
        self.erg = self.projekt.baugruppe_bauen(self.definition)
        mp = self.projekt.montageplan_von_baugruppe(gid)
        if mp is None:
            self.plan = self._vorschlag_rechnen(None)
            text = "Noch nicht gespeichert – Vorschlag aus der Baugruppe."
        else:
            self.plan = mp["daten"]
            text = f"{mp['nr']} · Version {mp['version']} · {mp['status']}"
            if mp["status"] == NEU_PRUEFEN:
                text += " – die Baugruppe oder die Vorrichtung hat sich geändert, bitte prüfen."
        self.status.setText(text)
        self._szene_bauen()
        self._anzeigen()

    def _vorschlag_rechnen(self, vorrichtung_id):
        try:
            return self.projekt.montageplan_vorschlag(self.gid, vorrichtung_id)
        except ProjektFehler as exc:
            self.meldung.emit(str(exc), True)
            return {"vorrichtung": None, "schritte": [], "hinweise": []}

    def vorschlag(self):
        if self.gid is None:
            return
        self.plan = self._vorschlag_rechnen(self.vorrichtung.currentData())
        self.status.setText("Vorschlag neu erzeugt – noch nicht gespeichert.")
        self._szene_bauen()
        self._anzeigen()

    def _szene_bauen(self):
        self.szene = None
        self.explosion_basis = None
        if not self.erg or not self.erg.exemplare:
            self.ansicht.setze_netz(None)
            return
        form = matrix = None
        vid = (self.plan or {}).get("vorrichtung")
        if vid:
            try:
                form = self.projekt.teil_form(int(vid))["form"]
                b = M.basis_einbau(self.definition)
                matrix = next((x.matrix for x in self.erg.exemplare if x.einbau == b), None)
            except ProjektFehler as exc:
                self.meldung.emit(str(exc), True)
        self.szene = SZ.aufbauen(self.erg, form, matrix)
        self.explosion_basis = SZ.verschiebungen(self.szene, M.explosion(self.definition, self.erg, 1.0))

    # ---------- Vorrichtung ----------
    def vorrichtung_setzen(self, teil_id: int | None):
        if self.plan is None:
            return
        v = None
        if teil_id:
            t = self.projekt.teil(teil_id)
            v = {"id": t["id"], "nr": t["nr"], "name": t["name"]}
        M.vorrichtung_umstellen(self.plan, v)
        self._szene_bauen()
        self._anzeigen()

    def montageplatte_erzeugen(self) -> dict | None:
        if self.gid is None:
            return None
        alt = self.vorrichtung.currentData()
        try:
            t = self.projekt.montageplatte_anlegen(self.gid, teil_id=alt)
            _, hinweise = self.projekt.montageplatte_vorschlag(self.gid)
        except ProjektFehler as exc:
            self.meldung.emit(str(exc), True)
            return None
        self._vorrichtungen_fuellen()
        self.vorrichtung.setCurrentIndex(self.vorrichtung.findData(t["id"]))
        if alt == t["id"]:
            self._szene_bauen()
            self._anzeigen()
        else:
            self.vorrichtung_setzen(t["id"])
        self.meldung.emit(f"{t['nr']} {t['name']} gespeichert. " + " ".join(hinweise), False)
        return t

    # ---------- Schritte ----------
    def _zeilen(self, feld: QPlainTextEdit) -> list[str]:
        return [z.strip() for z in feld.toPlainText().splitlines() if z.strip()]

    def _aktuell(self) -> dict | None:
        i = self.liste.currentRow()
        if self.plan is None or not (0 <= i < len(self.plan["schritte"])):
            return None
        return self.plan["schritte"][i]

    def _setze(self, feld: str, wert, liste: bool = True):
        s = self._aktuell()
        if self._fuellt or s is None or s.get(feld) == wert:
            return
        s[feld] = wert
        if liste and feld == "titel":
            self.liste.currentItem().setText(self._listentext(s))
        self._summe()

    def _moment_geaendert(self, item: QTableWidgetItem):
        s = self._aktuell()
        if self._fuellt or s is None or item.row() >= len(s["momente"]):
            return
        m = s["momente"][item.row()]
        if item.column() == 1:
            alt, m["wert"] = m.get("wert"), _zahl(item.text())
            if alt not in (None, "") and m["wert"] is not None:      # Wert auch in Text und Prüfschritten nachziehen
                vorher, nachher = f"M_A = {formatiere(float(alt))} N·m", f"M_A = {formatiere(m['wert'])} N·m"
                s["text"] = s.get("text", "").replace(vorher, nachher)
                s["pruefung"] = [q.replace(vorher, nachher) for q in s.get("pruefung", [])]
            m["quelle"] = "von Hand eingetragen" if m["wert"] is not None else m.get("quelle", "")
            self._fuellt = True
            self.f_momente.item(item.row(), 2).setText(m["quelle"])
            self.f_text.setPlainText(s.get("text", ""))
            self.f_pruefung.setPlainText("\n".join(s.get("pruefung", [])))
            self._fuellt = False
        elif item.column() == 0:
            m["was"] = item.text()
        self._summe()

    def setze_moment(self, zeile: int, wert: float):
        self.f_momente.item(zeile, 1).setText(formatiere(wert))

    def schritt_neu(self, titel_: str = "Neuer Schritt", **felder) -> dict | None:
        if self.plan is None:
            return None
        s = M._schritt(titel_, felder.pop("text", ""), **felder)
        i = self.liste.currentRow() + 1 if self.liste.currentRow() >= 0 else len(self.plan["schritte"])
        self.plan["schritte"].insert(i, s)
        M.nummerieren(self.plan)
        self._anzeigen(i)
        return s

    def schritt_loeschen(self, zeile: int | None = None):
        i = self.liste.currentRow() if zeile is None else zeile
        if self.plan is None or not (0 <= i < len(self.plan["schritte"])):
            return
        self.plan["schritte"].pop(i)
        M.nummerieren(self.plan)
        self._anzeigen(min(i, len(self.plan["schritte"]) - 1))

    def schritt_schieben(self, richtung: int, zeile: int | None = None):
        i = self.liste.currentRow() if zeile is None else zeile
        j = i + richtung
        if self.plan is None or not (0 <= i < len(self.plan["schritte"])) or not (0 <= j < len(self.plan["schritte"])):
            return
        s = self.plan["schritte"]
        s[i], s[j] = s[j], s[i]
        M.nummerieren(self.plan)
        self._anzeigen(j)

    # ---------- Anzeige ----------
    @staticmethod
    def _listentext(s: dict) -> str:
        return f"{s['nr']}. {s['titel']}"

    def _anzeigen(self, zeile: int = 0):
        self._fuellt = True
        self.liste.clear()
        for s in (self.plan or {}).get("schritte", []):
            self.liste.addItem(QListWidgetItem(self._listentext(s)))
        self.vorrichtung.setCurrentIndex(max(0, self.vorrichtung.findData((self.plan or {}).get("vorrichtung"))))
        self._fuellt = False
        self._aufnahme_zeigen()
        if self.liste.count():
            self.liste.setCurrentRow(max(0, min(zeile, self.liste.count() - 1)))
        else:
            self._details()
        self._ansicht_aktualisieren(anpassen=True)

    def _aufnahme_zeigen(self):
        vid = (self.plan or {}).get("vorrichtung")
        if not vid:
            self.aufnahme.setText("Ohne Vorrichtung wird das Grundteil in Prismen gelegt. Eine Montageplatte lässt "
                                  "sich aus der Baugruppe erzeugen.")
            return
        try:
            t = self.projekt.teil(int(vid))
        except ProjektFehler:
            self.aufnahme.setText("⚠ Die gewählte Vorrichtung gibt es nicht mehr.")
            return
        felder = vorlagen.MontageplatteParameter.__dataclass_fields__
        p = vorlagen.MontageplatteParameter(**{k: v for k, v in t["parameter"].items() if k in felder})
        punkte = vorlagen.montageplatte_aufnahmepunkte(p)
        self.aufnahme.setText(
            f"Aufnahmepunkte: Auflagen Ø{formatiere(p.d_auflage)} bei z = {formatiere(p.z_1)} und "
            f"{formatiere(p.z_2)} mm, Achshöhe {formatiere(p.achshoehe)} mm, {len(punkte) - 2} Befestigungslöcher "
            f"Ø{formatiere(p.d_befestigung)}; Platte {formatiere(p.laenge)} × {formatiere(p.breite)} × "
            f"{formatiere(p.dicke)} mm, {formatiere(t['masse'] or 0)} kg.")

    def _details(self):
        s = self._aktuell()
        self._fuellt = True
        for w in (self.f_titel, self.f_text, self.f_werkzeuge, self.f_pruefung, self.f_zeit, self.f_momente):
            w.setEnabled(s is not None)
        if s is None:
            self.f_titel.clear()
            self.f_text.clear()
            self.f_werkzeuge.clear()
            self.f_pruefung.clear()
            self.f_momente.setRowCount(0)
            self.f_teile.setText("–")
        else:
            self.f_titel.setText(s["titel"])
            self.f_text.setPlainText(s.get("text", ""))
            self.f_werkzeuge.setPlainText("\n".join(s.get("werkzeuge", [])))
            self.f_pruefung.setPlainText("\n".join(s.get("pruefung", [])))
            self.f_zeit.setValue(float(s.get("zeit") or 0))
            self.f_teile.setText(self._teile_text(s))
            self.f_momente.setRowCount(len(s.get("momente", [])))
            for i, m in enumerate(s.get("momente", [])):
                wert = "" if m.get("wert") in (None, "") else formatiere(float(m["wert"]))
                for j, text in enumerate((m.get("was", ""), wert, m.get("quelle", ""))):
                    item = QTableWidgetItem(text)
                    if j == 2:
                        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                    self.f_momente.setItem(i, j, item)
        self._fuellt = False
        self._summe()
        self._ansicht_aktualisieren(anpassen=False)

    def _teile_text(self, s: dict) -> str:
        if not s.get("einbauten"):
            return "–"
        einbauten = {e["id"]: e for e in self.definition.get("einbauten", [])}
        anzahl = {}
        for x in (self.erg.exemplare if self.erg else []):
            anzahl[x.einbau] = anzahl.get(x.einbau, 0) + 1
        teile = []
        for eid in s["einbauten"]:
            e = einbauten.get(eid)
            if e is None:
                teile.append(f"⚠ {eid} fehlt in der Baugruppe")
                continue
            n = anzahl.get(eid, 1)
            teile.append(f"{n}× {e.get('name') or e.get('norm')}" if n > 1 else (e.get("name") or e.get("norm", eid)))
        return ", ".join(teile)

    def _summe(self):
        if self.plan is None:
            self.summe.setText("")
            self.meldungen.setText("")
            return
        werkzeuge = M.werkzeugliste(self.plan)
        self.summe.setText(f"<b>{len(self.plan['schritte'])} Schritte</b> · Montagezeit ≈ "
                           f"{formatiere(M.gesamtzeit(self.plan))} min (Schätzwert) · {len(werkzeuge)} Werkzeuge und "
                           f"Hilfsmittel · Masse {formatiere(self.erg.masse if self.erg else 0)} kg")
        punkte = ["⚠ " + h for h in self.plan.get("hinweise", []) + M.pruefen(self.plan, self.definition)]
        self.meldungen.setText("<br>".join(punkte))

    def _ansicht_aktualisieren(self, anpassen: bool = False):
        f = self.explosion.value()
        self.explosion_text.setText(f"{f} %")
        if self.szene is None:
            self.ansicht.setze_netz(None)
            return
        verschiebung = self.explosion_basis * (f / 100) if f else None
        s = self._aktuell()
        if self.nur_bis.isChecked() and s is not None:
            sichtbar, neu = SZ.schritt_ansicht(self.szene, self.plan, s["nr"])
            self.ansicht.setze_netz(self.szene.netz(verschiebung, sichtbar), anpassen=anpassen,
                                    gruppen=self.szene.gruppen(neu, sichtbar))
        else:
            self.ansicht.setze_netz(self.szene.netz(verschiebung), anpassen=anpassen,
                                    gruppen=self.szene.gruppen())

    # ---------- Speichern, PDF ----------
    def plan_speichern(self) -> dict | None:
        if self.gid is None or self.plan is None:
            return None
        mp = self.projekt.montageplan_speichern(self.gid, M.nummerieren(self.plan))
        self.status.setText(f"{mp['nr']} · Version {mp['version']} · {mp['status']}")
        i = self.gruppe_wahl.findData(self.gid)
        g = self.projekt.baugruppe(self.gid)
        self.gruppe_wahl.setItemText(i, f"{g['nr']} {g['name']} ✓")
        self.meldung.emit(f"Montageplan {mp['nr']} gespeichert.", False)
        self.gespeichert.emit()
        return mp

    def pdf(self, ziel: str | None = None) -> Path | None:
        if self.gid is None or self.plan is None or self.szene is None:
            return None
        g = self.projekt.baugruppe(self.gid)
        if ziel is None:
            ziel, _ = QFileDialog.getSaveFileName(self, "Montageanleitung speichern",
                                                  f"Montageanleitung_{g['nr']}.pdf", "PDF (*.pdf)")
            if not ziel:
                return None
        from ..pdf import montageanleitung_erstellen
        bilder = szene_bilder(self.szene, self.plan, self.explosion_basis)
        vorrichtung = punkte = None
        if self.plan.get("vorrichtung"):
            t = self.projekt.teil(int(self.plan["vorrichtung"]))
            vorrichtung = {"nr": t["nr"], "name": t["name"]}
            felder = vorlagen.MontageplatteParameter.__dataclass_fields__
            punkte = vorlagen.montageplatte_aufnahmepunkte(
                vorlagen.MontageplatteParameter(**{k: v for k, v in t["parameter"].items() if k in felder}))
        pfad = montageanleitung_erstellen(g, M.nummerieren(self.plan), bilder, self.erg.stueckliste, ziel,
                                          self.projekt.name, vorrichtung, punkte)
        self.meldung.emit(f"Montageanleitung gespeichert: {Path(pfad).name}", False)
        return Path(pfad)
