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
            if not hasattr(e, k):
                continue
            if isinstance(getattr(e, k), bool):
                v = v.strip().lower() in ("1", "true", "ja", "wahr") if isinstance(v, str) else bool(v)
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
    rohteil_d: float | None = None          # Drehen: Rohteil-Ø für die Eilgang-Prüfung

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
        if woerter and woerter[0] in ("G94", "G95", "G98", "G99"):
            self.f_alt = None           # nach Wechsel der Vorschubart F neu setzen
        self.saetze.append(" ".join(w for w in woerter if w))

    def werkzeug(self, nr: int):
        """Werkzeugwechsel je Steuerung, mit Längen- bzw. Schneidenkorrektur."""
        self.f_alt = None
        d = self.e.dialekt
        if self.art == "drehen":
            if d == "fanuc":
                self.s(f"T{nr:02d}{nr:02d}")
            elif d == "linuxcnc":
                self.s(f"T{nr}", "M6", "G43")
            else:
                self.s(f"T{nr}", "D1")
        else:
            self.s(f"T{nr}", "M6")
            self.s(f"G43 H{nr}" if d in ("fanuc", "linuxcnc") else "D1")

    def vorschub_je_umdrehung(self) -> str:
        return "G99" if self.e.dialekt == "fanuc" else "G95"

    def vorschub_je_minute(self) -> str:
        return "G98" if self.e.dialekt == "fanuc" and self.art == "drehen" else "G94"

    def fertig(self) -> list[str]:
        e = self.e
        if e.dialekt == "fanuc":
            titel = _ascii(self.titel)
            if len(titel) > 40:
                titel = titel[:40].rsplit(" ", 1)[0]
            anfang = ["%", f"O{e.programmnummer:04d} ({titel})"]
        else:
            anfang = ["%", f"({_ascii(self.titel)})"]
        kopf = [f"({_ascii(t)})" for t in self.kopf]
        if self.art == "drehen":
            # Fanuc-Drehen (System A): G90 wäre der Längsdrehzyklus – absolut ist dort schon die Adresse X/Z
            grund = ["G18 G21 G40 G80" + {"fanuc": "", "linuxcnc": " G90 G7"}.get(e.dialekt, " G90")]
        else:
            grund = ["G17 G21 G40 G49 G80 G90 G94", "G54"]
        ende = ["M5", "M9", "M30"]
        rumpf = kopf + grund + self.saetze + ende
        if e.dialekt == "din":
            rumpf = [f"N{10 * (i + 1)} {z}" for i, z in enumerate(rumpf)]
        return anfang + rumpf + ["%"]


def _spindel(w: _Schreiber, n: float):
    if w.art == "drehen":
        w.s("G97", f"S{round(n)}", "M3")
    else:
        w.s(f"S{round(n)}", "M3")
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
    flaeche: float = 0.0     # Lage der Anbohrfläche entlang der Flächennormalen (Modell)
    spitze_frei: bool = False


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
    da = max(ziel)
    flaechen: dict = {}            # Achsbohrung = höchstens zwei Flächen; Zahnfuß-Stücke sind viele gleiche Flächen
    for achse, d, ort, _, _ in g.parallel:
        if achse == 2 and math.hypot(ort[0] - g.mitte[0], ort[1] - g.mitte[1]) < 0.5:
            flaechen[round(d, 1)] = flaechen.get(round(d, 1), 0) + 1
    bohr = {d for d, n in flaechen.items() if n <= 2 and d < 0.9 * da}
    r = _Geometrie(True, (-da / 2, -da / 2, g.lo[2]), (da / 2, da / 2, g.hi[2]), (0.0, 0.0), g.volumen)
    r.aussen = [(da, g.lo[2], g.hi[2])]
    r.innen = _zusammenfassen([(d, von, bis) for achse, d, ort, von, bis in g.parallel
                               if achse == 2 and round(d, 1) in bohr
                               and math.hypot(ort[0] - g.mitte[0], ort[1] - g.mitte[1]) < 0.5])
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
def _radius_an(g: _Geometrie, z: float, r_min: float, r_max: float) -> float:
    """Äußerer Radius des Teils an der Stelle z, abgetastet im Volumenmodell (größter Wert aus zwei Richtungen)."""
    if g.form is None:
        return r_max
    mx, my = g.mitte
    best = r_min
    for ux, uy in ((-1.0, 0.0), (0.0, -1.0)):
        lo, hi = r_min, r_max
        if not g.innen_material((mx + ux * (lo + 1e-4), my + uy * (lo + 1e-4), z)):
            continue
        while hi - lo > 0.005:                      # Halbierung auf 0,005 mm genau
            m = (lo + hi) / 2
            if g.innen_material((mx + ux * m, my + uy * m, z)):
                lo = m
            else:
                hi = m
        best = max(best, lo)
    return best


def _profil(g: _Geometrie) -> list[tuple[float, float]]:
    """Außenkontur als Punkte (z, d) entlang der Achse. Zwischen den Zylindern (Planschultern, Fasen, Kegel) und an
    den Stirnseiten wird der Radius im Volumenmodell abgetastet – so bleibt eine Schulter eine Planfläche."""
    zyl = [(a, b, d) for d, a, b in sorted(g.aussen, key=lambda t: t[1]) if b - a > 1e-6]
    if not zyl:
        return []
    zmin, zmax = g.lo[2], g.hi[2]
    pkt: list = []

    def luecke(z0: float, z1: float, d_lo: float, d_hi: float):
        if z1 - z0 < 1e-3:
            return
        eps = min(1e-3, (z1 - z0) / 10)
        r_lo = max(0.0, d_lo / 2 - (z1 - z0) * 3 - 1)    # Fasen und Kegel bleiben nahe am kleineren Ø
        for k in range(4):
            z = z0 + eps + (z1 - z0 - 2 * eps) * k / 3
            d = 2 * _radius_an(g, z, r_lo, d_hi / 2 + 0.01)
            d = next((dz for dz in (d_lo, d_hi) if abs(d - dz) < 0.05), d)   # Abtastrauschen am Zylinder
            pkt.append((round(z, 3), round(d, 2)))

    luecke(zmin, zyl[0][0], zyl[0][2], zyl[0][2])
    for i, (a, b, d) in enumerate(zyl):
        pkt += [(a, d), (b, d)]
        if i + 1 < len(zyl):
            luecke(b, zyl[i + 1][0], min(d, zyl[i + 1][2]), max(d, zyl[i + 1][2]))
    luecke(zyl[-1][1], zmax, zyl[-1][2], zyl[-1][2])
    if g.form is None or not pkt:
        return pkt
    if pkt[0][0] > zmin + 1e-6:
        pkt.insert(0, (zmin, pkt[0][1]))
    if pkt[-1][0] < zmax - 1e-6:
        pkt.append((zmax, pkt[-1][1]))
    return _vereinfachen(pkt)


def _vereinfachen(pkt: list) -> list:
    """Punkte auf einer Geraden zusammenfassen (Abtastung einer Fase ergibt sonst viele Sätze)."""
    out = [pkt[0]]
    for i in range(1, len(pkt) - 1):
        (z0, d0), (z1, d1), (z2, d2) = out[-1], pkt[i], pkt[i + 1]
        kreuz = (z1 - z0) * (d2 - d0) - (d1 - d0) * (z2 - z0)
        laenge = math.hypot(z2 - z0, d2 - d0) or 1.0
        if abs(kreuz) / laenge > 0.02:
            out.append((round(z1, 3), round(d1, 3)))
    out.append(pkt[-1])
    return out


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
        if d < d_max - 0.05:                      # Abtastgenauigkeit des Profils
            einstich = True
            d = d_max
        elif d < d_max:
            d = d_max
        d_max = max(d_max, d)
        out.append((w, d))
    return out, einstich


def _schnittlaenge(huelle: list, xp: float, w_ende: float, axial: float = 0.0) -> float:
    """Wie weit ein Schruppschnitt auf Ø xp vom Stirnende aus gehen darf, bevor er die Kontur berührt;
    vor einer Schulter bleibt das axiale Schlichtaufmaß stehen."""
    if not huelle or huelle[0][1] > xp + 1e-6:
        return 0.0
    for (w0, d0), (w1, d1) in zip(huelle, huelle[1:]):
        if d1 > xp + 1e-6:
            L = w0 if d0 > xp - 1e-6 else w0 + (w1 - w0) * (xp - d0) / (d1 - d0)
            return max(0.0, L - axial)
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
                  seite: str, z_teil: float, bohrungen: list, zentrieren: bool, vorgebohrt: float = 0.0) -> Programm:
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
                 + f". Werkzeugwechsel bei X{_z(D + 2 * einst.sicherheitsabstand)} Z{_z(einst.sicherheitsabstand + 50)} "
                 "(bezogen auf den Nullpunkt) – prüfen, ob der Revolver dort frei schwenkt, sonst anpassen.",
                 rohteil_d=D)
    w = _Schreiber(einst, "drehen", titel, [
        f"Teil {teil}", f"Rohteil {S._f(D)} x {S._f(l_roh)} mm, Aufmass Stirnseite {S._f(stirn)} mm",
        "Nullpunkt: Mitte fertige Stirnflaeche, X = Durchmesser", "UNGEPRUEFT - VOR DEM EINSATZ SIMULIEREN"])
    gvu = w.vorschub_je_umdrehung()
    x_frei = D + 2 * ab
    d_bohr_min = max(0.0, vorgebohrt - 2)   # Planen bis zur Mitte bzw. bis zur vorhandenen Bohrung
    for b in bohrungen:
        if b.get("vorhanden"):
            d_bohr_min = max(d_bohr_min, b["vorhanden"] - 2)

    # ---- Plandrehen und Schruppen (T1)
    w.k("T1 Schruppmeissel: Plandrehen und Laengsschruppen")
    w.werkzeug(1)
    p.werkzeuge.append("T1 Schruppmeißel (z. B. CNMG, r = 0,8 mm) – Plandrehen und Längsschruppen")
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
        w.werkzeug(3)
        p.werkzeuge.append("T3 Zentrierbohrer A4 DIN 333 – Zentrierbohrung für den Reitstock")
        _spindel(w, S.drehzahl(rv["vc_b"], 4, S.N_MAX_DREHEN))
        w.g0(x=0, z=ab)
        w.g1(z=-8, f=0.05)
        w.g0(z=ab)
        w.g0(x=x_frei, z=ab + 50)
        w.s("M5")
        w.s("M9")
        w.s("M0", "(Reitstock anstellen)")
        w.werkzeug(1)
        _spindel(w, S.drehzahl(rv["vc_d"], D, S.N_MAX_DREHEN))
        w.s(gvu)
    w.g0(x=x_frei, z=ab)
    # Schnittstufen nur auf zylindrischen Abschnitten (waagerechte Stücke der Kontur), nicht auf Fasenpunkten
    ziele = [d0 + 2 * a for (_, d0), (_, d1) in zip(huelle, huelle[1:]) if abs(d1 - d0) < 1e-6] or \
        [d + 2 * a for _, d in huelle]
    for xp in _stufen(D, ziele, 2 * ap):
        L = _schnittlaenge([(wi, d + 2 * a) for wi, d in huelle], xp, w_ende, a)
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
            w.werkzeug(4)
            p.werkzeuge.append(f"T4 Spiralbohrer Ø{S._f(db)} – Bohrung auf der Achse")
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
        w.werkzeug(5)
        p.werkzeuge.append(f"T5 Bohrstange (Ausdrehen ab Ø{S._f(start)}) – Bohrung Ø{S._f(b['d'])}")
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
    w.werkzeug(2)
    p.werkzeuge.append("T2 Schlichtmeißel (z. B. VNMG, r = 0,4 mm) – Kontur schlichten")
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


def _tiefbohren(w: _Schreiber, u: float, v: float, z_end: float, q: float, f: float, ab: float, achse: str,
                oben: float = 0.0):
    """Tiefbohren mit Entspänen, ausgeschrieben (keine Zyklen): je Hub q tiefer, dann ganz heraus.
    z_end zählt ab der Anbohrfläche, die bei Z = oben liegt."""
    if achse == "x":                       # Drehen: auf der Achse X0
        w.g0(x=0, z=ab)
    else:
        w.g0(x=u, y=v)
        w.g0(z=oben + ab)
    tiefe = -z_end
    n = max(1, math.ceil(tiefe / q - 1e-9))
    for k in range(1, n + 1):
        zk = oben - min(tiefe, k * q)
        w.g1(z=zk, f=f)
        w.g0(z=oben + ab)
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
        durch = max((b["d"] for b in seiten["max"] if b["durch"]), default=0.0) if nr == 2 else 0.0
        p = _drehen_seite(nr, g, plan, einst, teil, rv, seite, z_teil, bohr, lang and not bohr and not durch, durch)
        if nr == 1:
            p.warnungen = warn + p.warnungen
        if lang:
            p.warnungen.append(f"Schlankes Teil (L/D = {S._f((zmax - zmin) / D, 2)}): mit Reitstock spannen.")
        out.append(p)
    return out


# ================================================================ Fräsen
def _nuten(g: _Geometrie) -> tuple[list[dict], list[str]]:
    """Passfedernuten aus den halben Querzylindern (je Nut zwei runde Enden mit gleichem Radius). Ein Paar zählt
    nur, wenn die Mitte zwischen den Enden wirklich frei ist – sonst sind es Querbohrungen."""
    gruppen: dict = {}
    for c in g.quer:
        vz = 1.0 if (c.von + c.bis) >= 0 else -1.0        # Seite der Achse, auf der der Zylinder liegt
        radial = sorted(abs(t) for t in (c.von, c.bis))
        richtung = tuple(round(vz * x, 3) for x in c.achse)
        gruppen.setdefault((round(c.radius, 3), richtung), []).append((round(c.ort[2], 3), round(radial[0], 3),
                                                                        round(radial[1], 3)))
    profil = _profil(g)
    out, warn = [], []
    mx, my = g.mitte
    for (r, richtung), enden in gruppen.items():
        enden = sorted(set(enden))
        frei = list(enden)
        i = 0
        while i + 1 < len(frei):
            (za, ra, _), (zb, rb, _) = frei[i], frei[i + 1]
            boden = min(ra, rb)
            r_welle = _d_an(profil, (za + zb) / 2) / 2
            bohr = [d / 2 for d, a, b in g.innen if a - 1e-6 <= za <= b + 1e-6]
            radial = (boden + (max(bohr) if bohr and boden < max(bohr) + 1e-3 else r_welle)) / 2
            mitte = (mx + richtung[0] * radial, my + richtung[1] * radial, (za + zb) / 2)
            if zb - za <= 0.5 * r or g.innen_material(mitte):
                i += 1
                continue
            if bohr and boden < max(bohr) + 1e-3 or boden >= r_welle - 1e-3:
                out.append({"innen": True, "b": 2 * r, "za": za, "zb": zb})
            else:
                out.append({"innen": False, "b": 2 * r, "za": za, "zb": zb, "t": r_welle - boden, "r": r_welle,
                            "winkel": math.degrees(math.atan2(richtung[1], richtung[0]))})
            del frei[i:i + 2]
        for z, _, _ in frei:
            warn.append(f"Querbohrung Ø{S._f(2 * r)} bei z = {S._f(z)} ist nicht im Programm (von Hand ergänzen).")
    return out, warn


def _fraesen_nut(nr: int, nuten: list, g: _Geometrie, einst: Einstellungen, teil: str, rv: dict) -> Programm:
    zmin = g.lo[2]
    r_ref = max(n["r"] for n in nuten)                    # Z0 auf dem größten Nut-Ø, die anderen liegen tiefer
    titel = f"Fräsen – Passfedernut{'en' if len(nuten) > 1 else ''}"
    p = Programm(f"fraesen_nut_{nr}" if nr > 1 else "fraesen_nut", titel, "Fräsmaschine", "fraesen",
                 f"Welle waagerecht im Schraubstock bzw. in Prismen, Nut oben. Nullpunkt: X0 an der Stirnseite "
                 f"z = {_z(zmin)} im Modell, Y0 auf der Wellenachse, Z0 oben auf dem Ø{_z(2 * r_ref)}.")
    w = _Schreiber(einst, "fraesen", titel, [f"Teil {teil}",
                                             f"Nullpunkt: X0 Stirnseite, Y0 Wellenachse, Z0 Oberkante D{_z(2 * r_ref)}",
                                             "UNGEPRUEFT - VOR DEM EINSATZ SIMULIEREN"])
    ab = einst.sicherheitsabstand
    l_ges = g.hi[2] - zmin
    p.umrisse = [[(0, -r_ref), (l_ges, -r_ref), (l_ges, r_ref), (0, r_ref), (0, -r_ref)]]
    breiten = sorted({round(n["b"], 3) for n in nuten})
    for tnr, b in enumerate(breiten, 1):
        n = S.drehzahl(rv["vc_f"], b, S.N_MAX_FRAESEN)
        vf = round(rv["fz"] * S.ZAEHNE_FRAESER * n)
        w.k(f"T{tnr} Schaftfraeser D{S._f(b)}")
        w.werkzeug(tnr)
        auswahl = [x for x in nuten if round(x["b"], 3) == b]
        p.werkzeuge.append(f"T{tnr} Schaftfräser Ø{S._f(b)} (über Mitte schneidend) – {len(auswahl)} Passfedernut(en)")
        _spindel(w, n)
        for nut in auswahl:
            dz = r_ref - nut["r"]                         # Oberkante dieser Nut unter Z0
            w.k(f"Nut {S._f(b)} x {S._f(nut['zb'] - nut['za'] + b)}, Tiefe {S._f(nut['t'])}")
            xa, xb = nut["za"] - zmin, nut["zb"] - zmin
            w.g0(z=ab)
            w.g0(x=xa, y=0)
            schritte = max(1, math.ceil(nut["t"] / (0.5 * b) - 1e-9))
            x_ist = xa
            for k in range(1, schritte + 1):
                w.g1(z=-dz - nut["t"] * k / schritte, f=round(0.3 * vf))      # Eintauchen mit reduziertem Vorschub
                x_ist = xb if x_ist == xa else xa
                w.g1(x=x_ist, f=vf)
            w.g0(z=ab)
            p.umrisse.append([(xa, -b / 2), (xb, -b / 2), (xb, b / 2), (xa, b / 2), (xa, -b / 2)])
            if abs(nut["winkel"] - 90) > 1:
                p.warnungen.append(f"Nut {S._f(b)} mm liegt im Modell unter {S._f(nut['winkel'])}° – Welle so "
                                   "drehen, dass die Nut oben liegt.")
        w.g0(z=ab + 50)
    if len({round(n["winkel"]) for n in nuten}) > 1:
        p.warnungen.append("Die Nuten liegen unter verschiedenen Winkeln – zwischen den Nuten umspannen.")
    p.zeilen = w.fertig()
    return p


_ACHSEN = "xyz"
# Aufspannrichtung → (Index u, Vorzeichen u, Index v, Vorzeichen v): rechtshändig, Z der Maschine = Flächennormale
_UV = {(2, 1): (0, 1, 1, 1), (2, -1): (0, 1, 1, -1), (0, 1): (1, 1, 2, 1), (0, -1): (1, 1, 2, -1),
       (1, 1): (2, 1, 0, 1), (1, -1): (2, 1, 0, -1)}


def _bohrbilder(g: _Geometrie, ohne_achse: bool = False) -> tuple[dict, list[str]]:
    """Achsparallele Bohrungen je Aufspannung (Achse, Seite) in Maschinenkoordinaten u, v. Von welcher Seite
    gebohrt wird und ob die Bohrung durchgeht, entscheidet das Volumenmodell (Punkt 0,5 mm vor bzw. hinter dem
    Ende) – so werden auch Bohrungen in einer Flanschplatte unter einem Rohrstutzen richtig erkannt."""
    roh: dict = {}
    for achse, d, ort, von, bis in g.parallel:
        andere = [i for i in range(3) if i != achse]
        if ohne_achse and achse == 2 and math.hypot(ort[0] - g.mitte[0], ort[1] - g.mitte[1]) < 0.5:
            continue                                     # Achsbohrung des gedrehten Rohlings
        k = (achse, round(d, 2), round(ort[andere[0]], 1), round(ort[andere[1]], 1))
        a0, b0 = roh.get(k, (von, bis))[:2]
        roh[k] = (min(a0, von), max(b0, bis), ort)
    gruppen: dict = {}
    warn = []
    for (achse, d, _, _), (von, bis, ort) in sorted(roh.items()):
        def frei(t):
            q = list(ort)
            q[achse] = t
            return not g.innen_material(q)
        offen_oben, offen_unten = frei(bis + 0.5), frei(von - 0.5)
        if offen_oben and (not offen_unten or bis >= g.hi[achse] - 0.1 or von > g.lo[achse] + 0.1):
            seite = 1
        elif offen_unten:
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
        durch = offen_oben and offen_unten
        b = _Bohrung(d, u, v, bis - von, durch)
        b.flaeche = bis if seite > 0 else -von            # Lage der Anbohrfläche entlang der Flächennormalen
        if not durch:                                     # bricht die Bohrerspitze unten durch?
            spitze = list(ort)
            spitze[achse] = (von - 0.3 * d + 0.2) if seite > 0 else (bis + 0.3 * d - 0.2)
            if not g.innen_material(spitze):
                b.spitze_frei = True
                warn.append(f"Sackloch Ø{S._f(d)}: die Bohrerspitze bräche unten durch – Bohrtiefe nur bis zum "
                            "zylindrischen Grund, Grund nach Zeichnung prüfen.")
        gruppen.setdefault((achse, seite), []).append(b)
    return gruppen, warn


def _ursprung(g: _Geometrie, i: int, s: int) -> float:
    """Nullpunkt einer Maschinenachse: Drehachse (Drehteil) bzw. kleinster Wert der Hüllbox."""
    if g.drehteil:
        return s * (g.mitte[i] if i < 2 else 0.0)
    return min(s * g.lo[i], s * g.hi[i])


def _sortieren(bohrungen: list[_Bohrung], drehteil: bool) -> list[_Bohrung]:
    if drehteil:      # Lochkreis der Reihe nach rundum, ab 12 Uhr – für den Bediener leicht nachzuvollziehen
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
                 f"Fläche {flaeche} nach oben spannen. Nullpunkt X/Y: {null}, Z0 auf der Anbohrfläche "
                 f"({_ACHSEN[achse]} = {_z(seite * max(b.flaeche for b in bohrungen))} im Modell). "
                 f"X entspricht {'+' if su > 0 else '-'}{_ACHSEN[iu]}, Y entspricht {'+' if sv > 0 else '-'}"
                 f"{_ACHSEN[iv]} des Modells.")
    w = _Schreiber(einst, "fraesen", titel, [f"Teil {teil}", f"Nullpunkt: {null}, Z0 auf der Flaeche {flaeche}",
                                             "UNGEPRUEFT - VOR DEM EINSATZ SIMULIEREN"])
    ab = einst.sicherheitsabstand
    bohrungen = _sortieren(bohrungen, g.drehteil)
    z0 = max(b.flaeche for b in bohrungen)               # Z0 auf der höchsten Anbohrfläche
    if any(z0 - b.flaeche > 1e-3 for b in bohrungen):
        p.warnungen.append("Die Bohrungen beginnen auf verschiedenen Höhen – Z0 liegt auf der höchsten Fläche, "
                           "tiefer liegende werden entsprechend tiefer angefahren.")
    # Anbohren aller Bohrungen
    w.k(f"T1 NC-Anbohrer D{S._f(ANBOHREN_D)} 90 Grad")
    w.werkzeug(1)
    p.werkzeuge.append(f"T1 NC-Anbohrer Ø{S._f(ANBOHREN_D)} 90° – Anbohren")
    n = S.drehzahl(rv["vc_b"], ANBOHREN_D, S.N_MAX_FRAESEN)
    _spindel(w, n)
    w.g0(z=ab)
    for b in bohrungen:
        dz = z0 - b.flaeche
        tiefe = min(b.d, ANBOHREN_D) / 2 + 0.2
        w.g0(x=b.u, y=b.v)
        if dz > 1e-3:
            w.g0(z=-dz + ab)
        w.g1(z=-dz - tiefe, f=round(0.1 * n))
        w.g0(z=ab)
    w.g0(z=ab + 50)
    tnr = 1
    for d in sorted({round(b.d, 2) for b in bohrungen}):
        tnr += 1
        f = min(0.4, max(0.05, 0.015 * d))
        n = S.drehzahl(rv["vc_b"], d, S.N_MAX_FRAESEN)
        w.k(f"T{tnr} Spiralbohrer D{S._f(d)}")
        w.werkzeug(tnr)
        auswahl = [b for b in bohrungen if round(b.d, 2) == d]
        p.werkzeuge.append(f"T{tnr} Spiralbohrer Ø{S._f(d)} – {len(auswahl)} Bohrung(en)")
        _spindel(w, n)
        w.g0(z=ab)
        for b in auswahl:
            dz = z0 - b.flaeche
            tiefe = b.tiefe + (0.3 * d + 1 if b.durch else (0.0 if b.spitze_frei else 0.3 * d))
            _tiefbohren(w, b.u, b.v, -tiefe, max(2.0, d), round(f * n), ab, achse="z", oben=-dz)
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
    w.werkzeug(1)
    p.werkzeuge.append(f"T1 Schaftfräser Ø{S._f(d)}, z = {S.ZAEHNE_FRAESER} – Außenkontur")
    _spindel(w, n)
    ecken = [(-r, -r), (-r, lv + r), (lu + r, lv + r), (lu + r, -r), (-r, -r)]   # Gleichlauf außen
    w.g0(x=-r - ab - r, y=-r)
    w.g0(z=ab)
    schritte = max(1, math.ceil((h + 0.5) / (0.5 * d) - 1e-9))
    for k in range(1, schritte + 1):
        w.g1(z=-(h + 0.5) * k / schritte, f=round(0.3 * vf))
        for x, y in ecken:
            w.g1(x=x, y=y, f=vf)
        w.g1(x=-r - ab - r, y=-r)
    w.g0(z=ab + 50)
    p.zeilen = w.fertig()
    roh = plan.get("rohteil", {})
    if float(roh.get("h") or h) > h + 0.1:
        p.warnungen.append(f"Das Rohteil ist {S._f(float(roh['h']))} mm dick, das Teil {S._f(h)} mm – zuerst auf "
                           "Dicke planfräsen (nicht im Programm), danach Z0 auf die Oberseite setzen.")
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
    nuten, warnungen = _nuten(g) if g.drehteil else ([], [])
    aussen_nuten = [n for n in nuten if not n["innen"]]
    if aussen_nuten and "fraesen" in arten:
        out.append(_fraesen_nut(1, aussen_nuten, g, einst, teil, rv))
    elif aussen_nuten:
        warnungen.append("Das Teil hat Passfedernuten, der Arbeitsplan aber keinen Fräsgang – keine Nut im Programm.")
    warnungen += [f"Nabennut {S._f(n['b'])} mm in der Bohrung wird gestoßen oder geräumt – nicht im Programm."
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
        gruppen, warn = _bohrbilder(g, ohne_achse=rohling is not None)
        warnungen += warn
        for i, ((achse, seite), bohr) in enumerate(sorted(gruppen.items(), key=lambda t: (-t[0][1], t[0][0]))):
            out.append(_fraesen_bohren(i + 1, achse, seite, bohr, g, einst, teil, rv))
    if out:
        out[0].warnungen = warnungen + out[0].warnungen
    if einst.dialekt == "fanuc":             # fortlaufende Programmnummern
        for i, p in enumerate(out):
            p.zeilen[1] = re.sub(r"^O\d+", f"O{(einst.programmnummer + i - 1) % 9999 + 1:04d}", p.zeilen[1])
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
_BEKANNT_G = {0, 1, 7, 8, 17, 18, 19, 21, 40, 43, 49, 54, 80, 90, 94, 95, 96, 97, 98, 99}
_BEKANNT_M = {0, 1, 2, 3, 4, 5, 6, 8, 9, 30}


def pruefen(text: str, art: str, rohteil_d: float | None = None) -> Pruefung:
    """G-Code lesen und auf typische Fehler prüfen. art: "drehen" (X = Ø, Z) oder "fraesen" (X, Y, Z).
    rohteil_d (Drehen): Eilgänge mit Z < 0 innerhalb dieses Ø gelten als Eilgang im Material, außer in schon
    frei geschnittene Bereiche (z. B. zurück in die eigene Bohrung)."""
    p = Pruefung()
    pos = {"X": None, "Y": 0.0 if art == "drehen" else None, "Z": None}
    modal, f, s, spindel, je_umdrehung, css, ende = None, None, 0.0, False, False, False, False
    frei: dict = {}          # Lage quer zur Vorschubrichtung → tiefstes Z, das per Vorschub schon frei ist
    a_min = b_min = math.inf
    a_max = b_max = -math.inf
    for nr, roh in enumerate(text.splitlines(), 1):
        zeile = re.sub(r"\([^)]*\)", "", roh).split(";")[0].strip().upper()
        if not zeile or zeile == "%" or zeile.startswith("O"):
            continue
        if ende:
            p.hinweise.append(f"Zeile {nr}: Sätze nach dem Programmende werden nicht ausgeführt.")
            break
        woerter = [(b, float(w)) for b, w in _WORT.findall(zeile)]
        rest = _WORT.sub("", zeile).strip()
        if rest:
            p.fehler.append(f"Zeile {nr}: „{rest}“ ist kein gültiges Wort.")
        # Reihenfolge wie in der Steuerung: erst G, dann S/F/T, dann M, dann die Bewegung
        for buchst, zahl in woerter:
            if buchst != "G":
                continue
            gz = int(zahl)
            if gz in (0, 1):
                modal = gz
            elif gz == 91:
                p.fehler.append(f"Zeile {nr}: G91 (Kettenmaß) wird hier nicht unterstützt – nur G90.")
            elif gz == 20:
                p.fehler.append(f"Zeile {nr}: G20 (Zoll) – das Programm ist in mm (G21) gedacht.")
            elif gz == 95 or (gz == 99 and art == "drehen"):
                je_umdrehung = True
            elif gz == 94 or (gz == 98 and art == "drehen"):
                je_umdrehung = False
            elif gz == 96:
                css = True
            elif gz == 97:
                css = False
            elif gz in (2, 3):
                p.fehler.append(f"Zeile {nr}: Kreisbogen G{gz} wird vom Prüfer nicht ausgewertet.")
            elif gz not in _BEKANNT_G:
                p.hinweise.append(f"Zeile {nr}: G{gz} ist dem Prüfer unbekannt.")
        m6 = any(b == "M" and int(z) == 6 for b, z in woerter)
        for buchst, zahl in woerter:
            if buchst == "S":
                s = zahl
            elif buchst == "F":
                f = zahl
            elif buchst == "T" and not m6:
                p.werkzeugwechsel += 1
            elif buchst not in "GMNSFTXYZ":
                p.hinweise.append(f"Zeile {nr}: Adresse {buchst} ist dem Prüfer unbekannt.")
        for buchst, zahl in woerter:
            if buchst != "M":
                continue
            mz = int(zahl)
            if mz in (3, 4):
                if s <= 0:
                    p.fehler.append(f"Zeile {nr}: Spindel ein ohne Drehzahl S.")
                spindel = True
            elif mz in (0, 5):
                spindel = spindel and mz != 5
            elif mz == 6:
                p.werkzeugwechsel += 1
            elif mz in (2, 30):
                ende = True
            elif mz not in _BEKANNT_M:
                p.hinweise.append(f"Zeile {nr}: M{mz} ist dem Prüfer unbekannt.")
        ziel = dict(pos)
        bewegt = False
        for buchst, zahl in woerter:
            if buchst in "XYZ":
                ziel[buchst] = zahl
                bewegt = True
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
            schluessel = round(ziel["X"], 2)
            if modal == 1 and abs(ziel["X"] - pos["X"]) < 1e-9:
                frei[schluessel] = min(frei.get(schluessel, 0.0), ziel["Z"])
            elif modal == 0 and rohteil_d and ziel["Z"] < -1e-6 and abs(ziel["X"]) < rohteil_d - 1e-6 \
                    and ziel["Z"] < frei.get(schluessel, 0.0) - 1e-6 and ziel["Z"] < pos["Z"] - 1e-6:
                p.fehler.append(f"Zeile {nr}: Eilgang ins Material (X{_z(ziel['X'])} Z{_z(ziel['Z'])}).")
        else:
            d = math.dist((pos["X"], pos["Y"], pos["Z"]), (ziel["X"], ziel["Y"], ziel["Z"]))
            seg = Segment(pos["X"], pos["Y"], ziel["X"], ziel["Y"], modal == 0)
            if modal == 0 and min(pos["Z"], ziel["Z"]) < -1e-6 and \
                    (abs(ziel["X"] - pos["X"]) > 1e-6 or abs(ziel["Y"] - pos["Y"]) > 1e-6):
                p.fehler.append(f"Zeile {nr}: Eilgang seitlich unterhalb Z0 – Kollisionsgefahr im Werkstück.")
            schluessel = (round(ziel["X"], 2), round(ziel["Y"], 2))
            if modal == 1 and abs(ziel["X"] - pos["X"]) < 1e-9 and abs(ziel["Y"] - pos["Y"]) < 1e-9:
                frei[schluessel] = min(frei.get(schluessel, 0.0), ziel["Z"])
            elif modal == 0 and ziel["Z"] < pos["Z"] - 1e-6 and ziel["Z"] < frei.get(schluessel, 0.0) - 1e-6:
                p.fehler.append(f"Zeile {nr}: Eilgang nach unten ins Werkstück (Z{_z(ziel['Z'])}).")
        if modal == 1:
            if not f:
                p.fehler.append(f"Zeile {nr}: Vorschub-Bewegung ohne Vorschub F.")
            elif not spindel:
                p.fehler.append(f"Zeile {nr}: Schnitt bei stehender Spindel.")
            else:
                n = s
                if css and art == "drehen":          # G96: S ist die Schnittgeschwindigkeit in m/min
                    n = s * 1000 / (math.pi * max(abs(pos["X"]), abs(ziel["X"]), 1.0))
                vf = f * n if je_umdrehung else f
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
