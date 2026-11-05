"""CAM-Export: G-Code für einfache Dreh- und Fräsbearbeitung (Lastenheft K5, Entscheidung E42).

Aus der 3D-Geometrie eines Bauteils und seinem Arbeitsplan entstehen NC-Programme nach DIN 66025 / ISO 6983:

* **Drehen** (Drehteile): je Seite eine Aufspannung – Plandrehen, Zentrieren, Bohren und Ausdrehen auf der
  Achse, Längsschruppen achsparallel, Schlichten entlang der Kontur. Durchmesserprogrammierung, Nullpunkt in
  der Mitte der fertigen Stirnfläche, Z negativ ins Werkstück.
* **Fräsen**: Passfedernuten in Wellen (pendelnd mit Zustellung), Bohrbilder (Anbohren, Tiefbohren mit
  Entspänen) je Aufspannrichtung, bei plattenförmigen Teilen die Außenkontur als Rechteck.

Bewusst einfach und steuerungsneutral (E42): nur G0/G1 mit ausgeschriebenen Wegen – keine Zyklen, keine
Schneidenradius- oder Fräserradiuskorrektur, konstante Drehzahl (G97). Schnittwerte kommen aus
`schnittdaten` (Richtwerte, ungeprüft) – dieselben Werte wie im Arbeitsplan, darum passen die Zeiten zusammen.

`pruefen()` liest einen G-Code wieder ein (eigener kleiner Leser): Verfahrwege, Bereich, Hauptzeit und
typische Fehler (Vorschub ohne F, Schnitt bei stehender Spindel, Eilgang im Werkstück, fehlendes Programmende).
"""
from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import schnittdaten as S

HINWEIS = ("G-Code ist ungeprüft und wird ohne Werkzeugradiuskorrektur erzeugt. Vor dem Einsatz im Simulator der "
           "Steuerung testen, Werkzeugnummern, Nullpunkt und Schnittwerte an die eigene Maschine anpassen und den "
           "ersten Lauf mit reduziertem Eilgang und Vorschub fahren.")
DIALEKTE = {
    "din": "DIN 66025 / ISO 6983 (mit Satznummern)",
    "fanuc": "Fanuc-ähnlich (O-Nummer, Drehen G98/G99)",
    "linuxcnc": "LinuxCNC",
}
EILGANG = 5000.0          # mm/min – Richtwert für die Nebenzeit beim Prüfen
ANBOHREN_D = 10.0         # NC-Anbohrer 90°
BOHRER_MAX = 30.0         # größerer Ø: vorbohren und ausdrehen (wie im Arbeitsplan)
FRAESER_KONTUR = 20.0     # Schaftfräser für die Außenkontur (wie im Arbeitsplan-Vorschlag)


class CamFehler(ValueError):
    pass


@dataclass
class Einstellungen:
    dialekt: str = "din"
    sicherheitsabstand: float = 2.0     # mm über/vor dem Werkstück
    schnitttiefe: float = S.AP_SCHRUPPEN  # a_p mm je Schruppschnitt (radial)
    aufmass: float = 0.3                # mm radial fürs Schlichten
    kuehlung: bool = True
    programmnummer: int = 1000

    @classmethod
    def aus_dict(cls, d: dict | None) -> "Einstellungen":
        e = cls()
        for k, v in (d or {}).items():
            if hasattr(e, k):
                setattr(e, k, type(getattr(e, k))(v))
        return e

    def als_dict(self) -> dict:
        return asdict(self)

    def pruefen(self) -> None:
        if self.dialekt not in DIALEKTE:
            raise CamFehler(f"Unbekannte Steuerung „{self.dialekt}“.")
        if not 0.5 <= self.sicherheitsabstand <= 50:
            raise CamFehler("Der Sicherheitsabstand muss zwischen 0,5 und 50 mm liegen.")
        if not 0.2 <= self.schnitttiefe <= 10:
            raise CamFehler("Die Schnitttiefe muss zwischen 0,2 und 10 mm liegen.")
        if not 0 <= self.aufmass <= 2:
            raise CamFehler("Das Schlichtaufmaß muss zwischen 0 und 2 mm liegen.")
        if not 1 <= self.programmnummer <= 9999:
            raise CamFehler("Die Programmnummer muss zwischen 1 und 9999 liegen.")


@dataclass
class Segment:
    a0: float
    b0: float
    a1: float
    b1: float
    eilgang: bool


@dataclass
class Programm:
    schluessel: str
    titel: str
    maschine: str
    art: str                       # "drehen" | "fraesen"
    aufspannung: str
    zeilen: list[str] = field(default_factory=list)
    werkzeuge: list[str] = field(default_factory=list)
    warnungen: list[str] = field(default_factory=list)
    umrisse: list[list[tuple[float, float]]] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(self.zeilen) + "\n"

    def dateiname(self, teil_nr: str) -> str:
        return f"{_ascii(teil_nr).replace(' ', '_')}_{self.schluessel}.nc"


# ================================================================ Hilfen
def _z(x: float) -> str:
    """Zahl für den G-Code: Punkt als Dezimalzeichen, höchstens 3 Nachkommastellen, ohne „-0“."""
    t = f"{x:.3f}".rstrip("0").rstrip(".")
    return "0" if t in ("-0", "") else t


def _ascii(text: str) -> str:
    """Kommentare nur in ASCII – viele Steuerungen kennen keine Umlaute; Klammern würden Kommentare beenden."""
    for alt, neu in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("Ä", "AE"), ("Ö", "OE"), ("Ü", "UE"), ("ß", "ss"),
                     ("Ø", "D"), ("ø", "D"), ("×", "x"), ("–", "-"), ("—", "-"), ("·", "-"), ("→", "->"),
                     ("≈", "ca."), ("°", " Grad"), ("(", "["), (")", "]"), (";", ",")):
        text = text.replace(alt, neu)
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()


class _Schreiber:
    """Sammelt Sätze und setzt Programmkopf, Satznummern und Programmende je Steuerung."""

    def __init__(self, einst: Einstellungen, art: str, titel: str, kopf: list[str]):
        self.e, self.art = einst, art
        self.saetze: list[str] = []
        self.titel, self.kopf = titel, kopf
        self.f_alt: float | None = None

    def k(self, text: str):
        self.saetze.append(f"({_ascii(text)})")

    def g0(self, **achsen):
        self.s("G0", *(f"{a.upper()}{_z(v)}" for a, v in achsen.items()))

    def g1(self, f: float | None = None, **achsen):
        """Vorschub-Satz; F nur, wenn er sich ändert (modal)."""
        neu = f is not None and f != self.f_alt
        if neu:
            self.f_alt = f
        self.s("G1", *(f"{a.upper()}{_z(v)}" for a, v in achsen.items()), f"F{_z(f)}" if neu else "")

    def s(self, *woerter):
        if woerter and woerter[0] in ("T0101", "T0202", "T0303", "T0404", "T0505", "G94", "G95", "G98", "G99") or \
                (len(woerter) > 1 and woerter[1] == "M6"):
            self.f_alt = None           # nach Werkzeugwechsel oder Vorschubart F neu setzen
        self.saetze.append(" ".join(w for w in woerter if w))

    def vorschub_je_umdrehung(self) -> str:
        return "G99" if self.e.dialekt == "fanuc" else "G95"

    def vorschub_je_minute(self) -> str:
        return "G98" if self.e.dialekt == "fanuc" and self.art == "drehen" else "G94"

    def fertig(self) -> list[str]:
        e = self.e
        if e.dialekt == "fanuc":
            anfang = ["%", f"O{e.programmnummer:04d} ({_ascii(self.titel)[:40]})"]
        else:
            anfang = ["%", f"({_ascii(self.titel)})"]
        kopf = [f"({_ascii(t)})" for t in self.kopf]
        if self.art == "drehen":
            grund = ["G18 G21 G40 G80 G90" + (" G7" if e.dialekt == "linuxcnc" else "")]
        else:
            grund = ["G17 G21 G40 G49 G80 G90 G94", "G54"]
        ende = ["M5", "M9", "M30"]
        rumpf = kopf + grund + self.saetze + ende
        if e.dialekt == "din":
            rumpf = [f"N{10 * (i + 1)} {z}" for i, z in enumerate(rumpf)]
        return anfang + rumpf + ["%"]


def _spindel(w: _Schreiber, n: float):
    w.s("G97", f"S{round(n)}", "M3")
    if w.e.kuehlung:
        w.s("M8")


# ================================================================ Geometrie lesen
@dataclass
class _Bohrung:
    d: float
    u: float                 # Lage in der Aufspannung (X)
    v: float                 # (Y)
    tiefe: float
    durch: bool


@dataclass
class _Geometrie:
    drehteil: bool
    lo: tuple
    hi: tuple
    mitte: tuple              # x, y der Drehachse bzw. Hüllbox
    volumen: float
    aussen: list = field(default_factory=list)      # [(d, z_von, z_bis)] Außenzylinder auf der Achse
    innen: list = field(default_factory=list)       # [(d, z_von, z_bis)] Bohrungen auf der Achse
    quer: list = field(default_factory=list)        # Zylinder quer zur Achse (Nuten)
    parallel: list = field(default_factory=list)    # [(achse, d, ort, von, bis)] achsparallele Innenzylinder
    form: object = None

    def innen_material(self, punkt) -> bool:
        """Liegt der Punkt im Werkstoff? (für Durchgangsbohrungen)"""
        if self.form is None:
            return True
        from OCP.BRepClass3d import BRepClass3d_SolidClassifier
        from OCP.TopAbs import TopAbs_OUT
        from OCP.gp import gp_Pnt
        return BRepClass3d_SolidClassifier(self.form, gp_Pnt(*map(float, punkt)), 1e-6).State() != TopAbs_OUT


def _geometrie(form) -> _Geometrie:
    from ..cad.geometrie import eigenschaften
    from ..cad.zeichnung import zylinder_flaechen
    e = eigenschaften(form)
    gx, gy, _ = e.groesse
    mx, my = (e.minimum[0] + e.maximum[0]) / 2, (e.minimum[1] + e.maximum[1]) / 2
    zyl = zylinder_flaechen(form)

    def auf_achse(c):
        return abs(abs(c.achse[2]) - 1) < 1e-6 and math.hypot(c.ort[0] - mx, c.ort[1] - my) < 1e-3
    aussen = [c for c in zyl if auf_achse(c) and not c.innen]
    d_max = 2 * max((c.radius for c in aussen), default=0.0)
    drehteil = bool(aussen) and abs(gx - gy) < 1e-3 and abs(d_max - gx) < 0.01 * gx
    g = _Geometrie(drehteil, tuple(e.minimum), tuple(e.maximum), (mx, my), e.volumen, form=form)
    for c in zyl:
        achse = next((i for i in range(3) if abs(abs(c.achse[i]) - 1) < 1e-6), None)
        if drehteil and auf_achse(c):
            ziel = g.innen if c.innen else g.aussen
            ziel.append((2 * c.radius, c.von, c.bis))
        elif drehteil and c.innen and abs(c.achse[2]) < 1e-6:
            g.quer.append(c)
        elif c.innen and achse is not None:
            vz = 1.0 if c.achse[achse] > 0 else -1.0       # Ausdehnung auf die positive Achsrichtung beziehen
            von, bis = sorted((vz * c.von, vz * c.bis))
            g.parallel.append((achse, 2 * c.radius, tuple(c.ort), von, bis))
    g.innen = _zusammenfassen(g.innen)
    return g


def _als_rohling(g: _Geometrie, plan: dict) -> _Geometrie | None:
    """Nicht rotationssymmetrisches Teil, das trotzdem gedreht wird (z. B. Zahnradrohling): Außen-Ø aus dem
    Arbeitsplan, Bohrungen auf der Achse aus der Geometrie."""
    gx, gy = g.hi[0] - g.lo[0], g.hi[1] - g.lo[1]
    if abs(gx - gy) > 0.02 * max(gx, gy):
        return None
    ziel = [db for v in plan.get("vorgaenge", []) if v.get("art") == "laengsdrehen"
            for dv, db, _ in v.get("p", {}).get("abschnitte", []) if dv > db]
    if not ziel:
        return None
    bohr = {round(float(v.get("p", {}).get("d", 0)), 1) for v in plan.get("vorgaenge", []) if v.get("art") == "bohren"}
    da = max(ziel)
    r = _Geometrie(True, (-da / 2, -da / 2, g.lo[2]), (da / 2, da / 2, g.hi[2]), (0.0, 0.0), g.volumen)
    r.aussen = [(da, g.lo[2], g.hi[2])]
    r.innen = _zusammenfassen([(d, von, bis) for achse, d, ort, von, bis in g.parallel
                               if achse == 2 and round(d, 1) in bohr and math.hypot(ort[0], ort[1]) < 1e-3])
    return r


def _zusammenfassen(bereiche: list) -> list:
    """Gleicher Ø, in mehrere Flächen geteilt (Nut, Naht) → ein Bereich."""
    out: dict = {}
    for d, a, b in bereiche:
        k = round(d, 3)
        a0, b0 = out.get(k, (a, b))
        out[k] = (min(a0, a), max(b0, b))
    return [(d, a, b) for d, (a, b) in sorted(out.items())]


# ================================================================ Drehen
def _profil(g: _Geometrie) -> list[tuple[float, float]]:
    """Außenkontur als Punkte (z, d) entlang der Achse; Lücken zwischen Zylindern = Fasen/Kegel (gerade Linie)."""
    pkt = []
    for d, a, b in sorted(g.aussen, key=lambda t: t[1]):
        if b - a > 1e-6:
            pkt += [(a, d), (b, d)]
    zmin, zmax = g.lo[2], g.hi[2]
    if pkt and pkt[0][0] > zmin + 1e-3:           # Fase zur Stirnseite unter 45° annehmen
        pkt.insert(0, (zmin, max(0.0, pkt[0][1] - 2 * (pkt[0][0] - zmin))))
    if pkt and pkt[-1][0] < zmax - 1e-3:
        pkt.append((zmax, max(0.0, pkt[-1][1] - 2 * (zmax - pkt[-1][0]))))
    return pkt


def _d_an(profil: list, z: float) -> float:
    for (z0, d0), (z1, d1) in zip(profil, profil[1:]):
        if z0 - 1e-9 <= z <= z1 + 1e-9:
            return d0 if z1 - z0 < 1e-9 else d0 + (d1 - d0) * (z - z0) / (z1 - z0)
    return 0.0


def _seite(profil: list, z_face: float, z_teil: float) -> list[tuple[float, float]]:
    """Kontur einer Aufspannung als (w, d): w = Abstand von der Stirnseite, bis zur Teilungsstelle z_teil."""
    richtung = -1 if z_face > z_teil else 1
    innen = [(abs(z - z_face), d) for z, d in profil if (z - z_teil) * richtung < -1e-9]
    innen.append((abs(z_teil - z_face), _d_an(profil, z_teil)))
    return sorted(innen)


def _huelle(kontur: list) -> tuple[list, bool]:
    """Vom Stirnende aus mit Längsdrehen erreichbare Kontur (Durchmesser nimmt nicht ab); True = Einstich."""
    out, d_max, einstich = [], 0.0, False
    for w, d in kontur:
        if d < d_max - 1e-6:
            einstich = True
            d = d_max
        d_max = max(d_max, d)
        out.append((w, d))
    return out, einstich


def _schnittlaenge(huelle: list, xp: float, w_ende: float) -> float:
    """Wie weit ein Schruppschnitt auf Ø xp vom Stirnende aus gehen darf, bevor er die Kontur berührt."""
    if not huelle or huelle[0][1] > xp + 1e-6:
        return 0.0
    for (w0, d0), (w1, d1) in zip(huelle, huelle[1:]):
        if d1 > xp + 1e-6:
            return w0 if d0 > xp - 1e-6 else w0 + (w1 - w0) * (xp - d0) / (d1 - d0)
    return w_ende


def _stufen(von: float, bis_liste: list[float], schritt: float) -> list[float]:
    """Schnittdurchmesser von `von` abwärts, jede Zielstufe wird genau getroffen, je Schnitt höchstens `schritt`."""
    out, cur = [], von
    for t in sorted(set(round(b, 4) for b in bis_liste), reverse=True):
        if t >= cur - 1e-6:
            continue
        n = max(1, math.ceil((cur - t) / schritt - 1e-9))
        out += [cur - k * (cur - t) / n for k in range(1, n + 1)]
        cur = t
    return out


def _drehen_seite(nr: int, g: _Geometrie, plan: dict, einst: Einstellungen, teil: str, rv: dict,
                  seite: str, z_teil: float, bohrungen: list, zentrieren: bool) -> Programm:
    roh = plan.get("rohteil", {})
    D = float(roh.get("d") or 0)
    zmin, zmax = g.lo[2], g.hi[2]
    laenge = zmax - zmin
    z_face = zmax if seite == "max" else zmin
    l_roh = float(roh.get("l") or roh.get("h") or laenge)
    stirn = max(0.0, (l_roh - laenge) / 2)          # Aufmaß je Stirnseite
    profil = _profil(g)
    kontur = _seite(profil, z_face, z_teil)
    huelle, einstich = _huelle(kontur)
    w_ende = abs(z_teil - z_face)
    a, ab = einst.aufmass, einst.sicherheitsabstand
    ap = einst.schnitttiefe

    titel = f"Drehen – Aufspannung {nr} (Stirnseite z = {_z(z_face)})"
    p = Programm(f"drehen_{nr}", titel, "Drehmaschine", "drehen",
                 f"Nullpunkt Mitte fertige Stirnfläche (z = {_z(z_face)} im Modell), Z negativ ins Werkstück, "
                 f"X als Durchmesser. Spannen am Rohteil auf der Gegenseite, Spannlänge bis "
                 f"Z{_z(-w_ende - 5)} frei" + (", mit Reitstock (Zentrierbohrung)" if zentrieren else "")
                 + ".")
    w = _Schreiber(einst, "drehen", titel, [
        f"Teil {teil}", f"Rohteil {S._f(D)} x {S._f(l_roh)} mm, Aufmass Stirnseite {S._f(stirn)} mm",
        "Nullpunkt: Mitte fertige Stirnflaeche, X = Durchmesser", "UNGEPRUEFT - VOR DEM EINSATZ SIMULIEREN"])
    gvu = w.vorschub_je_umdrehung()
    x_frei = D + 2 * ab
    d_bohr_min = 0.0         # Planen bis zur Mitte bzw. bis zur vorhandenen Bohrung
    for b in bohrungen:
        if b.get("vorhanden"):
            d_bohr_min = max(d_bohr_min, b["vorhanden"] - 2)

    # ---- Plandrehen und Schruppen (T1)
    w.k("T1 Schruppmeissel: Plandrehen und Laengsschruppen")
    w.s("T0101")
    p.werkzeuge.append("T0101 Schruppmeißel (z. B. CNMG, r = 0,8 mm) – Plandrehen und Längsschruppen")
    _spindel(w, S.drehzahl(rv["vc_d"], D, S.N_MAX_DREHEN))
    w.s(gvu)
    w.g0(x=x_frei, z=stirn + ab)
    if stirn > 1e-6:
        n_plan = max(1, math.ceil(stirn / min(2.0, ap) - 1e-9))
        for k in range(1, n_plan + 1):
            zp = stirn - k * stirn / n_plan
            w.g0(z=zp)
            w.g1(x=d_bohr_min - 1.6 if d_bohr_min <= 0 else d_bohr_min, f=rv["f_d"])
            w.g0(z=zp + ab)
            w.g0(x=x_frei)
    if zentrieren:            # vor dem Schruppen, damit der Reitstock mitträgt
        w.g0(x=x_frei, z=ab + 50)
        w.k("T3 Zentrierbohrer A4 DIN 333")
        w.s("T0303")
        p.werkzeuge.append("T0303 Zentrierbohrer A4 DIN 333 – Zentrierbohrung für den Reitstock")
        _spindel(w, S.drehzahl(rv["vc_b"], 4, S.N_MAX_DREHEN))
        w.g0(x=0, z=ab)
        w.g1(z=-8, f=0.05)
        w.g0(z=ab)
        w.g0(x=x_frei, z=ab + 50)
        w.s("M5")
        w.s("M0", "(Reitstock anstellen)")
        w.s("T0101")
        _spindel(w, S.drehzahl(rv["vc_d"], D, S.N_MAX_DREHEN))
        w.s(gvu)
    w.g0(x=x_frei, z=ab)
    ziele = [d + 2 * a for _, d in huelle]
    for xp in _stufen(D, ziele, 2 * ap):
        L = _schnittlaenge([(wi, d + 2 * a) for wi, d in huelle], xp, w_ende)
        if L <= 1e-6:
            continue
        w.g0(x=xp)
        w.g1(z=-L, f=rv["f_d"])
        w.g1(x=xp + 2)
        w.g0(z=ab)
    w.g0(x=x_frei, z=ab + 50)

    # ---- Bohren auf der Achse
    for b in bohrungen:
        if b.get("bohrer"):
            db, tiefe = b["bohrer"], b["tiefe"]
            f = min(0.4, max(0.05, 0.015 * db))
            w.k(f"T4 Spiralbohrer D{S._f(db)}")
            w.s("T0404")
            p.werkzeuge.append(f"T0404 Spiralbohrer Ø{S._f(db)} – Bohrung auf der Achse")
            _spindel(w, S.drehzahl(rv["vc_b"], db, S.N_MAX_DREHEN))
            _tiefbohren(w, 0.0, 0.0, -(tiefe + 0.3 * db + (1 if b["durch"] else 0)), max(2.0, db), f, ab,
                        achse="x")
            w.g0(x=x_frei, z=ab + 50)

    # ---- Ausdrehen (T5)
    for b in bohrungen:
        if b["d"] <= b.get("bohrer", 0) + 1e-6:
            continue
        start = b.get("bohrer") or b.get("vorhanden") or 0.0
        L = b["tiefe"] + (1 if b["durch"] else 0)
        w.k(f"T5 Bohrstange: Bohrung D{S._f(b['d'])} ausdrehen")
        w.s("T0505")
        p.werkzeuge.append(f"T0505 Bohrstange (Ausdrehen ab Ø{S._f(start)}) – Bohrung Ø{S._f(b['d'])}")
        if start < 16:
            p.warnungen.append(f"Bohrung Ø{S._f(b['d'])}: Vorbohrung Ø{S._f(start)} ist für eine Bohrstange knapp.")
        _spindel(w, S.drehzahl(rv["vc_d"], b["d"], S.N_MAX_DREHEN))
        w.s(gvu)
        w.g0(x=start - 1, z=ab)
        for xp in [-x for x in _stufen(-start, [-(b["d"] - 2 * a)], 2 * ap)] + [b["d"]]:
            w.g0(x=xp)
            w.g1(z=-L, f=rv["f_d"] if xp < b["d"] - 1e-6 else S.F_SCHLICHTEN)
            w.g1(x=xp - 1)
            w.g0(z=ab)
        w.g0(x=x_frei, z=ab + 50)

    # ---- Schlichten (T2) entlang der Kontur
    w.k("T2 Schlichtmeissel: Kontur schlichten")
    w.s("T0202")
    p.werkzeuge.append("T0202 Schlichtmeißel (z. B. VNMG, r = 0,4 mm) – Kontur schlichten")
    d_min = min((d for _, d in huelle), default=D) or D
    _spindel(w, S.drehzahl(rv["vc_d"] * 1.2, d_min, S.N_MAX_DREHEN))
    w.s(gvu)
    if huelle:
        w0, d0 = huelle[0]
        w.g0(x=d0, z=ab)
        w.g1(z=-w0, f=S.F_SCHLICHTEN)
        for wi, d in huelle[1:]:
            w.g1(x=d, z=-wi)
        w.g1(x=min(x_frei, huelle[-1][1] + 2))
    w.g0(x=x_frei, z=ab + 50)

    if einstich:
        p.warnungen.append("Die Kontur hat einen Einstich (Ø wird zur Mitte hin kleiner) – er ist nicht im Programm "
                           "und muss mit einem Stechmeißel ergänzt werden.")
    p.zeilen = w.fertig()
    rz = D / 2
    p.umrisse = [[(stirn, 0), (stirn, rz), (-w_ende, rz), (-w_ende, 0)],
                 [(0, 0)] + [(-wi, d / 2) for wi, d in kontur] + [(-w_ende, 0)]]
    for b in bohrungen:
        L = b["tiefe"]
        p.umrisse.append([(0, b["d"] / 2), (-L, b["d"] / 2)])
    return p


def _tiefbohren(w: _Schreiber, u: float, v: float, z_end: float, q: float, f: float, ab: float, achse: str):
    """Tiefbohren mit Entspänen, ausgeschrieben (keine Zyklen): je Hub q tiefer, dann ganz heraus."""
    if achse == "x":                       # Drehen: auf der Achse X0
        w.g0(x=0, z=ab)
    else:
        w.g0(x=u, y=v)
        w.g0(z=ab)
    tiefe = -z_end
    n = max(1, math.ceil(tiefe / q - 1e-9))
    for k in range(1, n + 1):
        zk = -min(tiefe, k * q)
        w.g1(z=zk, f=f)
        w.g0(z=ab)
        if k < n:
            w.g0(z=zk + 0.5)
    w.g0(z=ab)


def _drehen(g: _Geometrie, plan: dict, einst: Einstellungen, teil: str, rv: dict) -> list[Programm]:
    zmin, zmax = g.lo[2], g.hi[2]
    gross = max(g.aussen, key=lambda t: (t[0], t[2] - t[1]))
    z_teil = (gross[1] + gross[2]) / 2           # Teilung in der Mitte des größten Ø
    roh = plan.get("rohteil", {})
    D = float(roh.get("d") or 0)
    if D <= 0:
        raise CamFehler("Im Arbeitsplan fehlt der Rohteil-Durchmesser – bitte unter „Arbeitspläne“ eintragen.")
    if D < max(d for d, _, _ in g.aussen) - 1e-6:
        raise CamFehler(f"Das Rohteil Ø{S._f(D)} ist kleiner als das Teil – Rohteil im Arbeitsplan prüfen.")
    # Bohrungen auf der Achse: aus welcher Seite, womit (Regeln wie im Arbeitsplan: bis Ø30 bohren, sonst vorbohren)
    vorhanden = {}
    for v in plan.get("vorgaenge", []):
        if v.get("art") == "laengsdrehen":
            for dv, db, _ in v.get("p", {}).get("abschnitte", []):
                if dv < db:
                    vorhanden[round(db, 1)] = dv
    gebohrt = {round(float(v["p"].get("d", 0)), 1) for v in plan.get("vorgaenge", []) if v.get("art") == "bohren"}
    seiten = {"max": [], "min": []}
    warn = []
    for d, a, b in g.innen:
        durch = a <= zmin + 0.1 and b >= zmax - 0.1
        seite = "max" if b >= zmax - 0.1 else ("min" if a <= zmin + 0.1 else None)
        if seite is None:
            warn.append(f"Innenbereich Ø{S._f(d)} ist von keiner Stirnseite aus erreichbar – nicht im Programm.")
            continue
        eintrag = {"d": d, "tiefe": b - a, "durch": durch}
        vor = vorhanden.get(round(d, 1))
        if vor and round(vor, 1) not in gebohrt:
            eintrag["vorhanden"] = vor                    # z. B. vorgebrannte Ronde
        elif d <= BOHRER_MAX + 1e-6:
            eintrag["bohrer"] = d
        else:
            eintrag["bohrer"] = BOHRER_MAX
        seiten[seite].append(eintrag)
    lang = (zmax - zmin) / D > 4
    out = []
    for nr, seite in ((1, "max"), (2, "min")):
        bohr = sorted(seiten[seite], key=lambda b: -b["d"])
        p = _drehen_seite(nr, g, plan, einst, teil, rv, seite, z_teil, bohr, lang and not bohr)
        if nr == 1:
            p.warnungen = warn + p.warnungen
        if lang:
            p.warnungen.append(f"Schlankes Teil (L/D = {S._f((zmax - zmin) / D, 2)}): mit Reitstock spannen.")
        out.append(p)
    return out


# ================================================================ Fräsen
def _nuten(g: _Geometrie) -> list[dict]:
    """Passfedernuten aus den halben Querzylindern (je Nut zwei runde Enden mit gleichem Radius)."""
    gruppen: dict = {}
    for c in g.quer:
        radial = sorted(abs(t) for t in (c.von, c.bis))
        gruppen.setdefault((round(c.radius, 3), tuple(round(x, 3) for x in c.achse)), []).append((c.ort[2], radial[0]))
    profil = _profil(g)
    out = []
    for (r, achse), enden in gruppen.items():
        enden = sorted(set((round(z, 3), round(rad, 3)) for z, rad in enden))
        for (za, ra), (zb, rb) in zip(enden[0::2], enden[1::2]):
            if zb - za <= 0.5 * r:
                continue
            boden = min(ra, rb)
            r_welle = _d_an(profil, (za + zb) / 2) / 2
            bohr = [d / 2 for d, a, b in g.innen if a - 1e-6 <= za <= b + 1e-6]
            if bohr and boden < max(bohr) + 1e-3 or boden >= r_welle - 1e-3:
                out.append({"innen": True, "b": 2 * r, "za": za, "zb": zb})
                continue
            out.append({"innen": False, "b": 2 * r, "za": za, "zb": zb, "t": r_welle - boden, "r": r_welle,
                        "winkel": math.degrees(math.atan2(achse[1], achse[0]))})
    return out


def _fraesen_nut(nr: int, nuten: list, g: _Geometrie, einst: Einstellungen, teil: str, rv: dict) -> Programm:
    zmin = g.lo[2]
    titel = f"Fräsen – Passfedernut{'en' if len(nuten) > 1 else ''}"
    p = Programm(f"fraesen_nut_{nr}" if nr > 1 else "fraesen_nut", titel, "Fräsmaschine", "fraesen",
                 f"Welle waagerecht im Schraubstock bzw. in Prismen, Nut oben. Nullpunkt: X0 an der Stirnseite "
                 f"z = {_z(zmin)} im Modell, Y0 auf der Wellenachse, Z0 oben auf dem Wellendurchmesser an der Nut.")
    w = _Schreiber(einst, "fraesen", titel, [f"Teil {teil}", "Nullpunkt: X0 Stirnseite, Y0 Wellenachse, Z0 Oberkante",
                                             "UNGEPRUEFT - VOR DEM EINSATZ SIMULIEREN"])
    ab = einst.sicherheitsabstand
    l_ges = g.hi[2] - zmin
    p.umrisse = [[(0, -nuten[0]["r"]), (l_ges, -nuten[0]["r"]), (l_ges, nuten[0]["r"]), (0, nuten[0]["r"]),
                  (0, -nuten[0]["r"])]]
    tnr = 0
    for nut in sorted(nuten, key=lambda n: n["b"]):
        b = nut["b"]
        tnr += 1
        n = S.drehzahl(rv["vc_f"], b, S.N_MAX_FRAESEN)
        vf = round(rv["fz"] * S.ZAEHNE_FRAESER * n)
        w.k(f"Nut {S._f(b)} x {S._f(nut['zb'] - nut['za'] + b)}, Tiefe {S._f(nut['t'])}: Schaftfraeser D{S._f(b)}")
        w.s(f"T{tnr}", "M6")
        p.werkzeuge.append(f"T{tnr} Schaftfräser Ø{S._f(b)} (über Mitte schneidend) – Passfedernut {S._f(b)} mm")
        _spindel(w, n)
        xa, xb = nut["za"] - zmin, nut["zb"] - zmin
        w.g0(x=xa, y=0)
        w.g0(z=ab)
        schritte = max(1, math.ceil(nut["t"] / (0.5 * b) - 1e-9))
        x_ist = xa
        for k in range(1, schritte + 1):
            w.g1(z=-nut["t"] * k / schritte, f=round(vf / 2))
            x_ist = xb if x_ist == xa else xa
            w.g1(x=x_ist, f=vf)
        w.g0(z=ab + 50)
        p.umrisse.append([(xa, -b / 2), (xb, -b / 2), (xb, b / 2), (xa, b / 2), (xa, -b / 2)])
        if abs(nut["winkel"] - 90) > 1:
            p.warnungen.append(f"Nut {S._f(b)} mm liegt im Modell unter {S._f(nut['winkel'])}° – Welle so drehen, "
                               "dass die Nut oben liegt.")
    p.zeilen = w.fertig()
    return p


_ACHSEN = "xyz"
# Aufspannrichtung → (Index u, Vorzeichen u, Index v, Vorzeichen v): rechtshändig, Z der Maschine = Flächennormale
_UV = {(2, 1): (0, 1, 1, 1), (2, -1): (0, 1, 1, -1), (0, 1): (1, 1, 2, 1), (0, -1): (1, 1, 2, -1),
       (1, 1): (2, 1, 0, 1), (1, -1): (2, 1, 0, -1)}


def _bohrbilder(g: _Geometrie) -> tuple[dict, list[str]]:
    """Achsparallele Bohrungen je Aufspannung (Achse, Seite) in Maschinenkoordinaten u, v."""
    roh: dict = {}
    for achse, d, ort, von, bis in g.parallel:
        andere = [i for i in range(3) if i != achse]
        k = (achse, round(d, 2), round(ort[andere[0]], 1), round(ort[andere[1]], 1))
        a0, b0 = roh.get(k, (von, bis))[:2]
        roh[k] = (min(a0, von), max(b0, bis), ort)
    gruppen: dict = {}
    warn = []
    for (achse, d, _, _), (von, bis, ort) in sorted(roh.items()):
        lo, hi = g.lo[achse], g.hi[achse]
        if bis >= hi - 0.1:
            seite = 1
        elif von <= lo + 0.1:
            seite = -1
        else:
            warn.append(f"Bohrung Ø{S._f(d)} beginnt an keiner Außenfläche – nicht im Programm.")
            continue
        if d > BOHRER_MAX + 1e-6:
            warn.append(f"Bohrung/Ausschnitt Ø{S._f(d)} ist zu groß für einen Bohrer – nach Zeichnung fräsen "
                        "(nicht im Programm).")
            continue
        iu, su, iv, sv = _UV[(achse, seite)]
        u0, v0 = _ursprung(g, iu, su), _ursprung(g, iv, sv)
        u, v = su * ort[iu] - u0, sv * ort[iv] - v0
        unten = list(ort)
        unten[achse] = (von - 0.5) if seite > 0 else (bis + 0.5)   # 0,5 mm hinter dem Bohrungsgrund
        durch = not g.innen_material(unten)
        gruppen.setdefault((achse, seite), []).append(_Bohrung(d, u, v, bis - von, durch))
    return gruppen, warn


def _ursprung(g: _Geometrie, i: int, s: int) -> float:
    """Nullpunkt einer Maschinenachse: Drehachse (Drehteil) bzw. kleinster Wert der Hüllbox."""
    if g.drehteil:
        return s * (g.mitte[i] if i < 2 else 0.0)
    return min(s * g.lo[i], s * g.hi[i])


def _sortieren(bohrungen: list[_Bohrung], drehteil: bool) -> list[_Bohrung]:
    if drehteil:      # Lochkreis: im Uhrzeigersinn ab 12 Uhr ist für den Bediener leicht nachzuvollziehen
        return sorted(bohrungen, key=lambda b: (round(b.d, 2), -math.atan2(b.u, b.v) % (2 * math.pi)))
    reihen: dict = {}
    for b in bohrungen:
        reihen.setdefault(round(b.v, 1), []).append(b)
    out = []
    for i, v in enumerate(sorted(reihen)):                   # Mäander: Reihe hin, nächste Reihe zurück
        out += sorted(reihen[v], key=lambda b: b.u, reverse=bool(i % 2))
    return sorted(out, key=lambda b: round(b.d, 2))


def _fraesen_bohren(nr: int, achse: int, seite: int, bohrungen: list, g: _Geometrie, einst: Einstellungen,
                    teil: str, rv: dict) -> Programm:
    flaeche = f"{'+' if seite > 0 else '-'}{_ACHSEN[achse]}"
    iu, su, iv, sv = _UV[(achse, seite)]
    titel = f"Bohren – Bohrbild von {flaeche} ({len(bohrungen)} Bohrungen)"
    null = "Drehachse" if g.drehteil else "Ecke der Hüllbox"
    p = Programm(f"bohren_{nr}", titel, "Fräsmaschine", "fraesen",
                 f"Fläche {flaeche} nach oben spannen. Nullpunkt X/Y: {null}, Z0 auf der Fläche "
                 f"({_ACHSEN[achse]} = {_z(g.hi[achse] if seite > 0 else g.lo[achse])} im Modell). "
                 f"X entspricht {'+' if su > 0 else '-'}{_ACHSEN[iu]}, Y entspricht {'+' if sv > 0 else '-'}"
                 f"{_ACHSEN[iv]} des Modells.")
    w = _Schreiber(einst, "fraesen", titel, [f"Teil {teil}", f"Nullpunkt: {null}, Z0 auf der Flaeche {flaeche}",
                                             "UNGEPRUEFT - VOR DEM EINSATZ SIMULIEREN"])
    ab = einst.sicherheitsabstand
    bohrungen = _sortieren(bohrungen, g.drehteil)
    # Anbohren aller Bohrungen
    w.k(f"T1 NC-Anbohrer D{S._f(ANBOHREN_D)} 90 Grad")
    w.s("T1", "M6")
    p.werkzeuge.append(f"T1 NC-Anbohrer Ø{S._f(ANBOHREN_D)} 90° – Anbohren")
    n = S.drehzahl(rv["vc_b"], ANBOHREN_D, S.N_MAX_FRAESEN)
    _spindel(w, n)
    w.g0(x=bohrungen[0].u, y=bohrungen[0].v)
    w.g0(z=ab)
    for b in bohrungen:
        tiefe = min(b.d, ANBOHREN_D) / 2 + 0.2
        w.g0(x=b.u, y=b.v)
        w.g1(z=-tiefe, f=round(0.1 * n))
        w.g0(z=ab)
    w.g0(z=ab + 50)
    tnr = 1
    for d in sorted({round(b.d, 2) for b in bohrungen}):
        tnr += 1
        f = min(0.4, max(0.05, 0.015 * d))
        n = S.drehzahl(rv["vc_b"], d, S.N_MAX_FRAESEN)
        w.k(f"T{tnr} Spiralbohrer D{S._f(d)}")
        w.s(f"T{tnr}", "M6")
        auswahl = [b for b in bohrungen if round(b.d, 2) == d]
        p.werkzeuge.append(f"T{tnr} Spiralbohrer Ø{S._f(d)} – {len(auswahl)} Bohrung(en)")
        _spindel(w, n)
        w.g0(x=auswahl[0].u, y=auswahl[0].v)
        w.g0(z=ab)
        for b in auswahl:
            z_end = -(b.tiefe + 0.3 * d + (1 if b.durch else 0))
            _tiefbohren(w, b.u, b.v, z_end, max(2.0, d), round(f * n), ab, achse="z")
        w.g0(z=ab + 50)
    p.zeilen = w.fertig()
    # Umrisse: Teilefläche in u, v
    if g.drehteil:
        r = (g.hi[0] - g.lo[0]) / 2
        p.umrisse = [[(r * math.cos(t / 36 * math.pi), r * math.sin(t / 36 * math.pi)) for t in range(73)]]
    else:
        lu, lv = g.hi[iu] - g.lo[iu], g.hi[iv] - g.lo[iv]
        p.umrisse = [[(0, 0), (lu, 0), (lu, lv), (0, lv), (0, 0)]]
    for b in bohrungen:
        p.umrisse.append([(b.u + b.d / 2 * math.cos(t / 12 * math.pi), b.v + b.d / 2 * math.sin(t / 12 * math.pi))
                          for t in range(25)])
    return p


def _fraesen_kontur(g: _Geometrie, plan: dict, einst: Einstellungen, teil: str, rv: dict) -> Programm:
    groesse = [g.hi[i] - g.lo[i] for i in range(3)]
    achse = groesse.index(min(groesse))
    iu, su, iv, sv = _UV[(achse, 1)]
    lu, lv, h = groesse[iu], groesse[iv], groesse[achse]
    d = FRAESER_KONTUR
    r = d / 2
    titel = "Fräsen – Außenkontur (Rechteck)"
    p = Programm("fraesen_kontur", titel, "Fräsmaschine", "fraesen",
                 f"Rohteil auf Parallelunterlagen spannen (Fräser fährt {_z(h + 0.5)} mm tief – Unterlagen innen "
                 f"freistellen). Nullpunkt X/Y: Ecke des Fertigteils, Z0 auf der Oberseite (+{_ACHSEN[achse]}).")
    w = _Schreiber(einst, "fraesen", titel, [f"Teil {teil}", f"Fertigmass {S._f(lu)} x {S._f(lv)} x {S._f(h)}",
                                             "Fraeserradius im Weg enthalten [keine G41/G42]",
                                             "UNGEPRUEFT - VOR DEM EINSATZ SIMULIEREN"])
    ab = einst.sicherheitsabstand
    n = S.drehzahl(rv["vc_f"], d, S.N_MAX_FRAESEN)
    vf = round(rv["fz"] * S.ZAEHNE_FRAESER * n)
    w.k(f"T1 Schaftfraeser D{S._f(d)}")
    w.s("T1", "M6")
    p.werkzeuge.append(f"T1 Schaftfräser Ø{S._f(d)}, z = {S.ZAEHNE_FRAESER} – Außenkontur")
    _spindel(w, n)
    ecken = [(-r, -r), (-r, lv + r), (lu + r, lv + r), (lu + r, -r), (-r, -r)]   # Gleichlauf außen
    w.g0(x=-r - ab - r, y=-r)
    w.g0(z=ab)
    schritte = max(1, math.ceil((h + 0.5) / (0.5 * d) - 1e-9))
    for k in range(1, schritte + 1):
        w.g1(z=-(h + 0.5) * k / schritte, f=round(vf / 2))
        for x, y in ecken:
            w.g1(x=x, y=y, f=vf)
        w.g1(x=-r - ab - r, y=-r)
    w.g0(z=ab + 50)
    p.zeilen = w.fertig()
    roh = plan.get("rohteil", {})
    ru, rv_ = float(roh.get("l") or lu), float(roh.get("b") or lv)
    if ru < rv_ and lu > lv:
        ru, rv_ = rv_, ru
    au, av = (ru - lu) / 2, (rv_ - lv) / 2
    p.umrisse = [[(-au, -av), (lu + au, -av), (lu + au, lv + av), (-au, lv + av), (-au, -av)],
                 [(0, 0), (lu, 0), (lu, lv), (0, lv), (0, 0)]]
    return p


# ================================================================ Einstieg
def erzeugen(form, plan: dict, einst: Einstellungen | dict | None = None, teil: str = "") -> list[Programm]:
    """NC-Programme für ein Bauteil aus Geometrie und Arbeitsplan. Leere Liste: nichts zu zerspanen."""
    einst = einst if isinstance(einst, Einstellungen) else Einstellungen.aus_dict(einst)
    einst.pruefen()
    from .arbeitsplan import gruppe
    roh = plan.get("rohteil", {})
    werkstoff = roh.get("werkstoff", "")
    try:
        rv = S.richtwerte(gruppe(werkstoff))
    except S.SchnittFehler as exc:
        raise CamFehler(f"Für den Werkstoff „{werkstoff.split(' · ')[0] or '–'}“ gibt es keine Schnittwerte "
                        "(Faserverbund oder unbekannt) – kein G-Code möglich.") from exc
    arten = {v.get("art") for v in plan.get("vorgaenge", [])}
    g = _geometrie(form)
    out: list[Programm] = []
    rohling = None
    if not g.drehteil and arten & {"plandrehen", "laengsdrehen"}:
        rohling = _als_rohling(g, plan)
    if (g.drehteil or rohling) and arten & {"plandrehen", "laengsdrehen"}:
        out += _drehen(rohling or g, plan, einst, teil, rv)
        if rohling:
            out[0].warnungen.append("Gedreht wird nur der Rohling (Kopfkreis, Stirnseiten, Bohrung) aus dem "
                                    "Arbeitsplan – die Verzahnung ist nicht im Programm.")
    nuten = _nuten(g) if g.drehteil else []
    aussen_nuten = [n for n in nuten if not n["innen"]]
    if aussen_nuten and "fraesen" in arten:
        out.append(_fraesen_nut(1, aussen_nuten, g, einst, teil, rv))
    warnungen = [f"Nabennut {S._f(n['b'])} mm in der Bohrung wird gestoßen oder geräumt – nicht im Programm."
                 for n in nuten if n["innen"]]
    if not g.drehteil and "fraesen" in arten:
        loch_vol = sum(math.pi / 4 * d ** 2 * (bis - von) for _, d, _, von, bis in g.parallel)
        box = math.prod(g.hi[i] - g.lo[i] for i in range(3))
        if g.volumen + loch_vol >= 0.97 * box:
            out.append(_fraesen_kontur(g, plan, einst, teil, rv))
        else:
            warnungen.append("Das Teil ist nicht plattenförmig – die Fräskontur bitte im CAM-System der Werkstatt "
                             "programmieren; hier nur die Bohrungen.")
    if "bohren" in arten:
        gruppen, warn = _bohrbilder(g)
        warnungen += warn
        for i, ((achse, seite), bohr) in enumerate(sorted(gruppen.items(), key=lambda t: (-t[0][1], t[0][0]))):
            out.append(_fraesen_bohren(i + 1, achse, seite, bohr, g, einst, teil, rv))
    if out:
        out[0].warnungen = warnungen + out[0].warnungen
    if einst.dialekt == "fanuc":             # fortlaufende Programmnummern
        for i, p in enumerate(out):
            p.zeilen[1] = re.sub(r"^O\d+", f"O{einst.programmnummer + i:04d}", p.zeilen[1])
    return out


def exportieren(programme: list[Programm], ordner, teil_nr: str) -> list[Path]:
    ordner = Path(ordner)
    ordner.mkdir(parents=True, exist_ok=True)
    pfade = []
    for p in programme:
        ziel = ordner / p.dateiname(teil_nr)
        ziel.write_text(p.text, encoding="ascii", newline="\n")
        pfade.append(ziel)
    return pfade


# ================================================================ Prüfen (eigener kleiner Leser)
@dataclass
class Pruefung:
    fehler: list[str] = field(default_factory=list)
    hinweise: list[str] = field(default_factory=list)
    segmente: list[Segment] = field(default_factory=list)
    weg_eilgang: float = 0.0
    weg_vorschub: float = 0.0
    zeit: float = 0.0                 # Hauptzeit min (nur Vorschubwege)
    zeit_eilgang: float = 0.0
    bereich: tuple = (0.0, 0.0, 0.0, 0.0)
    werkzeugwechsel: int = 0

    @property
    def ok(self) -> bool:
        return not self.fehler


_WORT = re.compile(r"([A-Z])\s*([-+]?(?:\d+\.?\d*|\.\d+))")
_BEKANNT_G = {0, 1, 7, 8, 17, 18, 19, 21, 40, 49, 54, 80, 90, 94, 95, 96, 97, 98, 99}
_BEKANNT_M = {0, 1, 2, 3, 4, 5, 6, 8, 9, 30}


def pruefen(text: str, art: str) -> Pruefung:
    """G-Code lesen und auf typische Fehler prüfen. art: "drehen" (X = Ø, Z) oder "fraesen" (X, Y, Z)."""
    p = Pruefung()
    pos = {"X": None, "Y": 0.0 if art == "drehen" else None, "Z": None}
    modal, f, s, spindel, je_umdrehung, ende = None, None, 0.0, False, False, False
    frei: dict = {}          # (X, Y) → tiefstes Z, das per Vorschub schon frei geschnitten ist
    a_min = b_min = math.inf
    a_max = b_max = -math.inf
    for nr, roh in enumerate(text.splitlines(), 1):
        zeile = re.sub(r"\([^)]*\)", "", roh.split(";")[0]).strip().upper()
        if not zeile or zeile == "%" or zeile.startswith("O"):
            continue
        if ende:
            p.hinweise.append(f"Zeile {nr}: Sätze nach dem Programmende werden nicht ausgeführt.")
            break
        woerter = _WORT.findall(zeile)
        rest = _WORT.sub("", zeile).strip()
        if rest:
            p.fehler.append(f"Zeile {nr}: „{rest}“ ist kein gültiges Wort.")
        ziel = dict(pos)
        bewegt = False
        for buchst, wert in woerter:
            zahl = float(wert)
            if buchst == "G":
                gz = int(zahl)
                if gz in (0, 1):
                    modal = gz
                elif gz == 91:
                    p.fehler.append(f"Zeile {nr}: G91 (Kettenmaß) wird hier nicht unterstützt – nur G90.")
                elif gz == 20:
                    p.fehler.append(f"Zeile {nr}: G20 (Zoll) – das Programm ist in mm (G21) gedacht.")
                elif gz in (95, 99) and art == "drehen":
                    je_umdrehung = True
                elif gz in (94, 98):
                    je_umdrehung = False
                elif gz in (2, 3):
                    p.fehler.append(f"Zeile {nr}: Kreisbogen G{gz} wird vom Prüfer nicht ausgewertet.")
                elif gz not in _BEKANNT_G:
                    p.hinweise.append(f"Zeile {nr}: G{gz} ist dem Prüfer unbekannt.")
            elif buchst == "M":
                mz = int(zahl)
                if mz in (3, 4):
                    if s <= 0:
                        p.fehler.append(f"Zeile {nr}: Spindel ein ohne Drehzahl S.")
                    spindel = True
                elif mz == 5:
                    spindel = False
                elif mz == 6:
                    p.werkzeugwechsel += 1
                elif mz in (2, 30):
                    ende = True
                elif mz not in _BEKANNT_M:
                    p.hinweise.append(f"Zeile {nr}: M{mz} ist dem Prüfer unbekannt.")
            elif buchst == "S":
                s = zahl
            elif buchst == "F":
                f = zahl
            elif buchst == "T":
                if art == "drehen":
                    p.werkzeugwechsel += 1
            elif buchst in "XYZ":
                ziel[buchst] = zahl
                bewegt = True
            elif buchst not in "N":
                p.hinweise.append(f"Zeile {nr}: Adresse {buchst} ist dem Prüfer unbekannt.")
        if not bewegt:
            continue
        if modal is None:
            p.fehler.append(f"Zeile {nr}: Bewegung ohne G0/G1.")
            modal = 0
        if None in (pos["X"], pos["Z"]) or (art != "drehen" and pos["Y"] is None):
            if modal == 1:
                p.fehler.append(f"Zeile {nr}: Vorschub-Bewegung, bevor die Startlage bekannt ist.")
            pos = {k: (v if v is not None else ziel.get(k)) for k, v in pos.items()}
            pos.update({k: v for k, v in ziel.items() if v is not None})
            continue
        if art == "drehen":
            d = math.hypot((ziel["X"] - pos["X"]) / 2, ziel["Z"] - pos["Z"])
            seg = Segment(pos["Z"], pos["X"] / 2, ziel["Z"], ziel["X"] / 2, modal == 0)
            if ziel["X"] < -2.0:
                p.fehler.append(f"Zeile {nr}: X{_z(ziel['X'])} liegt weit hinter der Drehmitte.")
        else:
            d = math.dist((pos["X"], pos["Y"], pos["Z"]), (ziel["X"], ziel["Y"], ziel["Z"]))
            seg = Segment(pos["X"], pos["Y"], ziel["X"], ziel["Y"], modal == 0)
            if modal == 0 and min(pos["Z"], ziel["Z"]) < -1e-6 and \
                    (abs(ziel["X"] - pos["X"]) > 1e-6 or abs(ziel["Y"] - pos["Y"]) > 1e-6):
                p.fehler.append(f"Zeile {nr}: Eilgang seitlich unterhalb Z0 – Kollisionsgefahr im Werkstück.")
            schon = frei.get((round(ziel["X"], 2), round(ziel["Y"], 2)), 0.0)
            if modal == 0 and ziel["Z"] < pos["Z"] - 1e-6 and ziel["Z"] < schon - 1e-6:
                p.fehler.append(f"Zeile {nr}: Eilgang nach unten ins Werkstück (Z{_z(ziel['Z'])}).")
        if modal == 1 and art != "drehen" and abs(ziel["X"] - pos["X"]) < 1e-9 and abs(ziel["Y"] - pos["Y"]) < 1e-9:
            k = (round(ziel["X"], 2), round(ziel["Y"], 2))
            frei[k] = min(frei.get(k, 0.0), ziel["Z"])
        if modal == 1:
            if not f:
                p.fehler.append(f"Zeile {nr}: Vorschub-Bewegung ohne Vorschub F.")
            elif not spindel:
                p.fehler.append(f"Zeile {nr}: Schnitt bei stehender Spindel.")
            else:
                vf = f * s if je_umdrehung else f
                p.zeit += d / vf if vf > 0 else 0.0
            p.weg_vorschub += d
        else:
            p.weg_eilgang += d
        if d > 1e-9:
            p.segmente.append(seg)
            for a, b in ((seg.a0, seg.b0), (seg.a1, seg.b1)):
                a_min, a_max, b_min, b_max = min(a_min, a), max(a_max, a), min(b_min, b), max(b_max, b)
        pos = ziel
    if not ende:
        p.fehler.append("Das Programmende M30 (oder M2) fehlt.")
    p.zeit_eilgang = p.weg_eilgang / EILGANG
    if p.segmente:
        p.bereich = (a_min, b_min, a_max, b_max)
    # Fehler je Zeile nur einmal, höchstens 20 zeigen
    p.fehler = list(dict.fromkeys(p.fehler))[:20]
    p.hinweise = list(dict.fromkeys(p.hinweise))[:20]
    return p
