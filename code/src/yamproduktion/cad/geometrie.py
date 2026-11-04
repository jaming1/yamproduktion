"""Dünne Schicht über dem Geometriekern Open CASCADE (OCP).

Alle Maße in mm. Die z-Achse ist die Drehachse rotationssymmetrischer Teile.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common, BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon, BRepBuilderAPI_Transform
from OCP.BRepFilletAPI import BRepFilletAPI_MakeChamfer
from OCP.BRepGProp import BRepGProp
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakePrism, BRepPrimAPI_MakeRevol
from OCP.Bnd import Bnd_Box
from OCP.GCPnts import GCPnts_QuasiUniformDeflection
from OCP.GProp import GProp_GProps
from OCP.IFSelect import IFSelect_RetDone
from OCP.Interface import Interface_Static
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Reader, STEPControl_Writer
from OCP.StlAPI import StlAPI_Writer
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_REVERSED
from OCP.TopExp import TopExp_Explorer
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS, TopoDS_Shape
from OCP.gp import gp_Ax1, gp_Ax2, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec


class GeometrieFehler(ValueError):
    pass


# OCP 7.7 nennt statische Methoden mit „_s“, ab 7.8 ohne – beide Fassungen unterstützen
_kante = getattr(TopoDS, "Edge", None) or TopoDS.Edge_s
_flaeche = getattr(TopoDS, "Face", None) or TopoDS.Face_s


# ---------------------------------------------------------------- Grundkörper
def zylinder(d: float, laenge: float, z0: float = 0.0, x: float = 0.0, y: float = 0.0) -> TopoDS_Shape:
    """Zylinder mit Durchmesser d entlang +z ab z0."""
    if d <= 0 or laenge <= 0:
        raise GeometrieFehler(f"Zylinder braucht positive Maße (d = {d}, l = {laenge}).")
    achse = gp_Ax2(gp_Pnt(x, y, z0), gp_Dir(0, 0, 1))
    return BRepPrimAPI_MakeCylinder(achse, d / 2, laenge).Shape()


def quader(x0: float, y0: float, z0: float, dx: float, dy: float, dz: float) -> TopoDS_Shape:
    return BRepPrimAPI_MakeBox(gp_Pnt(x0, y0, z0), dx, dy, dz).Shape()


def vereinigen(a: TopoDS_Shape, *weitere: TopoDS_Shape) -> TopoDS_Shape:
    for b in weitere:
        op = BRepAlgoAPI_Fuse(a, b)
        op.SimplifyResult()
        a = op.Shape()
    return a


def abziehen(a: TopoDS_Shape, *weitere: TopoDS_Shape) -> TopoDS_Shape:
    for b in weitere:
        a = BRepAlgoAPI_Cut(a, b).Shape()
    return a


def schnittmenge(a: TopoDS_Shape, b: TopoDS_Shape) -> TopoDS_Shape:
    return BRepAlgoAPI_Common(a, b).Shape()


def drehen_um_z(form: TopoDS_Shape, winkel_grad: float) -> TopoDS_Shape:
    t = gp_Trsf()
    t.SetRotation(gp_Ax2().Axis(), math.radians(winkel_grad))
    return BRepBuilderAPI_Transform(form, t, True).Shape()


def profil_extrudieren(punkte: list[tuple[float, float]], hoehe: float, z0: float = 0.0) -> TopoDS_Shape:
    """Geschlossenes Polygon in der xy-Ebene um `hoehe` in +z extrudieren."""
    poly = BRepBuilderAPI_MakePolygon()
    for x, y in punkte:
        poly.Add(gp_Pnt(x, y, z0))
    poly.Close()
    flaeche = BRepBuilderAPI_MakeFace(poly.Wire(), True).Face()
    return BRepPrimAPI_MakePrism(flaeche, gp_Vec(0, 0, hoehe)).Shape()


def abgesetzt(abschnitte: list[tuple[float, float]], fase: float = 0.0) -> TopoDS_Shape:
    """Rotationskörper aus Abschnitten (Durchmesser, Länge) entlang +z ab z = 0.
    Fasen nur an den außen liegenden (konvexen) Kanten jedes Absatzes und an den Enden."""
    if not abschnitte or any(d <= 0 or l <= 0 for d, l in abschnitte):
        raise GeometrieFehler("Jeder Absatz braucht positiven Durchmesser und Länge.")
    radien = [d / 2 for d, _ in abschnitte]
    pkt = [(0.0, 0.0)]
    z = 0.0
    for i, (r, (_, l)) in enumerate(zip(radien, abschnitte)):
        vor = radien[i - 1] if i else 0.0
        nach = radien[i + 1] if i + 1 < len(radien) else 0.0
        z1 = z + l
        if r > vor:
            c = min(fase, 0.9 * (r - vor), 0.45 * l)
            pkt += [(r - c, z), (r, z + c)] if c > 0 else [(r, z)]
        else:
            pkt.append((r, z))
        if r > nach:
            c = min(fase, 0.9 * (r - nach), 0.45 * l)
            pkt += [(r, z1 - c), (r - c, z1)] if c > 0 else [(r, z1)]
        else:
            pkt.append((r, z1))
        z = z1
    pkt.append((0.0, z))
    poly = BRepBuilderAPI_MakePolygon()
    vorher = None
    for r, zz in pkt:
        if vorher and abs(vorher[0] - r) < 1e-9 and abs(vorher[1] - zz) < 1e-9:
            continue
        poly.Add(gp_Pnt(r, 0, zz))
        vorher = (r, zz)
    poly.Close()
    flaeche = BRepBuilderAPI_MakeFace(poly.Wire(), True).Face()
    return BRepPrimAPI_MakeRevol(flaeche, gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), 2 * math.pi).Shape()


def kreiskanten_fasen(form: TopoDS_Shape, fase: float, nur_aussen_d: float | None = None) -> TopoDS_Shape:
    """Fase an allen Kreiskanten (optional nur an Kanten mit Durchmesser ≥ nur_aussen_d)."""
    if fase <= 0:
        return form
    op = BRepFilletAPI_MakeChamfer(form)
    exp = TopExp_Explorer(form, TopAbs_EDGE)
    anzahl = 0
    while exp.More():
        kante = _kante(exp.Current())
        kurve = BRepAdaptor_Curve(kante)
        if kurve.GetType().name == "GeomAbs_Circle" and kurve.IsClosed():
            r = kurve.Circle().Radius()
            if nur_aussen_d is None or 2 * r >= nur_aussen_d - 1e-6:
                op.Add(fase, kante)
                anzahl += 1
        exp.Next()
    if not anzahl:
        return form
    try:
        op.Build()
        return op.Shape() if op.IsDone() else form
    except Exception:       # Kern meldet z. B. zu große Fase – dann ohne Fase weiter
        return form


# ---------------------------------------------------------------- Eigenschaften
@dataclass
class Eigenschaften:
    volumen: float            # mm³
    flaeche: float            # mm²
    schwerpunkt: tuple[float, float, float]
    groesse: tuple[float, float, float]     # Abmessungen der Hüllbox in mm
    minimum: tuple[float, float, float]
    maximum: tuple[float, float, float]

    def masse(self, dichte_kg_m3: float) -> float:
        return self.volumen * 1e-9 * dichte_kg_m3


def eigenschaften(form: TopoDS_Shape) -> Eigenschaften:
    p = GProp_GProps()
    BRepGProp.VolumeProperties_s(form, p)
    f = GProp_GProps()
    BRepGProp.SurfaceProperties_s(form, f)
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(form, box, False, False)
    lo, hi = box.CornerMin(), box.CornerMax()
    x0, y0, z0, x1, y1, z1 = lo.X(), lo.Y(), lo.Z(), hi.X(), hi.Y(), hi.Z()
    s = p.CentreOfMass()
    return Eigenschaften(p.Mass(), f.Mass(), (s.X(), s.Y(), s.Z()), (x1 - x0, y1 - y0, z1 - z0),
                         (x0, y0, z0), (x1, y1, z1))


def ist_gueltig(form: TopoDS_Shape) -> bool:
    from OCP.BRepCheck import BRepCheck_Analyzer
    return not form.IsNull() and BRepCheck_Analyzer(form).IsValid()


# ---------------------------------------------------------------- Schnitt
def schneiden(form: TopoDS_Shape, achse: str = "x", position: float = 0.0, behalte_plus: bool = True) -> TopoDS_Shape:
    """Halbschnitt: entfernt alles auf einer Seite der Ebene achse = position."""
    e = eigenschaften(form)
    gross = 4 * max(e.groesse) + 100
    lo = [m - gross for m in e.minimum]
    ausdehnung = [2 * gross + g for g in e.groesse]
    i = "xyz".index(achse)
    if behalte_plus:          # Halbraum unterhalb der Ebene entfernen
        ausdehnung[i] = position - lo[i]
    else:
        lo[i] = position
        ausdehnung[i] = e.maximum[i] + gross - position
    if ausdehnung[i] <= 0:
        return form
    return abziehen(form, quader(*lo, *ausdehnung))


# ---------------------------------------------------------------- Netz für die Anzeige
@dataclass
class Netz:
    punkte: np.ndarray        # (n, 3)
    dreiecke: np.ndarray      # (m, 3) Indizes
    normalen: np.ndarray      # (m, 3) Flächennormalen je Dreieck
    flaeche_nr: np.ndarray    # (m,) Nummer der B-Rep-Fläche je Dreieck
    kanten: list[np.ndarray]  # Polylinien der Modellkanten


def netz(form: TopoDS_Shape, toleranz: float | None = None) -> Netz:
    if toleranz is None:
        toleranz = max(0.05, max(eigenschaften(form).groesse) / 400)
    BRepMesh_IncrementalMesh(form, toleranz, False, 0.35, True)
    punkte, dreiecke, flaeche_nr = [], [], []
    exp = TopExp_Explorer(form, TopAbs_FACE)
    nr = 0
    while exp.More():
        flaeche = _flaeche(exp.Current())
        ort = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(flaeche, ort)
        if tri is not None:
            trsf = ort.Transformation()
            basis = len(punkte)
            for i in range(1, tri.NbNodes() + 1):
                p = tri.Node(i).Transformed(trsf)
                punkte.append((p.X(), p.Y(), p.Z()))
            umgedreht = flaeche.Orientation() == TopAbs_REVERSED
            for i in range(1, tri.NbTriangles() + 1):
                a, b, c = tri.Triangle(i).Get()
                if umgedreht:
                    b, c = c, b
                dreiecke.append((basis + a - 1, basis + b - 1, basis + c - 1))
                flaeche_nr.append(nr)
        nr += 1
        exp.Next()
    if not dreiecke:
        raise GeometrieFehler("Das Teil hat keine darstellbare Oberfläche.")
    P = np.asarray(punkte, dtype=float)
    T = np.asarray(dreiecke, dtype=np.int64)
    n = np.cross(P[T[:, 1]] - P[T[:, 0]], P[T[:, 2]] - P[T[:, 0]])
    laenge = np.linalg.norm(n, axis=1)
    laenge[laenge == 0] = 1
    n = n / laenge[:, None]
    kanten = []
    exp = TopExp_Explorer(form, TopAbs_EDGE)
    while exp.More():
        kante = _kante(exp.Current())
        try:
            kurve = BRepAdaptor_Curve(kante)
            teil = GCPnts_QuasiUniformDeflection(kurve, toleranz)
            if teil.IsDone() and teil.NbPoints() >= 2:
                kanten.append(np.array([(q.X(), q.Y(), q.Z()) for q in
                                        (teil.Value(i) for i in range(1, teil.NbPoints() + 1))]))
        except Exception:
            pass
        exp.Next()
    return Netz(P, T, n, np.asarray(flaeche_nr), kanten)


# ---------------------------------------------------------------- Austausch
def step_schreiben(form: TopoDS_Shape, ziel: str | Path, name: str = "Teil") -> Path:
    ziel = Path(ziel)
    w = STEPControl_Writer()
    Interface_Static.SetCVal_s("write.step.schema", "AP214IS")
    Interface_Static.SetCVal_s("write.step.product.name", name)
    if w.Transfer(form, STEPControl_AsIs) != IFSelect_RetDone or w.Write(str(ziel)) != IFSelect_RetDone:
        raise GeometrieFehler(f"STEP-Datei {ziel.name} konnte nicht geschrieben werden.")
    return ziel


def step_lesen(quelle: str | Path) -> TopoDS_Shape:
    r = STEPControl_Reader()
    if r.ReadFile(str(quelle)) != IFSelect_RetDone:
        raise GeometrieFehler(f"STEP-Datei {Path(quelle).name} konnte nicht gelesen werden.")
    r.TransferRoots()
    return r.OneShape()


def stl_schreiben(form: TopoDS_Shape, ziel: str | Path, toleranz: float = 0.05) -> Path:
    ziel = Path(ziel)
    BRepMesh_IncrementalMesh(form, toleranz, False, 0.2, True)
    w = StlAPI_Writer()
    w.ASCIIMode = False
    if not w.Write(form, str(ziel)):
        raise GeometrieFehler(f"STL-Datei {ziel.name} konnte nicht geschrieben werden.")
    return ziel
