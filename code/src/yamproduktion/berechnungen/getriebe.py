"""Zahnradstufe: Stirnradpaar oder Planetenstufe (vereinfacht nach DIN 3990 / ISO 6336, Methode C-ähnlich).

  Geometrie (Geradverzahnung, Profilverschiebung 0):
    d = m·z;  d_b = d·cos α;  d_a = d + 2m;  a = (d1 + d2)/2
    ε_α = [√(r_a1² − r_b1²) + √(r_a2² − r_b2²) − a·sin α] / (π·m·cos α)
  Flankenpressung:  σ_H = Z_E·Z_H·Z_ε·√(F_t·K_A·K_v·(u+1)/(d1·b·u));  Z_H = √(2/(cos²α·tan α));  Z_ε = √((4 − ε_α)/3)
  Zahnfuß:          σ_F = F_t·K_A·K_v/(b·m)·Y_FS·Y_ε;  Y_ε = 0,25 + 0,75/ε_α
  Planetenstufe:    z_H = z_S + 2·z_P;  i = 1 + z_H/z_S (Hohlrad fest);  Montagebedingung (z_S + z_H)/n_P ganzzahlig
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .basis import Ergebnis, Feld, Groesse, Pruefung, Schritt, formatiere as f

TYP = "getriebe"
TITEL = "Zahnradstufe (Stirnrad / Planet)"
KURZ = "Getriebe"
BESCHREIBUNG = ("Geometrie, Überdeckung, Flankenpressung und Zahnfußspannung einer geradverzahnten Stufe. "
                "Für eine Planetenstufe wird der Eingriff Sonne–Planet mit dem Moment je Planet gerechnet.")
HAUPT = "S_H"
BAUARTEN = ("Stirnradstufe", "Planetenstufe (Hohlrad fest)")
Z_E_STAHL = 189.8

QUELLEN = [
    "DIN 3960: Geometrie Evolventenverzahnung, Profilüberdeckung ε_α",
    "DIN 3990-2 / ISO 6336-2: σ_H = Z_E·Z_H·Z_ε·√(F_t·K·(u+1)/(d1·b·u)), Z_E = 189,8 √MPa (Stahl/Stahl), "
    "Z_H = √(2·cos β_b/(cos²α_t·tan α_wt)), Z_ε = √((4 − ε_α)/3)",
    "DIN 3990-3 / ISO 6336-3: σ_F = F_t·K/(b·m)·Y_FS·Y_ε, Y_ε = 0,25 + 0,75/ε_α",
    "Planetengetriebe: Standübersetzung i0 = −z_H/z_S, Willis-Gleichung i = 1 − i0; Montagebedingung (Müller, Die Umlaufgetriebe)",
]

FELDER = [
    Feld("bauart", "Bauart", "", auswahl=BAUARTEN),
    Feld("m_n", "Modul m", "mm", 0.5, 30, 0.25, 2, "Normreihe DIN 780: 1; 1,25; 1,5; 2; 2,5; 3; 4; 5 …"),
    Feld("z1", "Zähnezahl Ritzel bzw. Sonne z1", "", 8, 200, 1, 0, "ohne Profilverschiebung z ≥ 17"),
    Feld("z2", "Zähnezahl Rad bzw. Planet z2", "", 8, 400, 1, 0, ""),
    Feld("n_p", "Anzahl Planeten", "", 1, 8, 1, 0, "nur Planetenstufe"),
    Feld("b_mm", "Zahnbreite b", "mm", 2, 500, 1, 1, "b ≈ 8…15·m"),
    Feld("alpha", "Eingriffswinkel α", "deg", 14.5, 25, 0.5, 1, "Normal 20°"),
    Feld("t_r", "Drehmoment langsame Welle (Rotor)", "N*m", 0.1, 1e6, 1, 1, "Rad bzw. Planetenträger; Nennmoment"),
    Feld("n_r", "Drehzahl langsame Welle (Rotor)", "1/min", 1, 10000, 5, 1, ""),
    Feld("k_a", "Anwendungsfaktor K_A", "", 1, 3, 0.05, 2, "Wind: ≥ 1,25 (Richtwert)"),
    Feld("k_v", "Dynamikfaktor K_v", "", 1, 2, 0.01, 2, "≈ 1,05–1,2 (Richtwert)"),
    Feld("k_gamma", "Lastaufteilung Planeten K_γ", "", 1, 1.5, 0.01, 2, "nur Planetenstufe; 3 Planeten ≈ 1,1"),
    Feld("y_fs", "Kopffaktor Y_FS", "", 3.5, 7, 0.05, 2, "aus Diagramm DIN 3990-3 ablesen, z = 20 → ≈ 4,3"),
    Feld("sigma_hlim", "Dauerfestigkeit Flanke σ_Hlim", "MPa", 300, 2000, 10, 0, "Werkstofftabelle DIN 3990-5"),
    Feld("sigma_flim", "Dauerfestigkeit Zahnfuß σ_Flim", "MPa", 100, 600, 5, 0, "Werkstofftabelle DIN 3990-5"),
]
FELD_EINHEITEN = {x.attr: x.einheit for x in FELDER if not x.auswahl}
FELD_NAMEN = {x.attr: x.name for x in FELDER}
FELD_SUCHBEGRIFFE: dict = {}
BERECHNUNGS_QUELLEN = {"t_r": ("antrieb", "M_R"), "n_r": ("antrieb", "n_R")}


class EingabeFehler(ValueError):
    pass


@dataclass
class GetriebeEingaben:
    bauart: str = BAUARTEN[1]
    m_n: float = 2.0
    z1: float = 21
    z2: float = 30
    n_p: float = 3
    b_mm: float = 30.0
    alpha: float = 20.0
    t_r: float = 215.0
    n_r: float = 263.0
    k_a: float = 1.25
    k_v: float = 1.1
    k_gamma: float = 1.1
    y_fs: float = 4.3
    sigma_hlim: float = 1500.0
    sigma_flim: float = 430.0

    def pruefen(self) -> None:
        if self.bauart not in BAUARTEN:
            raise EingabeFehler("Bitte eine Bauart wählen.")


def ueberdeckung(m: float, z1: int, z2: int, alpha_deg: float) -> float:
    a = math.radians(alpha_deg)
    r1, r2 = m * z1 / 2, m * z2 / 2
    rb1, rb2 = r1 * math.cos(a), r2 * math.cos(a)
    ra1, ra2 = r1 + m, r2 + m
    return (math.sqrt(ra1**2 - rb1**2) + math.sqrt(ra2**2 - rb2**2) - (r1 + r2) * math.sin(a)) / (math.pi * m * math.cos(a))


def z_h(alpha_deg: float) -> float:
    a = math.radians(alpha_deg)
    return math.sqrt(2 / (math.cos(a) ** 2 * math.tan(a)))


def berechne(e: GetriebeEingaben) -> Ergebnis:
    e.pruefen()
    planet = e.bauart == BAUARTEN[1]
    m, z1, z2 = e.m_n, int(round(e.z1)), int(round(e.z2))
    n_p = int(round(e.n_p)) if planet else 1
    d1, d2 = m * z1, m * z2
    a = (d1 + d2) / 2
    u = z2 / z1
    eps = ueberdeckung(m, z1, z2, e.alpha)
    ZH = z_h(e.alpha)
    Ze = math.sqrt((4 - eps) / 3)
    Ye = 0.25 + 0.75 / eps
    k_gamma = e.k_gamma if planet else 1.0
    if planet:
        z_hohl = z1 + 2 * z2
        i = 1 + z_hohl / z1
    else:
        z_hohl, i = 0, u
    # Der Rotor treibt das Rad bzw. den Planetenträger; Ritzel bzw. Sonne laufen schnell.
    t1 = e.t_r / i
    n1 = e.n_r * i
    T_eingriff = t1 / n_p * k_gamma
    Ft = 2 * T_eingriff * 1000 / d1
    v = math.pi * d1 / 1000 * n1 / 60
    K = e.k_a * e.k_v
    sigma_h = Z_E_STAHL * ZH * Ze * math.sqrt(Ft * K * (u + 1) / (d1 * e.b_mm * u))
    sigma_f = Ft * K / (e.b_mm * m) * e.y_fs * Ye
    S_H = e.sigma_hlim / sigma_h
    S_F = 2.0 * e.sigma_flim / sigma_f     # Y_ST = 2 (Prüfrad-Korrektur)
    if planet:
        montage = (z1 + z_hohl) / n_p
        montage_ok = abs(montage - round(montage)) < 1e-9
        # Nachbarbedingung: Kopfkreise der Planeten berühren sich nicht
        nachbar = 2 * a * math.sin(math.pi / n_p) > m * z2 + 2 * m
    else:
        montage, montage_ok, nachbar = 0.0, True, True
    zahn_ok = z1 >= 17 and z2 >= 17

    eingaben = [
        Groesse("Bauart", e.bauart, 0, ""), Groesse("m", "Modul", m, "mm"), Groesse("z1", "Zähnezahl Ritzel/Sonne", z1, "–"),
        Groesse("z2", "Zähnezahl Rad/Planet", z2, "–"), Groesse("b", "Zahnbreite", e.b_mm, "mm"), Groesse("α", "Eingriffswinkel", e.alpha, "°"),
        Groesse("T_R", "Moment langsame Welle", e.t_r, "N·m"), Groesse("n_R", "Drehzahl langsame Welle", e.n_r, "1/min"),
        Groesse("K_A", "Anwendungsfaktor", e.k_a, "–"), Groesse("K_v", "Dynamikfaktor", e.k_v, "–"),
        Groesse("Y_FS", "Kopffaktor", e.y_fs, "–"), Groesse("σ_Hlim", "Dauerfestigkeit Flanke", e.sigma_hlim, "MPa"),
        Groesse("σ_Flim", "Dauerfestigkeit Zahnfuß", e.sigma_flim, "MPa"),
    ]
    if planet:
        eingaben.insert(5, Groesse("n_P", "Anzahl Planeten", n_p, "–"))
        eingaben.append(Groesse("K_γ", "Lastaufteilung", k_gamma, "–"))
    S = Schritt
    schritte = [
        S("Teilkreise und Achsabstand", "d = m·z;  a = (d1 + d2)/2", f"d1 = {f(d1)} mm;  d2 = {f(d2)} mm",
          Groesse("a", "Achsabstand", a, "mm")),
        S("Profilüberdeckung", "ε_α = [√(r_a1² − r_b1²) + √(r_a2² − r_b2²) − a·sin α]/(π·m·cos α)",
          f"r_a1 = {f(d1 / 2 + m)};  r_b1 = {f(d1 / 2 * math.cos(math.radians(e.alpha)))} mm", Groesse("ε_α", "Profilüberdeckung", eps, "–")),
    ]
    if planet:
        schritte += [
            S("Hohlrad und Übersetzung", "z_H = z_S + 2·z_P;  i = 1 + z_H/z_S", f"z_H = {z1} + 2·{z2} = {z_hohl};  i = 1 + {z_hohl}/{z1}",
              Groesse("i", "Übersetzung", i, "–")),
            S("Montagebedingung", "(z_S + z_H)/n_P ganzzahlig", f"({z1} + {z_hohl})/{n_p} = {f(montage)}",
              Groesse("(z_S+z_H)/n_P", "Montagekennzahl", montage, "–")),
        ]
    schritte += [
        S("Moment und Drehzahl an Ritzel bzw. Sonne", "T1 = T_R/i;  n1 = n_R·i", f"T1 = {f(e.t_r)}/{f(i)};  n1 = {f(e.n_r)}·{f(i)}",
          Groesse("T1", "Moment an Ritzel/Sonne", t1, "N·m")),
    ]
    if planet:
        schritte += [
            S("Moment je Planeteneingriff", "T = T1/n_P·K_γ", f"T = {f(t1)}/{n_p}·{f(k_gamma)}", Groesse("T_P", "Moment je Eingriff", T_eingriff, "N·m")),
        ]
    schritte += [
        S("Umfangskraft", "F_t = 2·T/d1", f"F_t = 2·{f(T_eingriff)}·10³/{f(d1)}", Groesse("F_t", "Umfangskraft", Ft, "N")),
        S("Zonenfaktor und Überdeckungsfaktor", "Z_H = √(2/(cos²α·tan α));  Z_ε = √((4 − ε_α)/3)", f"Z_H = {f(ZH)};  Z_ε = {f(Ze)}",
          Groesse("Z_H", "Zonenfaktor", ZH, "–")),
        S("Flankenpressung", "σ_H = Z_E·Z_H·Z_ε·√(F_t·K_A·K_v·(u+1)/(d1·b·u))",
          f"σ_H = {f(Z_E_STAHL)}·{f(ZH)}·{f(Ze)}·√({f(Ft)}·{f(K)}·({f(u)}+1)/({f(d1)}·{f(e.b_mm)}·{f(u)}))",
          Groesse("σ_H", "Flankenpressung", sigma_h, "MPa")),
        S("Zahnfußspannung", "σ_F = F_t·K_A·K_v/(b·m)·Y_FS·Y_ε;  Y_ε = 0,25 + 0,75/ε_α",
          f"σ_F = {f(Ft)}·{f(K)}/({f(e.b_mm)}·{f(m)})·{f(e.y_fs)}·{f(Ye)}", Groesse("σ_F", "Zahnfußspannung", sigma_f, "MPa")),
        S("Sicherheiten", "S_H = σ_Hlim/σ_H;  S_F = σ_Flim·Y_ST/σ_F (Y_ST = 2)", f"S_H = {f(e.sigma_hlim)}/{f(sigma_h)};  S_F = 2·{f(e.sigma_flim)}/{f(sigma_f)}",
          Groesse("S_H", "Sicherheit Flanke", S_H, "–")),
    ]
    ergebnisse = [
        Groesse("S_H", "Sicherheit gegen Grübchen", S_H, "–"),
        Groesse("S_F", "Sicherheit gegen Zahnbruch", S_F, "–"),
        Groesse("i", "Übersetzung", i, "–"),
        Groesse("σ_H", "Flankenpressung", sigma_h, "MPa"),
        Groesse("σ_F", "Zahnfußspannung", sigma_f, "MPa"),
        Groesse("ε_α", "Profilüberdeckung", eps, "–"),
        Groesse("a", "Achsabstand", a, "mm"),
        Groesse("F_t", "Umfangskraft je Eingriff", Ft, "N"),
        Groesse("v", "Umfangsgeschwindigkeit", v, "m/s"),
        Groesse("n1", "Drehzahl schnelle Welle", n1, "1/min"),
        Groesse("T1", "Moment schnelle Welle (ohne Verluste)", t1, "N·m"),
    ]
    if planet:
        ergebnisse.append(Groesse("z_H", "Zähnezahl Hohlrad", z_hohl, "–"))
    tabelle = {"titel": "Zahnradgeometrie", "spalten": ["Rad", "z", "d (mm)", "d_a (mm)", "d_b (mm)"],
               "zeilen": [[n, str(z), f(m * z), f(m * z + 2 * m), f(m * z * math.cos(math.radians(e.alpha)))]
                          for n, z in (("Sonne" if planet else "Ritzel", z1), ("Planet" if planet else "Rad", z2))]}
    if planet:
        tabelle["zeilen"].append(["Hohlrad (innen)", str(z_hohl), f(m * z_hohl), f(m * z_hohl - 2 * m), f(m * z_hohl * math.cos(math.radians(e.alpha)))])
    pruefungen = [
        Pruefung("Profilüberdeckung", f"ε_α = {f(ep := eps, 3)} ≥ 1,2", ep >= 1.2),
        Pruefung("Kein Unterschnitt (ohne Profilverschiebung)", f"z1 = {z1}, z2 = {z2} ≥ 17", zahn_ok,
                 "" if zahn_ok else "Profilverschiebung vorsehen oder Zähnezahl erhöhen."),
        Pruefung("Sicherheit Flanke (Richtwert)", f"S_H = {f(S_H, 3)} ≥ 1,2", S_H >= 1.2),
        Pruefung("Sicherheit Zahnfuß (Richtwert)", f"S_F = {f(S_F, 3)} ≥ 1,5", S_F >= 1.5),
    ]
    if planet:
        pruefungen += [
            Pruefung("Montagebedingung", f"({z1} + {z_hohl})/{n_p} = {f(montage, 4)} ganzzahlig", montage_ok,
                     "" if montage_ok else "Zähnezahlen oder Planetenzahl ändern."),
            Pruefung("Nachbarbedingung", "Planeten-Kopfkreise berühren sich nicht", nachbar),
        ]
    hinweise = [
        "Vereinfachte Rechnung ohne Breitenlastfaktoren K_Hβ/K_Fβ, Lebensdauerfaktoren Z_NT/Y_NT und "
        "Schmierungseinflüsse. Für die Fertigung die volle Rechnung nach DIN 3990 oder ISO 6336 durchführen.",
        "Hohlrad–Planet-Eingriff (Innenverzahnung) wird nicht nachgewiesen; er ist wegen der konkaven Flanke meist weniger kritisch.",
    ]
    unbelegt = [
        "Richtwerte K_A ≥ 1,25, K_v, K_γ, Mindestsicherheiten S_H ≥ 1,2 und S_F ≥ 1,5 aus dem Gedächtnis.",
        "Y_FS, σ_Hlim und σ_Flim sind Eingaben aus Normdiagrammen und Werkstofftabellen; Literatur-Rechenbeispiel steht aus.",
    ]
    return Ergebnis(TITEL, TYP, eingaben, schritte, ergebnisse, pruefungen, QUELLEN, hinweise,
                    tabellen=[tabelle], unbelegt=unbelegt)
