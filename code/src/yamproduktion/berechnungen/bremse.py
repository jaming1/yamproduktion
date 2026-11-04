"""Mechanische Rotorbremse (Scheibenbremse) — Bremsmoment, Bremszeit, Wärme.

  Moment an der Rotorwelle:  M_Br,R = M_Br·i  (Bremse auf schneller Welle mit Übersetzung i)
  Verzögerung (konstant):    t = J·ω / (M_Br,R − Q)
  Bremswinkel:               φ = ω·t/2
  Wärme:                     E = ½·J·ω² + Q·φ
  Erwärmung Scheibe:         ΔT = E/(m·c)
  Zuspannkraft je Belag:     F_N = M_Br / (n_Bel·μ·r_m)
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .basis import Ergebnis, Feld, Groesse, Pruefung, Schritt, formatiere as f

TYP = "bremse"
TITEL = "Rotorbremse (Scheibenbremse)"
KURZ = "Bremse"
BESCHREIBUNG = ("Hält die Bremse den Rotor bei Überdrehzahl an? Bremszeit, Bremswinkel, Wärme in der Scheibe "
                "und Zuspannkraft des Bremssattels.")
HAUPT = "t_Br"
C_STAHL = 460.0

QUELLEN = [
    "Technische Mechanik, Drallsatz: J·dω/dt = −(M_Br − Q); Energiesatz E = ½·J·ω² + ∫Q dφ",
    "IEC 61400-2 Abschnitt 8 (Schutz- und Sicherheitssystem): Rotor muss aus jedem Betriebszustand sicher "
    "in einen ungefährlichen Zustand gebracht werden",
    "Scheibenbremse: Reibmoment M = n_Bel·μ·F_N·r_m (Roloff/Matek, Kap. Kupplungen und Bremsen)",
]

FELDER = [
    Feld("j_kgm2", "Trägheitsmoment Rotor J", "kg*m^2", 0.1, 1e5, 1, 1, "Näherung: B·m_Blatt·R²/3 + Nabe"),
    Feld("n_rpm", "Drehzahl bei Bremsbeginn", "1/min", 10, 3000, 5, 1, "Überdrehzahl aus Lastannahmen"),
    Feld("q_nm", "Antreibendes Rotormoment beim Bremsen", "N*m", 0, 1e6, 10, 1, "Nennmoment; vorsichtig höher"),
    Feld("m_br", "Bremsmoment an der Bremswelle", "N*m", 1, 1e6, 10, 1, "Katalogwert des Bremssattels"),
    Feld("i_br", "Übersetzung Rotor → Bremswelle", "", 1, 200, 0.1, 2, "1 bei Bremse auf der Rotorwelle"),
    Feld("s_min", "Geforderter Faktor M_Br/Q", "", 1, 5, 0.1, 2, "Richtwert ≥ 2"),
    Feld("t_max", "Zulässige Bremszeit", "s", 0.5, 60, 0.5, 1, ""),
    Feld("m_scheibe", "Masse Bremsscheibe", "kg", 0.1, 500, 0.1, 2, ""),
    Feld("dt_zul", "Zulässige Erwärmung Scheibe", "K", 20, 600, 10, 0, "Richtwert ≤ 200 K je Bremsung"),
    Feld("mu", "Reibwert Belag μ", "", 0.1, 0.6, 0.01, 2, "Sinterbelag ≈ 0,35–0,45"),
    Feld("r_m", "Mittlerer Reibradius r_m", "mm", 20, 1000, 1, 1, ""),
    Feld("n_bel", "Anzahl Reibflächen", "", 1, 8, 1, 0, "ein Sattel mit zwei Belägen: 2"),
]
FELD_EINHEITEN = {x.attr: x.einheit for x in FELDER if not x.auswahl}
FELD_NAMEN = {x.attr: x.name for x in FELDER}
FELD_SUCHBEGRIFFE: dict = {}
BERECHNUNGS_QUELLEN = {"n_rpm": ("lasten_iec", "n_max"), "q_nm": ("rotorauslegung", "M")}


class EingabeFehler(ValueError):
    pass


@dataclass
class BremsEingaben:
    j_kgm2: float = 120.0
    n_rpm: float = 395.0
    q_nm: float = 190.0
    m_br: float = 800.0
    i_br: float = 1.0
    s_min: float = 2.0
    t_max: float = 10.0
    m_scheibe: float = 8.0
    dt_zul: float = 200.0
    mu: float = 0.4
    r_m: float = 150.0
    n_bel: float = 2

    def pruefen(self) -> None:
        if self.m_br * self.i_br <= self.q_nm:
            raise EingabeFehler("Das Bremsmoment ist kleiner als das antreibende Rotormoment: der Rotor wird nicht langsamer.")


def berechne(e: BremsEingaben) -> Ergebnis:
    e.pruefen()
    w = 2 * math.pi * e.n_rpm / 60
    M_R = e.m_br * e.i_br
    t = e.j_kgm2 * w / (M_R - e.q_nm)
    phi = w * t / 2
    E_kin = 0.5 * e.j_kgm2 * w**2
    E = E_kin + e.q_nm * phi
    dT = E / (e.m_scheibe * C_STAHL)
    n_bel = int(round(e.n_bel))
    F_N = e.m_br * 1000 / (n_bel * e.mu * e.r_m)
    faktor = M_R / e.q_nm if e.q_nm else float("inf")

    eingaben = [
        Groesse("J", "Trägheitsmoment Rotor", e.j_kgm2, "kg·m²"), Groesse("n", "Drehzahl bei Bremsbeginn", e.n_rpm, "1/min"),
        Groesse("Q", "Antreibendes Rotormoment", e.q_nm, "N·m"), Groesse("M_Br", "Bremsmoment an der Bremswelle", e.m_br, "N·m"),
        Groesse("i", "Übersetzung", e.i_br, "–"), Groesse("m_S", "Masse Bremsscheibe", e.m_scheibe, "kg"),
        Groesse("c", "Wärmekapazität Stahl", C_STAHL, "J/(kg·K)"), Groesse("μ", "Reibwert", e.mu, "–"),
        Groesse("r_m", "Reibradius", e.r_m, "mm"), Groesse("n_Bel", "Reibflächen", n_bel, "–"),
    ]
    S = Schritt
    schritte = [
        S("Winkelgeschwindigkeit", "ω = 2π·n/60", f"ω = 2π·{f(e.n_rpm)}/60", Groesse("ω", "Winkelgeschwindigkeit", w, "1/s")),
        S("Bremsmoment an der Rotorwelle", "M_Br,R = M_Br·i", f"M_Br,R = {f(e.m_br)}·{f(e.i_br)}", Groesse("M_Br,R", "Bremsmoment Rotorwelle", M_R, "N·m")),
        S("Bremszeit", "t = J·ω/(M_Br,R − Q)", f"t = {f(e.j_kgm2)}·{f(w)}/({f(M_R)} − {f(e.q_nm)})", Groesse("t_Br", "Bremszeit", t, "s")),
        S("Bremswinkel", "φ = ω·t/2", f"φ = {f(w)}·{f(t)}/2 = {f(phi)} rad", Groesse("U", "Umdrehungen bis Stillstand", phi / (2 * math.pi), "–")),
        S("Wärme", "E = ½·J·ω² + Q·φ", f"E = ½·{f(e.j_kgm2)}·{f(w)}² + {f(e.q_nm)}·{f(phi)}", Groesse("E", "Bremsenergie", E / 1000, "kJ")),
        S("Erwärmung der Scheibe (ohne Wärmeabgabe)", "ΔT = E/(m·c)", f"ΔT = {f(E)}/({f(e.m_scheibe)}·{f(C_STAHL)})",
          Groesse("ΔT", "Erwärmung", dT, "K")),
        S("Zuspannkraft je Reibfläche", "F_N = M_Br/(n_Bel·μ·r_m)", f"F_N = {f(e.m_br)}·10³/({n_bel}·{f(e.mu)}·{f(e.r_m)})",
          Groesse("F_N", "Zuspannkraft", F_N, "N")),
    ]
    ergebnisse = [
        Groesse("t_Br", "Bremszeit", t, "s"),
        Groesse("U", "Umdrehungen bis Stillstand", phi / (2 * math.pi), "–"),
        Groesse("E", "Bremsenergie", E / 1000, "kJ"),
        Groesse("ΔT", "Erwärmung Scheibe", dT, "K"),
        Groesse("F_N", "Zuspannkraft je Reibfläche", F_N, "N"),
        Groesse("M_Br,R", "Bremsmoment an der Rotorwelle", M_R, "N·m"),
        Groesse("M_Br/Q", "Bremsmomentfaktor", faktor, "–"),
    ]
    pruefungen = [
        Pruefung("Bremsmoment ausreichend (Richtwert)", f"M_Br,R/Q = {f(faktor, 3)} ≥ {f(e.s_min)}", faktor >= e.s_min),
        Pruefung("Bremszeit", f"t = {f(t, 3)} s ≤ {f(e.t_max)} s", t <= e.t_max),
        Pruefung("Erwärmung (Richtwert)", f"ΔT = {f(dT, 3)} K ≤ {f(e.dt_zul)} K", dT <= e.dt_zul),
    ]
    hinweise = [
        "Annahme: antreibendes Rotormoment Q bleibt während des Bremsens konstant (konservativ, da es mit der Drehzahl sinkt).",
        "Das Bremsmoment beansprucht Welle, Passfeder und Getriebe; den Wert M_Br,R dort als Lastfall einsetzen.",
    ]
    unbelegt = ["Faktor M_Br/Q ≥ 2 und ΔT ≤ 200 K sind Richtwerte ohne Normbeleg."]
    return Ergebnis(TITEL, TYP, eingaben, schritte, ergebnisse, pruefungen, QUELLEN, hinweise, unbelegt=unbelegt)
