"""Wälzlager-Lebensdauer der Rotorlagerung (Lastenheft M23).

Zwei Lager, Rotor überhängend (Lager B rotorseitig, Festlager nimmt den Schub auf):
  1. Lagerkräfte          F_rB = F·(l + a)/l;  F_rA = F·a/l    (F = Rotorgewicht)
  2. Äquivalente Last     P = F_r,  wenn F_a/F_r ≤ e;  sonst P = X·F_r + Y·F_a
  3. Nominelle Lebensdauer L10 = (C/P)^p  [10⁶ Umdrehungen];  p = 3 Kugellager, 10/3 Rollenlager
  4. Stunden              L10h = 10⁶·L10 / (60·n)
  5. Modifiziert          L_nm = a1·a_ISO·L10
"""
from __future__ import annotations

from dataclasses import dataclass

from .basis import Ergebnis, Feld, Groesse, Pruefung, Schritt, formatiere as f

TYP = "lager"
TITEL = "Wälzlager-Lebensdauer (ISO 281)"
KURZ = "Lager"
BESCHREIBUNG = ("Lebensdauer der beiden Rotorlager aus Rotorgewicht und Rotorschub. Die Tragzahlen C kommen aus dem "
                "Lagerkatalog des gewählten Lagers.")
HAUPT = "L10h,B"
LAGERARTEN = ("Kugellager (p = 3)", "Rollenlager (p = 10/3)")
# Lebensdauerbeiwert a1 für die Erlebenswahrscheinlichkeit (ISO 281)
A1 = {"90 %": 1.0, "95 %": 0.64, "96 %": 0.55, "97 %": 0.47, "98 %": 0.37, "99 %": 0.25}

QUELLEN = [
    "ISO 281:2007 Wälzlager – Dynamische Tragzahlen und nominelle Lebensdauer: L10 = (C/P)^p, a1-Werte",
    "Lagerkataloge (z. B. Schaeffler, SKF): Faktoren e, X, Y je Lagerreihe, Lebensdauerbeiwert a_ISO",
    "Technische Mechanik: Auflagerkräfte eines Trägers mit Überhang",
]

FELDER = [
    Feld("masse_kg", "Rotormasse (überhängend)", "kg", 0, 1e5, 1, 1, "aus den Lastannahmen"),
    Feld("a_m", "Überhang a (Rotor bis Lager B)", "m", 0.01, 5, 0.01, 3, ""),
    Feld("l_m", "Lagerabstand l", "m", 0.02, 5, 0.01, 3, ""),
    Feld("f_ax", "Axialkraft im Betrieb (Rotorschub)", "N", 0, 1e7, 10, 1, "Schub bei Nennwind aus der Rotorauslegung"),
    Feld("n_rpm", "Drehzahl", "1/min", 1, 10000, 5, 1, "Nenndrehzahl des Rotors"),
    Feld("art", "Lagerart", "", auswahl=LAGERARTEN),
    Feld("c_b", "Dyn. Tragzahl Lager B (rotorseitig, Festlager)", "kN", 0.1, 5000, 1, 1, "aus dem Katalog"),
    Feld("c_a", "Dyn. Tragzahl Lager A (Loslager)", "kN", 0.1, 5000, 1, 1, "aus dem Katalog"),
    Feld("e_b", "Grenzwert e (Lager B)", "", 0.01, 3, 0.01, 2, "Katalog; Rillenkugellager je nach F_a/C0 0,2–0,44"),
    Feld("x_b", "Radialfaktor X (Lager B)", "", 0, 2, 0.01, 2, "Katalog; Rillenkugellager 0,56"),
    Feld("y_b", "Axialfaktor Y (Lager B)", "", 0, 5, 0.05, 2, "Katalog; Rillenkugellager 1,0–2,3"),
    Feld("zuverlaessigkeit", "Erlebenswahrscheinlichkeit", "", auswahl=tuple(A1), tipp="90 % = übliche L10"),
    Feld("a_iso", "Lebensdauerbeiwert a_ISO", "", 0.1, 50, 0.1, 2,
         "Schmierung, Sauberkeit, Ermüdungsgrenze – Katalog-Rechner; ohne Angabe 1,0"),
    Feld("lebensdauer_a", "Geforderte Lebensdauer", "a", 1, 50, 1, 0, "aus den Anforderungen"),
    Feld("stunden_jahr", "Betriebsstunden je Jahr", "h", 100, 8760, 100, 0,
         "Zeit, in der der Rotor dreht (Anteil über Einschaltwind, siehe Ertrag)"),
]
FELD_EINHEITEN = {x.attr: x.einheit for x in FELDER if not x.auswahl}
FELD_NAMEN = {x.attr: x.name for x in FELDER}
FELD_SUCHBEGRIFFE = {"lebensdauer_a": "lebensdauer"}
BERECHNUNGS_QUELLEN = {
    "masse_kg": ("lasten_iec", "m_r"),
    "a_m": ("lasten_iec", "L_rb"),
    "f_ax": ("rotorauslegung", "T"),
    "n_rpm": ("rotorauslegung", "n"),
}


class EingabeFehler(ValueError):
    pass


@dataclass
class LagerEingaben:
    masse_kg: float = 45.0
    a_m: float = 0.30
    l_m: float = 0.40
    f_ax: float = 620.0
    n_rpm: float = 263.0
    art: str = LAGERARTEN[0]
    c_b: float = 30.7
    c_a: float = 30.7
    e_b: float = 0.22
    x_b: float = 0.56
    y_b: float = 2.0
    zuverlaessigkeit: str = "90 %"
    a_iso: float = 1.0
    lebensdauer_a: float = 20
    stunden_jahr: float = 6000

    def pruefen(self) -> None:
        if self.art not in LAGERARTEN or self.zuverlaessigkeit not in A1:
            raise EingabeFehler("Ungültige Auswahl bei Lagerart oder Erlebenswahrscheinlichkeit.")
        if self.l_m <= 0 or self.n_rpm <= 0 or self.c_a <= 0 or self.c_b <= 0:
            raise EingabeFehler("Lagerabstand, Drehzahl und Tragzahlen müssen größer als 0 sein.")


def lebensdauer(c_kn: float, p_n: float, exponent: float) -> float:
    """L10 in 10⁶ Umdrehungen."""
    if p_n <= 0:
        return float("inf")
    return (c_kn * 1000 / p_n) ** exponent


def stunden(l10: float, n_rpm: float) -> float:
    return l10 * 1e6 / (60 * n_rpm)


def berechne(e: LagerEingaben) -> Ergebnis:
    e.pruefen()
    p_exp = 3.0 if e.art == LAGERARTEN[0] else 10 / 3
    F = e.masse_kg * 9.81
    fr_b = F * (e.l_m + e.a_m) / e.l_m
    fr_a = F * e.a_m / e.l_m
    fa = e.f_ax
    if fr_b > 0 and fa / fr_b <= e.e_b:
        p_b = fr_b
        p_text = f"F_a/F_r = {f(fa / fr_b, 3)} ≤ e = {f(e.e_b)} → P = F_r"
    else:
        p_b = e.x_b * fr_b + e.y_b * fa
        p_text = f"F_a/F_r = {f(fa / fr_b, 3) if fr_b else '∞'} > e → P = {f(e.x_b)}·{f(fr_b)} + {f(e.y_b)}·{f(fa)} N"
    p_a = fr_a
    l10_b = lebensdauer(e.c_b, p_b, p_exp)
    l10_a = lebensdauer(e.c_a, p_a, p_exp)
    a1 = A1[e.zuverlaessigkeit]
    lh_b = stunden(l10_b, e.n_rpm)
    lh_a = stunden(l10_a, e.n_rpm)
    lnm_b = stunden(a1 * e.a_iso * l10_b, e.n_rpm)
    lnm_a = stunden(a1 * e.a_iso * l10_a, e.n_rpm)
    soll = e.lebensdauer_a * e.stunden_jahr

    eingaben = [
        Groesse("m", "Rotormasse", e.masse_kg, "kg"),
        Groesse("a", "Überhang", e.a_m, "m"),
        Groesse("l", "Lagerabstand", e.l_m, "m"),
        Groesse("F_a", "Axialkraft (Festlager B)", fa, "N"),
        Groesse("n", "Drehzahl", e.n_rpm, "1/min"),
        Groesse("p", f"Lebensdauerexponent ({e.art})", p_exp, "–"),
        Groesse("C_B", "Dyn. Tragzahl Lager B", e.c_b, "kN"),
        Groesse("C_A", "Dyn. Tragzahl Lager A", e.c_a, "kN"),
        Groesse("a1", f"Beiwert Erlebenswahrscheinlichkeit {e.zuverlaessigkeit}", a1, "–"),
        Groesse("a_ISO", "Lebensdauerbeiwert", e.a_iso, "–"),
    ]
    S = Schritt
    schritte = [
        S("Radialkraft Lager B (rotorseitig)", "F_rB = m·g·(l + a)/l", f"F_rB = {f(F)} N·({f(e.l_m)} + {f(e.a_m)})/{f(e.l_m)}",
          Groesse("F_rB", "Radialkraft Lager B", fr_b, "N")),
        S("Radialkraft Lager A (Gegenlager, nach unten)", "F_rA = m·g·a/l", f"F_rA = {f(F)} N·{f(e.a_m)}/{f(e.l_m)}",
          Groesse("F_rA", "Radialkraft Lager A", fr_a, "N")),
        S("Äquivalente Last Lager B", "P = F_r (F_a/F_r ≤ e), sonst P = X·F_r + Y·F_a", p_text,
          Groesse("P_B", "Äquivalente Last Lager B", p_b, "N")),
        S("Nominelle Lebensdauer Lager B", "L10 = (C/P)^p", f"L10 = ({f(e.c_b * 1000)} N / {f(p_b)} N)^{f(p_exp)}",
          Groesse("L10,B", "Lebensdauer Lager B", l10_b, "10⁶ U")),
        S("Lebensdauer in Stunden Lager B", "L10h = 10⁶·L10/(60·n)", f"L10h = 10⁶·{f(l10_b)}/(60·{f(e.n_rpm)})",
          Groesse("L10h,B", "Lebensdauer Lager B", lh_b, "h")),
        S("Modifizierte Lebensdauer Lager B", "L_nmh = a1·a_ISO·L10h", f"L_nmh = {f(a1)}·{f(e.a_iso)}·{f(lh_b)} h",
          Groesse("L_nmh,B", "Modifizierte Lebensdauer Lager B", lnm_b, "h")),
        S("Lebensdauer Lager A", "L10h = 10⁶·(C/P)^p/(60·n)", f"L10h = 10⁶·({f(e.c_a * 1000)}/{f(p_a)})^{f(p_exp)}/(60·{f(e.n_rpm)})",
          Groesse("L10h,A", "Lebensdauer Lager A", lh_a, "h")),
        S("Geforderte Betriebsdauer", "L_soll = Lebensdauer · Betriebsstunden je Jahr",
          f"L_soll = {f(e.lebensdauer_a)} a · {f(e.stunden_jahr)} h/a", Groesse("L_soll", "Geforderte Betriebsdauer", soll, "h")),
    ]
    ergebnisse = [
        Groesse("L10h,B", "Lebensdauer Lager B (rotorseitig)", lh_b, "h"),
        Groesse("L_nmh,B", "Modifizierte Lebensdauer Lager B", lnm_b, "h"),
        Groesse("L10h,A", "Lebensdauer Lager A", lh_a, "h"),
        Groesse("L_nmh,A", "Modifizierte Lebensdauer Lager A", lnm_a, "h"),
        Groesse("L_soll", "Geforderte Betriebsdauer", soll, "h"),
        Groesse("P_B", "Äquivalente Last Lager B", p_b, "N"),
        Groesse("F_rB", "Radialkraft Lager B", fr_b, "N"),
        Groesse("F_rA", "Radialkraft Lager A", fr_a, "N"),
    ]
    pruefungen = [
        Pruefung("Lager B hält die geforderte Dauer", f"L_nmh,B = {f(lnm_b)} h ≥ {f(soll)} h", lnm_b >= soll,
                 "" if lnm_b >= soll else "Größeres Lager (höheres C) oder Rollenlager wählen."),
        Pruefung("Lager A hält die geforderte Dauer", f"L_nmh,A = {f(lnm_a)} h ≥ {f(soll)} h", lnm_a >= soll,
                 "" if lnm_a >= soll else "Größeres Lager wählen."),
    ]
    hinweise = [
        "Lebensdauer mit Betriebslasten (Rotorgewicht, Schub bei Nennwind) ohne γ_f. Die statische Tragfähigkeit "
        "(C0 gegen Bemessungslast aus den Lastannahmen) bitte mit dem Katalogwert C0 prüfen: s0 = C0/P0 ≥ 2.",
        "Biegemomente aus Lastfall A (Gieren, Schub außermittig) sind nicht als Lagerlast angesetzt – konservativ wäre "
        "ein Betriebsfaktor von 1,2–1,5 auf P.",
        "Die Tragzahlen sind Platzhalter (Größenordnung eines Rillenkugellagers mit 40 mm Bohrung) – Katalogwert des gewählten Lagers eintragen.",
    ]
    return Ergebnis(TITEL, TYP, eingaben, schritte, ergebnisse, pruefungen, QUELLEN, hinweise)
