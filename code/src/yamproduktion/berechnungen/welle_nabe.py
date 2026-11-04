"""Welle-Nabe-Verbindungen: Passfeder (DIN 6885 / DIN 6892 vereinfacht) und Pressverband (DIN 7190 vereinfacht).

Passfeder:   p = 2·T / (d·(h − t1)·l_tr·i·φ) ≤ p_zul;  l_tr = l − b (Form A);  φ = 1 (eine), 0,75 (zwei Federn)
Pressverband (Vollwelle, gleiche E-Moduln, dickwandige Zylinder nach Lamé):
  wirksames Übermaß  Ü_w = Ü − 0,8·(Rz_W + Rz_N)
  Fugendruck         p_F = (Ü_w / d_F)·E·(1 − Q_A²)/2        mit Q_A = d_F / D_A
  übertragbar        T = p_F·π·d_F²·l_F·ν/2
  Nabenspannung      σ_v,innen = 2·p_F/(1 − Q_A²) (Schubspannungshypothese, Innenrand) ≤ R_e
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .. import werkstoffe
from .basis import Ergebnis, Feld, Groesse, Pruefung, Schritt, formatiere as f

# Passfedern DIN 6885-1: Wellenbereich (über, bis] → (b, h, t1) in mm
PASSFEDERN = [
    (17, 22, 6, 6, 3.5), (22, 30, 8, 7, 4.0), (30, 38, 10, 8, 5.0), (38, 44, 12, 8, 5.0), (44, 50, 14, 9, 5.5),
    (50, 58, 16, 10, 6.0), (58, 65, 18, 11, 7.0), (65, 75, 20, 12, 7.5), (75, 85, 22, 14, 9.0),
    (85, 95, 25, 14, 9.0), (95, 110, 28, 16, 10.0),
]
E_STAHL = 210000.0


def passfeder(d: float) -> tuple[float, float, float]:
    for von, bis, b, h, t1 in PASSFEDERN:
        if von < d <= bis:
            return b, h, t1
    raise ValueError(f"Für d = {d} mm ist keine Passfeder hinterlegt (17 bis 110 mm).")


TYP_PASSFEDER = "passfeder"
TYP_PRESS = "pressverband"


@dataclass
class PassfederEingaben:
    d_mm: float = 80.0
    t_nm: float = 1290.0
    l_mm: float = 90.0
    anzahl: float = 1
    werkstoff_nabe: str = werkstoffe.bezeichnung(werkstoffe.werkstoff("EN-GJS-400-15"))
    s_min: float = 1.0

    def pruefen(self) -> None:
        if self.werkstoff_nabe not in werkstoffe.auswahl():
            raise ValueError("Bitte einen Werkstoff für die Nabe wählen.")
        if self.anzahl not in (1, 2):
            raise ValueError("Eine oder zwei Passfedern.")
        passfeder(self.d_mm)


def berechne_passfeder(e: PassfederEingaben) -> Ergebnis:
    e.pruefen()
    b, h, t1 = passfeder(e.d_mm)
    l_tr = e.l_mm - b
    if l_tr <= 0:
        raise ValueError("Die Passfeder ist kürzer als breit – Länge vergrößern.")
    i = int(e.anzahl)
    phi = 1.0 if i == 1 else 0.75
    w = werkstoffe.nach_bezeichnung(e.werkstoff_nabe)
    p_zul = 0.9 * w["re"] / e.s_min
    p = 2 * e.t_nm * 1000 / (e.d_mm * (h - t1) * l_tr * i * phi)
    l_min = 2 * e.t_nm * 1000 / (e.d_mm * (h - t1) * i * phi * p_zul) + b
    eingaben = [
        Groesse("d", "Wellendurchmesser", e.d_mm, "mm"),
        Groesse("T", "Drehmoment (Bemessung)", e.t_nm, "N·m"),
        Groesse("l", "Passfederlänge", e.l_mm, "mm"),
        Groesse("i", "Anzahl Passfedern", i, "–"),
        Groesse("R_e", f"Streckgrenze Nabe ({w['name']})", w["re"], "MPa"),
    ]
    schritte = [
        Schritt("Passfeder nach DIN 6885-1", "b × h, Nuttiefe Welle t1 aus Tabelle",
                f"d = {f(e.d_mm)} mm → {f(b)} × {f(h)} mm, t1 = {f(t1)} mm", Groesse("b", "Passfederbreite", b, "mm")),
        Schritt("Tragende Länge (Form A)", "l_tr = l − b", f"l_tr = {f(e.l_mm)} − {f(b)}", Groesse("l_tr", "Tragende Länge", l_tr, "mm")),
        Schritt("Flächenpressung an der Nabe", "p = 2·T/(d·(h − t1)·l_tr·i·φ)",
                f"p = 2·{f(e.t_nm)}·10³ N·mm/({f(e.d_mm)}·{f(h - t1)}·{f(l_tr)}·{i}·{f(phi)}) mm²", Groesse("p", "Flächenpressung", p, "MPa")),
        Schritt("Zulässige Pressung  [Richtwert]", "p_zul = 0,9·R_e,Nabe / S_min", f"p_zul = 0,9·{f(w['re'])}/{f(e.s_min)}",
                Groesse("p_zul", "Zulässige Pressung", p_zul, "MPa")),
        Schritt("Mindestlänge", "l_min = 2·T/(d·(h − t1)·i·φ·p_zul) + b", f"l_min = … + {f(b)}", Groesse("l_min", "Mindestlänge", l_min, "mm")),
    ]
    ergebnisse = [Groesse("p", "Flächenpressung", p, "MPa"), Groesse("p_zul", "Zulässige Pressung", p_zul, "MPa"),
                  Groesse("l_min", "Mindestlänge der Passfeder", l_min, "mm"),
                  Groesse("b×h", "Passfederquerschnitt b", b, "mm")]
    pruefungen = [Pruefung("Flächenpressung", f"p = {f(p)} MPa ≤ p_zul = {f(p_zul)} MPa", p <= p_zul,
                           "" if p <= p_zul else f"Passfeder auf mindestens {f(l_min)} mm verlängern oder zweite Feder.")]
    return Ergebnis("Passfederverbindung (vereinfacht nach DIN 6892)", TYP_PASSFEDER, eingaben, schritte, ergebnisse,
                    pruefungen, ["DIN 6885-1 Passfedern (Abmessungen)", "DIN 6892 Passfedern – Berechnung (Methode C, vereinfacht)",
                                 "Roloff/Matek, Kap. Welle-Nabe-Verbindungen"],
                    ["Drehmoment als Bemessungswert (inkl. γ_f) eintragen. Bei wechselnden Drehmomenten ist ein "
                     "Pressverband oder eine Keilwelle dauerfester."],
                    unbelegt=["Tragfaktor 0,9·R_e für p_zul ist ein Richtwert; DIN 6892 Methode B/C mit Stützfaktoren prüfen."])


@dataclass
class PressEingaben:
    d_f: float = 80.0
    d_a: float = 160.0
    l_f: float = 80.0
    ueber_um: float = 70.0
    rz_w: float = 4.0
    rz_n: float = 6.3
    nu: float = 0.12
    t_nm: float = 1290.0
    werkstoff_nabe: str = werkstoffe.bezeichnung(werkstoffe.werkstoff("C45", "+QT"))
    s_min: float = 1.5

    def pruefen(self) -> None:
        if self.werkstoff_nabe not in werkstoffe.auswahl():
            raise ValueError("Bitte einen Werkstoff für die Nabe wählen.")
        if self.d_a <= self.d_f:
            raise ValueError("Der Nabenaußendurchmesser muss größer als der Fugendurchmesser sein.")


def berechne_press(e: PressEingaben) -> Ergebnis:
    e.pruefen()
    w = werkstoffe.nach_bezeichnung(e.werkstoff_nabe)
    e_mod = w["e"] * 1000.0
    q_a = e.d_f / e.d_a
    ue_w = e.ueber_um - 0.8 * (e.rz_w + e.rz_n)
    if ue_w <= 0:
        raise ValueError("Nach der Glättung bleibt kein Übermaß – größeres Übermaß wählen.")
    xi = ue_w / 1000 / e.d_f
    p_f = xi * e_mod * (1 - q_a**2) / 2
    t_ueb = p_f * math.pi * e.d_f**2 * e.l_f * e.nu / 2 / 1000      # N·m
    s_r = t_ueb / e.t_nm if e.t_nm else float("inf")
    s_v = 2 * p_f / (1 - q_a**2)
    s_f = w["re"] / s_v
    eingaben = [
        Groesse("d_F", "Fugendurchmesser", e.d_f, "mm"), Groesse("D_A", "Nabenaußendurchmesser", e.d_a, "mm"),
        Groesse("l_F", "Fugenlänge", e.l_f, "mm"), Groesse("Ü", "Übermaß", e.ueber_um, "µm"),
        Groesse("ν", "Haftbeiwert", e.nu, "–"), Groesse("T", "Drehmoment (Bemessung)", e.t_nm, "N·m"),
        Groesse("E", f"E-Modul ({w['name']})", e_mod, "MPa"),
    ]
    schritte = [
        Schritt("Wirksames Übermaß (Glättung)", "Ü_w = Ü − 0,8·(Rz_W + Rz_N)", f"Ü_w = {f(e.ueber_um)} − 0,8·({f(e.rz_w)} + {f(e.rz_n)})",
                Groesse("Ü_w", "Wirksames Übermaß", ue_w, "µm")),
        Schritt("Fugendruck (Vollwelle, gleiches E)", "p_F = (Ü_w/d_F)·E·(1 − Q_A²)/2;  Q_A = d_F/D_A",
                f"p_F = {f(xi * 1000, 4)}‰·{f(e_mod)}·(1 − {f(q_a)}²)/2", Groesse("p_F", "Fugendruck", p_f, "MPa")),
        Schritt("Übertragbares Drehmoment", "T_ü = p_F·π·d_F²·l_F·ν/2", f"T_ü = {f(p_f)}·π·{f(e.d_f)}²·{f(e.l_f)}·{f(e.nu)}/2 N·mm",
                Groesse("T_ü", "Übertragbares Drehmoment", t_ueb, "N·m")),
        Schritt("Vergleichsspannung Nabe innen", "σ_v = 2·p_F/(1 − Q_A²)", f"σ_v = 2·{f(p_f)}/(1 − {f(q_a)}²)",
                Groesse("σ_v", "Vergleichsspannung Nabe", s_v, "MPa")),
    ]
    ergebnisse = [Groesse("T_ü", "Übertragbares Drehmoment", t_ueb, "N·m"), Groesse("S_R", "Sicherheit gegen Rutschen", s_r, "–"),
                  Groesse("p_F", "Fugendruck", p_f, "MPa"), Groesse("σ_v", "Vergleichsspannung Nabe", s_v, "MPa"),
                  Groesse("S_F", "Sicherheit Nabe gegen Fließen", s_f, "–")]
    pruefungen = [
        Pruefung("Rutschsicherheit", f"S_R = {f(s_r, 3)} ≥ {f(e.s_min, 3)}", s_r >= e.s_min,
                 "" if s_r >= e.s_min else "Übermaß oder Fugenlänge vergrößern."),
        Pruefung("Nabe fließt nicht", f"σ_v = {f(s_v)} MPa ≤ R_e = {f(w['re'])} MPa", s_v <= w["re"],
                 "" if s_v <= w["re"] else "Übermaß verkleinern oder Nabe dicker / fester."),
    ]
    return Ergebnis("Pressverband (vereinfacht nach DIN 7190)", TYP_PRESS, eingaben, schritte, ergebnisse, pruefungen,
                    ["DIN 7190-1:2017 Pressverbände – Berechnungsgrundlagen (elastische Auslegung)",
                     "Lamé-Gleichungen für dickwandige Zylinder; Roloff/Matek, Kap. Pressverbände"],
                    ["Vollwelle und Nabe mit gleichem E-Modul angenommen; für Guss-Naben (anderes E, Querdehnung) "
                     "gilt die allgemeine Gleichung nach DIN 7190.",
                     "Fügetemperatur für Querpressverband: ΔT ≈ (Ü + Spiel)/(α·d_F) mit α = 11·10⁻⁶ 1/K."],
                    unbelegt=["Haftbeiwert ν und Glättungsfaktor 0,8 sind Richtwerte aus dem Gedächtnis."])


# Modul-Schnittstelle: zwei Berechnungsarten in einer Datei
class _Art:
    def __init__(self, **kw):
        self.__dict__.update(kw)


_PF_FELDER = [
    Feld("d_mm", "Wellendurchmesser", "mm", 17.5, 110, 1, 1, "17 bis 110 mm"),
    Feld("t_nm", "Drehmoment (Bemessung)", "N*m", 1, 1e6, 10, 1, "aus Lastannahmen"),
    Feld("l_mm", "Passfederlänge l", "mm", 10, 400, 1, 0, "≤ Nabenlänge"),
    Feld("anzahl", "Anzahl Passfedern", "", 1, 2, 1, 0, "1 oder 2 (um 180° versetzt)"),
    Feld("werkstoff_nabe", "Werkstoff der Nabe", "", auswahl=werkstoffe.auswahl()),
    Feld("s_min", "Sicherheit", "", 1, 3, 0.1, 2, ""),
]
_PV_FELDER = [
    Feld("d_f", "Fugendurchmesser d_F", "mm", 5, 500, 1, 1, ""),
    Feld("d_a", "Nabenaußendurchmesser D_A", "mm", 6, 1000, 1, 1, ""),
    Feld("l_f", "Fugenlänge l_F", "mm", 5, 500, 1, 1, ""),
    Feld("ueber_um", "Übermaß Ü", "um", 1, 500, 1, 1, "aus Passung, z. B. H7/s6"),
    Feld("rz_w", "Rauheit Welle Rz", "um", 0.5, 50, 0.5, 1, ""),
    Feld("rz_n", "Rauheit Nabe Rz", "um", 0.5, 50, 0.5, 1, ""),
    Feld("nu", "Haftbeiwert ν", "", 0.05, 0.4, 0.01, 2, "Stahl/Stahl Querpressverband ≈ 0,12–0,2"),
    Feld("t_nm", "Drehmoment (Bemessung)", "N*m", 1, 1e6, 10, 1, "aus Lastannahmen"),
    Feld("werkstoff_nabe", "Werkstoff der Nabe", "", auswahl=werkstoffe.auswahl()),
    Feld("s_min", "Erforderliche Rutschsicherheit", "", 1, 3, 0.1, 2, ""),
]

passfeder_art = _Art(
    TYP=TYP_PASSFEDER, TITEL="Passfederverbindung (vereinfacht nach DIN 6892)", KURZ="Passfeder",
    BESCHREIBUNG="Flächenpressung einer Passfeder nach DIN 6885 und erforderliche Länge.", HAUPT="p",
    FELDER=_PF_FELDER, FELD_EINHEITEN={x.attr: x.einheit for x in _PF_FELDER if not x.auswahl},
    FELD_NAMEN={x.attr: x.name for x in _PF_FELDER}, FELD_SUCHBEGRIFFE={},
    BERECHNUNGS_QUELLEN={"t_nm": ("lasten_iec", "M_x,d")}, berechne=berechne_passfeder, Eingaben=PassfederEingaben)
press_art = _Art(
    TYP=TYP_PRESS, TITEL="Pressverband (vereinfacht nach DIN 7190)", KURZ="Pressverband",
    BESCHREIBUNG="Fugendruck, übertragbares Drehmoment und Nabenspannung eines zylindrischen Pressverbands.",
    HAUPT="T_ü", FELDER=_PV_FELDER, FELD_EINHEITEN={x.attr: x.einheit for x in _PV_FELDER if not x.auswahl},
    FELD_NAMEN={x.attr: x.name for x in _PV_FELDER}, FELD_SUCHBEGRIFFE={},
    BERECHNUNGS_QUELLEN={"t_nm": ("lasten_iec", "M_x,d")}, berechne=berechne_press, Eingaben=PressEingaben)
