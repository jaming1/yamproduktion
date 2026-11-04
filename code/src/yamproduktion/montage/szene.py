"""Montageszene für Anzeige und Anleitung: alle Exemplare einer Baugruppe als ein Netz, je Dreieck das Exemplar.

Jeder Einbau wird nur einmal vernetzt; weitere Exemplare (Lochkreis) werden durch Transformation der Punkte
erzeugt. Explosion = Verschiebung der Punkte je Exemplar, Montageschritt = Sichtbarkeit und Farbgruppe je
Exemplar – beides ohne neue Vernetzung.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..cad.baugruppe import bewegen
from ..cad.geometrie import Netz, eigenschaften, netz

GRUPPE_TEIL, GRUPPE_NEU, GRUPPE_VORRICHTUNG = 0, 1, 2


@dataclass
class Szene:
    punkte: np.ndarray
    dreiecke: np.ndarray
    normalen: np.ndarray
    ex_pkt: np.ndarray                  # Exemplar je Punkt
    ex_tri: np.ndarray                  # Exemplar je Dreieck
    kanten: list = field(default_factory=list)      # [(Exemplar, Polylinie)]
    einbau: list = field(default_factory=list)      # Einbau-id je Exemplar ("" = Vorrichtung)
    vorrichtung: int | None = None      # Index der Vorrichtung

    @property
    def anzahl(self) -> int:
        return len(self.einbau)

    def netz(self, verschiebung=None, sichtbar=None) -> Netz:
        P = self.punkte if verschiebung is None else self.punkte + np.asarray(verschiebung)[self.ex_pkt]
        if sichtbar is None:
            maske = np.ones(len(self.dreiecke), bool)
            kanten = [k for _, k in self.kanten]
        else:
            sichtbar = np.asarray(sichtbar, bool)
            maske = sichtbar[self.ex_tri]
            kanten = [k for i, k in self.kanten if sichtbar[i]]
        if verschiebung is not None:
            v = np.asarray(verschiebung)
            kanten = [k + v[i] for i, k in self.kanten if sichtbar is None or sichtbar[i]]
        return Netz(P, self.dreiecke[maske], self.normalen[maske], self.ex_tri[maske], kanten)

    def gruppen(self, neu=(), sichtbar=None) -> np.ndarray:
        """Farbgruppe je sichtbarem Dreieck (Reihenfolge wie in netz(…, sichtbar))."""
        g = np.full(self.anzahl, GRUPPE_TEIL)
        for i in neu:
            g[i] = GRUPPE_NEU
        if self.vorrichtung is not None:
            g[self.vorrichtung] = GRUPPE_VORRICHTUNG
        ex = self.ex_tri if sichtbar is None else self.ex_tri[np.asarray(sichtbar, bool)[self.ex_tri]]
        return g[ex]

    def exemplare_von(self, einbauten) -> list[int]:
        s = set(einbauten)
        return [i for i, e in enumerate(self.einbau) if e in s]


def aufbauen(erg, vorrichtung_form=None, basis_matrix=None) -> Szene:
    """Szene aus cad.baugruppe.Ergebnis; die Vorrichtung (in Koordinaten des Grundteils) wird mit dessen Matrix
    an die richtige Stelle gesetzt."""
    if not erg.exemplare:
        raise ValueError("Die Baugruppe ist leer.")
    gross = max(eigenschaften(erg.gesamtform()).groesse)
    tol = max(0.05, gross / 600)
    P, T, N, EP, ET, K, namen = [], [], [], [], [], [], []
    vorlagen: dict[str, tuple] = {}

    def anhaengen(i, pkt, tri, nor, kanten):
        basis = sum(len(p) for p in P)
        P.append(pkt)
        T.append(tri + basis)
        N.append(nor)
        EP.append(np.full(len(pkt), i))
        ET.append(np.full(len(tri), i))
        K.extend((i, k) for k in kanten)

    for i, x in enumerate(erg.exemplare):
        namen.append(x.einbau)
        if x.einbau not in vorlagen:
            n = netz(x.form, tol)
            vorlagen[x.einbau] = (n, x.matrix)
            anhaengen(i, n.punkte, n.dreiecke, n.normalen, n.kanten)
            continue
        n, M0 = vorlagen[x.einbau]
        A = x.matrix @ np.linalg.inv(M0)
        R, t = A[:3, :3], A[:3, 3]
        anhaengen(i, n.punkte @ R.T + t, n.dreiecke, n.normalen @ R.T, [k @ R.T + t for k in n.kanten])
    vi = None
    if vorrichtung_form is not None:
        form = vorrichtung_form if basis_matrix is None else bewegen(vorrichtung_form, basis_matrix)
        n = netz(form, tol)
        vi = len(namen)
        namen.append("")
        anhaengen(vi, n.punkte, n.dreiecke, n.normalen, n.kanten)
    return Szene(np.vstack(P), np.vstack(T), np.vstack(N), np.concatenate(EP), np.concatenate(ET), K, namen, vi)


def verschiebungen(szene: Szene, je_exemplar: list) -> np.ndarray:
    """Explosionsvektoren der Baugruppe auf die Szene übertragen (Vorrichtung bleibt stehen)."""
    v = np.zeros((szene.anzahl, 3))
    for i, d in enumerate(je_exemplar):
        v[i] = d
    return v


def schritt_ansicht(szene: Szene, plan: dict, nr: int) -> tuple[np.ndarray, list[int]]:
    """Sichtbarkeit nach Schritt `nr` (1-basiert) und die in diesem Schritt neuen Exemplare."""
    sichtbar = np.zeros(szene.anzahl, bool)
    if szene.vorrichtung is not None:
        sichtbar[szene.vorrichtung] = True
    neu: list[int] = []
    for s in plan.get("schritte", []):
        if s["nr"] > nr:
            break
        ids = szene.exemplare_von(s.get("einbauten", []))
        sichtbar[ids] = True
        if s["nr"] == nr:
            neu = ids
    return sichtbar, neu
