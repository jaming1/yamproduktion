"""Leistungskurve und Jahresenergieertrag (Lastenheft M18).

Rechenweg:
  1. Wind auf Nabenhöhe (Potenzgesetz nach Hellmann)  v_N = v_M · (h_N / h_M)^α
  2. Weibull-Skalenparameter                          c = v_N / Γ(1 + 1/k)      (k = 2: Rayleigh)
  3. Leistungskurve                                   P(v) = min(P_n, ½·ρ·A·cp·η·v³)  für v_ein ≤ v < v_ab
  4. Mittlere Leistung                                P̄ = ∫ P(v)·f(v) dv   mit f(v) = k/c·(v/c)^(k−1)·e^(−(v/c)^k)
  5. Jahresertrag                                     E = P̄ · 8760 h · Verfügbarkeit
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .basis import Ergebnis, Feld, Groesse, Pruefung, Schritt, formatiere as f

TYP = "ertrag"
TITEL = "Leistungskurve und Jahresenergieertrag"
KURZ = "Leistungskurve & Ertrag"
BESCHREIBUNG = ("Wie viel Strom liefert die Anlage im Jahr? Aus Rotordurchmesser und Windverteilung am Standort "
                "(Weibull, k = 2 entspricht Rayleigh) werden Leistungskurve und Jahresertrag berechnet.")
HAUPT = "E"
STUNDEN_JAHR = 8760.0

QUELLEN = [
    "W. Weibull: A statistical distribution function of wide applicability, J. Appl. Mech. 18 (1951)",
    "R. Gasch, J. Twele: Windkraftanlagen (Kap. Wind, Energieertrag): Weibull- und Rayleigh-Verteilung, "
    "Höhenprofil nach Hellmann",
    "E. Hau: Windkraftanlagen (Kap. Energielieferung): mittlere Leistung = ∫ P(v)·f(v) dv",
    "Prüfwert Rayleigh ohne Begrenzung: v³-Mittel = (6/π)·v̄³ (Energiemusterfaktor 1,91)",
]

FELDER = [
    Feld("durchmesser_m", "Rotordurchmesser", "m", 0.5, 30, 0.1, 2, "aus der Rotorauslegung"),
    Feld("leistung_nenn_kw", "Elektrische Nennleistung", "kW", 0.1, 100, 0.5, 1, "Leistung wird oberhalb begrenzt"),
    Feld("cp", "Leistungsbeiwert cp", "", 0.05, 0.59, 0.01, 2, "wie in der Rotorauslegung"),
    Feld("wirkungsgrad", "Wirkungsgrad Antriebsstrang", "", 0.1, 1.0, 0.01, 2, "Getriebe × Generator × Umrichter"),
    Feld("luftdichte", "Luftdichte", "kg/m^3", 0.5, 1.5, 0.005, 3, "1,225 auf Meereshöhe bei 15 °C"),
    Feld("v_ein", "Einschaltwindgeschwindigkeit", "m/s", 0.5, 10, 0.5, 1, "darunter steht die Anlage"),
    Feld("v_ab", "Abschaltwindgeschwindigkeit", "m/s", 10, 40, 1, 1, "darüber schaltet die Anlage ab (Sturm)"),
    Feld("v_mess", "Mittlerer Wind am Messpunkt", "m/s", 1, 15, 0.1, 1,
         "Jahresmittel am Standort (Windatlas oder eigene Messung) – ANNAHME, bitte Standortwert eintragen"),
    Feld("h_mess", "Höhe des Messpunkts", "m", 1, 200, 1, 1, "Windatlas meist 10 m"),
    Feld("h_nabe", "Nabenhöhe", "m", 2, 100, 0.5, 1, "Höhe der Rotormitte"),
    Feld("hellmann", "Höhenexponent α (Hellmann)", "", 0.05, 0.6, 0.01, 2,
         "glatt/offen 0,10–0,16 · Wiesen/Felder 0,16–0,2 · Hecken/Dorf 0,25–0,3 · Stadt 0,4"),
    Feld("weibull_k", "Weibull-Formfaktor k", "", 1.0, 4.0, 0.1, 1, "2,0 = Rayleigh (typisch im Binnenland 1,8–2,2)"),
    Feld("verfuegbarkeit", "Technische Verfügbarkeit", "", 0.5, 1.0, 0.01, 2, "Anteil der Zeit, in der die Anlage läuft"),
]

FELD_EINHEITEN = {x.attr: x.einheit for x in FELDER}
FELD_NAMEN = {x.attr: x.name for x in FELDER}
FELD_SUCHBEGRIFFE = {
    "leistung_nenn_kw": "nennleistung",
    "v_ein": "einschaltwind",
    "v_ab": "abschaltwind",
    "h_nabe": "nabenhöhe",
}
# Feld ← (Berechnungsart, Symbol) aus einer gespeicherten Berechnung
BERECHNUNGS_QUELLEN = {
    "durchmesser_m": ("rotorauslegung", "D"),
    "cp": ("rotorauslegung", "cp"),
    "wirkungsgrad": ("rotorauslegung", "η"),
    "luftdichte": ("rotorauslegung", "ρ"),
}


class EingabeFehler(ValueError):
    pass


@dataclass
class ErtragEingaben:
    durchmesser_m: float = 4.8
    leistung_nenn_kw: float = 5.0
    cp: float = 0.40
    wirkungsgrad: float = 0.85
    luftdichte: float = 1.225
    v_ein: float = 3.0
    v_ab: float = 25.0
    v_mess: float = 4.5
    h_mess: float = 10.0
    h_nabe: float = 12.0
    hellmann: float = 0.20
    weibull_k: float = 2.0
    verfuegbarkeit: float = 0.95

    def pruefen(self) -> None:
        if self.durchmesser_m <= 0:
            raise EingabeFehler("Der Rotordurchmesser muss größer als 0 sein.")
        if self.leistung_nenn_kw <= 0:
            raise EingabeFehler("Die Nennleistung muss größer als 0 sein.")
        if not 0 < self.cp <= 16 / 27:
            raise EingabeFehler("cp muss zwischen 0 und der Betz-Grenze 0,593 liegen.")
        if not 0 < self.wirkungsgrad <= 1 or not 0 < self.verfuegbarkeit <= 1:
            raise EingabeFehler("Wirkungsgrad und Verfügbarkeit liegen zwischen 0 und 1.")
        if self.v_ein >= self.v_ab:
            raise EingabeFehler("Die Einschaltwindgeschwindigkeit muss kleiner als die Abschaltgeschwindigkeit sein.")
        if self.v_mess <= 0 or self.h_mess <= 0 or self.h_nabe <= 0:
            raise EingabeFehler("Wind und Höhen müssen größer als 0 sein.")
        if self.weibull_k <= 0:
            raise EingabeFehler("Der Weibull-Formfaktor muss größer als 0 sein.")


def weibull_dichte(v: float, c: float, k: float) -> float:
    if v <= 0:
        return 0.0
    return k / c * (v / c) ** (k - 1) * math.exp(-((v / c) ** k))


def weibull_summe(v: float, c: float, k: float) -> float:
    """Verteilungsfunktion F(v) = 1 − e^(−(v/c)^k)."""
    return 0.0 if v <= 0 else 1 - math.exp(-((v / c) ** k))


def leistung(v: float, e: ErtragEingaben, flaeche: float) -> float:
    """Elektrische Leistung in W bei Windgeschwindigkeit v (vereinfachte Leistungskurve)."""
    if v < e.v_ein or v >= e.v_ab:
        return 0.0
    return min(e.leistung_nenn_kw * 1000, 0.5 * e.luftdichte * flaeche * e.cp * e.wirkungsgrad * v**3)


def mittelwert(funktion, c: float, k: float, v_max: float = 60.0, schritt: float = 0.01) -> float:
    """∫ funktion(v)·f(v) dv mit der Trapezregel (Schritt 0,01 m/s)."""
    n = int(v_max / schritt)
    summe = 0.0
    for i in range(n + 1):
        v = i * schritt
        w = 0.5 if i in (0, n) else 1.0
        summe += w * funktion(v) * weibull_dichte(v, c, k)
    return summe * schritt


def berechne(e: ErtragEingaben) -> Ergebnis:
    e.pruefen()
    flaeche = math.pi * e.durchmesser_m**2 / 4
    v_nabe = e.v_mess * (e.h_nabe / e.h_mess) ** e.hellmann
    c = v_nabe / math.gamma(1 + 1 / e.weibull_k)
    p_n = e.leistung_nenn_kw * 1000
    v_nenn = (2 * p_n / (e.luftdichte * flaeche * e.cp * e.wirkungsgrad)) ** (1 / 3)
    p_mittel = mittelwert(lambda v: leistung(v, e, flaeche), c, e.weibull_k)
    energie = p_mittel * STUNDEN_JAHR * e.verfuegbarkeit / 1000          # kWh/a
    volllast = energie / e.leistung_nenn_kw                                # h/a
    kf = energie / (e.leistung_nenn_kw * STUNDEN_JAHR)
    stillstand_unten = weibull_summe(e.v_ein, c, e.weibull_k)
    sturm = 1 - weibull_summe(e.v_ab, c, e.weibull_k)

    eingaben = [
        Groesse("D", "Rotordurchmesser", e.durchmesser_m, "m"),
        Groesse("P_n", "Elektrische Nennleistung", e.leistung_nenn_kw, "kW"),
        Groesse("cp", "Leistungsbeiwert", e.cp, "–"),
        Groesse("η", "Wirkungsgrad Antriebsstrang", e.wirkungsgrad, "–"),
        Groesse("ρ", "Luftdichte", e.luftdichte, "kg/m³"),
        Groesse("v_ein", "Einschaltwindgeschwindigkeit", e.v_ein, "m/s"),
        Groesse("v_ab", "Abschaltwindgeschwindigkeit", e.v_ab, "m/s"),
        Groesse("v_M", "Mittlerer Wind am Messpunkt (Annahme)", e.v_mess, "m/s"),
        Groesse("h_M", "Höhe des Messpunkts", e.h_mess, "m"),
        Groesse("h_N", "Nabenhöhe", e.h_nabe, "m"),
        Groesse("α", "Höhenexponent (Hellmann)", e.hellmann, "–"),
        Groesse("k", "Weibull-Formfaktor", e.weibull_k, "–"),
        Groesse("V", "Technische Verfügbarkeit", e.verfuegbarkeit, "–"),
    ]
    schritte = [
        Schritt("Mittlerer Wind auf Nabenhöhe", "v_N = v_M·(h_N/h_M)^α",
                f"v_N = {f(e.v_mess)} m/s·({f(e.h_nabe)} m/{f(e.h_mess)} m)^{f(e.hellmann)}",
                Groesse("v_N", "Mittlerer Wind auf Nabenhöhe", v_nabe, "m/s")),
        Schritt("Weibull-Skalenparameter", "c = v_N / Γ(1 + 1/k)",
                f"c = {f(v_nabe)} m/s / Γ(1 + 1/{f(e.weibull_k)}) = {f(v_nabe)} / {f(math.gamma(1 + 1 / e.weibull_k))}",
                Groesse("c", "Weibull-Skalenparameter", c, "m/s")),
        Schritt("Rotorfläche", "A = π·D²/4", f"A = π·{f(e.durchmesser_m)}² m²/4",
                Groesse("A", "Rotorfläche", flaeche, "m²")),
        Schritt("Wind, bei dem die Nennleistung erreicht wird", "v_r = (2·P_n / (ρ·A·cp·η))^(1/3)",
                f"v_r = (2·{f(p_n)} W / ({f(e.luftdichte)}·{f(flaeche)} m²·{f(e.cp)}·{f(e.wirkungsgrad)}))^(1/3)",
                Groesse("v_r", "Nennwind der Leistungskurve", v_nenn, "m/s")),
        Schritt("Mittlere elektrische Leistung", "P̄ = ∫ P(v)·f(v) dv  (Trapezregel, Δv = 0,01 m/s)",
                f"P(v) = min({f(e.leistung_nenn_kw)} kW; ½·ρ·A·cp·η·v³) zwischen {f(e.v_ein)} und {f(e.v_ab)} m/s",
                Groesse("P_m", "Mittlere elektrische Leistung", p_mittel / 1000, "kW")),
        Schritt("Jahresenergieertrag", "E = P̄ · 8760 h/a · V",
                f"E = {f(p_mittel / 1000)} kW · 8760 h/a · {f(e.verfuegbarkeit)}",
                Groesse("E", "Jahresenergieertrag", energie, "kWh/a")),
        Schritt("Volllaststunden und Kapazitätsfaktor", "t_VL = E / P_n;   KF = E / (P_n·8760 h)",
                f"t_VL = {f(energie)} kWh / {f(e.leistung_nenn_kw)} kW",
                Groesse("t_VL", "Volllaststunden", volllast, "h/a")),
    ]
    ergebnisse = [
        Groesse("E", "Jahresenergieertrag", energie, "kWh/a"),
        Groesse("P_m", "Mittlere elektrische Leistung", p_mittel / 1000, "kW"),
        Groesse("t_VL", "Volllaststunden", volllast, "h/a"),
        Groesse("KF", "Kapazitätsfaktor", kf * 100, "%"),
        Groesse("v_N", "Mittlerer Wind auf Nabenhöhe", v_nabe, "m/s"),
        Groesse("c", "Weibull-Skalenparameter", c, "m/s"),
        Groesse("v_r", "Nennwind der Leistungskurve", v_nenn, "m/s"),
        Groesse("t_unter", "Zeitanteil unter Einschaltwind", stillstand_unten * 100, "%"),
    ]

    # Leistungskurve und Häufigkeit je 1-m/s-Klasse
    zeilen, xs, ys = [], [], []
    for v in range(1, int(math.ceil(e.v_ab)) + 1):
        p = leistung(float(v), e, flaeche)
        stunden = STUNDEN_JAHR * (weibull_summe(v + 0.5, c, e.weibull_k) - weibull_summe(v - 0.5, c, e.weibull_k))
        zeilen.append([v, round(p / 1000, 3), round(stunden, 1), round(p / 1000 * stunden * e.verfuegbarkeit, 1)])
    for i in range(0, int(e.v_ab * 10) + 1):
        v = i / 10
        xs.append(v)
        ys.append(leistung(v, e, flaeche) / 1000)
    tabellen = [{"titel": "Leistungskurve und Windhäufigkeit (Klassen ±0,5 m/s)",
                 "spalten": ["v in m/s", "P in kW", "Stunden je Jahr", "Energie in kWh/a"], "zeilen": zeilen}]
    diagramm = {"titel": "Leistungskurve", "x_name": "Wind v in m/s", "y_name": "P in kW", "x": xs, "y": ys,
                "balken": [z[2] for z in zeilen], "balken_name": "Stunden je Jahr"}

    pruefungen = [
        Pruefung("Nennwind liegt im Betriebsbereich", f"v_ein = {f(e.v_ein)} < v_r = {f(v_nenn)} < v_ab = {f(e.v_ab)} m/s",
                 e.v_ein < v_nenn < e.v_ab,
                 "" if e.v_ein < v_nenn < e.v_ab else "Die Nennleistung wird im Betriebsbereich nie erreicht."),
        Pruefung("Wirtschaftlichkeit (Richtwert)", f"Kapazitätsfaktor = {f(kf * 100, 3)} % ≥ 10 %", kf >= 0.10,
                 "" if kf >= 0.10 else "Unter 10 % lohnt sich eine Kleinwindanlage selten – Standort oder "
                                       "Nabenhöhe prüfen."),
    ]
    hinweise = [
        "Der mittlere Wind am Standort ist eine Annahme, solange kein Messwert oder Windatlaswert eingetragen ist. "
        "Er bestimmt den Ertrag stärker als jede andere Größe (Ertrag ~ v³).",
        "Vereinfachte Leistungskurve mit konstantem cp. Eine gemessene Leistungskurve (IEC 61400-12-1) ersetzt sie später.",
        f"Zeitanteil über Abschaltwind: {f(sturm * 100, 3)} %.",
    ]
    return Ergebnis(TITEL, TYP, eingaben, schritte, ergebnisse, pruefungen, QUELLEN, hinweise,
                    tabellen=tabellen, diagramm=diagramm)
