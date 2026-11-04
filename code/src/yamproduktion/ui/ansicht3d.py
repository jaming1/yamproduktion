"""3D-Ansicht ohne OpenGL: schattierte Dreiecke und Modellkanten, nach Tiefe sortiert (Maleralgorithmus).

Reicht für Einzelteile mit einigen tausend Dreiecken, läuft überall (auch in Tests ohne Grafikkarte).
Bedienung: linke Maustaste drehen, rechte oder mittlere Maustaste verschieben, Mausrad zoomen,
Doppelklick = alles zeigen.
"""
from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

from ..cad.geometrie import Netz

ANSICHTEN = {   # (Azimut, Elevation) in Grad; z ist die Teileachse
    "Iso": (145.0, 25.0),
    "Vorne": (0.0, 0.0),
    "Oben": (0.0, 89.9),
    "Seite": (-90.0, 0.0),
}


def _drehung(azimut: float, elevation: float) -> np.ndarray:
    """Drehmatrix Teil → Bildschirm (x rechts, y oben, z zum Betrachter).
    Grundlage: Teileachse z liegt waagerecht im Bild (lange Wellen passen auf den Schirm);
    Azimut dreht um die Bild-Senkrechte, Elevation kippt um die Bild-Waagerechte."""
    a, e = math.radians(azimut), math.radians(elevation)
    basis = np.array([[0, 0, 1], [1, 0, 0], [0, 1, 0]], dtype=float)   # Teil-z → Bild-x, Teil-x → Bild-y
    ry = np.array([[math.cos(a), 0, math.sin(a)], [0, 1, 0], [-math.sin(a), 0, math.cos(a)]])
    rx = np.array([[1, 0, 0], [0, math.cos(e), -math.sin(e)], [0, math.sin(e), math.cos(e)]])
    return rx @ ry @ basis


class Ansicht3D(QWidget):
    geaendert = Signal()

    def __init__(self):
        super().__init__()
        self.setMinimumSize(420, 360)
        self.setMouseTracking(False)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAccessibleName("3D-Ansicht des Bauteils")
        self.netz: Netz | None = None
        self.schnittflaechen: np.ndarray | None = None
        self.azimut, self.elevation = ANSICHTEN["Iso"]
        self.zoom = 1.0
        self.verschiebung = np.zeros(2)
        self._maus = None
        self._mitte = np.zeros(3)
        self._radius = 1.0
        self._passend = 1.0           # Maßstab, bei dem das Teil die Ansicht füllt (bei Ansichtswechsel neu)
        self.hinweis = "Kein Teil"

    # ---------- Daten ----------
    def setze_netz(self, netz: Netz | None, schnitt_achse: int | None = None, schnitt_pos: float = 0.0,
                   anpassen: bool = True):
        self.netz = netz
        self.schnittflaechen = None
        if netz is not None:
            lo, hi = netz.punkte.min(axis=0), netz.punkte.max(axis=0)
            if anpassen or self._radius <= 0:
                self._mitte = (lo + hi) / 2
                self._radius = max(float(np.linalg.norm(hi - lo)) / 2, 1e-6)
            if schnitt_achse is not None:
                T = netz.dreiecke
                schwer = netz.punkte[T].mean(axis=1)[:, schnitt_achse]
                tol = 1e-3 * self._radius + 1e-6
                self.schnittflaechen = (np.abs(np.abs(netz.normalen[:, schnitt_achse]) - 1) < 1e-3) & \
                                       (np.abs(schwer - schnitt_pos) < tol)
        if anpassen:
            self.alles_zeigen()
        self.update()

    def blickrichtung(self) -> np.ndarray:
        """Richtung vom Teil zum Betrachter, in Teilkoordinaten."""
        return _drehung(self.azimut, self.elevation).T @ np.array([0.0, 0.0, 1.0])

    def ansicht(self, name: str):
        self.azimut, self.elevation = ANSICHTEN[name]
        self.alles_zeigen()
        self.geaendert.emit()

    def alles_zeigen(self):
        if self.netz is not None:
            Q = (self.netz.punkte - self._mitte) @ _drehung(self.azimut, self.elevation).T
            breite = max(float(np.ptp(Q[:, 0])), 1e-6)
            hoehe = max(float(np.ptp(Q[:, 1])), 1e-6)
            self._passend = 0.82 * min(max(self.width(), 100) / breite, max(self.height(), 100) / hoehe)
        self.zoom = 1.0
        self.verschiebung = np.zeros(2)
        self.update()

    # ---------- Maus ----------
    def mousePressEvent(self, ev):
        self._maus = (ev.position(), ev.button())

    def mouseMoveEvent(self, ev):
        if not self._maus:
            return
        start, knopf = self._maus
        d = ev.position() - start
        if knopf == Qt.LeftButton:
            self.azimut = (self.azimut + d.x() * 0.5) % 360
            self.elevation = max(-89.9, min(89.9, self.elevation - d.y() * 0.5))
        else:
            self.verschiebung += np.array([d.x(), d.y()])
        self._maus = (ev.position(), knopf)
        self.update()

    def mouseReleaseEvent(self, ev):
        self._maus = None
        self.geaendert.emit()

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        if self.zoom == 1.0 and not self.verschiebung.any():
            self.alles_zeigen()

    def mouseDoubleClickEvent(self, ev):
        self.alles_zeigen()

    def wheelEvent(self, ev):
        faktor = 1.0015 ** ev.angleDelta().y()
        self.zoom = max(0.1, min(50.0, self.zoom * faktor))
        self.update()

    def keyPressEvent(self, ev):
        schritte = {Qt.Key_Left: (-10, 0), Qt.Key_Right: (10, 0), Qt.Key_Up: (0, 10), Qt.Key_Down: (0, -10)}
        if ev.key() in schritte:
            da, de = schritte[ev.key()]
            self.azimut = (self.azimut + da) % 360
            self.elevation = max(-89.9, min(89.9, self.elevation + de))
            self.update()
        elif ev.key() in (Qt.Key_Plus, Qt.Key_Equal):
            self.zoom *= 1.2
            self.update()
        elif ev.key() == Qt.Key_Minus:
            self.zoom /= 1.2
            self.update()
        else:
            super().keyPressEvent(ev)

    # ---------- Zeichnen ----------
    def _farben(self):
        hg = self.palette().window().color()
        dunkel = hg.lightness() < 128
        return {
            "hintergrund": hg,
            "teil": np.array([170, 188, 210]) if dunkel else np.array([168, 186, 208]),
            "schnitt": np.array([224, 148, 72]),
            "kante": QColor(40, 48, 60) if not dunkel else QColor(12, 14, 18),
            "text": self.palette().windowText().color(),
        }

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        farben = self._farben()
        p.fillRect(self.rect(), farben["hintergrund"])
        if self.netz is None:
            p.setPen(farben["text"])
            p.drawText(self.rect(), Qt.AlignCenter, self.hinweis)
            return
        R = _drehung(self.azimut, self.elevation)
        n = self.netz
        Q = (n.punkte - self._mitte) @ R.T
        massstab = self._passend * self.zoom
        cx = self.width() / 2 + self.verschiebung[0]
        cy = self.height() / 2 + self.verschiebung[1]
        sx = cx + Q[:, 0] * massstab
        sy = cy - Q[:, 1] * massstab
        T = n.dreiecke
        normal = n.normalen @ R.T
        sichtbar = normal[:, 2] > -1e-6
        tiefe = Q[T, 2].mean(axis=1)
        licht = np.array([0.35, 0.45, 0.82])
        licht /= np.linalg.norm(licht)
        hell = 0.42 + 0.58 * np.clip(normal @ licht, 0, 1)

        # Kanten als Teilstücke mit eigener Tiefe – leicht zum Betrachter verschoben
        stuecke = []
        for linie in n.kanten:
            q = (linie - self._mitte) @ R.T
            for i in range(len(q) - 1):
                stuecke.append((float(q[i:i + 2, 2].mean()) + 0.008 * self._radius,
                                (cx + q[i, 0] * massstab, cy - q[i, 1] * massstab,
                                 cx + q[i + 1, 0] * massstab, cy - q[i + 1, 1] * massstab)))
        reihenfolge = [(float(tiefe[i]), 0, int(i)) for i in np.nonzero(sichtbar)[0]]
        reihenfolge += [(t, 1, k) for k, (t, _) in enumerate(stuecke)]
        reihenfolge.sort(key=lambda x: x[0])

        kanten_stift = QPen(farben["kante"], 1.2)
        schnitt = self.schnittflaechen
        for _, art, i in reihenfolge:
            if art == 0:
                a, b, c = T[i]
                if schnitt is not None and schnitt[i]:
                    rgb = np.clip(farben["schnitt"] * max(hell[i], 0.92), 0, 255).astype(int)
                else:
                    rgb = np.clip(farben["teil"] * hell[i], 0, 255).astype(int)
                farbe = QColor(int(rgb[0]), int(rgb[1]), int(rgb[2]))
                p.setPen(QPen(farbe, 0.8))
                p.setBrush(farbe)
                p.drawPolygon(QPolygonF([QPointF(sx[a], sy[a]), QPointF(sx[b], sy[b]), QPointF(sx[c], sy[c])]))
            else:
                x0, y0, x1, y1 = stuecke[i][1]
                p.setPen(kanten_stift)
                p.drawLine(QPointF(x0, y0), QPointF(x1, y1))
        self._achsenkreuz(p, R, farben["text"])

    def _achsenkreuz(self, p: QPainter, R: np.ndarray, farbe: QColor):
        ursprung = QPointF(34, self.height() - 34)
        for achse, name, f in ((0, "x", QColor(210, 70, 70)), (1, "y", QColor(70, 170, 90)), (2, "z", QColor(70, 120, 220))):
            v = R[:, achse]
            ende = QPointF(ursprung.x() + v[0] * 22, ursprung.y() - v[1] * 22)
            p.setPen(QPen(f, 2))
            p.drawLine(ursprung, ende)
            p.setPen(farbe)
            p.drawText(QPointF(ende.x() + 3, ende.y() + 4), name)
