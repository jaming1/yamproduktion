"""Baugruppen (Lastenheft M30, M32): Bauteile und Normteile einbauen, ausrichten, Masse & Schwerpunkt, Stückliste.

Eine Baugruppe ist ein JSON-Wörterbuch (wird im Projekt gespeichert, keine Geometrie – wie E14/E16):

    {"parameter": [{"name": "a", "formel": "300"}],
     "einbauten": [
        {"id": "E1", "art": "teil", "teil_id": 1, "name": "Hauptwelle",
         "lage": {"x": "0", "y": "0", "z": "0", "rx": "0", "ry": "0", "rz": "0"}},
        {"id": "E2", "art": "normteil", "norm": "22216 E", "name": "Festlager",
         "bezug": {"ziel": "E1", "abstand": "a", "umdrehen": false}},           # koaxial zu E1, entlang dessen Achse
        {"id": "E3", "art": "normteil", "norm": "ISO 4762 M12x40",
         "lage": {...}, "kreis": {"anzahl": "8", "radius": "90"}}]}            # Lochkreis um die z-Achse

„bezug“ (Verknüpfung): koaxial zur z-Achse des Ziel-Einbaus, um „abstand“ entlang dieser Achse verschoben,
auf Wunsch umgedreht (Achse zeigt entgegen) und um „rz“ gedreht. Ändert sich das Ziel, wandert das Teil mit.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from OCP.BRep import BRep_Builder
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.gp import gp_Trsf
from OCP.TopoDS import TopoDS_Compound

from . import normteile
from .ausdruck import AusdruckFehler, auswerten, tabelle_auswerten
from .geometrie import GeometrieFehler, eigenschaften


def leer() -> dict:
    return {"parameter": [], "einbauten": []}


def _drehung(rx: float, ry: float, rz: float) -> np.ndarray:
    a, b, c = (math.radians(w) for w in (rx, ry, rz))
    Rx = np.array([[1, 0, 0], [0, math.cos(a), -math.sin(a)], [0, math.sin(a), math.cos(a)]])
    Ry = np.array([[math.cos(b), 0, math.sin(b)], [0, 1, 0], [-math.sin(b), 0, math.cos(b)]])
    Rz = np.array([[math.cos(c), -math.sin(c), 0], [math.sin(c), math.cos(c), 0], [0, 0, 1]])
    return Rz @ Ry @ Rx


def _matrix(R: np.ndarray, t) -> np.ndarray:
    M = np.eye(4)
    M[:3, :3] = R
    M[:3, 3] = t
    return M


def nach_trsf(M: np.ndarray) -> gp_Trsf:
    t = gp_Trsf()
    t.SetValues(*[float(M[i, j]) for i in range(3) for j in range(4)])
    return t


def bewegen(form, M: np.ndarray):
    return BRepBuilderAPI_Transform(form, nach_trsf(M), True).Shape()


@dataclass
class Exemplar:
    einbau: str                  # id des Einbaus
    form: object                 # transformierter Körper
    matrix: np.ndarray
    schluessel: str = ""         # Stücklistenschlüssel (Teilnummer oder Norm)
    masse: float | None = None   # kg je Exemplar (None = unbekannt) – für Trägheit und Masse je Einbau (K4)


@dataclass
class Position:
    pos: int
    menge: int
    benennung: str
    sachnummer: str              # Teilnummer (T-001) oder Normbezeichnung
    werkstoff: str
    einzelmasse: float | None    # kg
    art: str                     # "Bauteil" / "Normteil"
    hinweis: str = ""

    @property
    def gesamtmasse(self) -> float | None:
        return None if self.einzelmasse is None else self.einzelmasse * self.menge


class ZyklusFehler(GeometrieFehler):
    pass


@dataclass
class Ergebnis:
    exemplare: list[Exemplar] = field(default_factory=list)
    stueckliste: list[Position] = field(default_factory=list)
    masse: float = 0.0                       # kg
    schwerpunkt: tuple = (0.0, 0.0, 0.0)     # mm
    werte: dict = field(default_factory=dict)
    fehler: str = ""
    meldungen: dict = field(default_factory=dict)   # Einbau-id → Fehler
    ohne_masse: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.fehler and not self.meldungen

    def positionspunkte(self) -> list[tuple[int, tuple]]:
        """Je Stücklistenposition ein Punkt am ersten Exemplar (für die Positionsnummern der Zeichnung):
        nahe der Oberkante in der Vorderansicht (kleinstes x), mittig in y und z."""
        pos = {p.sachnummer: p.pos for p in self.stueckliste}
        out, gesehen = [], set()
        for x in self.exemplare:
            if x.schluessel in gesehen or x.schluessel not in pos:
                continue
            gesehen.add(x.schluessel)
            e = eigenschaften(x.form)
            out.append((pos[x.schluessel], (e.minimum[0] + 0.15 * e.groesse[0], (e.minimum[1] + e.maximum[1]) / 2,
                                            (e.minimum[2] + e.maximum[2]) / 2)))
        return sorted(out)

    def gesamtform(self):
        bau = BRep_Builder()
        c = TopoDS_Compound()
        bau.MakeCompound(c)
        for x in self.exemplare:
            bau.Add(c, x.form)
        return c


def bauen(definition: dict, teil_quelle, ber=None) -> Ergebnis:
    """`teil_quelle(teil_id)` → dict(form, masse, werkstoff, nr, name). `ber` wie im Modellierer."""
    erg = Ergebnis()
    try:
        werte = tabelle_auswerten(definition.get("parameter", []), ber)
    except AusdruckFehler as exc:
        erg.fehler = f"Parameter: {exc}"
        return erg
    erg.werte = werte

    def w(text, standard=0.0):
        if text in (None, ""):
            return standard
        return auswerten(text, werte, ber)

    einbauten = {e["id"]: e for e in definition.get("einbauten", [])}
    matrizen: dict[str, np.ndarray] = {}
    teile_cache: dict = {}
    positionen: dict[str, Position] = {}
    gesamt_m, moment = 0.0, np.zeros(3)

    def lage(eid: str, kette: tuple = ()) -> np.ndarray:
        if eid in matrizen:
            return matrizen[eid]
        if eid in kette:
            raise ZyklusFehler("Die Verknüpfungen verweisen im Kreis aufeinander: " + " → ".join(kette + (eid,)))
        e = einbauten[eid]
        l = e.get("lage", {})
        b = e.get("bezug")
        if b and b.get("ziel"):
            if b["ziel"] not in einbauten:
                raise GeometrieFehler(f"Bezug auf „{b['ziel']}“, das es nicht gibt.")
            ziel = lage(b["ziel"], kette + (eid,))
            R = _drehung(180 if b.get("umdrehen") else 0, 0, w(l.get("rz")))
            lokal = _matrix(R, (0, 0, w(b.get("abstand"))))
            M = ziel @ lokal
        else:
            M = _matrix(_drehung(w(l.get("rx")), w(l.get("ry")), w(l.get("rz"))), (w(l.get("x")), w(l.get("y")), w(l.get("z"))))
        matrizen[eid] = M
        return M

    for eid, e in einbauten.items():
        try:
            M = lage(eid)
            if e["art"] == "teil":
                if e["teil_id"] not in teile_cache:
                    teile_cache[e["teil_id"]] = teil_quelle(e["teil_id"])
                t = teile_cache[e["teil_id"]]
                form, masse, schluessel = t["form"], t.get("masse"), t["nr"]
                benennung, sachnr, werkstoff, art, hinweis = t["name"], t["nr"], t.get("werkstoff", ""), "Bauteil", ""
            else:
                n = normteile.erzeugen(e["norm"])
                form, masse, schluessel = n.form, n.masse, n.norm
                benennung, sachnr, werkstoff, art, hinweis = n.benennung, n.norm, n.werkstoff, "Normteil", n.hinweis
            kreis = e.get("kreis")
            lagen = [np.eye(4)]
            if kreis and kreis.get("anzahl"):
                n_k = int(round(w(kreis["anzahl"])))
                r = w(kreis.get("radius"), 0)
                if n_k < 1:
                    raise GeometrieFehler("Die Anzahl im Lochkreis muss mindestens 1 sein.")
                w0 = w(kreis.get("startwinkel"), 0)
                lagen = []
                for i in range(n_k):
                    phi = math.radians(w0 + 360 * i / n_k)
                    lagen.append(_matrix(_drehung(0, 0, 0), (r * math.cos(phi), r * math.sin(phi), 0)))
            for L in lagen:
                MM = M @ L
                erg.exemplare.append(Exemplar(eid, bewegen(form, MM), MM, schluessel, masse))
                if masse:
                    s = eigenschaften(form).schwerpunkt
                    gesamt_m += masse
                    moment += masse * (MM @ np.array([*s, 1.0]))[:3]
            menge = len(lagen)
            if schluessel in positionen:
                positionen[schluessel].menge += menge
            else:
                positionen[schluessel] = Position(0, menge, benennung, sachnr, werkstoff, masse, art, hinweis)
            if not masse:
                erg.ohne_masse.append(e.get("name") or sachnr)
        except ZyklusFehler as exc:
            erg.fehler = str(exc)
            erg.exemplare.clear()
            return erg
        except (GeometrieFehler, AusdruckFehler, KeyError, ValueError) as exc:
            erg.meldungen[eid] = str(exc) if not isinstance(exc, KeyError) else f"Angabe {exc} fehlt."
    # Stückliste: erst Bauteile (nach Nummer), dann Normteile (nach Bezeichnung)
    liste = sorted(positionen.values(), key=lambda p: (p.art != "Bauteil", p.sachnummer))
    for i, p in enumerate(liste, 1):
        p.pos = i
    erg.stueckliste = liste
    erg.masse = gesamt_m
    erg.schwerpunkt = tuple(moment / gesamt_m) if gesamt_m else (0.0, 0.0, 0.0)
    if erg.meldungen and not erg.fehler:
        erg.fehler = "; ".join(f"{einbauten[k].get('name') or k}: {v}" for k, v in erg.meldungen.items())
    return erg


def naechste_id(definition: dict) -> str:
    vorhanden = {e["id"] for e in definition.get("einbauten", [])}
    i = 1
    while f"E{i}" in vorhanden:
        i += 1
    return f"E{i}"


def stueckliste_csv(stueckliste: list[Position]) -> str:
    """Stückliste als CSV (Semikolon, Dezimalkomma – öffnet direkt in Excel/Numbers mit deutscher Einstellung)."""
    zeilen = ["Pos;Menge;Benennung;Sachnummer / Norm;Werkstoff;Einzelmasse kg;Gesamtmasse kg"]
    for p in stueckliste:
        def z(v):
            return "" if v is None else f"{v:.3f}".replace(".", ",")
        zeilen.append(f"{p.pos};{p.menge};{p.benennung};{p.sachnummer};{p.werkstoff};{z(p.einzelmasse)};{z(p.gesamtmasse)}")
    return "\n".join(zeilen) + "\n"
