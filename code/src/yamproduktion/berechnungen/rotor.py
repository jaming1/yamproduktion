"""Rotorauslegung einer Windkraftanlage aus der gewünschten Nennleistung.

Grundlage ist die Leistung im Wind P = ½·ρ·A·v³ und der Leistungsbeiwert cp,
der nach Betz höchstens 16/27 ≈ 0,593 betragen kann.

Rechenweg:
  1. Erforderliche Rotorfläche  A = 2·P_el / (ρ · cp · η · v³)
  2. Rotordurchmesser           D = √(4·A / π)
  3. Nenndrehzahl               n = λ · v / (π · D)            [1/s]
  4. Mechanische Rotorleistung  P_mech = P_el / η
  5. Rotordrehmoment            M = P_mech / (2·π·n)
  6. Rotorschub (Impulstheorie) cp = 4a(1−a)² → a;  cT = 4a(1−a);  T = ½·ρ·A·v²·cT
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .basis import Ergebnis, Feld, Groesse, Pruefung, Schritt, formatiere as f

BETZ_GRENZE = 16 / 27
TYP = "rotorauslegung"
TITEL = "Rotorauslegung aus Nennleistung"
KURZ = "Rotorauslegung"
BESCHREIBUNG = ("Aus der gewünschten Leistung den Rotordurchmesser, die Drehzahl, das Drehmoment und den Schub "
                "bestimmen. Ergebnis wird sofort neu berechnet.")
HAUPT = "D"

FELDER = [
    Feld("leistung_el_kw", "Elektrische Nennleistung", "kW", 0.1, 100, 0.5, 1, "Leistung am Generatorausgang bei Nennwind"),
    Feld("wind_nenn_ms", "Nennwindgeschwindigkeit", "m/s", 1, 30, 0.5, 1, "Wind, bei dem die Nennleistung erreicht wird"),
    Feld("luftdichte", "Luftdichte", "kg/m^3", 0.5, 1.5, 0.005, 3, "1,225 auf Meereshöhe bei 15 °C"),
    Feld("cp", "Leistungsbeiwert cp", "", 0.05, 0.99, 0.01, 2, "Anteil der Windleistung, den der Rotor nutzt (0,35–0,45)"),
    Feld("wirkungsgrad", "Wirkungsgrad Antriebsstrang", "", 0.1, 1.0, 0.01, 2, "Getriebe × Generator × Umrichter"),
    Feld("schnelllaufzahl", "Schnelllaufzahl λ", "", 0.5, 15, 0.5, 1, "Dreiblattrotor: 6 bis 8"),
]
BERECHNUNGS_QUELLEN: dict = {}

QUELLEN = [
    "A. Betz: Das Maximum der theoretisch möglichen Ausnützung des Windes durch Windmotoren, 1920",
    "R. Gasch, J. Twele: Windkraftanlagen – Grundlagen, Entwurf, Planung und Betrieb (Kap. Energiewandlung)",
    "Impulstheorie (Rankine-Froude): cp = 4a(1−a)², cT = 4a(1−a); z. B. Hau: Windkraftanlagen, Kap. 4",
]


# Einheiten der Eingabefelder (für die Übernahme aus Anforderungen)
FELD_EINHEITEN = {
    "leistung_el_kw": "kW",
    "wind_nenn_ms": "m/s",
    "luftdichte": "kg/m^3",
    "cp": "",
    "wirkungsgrad": "",
    "schnelllaufzahl": "",
}
# Lesbare Namen der Eingabefelder (für Rückverfolgung)
FELD_NAMEN = {
    "leistung_el_kw": "Nennleistung",
    "wind_nenn_ms": "Nennwind",
    "luftdichte": "Luftdichte",
    "cp": "Leistungsbeiwert",
    "wirkungsgrad": "Wirkungsgrad",
    "schnelllaufzahl": "Schnelllaufzahl",
}
# Suchbegriffe, um passende Anforderungen zu finden
FELD_SUCHBEGRIFFE = {
    "leistung_el_kw": "nennleistung",
    "wind_nenn_ms": "nennwind",
}


class EingabeFehler(ValueError):
    """Ungültige Eingabe mit verständlicher Erklärung."""


def induktion_aus_cp(cp: float) -> float:
    """Axialer Induktionsfaktor a ≤ 1/3 aus cp = 4a(1−a)² (Impulstheorie, Bisektion)."""
    cp = min(cp, BETZ_GRENZE)
    lo, hi = 0.0, 1 / 3
    for _ in range(80):
        mitte = (lo + hi) / 2
        if 4 * mitte * (1 - mitte) ** 2 < cp:
            lo = mitte
        else:
            hi = mitte
    return (lo + hi) / 2


@dataclass
class RotorEingaben:
    leistung_el_kw: float = 5.0        # elektrische Nennleistung
    wind_nenn_ms: float = 11.0         # Nennwindgeschwindigkeit
    luftdichte: float = 1.225          # kg/m³ (Normatmosphäre, Meereshöhe, 15 °C)
    cp: float = 0.40                   # Leistungsbeiwert des Rotors
    wirkungsgrad: float = 0.85         # Antriebsstrang + Generator + Umrichter
    schnelllaufzahl: float = 6.0       # λ = Blattspitzengeschwindigkeit / Windgeschwindigkeit

    def pruefen(self) -> None:
        if self.leistung_el_kw <= 0:
            raise EingabeFehler("Die Nennleistung muss größer als 0 kW sein.")
        if not 1 <= self.wind_nenn_ms <= 30:
            raise EingabeFehler("Die Nennwindgeschwindigkeit sollte zwischen 1 und 30 m/s liegen.")
        if not 0.5 <= self.luftdichte <= 1.5:
            raise EingabeFehler("Die Luftdichte liegt üblicherweise zwischen 0,9 und 1,3 kg/m³.")
        if not 0 < self.cp < 1:
            raise EingabeFehler("Der Leistungsbeiwert cp muss zwischen 0 und 1 liegen (realistisch 0,35–0,45).")
        if not 0 < self.wirkungsgrad <= 1:
            raise EingabeFehler("Der Wirkungsgrad muss zwischen 0 und 1 liegen (z. B. 0,85).")
        if not 0 < self.schnelllaufzahl <= 15:
            raise EingabeFehler("Die Schnelllaufzahl liegt üblicherweise zwischen 1 und 10 (Dreiblatt: 6–8).")


def berechne(e: RotorEingaben) -> Ergebnis:
    e.pruefen()

    p_el = e.leistung_el_kw * 1000.0          # W
    v, rho, cp, eta, lam = e.wind_nenn_ms, e.luftdichte, e.cp, e.wirkungsgrad, e.schnelllaufzahl

    flaeche = 2 * p_el / (rho * cp * eta * v**3)
    durchmesser = math.sqrt(4 * flaeche / math.pi)
    n_s = lam * v / (math.pi * durchmesser)   # 1/s
    n_min = n_s * 60
    p_mech = p_el / eta
    moment = p_mech / (2 * math.pi * n_s)
    v_spitze = lam * v
    p_wind = 0.5 * rho * flaeche * v**3
    a = induktion_aus_cp(cp)
    ct = 4 * a * (1 - a)
    schub = 0.5 * rho * flaeche * v**2 * ct

    eingaben = [
        Groesse("P_el", "Elektrische Nennleistung", e.leistung_el_kw, "kW"),
        Groesse("v", "Nennwindgeschwindigkeit", v, "m/s"),
        Groesse("ρ", "Luftdichte", rho, "kg/m³"),
        Groesse("cp", "Leistungsbeiwert", cp, "–"),
        Groesse("η", "Wirkungsgrad Antriebsstrang", eta, "–"),
        Groesse("λ", "Schnelllaufzahl", lam, "–"),
    ]

    schritte = [
        Schritt(
            "Erforderliche Rotorfläche",
            "A = 2·P_el / (ρ·cp·η·v³)",
            f"A = 2·{f(p_el)} W / ({f(rho)}·{f(cp)}·{f(eta)}·{f(v)}³ m³/s³)",
            Groesse("A", "Rotorfläche", flaeche, "m²"),
        ),
        Schritt(
            "Rotordurchmesser",
            "D = √(4·A / π)",
            f"D = √(4·{f(flaeche)} m² / π)",
            Groesse("D", "Rotordurchmesser", durchmesser, "m"),
        ),
        Schritt(
            "Nenndrehzahl des Rotors",
            "n = λ·v / (π·D)",
            f"n = {f(lam)}·{f(v)} m/s / (π·{f(durchmesser)} m) = {f(n_s)} 1/s",
            Groesse("n", "Nenndrehzahl", n_min, "1/min"),
        ),
        Schritt(
            "Mechanische Rotorleistung",
            "P_mech = P_el / η",
            f"P_mech = {f(p_el)} W / {f(eta)}",
            Groesse("P_mech", "Mechanische Rotorleistung", p_mech / 1000, "kW"),
        ),
        Schritt(
            "Drehmoment an der Rotorwelle",
            "M = P_mech / (2·π·n)",
            f"M = {f(p_mech)} W / (2·π·{f(n_s)} 1/s)",
            Groesse("M", "Rotordrehmoment", moment, "N·m"),
        ),
        Schritt(
            "Axialer Induktionsfaktor und Schubbeiwert (Impulstheorie)",
            "cp = 4·a·(1−a)²  →  a;   cT = 4·a·(1−a)",
            f"{f(cp)} = 4·a·(1−a)²  →  a = {f(a)};   cT = 4·{f(a)}·(1−{f(a)})",
            Groesse("cT", "Schubbeiwert", ct, "–"),
        ),
        Schritt(
            "Rotorschub bei Nennwind",
            "T = ½·ρ·A·v²·cT",
            f"T = ½·{f(rho)}·{f(flaeche)} m²·{f(v)}² m²/s²·{f(ct)}",
            Groesse("T", "Rotorschub bei Nennwind", schub, "N"),
        ),
    ]

    ergebnisse = [
        Groesse("D", "Rotordurchmesser", durchmesser, "m"),
        Groesse("A", "Rotorfläche", flaeche, "m²"),
        Groesse("n", "Nenndrehzahl", n_min, "1/min"),
        Groesse("M", "Rotordrehmoment", moment, "N·m"),
        Groesse("P_mech", "Mechanische Rotorleistung", p_mech / 1000, "kW"),
        Groesse("P_wind", "Leistung im Wind (Rotorfläche)", p_wind / 1000, "kW"),
        Groesse("v_tip", "Blattspitzengeschwindigkeit", v_spitze, "m/s"),
        Groesse("T", "Rotorschub bei Nennwind", schub, "N"),
        Groesse("cT", "Schubbeiwert", ct, "–"),
    ]

    pruefungen = [
        Pruefung(
            "Betz-Grenze",
            f"cp = {f(cp)} ≤ 16/27 ≈ 0,593",
            cp <= BETZ_GRENZE,
            "" if cp <= BETZ_GRENZE else "Kein Rotor kann mehr als 59,3 % der Windleistung entnehmen.",
        ),
        Pruefung(
            "Realistischer Leistungsbeiwert",
            f"cp = {f(cp)} ≤ 0,50",
            cp <= 0.50,
            "" if cp <= 0.50 else "Kleinwindanlagen erreichen in der Praxis meist cp = 0,35 bis 0,45.",
        ),
        Pruefung(
            "Blattspitzengeschwindigkeit (Lärm, Erosion)",
            f"v_tip = {f(v_spitze)} m/s ≤ 80 m/s",
            v_spitze <= 80,
            "" if v_spitze <= 80 else "Hohe Spitzengeschwindigkeit: Lärm und Erosion prüfen, λ verringern.",
        ),
    ]

    hinweise = [
        "Vorauslegung nach Energieerhaltung. Der Schub gilt für den Betrieb bei Nennwind; Bemessungslasten "
        "stehen in der Berechnung „Lastannahmen IEC 61400-2“.",
        "Luftdichte 1,225 kg/m³ gilt für Meereshöhe und 15 °C; für höher gelegene Standorte anpassen.",
    ]

    return Ergebnis(TITEL, TYP, eingaben, schritte, ergebnisse, pruefungen, QUELLEN, hinweise)
