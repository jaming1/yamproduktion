"""Seite „Zeichnungen“: technische Zeichnung eines Bauteils oder einer Baugruppe, Vorschau, Export PDF/DXF (MS8)."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget,
)

from ..berechnungen.basis import formatiere
from ..cad import zeichnung as Z
from ..modell import NEU_PRUEFEN, Projekt, ProjektFehler
from .seiten import karte, titel

SCHNITT = {"auto": "Schnitt automatisch", "ja": "Schnitt A–A", "nein": "Ohne Schnitt"}


class Blatt(QWidget):
    """Vorschau des Zeichnungsblatts – weißes Papier wie gedruckt, auch im dunklen Modus."""

    def __init__(self):
        super().__init__()
        self.zeichnung: Z.Zeichnung | None = None
        self.setMinimumSize(560, 400)
        self.setAccessibleName("Zeichnungsvorschau")

    def setze(self, z: Z.Zeichnung | None):
        self.zeichnung = z
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        z = self.zeichnung
        if z is None:
            p.setPen(self.palette().text().color())
            p.drawText(self.rect(), Qt.AlignCenter, "Teil oder Baugruppe wählen")
            return
        rand = 8
        s = min((self.width() - 2 * rand) / z.breite, (self.height() - 2 * rand) / z.hoehe)
        ox = (self.width() - z.breite * s) / 2
        oy = (self.height() + z.hoehe * s) / 2

        def pt(x, y):
            return QPointF(ox + x * s, oy - y * s)
        p.fillRect(QRectF(pt(0, z.hoehe), pt(z.breite, 0)), QColor("#FFFFFF"))
        schwarz = QColor("#111111")
        for el in z.elemente:
            if isinstance(el, Z.Linie):
                breite, muster = Z.LINIEN[el.art]
                stift = QPen(schwarz, max(0.6, breite * s))
                if muster:
                    stift.setDashPattern([max(0.5, v / breite) for v in muster])
                p.setPen(stift)
                p.drawLine(pt(el.x0, el.y0), pt(el.x1, el.y1))
            elif isinstance(el, Z.Polygon):
                p.setPen(Qt.NoPen)
                p.setBrush(QBrush(schwarz))
                p.drawPolygon(QPolygonF([pt(x, y) for x, y in el.punkte]))
                p.setBrush(Qt.NoBrush)
        p.setPen(schwarz)
        for el in z.elemente:
            if isinstance(el, Z.Text):
                f = QFont()
                f.setPixelSize(max(4, round(el.hoehe * s * 1.25)))
                p.setFont(f)
                breite_t = p.fontMetrics().horizontalAdvance(el.text)
                dx = {"links": 0, "mitte": -breite_t / 2, "rechts": -breite_t}[el.ausrichtung]
                p.save()
                p.translate(pt(el.x, el.y))
                p.rotate(-el.drehung)
                p.drawText(QPointF(dx, 0), el.text)
                p.restore()


class ZeichnungSeite(QWidget):
    meldung = Signal(str, bool)

    def __init__(self):
        super().__init__()
        self.projekt: Projekt | None = None
        self.zeichnung: Z.Zeichnung | None = None
        self.objekt: tuple[str, int] | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 24, 32, 24)
        lay.addWidget(titel("Zeichnungen", "Technische Zeichnung nach ISO 128 (Projektionsmethode 1) mit Schnitt, "
                                           "Bemaßung, Passmaßen und Schriftfeld – als PDF oder DXF."))
        k, kl = karte()
        zeile = QHBoxLayout()
        self.wahl = QComboBox()
        self.wahl.setAccessibleName("Teil oder Baugruppe")
        self.wahl.setMinimumContentsLength(22)
        self.wahl.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.wahl.activated.connect(lambda _: self._gewaehlt())
        zeile.addWidget(self.wahl, 2)
        self.schnitt = QComboBox()
        for schluessel, text in SCHNITT.items():
            self.schnitt.addItem(text, schluessel)
        self.schnitt.activated.connect(lambda _: self.erstellen())
        zeile.addWidget(self.schnitt)
        self.massstab = QComboBox()
        self.massstab.addItem("Maßstab automatisch", None)
        for m in Z.MASSSTAEBE:
            self.massstab.addItem(Z.massstab_text(m), m)
        self.massstab.activated.connect(lambda _: self.erstellen())
        zeile.addWidget(self.massstab)
        kl.addLayout(zeile)
        zeile = QHBoxLayout()
        zeile.addWidget(QLabel("Passmaße"))
        self.toleranzen = QLineEdit()
        self.toleranzen.setPlaceholderText("z. B. Ø80 k6; Ø140 H7")
        self.toleranzen.setToolTip("Toleranzklasse je Durchmesser (ISO 286), mit Semikolon getrennt")
        self.toleranzen.editingFinished.connect(self.erstellen)
        zeile.addWidget(self.toleranzen, 2)
        zeile.addWidget(QLabel("Erstellt"))
        self.ersteller = QLineEdit()
        self.ersteller.setPlaceholderText("Name")
        self.ersteller.editingFinished.connect(self.erstellen)
        zeile.addWidget(self.ersteller, 1)
        kl.addLayout(zeile)
        self.fehler = QLabel()
        self.fehler.setObjectName("Fehler")
        self.fehler.setWordWrap(True)
        self.fehler.hide()
        kl.addWidget(self.fehler)
        self.blatt = Blatt()
        kl.addWidget(self.blatt, 1)
        zeile = QHBoxLayout()
        self.pdf_knopf = QPushButton("Als PDF speichern …")
        self.pdf_knopf.setObjectName("Haupt")
        self.pdf_knopf.clicked.connect(lambda: self.exportieren(art="pdf"))
        zeile.addWidget(self.pdf_knopf)
        self.dxf_knopf = QPushButton("Als DXF speichern …")
        self.dxf_knopf.setToolTip("DXF R12 mit Layern je Linienart – für jedes CAD- oder Laserprogramm")
        self.dxf_knopf.clicked.connect(lambda: self.exportieren(art="dxf"))
        zeile.addWidget(self.dxf_knopf)
        self.info = QLabel()
        self.info.setObjectName("Klein")
        self.info.setWordWrap(True)
        zeile.addWidget(self.info, 1)
        kl.addLayout(zeile)
        lay.addWidget(k, 1)

    # ---------- Projekt
    def setze_projekt(self, projekt: Projekt):
        self.projekt = projekt
        self.objekt = None
        self.zeichnung = None
        self.blatt.setze(None)
        self.laden()

    def laden(self):
        self.wahl.clear()
        if not self.projekt:
            return
        for t in self.projekt.teile():
            self.wahl.addItem(f"{t['nr']} {t['name']}" + (" ⚠" if t["status"] == NEU_PRUEFEN else ""), f"teil:{t['id']}")
        for g in self.projekt.baugruppen():
            self.wahl.addItem(f"{g['nr']} {g['name']} (Baugruppe)" + (" ⚠" if g["status"] == NEU_PRUEFEN else ""),
                              f"baugruppe:{g['id']}")
        if self.objekt:
            i = self.wahl.findData(f"{self.objekt[0]}:{self.objekt[1]}")
            if i >= 0:
                self.wahl.setCurrentIndex(i)
        self._knoepfe()

    def oeffnen(self, typ: str, id_: int):
        self.objekt = (typ, id_)
        self.toleranzen.setText(self.projekt.passmasse(typ, id_) if self.projekt else "")
        self.laden()
        self.erstellen()

    def _gewaehlt(self):
        daten = self.wahl.currentData()
        self.objekt = (daten.split(":")[0], int(daten.split(":")[1])) if daten else None
        self.toleranzen.setText(self.projekt.passmasse(*self.objekt) if self.objekt and self.projekt else "")
        self.erstellen()

    def _knoepfe(self):
        self.pdf_knopf.setEnabled(self.zeichnung is not None)
        self.dxf_knopf.setEnabled(self.zeichnung is not None)

    @staticmethod
    def toleranzen_lesen(text: str) -> dict:
        from ..modell import Projekt
        return Projekt.passmasse_lesen(text)

    # ---------- Erstellen
    def erstellen(self) -> Z.Zeichnung | None:
        if not self.projekt or not self.objekt:
            return None
        typ, id_ = self.objekt
        p = self.projekt
        try:
            schnitt = {"auto": None, "ja": True, "nein": False}[self.schnitt.currentData()]
            p.passmasse_speichern(typ, id_, self.toleranzen.text().strip())
            self.zeichnung = p.zeichnung(typ, id_, self.ersteller.text().strip(), schnitt=schnitt,
                                         massstab=self.massstab.currentData())
            self.fehler.hide()
        except (ProjektFehler, ValueError, TypeError) as exc:
            self.zeichnung = None
            self.fehler.setText(f"⚠ Zeichnung nicht möglich: {exc}")
            self.fehler.show()
        self.blatt.setze(self.zeichnung)
        if self.zeichnung:
            self.info.setText(f"A3 quer · Maßstab {Z.massstab_text(self.zeichnung.massstab)} · "
                              + " ".join(self.zeichnung.hinweise))
        self._knoepfe()
        return self.zeichnung

    def exportieren(self, ziel: str | None = None, art: str = "pdf") -> Path | None:
        if self.zeichnung is None:
            return None
        if ziel is None:
            ordner = self.projekt.pfad.parent
            ziel, _ = QFileDialog.getSaveFileName(self, "Zeichnung speichern",
                                                  str(ordner / f"{self.zeichnung.titel or 'Zeichnung'}.{art}"),
                                                  "PDF (*.pdf)" if art == "pdf" else "DXF (*.dxf)")
            if not ziel:
                return None
        try:
            pfad = Z.als_pdf(self.zeichnung, ziel) if art == "pdf" else Z.als_dxf(self.zeichnung, ziel)
        except OSError as exc:
            self.meldung.emit(f"Speichern fehlgeschlagen: {exc}", True)
            return None
        self.meldung.emit(f"Zeichnung gespeichert: {Path(pfad).name}", False)
        return Path(pfad)


