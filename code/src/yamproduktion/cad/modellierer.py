"""Freies Modellieren mit Feature-Baum (Lastenheft M27, M28, M33).

Ein freies Teil ist ein JSON-Wörterbuch:

    {"parameter": [{"name": "d", "formel": "80", "kommentar": ""}, ...],
     "features": [{"art": "skizze", "name": "Skizze1", "skizze": {...}},
                  {"art": "extrusion", "name": "Extrusion1", "skizze": "Skizze1", "hoehe": "l", "operation": "neu"},
                  {"art": "bohrung", ...}, {"art": "fase", ...}, ...],
     "werkstoff": "S355J2 · warmgewalzt"}

`bauen()` arbeitet die Features der Reihe nach ab. Ein fehlerhaftes Feature hält den Baum an; alle
Features davor bleiben sichtbar, die Meldung sagt, was nicht passt.
"""
from __future__ import annotations

import math
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.BRepFilletAPI import BRepFilletAPI_MakeChamfer, BRepFilletAPI_MakeFillet
from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakePrism, BRepPrimAPI_MakeRevol
from OCP.TopAbs import TopAbs_EDGE, TopAbs_SOLID
from OCP.TopExp import TopExp_Explorer
from OCP.gp import gp_Ax1, gp_Ax2, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec

from . import skizze as S
from .ausdruck import AusdruckFehler, auswerten, tabelle_auswerten
from .geometrie import GeometrieFehler, eigenschaften, ist_gueltig, step_lesen

ARTEN = {
    "skizze": "Skizze",
    "extrusion": "Extrusion",
    "rotation": "Rotation",
    "bohrung": "Bohrung",
    "fase": "Fase",
    "verrundung": "Verrundung",
    "muster": "Muster",
    "import": "STEP-Import",
}
OPERATIONEN = ("neu", "hinzufügen", "abziehen")
KANTENWAHL = {
    "alle": "Alle Kanten",
    "kreis": "Alle Kreiskanten",
    "oben": "Oberste Fläche (größtes z)",
    "unten": "Unterste Fläche (kleinstes z)",
    "aussen": "Äußere Kreiskanten",
    "senkrecht": "Senkrechte Kanten (∥ z)",
}


def _edge(s):
    from OCP.TopoDS import TopoDS
    return (getattr(TopoDS, "Edge", None) or TopoDS.Edge_s)(s)


def leer() -> dict:
    return {"parameter": [], "features": [], "werkstoff": ""}


@dataclass
class Schritt:
    name: str
    art: str
    ok: bool
    meldung: str = ""


@dataclass
class Ergebnis:
    form: object | None
    schritte: list[Schritt] = field(default_factory=list)
    werte: dict[str, float] = field(default_factory=dict)
    bezuege: list[tuple[str, str]] = field(default_factory=list)   # benutzte ber("typ", "symbol")
    fehler: str = ""

    @property
    def ok(self) -> bool:
        return not self.fehler and self.form is not None


def _vereinigen(a, b):
    op = BRepAlgoAPI_Fuse(a, b)
    op.SimplifyResult()
    return op.Shape()


def _verknuepfen(form, werkzeug, operation):
    if form is None or operation == "neu":
        if form is not None and operation == "neu":
            return _vereinigen(form, werkzeug)     # weiterer Körper im selben Teil
        if operation == "abziehen":
            raise GeometrieFehler("Abziehen geht erst, wenn schon ein Körper da ist.")
        return werkzeug
    if operation == "hinzufügen":
        return _vereinigen(form, werkzeug)
    if operation == "abziehen":
        return BRepAlgoAPI_Cut(form, werkzeug).Shape()
    raise GeometrieFehler(f"Unbekannte Operation „{operation}“.")


def _kanten(form, wahl: str):
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    e = eigenschaften(form)
    alle = []
    exp = TopExp_Explorer(form, TopAbs_EDGE)
    gesehen = set()
    while exp.More():
        k = _edge(exp.Current())
        h = k.__hash__()
        if h not in gesehen:
            gesehen.add(h)
            alle.append(k)
        exp.Next()
    if wahl == "alle":
        return alle
    tol = 1e-4 * max(e.groesse) + 1e-6
    treffer = []
    radien = []
    for k in alle:
        c = BRepAdaptor_Curve(k)
        ist_kreis = c.GetType().name == "GeomAbs_Circle"
        a, b = c.FirstParameter(), c.LastParameter()
        p0, p1, pm = c.Value(a), c.Value(b), c.Value((a + b) / 2)
        if wahl == "kreis" and ist_kreis:
            treffer.append(k)
        elif wahl == "oben" and all(abs(p.Z() - e.maximum[2]) < tol for p in (p0, p1, pm)):
            treffer.append(k)
        elif wahl == "unten" and all(abs(p.Z() - e.minimum[2]) < tol for p in (p0, p1, pm)):
            treffer.append(k)
        elif wahl == "senkrecht" and not ist_kreis and abs(p0.Z() - p1.Z()) > tol and \
                abs(p0.X() - p1.X()) < tol and abs(p0.Y() - p1.Y()) < tol:
            treffer.append(k)
        elif wahl == "aussen" and ist_kreis:
            radien.append((c.Circle().Radius(), k))
    if wahl == "aussen" and radien:
        r_max = max(r for r, _ in radien)
        treffer = [k for r, k in radien if abs(r - r_max) < tol]
    return treffer


def _richtung(n, umkehren: bool):
    return tuple(-x for x in n) if umkehren else tuple(n)


def bauen(definition: dict, ber=None, bis: int | None = None) -> Ergebnis:
    """Baut das Teil. `ber(typ, symbol)` liefert Werte aus Berechnungen; `bis` = nur die ersten n Features."""
    bezuege: list[tuple[str, str]] = []

    def ber_merken(typ, symbol):
        bezuege.append((typ, symbol))
        return ber(typ, symbol) if ber else None

    try:
        werte = tabelle_auswerten(definition.get("parameter", []), ber_merken)
    except AusdruckFehler as exc:
        return Ergebnis(None, [], {}, bezuege, f"Parameter: {exc}")

    def w(formel):
        return auswerten(formel, werte, ber_merken)

    form = None
    skizzen: dict[str, dict] = {}
    werkzeuge: dict[str, tuple] = {}     # Feature-Name → (Werkzeugkörper, Operation) für Muster
    schritte: list[Schritt] = []
    features = definition.get("features", [])
    if bis is not None:
        features = features[:bis]
    namen = set()
    for f in features:
        art, name = f.get("art"), f.get("name", "")
        if name in namen:
            fehler = f"Der Name „{name}“ kommt zweimal vor."
            schritte.append(Schritt(name, art, False, fehler))
            return Ergebnis(form, schritte, werte, bezuege, f"{name}: {fehler}")
        namen.add(name)
        try:
            if art == "skizze":
                skizzen[name] = f["skizze"]
                l = S.loesen(f["skizze"], werte, ber_merken)
                if not l.ok:
                    raise GeometrieFehler(l.meldung)
                schritte.append(Schritt(name, art, True))
                continue
            if art in ("extrusion", "rotation"):
                if f.get("skizze") not in skizzen:
                    raise GeometrieFehler(f"Die Skizze „{f.get('skizze')}“ gibt es (davor) nicht.")
                flaechen, (u, v, n, _) = S.flaechen(skizzen[f["skizze"]], werte, ber_merken)
                koerper = None
                for fl in flaechen:
                    if art == "extrusion":
                        h = w(f.get("hoehe", 10))
                        if h <= 0:
                            raise GeometrieFehler("Die Höhe muss größer als 0 sein.")
                        richtung = _richtung(n, f.get("umkehren", False))
                        if f.get("symmetrisch"):
                            t = gp_Trsf()
                            t.SetTranslation(gp_Vec(*[-x * h / 2 for x in richtung]))
                            fl = BRepBuilderAPI_Transform(fl, t, True).Shape()
                        k = BRepPrimAPI_MakePrism(fl, gp_Vec(*[x * h for x in richtung])).Shape()
                    else:
                        winkel = w(f.get("winkel", 360))
                        if not 0 < winkel <= 360:
                            raise GeometrieFehler("Der Drehwinkel muss zwischen 0 und 360° liegen.")
                        achse_skizze = u if f.get("achse", "x") == "x" else v
                        _, _, _, d = S._ebene(skizzen[f["skizze"]], werte, ber_merken)
                        ursprung = gp_Pnt(*[d * x for x in n])
                        k = BRepPrimAPI_MakeRevol(fl, gp_Ax1(ursprung, gp_Dir(*achse_skizze)), math.radians(winkel)).Shape()
                    koerper = k if koerper is None else _vereinigen(koerper, k)
                op = f.get("operation", "neu")
                form = _verknuepfen(form, koerper, op)
                werkzeuge[name] = (koerper, op)
            elif art == "bohrung":
                u, v, n = S.EBENEN[f.get("ebene", "XY")]
                d0 = w(f.get("versatz", 0))
                x, y = w(f.get("x", 0)), w(f.get("y", 0))
                dm = w(f["d"])
                if dm <= 0:
                    raise GeometrieFehler("Der Bohrungsdurchmesser muss größer als 0 sein.")
                tiefe_text = str(f.get("tiefe", "durch")).strip()
                if tiefe_text == "durch":
                    if form is None:
                        raise GeometrieFehler("Bohren geht erst, wenn ein Körper da ist.")
                    tiefe = 4 * max(eigenschaften(form).groesse) + 10
                    start_zurueck = tiefe / 2
                else:
                    tiefe, start_zurueck = w(tiefe_text), 0.0
                    if tiefe <= 0:
                        raise GeometrieFehler("Die Bohrtiefe muss größer als 0 sein.")
                # Bohrt von der Ebene aus gegen die Normale ins Material
                mitte = [x * u[i] + y * v[i] + d0 * n[i] + start_zurueck * n[i] for i in range(3)]
                k = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(*mitte), gp_Dir(*[-c for c in n])), dm / 2, tiefe).Shape()
                form = _verknuepfen(form, k, "abziehen")
                werkzeuge[name] = (k, "abziehen")
            elif art in ("fase", "verrundung"):
                if form is None:
                    raise GeometrieFehler("Erst einen Körper erzeugen.")
                g = w(f.get("groesse", 1))
                if g <= 0:
                    raise GeometrieFehler("Die Größe muss größer als 0 sein.")
                kanten = _kanten(form, f.get("kanten", "alle"))
                if not kanten:
                    raise GeometrieFehler("Keine passenden Kanten gefunden.")
                bau = BRepFilletAPI_MakeChamfer(form) if art == "fase" else BRepFilletAPI_MakeFillet(form)
                for k in kanten:
                    bau.Add(g, k)
                try:
                    bau.Build()
                except Exception:
                    pass
                if not bau.IsDone():
                    raise GeometrieFehler(f"{ARTEN[art]} {g:g} mm lässt sich an diesen Kanten nicht anbringen "
                                          "(zu groß oder Kanten treffen sich).")
                neu = bau.Shape()
                if not ist_gueltig(neu):
                    raise GeometrieFehler(f"{ARTEN[art]} ergibt einen ungültigen Körper – kleinere Größe oder andere Kanten wählen.")
                form = neu
            elif art == "muster":
                ziel = f.get("feature")
                if ziel not in werkzeuge:
                    raise GeometrieFehler(f"Das Feature „{ziel}“ (davor, mit Körper) gibt es nicht.")
                werkzeug, op = werkzeuge[ziel]
                anzahl = int(round(w(f.get("anzahl", 4))))
                if anzahl < 2:
                    raise GeometrieFehler("Ein Muster braucht mindestens 2 Exemplare.")
                kopien = None
                for i in range(1, anzahl):
                    t = gp_Trsf()
                    if f.get("muster", "kreis") == "kreis":
                        gesamt = w(f.get("winkel", 360))
                        schritt = gesamt / anzahl if abs(gesamt - 360) < 1e-9 else gesamt / (anzahl - 1)
                        achse = {"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1)}[f.get("achse", "z")]
                        t.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(*achse)), math.radians(schritt * i))
                    else:
                        richt = {"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1)}[f.get("richtung", "x")]
                        a = w(f.get("abstand", 10))
                        t.SetTranslation(gp_Vec(*[c * a * i for c in richt]))
                    kopie = BRepBuilderAPI_Transform(werkzeug, t, True).Shape()
                    kopien = kopie if kopien is None else _vereinigen(kopien, kopie)
                form = _verknuepfen(form, kopien, "hinzufügen" if op == "neu" else op)
                werkzeuge[name] = (kopien, op)
            elif art == "import":
                with tempfile.TemporaryDirectory() as ordner:
                    datei = Path(ordner) / "import.step"
                    datei.write_text(f["step"], encoding="utf-8")
                    k = step_lesen(datei)
                op = f.get("operation", "neu")
                form = _verknuepfen(form, k, op)
                werkzeuge[name] = (k, op)
            else:
                raise GeometrieFehler(f"Unbekannte Feature-Art „{art}“.")
            if form is not None and not ist_gueltig(form):
                raise GeometrieFehler("Das Ergebnis ist kein gültiger Körper.")
            schritte.append(Schritt(name, art, True))
        except (GeometrieFehler, AusdruckFehler, KeyError, ValueError) as exc:
            text = str(exc) if not isinstance(exc, KeyError) else f"Angabe {exc} fehlt."
            schritte.append(Schritt(name, art, False, text))
            return Ergebnis(form, schritte, werte, bezuege, f"{name}: {text}")
    return Ergebnis(form, schritte, werte, bezuege, "")


def anzahl_koerper(form) -> int:
    n = 0
    exp = TopExp_Explorer(form, TopAbs_SOLID)
    while exp.More():
        n += 1
        exp.Next()
    return n


def naechster_name(definition: dict, art: str) -> str:
    basis = "Import" if art == "import" else ARTEN[art]
    namen = {f["name"] for f in definition.get("features", [])}
    i = 1
    while f"{basis}{i}" in namen:
        i += 1
    return f"{basis}{i}"
