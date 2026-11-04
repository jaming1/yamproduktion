"""Technische Zeichnung (Lastenheft M31): Ansichten, Schnitt, Bemaßung, Toleranzen, Schriftfeld; Export PDF und DXF.

Projektionsmethode 1 (Europa, ISO 128 / ISO 5456-2): Draufsicht unter, Seitenansicht von links rechts neben der
Vorderansicht. Die Teileachse z liegt in der Vorderansicht waagerecht (Wellen liegen, wie in der Zeichnung üblich).
Blatt A3 quer (420 × 297 mm), Rahmen und Schriftfeld in Anlehnung an ISO 7200, Linien nach ISO 128-20.

Die Zeichnung ist eine Liste einfacher Elemente in Blatt-Millimetern (Linie, Polygon, Text). Daraus entstehen
PDF, DXF und die Vorschau auf dem Bildschirm – alle drei zeigen dasselbe.
"""
from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.GCPnts import GCPnts_QuasiUniformDeflection
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
from OCP.HLRAlgo import HLRAlgo_Projector
from OCP.HLRBRep import HLRBRep_Algo, HLRBRep_HLRToShape
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
from OCP.TopExp import TopExp_Explorer

from ..berechnungen.basis import formatiere
from .geometrie import eigenschaften, schneiden

BLATT = (420.0, 297.0)                   # A3 quer
RAND_LINKS, RAND = 20.0, 10.0
SCHRIFTFELD = (180.0, 46.0)
MASSSTAEBE = (5.0, 2.0, 1.0, 0.5, 0.4, 0.2, 0.1, 0.05, 0.02)   # 5:1 … 1:50
ALLGEMEINTOLERANZ = "ISO 2768-mK"
# (Richtung zum Betrachter N, Blatt-rechts R) in Teilkoordinaten; Blatt-oben = N × R
ANSICHTEN = {
    "vorne": ((0, -1, 0), (0, 0, 1)),
    "oben": ((-1, 0, 0), (0, 0, 1)),
    "links": ((0, 0, -1), (0, -1, 0)),
}
LINIEN = {   # Art → (Breite mm, Strichmuster mm oder None)
    "sichtbar": (0.5, None), "verdeckt": (0.25, (3.0, 1.5)), "mitte": (0.25, (12.0, 2.0, 1.0, 2.0)),
    "duenn": (0.25, None), "rahmen": (0.7, None), "schraffur": (0.18, None), "schnittlinie": (0.7, None),
}


@dataclass
class Linie:
    x0: float
    y0: float
    x1: float
    y1: float
    art: str = "sichtbar"


@dataclass
class Polygon:
    punkte: list
    gefuellt: bool = True


@dataclass
class Text:
    x: float
    y: float
    text: str
    hoehe: float = 3.5
    ausrichtung: str = "mitte"   # links / mitte / rechts
    drehung: float = 0.0


@dataclass
class Zeichnung:
    elemente: list = field(default_factory=list)
    massstab: float = 1.0
    titel: str = ""
    breite: float = BLATT[0]
    hoehe: float = BLATT[1]
    hinweise: list = field(default_factory=list)

    def linie(self, *a, art="sichtbar"):
        self.elemente.append(Linie(*a, art=art))

    def text(self, *a, **k):
        self.elemente.append(Text(*a, **k))


def massstab_text(m: float) -> str:
    if m >= 1:
        return f"{m:g}:1"
    return f"1:{1 / m:g}"


# ---------------------------------------------------------------- Projektion
def _polylinie(kante, toleranz: float) -> list[tuple[float, float]]:
    c = BRepAdaptor_Curve(kante)
    a, b = c.FirstParameter(), c.LastParameter()
    if c.GetType().name == "GeomAbs_Line":
        p, q = c.Value(a), c.Value(b)
        return [(p.X(), p.Y()), (q.X(), q.Y())]
    d = GCPnts_QuasiUniformDeflection(c, toleranz, a, b)
    if d.IsDone() and d.NbPoints() >= 2:
        return [(d.Value(i).X(), d.Value(i).Y()) for i in range(1, d.NbPoints() + 1)]
    return [(c.Value(a + (b - a) * t / 16).X(), c.Value(a + (b - a) * t / 16).Y()) for t in range(17)]


def _kanten(form) -> list:
    from OCP.TopoDS import TopoDS
    kast = getattr(TopoDS, "Edge", None) or TopoDS.Edge_s
    out = []
    if form is None or form.IsNull():
        return out
    e = TopExp_Explorer(form, TopAbs_EDGE)
    while e.More():
        out.append(kast(e.Current()))
        e.Next()
    return out


def projizieren(form, ansicht: str, verdeckt: bool = True) -> dict[str, list]:
    """Verdeckte-Kanten-Projektion: {"sichtbar": [Polylinien], "verdeckt": [...]} in Teil-mm (Blattlage)."""
    N, R = ANSICHTEN[ansicht]
    algo = HLRBRep_Algo()
    algo.Add(form)
    algo.Projector(HLRAlgo_Projector(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(*N), gp_Dir(*R))))
    algo.Update()
    algo.Hide()
    h = HLRBRep_HLRToShape(algo)
    tol = max(0.01, max(eigenschaften(form).groesse) / 2000)
    erg = {"sichtbar": [], "verdeckt": []}
    for art, namen in (("sichtbar", ("VCompound", "OutLineVCompound")),
                       ("verdeckt", ("HCompound", "OutLineHCompound") if verdeckt else ())):
        for name in namen:
            for k in _kanten(getattr(h, name)()):
                erg[art].append(_polylinie(k, tol))
    return erg


def _blattlage(punkt3d, ansicht: str) -> tuple[float, float]:
    N, R = (np.array(v, float) for v in ANSICHTEN[ansicht])
    U = np.cross(N, R)
    p = np.asarray(punkt3d, float)
    return float(p @ R), float(p @ U)


def _grenzen(linien) -> tuple[float, float, float, float]:
    pts = [p for l in linien for p in l]
    if not pts:
        return 0, 0, 0, 0
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


# ---------------------------------------------------------------- Geometrie für die Bemaßung
@dataclass
class Zylinder:
    radius: float
    achse: tuple          # Richtung
    ort: tuple            # Punkt auf der Achse
    von: float            # Ausdehnung entlang der Achse (absolut, Punkt · Richtung)
    bis: float
    innen: bool           # Bohrung (Fläche zeigt zur Achse)


def zylinder_flaechen(form) -> list[Zylinder]:
    from OCP.TopoDS import TopoDS
    from OCP.TopAbs import TopAbs_REVERSED
    fast = getattr(TopoDS, "Face", None) or TopoDS.Face_s
    out = []
    e = TopExp_Explorer(form, TopAbs_FACE)
    while e.More():
        f = fast(e.Current())
        s = BRepAdaptor_Surface(f)
        if s.GetType().name == "GeomAbs_Cylinder":
            cyl = s.Cylinder()
            ax = cyl.Axis()
            d = np.array([ax.Direction().X(), ax.Direction().Y(), ax.Direction().Z()])
            o = np.array([ax.Location().X(), ax.Location().Y(), ax.Location().Z()])
            # Ausdehnung entlang der Achse aus den Kanten
            ts = []
            for k in _kanten(f):
                c = BRepAdaptor_Curve(k)
                for t in (c.FirstParameter(), c.LastParameter()):
                    p = c.Value(t)
                    ts.append(float(np.array([p.X(), p.Y(), p.Z()]) @ d))
            # innen: Flächennormale zeigt zur Achse – bei umgekehrter Orientierung der Fläche
            innen = f.Orientation() == TopAbs_REVERSED
            if ts:
                out.append(Zylinder(cyl.Radius(), tuple(d), tuple(o), min(ts), max(ts), innen))
        e.Next()
    return out


def ebenen_quer_zur_achse(form) -> list[float]:
    """z-Lage aller ebenen Flächen senkrecht zur z-Achse (Wellenabsätze, Stirnseiten)."""
    from OCP.TopoDS import TopoDS
    fast = getattr(TopoDS, "Face", None) or TopoDS.Face_s
    out = set()
    e = TopExp_Explorer(form, TopAbs_FACE)
    while e.More():
        s = BRepAdaptor_Surface(fast(e.Current()))
        if s.GetType().name == "GeomAbs_Plane":
            pl = s.Plane()
            if abs(abs(pl.Axis().Direction().Z()) - 1) < 1e-6:
                out.add(round(pl.Location().Z(), 3))
        e.Next()
    return sorted(out)


# ---------------------------------------------------------------- Bemaßung
def _pfeil(z: Zeichnung, x, y, richtung, laenge=3.0, breite=1.0):
    dx, dy = richtung
    n = math.hypot(dx, dy) or 1
    dx, dy = dx / n, dy / n
    z.elemente.append(Polygon([(x, y), (x - dx * laenge - dy * breite / 2, y - dy * laenge + dx * breite / 2),
                               (x - dx * laenge + dy * breite / 2, y - dy * laenge - dx * breite / 2)]))


def mass_waagerecht(z: Zeichnung, x0, x1, y_kante0, y_kante1, y_linie, text):
    """Waagerechtes Maß zwischen x0 und x1; Hilfslinien von den Kanten bis über die Maßlinie."""
    ueber = 2.0 if y_linie > max(y_kante0, y_kante1) else -2.0
    z.linie(x0, y_kante0 + math.copysign(1.0, ueber), x0, y_linie + ueber, art="duenn")
    z.linie(x1, y_kante1 + math.copysign(1.0, ueber), x1, y_linie + ueber, art="duenn")
    z.linie(x0, y_linie, x1, y_linie, art="duenn")
    if abs(x1 - x0) > 8:
        _pfeil(z, x0, y_linie, (-1, 0))
        _pfeil(z, x1, y_linie, (1, 0))
    else:   # Pfeile außen
        _pfeil(z, x0, y_linie, (1, 0))
        _pfeil(z, x1, y_linie, (-1, 0))
    z.text((x0 + x1) / 2, y_linie + 1.2, text, 3.5, "mitte")


def mass_senkrecht(z: Zeichnung, y0, y1, x_kante0, x_kante1, x_linie, text):
    links = x_linie < min(x_kante0, x_kante1)
    s = -1.0 if links else 1.0
    z.linie(x_kante0 + s, y0, x_linie + 2 * s, y0, art="duenn")
    z.linie(x_kante1 + s, y1, x_linie + 2 * s, y1, art="duenn")
    z.linie(x_linie, y0, x_linie, y1, art="duenn")
    if abs(y1 - y0) > 8:
        _pfeil(z, x_linie, y0, (0, -1) if y0 < y1 else (0, 1))
        _pfeil(z, x_linie, y1, (0, 1) if y0 < y1 else (0, -1))
    else:
        _pfeil(z, x_linie, y0, (0, 1) if y0 < y1 else (0, -1))
        _pfeil(z, x_linie, y1, (0, -1) if y0 < y1 else (0, 1))
    z.text(x_linie - 1.2, (y0 + y1) / 2, text, 3.5, "mitte", drehung=90)


def _durchmesser_text(d: float, toleranzen: dict) -> str:
    grund = f"Ø{formatiere(d)}"
    tol = toleranzen.get(formatiere(d)) or toleranzen.get(f"Ø{formatiere(d)}")
    return f"{grund} {tol}" if tol else grund


# ---------------------------------------------------------------- Schraffur
def _schraffur(z: Zeichnung, polygone: list[list[tuple]], abstand: float = 3.0, winkel: float = 45.0):
    """45°-Schraffur der Schnittflächen (gerade-ungerade-Regel, Löcher bleiben frei)."""
    if not polygone:
        return
    w = math.radians(winkel)
    d = np.array([math.cos(w), math.sin(w)])      # Linienrichtung
    nrm = np.array([-d[1], d[0]])
    alle = np.array([p for poly in polygone for p in poly])
    s_min, s_max = (alle @ nrm).min(), (alle @ nrm).max()
    s = s_min + abstand / 2
    while s < s_max:
        schnitte = []
        for poly in polygone:
            for i in range(len(poly)):
                a, b = np.array(poly[i]), np.array(poly[(i + 1) % len(poly)])
                sa, sb = a @ nrm - s, b @ nrm - s
                if (sa < 0) != (sb < 0):
                    t = sa / (sa - sb)
                    schnitte.append(float((a + t * (b - a)) @ d))
        schnitte.sort()
        for i in range(0, len(schnitte) - 1, 2):
            p, q = s * nrm + schnitte[i] * d, s * nrm + schnitte[i + 1] * d
            z.linie(p[0], p[1], q[0], q[1], art="schraffur")
        s += abstand


def _schnittflaechen(halbe, ebene_y: float, ansicht: str, toleranz: float) -> list[list[tuple]]:
    """Ebene Flächen des Halbschnitts in der Schnittebene y = ebene_y als 2D-Polygone (Teil-mm, Blattlage)."""
    from OCP.TopoDS import TopoDS
    from OCP.BRepTools import BRepTools_WireExplorer
    from OCP.TopAbs import TopAbs_WIRE
    fast = getattr(TopoDS, "Face", None) or TopoDS.Face_s
    wast = getattr(TopoDS, "Wire", None) or TopoDS.Wire_s
    polys = []
    e = TopExp_Explorer(halbe, TopAbs_FACE)
    while e.More():
        f = fast(e.Current())
        s = BRepAdaptor_Surface(f)
        if s.GetType().name == "GeomAbs_Plane":
            pl = s.Plane()
            n = pl.Axis().Direction()
            if abs(abs(n.Y()) - 1) < 1e-6 and abs(pl.Location().Y() - ebene_y) < 1e-4:
                we = TopExp_Explorer(f, TopAbs_WIRE)
                while we.More():
                    draht = wast(we.Current())
                    pts = []
                    wx = BRepTools_WireExplorer(draht)
                    while wx.More():
                        c = BRepAdaptor_Curve(wx.Current())
                        a, b = c.FirstParameter(), c.LastParameter()
                        n_p = 2 if c.GetType().name == "GeomAbs_Line" else 24
                        vorwaerts = wx.Current().Orientation().name == "TopAbs_FORWARD"
                        ts = [a + (b - a) * i / (n_p - 1) for i in range(n_p)]
                        if not vorwaerts:
                            ts.reverse()
                        for t in ts[:-1]:
                            p = c.Value(t)
                            pts.append(_blattlage((p.X(), p.Y(), p.Z()), ansicht))
                        wx.Next()
                    if len(pts) >= 3:
                        polys.append(pts)
                    we.Next()
        e.Next()
    return polys


# ---------------------------------------------------------------- Blatt
def _rahmen_und_schriftfeld(z: Zeichnung, felder: dict):
    W, H = BLATT
    z.linie(0, 0, W, 0, art="duenn")
    z.linie(W, 0, W, H, art="duenn")
    z.linie(W, H, 0, H, art="duenn")
    z.linie(0, H, 0, 0, art="duenn")
    x0, y0, x1, y1 = RAND_LINKS, RAND, W - RAND, H - RAND
    for a in ((x0, y0, x1, y0), (x1, y0, x1, y1), (x1, y1, x0, y1), (x0, y1, x0, y0)):
        z.linie(*a, art="rahmen")
    # Schriftfeld unten rechts
    bw, bh = SCHRIFTFELD
    sx, sy = x1 - bw, y0
    z.linie(sx, sy, sx, sy + bh, art="rahmen")
    z.linie(sx, sy + bh, x1, sy + bh, art="rahmen")
    zeilen = [sy + 10, sy + 19, sy + 28, sy + 37]
    for y in zeilen:
        z.linie(sx, y, x1, y, art="duenn")
    for x in (sx + 60, sx + 120):
        z.linie(x, sy + 19, x, sy + bh, art="duenn")
    z.linie(sx + 120, sy, sx + 120, sy + 19, art="duenn")

    def feld(x, y, titel, wert, gross=False):
        z.text(x + 1.5, y + 6.2, titel, 2.0, "links")
        wert = str(wert)
        if len(wert) > 30:          # Feld 60 mm breit
            wert = wert[:29] + "…"
        z.text(x + 1.5, y + 1.6, wert, 5.0 if gross else 3.0, "links")
    feld(sx, sy + 37, "Erstellt", felder.get("ersteller", ""))
    feld(sx + 60, sy + 37, "Datum", felder.get("datum", ""))
    feld(sx + 120, sy + 37, "Maßstab", felder.get("massstab", ""))
    feld(sx, sy + 28, "Werkstoff", felder.get("werkstoff", ""))
    feld(sx + 60, sy + 28, "Masse", felder.get("masse", ""))
    feld(sx + 120, sy + 28, "Allgemeintoleranz", felder.get("toleranz", ALLGEMEINTOLERANZ))
    feld(sx, sy + 19, "Projekt", felder.get("projekt", ""))
    feld(sx + 60, sy + 19, "Oberfläche (wenn nicht angegeben)", felder.get("oberflaeche", "Ra 3,2"))
    feld(sx + 120, sy + 19, "Blatt", felder.get("blatt", "1/1"))
    z.text(sx + 1.5, sy + 13.0, felder.get("benennung", ""), 5.0, "links")
    z.text(sx + 1.5, sy + 2.0, felder.get("sachnummer", ""), 5.0, "links")
    feld(sx + 120, sy + 10, "Version / Status", felder.get("version", ""))
    feld(sx + 120, sy, "Projektionsmethode", "")
    _symbol_methode1(z, sx + 160, sy + 4.5)
    return sx, sy + bh


def _symbol_methode1(z: Zeichnung, x, y):
    """Symbol Projektionsmethode 1 (ISO 128): Kegelstumpf, Kreise rechts."""
    z.linie(x - 8, y - 2.5, x - 8, y + 2.5, art="duenn")
    z.linie(x - 8, y + 2.5, x - 1, y + 4, art="duenn")
    z.linie(x - 1, y + 4, x - 1, y - 4, art="duenn")
    z.linie(x - 1, y - 4, x - 8, y - 2.5, art="duenn")
    for r in (4, 2.5):
        pts = [(x + 6 + r * math.cos(t * math.pi / 12), y + r * math.sin(t * math.pi / 12)) for t in range(25)]
        for a, b in zip(pts, pts[1:]):
            z.linie(*a, *b, art="duenn")


def _waehle_massstab(breite_mm: float, hoehe_mm: float, platz_b: float, platz_h: float) -> float:
    for m in MASSSTAEBE:
        if breite_mm * m <= platz_b and hoehe_mm * m <= platz_h:
            return m
    return MASSSTAEBE[-1]


def zeichnung_erstellen(form, felder: dict, schnitt: bool | None = None, toleranzen: dict | None = None,
                        massstab: float | None = None, stueckliste: list | None = None,
                        positionen: list | None = None) -> Zeichnung:
    """Zeichnung eines Teils (oder einer Baugruppe mit Stückliste) mit drei Ansichten.
    felder: benennung, sachnummer, werkstoff, masse, projekt, ersteller, version …
    toleranzen: {"80": "k6", "Ø140": "H7"} – an passende Durchmessermaße angehängt.
    positionen: [(Pos-Nr., (x, y, z))] – Positionsnummern der Baugruppenzeichnung mit Hinweislinie zum Punkt."""
    toleranzen = toleranzen or {}
    z = Zeichnung(titel=felder.get("benennung", ""))
    e = eigenschaften(form)
    # Teil so verschieben, dass seine Achse z durch den Ursprung geht (Mitte in x, y), Anfang bei z = 0
    from .baugruppe import bewegen
    M = np.eye(4)
    M[:3, 3] = [-(e.minimum[0] + e.maximum[0]) / 2, -(e.minimum[1] + e.maximum[1]) / 2, -e.minimum[2]]
    form = bewegen(form, M)
    e = eigenschaften(form)
    gx, gy, gz = e.groesse

    # Platz: links oben bis zum Schriftfeld (bzw. der Stückliste); Vorder- + Seitenansicht nebeneinander,
    # Draufsicht darunter
    W, H = BLATT
    nutz_b = W - RAND_LINKS - RAND - 30
    nutz_h = H - 2 * RAND - SCHRIFTFELD[1] - 30
    if stueckliste:
        nutz_h -= min(8 + 6 * len(stueckliste), 90)
    abstand = 35.0
    zyl = zylinder_flaechen(form)
    auf_achse = [c for c in zyl if abs(abs(c.achse[2]) - 1) < 1e-6 and math.hypot(c.ort[0], c.ort[1]) < 1e-3]
    # Draufsicht nur, wenn sie etwas Neues zeigt: nicht bei Drehteilen (Welle, Scheibe) und nicht bei flachen Teilen
    drehteil = bool(auf_achse) and abs(gx - gy) < 1e-3 and abs(2 * max(c.radius for c in auf_achse) - gx) < 1e-3
    mit_draufsicht = not drehteil and gz > 0.35 * max(gx, gy)
    z_parallel = [c for c in zyl if c.innen and abs(abs(c.achse[2]) - 1) < 1e-6]
    bohrbild = any(math.hypot(c.ort[0], c.ort[1]) > 1e-3 for c in z_parallel)
    if schnitt is None:      # Schnitt A–A automatisch bei Bohrungen längs der Achse; Wellen nach ISO 128-40 nicht
        schnitt = bool(z_parallel)
    # Seitenansicht entfällt bei Drehteilen ohne Schnitt und Lochbild: Ø-Maße beschreiben sie vollständig
    mit_seite = not (drehteil and not schnitt and not bohrbild and not stueckliste)
    hoehe_bedarf = gx + gy if mit_draufsicht else gx
    m = massstab or _waehle_massstab(gz + (gy if mit_seite else 0), hoehe_bedarf,
                                     nutz_b - (2 * abstand if mit_seite else 10),
                                     nutz_h - (2 if mit_draufsicht else 1) * abstand)
    z.massstab = m
    felder = dict(felder, massstab=massstab_text(m), datum=felder.get("datum") or dt.date.today().strftime("%d.%m.%Y"))

    # Ansichten projizieren; Schnitt A–A automatisch, wenn das Teil Bohrungen/Innenformen hat (Wellen werden
    # nach ISO 128-40 nicht längs geschnitten)
    halb = None
    if schnitt:
        halb = schneiden(form, "y", 0.0, behalte_plus=True)     # Betrachter steht bei −y: vordere Hälfte weg
    vorne = projizieren(halb if halb is not None else form, "vorne", verdeckt=not schnitt)
    oben = projizieren(form, "oben") if mit_draufsicht else {"sichtbar": [], "verdeckt": []}
    links = projizieren(form, "links") if mit_seite else {"sichtbar": [], "verdeckt": []}

    # Lage auf dem Blatt (Blatt-mm): Mittelpunkte
    bv = (gz * m, gx * m)          # Vorderansicht: Breite = z, Höhe = x
    bl = (gy * m, gx * m) if mit_seite else (-abstand, gx * m)   # Seitenansicht: Breite = y
    bo = (gz * m, gy * m) if mit_draufsicht else (0.0, -abstand)   # Draufsicht: Höhe = y
    gesamt_b = bv[0] + abstand + bl[0]
    gesamt_h = bv[1] + abstand + bo[1]
    links_x = RAND_LINKS + 25 + max(0.0, (nutz_b - gesamt_b) / 2)
    oben_y = H - RAND - 22 - max(0.0, (nutz_h - gesamt_h) / 3)
    mv = (links_x + bv[0] / 2, oben_y - bv[1] / 2)
    ml = (links_x + bv[0] + abstand + bl[0] / 2, mv[1])
    mo = (mv[0], oben_y - bv[1] - abstand - bo[1] / 2)

    def setzen(proj, mitte, ansicht, grenze_teil):
        cx, cy = (grenze_teil[0] + grenze_teil[2]) / 2, (grenze_teil[1] + grenze_teil[3]) / 2
        for art in ("verdeckt", "sichtbar"):
            for pl in proj[art]:
                for a, b in zip(pl, pl[1:]):
                    z.linie(mitte[0] + (a[0] - cx) * m, mitte[1] + (a[1] - cy) * m,
                            mitte[0] + (b[0] - cx) * m, mitte[1] + (b[1] - cy) * m, art=art)

        def nach_blatt(px, py):
            return mitte[0] + (px - cx) * m, mitte[1] + (py - cy) * m
        return nach_blatt

    # Teilgrenzen je Ansicht (aus der Hüllbox, damit Halbschnitt und Ansicht dieselbe Mitte haben)
    def box(ansicht):
        ecken = [(x, y, zz) for x in (e.minimum[0], e.maximum[0]) for y in (e.minimum[1], e.maximum[1])
                 for zz in (e.minimum[2], e.maximum[2])]
        pts = [_blattlage(p, ansicht) for p in ecken]
        return min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts)

    gv, gl, go = box("vorne"), box("links"), box("oben")
    nb_v = setzen(vorne, mv, "vorne", gv)
    nb_l = setzen(links, ml, "links", gl)
    nb_o = setzen(oben, mo, "oben", go)

    # Schnittflächen schraffieren, Schnittverlauf in der Seitenansicht
    if halb is not None:
        tol = max(gx, gy, gz) / 400
        # je Körper eigene Schraffur (Richtung/Abstand wechseln), damit Nachbarteile unterscheidbar sind
        from OCP.TopAbs import TopAbs_SOLID
        koerper = []
        ex = TopExp_Explorer(halb, TopAbs_SOLID)
        while ex.More():
            koerper.append(ex.Current())
            ex.Next()
        grund = max(2.0, min(4.0, 0.03 * max(bv)))
        for i, k in enumerate(koerper or [halb]):
            polys = [[nb_v(*p) for p in poly] for poly in _schnittflaechen(k, 0.0, "vorne", tol)]
            _schraffur(z, polys, abstand=grund * (1, 1, 0.7)[i % 3], winkel=(45, 135, 45)[i % 3])
        y_oben, y_unten = ml[1] + bl[1] / 2 + 6, ml[1] - bl[1] / 2 - 6
        x_s = nb_l(0.0, 0.0)[0]
        z.linie(x_s, y_oben, x_s, y_oben - 5, art="schnittlinie")
        z.linie(x_s, y_unten, x_s, y_unten + 5, art="schnittlinie")
        for y_p, pf in ((y_oben, 1), (y_unten, -1)):
            z.linie(x_s, y_p, x_s - 6, y_p, art="duenn")     # Blickrichtung nach links (zur Vorderansicht)
            _pfeil(z, x_s - 6, y_p, (-1, 0))
            z.text(x_s - 9, y_p + 1.2 * pf - (1.5 if pf < 0 else 0), "A", 5.0, "mitte")
        z.text(mv[0] - bv[0] / 2, mv[1] + bv[1] / 2 + (30 if positionen else 14), "A–A", 5.0, "links")

    # Mittellinien der Rotationsachse(n) entlang z
    hat_achse = any(abs(abs(c.achse[2]) - 1) < 1e-6 and math.hypot(c.ort[0], c.ort[1]) < 1e-3 for c in zyl)
    if hat_achse:
        x0, y0 = nb_v(gv[0], 0.0)
        x1, _ = nb_v(gv[2], 0.0)
        z.linie(x0 - 4, y0, x1 + 4, y0, art="mitte")
        if mit_draufsicht:
            x0, y0 = nb_o(go[0], 0.0)
            x1, _ = nb_o(go[2], 0.0)
            z.linie(x0 - 4, y0, x1 + 4, y0, art="mitte")
        if mit_seite:
            cx, cy = nb_l(0.0, 0.0)
            r = max(bl) / 2 + 4
            z.linie(cx - r, cy, cx + r, cy, art="mitte")
            z.linie(cx, cy - r, cx, cy + r, art="mitte")

    # ---- Bemaßung
    # Gesamtlänge unter der Vorderansicht, Gesamthöhe links daneben
    xa, yu = nb_v(gv[0], gv[1])
    xb, yo = nb_v(gv[2], gv[3])
    mass_waagerecht(z, xa, xb, yu, yu, yu - 10, formatiere(gz))
    # Durchmesser auf der Achse (Absätze) in der Vorderansicht, sonst Gesamthöhe
    laengste = {}
    for c in auf_achse:          # je Durchmesser der längste Absatz (dort ist Platz für das Maß)
        k = (round(c.radius * 2, 3), c.innen)
        if k not in laengste or c.bis - c.von > laengste[k].bis - laengste[k].von:
            laengste[k] = c
    aussen = sorted(laengste.values(), key=lambda c: -c.radius)
    if stueckliste:      # Baugruppe: nur Hauptmaße, dafür Positionsnummern
        aussen = []
        mass_senkrecht(z, yu, yo, xa, xa, xa - 10, formatiere(gx))
        if positionen:
            _positionsnummern(z, positionen, M, nb_v, gv, m)
    if aussen:
        aussen_links = 0
        for c in aussen[:7]:
            mitte_z = (c.von + c.bis) / 2 * (1 if c.achse[2] > 0 else -1)
            if c.innen:
                mitte_z = c.von * (1 if c.achse[2] > 0 else -1) + 6 / m
            x, y0 = nb_v(mitte_z, -c.radius)
            _, y1 = nb_v(mitte_z, c.radius)
            text = _durchmesser_text(2 * c.radius, toleranzen)
            if (c.bis - c.von) * m < 14:
                # zu schmal für ein Maß im Teil: links neben der Ansicht mit Hilfslinien
                x_kante = nb_v(gv[0], 0)[0]
                x_m = x_kante - 10 - 9 * aussen_links
                aussen_links += 1
                mass_senkrecht(z, y0, y1, nb_v(min(c.von, c.bis) * (1 if c.achse[2] > 0 else -1), 0)[0],
                               nb_v(min(c.von, c.bis) * (1 if c.achse[2] > 0 else -1), 0)[0], x_m, text)
                continue
            # Durchmessermaß im Teil (senkrechte Maßlinie mit Text)
            z.linie(x, y0, x, y1, art="duenn")
            _pfeil(z, x, y0, (0, -1))
            _pfeil(z, x, y1, (0, 1))
            z.text(x - 1.2, (y0 + y1) / 2 + (6 if c.innen else 0), text, 3.5, "mitte", drehung=90)
        # Absatzmaße: Kettenmaße der Zylinderlängen über der Ansicht
        stufen = sorted(set(ebenen_quer_zur_achse(form)) | {round(gv[0], 3), round(gv[2], 3)})
        stufen = [s for s in stufen if gv[0] - 1e-6 <= s <= gv[2] + 1e-6]
        # Fasen (< 2,5 mm) nicht als eigene Absätze bemaßen; die Enden bleiben
        zusammen = []
        for s_ in stufen:
            if zusammen and s_ - zusammen[-1] < 2.5:
                if s_ == stufen[-1]:
                    zusammen[-1] = s_
                continue
            zusammen.append(s_)
        stufen = zusammen
        if 2 < len(stufen) <= 9:
            y_k = nb_v(0, gv[3])[1]
            for a, b in zip(stufen, stufen[1:]):
                xa2, _ = nb_v(a, 0)
                xb2, _ = nb_v(b, 0)
                mass_waagerecht(z, xa2, xb2, y_k, y_k, y_k + 9, formatiere(b - a))
    elif not stueckliste:
        mass_senkrecht(z, yu, yo, xa, xa, xa - 10, formatiere(gx))
    # Seitenansicht: Breite unten
    xa, yu = nb_l(gl[0], gl[1])
    xb, _ = nb_l(gl[2], gl[1])
    if mit_seite and not aussen and not (stueckliste and abs(gx - gy) < 1e-3):
        mass_waagerecht(z, xa, xb, yu, yu, yu - (16 if halb is not None else 10), formatiere(gy))
    # Bohrungsbilder parallel zur Achse (Lochkreise) in der Seitenansicht beschriften
    loecher = {}
    for c in zyl:
        r_ort = math.hypot(c.ort[0], c.ort[1])
        if not stueckliste and c.innen and abs(abs(c.achse[2]) - 1) < 1e-6 and r_ort > 1e-3:
            loecher.setdefault((round(2 * c.radius, 2), round(2 * r_ort, 2)), set()).add(
                (round(c.ort[0], 2), round(c.ort[1], 2)))
    zeile = 0
    for (d_l, d_lk), orte in sorted(loecher.items()):
        z.text(ml[0], ml[1] - bl[1] / 2 - 18 - 6 * zeile,
               f"{len(orte)}× Ø{formatiere(d_l)} auf Lochkreis Ø{formatiere(d_lk)}", 3.5, "mitte")
        # Lochkreis als Mittellinie
        cx, cy = nb_l(0.0, 0.0)
        r = d_lk / 2 * m
        pts = [(cx + r * math.cos(t * math.pi / 36), cy + r * math.sin(t * math.pi / 36)) for t in range(73)]
        for a, b in zip(pts, pts[1:]):
            z.linie(*a, *b, art="mitte")
        zeile += 1

    # Ansichten benennen (nur wenn nicht selbsterklärend) – Schriftfeld, Hinweise
    titel_x, titel_y = _rahmen_und_schriftfeld(z, felder)
    if stueckliste:
        _stueckliste_auf_blatt(z, stueckliste, titel_x, titel_y)
    tol_text = ", ".join(f"Ø{k.lstrip('Ø')} {v}" for k, v in toleranzen.items())
    if tol_text:
        z.text(RAND_LINKS + 4, RAND + 4, f"Passmaße: {tol_text}", 3.0, "links")
    z.hinweise.append("Bemaßung automatisch: Gesamtmaße, Durchmesser, Absätze, Lochkreise. Funktionsmaße prüfen.")
    return z


def _positionsnummern(z: Zeichnung, positionen: list, M: np.ndarray, nb_v, gv, m: float):
    """Positionsnummern über der Vorderansicht, Hinweislinie mit Punkt zum Teil (ISO 6433)."""
    y_kreis = nb_v(0, gv[3])[1] + 16
    punkte = []
    for pos, p in positionen:
        q = (M @ np.array([*p, 1.0]))[:3]
        punkte.append((pos, nb_v(*_blattlage(q, "vorne"))))
    punkte.sort(key=lambda t: t[1][0])
    letztes_x = -1e9
    for pos, (px, py) in punkte:
        kx = max(px, letztes_x + 11)
        letztes_x = kx
        z.linie(px, py, kx, y_kreis - 4, art="duenn")
        z.elemente.append(Polygon([(px + 0.6 * math.cos(t * math.pi / 4), py + 0.6 * math.sin(t * math.pi / 4))
                                   for t in range(8)]))
        kreis = [(kx + 4 * math.cos(t * math.pi / 16), y_kreis + 4 * math.sin(t * math.pi / 16)) for t in range(33)]
        for a, b in zip(kreis, kreis[1:]):
            z.linie(*a, *b, art="duenn")
        z.text(kx, y_kreis - 1.7, str(pos), 4.5, "mitte")


def _stueckliste_auf_blatt(z: Zeichnung, stueckliste: list, x0: float, y0: float):
    W = BLATT[0] - RAND
    spalten = [("Pos", 10), ("Menge", 13), ("Benennung", 72), ("Sachnr. / Norm", 55), ("Masse kg", 30)]
    zeilen = [(str(p.pos), str(p.menge), p.benennung[:40], p.sachnummer[:30],
               formatiere(p.gesamtmasse) if p.gesamtmasse is not None else "–") for p in stueckliste[:14]]
    h = 6.0
    y = y0
    for werte in reversed(zeilen):
        x = x0
        for (titel, b), wert in zip(spalten, werte):
            z.text(x + 1.2, y + 1.8, wert, 2.8, "links")
            x += b
        z.linie(x0, y + h, W, y + h, art="duenn")
        y += h
    x = x0
    for titel, b in spalten:
        z.text(x + 1.2, y + 1.8, titel, 2.8, "links")
        z.linie(x, y0, x, y + h, art="duenn")
        x += b
    z.linie(x0, y + h, W, y + h, art="rahmen")
    z.linie(x0, y0, x0, y + h, art="rahmen")


# ---------------------------------------------------------------- Ausgabe
def als_pdf(z: Zeichnung, ziel: str | Path) -> Path:
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas
    from ..pdf import _schrift
    schrift, _ = _schrift()
    ziel = Path(ziel)
    c = canvas.Canvas(str(ziel), pagesize=(z.breite * mm, z.hoehe * mm))
    c.setTitle(z.titel or "Zeichnung")
    for el in z.elemente:
        if isinstance(el, Linie):
            breite, muster = LINIEN[el.art]
            c.setLineWidth(breite * mm)
            c.setDash([v * mm for v in muster] if muster else [])
            c.line(el.x0 * mm, el.y0 * mm, el.x1 * mm, el.y1 * mm)
        elif isinstance(el, Polygon):
            p = c.beginPath()
            p.moveTo(el.punkte[0][0] * mm, el.punkte[0][1] * mm)
            for x, y in el.punkte[1:]:
                p.lineTo(x * mm, y * mm)
            p.close()
            c.setDash([])
            c.drawPath(p, stroke=0, fill=1 if el.gefuellt else 0)
        elif isinstance(el, Text):
            c.saveState()
            c.translate(el.x * mm, el.y * mm)
            c.rotate(el.drehung)
            c.setFont(schrift, el.hoehe * mm * 1.25)
            if el.ausrichtung == "mitte":
                c.drawCentredString(0, 0, el.text)
            elif el.ausrichtung == "rechts":
                c.drawRightString(0, 0, el.text)
            else:
                c.drawString(0, 0, el.text)
            c.restoreState()
    c.showPage()
    c.save()
    return ziel


def als_dxf(z: Zeichnung, ziel: str | Path) -> Path:
    """DXF R12 (ASCII) mit Layern je Linienart – liest jedes CAD-Programm. Einheit mm, Maßstab 1:1 des Blattes."""
    ziel = Path(ziel)
    zeilen = ["0", "SECTION", "2", "HEADER", "9", "$INSUNITS", "70", "4", "0", "ENDSEC",
              "0", "SECTION", "2", "TABLES", "0", "TABLE", "2", "LTYPE", "70", "3"]
    for name, muster in (("CONTINUOUS", []), ("DASHED", [3.0, -1.5]), ("CENTER", [12.0, -2.0, 1.0, -2.0])):
        zeilen += ["0", "LTYPE", "2", name, "70", "0", "3", name, "72", "65", "73", str(len(muster)),
                   "40", f"{sum(abs(v) for v in muster):.3f}"]
        for v in muster:
            zeilen += ["49", f"{v:.3f}"]
    zeilen += ["0", "ENDTAB", "0", "TABLE", "2", "LAYER", "70", str(len(LINIEN))]
    farben = {"sichtbar": 7, "verdeckt": 8, "mitte": 1, "duenn": 3, "rahmen": 7, "schraffur": 8, "schnittlinie": 1}
    typen = {"verdeckt": "DASHED", "mitte": "CENTER"}
    for art in LINIEN:
        zeilen += ["0", "LAYER", "2", art.upper(), "70", "0", "62", str(farben[art]), "6", typen.get(art, "CONTINUOUS")]
    zeilen += ["0", "ENDTAB", "0", "ENDSEC", "0", "SECTION", "2", "ENTITIES"]
    for el in z.elemente:
        if isinstance(el, Linie):
            zeilen += ["0", "LINE", "8", el.art.upper(), "10", f"{el.x0:.4f}", "20", f"{el.y0:.4f}", "30", "0",
                       "11", f"{el.x1:.4f}", "21", f"{el.y1:.4f}", "31", "0"]
        elif isinstance(el, Polygon):
            pts = el.punkte
            zeilen += ["0", "SOLID", "8", "DUENN"]
            p4 = pts + [pts[-1]] * (4 - len(pts)) if len(pts) < 4 else pts[:4]
            for i, (x, y) in enumerate(p4):
                zeilen += [str(10 + i), f"{x:.4f}", str(20 + i), f"{y:.4f}", str(30 + i), "0"]
        elif isinstance(el, Text):
            h = {"links": "0", "mitte": "1", "rechts": "2"}[el.ausrichtung]
            zeilen += ["0", "TEXT", "8", "DUENN", "10", f"{el.x:.4f}", "20", f"{el.y:.4f}", "30", "0",
                       "40", f"{el.hoehe:.2f}", "1", el.text, "50", f"{el.drehung:.1f}", "72", h,
                       "11", f"{el.x:.4f}", "21", f"{el.y:.4f}", "31", "0"]
    zeilen += ["0", "ENDSEC", "0", "EOF"]
    ziel.write_text("\n".join(zeilen) + "\n", encoding="cp1252", errors="replace")
    return ziel
