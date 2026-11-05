"""Kollisionsprüfung, Masse und Schwerpunkt einer Baugruppe (Lastenheft K4, Entscheidung E41).

Geprüft wird jedes Paar von Exemplaren (auch die Exemplare eines Lochkreises untereinander):

1. Vorfilter über die Hüllboxen (um den Mindestabstand vergrößert) – Paare, die weit auseinander liegen,
   kosten so fast nichts.
2. Schnittmenge der Körper (Boolesche Operation). Volumen über `min_volumen` → **Durchdringung**.
3. Sonst kürzester Abstand der Körper: ≤ `beruehr_toleranz` → **Berührung** (z. B. Lager auf Welle, Passung),
   kleiner als `mindestabstand` → **Spiel zu klein**.

Befunde sind Hinweise, keine Urteile: gewollte Überdeckungen (Presspassung, vereinfachte Schraube ohne
Bohrung im Gegenstück) werden als Ausnahme mit Begründung festgehalten und dann nicht mehr als Fehler gezählt.
Ausnahmen gelten für ein Paar von Einbauten (alle Exemplare eines Lochkreises zusammen).

Masse und Schwerpunkt kommen aus `baugruppe.bauen`; hier zusätzlich die Massenträgheit um den Schwerpunkt
(Hauptträgheitsmomente) und die Masse je Einbau – Teile ohne Masse werden genannt und nicht mitgezählt.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps

from .geometrie import schnittmenge

DURCHDRINGUNG = "Durchdringung"
BERUEHRUNG = "Berührung"
SPIEL = "Spiel zu klein"
ARTEN = (DURCHDRINGUNG, SPIEL, BERUEHRUNG)       # nach Schwere geordnet


@dataclass
class Befund:
    a: int                    # Index des Exemplars in ergebnis.exemplare
    b: int
    einbau_a: str             # Einbau-ids (für Ausnahmen)
    einbau_b: str
    name_a: str               # lesbar, z. B. „E4 Schraube (3/8)“
    name_b: str
    art: str
    volumen: float = 0.0      # mm³ Überschneidung (nur Durchdringung)
    abstand: float = 0.0      # mm kürzester Abstand (0 bei Durchdringung/Berührung)
    ort: tuple = (0.0, 0.0, 0.0)    # mm, Mitte der Überschneidung bzw. des kürzesten Abstands
    ausnahme: str = ""        # Begründung, wenn als gewollt festgehalten

    @property
    def ist_fehler(self) -> bool:
        return self.art in (DURCHDRINGUNG, SPIEL) and not self.ausnahme

    @property
    def paar(self) -> tuple[str, str]:
        return paar(self.einbau_a, self.einbau_b)


@dataclass
class Pruefung:
    befunde: list[Befund] = field(default_factory=list)
    paare_geprueft: int = 0           # Paare nach dem Vorfilter genau geprüft
    paare_gesamt: int = 0
    mindestabstand: float = 0.0
    fehler: str = ""                  # Prüfung selbst ging schief (z. B. kaputte Geometrie)

    def anzahl(self, art: str, mit_ausnahmen: bool = False) -> int:
        return sum(1 for b in self.befunde if b.art == art and (mit_ausnahmen or not b.ausnahme))

    @property
    def fehler_anzahl(self) -> int:
        return sum(1 for b in self.befunde if b.ist_fehler)

    @property
    def ok(self) -> bool:
        return not self.fehler and self.fehler_anzahl == 0

    def betroffene(self) -> list[int]:
        """Exemplare mit offenem Befund (Durchdringung oder zu wenig Spiel) – für die Hervorhebung."""
        s = set()
        for b in self.befunde:
            if b.ist_fehler:
                s.update((b.a, b.b))
        return sorted(s)

    def zusammenfassung(self) -> str:
        if self.fehler:
            return self.fehler
        teile = []
        for art in ARTEN:
            n = self.anzahl(art)
            if n:
                teile.append(f"{n} × {art}")
        aus = sum(1 for b in self.befunde if b.ausnahme)
        if aus:
            teile.append(f"{aus} als gewollt vermerkt")
        if not teile:
            return "Keine Kollision gefunden."
        return ("Keine offene Kollision. " if self.ok else "") + " · ".join(teile)


def paar(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a <= b else (b, a)


def _box(form, rand: float) -> np.ndarray:
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(form, box, False, False)
    lo, hi = box.CornerMin(), box.CornerMax()
    return np.array([lo.X() - rand, lo.Y() - rand, lo.Z() - rand, hi.X() + rand, hi.Y() + rand, hi.Z() + rand])


def _boxen_ueberlappen(p: np.ndarray, q: np.ndarray) -> bool:
    return bool(np.all(p[:3] <= q[3:]) and np.all(q[:3] <= p[3:]))


def _volumen(form) -> tuple[float, tuple]:
    g = GProp_GProps()
    BRepGProp.VolumeProperties_s(form, g)
    s = g.CentreOfMass()
    return abs(g.Mass()), (s.X(), s.Y(), s.Z())


def namen(ergebnis, definition: dict) -> list[str]:
    """Lesbarer Name je Exemplar: „E4 Schraube“, bei Lochkreisen mit Zähler „(3/8)“."""
    einbauten = {e["id"]: e for e in definition.get("einbauten", [])}
    zahl = {}
    for x in ergebnis.exemplare:
        zahl[x.einbau] = zahl.get(x.einbau, 0) + 1
    lauf, out = {}, []
    for x in ergebnis.exemplare:
        lauf[x.einbau] = lauf.get(x.einbau, 0) + 1
        e = einbauten.get(x.einbau, {})
        name = f"{x.einbau} {e.get('name') or e.get('norm') or ''}".strip()
        if zahl[x.einbau] > 1:
            name += f" ({lauf[x.einbau]}/{zahl[x.einbau]})"
        out.append(name)
    return out


def pruefen(ergebnis, definition: dict, ausnahmen: dict | None = None, mindestabstand: float = 0.0,
            min_volumen: float = 0.01, beruehr_toleranz: float = 1e-3) -> Pruefung:
    """Alle Exemplare paarweise prüfen. `ausnahmen`: {(einbau_a, einbau_b): Begründung} (Schlüssel per `paar`)."""
    ausnahmen = ausnahmen or {}
    ex = ergebnis.exemplare
    pr = Pruefung(mindestabstand=max(0.0, float(mindestabstand or 0)))
    pr.paare_gesamt = len(ex) * (len(ex) - 1) // 2
    if len(ex) < 2:
        return pr
    rand = max(pr.mindestabstand, beruehr_toleranz)
    try:
        boxen = [_box(x.form, rand / 2) for x in ex]
    except Exception as exc:          # OCCT wirft eigene Ausnahmen
        pr.fehler = f"Prüfung nicht möglich: {exc}"
        return pr
    nam = namen(ergebnis, definition)
    for i in range(len(ex)):
        for j in range(i + 1, len(ex)):
            if not _boxen_ueberlappen(boxen[i], boxen[j]):
                continue
            pr.paare_geprueft += 1
            a, b = ex[i], ex[j]
            befund = Befund(i, j, a.einbau, b.einbau, nam[i], nam[j], "")
            try:
                vol, ort = _volumen(schnittmenge(a.form, b.form))
                if vol > min_volumen:
                    befund.art, befund.volumen, befund.ort = DURCHDRINGUNG, vol, ort
                else:
                    d = BRepExtrema_DistShapeShape(a.form, b.form)
                    if not d.IsDone():
                        continue
                    abstand = d.Value()
                    p, q = d.PointOnShape1(1), d.PointOnShape2(1)
                    befund.ort = ((p.X() + q.X()) / 2, (p.Y() + q.Y()) / 2, (p.Z() + q.Z()) / 2)
                    befund.abstand = abstand
                    if abstand <= beruehr_toleranz:
                        befund.art, befund.abstand = BERUEHRUNG, 0.0
                    elif abstand < pr.mindestabstand:
                        befund.art = SPIEL
                    else:
                        continue
            except Exception as exc:
                pr.fehler = f"Prüfung von {nam[i]} und {nam[j]} nicht möglich: {exc}"
                continue
            befund.ausnahme = ausnahmen.get(befund.paar, "")
            pr.befunde.append(befund)
    pr.befunde.sort(key=lambda b: (ARTEN.index(b.art), bool(b.ausnahme), -b.volumen, b.abstand, b.a, b.b))
    return pr


# ---------------------------------------------------------------- Masse, Schwerpunkt, Trägheit
@dataclass
class MasseEinbau:
    einbau: str
    name: str
    menge: int
    masse: float | None       # kg gesamt (alle Exemplare)
    anteil: float = 0.0       # an der Gesamtmasse


@dataclass
class Massen:
    masse: float = 0.0                              # kg
    schwerpunkt: tuple = (0.0, 0.0, 0.0)            # mm
    traegheit: np.ndarray = field(default_factory=lambda: np.zeros((3, 3)))   # kg·mm² um den Schwerpunkt
    haupt: tuple = (0.0, 0.0, 0.0)                  # Hauptträgheitsmomente kg·mm², aufsteigend
    hauptachsen: np.ndarray = field(default_factory=lambda: np.eye(3))        # Spalten = Achsen
    je_einbau: list[MasseEinbau] = field(default_factory=list)
    ohne_masse: list[str] = field(default_factory=list)

    def traegheit_kgm2(self) -> np.ndarray:
        return self.traegheit * 1e-6


def massen(ergebnis, definition: dict) -> Massen:
    """Masse, Schwerpunkt und Trägheitstensor aus den Exemplaren (homogene Dichte je Teil angenommen)."""
    einbauten = {e["id"]: e for e in definition.get("einbauten", [])}
    m_ges, moment = 0.0, np.zeros(3)
    teile = []                  # (m, Schwerpunkt, Tensor um eigenen Schwerpunkt)
    je: dict[str, MasseEinbau] = {}
    for x in ergebnis.exemplare:
        e = einbauten.get(x.einbau, {})
        z = je.setdefault(x.einbau, MasseEinbau(x.einbau, e.get("name") or e.get("norm") or x.einbau, 0, None))
        z.menge += 1
        m = getattr(x, "masse", None)
        if not m:
            continue
        g = GProp_GProps()
        BRepGProp.VolumeProperties_s(x.form, g)
        v = abs(g.Mass())
        if v <= 0:
            continue
        s = g.CentreOfMass()
        mat = g.MatrixOfInertia()        # um den eigenen Schwerpunkt, Dichte 1 → mm⁵
        J = np.array([[mat.Value(r, c) for c in (1, 2, 3)] for r in (1, 2, 3)]) * (m / v)
        sp = np.array([s.X(), s.Y(), s.Z()])
        teile.append((m, sp, J))
        m_ges += m
        moment += m * sp
        z.masse = (z.masse or 0.0) + m
    out = Massen(je_einbau=list(je.values()))
    out.ohne_masse = [z.name for z in out.je_einbau if z.masse is None]
    if not m_ges:
        return out
    S = moment / m_ges
    I = np.zeros((3, 3))
    for m, sp, J in teile:              # Steiner: J + m (|d|² E − d dᵀ)
        d = sp - S
        I += J + m * (float(d @ d) * np.eye(3) - np.outer(d, d))
    werte, achsen = np.linalg.eigh((I + I.T) / 2)
    out.masse, out.schwerpunkt, out.traegheit = m_ges, tuple(float(c) for c in S), I
    out.haupt, out.hauptachsen = tuple(float(w) for w in werte), achsen
    for z in out.je_einbau:
        z.anteil = (z.masse or 0.0) / m_ges
    out.je_einbau.sort(key=lambda z: -(z.masse or 0.0))
    return out
