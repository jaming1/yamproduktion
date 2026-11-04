"""Hochfeste Schraubenverbindung, vereinfacht nach VDI 2230 Blatt 1 (Lastenheft M24).

Rechenweg:
  1. Gewindemaße           d2 = d − 0,6495·P;  d3 = d − 1,2269·P;  A_s aus Tabelle (ISO 898-1)
  2. Zul. Montagevorspannkraft  F_Mzul = ν·R_p0,2·A_0 / √(1 + 3·[3/2·(d2/d0)·(P/(π·d2) + 1,155·µ_G)]²)
                                (A_0 = A_s, d0 = (d2 + d3)/2, Ausnutzung ν = 0,9)
  3. Anziehmoment          M_A = F_Mzul·(0,16·P + 0,58·d2·µ_G + D_Km/2·µ_K)
  4. Klemmkraftbedarf      F_Kerf = F_Q/(q_F·µ_T) ;  F_Mmin = F_Kerf + (1 − Φ)·F_A + F_Z ;  F_Mmax = α_A·F_Mmin ≤ F_Mzul
  5. Max. Schraubenkraft   F_Smax = F_Mzul + Φ·F_A;  σ_red,B ≤ R_p0,2 (vereinfacht: F_Smax/A_s)
  6. Dauerhaltbarkeit      σ_a = Φ·F_A/(2·A_s) ≤ σ_ASV = 0,85·(150/d + 45)  (schlussgerollt, MPa, d in mm)
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .basis import Ergebnis, Feld, Groesse, Pruefung, Schritt, formatiere as f

TYP = "schrauben"
TITEL = "Schraubenverbindung (vereinfacht nach VDI 2230)"
KURZ = "Schrauben"
BESCHREIBUNG = ("Vorspannkraft, Anziehmoment, Klemmkraft und Dauerhaltbarkeit einer hochfesten Schraube – "
                "z. B. für den Turmflansch oder die Nabenbefestigung.")
HAUPT = "M_A"

# Regelgewinde: Steigung P in mm, Spannungsquerschnitt A_s in mm² (ISO 898-1 / ISO 724)
GEWINDE = {
    "M6": (1.0, 20.1), "M8": (1.25, 36.6), "M10": (1.5, 58.0), "M12": (1.75, 84.3), "M16": (2.0, 157.0),
    "M20": (2.5, 245.0), "M24": (3.0, 353.0), "M30": (3.5, 561.0), "M36": (4.0, 817.0),
}
# Festigkeitsklasse: R_p0,2 in MPa (ISO 898-1, Mindestwerte; 8.8 für d ≤ 16 / d > 16)
KLASSEN = ("8.8", "10.9", "12.9")


def rp02(klasse: str, d: float) -> float:
    if klasse == "8.8":
        return 640.0 if d <= 16 else 660.0
    return {"10.9": 940.0, "12.9": 1100.0}[klasse]


QUELLEN = [
    "VDI 2230 Blatt 1:2015 Systematische Berechnung hochbeanspruchter Schraubenverbindungen (Gleichungen für "
    "F_Mzul, M_A, σ_ASV)",
    "ISO 898-1: Mechanische Eigenschaften von Schrauben (R_p0,2 je Festigkeitsklasse), Spannungsquerschnitte A_s",
    "Roloff/Matek Maschinenelemente, Kap. Schraubenverbindungen",
]

FELDER = [
    Feld("gewinde", "Gewinde", "", auswahl=tuple(GEWINDE)),
    Feld("klasse", "Festigkeitsklasse", "", auswahl=KLASSEN),
    Feld("anzahl", "Anzahl Schrauben", "", 1, 200, 1, 0, "z. B. Schrauben am Turmflansch"),
    Feld("f_a", "Axiale Betriebskraft je Schraube F_A", "N", 0, 1e7, 100, 1, "Zug in Schraubenachse (aus Turm & Fundament)"),
    Feld("f_q", "Querkraft gesamt F_Q", "N", 0, 1e7, 100, 1, "wird über Reibung übertragen"),
    Feld("mu_g", "Reibwert Gewinde µ_G", "", 0.04, 0.3, 0.01, 2, "geschmiert 0,10–0,14"),
    Feld("mu_k", "Reibwert Kopfauflage µ_K", "", 0.04, 0.3, 0.01, 2, ""),
    Feld("mu_t", "Reibwert Trennfuge µ_T", "", 0.05, 0.6, 0.01, 2, "Stahl/Stahl trocken ≈ 0,15–0,2"),
    Feld("phi", "Kraftverhältnis Φ_n", "", 0.01, 0.5, 0.01, 2, "Anteil von F_A, der in die Schraube geht (oft 0,05–0,15)"),
    Feld("f_z", "Vorspannkraftverlust durch Setzen F_Z", "N", 0, 1e6, 100, 0, "Richtwert ≈ 5–10 % der Vorspannkraft"),
    Feld("alpha_a", "Anziehfaktor α_A", "", 1.0, 4.0, 0.1, 1, "Drehmomentschlüssel 1,4–1,6 · Schlagschrauber 2,5–4"),
    Feld("d_km", "Reibdurchmesser Kopfauflage D_Km", "mm", 3, 200, 0.5, 1, "≈ (Kopfauflage-Ø + Bohrung)/2"),
]
FELD_EINHEITEN = {x.attr: x.einheit for x in FELDER if not x.auswahl}
FELD_NAMEN = {x.attr: x.name for x in FELDER}
FELD_SUCHBEGRIFFE: dict = {}
BERECHNUNGS_QUELLEN = {"f_a": ("turm", "F_A,Schraube"), "anzahl": ("turm", "n_S")}


class EingabeFehler(ValueError):
    pass


@dataclass
class SchraubenEingaben:
    gewinde: str = "M16"
    klasse: str = "10.9"
    anzahl: float = 12
    f_a: float = 15000.0
    f_q: float = 3000.0
    mu_g: float = 0.12
    mu_k: float = 0.12
    mu_t: float = 0.15
    phi: float = 0.10
    f_z: float = 5000.0
    alpha_a: float = 1.6
    d_km: float = 20.5

    def pruefen(self) -> None:
        if self.gewinde not in GEWINDE or self.klasse not in KLASSEN:
            raise EingabeFehler("Bitte Gewinde und Festigkeitsklasse aus der Liste wählen.")
        if int(self.anzahl) < 1:
            raise EingabeFehler("Mindestens eine Schraube.")


def f_m_zul(d: float, p: float, a_s: float, rp: float, mu_g: float, nu: float = 0.9) -> float:
    d2 = d - 0.6495 * p
    d3 = d - 1.2269 * p
    d0 = (d2 + d3) / 2
    klammer = 1.5 * d2 / d0 * (p / (math.pi * d2) + 1.155 * mu_g)
    return nu * rp * a_s / math.sqrt(1 + 3 * klammer**2)


def berechne(e: SchraubenEingaben) -> Ergebnis:
    e.pruefen()
    d = float(e.gewinde[1:])
    p, a_s = GEWINDE[e.gewinde]
    rp = rp02(e.klasse, d)
    d2 = d - 0.6495 * p
    d3 = d - 1.2269 * p
    n = int(round(e.anzahl))
    fm = f_m_zul(d, p, a_s, rp, e.mu_g)
    m_a = fm * (0.16 * p + 0.58 * d2 * e.mu_g + e.d_km / 2 * e.mu_k) / 1000     # N·m
    q_f = n
    f_kerf = e.f_q / (q_f * e.mu_t) if e.f_q else 0.0
    f_m_min = f_kerf + (1 - e.phi) * e.f_a + e.f_z
    f_m_max = e.alpha_a * f_m_min
    f_s_max = fm + e.phi * e.f_a
    s_max = f_s_max / a_s
    s_a = e.phi * e.f_a / (2 * a_s)
    s_asv = 0.85 * (150 / d + 45)
    s_d = s_asv / s_a if s_a > 0 else float("inf")

    eingaben = [
        Groesse("d", f"Gewinde {e.gewinde}, Festigkeitsklasse {e.klasse}", d, "mm"),
        Groesse("P", "Steigung", p, "mm"),
        Groesse("A_s", "Spannungsquerschnitt", a_s, "mm²"),
        Groesse("R_p0,2", "Mindest-Dehngrenze", rp, "MPa"),
        Groesse("n", "Anzahl Schrauben", n, "–"),
        Groesse("F_A", "Axiale Betriebskraft je Schraube", e.f_a, "N"),
        Groesse("F_Q", "Querkraft gesamt", e.f_q, "N"),
        Groesse("µ_G", "Reibwert Gewinde", e.mu_g, "–"),
        Groesse("µ_K", "Reibwert Kopfauflage", e.mu_k, "–"),
        Groesse("µ_T", "Reibwert Trennfuge", e.mu_t, "–"),
        Groesse("Φ_n", "Kraftverhältnis", e.phi, "–"),
        Groesse("F_Z", "Setzverlust", e.f_z, "N"),
        Groesse("α_A", "Anziehfaktor", e.alpha_a, "–"),
        Groesse("D_Km", "Reibdurchmesser Kopf", e.d_km, "mm"),
    ]
    S = Schritt
    schritte = [
        S("Flanken- und Kerndurchmesser", "d2 = d − 0,6495·P;  d3 = d − 1,2269·P",
          f"d2 = {f(d)} − 0,6495·{f(p)};  d3 = {f(d)} − 1,2269·{f(p)} = {f(d3)} mm", Groesse("d2", "Flankendurchmesser", d2, "mm")),
        S("Zulässige Montagevorspannkraft (ν = 0,9)",
          "F_Mzul = ν·R_p0,2·A_s / √(1 + 3·[3/2·(d2/d0)·(P/(π·d2) + 1,155·µ_G)]²)",
          f"F_Mzul = 0,9·{f(rp)} MPa·{f(a_s)} mm² / √(…), d0 = {f((d2 + d3) / 2)} mm",
          Groesse("F_Mzul", "Zulässige Montagevorspannkraft", fm, "N")),
        S("Anziehmoment", "M_A = F_Mzul·(0,16·P + 0,58·d2·µ_G + D_Km/2·µ_K)",
          f"M_A = {f(fm)} N·(0,16·{f(p)} + 0,58·{f(d2)}·{f(e.mu_g)} + {f(e.d_km)}/2·{f(e.mu_k)}) mm",
          Groesse("M_A", "Anziehmoment", m_a, "N·m")),
        S("Erforderliche Klemmkraft gegen Rutschen", "F_Kerf = F_Q/(n·µ_T)", f"F_Kerf = {f(e.f_q)}/({n}·{f(e.mu_t)})",
          Groesse("F_Kerf", "Klemmkraftbedarf je Schraube", f_kerf, "N")),
        S("Mindest- und Höchst-Montagevorspannkraft", "F_Mmin = F_Kerf + (1 − Φ)·F_A + F_Z;  F_Mmax = α_A·F_Mmin",
          f"F_Mmin = {f(f_kerf)} + (1 − {f(e.phi)})·{f(e.f_a)} + {f(e.f_z)} = {f(f_m_min)} N;  F_Mmax = {f(e.alpha_a)}·{f(f_m_min)}",
          Groesse("F_Mmax", "Höchste Montagevorspannkraft", f_m_max, "N")),
        S("Maximale Schraubenkraft", "F_Smax = F_Mzul + Φ·F_A;  σ = F_Smax/A_s",
          f"F_Smax = {f(fm)} + {f(e.phi)}·{f(e.f_a)} = {f(f_s_max)} N", Groesse("σ_max", "Max. Spannung im Gewinde", s_max, "MPa")),
        S("Ausschlagspannung und Dauerhaltbarkeit", "σ_a = Φ·F_A/(2·A_s);  σ_ASV = 0,85·(150/d + 45)",
          f"σ_a = {f(e.phi)}·{f(e.f_a)}/(2·{f(a_s)});  σ_ASV = 0,85·(150/{f(d)} + 45) = {f(s_asv)} MPa",
          Groesse("σ_a", "Ausschlagspannung", s_a, "MPa")),
    ]
    ergebnisse = [
        Groesse("M_A", "Anziehmoment", m_a, "N·m"),
        Groesse("F_Mzul", "Zulässige Montagevorspannkraft", fm, "N"),
        Groesse("F_Mmax", "Erforderliche Höchst-Montagevorspannkraft", f_m_max, "N"),
        Groesse("F_Kerf", "Klemmkraftbedarf je Schraube", f_kerf, "N"),
        Groesse("σ_max", "Max. Spannung im Gewinde", s_max, "MPa"),
        Groesse("σ_a", "Ausschlagspannung", s_a, "MPa"),
        Groesse("σ_ASV", "Dauerhaltbarkeit (schlussgerollt)", s_asv, "MPa"),
        Groesse("S_D", "Sicherheit Dauerhaltbarkeit", s_d, "–"),
    ]
    pruefungen = [
        Pruefung("Vorspannkraft reicht", f"F_Mmax = {f(f_m_max)} N ≤ F_Mzul = {f(fm)} N", f_m_max <= fm,
                 "" if f_m_max <= fm else "Größere Schraube, höhere Festigkeitsklasse, mehr Schrauben oder genaueres Anziehverfahren."),
        Pruefung("Keine Überlastung im Betrieb", f"σ_max = {f(s_max)} MPa ≤ R_p0,2 = {f(rp)} MPa", s_max <= rp),
        Pruefung("Dauerhaltbarkeit", f"σ_a = {f(s_a)} MPa ≤ σ_ASV = {f(s_asv)} MPa", s_a <= s_asv),
    ]
    hinweise = [
        "Vereinfachung: Φ_n und F_Z sind Eingaben statt aus Nachgiebigkeiten von Schraube und Platten berechnet; "
        "Flächenpressung unter dem Kopf ist nicht nachgewiesen.",
        "Für die Montage: Anziehmoment M_A mit Drehmomentschlüssel, Reibwerte nur gültig für den angegebenen Schmierzustand.",
    ]
    unbelegt = ["Die Prüfung mit einem Literatur-Rechenbeispiel aus VDI 2230 / Roloff-Matek (N5) steht noch aus."]
    return Ergebnis(TITEL, TYP, eingaben, schritte, ergebnisse, pruefungen, QUELLEN, hinweise, unbelegt=unbelegt)
