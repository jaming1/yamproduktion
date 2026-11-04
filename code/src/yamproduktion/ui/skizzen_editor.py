"""2D-Skizzen-Editor (Lastenheft M27): zeichnen, Bedingungen setzen, bemaßen – der Löser hält alles stimmig.

Werkzeuge: Auswahl, Linie (Kette, Esc beendet), Rechteck (2 Klicks), Kreis (Mitte, Rand), Bogen (Mitte, Anfang,
Ende gegen den Uhrzeigersinn). Klicks in der Nähe eines Punktes rasten dort ein (gemeinsamer Punkt).
Bedingungen wirken auf die Auswahl (Klick wählt, Umschalt+Klick erweitert). Entf löscht die Auswahl.
"""
from __future__ import annotations

import copy
import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QGridLayout, QHBoxLayout, QInputDialog, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QVBoxLayout, QWidget,
)

from ..berechnungen.basis import formatiere
from ..cad import skizze as S
from ..cad.ausdruck import AusdruckFehler, auswerten

WERKZEUGE = {"auswahl": "Auswahl", "linie": "Linie", "rechteck": "Rechteck", "kreis": "Kreis", "bogen": "Bogen"}
ZEICHEN = {"horizontal": "H", "vertikal": "V", "parallel": "∥", "senkrecht": "⊥", "gleich": "=", "tangential": "T",
           "koinzident": "●", "auf_linie": "∈", "fix": "⚓"}
FANG_PX = 9


class Zeichenflaeche(QWidget):
    """Die eigentliche Zeichenfläche. Koordinaten der Skizze in mm, v nach oben."""
    geaendert = Signal()          # Skizze verändert (gelöst)
    meldung = Signal(str, bool)

    def __init__(self):
        super().__init__()
        self.setMinimumSize(340, 380)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        self.setAccessibleName("Skizzen-Zeichenfläche")
        self.sk = S.leer()
        self.parameter: dict[str, float] = {}
        self.ber = None
        self.werkzeug = "auswahl"
        self.hilfslinie = False
        self.auswahl: list[str] = []
        self._klicks: list[str] = []      # Punkt-ids der laufenden Eingabe
        self._maus = None                 # aktuelle Mausposition (Skizze)
        self._ziehen = None
        self.massstab = 3.0
        self.mitte = [0.0, 0.0]
        self.status = ""

    # ---------- Koordinaten ----------
    def nach_bild(self, u: float, v: float) -> QPointF:
        return QPointF(self.width() / 2 + (u - self.mitte[0]) * self.massstab,
                       self.height() / 2 - (v - self.mitte[1]) * self.massstab)

    def nach_skizze(self, p: QPointF) -> tuple[float, float]:
        return ((p.x() - self.width() / 2) / self.massstab + self.mitte[0],
                -(p.y() - self.height() / 2) / self.massstab + self.mitte[1])

    def alles_zeigen(self):
        xs, ys = [0.0], [0.0]
        for e in self.sk["elemente"]:
            if e["art"] == "kreis":
                m = self.sk["punkte"][e["m"]]
                xs += [m[0] - e["r"], m[0] + e["r"]]
                ys += [m[1] - e["r"], m[1] + e["r"]]
        for x, y in self.sk["punkte"].values():
            xs.append(x)
            ys.append(y)
        b, h = max(max(xs) - min(xs), 10), max(max(ys) - min(ys), 10)
        self.mitte = [(max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2]
        self.massstab = 0.75 * min(max(self.width(), 200) / b, max(self.height(), 200) / h)
        self.update()

    # ---------- Daten ----------
    def setze(self, sk: dict, parameter: dict | None = None, ber=None):
        self.sk = copy.deepcopy(sk)
        self.parameter = parameter or {}
        self.ber = ber
        self.auswahl, self._klicks = [], []
        self.loesen(melden=False)
        self.alles_zeigen()

    def loesen(self, melden: bool = True) -> bool:
        try:
            neu, l = S.geloest(self.sk, self.parameter, self.ber)
        except (S.GeometrieFehler, AusdruckFehler) as exc:
            self.status = f"⚠ {exc}"
            self.update()
            return False
        if l.ok:
            self.sk = neu
            self.status = ("✓ Vollständig bestimmt" if l.freiheitsgrade == 0 else
                           f"Noch {l.freiheitsgrade} Freiheitsgrad{'e' if l.freiheitsgrade > 1 else ''} offen")
        else:
            self.status = f"⚠ {l.meldung}"
        self.update()
        if melden:
            self.geaendert.emit()
        return l.ok

    def _fang(self, u: float, v: float) -> str | None:
        beste, abstand = None, FANG_PX / self.massstab
        for pid, (x, y) in self.sk["punkte"].items():
            d = math.hypot(x - u, y - v)
            if d <= abstand:
                beste, abstand = pid, d
        return beste

    def _punkt(self, u: float, v: float) -> str:
        return self._fang(u, v) or S.punkt_neu(self.sk, u, v)

    def treffer(self, u: float, v: float) -> str | None:
        """Punkt oder Element unter der Maus."""
        pid = self._fang(u, v)
        if pid:
            return pid
        tol = FANG_PX / self.massstab
        beste, bd = None, tol
        P = self.sk["punkte"]
        for e in self.sk["elemente"]:
            if e["art"] == "linie":
                (x0, y0), (x1, y1) = P[e["p"][0]], P[e["p"][1]]
                dx, dy = x1 - x0, y1 - y0
                t = max(0.0, min(1.0, ((u - x0) * dx + (v - y0) * dy) / max(dx * dx + dy * dy, 1e-12)))
                d = math.hypot(u - x0 - t * dx, v - y0 - t * dy)
            else:
                m = P[e["m"]]
                r = e["r"] if e["art"] == "kreis" else math.hypot(P[e["p"][0]][0] - m[0], P[e["p"][0]][1] - m[1])
                d = abs(math.hypot(u - m[0], v - m[1]) - r)
                if e["art"] == "bogen" and not self._im_bogen(e, u, v):
                    d = tol * 2
            if d < bd:
                beste, bd = e["id"], d
        return beste

    def _bogenwinkel(self, e):
        P = self.sk["punkte"]
        m, a, b = P[e["m"]], P[e["p"][0]], P[e["p"][1]]
        w0 = math.degrees(math.atan2(a[1] - m[1], a[0] - m[0]))
        w1 = math.degrees(math.atan2(b[1] - m[1], b[0] - m[0]))
        spanne = (w1 - w0) % 360 or 360
        return w0, spanne

    def _im_bogen(self, e, u, v):
        m = self.sk["punkte"][e["m"]]
        w0, spanne = self._bogenwinkel(e)
        w = math.degrees(math.atan2(v - m[1], u - m[0]))
        return (w - w0) % 360 <= spanne

    # ---------- Eingabe ----------
    def setze_werkzeug(self, name: str):
        self.werkzeug = name
        self._klicks = []
        self.update()

    def klick(self, u: float, v: float, erweitern: bool = False):
        """Ein Klick in Skizzenkoordinaten (mm) – gleich wie mit der Maus; für Tests und Tastatur."""
        w = self.werkzeug
        if w == "auswahl":
            t = self.treffer(u, v)
            if not erweitern:
                self.auswahl = []
            if t and t in self.auswahl:
                self.auswahl.remove(t)
            elif t:
                self.auswahl.append(t)
            self.update()
            return
        if w == "rechteck":
            if not self._klicks:
                self._klicks = [self._fang(u, v) or f"@{u},{v}"]
                self.update()
                return
            erster = self._klicks[0]
            x0, y0 = self.sk["punkte"][erster] if not erster.startswith("@") else map(float, erster[1:].split(","))
            if abs(u - x0) < 1e-6 or abs(v - y0) < 1e-6:
                return
            e = S.rechteck_neu(self.sk, x0, y0, u, v)
            ecke = S.element(self.sk, e[0])["p"][0]
            if not erster.startswith("@"):
                S.bedingung(self.sk, "koinzident", a=erster, b=ecke)
            gegen = self._fang(u, v)
            ecke2 = S.element(self.sk, e[1])["p"][1]
            if gegen and gegen != ecke2 and gegen in self.sk["punkte"] and gegen not in S.element(self.sk, e[1])["p"]:
                S.bedingung(self.sk, "koinzident", a=gegen, b=ecke2)
            self._klicks = []
            self.loesen()
            return
        pid = self._punkt(u, v)
        self._klicks.append(pid)
        if w == "linie" and len(self._klicks) == 2:
            a, b = self._klicks
            if a != b:
                S.linie_neu(self.sk, a, b, hilf=self.hilfslinie)
                self._klicks = [b]
                self.loesen()
            else:
                self._klicks = [a]
        elif w == "kreis" and len(self._klicks) == 2:
            m, rand = self._klicks
            mx, my = self.sk["punkte"][m]
            rx, ry = self.sk["punkte"][rand]
            r = math.hypot(rx - mx, ry - my)
            self._aufraeumen(rand)
            if r > 1e-6:
                S.kreis_neu(self.sk, m, r)
            self._klicks = []
            self.loesen()
        elif w == "bogen" and len(self._klicks) == 3:
            m, a, b = self._klicks
            (mx, my), (ax, ay), (bx, by) = (self.sk["punkte"][k] for k in (m, a, b))
            r = math.hypot(ax - mx, ay - my)
            wb = math.atan2(by - my, bx - mx)
            if not self._fang(*self.sk["punkte"][b]) or b not in self._alte_punkte():
                self.sk["punkte"][b] = [mx + r * math.cos(wb), my + r * math.sin(wb)]
            S.bogen_neu(self.sk, m, a, b)
            self._klicks = []
            self.loesen()
        else:
            self.update()

    def _alte_punkte(self):
        benutzt = {"p0"}
        for e in self.sk["elemente"]:
            benutzt.update(e.get("p", []))
            if "m" in e:
                benutzt.add(e["m"])
        return benutzt

    def _aufraeumen(self, pid: str):
        """Hilfspunkt (z. B. Kreisrand) wieder entfernen, wenn ihn nichts benutzt."""
        if pid != "p0" and pid not in self._alte_punkte() and \
                not any(pid in (b.get("a"), b.get("b")) for b in self.sk["bedingungen"]):
            self.sk["punkte"].pop(pid, None)

    def abbrechen(self):
        for pid in self._klicks:
            if not pid.startswith("@"):
                self._aufraeumen(pid)
        self._klicks = []
        self.update()

    def loeschen(self):
        for t in list(self.auswahl):
            if t in {e["id"] for e in self.sk["elemente"]}:
                S.element_loeschen(self.sk, t)
        self.auswahl = []
        self.loesen()

    # ---------- Bedingungen ----------
    def _arten(self):
        ids = {e["id"]: e["art"] for e in self.sk["elemente"]}
        return [("punkt" if t in self.sk["punkte"] else ids.get(t)) for t in self.auswahl]

    def messen(self, art: str, b: dict) -> float:
        """Aktueller Wert einer Bemaßung – Vorschlag für den Dialog."""
        P = self.sk["punkte"]
        if art == "laenge":
            e = S.element(self.sk, b["e"])
            (x0, y0), (x1, y1) = P[e["p"][0]], P[e["p"][1]]
            return math.hypot(x1 - x0, y1 - y0)
        if art in ("radius", "durchmesser"):
            e = S.element(self.sk, b["e"])
            m = P[e["m"]]
            r = e["r"] if e["art"] == "kreis" else math.hypot(P[e["p"][0]][0] - m[0], P[e["p"][0]][1] - m[1])
            return r if art == "radius" else 2 * r
        if art in ("abstand", "abstand_h", "abstand_v"):
            if b["b"] in P and b["a"] in P:
                (x0, y0), (x1, y1) = P[b["a"]], P[b["b"]]
                return {"abstand": math.hypot(x1 - x0, y1 - y0), "abstand_h": abs(x1 - x0), "abstand_v": abs(y1 - y0)}[art]
            pid, eid = (b["a"], b["b"]) if b["a"] in P else (b["b"], b["a"])
            e = S.element(self.sk, eid)
            (x0, y0), (x1, y1) = P[e["p"][0]], P[e["p"][1]]
            x, y = P[pid]
            return abs((x1 - x0) * (y0 - y) - (x0 - x) * (y1 - y0)) / max(math.hypot(x1 - x0, y1 - y0), 1e-12)
        if art == "winkel":
            r = []
            for k in (b["a"], b["b"]):
                e = S.element(self.sk, k)
                (x0, y0), (x1, y1) = P[e["p"][0]], P[e["p"][1]]
                r.append(math.atan2(y1 - y0, x1 - x0))
            w = abs(math.degrees(r[1] - r[0])) % 180
            return w
        return 0.0

    def bedingen(self, art: str, wert=None, interaktiv: bool = False) -> bool:
        """Setzt die Bedingung `art` auf die Auswahl. Widerspricht sie, wird sie wieder entfernt."""
        vorher = copy.deepcopy(self.sk)
        a = self.auswahl
        arten = self._arten()
        linien = all(x == "linie" for x in arten)
        rund = all(x in ("kreis", "bogen") for x in arten)
        b: dict | None = None
        if art in ("horizontal", "vertikal", "laenge") and len(a) == 1 and arten == ["linie"]:
            b = {"e": a[0]}
        elif art in ("horizontal", "vertikal") and len(a) == 2 and arten == ["punkt", "punkt"]:
            hilf = S.linie_neu(self.sk, a[0], a[1], hilf=True)
            b = {"e": hilf}
        elif art in ("parallel", "senkrecht", "winkel") and len(a) == 2 and linien:
            b = {"a": a[0], "b": a[1]}
        elif art == "gleich" and len(a) == 2 and (linien or rund):
            b = {"a": a[0], "b": a[1]}
        elif art in ("radius", "durchmesser") and len(a) == 1 and rund:
            b = {"e": a[0]}
        elif art == "tangential" and len(a) == 2 and sorted(arten)[1] in ("kreis", "bogen", "linie") and \
                any(x in ("kreis", "bogen") for x in arten):
            b = {"a": a[0], "b": a[1]}
        elif art == "koinzident" and len(a) == 2 and arten == ["punkt", "punkt"]:
            b = {"a": a[0], "b": a[1]}
        elif art in ("auf_linie", "koinzident") and len(a) == 2 and sorted(arten) == ["linie", "punkt"]:
            art = "auf_linie"
            b = {"a": a[arten.index("punkt")], "b": a[arten.index("linie")]}
        elif art in ("abstand", "abstand_h", "abstand_v") and len(a) == 2 and arten == ["punkt", "punkt"]:
            b = {"a": a[0], "b": a[1]}
        elif art == "abstand" and len(a) == 2 and sorted(arten) == ["linie", "punkt"]:
            b = {"a": a[arten.index("punkt")], "b": a[arten.index("linie")]}
        elif art == "fix" and len(a) == 1 and arten == ["punkt"]:
            b = {"a": a[0]}
        if b is None:
            self.sk = vorher
            self.meldung.emit(f"„{S.BEDINGUNGEN[art][0]}“ passt nicht zur Auswahl ({self._auswahl_text()}). "
                              + HINWEISE.get(art, ""), True)
            return False
        if S.BEDINGUNGEN[art][1]:
            vorschlag = self.messen(art, b)
            if wert is None and interaktiv:
                text, ok = QInputDialog.getText(self, S.BEDINGUNGEN[art][0],
                                                "Wert (mm bzw. °) oder Formel mit Parametern, z. B. d/2:",
                                                text=formatiere(vorschlag))
                if not ok or not text.strip():
                    self.sk = vorher
                    return False
                wert = text.strip()
            b["wert"] = str(wert if wert is not None else round(vorschlag, 4))
            try:
                auswerten(b["wert"], self.parameter, self.ber)
            except AusdruckFehler as exc:
                self.sk = vorher
                self.meldung.emit(str(exc), True)
                return False
        S.bedingung(self.sk, art, **b)
        if not self.loesen(melden=False):
            meldung = self.status.lstrip("⚠ ")
            self.sk = vorher
            self.loesen(melden=False)
            self.meldung.emit(f"{S.BEDINGUNGEN[art][0]} nicht gesetzt: {meldung}", True)
            return False
        self.geaendert.emit()
        return True

    def _auswahl_text(self) -> str:
        if not self.auswahl:
            return "nichts gewählt"
        namen = {"punkt": "Punkt", "linie": "Linie", "kreis": "Kreis", "bogen": "Bogen"}
        return ", ".join(namen.get(x, "?") for x in self._arten())

    def bedingung_entfernen(self, index: int):
        del self.sk["bedingungen"][index]
        self.loesen()

    # ---------- Maus / Tasten ----------
    def mousePressEvent(self, ev):
        self.setFocus()
        if ev.button() == Qt.RightButton or ev.button() == Qt.MiddleButton:
            self._ziehen = ev.position()
            return
        u, v = self.nach_skizze(ev.position())
        self.klick(u, v, erweitern=bool(ev.modifiers() & (Qt.ShiftModifier | Qt.ControlModifier | Qt.MetaModifier)))

    def mouseMoveEvent(self, ev):
        if self._ziehen is not None:
            d = ev.position() - self._ziehen
            self.mitte[0] -= d.x() / self.massstab
            self.mitte[1] += d.y() / self.massstab
            self._ziehen = ev.position()
        self._maus = self.nach_skizze(ev.position())
        if self._klicks or self._ziehen is not None:
            self.update()

    def mouseReleaseEvent(self, ev):
        self._ziehen = None

    def mouseDoubleClickEvent(self, ev):
        if self.werkzeug == "linie":
            self.abbrechen()

    def wheelEvent(self, ev):
        vorher = self.nach_skizze(ev.position())
        self.massstab = max(0.02, min(200.0, self.massstab * 1.0015 ** ev.angleDelta().y()))
        nachher = self.nach_skizze(ev.position())
        self.mitte[0] += vorher[0] - nachher[0]
        self.mitte[1] += vorher[1] - nachher[1]
        self.update()

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key_Escape:
            self.abbrechen()
        elif ev.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self.loeschen()
        else:
            super().keyPressEvent(ev)

    # ---------- Zeichnen ----------
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        pal = self.palette()
        hg = pal.base().color()
        dunkel = hg.lightness() < 128
        text = pal.windowText().color()
        akzent = pal.highlight().color()
        linie = QColor(225, 230, 236) if dunkel else QColor(30, 36, 44)
        raster = QColor(255, 255, 255, 18) if dunkel else QColor(0, 0, 0, 16)
        mass_farbe = QColor(255, 176, 92) if dunkel else QColor(176, 92, 0)
        p.fillRect(self.rect(), hg)

        # Raster: 1-2-5-Schritte, etwa alle 40 px
        roh = 40 / self.massstab
        stufe = 10 ** math.floor(math.log10(roh))
        schritt = next(s * stufe for s in (1, 2, 5, 10) if s * stufe >= roh)
        u0, v1 = self.nach_skizze(QPointF(0, 0))
        u1, v0 = self.nach_skizze(QPointF(self.width(), self.height()))
        p.setPen(QPen(raster, 1))
        u = math.floor(u0 / schritt) * schritt
        while u <= u1:
            x = self.nach_bild(u, 0).x()
            p.drawLine(QPointF(x, 0), QPointF(x, self.height()))
            u += schritt
        v = math.floor(v0 / schritt) * schritt
        while v <= v1:
            y = self.nach_bild(0, v).y()
            p.drawLine(QPointF(0, y), QPointF(self.width(), y))
            v += schritt
        o = self.nach_bild(0, 0)
        p.setPen(QPen(QColor(210, 70, 70, 160), 1.2))
        p.drawLine(QPointF(0, o.y()), QPointF(self.width(), o.y()))
        p.setPen(QPen(QColor(70, 170, 90, 160), 1.2))
        p.drawLine(QPointF(o.x(), 0), QPointF(o.x(), self.height()))

        P = self.sk["punkte"]
        for e in self.sk["elemente"]:
            gewaehlt = e["id"] in self.auswahl
            stift = QPen(akzent if gewaehlt else linie, 2.6 if gewaehlt else 1.8)
            if e.get("hilf"):
                stift.setStyle(Qt.DashLine)
                stift.setWidthF(1.2)
            p.setPen(stift)
            p.setBrush(Qt.NoBrush)
            if e["art"] == "linie":
                p.drawLine(self.nach_bild(*P[e["p"][0]]), self.nach_bild(*P[e["p"][1]]))
            else:
                m = P[e["m"]]
                if e["art"] == "kreis":
                    r = e["r"]
                    w0, spanne = 0.0, 360.0
                else:
                    a = P[e["p"][0]]
                    r = math.hypot(a[0] - m[0], a[1] - m[1])
                    w0, spanne = self._bogenwinkel(e)
                c = self.nach_bild(*m)
                rr = r * self.massstab
                p.drawArc(QRectF(c.x() - rr, c.y() - rr, 2 * rr, 2 * rr), int(w0 * 16), int(spanne * 16))

        # Bedingungen und Bemaßungen
        klein = QFont(self.font())
        klein.setPointSizeF(max(self.font().pointSizeF() * 0.8, 8))
        p.setFont(klein)
        for i, b in enumerate(self.sk["bedingungen"]):
            ort = self._ort(b)
            if ort is None:
                continue
            if S.BEDINGUNGEN[b["art"]][1]:
                wert = b.get("wert", "")
                try:
                    zahl = auswerten(wert, self.parameter, self.ber)
                    beschriftung = formatiere(zahl) if _ist_zahl(wert) else f"{wert} = {formatiere(zahl)}"
                except AusdruckFehler:
                    beschriftung = f"{wert} ?"
                vor = {"radius": "R ", "durchmesser": "Ø ", "winkel": "∠ "}.get(b["art"], "")
                nach = " °" if b["art"] == "winkel" else ""
                self._schild(p, ort, vor + beschriftung + nach, mass_farbe, hg)
            elif b["art"] in ZEICHEN and b["art"] not in ("koinzident",):
                p.setPen(QColor(text.red(), text.green(), text.blue(), 150))
                p.drawText(ort + QPointF(4, -4), ZEICHEN[b["art"]])

        for pid, (x, y) in P.items():
            q = self.nach_bild(x, y)
            gewaehlt = pid in self.auswahl or pid in self._klicks
            p.setPen(Qt.NoPen)
            p.setBrush(akzent if gewaehlt else (QColor(210, 70, 70) if pid == "p0" else linie))
            g = 7 if gewaehlt else 5
            p.drawRect(QRectF(q.x() - g / 2, q.y() - g / 2, g, g))

        # Gummiband der laufenden Eingabe
        if self._klicks and self._maus:
            p.setPen(QPen(akzent, 1.2, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            erster = self._klicks[0]
            start = P[erster] if not erster.startswith("@") else tuple(map(float, erster[1:].split(",")))
            a, m = self.nach_bild(*start), self.nach_bild(*self._maus)
            if self.werkzeug == "linie":
                p.drawLine(self.nach_bild(*P[self._klicks[-1]]), m)
            elif self.werkzeug == "rechteck":
                p.drawRect(QRectF(a, m).normalized())
            elif self.werkzeug in ("kreis", "bogen"):
                rr = math.hypot(m.x() - a.x(), m.y() - a.y())
                p.drawEllipse(a, rr, rr)

        hinweis = HILFE[self.werkzeug] if not self._klicks else HILFE_WEITER.get(self.werkzeug, "")
        p.setFont(self.font())
        p.setPen(QColor(text.red(), text.green(), text.blue(), 170))
        p.drawText(QRectF(10, 8, self.width() - 20, 22), Qt.AlignLeft, hinweis)
        if self.status:
            if self.status.startswith("⚠"):
                p.setPen(QColor(255, 138, 128) if dunkel else QColor(179, 38, 30))
            elif self.status.startswith("✓"):
                p.setPen(QColor(111, 208, 138) if dunkel else QColor(30, 123, 52))
            else:
                p.setPen(QColor(text.red(), text.green(), text.blue(), 170))
            p.drawText(QRectF(10, self.height() - 28, self.width() - 20, 22), Qt.AlignLeft, self.status)

    def _schild(self, p: QPainter, ort: QPointF, text: str, farbe: QColor, hg: QColor):
        m = p.fontMetrics()
        b, h = m.horizontalAdvance(text) + 10, m.height() + 4
        r = QRectF(ort.x() - b / 2, ort.y() - h / 2, b, h)
        p.setPen(QPen(farbe, 1))
        p.setBrush(hg)
        p.drawRoundedRect(r, 4, 4)
        p.setPen(farbe)
        p.drawText(r, Qt.AlignCenter, text)

    def _ort(self, b: dict) -> QPointF | None:
        P = self.sk["punkte"]
        try:
            if "e" in b:
                e = S.element(self.sk, b["e"])
                if e["art"] == "linie":
                    (x0, y0), (x1, y1) = P[e["p"][0]], P[e["p"][1]]
                    lang = max(math.hypot(x1 - x0, y1 - y0), 1e-9)
                    nx, ny = -(y1 - y0) / lang, (x1 - x0) / lang
                    a = 16 / self.massstab
                    return self.nach_bild((x0 + x1) / 2 + nx * a, (y0 + y1) / 2 + ny * a)
                m = P[e["m"]]
                r = e["r"] if e["art"] == "kreis" else math.hypot(P[e["p"][0]][0] - m[0], P[e["p"][0]][1] - m[1])
                return self.nach_bild(m[0] + r * 0.72 + 6 / self.massstab, m[1] + r * 0.72 + 6 / self.massstab)
            pkt = []
            for k in (b.get("a"), b.get("b")):
                if k in P:
                    pkt.append(P[k])
                elif k:
                    e = S.element(self.sk, k)
                    if e["art"] == "linie":
                        (x0, y0), (x1, y1) = P[e["p"][0]], P[e["p"][1]]
                        pkt.append(((x0 + x1) / 2, (y0 + y1) / 2))
                    else:
                        pkt.append(P[e["m"]])
            if not pkt:
                return None
            x = sum(q[0] for q in pkt) / len(pkt)
            y = sum(q[1] for q in pkt) / len(pkt)
            if b["art"] == "abstand_h" and len(pkt) == 2:
                y = min(pkt[0][1], pkt[1][1]) - 12 / self.massstab
            elif b["art"] == "abstand_v" and len(pkt) == 2:
                x = max(pkt[0][0], pkt[1][0]) + 14 / self.massstab
            return self.nach_bild(x, y)
        except KeyError:
            return None


def _ist_zahl(text) -> bool:
    try:
        float(str(text).replace(",", "."))
        return True
    except ValueError:
        return False


HILFE = {
    "auswahl": "Klick wählt · ⇧ mehrere · Mausrad zoomt",
    "linie": "Linie: Startpunkt klicken",
    "rechteck": "Rechteck: erste Ecke klicken",
    "kreis": "Kreis: Mittelpunkt klicken",
    "bogen": "Bogen: Mittelpunkt klicken",
}
HILFE_WEITER = {
    "linie": "Nächster Punkt · Doppelklick oder Esc beendet die Kette",
    "rechteck": "Gegenüberliegende Ecke klicken",
    "kreis": "Punkt auf dem Rand klicken",
    "bogen": "Anfang, dann Ende klicken (gegen den Uhrzeigersinn)",
}
HINWEISE = {
    "horizontal": "Eine Linie oder zwei Punkte wählen.",
    "vertikal": "Eine Linie oder zwei Punkte wählen.",
    "laenge": "Eine Linie wählen.",
    "parallel": "Zwei Linien wählen.",
    "senkrecht": "Zwei Linien wählen.",
    "winkel": "Zwei Linien wählen.",
    "gleich": "Zwei Linien oder zwei Kreise/Bögen wählen.",
    "radius": "Einen Kreis oder Bogen wählen.",
    "durchmesser": "Einen Kreis oder Bogen wählen.",
    "tangential": "Linie und Bogen oder zwei Bögen wählen.",
    "koinzident": "Zwei Punkte oder Punkt und Linie wählen.",
    "abstand": "Zwei Punkte oder Punkt und Linie wählen.",
    "abstand_h": "Zwei Punkte wählen.",
    "abstand_v": "Zwei Punkte wählen.",
    "fix": "Einen Punkt wählen.",
}
KNOEPFE = [   # (Bedingung, Beschriftung, Tipp)
    ("horizontal", "Waagerecht", "Linie (oder zwei Punkte) waagerecht"),
    ("vertikal", "Senkrecht", "Linie (oder zwei Punkte) senkrecht"),
    ("parallel", "Parallel", "Zwei Linien parallel"),
    ("senkrecht", "Rechtwinklig", "Zwei Linien im rechten Winkel"),
    ("gleich", "Gleich", "Gleich lang bzw. gleicher Radius"),
    ("tangential", "Tangential", "Linie berührt Bogen tangential"),
    ("koinzident", "Deckungsgleich", "Punkte aufeinander bzw. Punkt auf Linie"),
    ("fix", "Fest", "Punkt festhalten"),
    ("laenge", "Länge …", "Länge einer Linie bemaßen"),
    ("abstand", "Abstand …", "Abstand Punkt–Punkt oder Punkt–Linie"),
    ("abstand_h", "Abstand ↔ …", "Waagerechter Abstand zweier Punkte"),
    ("abstand_v", "Abstand ↕ …", "Senkrechter Abstand zweier Punkte"),
    ("durchmesser", "Ø …", "Durchmesser eines Kreises"),
    ("radius", "R …", "Radius eines Kreises oder Bogens"),
    ("winkel", "Winkel …", "Winkel zwischen zwei Linien"),
]


class SkizzenEditor(QWidget):
    """Zeichenfläche mit Werkzeugleiste, Bedingungsknöpfen und Liste der Bedingungen."""
    fertig = Signal()
    geaendert = Signal()
    meldung = Signal(str, bool)

    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        leiste = QHBoxLayout()
        self.werkzeug_knoepfe = QButtonGroup(self)
        self.werkzeug_knoepfe.setExclusive(True)
        self.knopf: dict[str, QPushButton] = {}
        for schluessel, text in WERKZEUGE.items():
            b = QPushButton(text)
            b.setObjectName("Skizze")
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, s=schluessel: self.flaeche.setze_werkzeug(s))
            self.werkzeug_knoepfe.addButton(b)
            self.knopf[schluessel] = b
            leiste.addWidget(b)
        self.knopf["auswahl"].setChecked(True)
        self.hilf = QCheckBox("Hilfslinie")
        self.hilf.setToolTip("Gestrichelte Linie, gehört nicht zum Profil – z. B. als Drehachse")
        self.hilf.toggled.connect(lambda an: setattr(self.flaeche, "hilfslinie", an))
        leiste.addWidget(self.hilf)
        leiste.addStretch()
        b = QPushButton("Einpassen")
        b.setObjectName("Skizze")
        b.setToolTip("Ganze Skizze zeigen")
        b.clicked.connect(lambda: self.flaeche.alles_zeigen())
        leiste.addWidget(b)
        lay.addLayout(leiste)

        mitte = QHBoxLayout()
        self.flaeche = Zeichenflaeche()
        self.flaeche.geaendert.connect(self._geaendert)
        self.flaeche.meldung.connect(self.meldung.emit)
        mitte.addWidget(self.flaeche, 1)
        seiten_box = QWidget()
        seiten_box.setFixedWidth(250)
        seite = QVBoxLayout(seiten_box)
        seite.setContentsMargins(0, 0, 0, 0)
        self.fertig_knopf = QPushButton("Skizze fertig")
        self.fertig_knopf.setObjectName("Haupt")
        self.fertig_knopf.setToolTip("Zurück zur 3D-Ansicht")
        self.fertig_knopf.clicked.connect(self.fertig.emit)
        seite.addWidget(self.fertig_knopf)
        k = QLabel("Bedingungen")
        k.setObjectName("Unterabschnitt")
        seite.addWidget(k)
        raster = QGridLayout()
        raster.setSpacing(4)
        self.bedingungs_knopf: dict[str, QPushButton] = {}
        for i, (art, text, tipp) in enumerate(KNOEPFE):
            b = QPushButton(text)
            b.setObjectName("Skizze")
            b.setToolTip(tipp + ". " + HINWEISE.get(art, ""))
            b.clicked.connect(lambda _=False, a=art: self.flaeche.bedingen(a, interaktiv=True))
            raster.addWidget(b, i // 2, i % 2)
            self.bedingungs_knopf[art] = b
        seite.addLayout(raster)
        self.liste = QListWidget()
        self.liste.setAccessibleName("Liste der Bedingungen")
        seite.addWidget(self.liste, 1)
        entf = QPushButton("Bedingung entfernen")
        entf.setObjectName("Skizze")
        entf.clicked.connect(self._bedingung_entfernen)
        seite.addWidget(entf)
        mitte.addWidget(seiten_box)
        lay.addLayout(mitte, 1)

    def setze(self, sk: dict, parameter: dict, ber=None):
        self.flaeche.setze(sk, parameter, ber)
        self._liste_fuellen()

    @property
    def skizze(self) -> dict:
        return self.flaeche.sk

    def _geaendert(self):
        self._liste_fuellen()
        self.geaendert.emit()

    def _liste_fuellen(self):
        self.liste.clear()
        for b in self.flaeche.sk["bedingungen"]:
            name = S.BEDINGUNGEN[b["art"]][0]
            ziele = " · ".join(str(b[k]) for k in ("e", "a", "b") if k in b)
            text = f"{name}  {ziele}" + (f"  = {b['wert']}" if "wert" in b else "")
            self.liste.addItem(QListWidgetItem(text))

    def _bedingung_entfernen(self):
        z = self.liste.currentRow()
        if z >= 0:
            self.flaeche.bedingung_entfernen(z)
