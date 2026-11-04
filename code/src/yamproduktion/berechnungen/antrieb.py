"""Antriebsstrang und Generatorauswahl (Lastenheft M20).

Rechenweg:
  1. Gesamtwirkungsgrad          η_ges = η_Getriebe · η_Generator · η_Umrichter
  2. Leistungen je Stufe         P_Rotor = P_el / η_ges;  P_Gen,ein = P_Rotor · η_Getriebe
  3. Drehmoment Rotorwelle       M_Rotor = P_Rotor / ω_Rotor
  4a. Mit Getriebe               i = n_Gen / n_Rotor;   M_Gen = M_Rotor · η_Getriebe / i
  4b. Direktantrieb              n_Gen = n_Rotor;       Polpaarzahl p = 60·f / n_Gen  (aufgerundet)
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .basis import Ergebnis, Feld, Groesse, Pruefung, Schritt, formatiere as f

TYP = "antrieb"
TITEL = "Antriebsstrang und Generatorauswahl"
KURZ = "Antriebsstrang"
BESCHREIBUNG = ("Drehmomente, Drehzahlen und Leistungen vom Rotor bis zum Netz. Ergebnis ist das Anforderungsprofil "
                "an den Generator (und an das Getriebe, falls vorhanden).")
HAUPT = "M_Gen"
BAUARTEN = ("Direktantrieb (Vielpol-Synchrongenerator)", "Getriebe + schnelllaufender Generator")
I_STUFE_MAX = 6.0   # Richtwert Übersetzung je Stirnradstufe

QUELLEN = [
    "Grundgleichungen der Mechanik: P = M·ω, ω = 2π·n/60",
    "Synchrondrehzahl elektrischer Maschinen: n = 60·f / p (p = Polpaarzahl)",
    "R. Gasch, J. Twele: Windkraftanlagen (Kap. Triebstrang und Generator)",
    "Roloff/Matek Maschinenelemente (Kap. Zahnradgetriebe): Übersetzung je Stirnradstufe i ≤ 6 als Richtwert",
]

FELDER = [
    Feld("bauart", "Bauart", "", auswahl=BAUARTEN, tipp="Aus dem gewählten Konzept"),
    Feld("leistung_el_kw", "Elektrische Nennleistung", "kW", 0.1, 100, 0.5, 1, "ins Netz bzw. in die Batterie"),
    Feld("drehzahl_rotor", "Nenndrehzahl Rotor", "1/min", 10, 2000, 5, 1, "aus der Rotorauslegung"),
    Feld("drehzahl_gen", "Generator-Nenndrehzahl (nur mit Getriebe)", "1/min", 100, 6000, 50, 0,
         "z. B. 1500 1/min (4-polig, 50 Hz) oder 1000 1/min (6-polig)"),
    Feld("eta_getriebe", "Wirkungsgrad Getriebe", "", 0.5, 1.0, 0.01, 3, "je Stirnradstufe etwa 0,98"),
    Feld("eta_generator", "Wirkungsgrad Generator", "", 0.5, 1.0, 0.01, 3, "Kleingeneratoren 0,85–0,93"),
    Feld("eta_umrichter", "Wirkungsgrad Umrichter / Gleichrichter", "", 0.5, 1.0, 0.01, 3, "0,93–0,97"),
    Feld("frequenz_hz", "Ziel-Frequenz (Direktantrieb)", "Hz", 5, 400, 1, 0,
         "Mit Umrichter frei wählbar; höhere Frequenz → kleinerer Generator"),
    Feld("eta_rotor_annahme", "In der Rotorauslegung angenommenes η", "", 0.1, 1.0, 0.01, 2,
         "zum Abgleich: passt die Annahme zum Antriebsstrang?"),
]
FELD_EINHEITEN = {x.attr: x.einheit for x in FELDER if not x.auswahl}
FELD_NAMEN = {x.attr: x.name for x in FELDER}
FELD_SUCHBEGRIFFE = {"leistung_el_kw": "nennleistung"}
BERECHNUNGS_QUELLEN = {
    "drehzahl_rotor": ("rotorauslegung", "n"),
    "eta_rotor_annahme": ("rotorauslegung", "η"),
}


class EingabeFehler(ValueError):
    pass


@dataclass
class AntriebEingaben:
    bauart: str = BAUARTEN[0]
    leistung_el_kw: float = 5.0
    drehzahl_rotor: float = 260.0
    drehzahl_gen: float = 1500.0
    eta_getriebe: float = 0.96
    eta_generator: float = 0.90
    eta_umrichter: float = 0.95
    frequenz_hz: float = 50.0
    eta_rotor_annahme: float = 0.85

    @property
    def mit_getriebe(self) -> bool:
        return self.bauart == BAUARTEN[1]

    def pruefen(self) -> None:
        if self.bauart not in BAUARTEN:
            raise EingabeFehler(f"Unbekannte Bauart „{self.bauart}“.")
        if self.leistung_el_kw <= 0 or self.drehzahl_rotor <= 0:
            raise EingabeFehler("Leistung und Rotordrehzahl müssen größer als 0 sein.")
        for name in ("eta_getriebe", "eta_generator", "eta_umrichter"):
            if not 0 < getattr(self, name) <= 1:
                raise EingabeFehler(f"„{FELD_NAMEN[name]}“ muss zwischen 0 und 1 liegen.")
        if self.mit_getriebe and self.drehzahl_gen <= self.drehzahl_rotor:
            raise EingabeFehler("Mit Getriebe muss der Generator schneller drehen als der Rotor.")


def berechne(e: AntriebEingaben) -> Ergebnis:
    e.pruefen()
    p_el = e.leistung_el_kw * 1000
    eta_g = e.eta_getriebe if e.mit_getriebe else 1.0
    eta_ges = eta_g * e.eta_generator * e.eta_umrichter
    p_rotor = p_el / eta_ges
    p_gen_ein = p_rotor * eta_g
    p_gen_aus = p_gen_ein * e.eta_generator
    w_rotor = 2 * math.pi * e.drehzahl_rotor / 60
    m_rotor = p_rotor / w_rotor

    eingaben = [
        Groesse("Bauart", e.bauart, 1 if e.mit_getriebe else 0, ""),
        Groesse("P_el", "Elektrische Nennleistung", e.leistung_el_kw, "kW"),
        Groesse("n_R", "Nenndrehzahl Rotor", e.drehzahl_rotor, "1/min"),
        Groesse("η_G", "Wirkungsgrad Getriebe", eta_g, "–"),
        Groesse("η_Gen", "Wirkungsgrad Generator", e.eta_generator, "–"),
        Groesse("η_U", "Wirkungsgrad Umrichter", e.eta_umrichter, "–"),
    ]
    schritte = [
        Schritt("Gesamtwirkungsgrad", "η_ges = η_G·η_Gen·η_U", f"η_ges = {f(eta_g)}·{f(e.eta_generator)}·{f(e.eta_umrichter)}",
                Groesse("η_ges", "Gesamtwirkungsgrad", eta_ges, "–")),
        Schritt("Leistung an der Rotorwelle", "P_R = P_el / η_ges", f"P_R = {f(p_el)} W / {f(eta_ges)}",
                Groesse("P_R", "Leistung Rotorwelle", p_rotor / 1000, "kW")),
        Schritt("Drehmoment an der Rotorwelle", "M_R = P_R / (2π·n_R/60)",
                f"M_R = {f(p_rotor)} W / (2π·{f(e.drehzahl_rotor)}/60 1/s)", Groesse("M_R", "Drehmoment Rotorwelle", m_rotor, "N·m")),
    ]
    ergebnisse = []
    pruefungen = []
    if e.mit_getriebe:
        i = e.drehzahl_gen / e.drehzahl_rotor
        stufen = max(1, math.ceil(math.log(i) / math.log(I_STUFE_MAX) - 1e-9))
        n_gen = e.drehzahl_gen
        m_gen = m_rotor * eta_g / i
        schritte += [
            Schritt("Übersetzung", "i = n_Gen / n_R", f"i = {f(n_gen)} / {f(e.drehzahl_rotor)}", Groesse("i", "Übersetzung", i, "–")),
            Schritt("Anzahl Stirnradstufen (Richtwert)", "z = ⌈ln i / ln 6⌉", f"z = ⌈ln {f(i)} / ln 6⌉",
                    Groesse("z", "Getriebestufen", stufen, "–")),
            Schritt("Drehmoment an der Generatorwelle", "M_Gen = M_R·η_G / i", f"M_Gen = {f(m_rotor)}·{f(eta_g)} / {f(i)}",
                    Groesse("M_Gen", "Generator-Nennmoment", m_gen, "N·m")),
        ]
        ergebnisse += [Groesse("i", "Getriebeübersetzung", i, "–"), Groesse("z", "Getriebestufen (Richtwert)", stufen, "–")]
        pruefungen.append(Pruefung("Übersetzung je Stufe", f"i je Stufe = {f(i ** (1 / stufen), 3)} ≤ 6", i ** (1 / stufen) <= I_STUFE_MAX + 1e-9))
    else:
        n_gen = e.drehzahl_rotor
        m_gen = m_rotor
        p = math.ceil(60 * e.frequenz_hz / n_gen - 1e-9)
        f_ist = p * n_gen / 60
        schritte += [
            Schritt("Polpaarzahl des Generators", "p = ⌈60·f / n_Gen⌉;  f_ist = p·n_Gen/60",
                    f"p = ⌈60·{f(e.frequenz_hz)} Hz / {f(n_gen)} 1/min⌉", Groesse("p", "Polpaarzahl", p, "–")),
        ]
        ergebnisse += [Groesse("p", "Polpaarzahl", p, "–"), Groesse("2p", "Polzahl", 2 * p, "–"),
                       Groesse("f_ist", "Frequenz bei Nenndrehzahl", f_ist, "Hz")]
        pruefungen.append(Pruefung("Polzahl baubar (Richtwert)", f"2p = {2 * p} ≤ 80", 2 * p <= 80,
                                   "" if 2 * p <= 80 else "Sehr viele Pole: Ziel-Frequenz senken oder Getriebe vorsehen."))
    ergebnisse = [
        Groesse("M_Gen", "Generator-Nennmoment", m_gen, "N·m"),
        Groesse("n_Gen", "Generator-Nenndrehzahl", n_gen, "1/min"),
        Groesse("P_Gen,ein", "Mechanische Leistung am Generator", p_gen_ein / 1000, "kW"),
        Groesse("P_Gen,aus", "Elektrische Leistung Generator", p_gen_aus / 1000, "kW"),
        Groesse("M_R", "Drehmoment Rotorwelle", m_rotor, "N·m"),
        Groesse("P_R", "Leistung Rotorwelle", p_rotor / 1000, "kW"),
        Groesse("η_ges", "Gesamtwirkungsgrad", eta_ges, "–"),
    ] + ergebnisse
    abweichung = abs(eta_ges - e.eta_rotor_annahme)
    pruefungen.insert(0, Pruefung(
        "Wirkungsgrad passt zur Rotorauslegung", f"|η_ges − η_Rotor| = |{f(eta_ges, 3)} − {f(e.eta_rotor_annahme, 3)}| ≤ 0,02",
        abweichung <= 0.02,
        "" if abweichung <= 0.02 else f"Rotorauslegung mit η = {f(eta_ges, 3)} neu rechnen, sonst stimmt der Durchmesser nicht."))
    zeilen = [["Rotorwelle", round(e.drehzahl_rotor, 1), round(m_rotor, 1), round(p_rotor / 1000, 3)]]
    if e.mit_getriebe:
        zeilen.append(["Generatorwelle (nach Getriebe)", round(n_gen, 1), round(m_gen, 1), round(p_gen_ein / 1000, 3)])
    else:
        zeilen.append(["Generatorwelle (= Rotorwelle)", round(n_gen, 1), round(m_gen, 1), round(p_gen_ein / 1000, 3)])
    zeilen.append(["Generator-Klemmen", "", "", round(p_gen_aus / 1000, 3)])
    zeilen.append(["Netz / Batterie (nach Umrichter)", "", "", round(p_el / 1000, 3)])
    tabellen = [{"titel": "Leistungsfluss", "spalten": ["Stelle", "n in 1/min", "M in N·m", "P in kW"], "zeilen": zeilen}]
    hinweise = [
        "Generatoranforderung für die Auswahl beim Hersteller: Nennmoment, Nenndrehzahl, Nennleistung und "
        "Wirkungsgrad wie oben; Überlast mindestens nach Lastannahmen (Lastfall F).",
        "Wirkungsgrade sind Annahmen, bis Datenblätter von Getriebe, Generator und Umrichter vorliegen.",
    ]
    return Ergebnis(TITEL, TYP, eingaben, schritte, ergebnisse, pruefungen, QUELLEN, hinweise, tabellen=tabellen)
