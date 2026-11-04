"""Parametrische Vorlagen-Teile (Lastenheft M29, S6): Welle, Flansch, Nabe, Zahnrad.

Jede Vorlage beschreibt ihre Parameter wie eine Berechnung (FELDER, BERECHNUNGS_QUELLEN). Dadurch
übernimmt ein Teil seine Maße direkt aus den gespeicherten Berechnungen und wird bei deren Änderung
„neu prüfen“ (Rückverfolgung wie bei Berechnungen).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

from .. import werkstoffe
from ..berechnungen.basis import Feld
from ..berechnungen.welle_nabe import passfeder
from .geometrie import GeometrieFehler, abgesetzt, abziehen, profil_extrudieren, quader, vereinigen, zylinder

WERKSTOFFE = werkstoffe.auswahl()

# Durchgangslöcher für Schrauben, Reihe „mittel“ (ISO 273) – Norm, ungeprüft
DURCHGANGSLOCH_MITTEL = {6: 6.6, 8: 9.0, 10: 11.0, 12: 13.5, 16: 17.5, 20: 22.0, 24: 26.0, 30: 33.0, 36: 39.0}


def durchgangsloch(d_schraube: float) -> float:
    d = int(round(d_schraube))
    if d in DURCHGANGSLOCH_MITTEL:
        return DURCHGANGSLOCH_MITTEL[d]
    return round(d_schraube * 1.1, 1)


def _radialer_zylinder(d: float, y0: float, hoehe: float, z: float, x: float = 0.0):
    """Zylinder mit Achse in +y (für Passfedernut Form A)."""
    return BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(x, y0, z), gp_Dir(0, 1, 0)), d / 2, hoehe).Shape()


def passfedernut(d_welle: float, l_nut: float, z_mitte: float, aussen: bool = True):
    """Nut Form A (rund) nach DIN 6885: Breite b, Tiefe t1 in der Welle; bei aussen=False Nabennut (t2 ≈ h − t1)."""
    b, h, t1 = passfeder(d_welle)
    tiefe = t1 if aussen else (h - t1) + 0.4
    if l_nut < b:
        raise GeometrieFehler(f"Die Passfeder ({l_nut:g} mm) ist kürzer als breit ({b:g} mm).")
    r = d_welle / 2
    if aussen:
        y0, hoehe = r - tiefe, tiefe + 2
    else:
        y0, hoehe = r - 1, tiefe + 1
    gerade = l_nut - b
    teile = [_radialer_zylinder(b, y0, hoehe, z_mitte - gerade / 2), _radialer_zylinder(b, y0, hoehe, z_mitte + gerade / 2)]
    if gerade > 0:
        teile.append(quader(-b / 2, y0, z_mitte - gerade / 2, b, hoehe, gerade))
    return vereinigen(*teile)


@dataclass
class Vorlage:
    TYP: str
    TITEL: str
    KURZ: str
    BESCHREIBUNG: str
    FELDER: list
    Eingaben: type
    erzeuge: object
    BERECHNUNGS_QUELLEN: dict
    FELD_SUCHBEGRIFFE: dict = field(default_factory=dict)

    @property
    def FELD_EINHEITEN(self) -> dict:      # noqa: N802
        return {x.attr: x.einheit for x in self.FELDER if not x.auswahl}

    @property
    def FELD_NAMEN(self) -> dict:          # noqa: N802
        return {x.attr: x.name for x in self.FELDER}


# ================================================================ Welle
@dataclass
class WelleParameter:
    d_lager: float = 80.0
    a_mm: float = 300.0
    l_mm: float = 400.0
    b_lager: float = 26.0
    d_nabe: float = 75.0
    l_nabe: float = 100.0
    l_pf: float = 90.0
    d_mitte: float = 90.0
    d_ende: float = 70.0
    l_ende: float = 80.0
    fase: float = 1.5
    werkstoff: str = werkstoffe.bezeichnung(werkstoffe.werkstoff("42CrMo4", "40–100"))


def erzeuge_welle(p: WelleParameter):
    """Abgesetzte Rotorwelle; z = 0 am rotorseitigen Ende.
    Nabensitz – Lager B (rotorseitig, Abstand a von der Nabenmitte) – Bund – Lager A (Abstand l) – Generatorzapfen."""
    if p.d_nabe > p.d_lager or p.d_ende > p.d_lager:
        raise GeometrieFehler("Nabensitz und Generatorzapfen dürfen nicht dicker als der Lagersitz sein (Montage über das Wellenende).")
    if p.d_mitte <= p.d_lager:
        raise GeometrieFehler("Der Bund zwischen den Lagern muss dicker als der Lagersitz sein (Anlage für die Lager).")
    z_b = p.l_nabe / 2 + p.a_mm
    z_a = z_b + p.l_mm
    if z_b - p.b_lager / 2 <= p.l_nabe:
        raise GeometrieFehler("Der Überhang a ist zu kurz: Lager B überdeckt den Nabensitz.")
    if p.l_mm <= p.b_lager:
        raise GeometrieFehler("Der Lagerabstand ist kleiner als die Lagerbreite.")
    abschnitte = [
        (p.d_nabe, p.l_nabe),
        (p.d_lager, z_b + p.b_lager / 2 - p.l_nabe),
        (p.d_mitte, p.l_mm - p.b_lager),
        (p.d_lager, p.b_lager),
        (p.d_ende, p.l_ende),
    ]
    form = abgesetzt(abschnitte, p.fase)
    if p.l_pf > 0:
        if p.l_pf > p.l_nabe - 2:
            raise GeometrieFehler("Die Passfeder ist länger als der Nabensitz.")
        form = abziehen(form, passfedernut(p.d_nabe, p.l_pf, p.l_nabe / 2))
    return form


WELLE = Vorlage(
    TYP="welle", TITEL="Rotorwelle (abgesetzt)", KURZ="Welle",
    BESCHREIBUNG="Abgesetzte Welle mit Nabensitz und Passfedernut, zwei Lagersitzen, Bund und Generatorzapfen. "
                 "Durchmesser, Überhang und Lagerabstand kommen aus der Wellenberechnung.",
    FELDER=[
        Feld("d_lager", "Lagersitz-Durchmesser", "mm", 10, 400, 1, 1, "aus der Wellenberechnung (Nachweisquerschnitt)"),
        Feld("a_mm", "Überhang Nabenmitte → Lager B", "mm", 20, 3000, 5, 1, "aus der Wellenberechnung"),
        Feld("l_mm", "Lagerabstand", "mm", 20, 3000, 5, 1, "aus der Wellenberechnung"),
        Feld("b_lager", "Lagerbreite", "mm", 5, 200, 1, 1, "aus dem Lagerkatalog"),
        Feld("d_nabe", "Nabensitz-Durchmesser", "mm", 10, 400, 1, 1, "aus der Passfederberechnung"),
        Feld("l_nabe", "Nabensitz-Länge", "mm", 10, 1000, 1, 1, ""),
        Feld("l_pf", "Passfederlänge (0 = ohne)", "mm", 0, 1000, 1, 1, "aus der Passfederberechnung"),
        Feld("d_mitte", "Bund-Durchmesser", "mm", 10, 500, 1, 1, "Schulterhöhe nach Lagerkatalog"),
        Feld("d_ende", "Generatorzapfen-Durchmesser", "mm", 10, 400, 1, 1, ""),
        Feld("l_ende", "Generatorzapfen-Länge", "mm", 10, 1000, 1, 1, ""),
        Feld("fase", "Fase an den Absätzen", "mm", 0, 10, 0.5, 1, ""),
        Feld("werkstoff", "Werkstoff", "", auswahl=WERKSTOFFE),
    ],
    Eingaben=WelleParameter, erzeuge=erzeuge_welle,
    BERECHNUNGS_QUELLEN={"d_lager": ("welle", "d"), "a_mm": ("welle", "a"), "l_mm": ("welle", "l"),
                         "d_nabe": ("passfeder", "d"), "l_pf": ("passfeder", "l")},
)


# ================================================================ Flansch
@dataclass
class FlanschParameter:
    d_rohr: float = 406.4
    t_rohr: float = 10.0
    d_a: float = 560.0
    dicke: float = 30.0
    h_stutzen: float = 60.0
    d_l: float = 480.0
    n: float = 16
    d_schraube: float = 24.0
    werkstoff: str = werkstoffe.bezeichnung(werkstoffe.werkstoff("S355J2"))


def erzeuge_flansch(p: FlanschParameter):
    """Turmfußflansch: Ringplatte mit Lochkreis und angeschweißtem Rohrstutzen (Schweißnaht nicht modelliert)."""
    d_loch = durchgangsloch(p.d_schraube)
    d_i = p.d_rohr - 2 * p.t_rohr
    n = int(round(p.n))
    if d_i <= 0:
        raise GeometrieFehler("Die Wanddicke ist zu groß für den Rohrdurchmesser.")
    if p.d_l - d_loch < p.d_rohr + 2 * p.t_rohr:
        raise GeometrieFehler("Der Lochkreis liegt zu nah am Rohr – kein Platz für Schraubenkopf und Naht.")
    if p.d_a < p.d_l + 2 * d_loch:
        raise GeometrieFehler("Der Außendurchmesser ist zu klein: Randabstand der Löcher < 1·d_Loch.")
    if n < 3 or math.pi * p.d_l / n < 2.2 * d_loch:
        raise GeometrieFehler("Zu viele Löcher für den Lochkreis (Lochabstand < 2,2·d_Loch).")
    platte = abziehen(zylinder(p.d_a, p.dicke), zylinder(d_i, p.dicke + 2, -1))
    form = platte
    if p.h_stutzen > 0:
        stutzen = abziehen(zylinder(p.d_rohr, p.h_stutzen, p.dicke), zylinder(d_i, p.h_stutzen + 2, p.dicke - 1))
        form = vereinigen(platte, stutzen)
    loecher = [zylinder(d_loch, p.dicke + 2, -1, x=p.d_l / 2 * math.cos(2 * math.pi * k / n + math.pi / n),
                        y=p.d_l / 2 * math.sin(2 * math.pi * k / n + math.pi / n)) for k in range(n)]
    form = abziehen(form, vereinigen(*loecher))
    return form


FLANSCH = Vorlage(
    TYP="flansch", TITEL="Turmflansch mit Rohrstutzen", KURZ="Flansch",
    BESCHREIBUNG="Ringflansch mit Lochkreis und Rohrstutzen. Rohr, Lochkreis und Schraubenzahl kommen aus der "
                 "Turmberechnung, das Durchgangsloch aus der Schraubenberechnung (ISO 273, Reihe mittel).",
    FELDER=[
        Feld("d_rohr", "Rohraußendurchmesser", "mm", 20, 3000, 1, 1, "aus der Turmberechnung"),
        Feld("t_rohr", "Rohrwanddicke", "mm", 1, 100, 0.5, 1, "aus der Turmberechnung"),
        Feld("d_a", "Flansch-Außendurchmesser", "mm", 30, 4000, 1, 1, ""),
        Feld("dicke", "Flanschdicke", "mm", 3, 300, 1, 1, ""),
        Feld("h_stutzen", "Höhe Rohrstutzen (0 = ohne)", "mm", 0, 2000, 5, 1, ""),
        Feld("d_l", "Lochkreis", "mm", 30, 4000, 1, 1, "aus der Turmberechnung"),
        Feld("n", "Anzahl Schrauben", "", 3, 200, 1, 0, "aus der Turmberechnung"),
        Feld("d_schraube", "Schrauben-Nenndurchmesser", "mm", 6, 36, 1, 0, "aus der Schraubenberechnung"),
        Feld("werkstoff", "Werkstoff", "", auswahl=WERKSTOFFE),
    ],
    Eingaben=FlanschParameter, erzeuge=erzeuge_flansch,
    BERECHNUNGS_QUELLEN={"d_rohr": ("turm", "D"), "t_rohr": ("turm", "t"), "d_l": ("turm", "D_L"),
                         "n": ("turm", "n_S"), "d_schraube": ("schrauben", "d")},
)


# ================================================================ Nabe
@dataclass
class NabeParameter:
    d_f: float = 80.0
    d_a: float = 160.0
    l_f: float = 80.0
    mit_nut: str = "ja"
    d_scheibe: float = 360.0
    dicke_scheibe: float = 25.0
    d_lk: float = 300.0
    n_loecher: float = 12
    d_loch: float = 17.5
    werkstoff: str = werkstoffe.bezeichnung(werkstoffe.werkstoff("EN-GJS-400-15"))


def erzeuge_nabe(p: NabeParameter):
    """Rotornabe: Nabenkörper mit Bohrung (Pressverband bzw. Passfeder) und Blattanschlussscheibe vorn."""
    n = int(round(p.n_loecher))
    if p.d_a <= p.d_f + 10:
        raise GeometrieFehler("Die Nabe ist zu dünnwandig (D_A ≤ d_F + 10 mm).")
    if p.d_scheibe <= p.d_a or p.d_lk - p.d_loch <= p.d_a or p.d_lk + 2 * p.d_loch > p.d_scheibe:
        raise GeometrieFehler("Lochkreis und Scheibe passen nicht: D_A < Lochkreis − d_Loch und Lochkreis + 2·d_Loch ≤ Scheibe.")
    if p.dicke_scheibe >= p.l_f:
        raise GeometrieFehler("Die Scheibe ist dicker als die Nabe lang.")
    koerper = vereinigen(zylinder(p.d_a, p.l_f), zylinder(p.d_scheibe, p.dicke_scheibe))
    koerper = abziehen(koerper, zylinder(p.d_f, p.l_f + 2, -1))
    if p.mit_nut == "ja":
        koerper = abziehen(koerper, passfedernut(p.d_f, p.l_f + 4, p.l_f / 2, aussen=False))
    loecher = [zylinder(p.d_loch, p.dicke_scheibe + 2, -1, x=p.d_lk / 2 * math.cos(2 * math.pi * k / n),
                        y=p.d_lk / 2 * math.sin(2 * math.pi * k / n)) for k in range(n)]
    return abziehen(koerper, vereinigen(*loecher))


NABE = Vorlage(
    TYP="nabe", TITEL="Rotornabe mit Blattanschluss", KURZ="Nabe",
    BESCHREIBUNG="Nabenkörper mit Bohrung und durchgehender Passfedernut, vorn eine Scheibe mit Lochkreis für den "
                 "Blattanschluss. Bohrung, Außendurchmesser und Länge kommen aus der Pressverband-Berechnung.",
    FELDER=[
        Feld("d_f", "Bohrung (Fugendurchmesser)", "mm", 10, 500, 1, 1, "aus Pressverband"),
        Feld("d_a", "Nabenaußendurchmesser", "mm", 20, 1000, 1, 1, "aus Pressverband"),
        Feld("l_f", "Nabenlänge", "mm", 10, 1000, 1, 1, "aus Pressverband"),
        Feld("mit_nut", "Passfedernut", "", auswahl=("ja", "nein")),
        Feld("d_scheibe", "Durchmesser Blattscheibe", "mm", 30, 3000, 1, 1, ""),
        Feld("dicke_scheibe", "Dicke Blattscheibe", "mm", 3, 200, 1, 1, ""),
        Feld("d_lk", "Lochkreis Blattanschluss", "mm", 20, 3000, 1, 1, ""),
        Feld("n_loecher", "Anzahl Löcher", "", 3, 60, 1, 0, "z. B. 3 Blätter × 4"),
        Feld("d_loch", "Lochdurchmesser", "mm", 3, 60, 0.5, 1, "M16 mittel: 17,5"),
        Feld("werkstoff", "Werkstoff", "", auswahl=WERKSTOFFE),
    ],
    Eingaben=NabeParameter, erzeuge=erzeuge_nabe,
    BERECHNUNGS_QUELLEN={"d_f": ("pressverband", "d_F"), "d_a": ("pressverband", "D_A"), "l_f": ("pressverband", "l_F")},
)


# ================================================================ Zahnrad
def evolvente(alpha: float) -> float:
    return math.tan(alpha) - alpha


def zahnprofil(m: float, z: int, alpha_grad: float = 20.0, punkte_je_flanke: int = 10) -> list[tuple[float, float]]:
    """Stirnschnitt eines Außenzahnrads (Evolvente, ohne Profilverschiebung, Fußgrund als Kreisbogen).
    Kopfspiel 0,25·m (DIN 867)."""
    if z < 6:
        raise GeometrieFehler("Mindestens 6 Zähne.")
    a = math.radians(alpha_grad)
    r = m * z / 2
    rb = r * math.cos(a)
    ra = r + m
    rf = r - 1.25 * m
    psi = math.pi / (2 * z)                  # halbe Zahndicke am Teilkreis als Winkel
    def theta(R):
        return psi + evolvente(a) - evolvente(math.acos(min(1.0, rb / R)))
    r_start = max(rb, rf)
    radien = [r_start + (ra - r_start) * (i / punkte_je_flanke) ** 1.3 for i in range(punkte_je_flanke + 1)]
    profil = []
    for k in range(z):
        mitte = 2 * math.pi * k / z
        links = []
        if rf < rb:
            links.append((rf, mitte - theta(rb)))
        links += [(R, mitte - theta(R)) for R in radien]
        rechts = [(R, mitte + theta(R)) for R in reversed(radien)]
        if rf < rb:
            rechts.append((rf, mitte + theta(rb)))
        kopf = [(ra, mitte - theta(ra) + (2 * theta(ra)) * i / 4) for i in range(1, 4)]
        profil += links + kopf + rechts
        # Fußbogen bis zur nächsten Zahnlücke
        start = mitte + (theta(rb) if rf < rb else theta(rf))
        ende = 2 * math.pi * (k + 1) / z - (theta(rb) if rf < rb else theta(rf))
        profil += [(rf, start + (ende - start) * i / 4) for i in range(1, 4)]
    return [(R * math.cos(w), R * math.sin(w)) for R, w in profil]


def zahnrad_flaeche(m: float, z: int, alpha_grad: float = 20.0):
    """Stirnschnitt als Fläche mit glatten Flanken: Evolventen als interpolierte B-Splines, Kopf und Fuß als
    Kreisbögen (für saubere STEP-Daten und Fertigung)."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeWire
    from OCP.GC import GC_MakeArcOfCircle
    from OCP.GeomAPI import GeomAPI_Interpolate
    try:
        from OCP.TColgp import TColgp_HArray1OfPnt          # OCP ≤ 7.7
    except ImportError:
        from OCP.collections import HArray1_gp_Pnt as TColgp_HArray1OfPnt   # OCP ≥ 7.8

    if z < 6:
        raise GeometrieFehler("Mindestens 6 Zähne.")
    a = math.radians(alpha_grad)
    r = m * z / 2
    rb, ra, rf = r * math.cos(a), r + m, r - 1.25 * m
    psi = math.pi / (2 * z)

    def theta(R):
        return psi + evolvente(a) - evolvente(math.acos(min(1.0, rb / R)))

    def pkt(R, w):
        return gp_Pnt(R * math.cos(w), R * math.sin(w), 0)

    r_start = max(rb, rf)
    n = 12
    radien = [r_start + (ra - r_start) * (i / n) ** 1.3 for i in range(n + 1)]

    def spline(punkte):
        feld = TColgp_HArray1OfPnt(1, len(punkte))
        for i, q in enumerate(punkte, 1):
            feld.SetValue(i, q)
        interp = GeomAPI_Interpolate(feld, False, 1e-7)
        interp.Perform()
        return BRepBuilderAPI_MakeEdge(interp.Curve()).Edge()

    def bogen(p1, p2, p3):
        return BRepBuilderAPI_MakeEdge(GC_MakeArcOfCircle(p1, p2, p3).Value()).Edge()

    def fuss_winkel(k):        # Winkel, an dem der Fußkreis in die linke Flanke von Zahn k übergeht
        return 2 * math.pi * k / z - (theta(rb) if rf < rb else theta(r_start))

    draht = BRepBuilderAPI_MakeWire()
    for k in range(z):
        mitte = 2 * math.pi * k / z
        links = [pkt(R, mitte - theta(R)) for R in radien]
        rechts = [pkt(R, mitte + theta(R)) for R in reversed(radien)]
        if rf < rb:
            draht.Add(BRepBuilderAPI_MakeEdge(pkt(rf, fuss_winkel(k)), links[0]).Edge())
        draht.Add(spline(links))
        draht.Add(bogen(links[-1], pkt(ra, mitte), rechts[0]))
        draht.Add(spline(rechts))
        ende_rechts = rechts[-1]
        if rf < rb:
            ende_rechts = pkt(rf, mitte + theta(rb))
            draht.Add(BRepBuilderAPI_MakeEdge(rechts[-1], ende_rechts).Edge())
        w0 = mitte + (theta(rb) if rf < rb else theta(r_start))
        w1 = fuss_winkel(k + 1) if k + 1 < z else fuss_winkel(0) + 2 * math.pi
        naechster = pkt(rf, fuss_winkel((k + 1) % z))
        draht.Add(bogen(ende_rechts, pkt(rf, (w0 + w1) / 2), naechster))
    if not draht.IsDone():
        raise GeometrieFehler("Das Zahnprofil ließ sich nicht schließen.")
    return BRepBuilderAPI_MakeFace(draht.Wire(), True).Face()


@dataclass
class ZahnradParameter:
    rad: str = "Ritzel bzw. Sonne (z1)"
    m_n: float = 2.0
    z1: float = 21
    z2: float = 30
    b_mm: float = 30.0
    alpha: float = 20.0
    d_bohrung: float = 20.0
    werkstoff: str = werkstoffe.bezeichnung(werkstoffe.werkstoff("16MnCr5"))


RAEDER = ("Ritzel bzw. Sonne (z1)", "Rad bzw. Planet (z2)")


def erzeuge_zahnrad(p: ZahnradParameter):
    z = int(round(p.z1 if p.rad == RAEDER[0] else p.z2))
    rf = p.m_n * z / 2 - 1.25 * p.m_n
    if p.d_bohrung >= 2 * rf - 2 * p.m_n:
        raise GeometrieFehler("Die Bohrung ist zu groß: der Zahnkranz wird dünner als 1·m.")
    from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
    from OCP.gp import gp_Vec
    form = BRepPrimAPI_MakePrism(zahnrad_flaeche(p.m_n, z, p.alpha), gp_Vec(0, 0, p.b_mm)).Shape()
    if p.d_bohrung > 0:
        form = abziehen(form, zylinder(p.d_bohrung, p.b_mm + 2, -1))
    return form


ZAHNRAD = Vorlage(
    TYP="zahnrad", TITEL="Stirnrad (Evolventenverzahnung)", KURZ="Zahnrad",
    BESCHREIBUNG="Geradverzahntes Stirnrad mit Evolventenprofil und Bohrung. Modul, Zähnezahlen und Breite kommen "
                 "aus der Getriebeberechnung.",
    FELDER=[
        Feld("rad", "Welches Rad", "", auswahl=RAEDER),
        Feld("m_n", "Modul m", "mm", 0.5, 30, 0.25, 2, "aus der Getriebeberechnung"),
        Feld("z1", "Zähnezahl z1", "", 6, 200, 1, 0, "aus der Getriebeberechnung"),
        Feld("z2", "Zähnezahl z2", "", 6, 400, 1, 0, "aus der Getriebeberechnung"),
        Feld("b_mm", "Zahnbreite", "mm", 2, 500, 1, 1, "aus der Getriebeberechnung"),
        Feld("alpha", "Eingriffswinkel", "deg", 14.5, 25, 0.5, 1, ""),
        Feld("d_bohrung", "Bohrung (0 = voll)", "mm", 0, 1000, 1, 1, ""),
        Feld("werkstoff", "Werkstoff", "", auswahl=WERKSTOFFE),
    ],
    Eingaben=ZahnradParameter, erzeuge=erzeuge_zahnrad,
    BERECHNUNGS_QUELLEN={"m_n": ("getriebe", "m"), "z1": ("getriebe", "z1"), "z2": ("getriebe", "z2"),
                         "b_mm": ("getriebe", "b"), "alpha": ("getriebe", "α")},
)

VORLAGEN = {v.TYP: v for v in (WELLE, FLANSCH, NABE, ZAHNRAD)}


def dichte(werkstoff_bezeichnung: str) -> float:
    return float(werkstoffe.nach_bezeichnung(werkstoff_bezeichnung)["dichte"])
