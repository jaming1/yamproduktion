"""Festigkeitsnachweis einer Welle, vereinfacht nach DIN 743 (Lastenheft M22).

Nachgewiesen wird ein Querschnitt (z. B. Rotorwelle am ersten Lager):
  1. Nennspannungen   σ_b = M_b / W_b;  τ_t = T / W_t;  σ_zd = F / A
  2. Bruch / Fließen  S_F = 1 / √((σ_zd/σ_zdFK + σ_b/σ_bFK)² + (τ_t/τ_tFK)²)
  3. Dauerfestigkeit  Gestaltfestigkeit mit Kerbwirkung, Größe, Oberfläche; Mittelspannungseinfluss
                      S_D = 1 / √((σ_ba/σ_bADK)² + (τ_ta/τ_tADK)²)
  4. Verformung       Durchbiegung und Neigung am Lager für eine überhängende Last (Rotor)

Umlaufbiegung: Bei einer drehenden Welle wird jedes stehende Biegemoment zur Wechselbiegung
(Mittelspannung 0, Ausschlag = Moment). Torsion: Mittelwert = Nennmoment, Ausschlag aus Lastfall A.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

from .. import werkstoffe
from .basis import Ergebnis, Feld, Groesse, Pruefung, Schritt, formatiere as f

TYP = "welle"
TITEL = "Festigkeitsnachweis Welle (vereinfacht nach DIN 743)"
KURZ = "Welle"
BESCHREIBUNG = ("Sicherheit gegen Fließen und gegen Dauerbruch an einem Wellenquerschnitt, dazu Durchbiegung und "
                "Neigung am Lager. Lasten kommen aus den Lastannahmen.")
HAUPT = "S_D"
WERKSTOFFE = werkstoffe.auswahl(("Vergütungsstahl", "Baustahl", "Einsatzstahl"))
E_STAHL = 210000.0   # MPa

QUELLEN = [
    "DIN 743-1 bis -3:2012 Tragfähigkeitsberechnung von Wellen und Achsen (Normtext nicht eingesehen; Faktoren "
    "aus dem Gedächtnis, siehe „Unbelegt“)",
    "Roloff/Matek Maschinenelemente, Kap. Achsen und Wellen (Ablauf des Nachweises nach DIN 743)",
    "Technische Mechanik: W_b = π·d³/32, W_t = π·d³/16, I = π·d⁴/64; Kragarm über zwei Stützen: "
    "f = F·a²·(l + a)/(3·E·I), Neigung im rotorseitigen Lager θ = F·a·l/(3·E·I)",
]

FELDER = [
    Feld("werkstoff", "Werkstoff", "", auswahl=WERKSTOFFE, tipp="aus der Werkstoffdatenbank"),
    Feld("d_mm", "Wellendurchmesser am Nachweisquerschnitt", "mm", 5, 500, 1, 1, "z. B. Lagersitz Rotorseite"),
    Feld("m_b_d", "Biegemoment Bemessung M_b,d", "N*m", 0, 1e7, 10, 1, "aus Lastannahmen (inkl. γ_f)"),
    Feld("t_d", "Drehmoment Bemessung T_d", "N*m", 0, 1e7, 10, 1, "aus Lastannahmen (inkl. γ_f)"),
    Feld("f_ax_d", "Axialkraft Bemessung F_d", "N", 0, 1e8, 100, 1, "Rotorschub aus Lastannahmen (inkl. γ_f)"),
    Feld("dm_b", "Schwingbreite Biegemoment ΔM_b", "N*m", 0, 1e7, 10, 1, "Lastfall A"),
    Feld("t_m", "Mittleres Drehmoment T_m", "N*m", 0, 1e7, 10, 1, "Nennmoment des Rotors"),
    Feld("dt", "Schwingbreite Drehmoment ΔT", "N*m", 0, 1e7, 10, 1, "Lastfall A"),
    Feld("beta_s", "Kerbwirkungszahl Biegung β_σ", "", 1, 5, 0.1, 2,
         "glatt 1,0 · Absatz mit großem Radius ≈ 1,5–2 · Passfedernut ≈ 2–2,5 · Pressverband ≈ 2–3 (Tabelle DIN 743-2)"),
    Feld("beta_t", "Kerbwirkungszahl Torsion β_τ", "", 1, 5, 0.1, 2, "meist kleiner als β_σ, z. B. 1,3–1,8"),
    Feld("rz_um", "Rauheit Rz", "um", 0.5, 100, 0.5, 1, "geschliffen 1–4 · feingedreht 6,3 · gedreht 12,5–25"),
    Feld("s_min", "Erforderliche Sicherheit S_min", "", 1, 5, 0.1, 2, "DIN 743: 1,2"),
    Feld("masse_kg", "Überhängende Masse (Rotor)", "kg", 0, 1e5, 1, 1, "für die Durchbiegung"),
    Feld("a_m", "Überhang a (Rotor bis erstes Lager)", "m", 0.01, 5, 0.01, 3, ""),
    Feld("l_m", "Lagerabstand l", "m", 0.02, 5, 0.01, 3, "Abstand der beiden Lager"),
    Feld("theta_zul", "Zulässige Neigung am Lager", "mrad", 0.1, 50, 0.1, 1,
         "Rillenkugellager ≈ 1–3 · Zylinderrollen ≈ 1 · Pendelrollenlager ≈ 30 (Herstellerangabe)"),
]
FELD_EINHEITEN = {x.attr: x.einheit for x in FELDER if not x.auswahl}
FELD_NAMEN = {x.attr: x.name for x in FELDER}
FELD_SUCHBEGRIFFE: dict = {}
BERECHNUNGS_QUELLEN = {
    "m_b_d": ("lasten_iec", "M_shaft,d"),
    "t_d": ("lasten_iec", "M_x,d"),
    "f_ax_d": ("lasten_iec", "F_x,d"),
    "dm_b": ("lasten_iec", "ΔM_shaft"),
    "dt": ("lasten_iec", "ΔM_x"),
    "t_m": ("rotorauslegung", "M"),
    "masse_kg": ("lasten_iec", "m_r"),
    "a_m": ("lasten_iec", "L_rb"),
}


class EingabeFehler(ValueError):
    pass


@dataclass
class WelleEingaben:
    werkstoff: str = werkstoffe.bezeichnung(werkstoffe.werkstoff("42CrMo4", "40–100"))
    d_mm: float = 80.0
    m_b_d: float = 6050.0
    t_d: float = 1290.0
    f_ax_d: float = 10260.0
    dm_b: float = 590.0
    t_m: float = 215.0
    dt: float = 225.0
    beta_s: float = 2.0
    beta_t: float = 1.6
    rz_um: float = 6.3
    s_min: float = 1.2
    masse_kg: float = 45.0
    a_m: float = 0.30
    l_m: float = 0.40
    theta_zul: float = 1.0

    def pruefen(self) -> None:
        if self.werkstoff not in WERKSTOFFE:
            raise EingabeFehler("Bitte einen Stahl aus der Werkstoffdatenbank wählen.")
        if self.d_mm <= 0 or self.l_m <= 0 or self.a_m < 0:
            raise EingabeFehler("Durchmesser und Lagerabstand müssen größer als 0 sein.")
        if self.beta_s < 1 or self.beta_t < 1:
            raise EingabeFehler("Kerbwirkungszahlen sind mindestens 1,0.")


def gueltig_bis_mm(zustand: str) -> float:
    """Obere Abmessungsgrenze der Werkstoffwerte aus dem Zustandstext (Standard 16 mm)."""
    treffer = re.findall(r"(\d+)\s*mm", zustand)
    return float(treffer[-1]) if treffer else 16.0


def k1(d: float, d_bis: float, gruppe: str) -> float:
    """Technologischer Größeneinflussfaktor (unbelegt): Abfall der Festigkeit über den Tabellenbereich hinaus."""
    if d <= d_bis:
        return 1.0
    faktor = 0.23 if gruppe == "Baustahl" else 0.26
    return max(0.6, 1 - faktor * math.log10(min(d, 300) / d_bis))


def k2(d: float) -> float:
    """Geometrischer Größeneinflussfaktor für Biegung und Torsion (unbelegt)."""
    if d < 7.5:
        return 1.0
    if d >= 150:
        return 0.8
    return 1 - 0.2 * math.log10(d / 7.5) / math.log10(20)


def k_f_sigma(rz: float, rm: float) -> float:
    """Einflussfaktor der Oberflächenrauheit, Biegung (unbelegt)."""
    return 1 - 0.22 * math.log10(rz) * (math.log10(rm / 20) - 1)


def berechne(e: WelleEingaben) -> Ergebnis:
    e.pruefen()
    w = werkstoffe.nach_bezeichnung(e.werkstoff)
    rm, re_ = float(w["rm"]), float(w["re"])
    d = e.d_mm
    wb = math.pi * d**3 / 32           # mm³
    wt = math.pi * d**3 / 16
    a_q = math.pi * d**2 / 4
    i_ = math.pi * d**4 / 64           # mm⁴

    # 1. Nennspannungen (MPa)
    s_b = e.m_b_d * 1000 / wb
    t_t = e.t_d * 1000 / wt
    s_zd = e.f_ax_d / a_q
    s_ba = e.dm_b / 2 * 1000 / wb      # Umlaufbiegung: Ausschlag
    t_tm = e.t_m * 1000 / wt
    t_ta = e.dt / 2 * 1000 / wt

    # 2. Statische Bauteilfestigkeit
    d_bis = gueltig_bis_mm(w["zustand"])
    K1 = k1(d, d_bis, w["gruppe"])
    K2F = 1.2
    s_bFK = K1 * K2F * re_
    t_tFK = K1 * K2F * re_ / math.sqrt(3)
    s_zdFK = K1 * re_
    S_F = 1 / math.sqrt((s_zd / s_zdFK + s_b / s_bFK) ** 2 + (t_t / t_tFK) ** 2)

    # 3. Gestaltfestigkeit
    s_bW = 0.5 * K1 * rm
    t_tW = 0.3 * K1 * rm
    K2 = k2(d)
    KFs = k_f_sigma(e.rz_um, rm)
    KFt = 0.575 * KFs + 0.425
    Ks = e.beta_s / K2 + 1 / KFs - 1
    Kt = e.beta_t / K2 + 1 / KFt - 1
    s_bWK = s_bW / Ks
    t_tWK = t_tW / Kt
    psi_s = s_bWK / (2 * K1 * rm - s_bWK)
    psi_t = t_tWK / (2 * K1 * rm - t_tWK)
    s_mv = math.sqrt(3) * t_tm                 # Vergleichsmittelspannung (nur Torsion mittel)
    t_mv = s_mv / math.sqrt(3)
    s_bADK = max(1e-9, s_bWK - psi_s * s_mv)
    t_tADK = max(1e-9, t_tWK - psi_t * t_mv)
    S_D = 1 / math.sqrt((s_ba / s_bADK) ** 2 + (t_ta / t_tADK) ** 2) if (s_ba or t_ta) else float("inf")

    # 4. Verformung (Kragarm über zwei Stützen)
    F = e.masse_kg * 9.81
    a, l = e.a_m * 1000, e.l_m * 1000     # mm
    f_mm = F * a**2 * (l + a) / (3 * E_STAHL * i_)
    theta = F * a * l / (3 * E_STAHL * i_) * 1000   # mrad, am rotorseitigen Lager

    eingaben = [
        Groesse("Werkstoff", e.werkstoff, 0, ""),
        Groesse("R_m", "Zugfestigkeit", rm, "MPa"),
        Groesse("R_e", "Streckgrenze", re_, "MPa"),
        Groesse("d", "Wellendurchmesser", d, "mm"),
        Groesse("M_b,d", "Biegemoment Bemessung", e.m_b_d, "N·m"),
        Groesse("T_d", "Drehmoment Bemessung", e.t_d, "N·m"),
        Groesse("F_d", "Axialkraft Bemessung", e.f_ax_d, "N"),
        Groesse("ΔM_b", "Schwingbreite Biegemoment", e.dm_b, "N·m"),
        Groesse("T_m", "Mittleres Drehmoment", e.t_m, "N·m"),
        Groesse("ΔT", "Schwingbreite Drehmoment", e.dt, "N·m"),
        Groesse("β_σ", "Kerbwirkungszahl Biegung", e.beta_s, "–"),
        Groesse("β_τ", "Kerbwirkungszahl Torsion", e.beta_t, "–"),
        Groesse("Rz", "Rauheit", e.rz_um, "µm"),
        Groesse("m", "Überhängende Masse", e.masse_kg, "kg"),
        Groesse("a", "Überhang", e.a_m, "m"),
        Groesse("l", "Lagerabstand", e.l_m, "m"),
    ]
    S = Schritt
    schritte = [
        S("Querschnittswerte", "W_b = π·d³/32;  W_t = π·d³/16;  A = π·d²/4",
          f"W_b = π·{f(d)}³/32 mm³", Groesse("W_b", "Widerstandsmoment Biegung", wb, "mm³")),
        S("Biegespannung (Bemessung)", "σ_b = M_b,d / W_b", f"σ_b = {f(e.m_b_d)}·10³ N·mm / {f(wb)} mm³",
          Groesse("σ_b", "Biegespannung", s_b, "MPa")),
        S("Torsionsspannung (Bemessung)", "τ_t = T_d / W_t", f"τ_t = {f(e.t_d)}·10³ N·mm / {f(wt)} mm³",
          Groesse("τ_t", "Torsionsspannung", t_t, "MPa")),
        S("Zugspannung aus Schub (Bemessung)", "σ_zd = F_d / A", f"σ_zd = {f(e.f_ax_d)} N / {f(a_q)} mm²",
          Groesse("σ_zd", "Zug-/Druckspannung", s_zd, "MPa")),
        S("Größeneinfluss Werkstoff  [unbelegt]", "K1 = 1 bis d_Tabelle; darüber 1 − 0,26·lg(d/d_Tabelle) (Baustahl 0,23)",
          f"d = {f(d)} mm, Tabellenwerte gelten bis {f(d_bis)} mm", Groesse("K1", "Größeneinflussfaktor Werkstoff", K1, "–")),
        S("Fließgrenzen des Bauteils  [K2F unbelegt]", "σ_bFK = K1·K2F·R_e;  τ_tFK = K1·K2F·R_e/√3;  K2F = 1,2",
          f"σ_bFK = {f(K1)}·1,2·{f(re_)} MPa", Groesse("σ_bFK", "Bauteilfließgrenze Biegung", s_bFK, "MPa")),
        S("Sicherheit gegen Fließen", "S_F = 1/√((σ_zd/σ_zdFK + σ_b/σ_bFK)² + (τ_t/τ_tFK)²)",
          f"S_F = 1/√(({f(s_zd)}/{f(s_zdFK)} + {f(s_b)}/{f(s_bFK)})² + ({f(t_t)}/{f(t_tFK)})²)",
          Groesse("S_F", "Sicherheit gegen Fließen", S_F, "–")),
        S("Wechselfestigkeit Probestab  [unbelegt]", "σ_bW = 0,5·K1·R_m;  τ_tW = 0,3·K1·R_m",
          f"σ_bW = 0,5·{f(K1)}·{f(rm)} MPa", Groesse("σ_bW", "Biegewechselfestigkeit", s_bW, "MPa")),
        S("Geometrischer Größeneinfluss  [unbelegt]", "K2 = 1 − 0,2·lg(d/7,5 mm)/lg 20  (7,5 ≤ d < 150 mm)",
          f"K2 = 1 − 0,2·lg({f(d)}/7,5)/lg 20", Groesse("K2", "Geometrischer Größeneinflussfaktor", K2, "–")),
        S("Oberflächeneinfluss  [unbelegt]", "K_Fσ = 1 − 0,22·lg(Rz)·(lg(R_m/20) − 1);  K_Fτ = 0,575·K_Fσ + 0,425",
          f"K_Fσ = 1 − 0,22·lg {f(e.rz_um)}·(lg({f(rm)}/20) − 1)", Groesse("K_Fσ", "Rauheitsfaktor Biegung", KFs, "–")),
        S("Gesamteinflussfaktoren", "K_σ = β_σ/K2 + 1/K_Fσ − 1;  K_τ = β_τ/K2 + 1/K_Fτ − 1",
          f"K_σ = {f(e.beta_s)}/{f(K2)} + 1/{f(KFs)} − 1;  K_τ = {f(e.beta_t)}/{f(K2)} + 1/{f(KFt)} − 1",
          Groesse("K_σ", "Gesamteinflussfaktor Biegung", Ks, "–")),
        S("Gestaltwechselfestigkeit", "σ_bWK = σ_bW/K_σ;  τ_tWK = τ_tW/K_τ",
          f"σ_bWK = {f(s_bW)}/{f(Ks)};  τ_tWK = {f(t_tW)}/{f(Kt)} = {f(t_tWK)} MPa",
          Groesse("σ_bWK", "Gestaltwechselfestigkeit Biegung", s_bWK, "MPa")),
        S("Mittelspannungseinfluss  [unbelegt]", "ψ = σ_WK/(2·K1·R_m − σ_WK);  σ_mv = √3·τ_tm;  σ_ADK = σ_WK − ψ·σ_mv",
          f"τ_tm = {f(t_tm)} MPa;  σ_mv = {f(s_mv)} MPa;  τ_tADK = {f(t_tADK)} MPa",
          Groesse("σ_bADK", "Gestaltausschlagfestigkeit Biegung", s_bADK, "MPa")),
        S("Ausschlagspannungen (Lastfall A)", "σ_ba = (ΔM_b/2)/W_b  (Umlaufbiegung);  τ_ta = (ΔT/2)/W_t",
          f"σ_ba = {f(e.dm_b / 2)}·10³/{f(wb)};  τ_ta = {f(e.dt / 2)}·10³/{f(wt)} = {f(t_ta)} MPa",
          Groesse("σ_ba", "Biegeausschlagspannung", s_ba, "MPa")),
        S("Sicherheit gegen Dauerbruch", "S_D = 1/√((σ_ba/σ_bADK)² + (τ_ta/τ_tADK)²)",
          f"S_D = 1/√(({f(s_ba)}/{f(s_bADK)})² + ({f(t_ta)}/{f(t_tADK)})²)", Groesse("S_D", "Sicherheit gegen Dauerbruch", S_D, "–")),
        S("Durchbiegung am Rotor", "f = F·a²·(l + a)/(3·E·I);  F = m·g;  I = π·d⁴/64",
          f"f = {f(F)} N·{f(a)}² mm²·({f(l)} + {f(a)}) mm/(3·210000 MPa·{f(i_)} mm⁴)", Groesse("f", "Durchbiegung am Rotor", f_mm, "mm")),
        S("Neigung im rotorseitigen Lager", "θ = F·a·l/(3·E·I)", f"θ = {f(F)}·{f(a)}·{f(l)}/(3·210000·{f(i_)})",
          Groesse("θ", "Neigung am Lager", theta, "mrad")),
    ]
    ergebnisse = [
        Groesse("S_D", "Sicherheit gegen Dauerbruch", S_D, "–"),
        Groesse("S_F", "Sicherheit gegen Fließen", S_F, "–"),
        Groesse("σ_b", "Biegespannung (Bemessung)", s_b, "MPa"),
        Groesse("τ_t", "Torsionsspannung (Bemessung)", t_t, "MPa"),
        Groesse("σ_ba", "Biegeausschlagspannung", s_ba, "MPa"),
        Groesse("σ_bADK", "Gestaltausschlagfestigkeit Biegung", s_bADK, "MPa"),
        Groesse("f", "Durchbiegung am Rotor", f_mm, "mm"),
        Groesse("θ", "Neigung am Lager", theta, "mrad"),
        Groesse("d", "Wellendurchmesser", d, "mm"),
    ]
    pruefungen = [
        Pruefung("Sicherheit gegen Fließen", f"S_F = {f(S_F, 3)} ≥ {f(e.s_min, 3)}", S_F >= e.s_min,
                 "" if S_F >= e.s_min else "Durchmesser vergrößern oder festeren Werkstoff wählen."),
        Pruefung("Sicherheit gegen Dauerbruch", f"S_D = {f(S_D, 3)} ≥ {f(e.s_min, 3)}", S_D >= e.s_min,
                 "" if S_D >= e.s_min else "Durchmesser vergrößern, Kerbe entschärfen (größerer Radius) oder Oberfläche verbessern."),
        Pruefung("Neigung am Lager", f"θ = {f(theta, 3)} mrad ≤ {f(e.theta_zul, 3)} mrad", theta <= e.theta_zul,
                 "" if theta <= e.theta_zul else "Lagerabstand vergrößern, Welle steifer oder winkelbewegliches Lager."),
        Pruefung("Werkstoffwerte gelten für diesen Durchmesser", f"d = {f(d)} mm ≤ {f(d_bis)} mm", d <= d_bis,
                 "" if d <= d_bis else "Festigkeit über K1 abgemindert – besser die Werkstoffzeile für diesen Durchmesser wählen."),
    ]
    hinweise = [
        "Lasten aus den Lastannahmen enthalten bereits γ_f = 3 (Bemessung). Die Dauerfestigkeit wird mit den "
        "Schwingbreiten aus Lastfall A (γ_f = 1) nachgewiesen.",
        "Kerbwirkungszahlen sind Eingaben: Für die endgültige Welle aus DIN 743-2 bzw. Kerbformzahl-Diagrammen ablesen, "
        "sobald die Geometrie im CAD feststeht.",
        "Neigung: Herstellerangabe des gewählten Lagers verwenden.",
    ]
    unbelegt = [
        "Faktoren K1, K2, K2F, K_Fσ, die Wechselfestigkeiten 0,5·R_m / 0,3·R_m und die Mittelspannungsempfindlichkeit ψ "
        "sind aus dem Gedächtnis nach DIN 743 übernommen – mit der Norm oder Roloff/Matek prüfen.",
        "Die Prüfung mit einem Literatur-Rechenbeispiel (N5) steht noch aus.",
    ]
    return Ergebnis(TITEL, TYP, eingaben, schritte, ergebnisse, pruefungen, QUELLEN, hinweise, unbelegt=unbelegt)
