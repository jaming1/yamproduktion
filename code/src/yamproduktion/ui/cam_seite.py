"""Seite „CAM-Export (G-Code)“: NC-Programme aus dem Arbeitsplan, Werkzeugweg-Vorschau, Prüfung, Export (K5)."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QGridLayout, QHBoxLayout, QLabel, QListWidget,
    QPlainTextEdit, QPushButton, QSplitter, QVBoxLayout, QWidget,
)

from ..berechnungen.basis import formatiere
from ..fertigung import cam
from ..modell import NEU_PRUEFEN, Projekt, ProjektFehler
from . import thema
from .seiten import karte, scrollbar, titel

# Arbeitsgänge, deren Hauptzeit t_h im Arbeitsplan mit der CAM-Hauptzeit vergleichbar ist
SPANENDE_ARTEN = ("plandrehen", "laengsdrehen", "bohren", "fraesen")
# (Feld in cam.Einstellungen, Beschriftung, Bereich, Schritt, Tooltip)
MASS_FELDER = (
    ("sicherheitsabstand", "Sicherheitsabstand", (0.5, 50.0), 0.5,
     "Abstand über dem Werkstück, auf dem im Eilgang angefahren wird (mm)"),
    ("schnitttiefe", "Schnitttiefe a_p", (0.1, 20.0), 0.5, "Zustellung je Schruppschnitt (mm)"),
    ("aufmass", "Schlichtaufmaß", (0.0, 3.0), 0.1, "Aufmaß, das nach dem Schruppen für das Schlichten stehen bleibt (mm)"),
)


def _farben(widget: QWidget) -> dict:
    """Farben des aktuellen Themas – erkannt an der Helligkeit des Fensterhintergrunds."""
    dunkel = widget.palette().window().color().lightness() < 128
    return thema.FARBEN["dunkel" if dunkel else "hell"]


class WegVorschau(QWidget):
    """Werkzeugweg in der Ebene: Eilgang gestrichelt, Vorschub durchgezogen, Umrisse dünn grau (1:1)."""

    def __init__(self):
        super().__init__()
        self.segmente: list[cam.Segment] = []
        self.umrisse: list[list[tuple[float, float]]] = []
        self.art = "drehen"
        self.setMinimumSize(420, 300)
        self.setAccessibleName("Werkzeugweg-Vorschau")

    def setze(self, segmente, umrisse, art: str):
        self.segmente = list(segmente or [])
        self.umrisse = [list(u) for u in (umrisse or []) if u]
        self.art = art
        self.update()

    def achsen(self) -> tuple[str, str]:
        return ("Z", "X/2") if self.art == "drehen" else ("X", "Y")

    def bereich(self) -> tuple[float, float, float, float] | None:
        punkte = [(s.a0, s.b0) for s in self.segmente] + [(s.a1, s.b1) for s in self.segmente]
        punkte += [pt for u in self.umrisse for pt in u]
        if not punkte:
            return None
        a = [p[0] for p in punkte] + [0.0]
        b = [p[1] for p in punkte] + [0.0]
        return min(a), max(a), min(b), max(b)

    def _hat_punkte(self) -> bool:
        return any(not g.eilgang and abs(g.a1 - g.a0) < 1e-6 and abs(g.b1 - g.b0) < 1e-6 for g in self.segmente)

    def paintEvent(self, _):
        f = _farben(self)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(f["flaeche"]))
        p.setPen(QPen(QColor(f["linie"]), 1))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 8, 8)
        schrift = QFont(self.font())
        schrift.setPixelSize(14)
        p.setFont(schrift)
        b = self.bereich()
        if b is None:
            p.setPen(QColor(f["text2"]))
            p.drawText(self.rect(), Qt.AlignCenter, "Kein Werkzeugweg – Programm wählen")
            return
        amin, amax, bmin, bmax = b
        breite, hoehe = max(amax - amin, 1e-6), max(bmax - bmin, 1e-6)
        rand_l, rand_r, rand_o, rand_u = 56, 28, 28, 44
        s = min((self.width() - rand_l - rand_r) / breite, (self.height() - rand_o - rand_u) / hoehe)
        s = max(s, 1e-6)
        ox = rand_l + ((self.width() - rand_l - rand_r) - breite * s) / 2 - amin * s
        oy = rand_o + ((self.height() - rand_o - rand_u) + hoehe * s) / 2 + bmin * s

        def pt(a, bb):
            return QPointF(ox + a * s, oy - bb * s)

        # Achsen durch den Nullpunkt
        grau = QColor(f["text2"])
        p.setPen(QPen(grau, 1, Qt.DashDotLine))
        p.drawLine(pt(amin, 0), pt(amax, 0))
        p.drawLine(pt(0, bmin), pt(0, bmax))
        p.setPen(grau)
        name_a, name_b = self.achsen()
        ende_a = pt(amax, 0)
        p.drawText(QPointF(min(ende_a.x() + 6, self.width() - 22), ende_a.y() + 5), name_a)
        ende_b = pt(0, bmax)
        p.drawText(QPointF(ende_b.x() - 10, max(ende_b.y() - 8, 16)), name_b)
        # Maßstab unten: Bereich in mm
        p.drawText(QRectF(8, self.height() - 30, self.width() - 16, 24), Qt.AlignLeft | Qt.AlignVCenter,
                   f"{name_a} {formatiere(amin)} … {formatiere(amax)} mm   ·   "
                   f"{name_b} {formatiere(bmin)} … {formatiere(bmax)} mm")
        p.drawText(QRectF(8, self.height() - 30, self.width() - 16, 24), Qt.AlignRight | Qt.AlignVCenter,
                   "– – Eilgang   —— Vorschub" + ("   ● Bohren/Eintauchen" if self._hat_punkte() else ""))

        # Umrisse von Rohteil und Fertigteil
        p.setPen(QPen(QColor(f["linie"]).darker(115 if f is thema.FARBEN["hell"] else 70), 1.2))
        for u in self.umrisse:
            pfad = QPainterPath(pt(*u[0]))
            for q in u[1:]:
                pfad.lineTo(pt(*q))
            p.drawPath(pfad)

        # Werkzeugweg
        eil = QPen(grau, 1.2, Qt.DashLine)
        vor = QPen(QColor(f["akzent"]), 2.0)
        punkte = set()
        for seg in self.segmente:
            if not seg.eilgang and abs(seg.a1 - seg.a0) < 1e-6 and abs(seg.b1 - seg.b0) < 1e-6:
                punkte.add((round(seg.a0, 3), round(seg.b0, 3)))     # senkrecht zur Ebene: Bohren/Eintauchen
                continue
            p.setPen(eil if seg.eilgang else vor)
            p.drawLine(pt(seg.a0, seg.b0), pt(seg.a1, seg.b1))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(f["akzent"]))
        for a, bb in punkte:
            p.drawEllipse(pt(a, bb), 3.5, 3.5)


class CamSeite(QWidget):
    meldung = Signal(str, bool)
    gespeichert = Signal()

    def __init__(self):
        super().__init__()
        self.projekt: Projekt | None = None
        self.teil_id: int | None = None
        self.einst = cam.Einstellungen()
        self.programme: list = []
        self.pruefungen: dict[str, cam.Pruefung] = {}
        self.fehler_text = ""
        self._fuellt = False

        inhalt = QWidget()
        lay = QVBoxLayout(inhalt)
        lay.setContentsMargins(32, 24, 32, 24)
        lay.addWidget(titel("CAM-Export (G-Code)",
                            "Je Bauteil: NC-Programme für Drehen und Fräsen aus dem Arbeitsplan – mit Vorschau des "
                            "Werkzeugwegs, Prüfung und Export als .nc-Datei."))

        # ---- Kopf: Teil, Speichern, Export, Status, Einstellungen
        k, kl = karte()
        zeile = QHBoxLayout()
        self.teil_wahl = QComboBox()
        self.teil_wahl.setAccessibleName("Bauteil")
        self.teil_wahl.setMinimumContentsLength(24)
        self.teil_wahl.activated.connect(lambda _: self.teil_laden(self.teil_wahl.currentData()))
        zeile.addWidget(self.teil_wahl, 2)
        self.speichern = QPushButton("NC-Programme speichern")
        self.speichern.setObjectName("Haupt")
        self.speichern.setShortcut("Ctrl+S")
        self.speichern.setToolTip("Einstellungen und Programme im Projekt ablegen (neue Version)")
        self.speichern.clicked.connect(lambda: self.programme_speichern())
        zeile.addWidget(self.speichern)
        self.export_knopf = QPushButton("G-Code exportieren …")
        self.export_knopf.setToolTip("Alle Programme dieses Bauteils als .nc-Dateien in einen Ordner schreiben")
        self.export_knopf.clicked.connect(lambda: self.exportieren())
        zeile.addWidget(self.export_knopf)
        kl.addLayout(zeile)
        self.status = QLabel()
        self.status.setObjectName("Klein")
        self.status.setWordWrap(True)
        kl.addWidget(self.status)

        # Einstellungen: zwei Zeilen mit je drei Feldern (Beschriftung links vom Feld)
        einst = QGridLayout()
        einst.setHorizontalSpacing(12)
        einst.setVerticalSpacing(10)
        self.dialekt = QComboBox()
        for schluessel, text in cam.DIALEKTE.items():
            self.dialekt.addItem(text, schluessel)
        self.dialekt.setAccessibleName("Steuerung")
        self.dialekt.setToolTip("Dialekt des G-Codes – passend zur Steuerung der Maschine wählen")
        self.dialekt.activated.connect(lambda _: self.setze_einstellung("dialekt", self.dialekt.currentData()))
        self.programmnummer = QDoubleSpinBox()          # wie die übrigen Zahlenfelder gestaltet, ganzzahlig
        self.programmnummer.setDecimals(0)
        self.programmnummer.setMaximumWidth(150)
        self.programmnummer.setRange(1, 9999)
        self.programmnummer.setKeyboardTracking(False)
        self.programmnummer.setAccessibleName("Programmnummer")
        self.programmnummer.setToolTip("Nummer des ersten Programms (O-Nummer, nur bei Fanuc), weitere zählen hoch")
        self.programmnummer.valueChanged.connect(lambda v: self.setze_einstellung("programmnummer", int(v)))
        self.kuehlung = QCheckBox("Kühlmittel ein (M8)")
        self.kuehlung.toggled.connect(lambda v: self.setze_einstellung("kuehlung", v))
        self.mass_felder: dict[str, QDoubleSpinBox] = {}
        for name, text, (von, bis), schritt, tipp in MASS_FELDER:
            e = QDoubleSpinBox()
            e.setRange(von, bis)
            e.setSingleStep(schritt)
            e.setDecimals(2)
            e.setSuffix(" mm")
            e.setKeyboardTracking(False)
            e.setToolTip(tipp)
            e.setAccessibleName(text)
            e.setMinimumWidth(120)
            e.setMaximumWidth(150)
            e.valueChanged.connect(lambda v, n=name: self.setze_einstellung(n, v))
            self.mass_felder[name] = e
        # Zeile 1: Steuerung (breit), Programmnummer, Kühlmittel – Zeile 2: die drei Maße
        einst.addWidget(QLabel("Steuerung"), 0, 0)
        einst.addWidget(self.dialekt, 0, 1, 1, 3)
        einst.addWidget(QLabel("Programmnummer"), 0, 4)
        einst.addWidget(self.programmnummer, 0, 5, Qt.AlignLeft)
        einst.addWidget(self.kuehlung, 0, 6)
        for i, (name, text, *_) in enumerate(MASS_FELDER):
            einst.addWidget(QLabel(text), 1, 2 * i)
            einst.addWidget(self.mass_felder[name], 1, 2 * i + 1, Qt.AlignLeft)
        einst.setColumnStretch(7, 1)
        kl.addLayout(einst)
        lay.addWidget(k)

        # ---- Programme | Vorschau + G-Code
        k, kl = karte()
        self.leer_text = QLabel()
        self.leer_text.setWordWrap(True)
        kl.addWidget(self.leer_text)
        self.teiler = QSplitter(Qt.Horizontal)
        self.teiler.setChildrenCollapsible(False)
        links = QWidget()
        ll = QVBoxLayout(links)
        ll.setContentsMargins(0, 0, 8, 0)
        t = QLabel("Programme")
        t.setObjectName("Abschnitt")
        ll.addWidget(t)
        self.liste = QListWidget()
        self.liste.setAccessibleName("NC-Programme")
        self.liste.setMinimumHeight(120)
        self.liste.setMaximumHeight(220)
        self.liste.setWordWrap(True)
        self.liste.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.liste.currentRowChanged.connect(lambda _: self._programm_zeigen())
        ll.addWidget(self.liste)
        self.aufspannung = QLabel()
        self.aufspannung.setWordWrap(True)
        ll.addWidget(self.aufspannung)
        u = QLabel("Werkzeuge")
        u.setObjectName("Unterabschnitt")
        ll.addWidget(u)
        self.werkzeuge = QLabel()
        self.werkzeuge.setWordWrap(True)
        self.werkzeuge.setTextInteractionFlags(Qt.TextSelectableByMouse)
        ll.addWidget(self.werkzeuge)
        self.warnungen = QLabel()
        self.warnungen.setObjectName("Fehler")
        self.warnungen.setWordWrap(True)
        ll.addWidget(self.warnungen)
        ll.addStretch()
        links.setMinimumWidth(360)
        self.teiler.addWidget(links)

        rechts = QSplitter(Qt.Vertical)
        rechts.setChildrenCollapsible(False)
        self.vorschau = WegVorschau()
        rechts.addWidget(self.vorschau)
        self.code = QPlainTextEdit()
        self.code.setReadOnly(True)
        self.code.setAccessibleName("G-Code")
        self.code.setLineWrapMode(QPlainTextEdit.NoWrap)
        fest = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        self.code.setFont(fest)
        self.code.setStyleSheet(f'QPlainTextEdit {{ font-family: "{fest.family()}", "Menlo", monospace; '
                                f'font-size: 16px; }}')
        self.code.setMinimumHeight(200)
        rechts.addWidget(self.code)
        rechts.setSizes([340, 340])
        self.teiler.addWidget(rechts)
        self.teiler.setStretchFactor(0, 2)
        self.teiler.setStretchFactor(1, 5)
        self.teiler.setMinimumHeight(700)
        kl.addWidget(self.teiler)
        lay.addWidget(k)

        # ---- Prüfung
        k, kl = karte()
        t = QLabel("Prüfung des G-Codes")
        t.setObjectName("Abschnitt")
        kl.addWidget(t)
        self.pruef_ergebnis = QLabel()
        self.pruef_ergebnis.setWordWrap(True)
        kl.addWidget(self.pruef_ergebnis)
        self.pruef_text = QLabel()
        self.pruef_text.setWordWrap(True)
        kl.addWidget(self.pruef_text)
        self.hinweis = QLabel(cam.HINWEIS)
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
        self.programme = []
        self.fehler_text = ""
        self.teil_wahl.clear()
        if self.isVisible():
            self.laden()
        else:
            self._anzeigen()          # Programme erst erzeugen, wenn die Seite geöffnet wird

    def laden(self):
        """Beim Öffnen der Seite: Bauteile auflisten und die Programme des gewählten Teils (neu) erzeugen."""
        self._teile_fuellen()
        if not self.projekt:
            self._anzeigen()
            return
        ids = [self.teil_wahl.itemData(i) for i in range(self.teil_wahl.count())]
        if self.teil_id not in ids:
            self.teil_id = None
            self.programme = []
        if self.teil_id is None and ids:
            self.teil_laden(ids[0])
        elif self.teil_id is not None:
            self.erzeugen()           # das Teil oder sein Arbeitsplan kann sich inzwischen geändert haben
        else:
            self._anzeigen()

    def _teile_fuellen(self):
        """Auswahlliste der Bauteile mit ✓ (NC-Programm gespeichert) oder ⚠ (neu prüfen)."""
        self.teil_wahl.blockSignals(True)
        self.teil_wahl.clear()
        if self.projekt:
            for t in self.projekt.teile():
                nc = self.projekt.cam_von_teil(t["id"])
                zeichen = "" if nc is None else (" ⚠" if nc["status"] == NEU_PRUEFEN else " ✓")
                self.teil_wahl.addItem(f"{t['nr']} {t['name']}{zeichen}", t["id"])
        if self.teil_id is not None:
            self.teil_wahl.setCurrentIndex(max(0, self.teil_wahl.findData(self.teil_id)))
        self.teil_wahl.blockSignals(False)

    def teil_laden(self, teil_id: int | None):
        if teil_id is None or not self.projekt:
            return
        self.teil_id = teil_id
        if self.teil_wahl.findData(teil_id) < 0:
            self._teile_fuellen()
        self.teil_wahl.setCurrentIndex(max(0, self.teil_wahl.findData(teil_id)))
        nc = self.projekt.cam_von_teil(teil_id)
        daten = (nc or {}).get("daten") or {}
        self.einst = cam.Einstellungen.aus_dict(daten.get("einstellungen"))
        self.erzeugen()

    # ================================================================ Erzeugen
    def setze_einstellung(self, name: str, wert):
        """Eine Einstellung ändern und die Programme sofort neu erzeugen."""
        if self._fuellt or self.teil_id is None:
            return
        if getattr(self.einst, name, None) == wert:
            return
        setattr(self.einst, name, wert)
        self.erzeugen()

    def erzeugen(self):
        alt = self._gewaehlt()
        alt_schluessel = alt.schluessel if alt else None
        self.fehler_text = ""
        self.pruefungen = {}
        try:
            self.programme = list(self.projekt.cam_erzeugen(self.teil_id, self.einst.als_dict()))
        except (cam.CamFehler, ProjektFehler, ValueError, KeyError) as exc:
            self.programme = []
            self.fehler_text = str(exc) or exc.__class__.__name__
        for prog in self.programme:
            try:
                self.pruefungen[prog.schluessel] = cam.pruefen(prog.text, prog.art)
            except (cam.CamFehler, ValueError) as exc:
                self.pruefungen[prog.schluessel] = cam.Pruefung(
                    fehler=[f"Prüfung nicht möglich: {exc}"], hinweise=[], segmente=[],
                    weg_eilgang=0.0, weg_vorschub=0.0, zeit=0.0)
        self._anzeigen(alt_schluessel)

    def _gewaehlt(self):
        z = self.liste.currentRow()
        return self.programme[z] if 0 <= z < len(self.programme) else None

    # ================================================================ Anzeigen
    def _anzeigen(self, schluessel: str | None = None):
        hat_teil = self.projekt is not None and self.teil_id is not None
        hat = hat_teil and bool(self.programme)
        for w in (self.speichern, self.export_knopf):
            w.setEnabled(hat)
        for w in (self.dialekt, self.programmnummer, self.kuehlung, *self.mass_felder.values()):
            w.setEnabled(hat_teil)
        # Die O-Programmnummer schreibt nur der Fanuc-Dialekt in den Kopf
        self.programmnummer.setEnabled(hat_teil and self.einst.dialekt == "fanuc")
        self._einstellungen_zeigen()
        self._status_zeigen()
        if not self.projekt:
            leer = ""
        elif not hat_teil:
            leer = ("Zuerst ein Bauteil anlegen (Bauteile 3D oder Modellieren) und einen Arbeitsplan speichern – "
                    "dann entstehen hier die NC-Programme.")
        elif self.fehler_text:
            leer = f"⚠ Für dieses Bauteil lässt sich kein NC-Programm erzeugen: {self.fehler_text}"
        elif not self.programme:
            leer = ("Der Arbeitsplan enthält keine Dreh-, Bohr- oder Fräsgänge – für dieses Bauteil gibt es kein "
                    "NC-Programm.")
        else:
            leer = ""
        self.leer_text.setText(leer)
        self.leer_text.setVisible(bool(leer))
        self.teiler.setVisible(hat)

        self.liste.blockSignals(True)
        self.liste.clear()
        wahl = 0
        for i, prog in enumerate(self.programme):
            pr = self.pruefungen.get(prog.schluessel)
            zeichen = "✓" if pr is not None and pr.ok else "⚠"
            self.liste.addItem(f"{zeichen}  {prog.titel}\n     {prog.maschine}")
            if prog.schluessel == schluessel:
                wahl = i
        if self.programme:
            self.liste.setCurrentRow(wahl)
        self.liste.blockSignals(False)
        self._programm_zeigen()

    def _einstellungen_zeigen(self):
        self._fuellt = True
        e = self.einst
        i = self.dialekt.findData(e.dialekt)
        self.dialekt.setCurrentIndex(max(0, i))
        self.programmnummer.setValue(int(e.programmnummer))
        for name, feld in self.mass_felder.items():
            feld.setValue(float(getattr(e, name)))
        self.kuehlung.setChecked(bool(e.kuehlung))
        self._fuellt = False

    def _status_zeigen(self):
        if not self.projekt or self.teil_id is None:
            self.status.setText("")
            return
        nc = self.projekt.cam_von_teil(self.teil_id)
        if nc is None:
            self.status.setText("Noch nicht gespeichert – Programme aus dem Arbeitsplan erzeugt.")
            return
        text = f"{nc['nr']} · Version {nc['version']} · {nc['status']}"
        if nc["status"] == NEU_PRUEFEN:
            text += " – das Bauteil wurde geändert, bitte Programme prüfen und neu speichern."
        gespeichert = ((nc.get("daten") or {}).get("einstellungen")) or {}
        if gespeichert and cam.Einstellungen.aus_dict(gespeichert).als_dict() != self.einst.als_dict():
            text += " · Einstellungen geändert, noch nicht gespeichert."
        self.status.setText(text)

    def _programm_zeigen(self):
        prog = self._gewaehlt()
        if prog is None:
            self.aufspannung.setText("")
            self.werkzeuge.setText("")
            self.warnungen.hide()
            self.vorschau.setze([], [], "drehen")
            self.code.setPlainText("")
            self.pruef_ergebnis.setText("")
            self.pruef_ergebnis.setObjectName("")
            self.pruef_ergebnis.hide()
            self.pruef_text.setText("Noch kein Programm." if self.projekt else "")
            return
        self.aufspannung.setText(f"<b>Aufspannung</b><br>{prog.aufspannung}")
        self.werkzeuge.setText("<br>".join(prog.werkzeuge) if prog.werkzeuge else "–")
        self.warnungen.setText("⚠ " + "<br>⚠ ".join(prog.warnungen) if prog.warnungen else "")
        self.warnungen.setVisible(bool(prog.warnungen))
        self.code.setPlainText(prog.text)
        pr = self.pruefungen.get(prog.schluessel)
        self.vorschau.setze(pr.segmente if pr else [], prog.umrisse, prog.art)
        self._pruefung_zeigen(prog, pr)

    def _pruefung_zeigen(self, prog, pr):
        self.pruef_ergebnis.show()
        if pr is None:
            self.pruef_ergebnis.setObjectName("Fehler")
            self.pruef_ergebnis.setText("⚠ Nicht geprüft.")
        elif pr.ok:
            self.pruef_ergebnis.setObjectName("Ok")
            self.pruef_ergebnis.setText(f"✓ Keine Fehler gefunden – {prog.titel}")
        else:
            self.pruef_ergebnis.setObjectName("Fehler")
            self.pruef_ergebnis.setText(f"⚠ {len(pr.fehler)} Fehler in {prog.titel}:<br>• "
                                        + "<br>• ".join(pr.fehler))
        self.pruef_ergebnis.style().unpolish(self.pruef_ergebnis)
        self.pruef_ergebnis.style().polish(self.pruef_ergebnis)
        teile = []
        if pr is not None:
            teile.append(f"Verfahrwege: Eilgang {formatiere(pr.weg_eilgang)} mm · Vorschub "
                         f"{formatiere(pr.weg_vorschub)} mm")
            nebenzeit = getattr(pr, "zeit_eilgang", 0.0)
            teile.append(f"Geschätzte Hauptzeit dieses Programms: <b>{formatiere(pr.zeit)} min</b>"
                         + (f" (dazu Eilgang etwa {formatiere(nebenzeit)} min)" if nebenzeit else "")
                         + (f" · Werkzeugwechsel: {pr.werkzeugwechsel}" if getattr(pr, "werkzeugwechsel", 0) else ""))
            if pr.hinweise:
                teile.append("Hinweise:<br>• " + "<br>• ".join(pr.hinweise))
        teile.append(self._vergleich_arbeitsplan())
        self.pruef_text.setText("<br>".join(t for t in teile if t))

    def _vergleich_arbeitsplan(self) -> str:
        """Summe der CAM-Hauptzeiten aller Programme gegen t_h der spanenden Gänge im Arbeitsplan."""
        summe_cam = sum(pr.zeit for pr in self.pruefungen.values())
        text = f"Alle Programme zusammen: {formatiere(summe_cam)} min"
        try:
            kalk = self.projekt.kalkulation_teil(self.teil_id)
        except (ProjektFehler, ValueError, KeyError):
            kalk = None
        if kalk is None:
            return text + " · Kein gespeicherter Arbeitsplan zum Vergleich."
        th = sum(g.th or 0.0 for g in kalk.gaenge if g.art in SPANENDE_ARTEN)
        if th <= 0:
            return text + " · Der Arbeitsplan nennt keine Hauptzeit für Drehen, Bohren oder Fräsen."
        abw = (summe_cam - th) / th * 100
        return (text + f" · Arbeitsplan t_h (Drehen, Bohren, Fräsen): {formatiere(th)} min · Abweichung "
                f"{'+' if abw >= 0 else '−'}{formatiere(abs(abw))} %")

    # ================================================================ Speichern / Export
    def programme_speichern(self) -> dict | None:
        if not self.projekt or self.teil_id is None or not self.programme:
            return None
        try:
            nc = self.projekt.cam_speichern(self.teil_id, self.einst.als_dict())
        except (cam.CamFehler, ProjektFehler, ValueError) as exc:
            self.meldung.emit(f"Speichern nicht möglich: {exc}", True)
            return None
        self.meldung.emit(f"{nc['nr']} gespeichert – Version {nc['version']}, "
                          f"{len(self.programme)} Programm(e).", False)
        self._teile_fuellen()
        self._status_zeigen()
        self.gespeichert.emit()
        return nc

    def exportieren(self, ordner: str | None = None) -> list[Path]:
        if not self.projekt or self.teil_id is None or not self.programme:
            return []
        if ordner is None:
            ordner = QFileDialog.getExistingDirectory(self, "Ordner für die NC-Dateien wählen",
                                                      str(self.projekt.pfad.parent))
            if not ordner:
                return []
        t = self.projekt.teil(self.teil_id)
        try:
            pfade = [Path(p) for p in cam.exportieren(self.programme, ordner, t["nr"])]
        except (OSError, cam.CamFehler, ValueError) as exc:
            self.meldung.emit(f"Export fehlgeschlagen: {exc}", True)
            return []
        self.meldung.emit(f"{len(pfade)} NC-Datei(en) geschrieben: " + ", ".join(p.name for p in pfade)
                          + " – vor dem Einsatz im Simulator der Steuerung prüfen.", False)
        return pfade
