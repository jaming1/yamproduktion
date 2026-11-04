"""Normteil-Bibliothek (Lastenheft M30): Schrauben, Muttern, Scheiben, Wälzlager, Passfedern.

Maße aus den Normen bzw. Herstellerangaben (Tabellenbuch) – Stand „Norm, ungeprüft“: vor der Bestellung mit dem
Katalog abgleichen. Die Geometrie ist vereinfacht (kein Gewinde, Lager als Vollring); sie dient Ansicht,
Kollision, Masse und Stückliste.

Bezeichnungen (Schlüssel):  „ISO 4762 M12x40“, „ISO 4017 M16x60“, „ISO 4032 M12“, „ISO 7089 12“,
„6216“ (Rillenkugellager), „22216 E“ (Pendelrollenlager), „DIN 6885 A 22x14x80“.
Lage: Achse = z. Schrauben: Kopfauflage bei z = 0, Schaft in −z, Kopf in +z. Lager, Mutter, Scheibe: z = 0 … Breite.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

from OCP.BRepBuilderAPI import BRepBuilderAPI_MakePolygon, BRepBuilderAPI_MakeFace
from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
from OCP.gp import gp_Pnt, gp_Vec

from .geometrie import GeometrieFehler, abziehen, vereinigen, zylinder

HINWEIS = "Maße nach Norm/Katalog aus dem Tabellenbuch, nicht geprüft – vor Bestellung mit dem Katalog abgleichen."
STAHL = 7850.0          # kg/m³
LAGER_FUELLGRAD = 0.62  # Vollring → Lagermasse; grobe Näherung, unbelegt

# ISO 4762 Zylinderschraube mit Innensechskant: d → (Kopf-Ø dk, Kopfhöhe k, Schlüsselweite s Innensechskant)
ISO_4762 = {6: (10, 6, 5), 8: (13, 8, 6), 10: (16, 10, 8), 12: (18, 12, 10), 16: (24, 16, 14), 20: (30, 20, 17),
            24: (36, 24, 19)}
# ISO 4017 Sechskantschraube (Gewinde bis Kopf): d → (Schlüsselweite s, Kopfhöhe k)
ISO_4017 = {6: (10, 4.0), 8: (13, 5.3), 10: (16, 6.4), 12: (18, 7.5), 16: (24, 10.0), 20: (30, 12.5), 24: (36, 15.0)}
# ISO 4032 Sechskantmutter: d → (s, m)
ISO_4032 = {6: (10, 5.2), 8: (13, 6.8), 10: (16, 8.4), 12: (18, 10.8), 16: (24, 14.8), 20: (30, 18.0), 24: (36, 21.5)}
# ISO 7089 Scheibe: Nenngröße → (d1, d2, h)
ISO_7089 = {6: (6.4, 12, 1.6), 8: (8.4, 16, 1.6), 10: (10.5, 20, 2.0), 12: (13.0, 24, 2.5), 16: (17.0, 30, 3.0),
            20: (21.0, 37, 3.0), 24: (25.0, 44, 4.0)}
# Wälzlager (ISO 15 Maßreihen): Bezeichnung → (d, D, B, Art)
LAGER = {
    **{f"62{k:02d}": (5 * k, D, B, "Rillenkugellager") for k, D, B in (
        (5, 52, 15), (6, 62, 16), (7, 72, 17), (8, 80, 18), (9, 85, 19), (10, 90, 20), (11, 100, 21), (12, 110, 22),
        (13, 120, 23), (14, 125, 24), (15, 130, 25), (16, 140, 26), (18, 160, 30), (20, 180, 34))},
    **{f"63{k:02d}": (5 * k, D, B, "Rillenkugellager") for k, D, B in (
        (6, 72, 19), (8, 90, 23), (10, 110, 27), (12, 130, 31), (16, 170, 39))},
    "22216 E": (80, 140, 33, "Pendelrollenlager"), "22218 E": (90, 160, 40, "Pendelrollenlager"),
    "22220 E": (100, 180, 46, "Pendelrollenlager"),
}
SCHRAUBEN_LAENGEN = (10, 12, 16, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 80, 90, 100, 110, 120, 130, 140, 150,
                     160, 180, 200)


@dataclass
class Normteil:
    norm: str            # vollständige Bezeichnung (Schlüssel der Stückliste)
    benennung: str
    form: object         # OCP-Körper
    masse: float         # kg
    werkstoff: str
    hinweis: str = HINWEIS


def _sechskant(s: float, hoehe: float, z0: float):
    r = s / math.sqrt(3)          # Eckmaß e = 2r
    poly = BRepBuilderAPI_MakePolygon()
    for i in range(6):
        w = math.radians(30 + 60 * i)
        poly.Add(gp_Pnt(r * math.cos(w), r * math.sin(w), z0))
    poly.Close()
    flaeche = BRepBuilderAPI_MakeFace(poly.Wire()).Face()
    return BRepPrimAPI_MakePrism(flaeche, gp_Vec(0, 0, hoehe)).Shape()


def _masse(form, dichte: float, faktor: float = 1.0) -> float:
    from .geometrie import eigenschaften
    return eigenschaften(form).volumen * 1e-9 * dichte * faktor


def katalog() -> dict[str, list[str]]:
    """Auswahl für die Oberfläche: Gruppe → Bezeichnungen (Schrauben mit typischer Länge)."""
    return {
        "Zylinderschraube ISO 4762": [f"ISO 4762 M{d}x{l}" for d in ISO_4762 for l in (2 * d, 3 * d, 4 * d) if l in SCHRAUBEN_LAENGEN],
        "Sechskantschraube ISO 4017": [f"ISO 4017 M{d}x{l}" for d in ISO_4017 for l in (2 * d, 3 * d, 4 * d) if l in SCHRAUBEN_LAENGEN],
        "Sechskantmutter ISO 4032": [f"ISO 4032 M{d}" for d in ISO_4032],
        "Scheibe ISO 7089": [f"ISO 7089 {d}" for d in ISO_7089],
        "Wälzlager": list(LAGER),
        "Passfeder DIN 6885 A": [f"DIN 6885 A {b}x{h}x{l}" for b, h, l in ((14, 9, 63), (16, 10, 70), (18, 11, 80),
                                                                            (20, 12, 90), (22, 14, 80), (22, 14, 100))],
    }


def erzeugen(norm: str) -> Normteil:
    """Normteil aus seiner Bezeichnung erzeugen. Wirft GeometrieFehler bei unbekannter Größe."""
    text = " ".join(norm.replace("×", "x").split())
    if m := re.fullmatch(r"ISO (4762|4017) M(\d+)x(\d+(?:\.\d+)?)", text):
        art, d, l = m.group(1), int(m.group(2)), float(m.group(3))
        tabelle = ISO_4762 if art == "4762" else ISO_4017
        if d not in tabelle:
            raise GeometrieFehler(f"M{d} ist in ISO {art} hier nicht hinterlegt ({', '.join(f'M{k}' for k in tabelle)}).")
        if l < 2 * 0.8 * d / 2 or l > 300:
            raise GeometrieFehler(f"Schraubenlänge {l:g} mm passt nicht zu M{d}.")
        schaft = zylinder(d, l, -l)
        if art == "4762":
            dk, k, s = tabelle[d]
            kopf = abziehen(zylinder(dk, k, 0.0), _sechskant(s, 0.6 * k, k - 0.6 * k + 0.001))
            benennung = "Zylinderschraube mit Innensechskant"
        else:
            s, k = tabelle[d]
            kopf = _sechskant(s, k, 0.0)
            benennung = "Sechskantschraube"
        form = vereinigen(schaft, kopf)
        return Normteil(text, benennung, form, _masse(form, STAHL), "Festigkeitsklasse 8.8")
    if m := re.fullmatch(r"ISO 4032 M(\d+)", text):
        d = int(m.group(1))
        if d not in ISO_4032:
            raise GeometrieFehler(f"M{d} ist in ISO 4032 hier nicht hinterlegt.")
        s, mh = ISO_4032[d]
        form = abziehen(_sechskant(s, mh, 0.0), zylinder(d, mh + 2, -1))
        return Normteil(text, "Sechskantmutter", form, _masse(form, STAHL), "Festigkeitsklasse 8")
    if m := re.fullmatch(r"ISO 7089 (\d+)", text):
        d = int(m.group(1))
        if d not in ISO_7089:
            raise GeometrieFehler(f"Scheibe {d} ist in ISO 7089 hier nicht hinterlegt.")
        d1, d2, h = ISO_7089[d]
        form = abziehen(zylinder(d2, h, 0.0), zylinder(d1, h + 2, -1))
        return Normteil(text, "Scheibe", form, _masse(form, STAHL), "Stahl 200 HV")
    if text in LAGER:
        d, D, B, art = LAGER[text]
        form = abziehen(zylinder(D, B, 0.0), zylinder(d, B + 2, -1))
        return Normteil(text, art, form, _masse(form, STAHL, LAGER_FUELLGRAD), "Wälzlagerstahl 100Cr6",
                        HINWEIS + " Masse genähert (Vollring × 0,62).")
    if m := re.fullmatch(r"DIN 6885 A (\d+)x(\d+)x(\d+)", text):
        b, h, l = (float(m.group(i)) for i in (1, 2, 3))
        if l < b:
            raise GeometrieFehler("Die Passfeder ist kürzer als breit.")
        # Form A: rundstirnig; Achse x, Höhe y, liegt bei z = 0 … h
        from .geometrie import quader
        gerade = quader(-(l - b) / 2, -b / 2, 0, l - b, b, h)
        form = vereinigen(gerade, zylinder(b, h, 0.0, -(l - b) / 2, 0.0), zylinder(b, h, 0.0, (l - b) / 2, 0.0))
        return Normteil(text, "Passfeder Form A", form, _masse(form, STAHL), "C45+C")
    raise GeometrieFehler(f"Das Normteil „{norm}“ kenne ich nicht. Beispiele: ISO 4762 M12x40, ISO 4032 M12, 6216.")
