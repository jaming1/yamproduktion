"""2D-Skizzen mit Bedingungen und Bemaßungen (Lastenheft M27), gelöst mit einem eigenen Gauß-Newton-Löser.

Eine Skizze ist ein reines Daten-Wörterbuch (JSON-fähig, wird im Projekt gespeichert):

    {"ebene": "XY", "versatz": "0",
     "punkte": {"p1": [0, 0], ...},
     "elemente": [{"id": "e1", "art": "linie", "p": ["p1", "p2"]},
                  {"id": "e2", "art": "kreis", "m": "p3", "r": 10},
                  {"id": "e3", "art": "bogen", "m": "p4", "p": ["p5", "p6"]},   # gegen den Uhrzeigersinn
                  {"id": "e4", "art": "linie", "p": [...], "hilf": true}],      # Hilfslinie: nicht im Profil
     "bedingungen": [{"art": "horizontal", "e": "e1"}, {"art": "abstand", "a": "p1", "b": "p2", "wert": "l"}, ...]}

Der Punkt „p0“ ist immer der Ursprung und fest. Bemaßungen dürfen Formeln mit Parametern enthalten.
"""
from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field

import numpy as np

from .ausdruck import auswerten
from .geometrie import GeometrieFehler

EBENEN = {   # Ursprung-Versatz entlang der Normalen; Achsen u, v, Normale n (rechtshändig)
    "XY": ((1, 0, 0), (0, 1, 0), (0, 0, 1)),
    "XZ": ((1, 0, 0), (0, 0, 1), (0, -1, 0)),
    "YZ": ((0, 1, 0), (0, 0, 1), (1, 0, 0)),
}

BEDINGUNGEN = {   # Art → (Anzeigename, braucht Wert)
    "horizontal": ("Waagerecht", False),
    "vertikal": ("Senkrecht (vertikal)", False),
    "parallel": ("Parallel", False),
    "senkrecht": ("Rechtwinklig", False),
    "gleich": ("Gleich lang / gleicher Radius", False),
    "koinzident": ("Deckungsgleich", False),
    "auf_linie": ("Punkt auf Linie", False),
    "fix": ("Fest", False),
    "tangential": ("Tangential", False),
    "abstand": ("Abstand", True),
    "abstand_h": ("Waagerechter Abstand", True),
    "abstand_v": ("Senkrechter Abstand", True),
    "laenge": ("Länge", True),
    "radius": ("Radius", True),
    "durchmesser": ("Durchmesser", True),
    "winkel": ("Winkel", True),
}


def leer(ebene: str = "XY", versatz="0") -> dict:
    return {"ebene": ebene, "versatz": versatz, "punkte": {"p0": [0.0, 0.0]}, "elemente": [], "bedingungen": []}


def _neue_id(vorhanden, praefix: str) -> str:
    i = 1
    while f"{praefix}{i}" in vorhanden:
        i += 1
    return f"{praefix}{i}"


# ---------------------------------------------------------------- Bearbeiten (für Editor und Tests)
def punkt_neu(sk: dict, x: float, y: float) -> str:
    pid = _neue_id(sk["punkte"], "p")
    sk["punkte"][pid] = [float(x), float(y)]
    return pid


def element(sk: dict, eid: str) -> dict:
    for e in sk["elemente"]:
        if e["id"] == eid:
            return e
    raise KeyError(eid)


def linie_neu(sk: dict, a: str, b: str, hilf: bool = False) -> str:
    eid = _neue_id({e["id"] for e in sk["elemente"]}, "e")
    sk["elemente"].append({"id": eid, "art": "linie", "p": [a, b], "hilf": hilf})
    return eid


def kreis_neu(sk: dict, m: str, r: float) -> str:
    eid = _neue_id({e["id"] for e in sk["elemente"]}, "e")
    sk["elemente"].append({"id": eid, "art": "kreis", "m": m, "r": float(r)})
    return eid


def bogen_neu(sk: dict, m: str, a: str, b: str) -> str:
    eid = _neue_id({e["id"] for e in sk["elemente"]}, "e")
    sk["elemente"].append({"id": eid, "art": "bogen", "m": m, "p": [a, b]})
    return eid


def rechteck_neu(sk: dict, x0: float, y0: float, x1: float, y1: float) -> list[str]:
    """Rechteck aus vier Linien mit gemeinsamen Eckpunkten, waagerecht/senkrecht bedingt."""
    p = [punkt_neu(sk, x0, y0), punkt_neu(sk, x1, y0), punkt_neu(sk, x1, y1), punkt_neu(sk, x0, y1)]
    e = [linie_neu(sk, p[i], p[(i + 1) % 4]) for i in range(4)]
    bedingung(sk, "horizontal", e=e[0])
    bedingung(sk, "horizontal", e=e[2])
    bedingung(sk, "vertikal", e=e[1])
    bedingung(sk, "vertikal", e=e[3])
    return e


def bedingung(sk: dict, art: str, **daten) -> dict:
    if art not in BEDINGUNGEN:
        raise GeometrieFehler(f"Unbekannte Bedingung „{art}“.")
    b = {"art": art, **daten}
    sk["bedingungen"].append(b)
    return b


def element_loeschen(sk: dict, eid: str) -> None:
    e = element(sk, eid)
    sk["elemente"].remove(e)
    sk["bedingungen"] = [b for b in sk["bedingungen"] if eid not in (b.get("e"), b.get("a"), b.get("b"))]
    benutzt = {"p0"}
    for x in sk["elemente"]:
        benutzt.update(x.get("p", []))
        if "m" in x:
            benutzt.add(x["m"])
    for pid in list(sk["punkte"]):
        if pid not in benutzt:
            del sk["punkte"][pid]
            sk["bedingungen"] = [b for b in sk["bedingungen"] if pid not in (b.get("a"), b.get("b"))]


# ---------------------------------------------------------------- Lösen
@dataclass
class Loesung:
    punkte: dict[str, tuple[float, float]]
    radien: dict[str, float]
    ok: bool
    freiheitsgrade: int
    meldung: str = ""
    werte: dict = field(default_factory=dict)   # ausgewertete Bemaßungen je Bedingung (Index → Wert)


def _unbekannte(sk: dict):
    """Unbekannte: x, y je Punkt (außer dem Ursprung p0) und der Radius je Kreis."""
    index, start = {}, []
    for pid, (x, y) in sk["punkte"].items():
        if pid == "p0":
            continue
        index[pid] = len(start)
        start += [float(x), float(y)]
    for e in sk["elemente"]:
        if e["art"] == "kreis":
            index[e["id"]] = len(start)
            start.append(float(e["r"]))
    return index, np.array(start, dtype=float)


def _gleichungen(sk: dict, parameter, ber):
    """Baut die Bedingungen als Liste von Restfunktionen f(punkt, radius) → Zahl (0 = erfüllt).
    Vorzeichen (Seite, Drehsinn) werden aus der aktuellen Lage übernommen – die Skizze klappt nicht um."""
    P = sk["punkte"]
    elemente = {e["id"]: e for e in sk["elemente"]}
    werte = {}
    gl = []

    def vorzeichen(v):
        return 1.0 if v >= 0 else -1.0

    def richtung(pt, eid):
        e = elemente[eid]
        a, b = pt(e["p"][0]), pt(e["p"][1])
        return b[0] - a[0], b[1] - a[1]

    def radius(pt, rd, eid):
        e = elemente[eid]
        if e["art"] == "kreis":
            return rd(eid)
        m, a = pt(e["m"]), pt(e["p"][0])
        return math.hypot(a[0] - m[0], a[1] - m[1])

    def abstand_punkt_linie(pt, pid, eid):
        e = elemente[eid]
        a, b, q = pt(e["p"][0]), pt(e["p"][1]), pt(pid)
        lang = math.hypot(b[0] - a[0], b[1] - a[1]) or 1e-12
        return ((b[0] - a[0]) * (q[1] - a[1]) - (b[1] - a[1]) * (q[0] - a[0])) / lang

    def jetzt(pid):
        return P[pid]

    def jetzt_r(eid):
        return elemente[eid]["r"]

    def name(k):
        if k in P or k in elemente:
            return k
        raise GeometrieFehler(f"Die Bedingung verweist auf „{k}“, das es nicht mehr gibt.")

    for i, b in enumerate(sk["bedingungen"]):
        art = b["art"]
        for k in ("e", "a", "b"):
            if k in b:
                name(b[k])
        wert = None
        if BEDINGUNGEN[art][1]:
            wert = auswerten(b["wert"], parameter, ber)
            werte[i] = wert
            if art in ("abstand", "abstand_h", "abstand_v", "laenge", "radius", "durchmesser") and wert <= 0:
                raise GeometrieFehler(f"{BEDINGUNGEN[art][0]} muss größer als 0 sein (ist {wert:g}).")
        A, B, E = b.get("a"), b.get("b"), b.get("e")
        if art in ("horizontal", "vertikal"):
            k = 1 if art == "horizontal" else 0
            gl.append(lambda pt, rd, E=E, k=k: (pt(elemente[E]["p"][1])[k] - pt(elemente[E]["p"][0])[k]))
        elif art in ("parallel", "senkrecht"):
            def f(pt, rd, A=A, B=B, art=art):
                (ax, ay), (bx, by) = richtung(pt, A), richtung(pt, B)
                n = (math.hypot(ax, ay) * math.hypot(bx, by)) or 1e-12
                return ((ax * by - ay * bx) if art == "parallel" else (ax * bx + ay * by)) / n * 100
            gl.append(f)
        elif art == "gleich":
            if elemente[A]["art"] == "linie":
                gl.append(lambda pt, rd, A=A, B=B: math.hypot(*richtung(pt, A)) - math.hypot(*richtung(pt, B)))
            else:
                gl.append(lambda pt, rd, A=A, B=B: radius(pt, rd, A) - radius(pt, rd, B))
        elif art == "koinzident":
            gl.append(lambda pt, rd, A=A, B=B: pt(A)[0] - pt(B)[0])
            gl.append(lambda pt, rd, A=A, B=B: pt(A)[1] - pt(B)[1])
        elif art == "auf_linie":
            gl.append(lambda pt, rd, A=A, B=B: abstand_punkt_linie(pt, A, B))
        elif art == "fix":
            x0, y0 = P[A]
            gl.append(lambda pt, rd, A=A, x0=x0: pt(A)[0] - x0)
            gl.append(lambda pt, rd, A=A, y0=y0: pt(A)[1] - y0)
        elif art == "tangential":
            linie = A if elemente[A]["art"] == "linie" else (B if elemente[B]["art"] == "linie" else None)
            if linie:
                rund = B if linie == A else A
                m = elemente[rund]["m"]
                s0 = vorzeichen(abstand_punkt_linie(jetzt, m, linie))
                gl.append(lambda pt, rd, L=linie, R=rund, m=m, s0=s0:
                          s0 * abstand_punkt_linie(pt, m, L) - radius(pt, rd, R))
            else:
                ma, mb = elemente[A]["m"], elemente[B]["m"]
                d0 = math.hypot(P[ma][0] - P[mb][0], P[ma][1] - P[mb][1])
                ra, rb = radius(jetzt, jetzt_r, A), radius(jetzt, jetzt_r, B)
                innen = abs(d0 - abs(ra - rb)) < abs(d0 - (ra + rb))
                gl.append(lambda pt, rd, A=A, B=B, ma=ma, mb=mb, innen=innen:
                          math.hypot(pt(ma)[0] - pt(mb)[0], pt(ma)[1] - pt(mb)[1])
                          - (abs(radius(pt, rd, A) - radius(pt, rd, B)) if innen else radius(pt, rd, A) + radius(pt, rd, B)))
        elif art == "abstand":
            if A in P and B in P:
                gl.append(lambda pt, rd, A=A, B=B, w=wert: math.hypot(pt(A)[0] - pt(B)[0], pt(A)[1] - pt(B)[1]) - w)
            else:
                pid, eid = (A, B) if A in P else (B, A)
                s0 = vorzeichen(abstand_punkt_linie(jetzt, pid, eid))
                gl.append(lambda pt, rd, p_=pid, e_=eid, s0=s0, w=wert: s0 * abstand_punkt_linie(pt, p_, e_) - w)
        elif art in ("abstand_h", "abstand_v"):
            k = 0 if art == "abstand_h" else 1
            s0 = vorzeichen(P[B][k] - P[A][k])
            gl.append(lambda pt, rd, A=A, B=B, k=k, s0=s0, w=wert: s0 * (pt(B)[k] - pt(A)[k]) - w)
        elif art == "laenge":
            gl.append(lambda pt, rd, E=E, w=wert: math.hypot(*richtung(pt, E)) - w)
        elif art in ("radius", "durchmesser"):
            faktor = 1.0 if art == "radius" else 2.0
            gl.append(lambda pt, rd, E=E, w=wert, f_=faktor: f_ * radius(pt, rd, E) - w)
        elif art == "winkel":
            (ax, ay), (bx, by) = richtung(jetzt, A), richtung(jetzt, B)
            s0 = vorzeichen(ax * by - ay * bx)
            w = math.radians(wert) * s0

            def f(pt, rd, A=A, B=B, w=w):
                (ax, ay), (bx, by) = richtung(pt, A), richtung(pt, B)
                n = (math.hypot(ax, ay) * math.hypot(bx, by)) or 1e-12
                return ((ax * by - ay * bx) * math.cos(w) - (ax * bx + ay * by) * math.sin(w)) / n * 100
            gl.append(f)
    # Bögen: Endpunkt liegt auf demselben Radius wie der Anfangspunkt
    for e in sk["elemente"]:
        if e["art"] == "bogen":
            gl.append(lambda pt, rd, e=e: math.hypot(pt(e["p"][1])[0] - pt(e["m"])[0], pt(e["p"][1])[1] - pt(e["m"])[1])
                      - math.hypot(pt(e["p"][0])[0] - pt(e["m"])[0], pt(e["p"][0])[1] - pt(e["m"])[1]))
    return gl, werte


def loesen(sk: dict, parameter: dict[str, float] | None = None, ber=None) -> Loesung:
    """Löst die Skizze mit dem Gauß-Newton-Verfahren (kleinste Änderung bei unterbestimmten Skizzen).
    Wirft keinen Fehler bei Widersprüchen, sondern meldet sie in Loesung.meldung."""
    parameter = parameter or {}
    index, x = _unbekannte(sk)
    gl, werte = _gleichungen(sk, parameter, ber)

    def zugriff(v):
        def pt(pid):
            if pid == "p0":
                return (0.0, 0.0)
            i = index[pid]
            return (v[i], v[i + 1])

        def rd(eid):
            return v[index[eid]]
        return pt, rd

    def rest(v):
        pt, rd = zugriff(v)
        return np.array([f(pt, rd) for f in gl], dtype=float)

    def jacobi(v, r0):
        J = np.zeros((len(gl), len(v)))
        for j in range(len(v)):
            h = 1e-7 * max(1.0, abs(v[j]))
            w = v.copy()
            w[j] += h
            J[:, j] = (rest(w) - r0) / h
        return J

    ok, meldung, frei = True, "", len(x)
    if gl and len(x):
        r = rest(x)
        for _ in range(60):
            if np.max(np.abs(r)) < 1e-9:
                break
            J = jacobi(x, r)
            schritt = np.linalg.lstsq(J, -r, rcond=None)[0]
            t, norm = 1.0, np.linalg.norm(r)
            while t > 1e-4:
                neu = x + t * schritt
                r_neu = rest(neu)
                if np.linalg.norm(r_neu) < norm or t <= 1e-3:
                    break
                t /= 2
            x, r = neu, r_neu
        J = jacobi(x, r)
        rang = int(np.linalg.matrix_rank(J, tol=1e-7 * max(1.0, float(np.abs(J).max(initial=0)))))
        frei = len(x) - rang
        if np.max(np.abs(r)) > 1e-7:
            ok = False
            meldung = ("Die Bedingungen widersprechen sich. Zuletzt hinzugefügte Bedingung entfernen."
                       if rang < len(gl) else
                       "Der Löser findet keine Lösung. Skizze näher an die gewünschte Form ziehen.")
    elif gl:
        r = rest(x)
        if np.max(np.abs(r)) > 1e-7:
            ok, meldung = False, "Die Bedingungen widersprechen sich. Zuletzt hinzugefügte Bedingung entfernen."
        frei = 0
    if ok:
        pt, rd = zugriff(x)
        punkte = {pid: tuple(map(float, pt(pid))) for pid in sk["punkte"]}
        radien = {e["id"]: float(rd(e["id"])) for e in sk["elemente"] if e["art"] == "kreis"}
    else:
        punkte = {pid: tuple(v) for pid, v in sk["punkte"].items()}
        radien = {e["id"]: float(e["r"]) for e in sk["elemente"] if e["art"] == "kreis"}
    return Loesung(punkte, radien, ok, frei, meldung, werte)


def geloest(sk: dict, parameter: dict[str, float] | None = None, ber=None) -> tuple[dict, Loesung]:
    """Kopie der Skizze mit den gelösten Koordinaten (für Anzeige und Speichern)."""
    l = loesen(sk, parameter, ber)
    neu = copy.deepcopy(sk)
    if l.ok:
        for pid, xy in l.punkte.items():
            neu["punkte"][pid] = [float(xy[0]), float(xy[1])]
        for e in neu["elemente"]:
            if e["art"] == "kreis":
                e["r"] = float(l.radien[e["id"]])
    return neu, l


# ---------------------------------------------------------------- Profil → Flächen
def _ebene(sk: dict, parameter, ber):
    u, v, n = EBENEN[sk.get("ebene", "XY")]
    d = auswerten(sk.get("versatz", 0) or 0, parameter, ber)
    return u, v, n, d


def nach_3d(sk: dict, x: float, y: float, parameter=None, ber=None):
    u, v, n, d = _ebene(sk, parameter, ber)
    return tuple(x * u[i] + y * v[i] + d * n[i] for i in range(3))


def flaechen(sk: dict, parameter: dict[str, float] | None = None, ber=None):
    """Löst die Skizze und baut aus allen geschlossenen Konturen ebene Flächen (innere Konturen = Löcher)."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace
    from OCP.BRepGProp import BRepGProp
    from OCP.GC import GC_MakeArcOfCircle, GC_MakeCircle
    from OCP.GProp import GProp_GProps
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

    sk_g, l = geloest(sk, parameter, ber)
    if not l.ok:
        raise GeometrieFehler(f"Skizze: {l.meldung}")
    u, v, n, d = _ebene(sk_g, parameter, ber)
    P = {pid: gp_Pnt(*nach_3d(sk_g, x, y, parameter, ber)) for pid, (x, y) in sk_g["punkte"].items()}
    kanten = []           # (Start, Ende, Kante) in Skizzenkoordinaten
    kreise = []
    for e in sk_g["elemente"]:
        if e.get("hilf"):
            continue
        if e["art"] == "linie":
            a, b = P[e["p"][0]], P[e["p"][1]]
            if a.Distance(b) < 1e-7:
                continue
            kanten.append((sk_g["punkte"][e["p"][0]], sk_g["punkte"][e["p"][1]], BRepBuilderAPI_MakeEdge(a, b).Edge()))
        elif e["art"] == "bogen":
            m = sk_g["punkte"][e["m"]]
            a, b = sk_g["punkte"][e["p"][0]], sk_g["punkte"][e["p"][1]]
            r = math.hypot(a[0] - m[0], a[1] - m[1])
            w0 = math.atan2(a[1] - m[1], a[0] - m[0])
            w1 = math.atan2(b[1] - m[1], b[0] - m[0])
            if w1 <= w0:
                w1 += 2 * math.pi
            wm = (w0 + w1) / 2
            mitte = gp_Pnt(*nach_3d(sk_g, m[0] + r * math.cos(wm), m[1] + r * math.sin(wm), parameter, ber))
            kanten.append((a, b, BRepBuilderAPI_MakeEdge(GC_MakeArcOfCircle(P[e["p"][0]], mitte, P[e["p"][1]]).Value()).Edge()))
        elif e["art"] == "kreis":
            achse = gp_Ax2(P[e["m"]], gp_Dir(*n), gp_Dir(*u))
            kreise.append(BRepBuilderAPI_MakeEdge(GC_MakeCircle(achse, float(e["r"])).Value()).Edge())
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeWire

    def gleich(p, q):
        return abs(p[0] - q[0]) < 1e-6 and abs(p[1] - q[1]) < 1e-6

    draehte = []
    offen = list(kanten)
    while offen:
        start, ende, kante = offen.pop(0)
        kette = [kante]
        while not gleich(ende, start):
            weiter = next((k for k in offen if gleich(k[0], ende) or gleich(k[1], ende)), None)
            if weiter is None:
                raise GeometrieFehler("Die Skizze hat eine offene Kontur. Endpunkte verbinden (gleiche Punkte benutzen).")
            offen.remove(weiter)
            ende = weiter[1] if gleich(weiter[0], ende) else weiter[0]
            kette.append(weiter[2])
        bau = BRepBuilderAPI_MakeWire()
        for k in kette:
            bau.Add(k)
        if not bau.IsDone():
            raise GeometrieFehler("Eine Kontur der Skizze ließ sich nicht schließen.")
        draehte.append(bau.Wire())
    for k in kreise:
        draehte.append(BRepBuilderAPI_MakeWire(k).Wire())
    if not draehte:
        raise GeometrieFehler("Die Skizze enthält keine geschlossene Kontur.")

    def flaeche(w):
        f = BRepBuilderAPI_MakeFace(w, True).Face()
        g = GProp_GProps()
        BRepGProp.SurfaceProperties_s(f, g)
        return f, g.Mass()

    einzel = sorted((flaeche(w) + (w,) for w in draehte), key=lambda t: -t[1])
    # Verschachtelung: eine Kontur liegt in der kleinsten größeren Kontur, die einen ihrer Punkte enthält
    from OCP.BRepClass import BRepClass_FaceClassifier
    from OCP.BRepTools import BRepTools_WireExplorer
    from OCP.TopAbs import TopAbs_IN
    eltern = [-1] * len(einzel)
    for i in range(len(einzel)):
        ex = BRepTools_WireExplorer(einzel[i][2])
        probe = BRep_punkt(ex.CurrentVertex())
        for j in range(i - 1, -1, -1):
            if BRepClass_FaceClassifier(einzel[j][0], probe, 1e-6).State() == TopAbs_IN:
                eltern[i] = j
                break
    tiefe = []
    for i in range(len(einzel)):
        t, k = 0, eltern[i]
        while k >= 0:
            t, k = t + 1, eltern[k]
        tiefe.append(t)
    ergebnis = []
    for i, (f, _, w) in enumerate(einzel):
        if tiefe[i] % 2:
            continue
        bau = BRepBuilderAPI_MakeFace(f)
        for j in range(len(einzel)):
            if eltern[j] == i and tiefe[j] % 2:
                bau.Add(einzel[j][2])        # Orientierung richtet ShapeFix_Face
        flaeche_mit_loch = bau.Face()
        from OCP.ShapeFix import ShapeFix_Face
        fix = ShapeFix_Face(flaeche_mit_loch)
        fix.FixOrientation()
        fix.Perform()
        ergebnis.append(fix.Face())
    return ergebnis, (u, v, n, d)


def BRep_punkt(vertex):   # noqa: N802
    from OCP.BRep import BRep_Tool
    from OCP.TopoDS import TopoDS
    vx = (getattr(TopoDS, "Vertex", None) or TopoDS.Vertex_s)(vertex)
    return BRep_Tool.Pnt_s(vx)
