"""Lastannahmen für Kleinwindanlagen nach dem vereinfachten Lastmodell (SLM) der IEC 61400-2 (Lastenheft M19).

Koordinaten wie in der Norm:
  Blatt:  x = in Schubrichtung (Schlag), y = in Drehrichtung (Schwenk), z = längs des Blatts
  Welle:  x = Wellenachse (Schub, Drehmoment), „shaft“ = Biegung der Welle am ersten Lager

Belegt (aus Sekundärquellen, die die Norm zitieren): Lastfälle A, B, D, H und die Teilsicherheits-
beiwerte für Lasten. Unbelegt (aus dem Gedächtnis, vor Bau mit dem Normtext prüfen): Lastfälle E und F
sowie die Klassenwerte V_ref. Diese Stellen sind im Protokoll ausdrücklich gekennzeichnet.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .basis import Ergebnis, Feld, Groesse, Pruefung, Schritt, formatiere as f

TYP = "lasten_iec"
TITEL = "Lastannahmen nach IEC 61400-2 (vereinfachtes Lastmodell)"
KURZ = "Lastannahmen IEC 61400-2"
BESCHREIBUNG = ("Bemessungslasten für Blatt, Rotorwelle und Gondel nach dem vereinfachten Lastmodell der "
                "Kleinwindnorm. Grundlage für Welle, Lager, Schrauben und Turm in Meilenstein 5.")
HAUPT = "F_x,d"
G = 9.81

KLASSEN = {"I": 50.0, "II": 42.5, "III": 37.5, "IV": 30.0}   # V_ref in m/s (unbelegt, siehe oben)
GAMMA_F_BRUCH = 3.0     # Teilsicherheitsbeiwert Last, vereinfachtes Lastmodell, Bruch (belegt)
GAMMA_F_ERMUEDUNG = 1.0  # dto. Ermüdung (belegt)
C_T_MAX = 0.5           # Lastfall D (belegt)
C_D = 1.5               # Widerstandsbeiwert Blatt, Lastfall H (belegt)
E_R_ANTEIL = 0.005      # Rotorexzentrizität e_r = 0,005·R, wenn nicht anders nachgewiesen (belegt)

QUELLEN = [
    "IEC 61400-2:2013 Small wind turbines – Design requirements, Abschnitt 7.4 „Simplified load calculations“ "
    "(Normtext selbst nicht eingesehen)",
    "NREL/TP-5000-83708 (2022): Improvements to the Simplified Loads Methodology in IEC 61400-2 – zitiert die "
    "SLM-Gleichungen IEC21–IEC26, IEC27–IEC30, IEC38–IEC43 und Tabelle der Teilsicherheitsbeiwerte",
    "NREL/CP-500-33004 (2003): Investigation of the IEC Safety Standard for Small Wind Turbine Design – "
    "Lastfall D: F = C_T·½·ρ·A·(2,5·V_ave)², C_T = 0,5",
    "D. Wood: Small Wind Turbines – Analysis, Design, and Application, Springer 2011, Kap. 9 "
    "„Using the IEC Simple Load Model“",
]

FELDER = [
    Feld("klasse", "Anlagenklasse", "", auswahl=tuple(KLASSEN), tipp="I: windreiche Küste … IV: Binnenland. "
         "Bestimmt V_ref, V_ave = 0,2·V_ref und V_e50 = 1,4·V_ref"),
    Feld("durchmesser_m", "Rotordurchmesser", "m", 0.5, 30, 0.1, 2, "aus der Rotorauslegung"),
    Feld("drehzahl_rpm", "Auslegungsdrehzahl n_design", "1/min", 10, 2000, 5, 1, "aus der Rotorauslegung"),
    Feld("moment_nm", "Auslegungsdrehmoment Q_design", "N*m", 1, 1e6, 10, 1, "Rotordrehmoment aus der Rotorauslegung"),
    Feld("schnelllaufzahl", "Auslegungs-Schnelllaufzahl λ_design", "", 1, 15, 0.5, 1, "aus der Rotorauslegung"),
    Feld("blattzahl", "Blattzahl B", "", 1, 6, 1, 0, "Dreiblattrotor: 3"),
    Feld("blattmasse_kg", "Masse eines Blatts m_B", "kg", 0.1, 500, 0.5, 1, "ANNAHME bis zur Konstruktion (MS6–MS8)"),
    Feld("r_cog_anteil", "Schwerpunkt Blatt R_cog / R", "", 0.1, 0.8, 0.01, 2,
         "Abstand Blattschwerpunkt von der Rotorachse, bezogen auf R (typisch 0,3–0,4)"),
    Feld("rotormasse_kg", "Masse des Rotors m_r (Blätter + Nabe)", "kg", 0.5, 2000, 1, 1, "ANNAHME bis zur Konstruktion"),
    Feld("l_rb_m", "Abstand Rotor – erstes Lager L_rb", "m", 0.01, 3, 0.01, 2, "Hebelarm für die Wellenbiegung"),
    Feld("l_rt_m", "Abstand Rotor – Gierachse L_rt", "m", 0.01, 3, 0.01, 2, "für Lastfall B (Gieren)"),
    Feld("flaeche_blatt_m2", "Projizierte Blattfläche A_proj,B", "m^2", 0.01, 20, 0.01, 2,
         "Fläche eines Blatts in Draufsicht, etwa mittlere Profiltiefe × Blattlänge"),
    Feld("n_max_faktor", "Maximaldrehzahl n_max / n_design", "", 1.0, 3.0, 0.05, 2,
         "ANNAHME: aus Regelung oder Messung bestimmen (Lastfall E)"),
    Feld("kurzschluss_faktor", "Kurzschluss-Faktor G", "", 1.0, 5.0, 0.1, 1,
         "Verhältnis Kurzschlussmoment / Nennmoment des Generators (Lastfall F, ohne Nachweis 2,0)"),
    Feld("luftdichte", "Luftdichte", "kg/m^3", 0.5, 1.5, 0.005, 3, "Norm: 1,225 kg/m³"),
]
FELD_EINHEITEN = {x.attr: x.einheit for x in FELDER if not x.auswahl}
FELD_NAMEN = {x.attr: x.name for x in FELDER}
FELD_SUCHBEGRIFFE: dict = {}
BERECHNUNGS_QUELLEN = {
    "durchmesser_m": ("rotorauslegung", "D"),
    "drehzahl_rpm": ("rotorauslegung", "n"),
    "moment_nm": ("rotorauslegung", "M"),
    "schnelllaufzahl": ("rotorauslegung", "λ"),
}


class EingabeFehler(ValueError):
    pass


@dataclass
class LastEingaben:
    klasse: str = "III"
    durchmesser_m: float = 4.8
    drehzahl_rpm: float = 260.0
    moment_nm: float = 215.0
    schnelllaufzahl: float = 6.0
    blattzahl: float = 3
    blattmasse_kg: float = 8.0
    r_cog_anteil: float = 0.33
    rotormasse_kg: float = 45.0
    l_rb_m: float = 0.30
    l_rt_m: float = 0.40
    flaeche_blatt_m2: float = 0.45
    n_max_faktor: float = 1.5
    kurzschluss_faktor: float = 2.0
    luftdichte: float = 1.225

    def pruefen(self) -> None:
        if self.klasse not in KLASSEN:
            raise EingabeFehler(f"Anlagenklasse „{self.klasse}“ gibt es nicht (I bis IV).")
        for name in ("durchmesser_m", "drehzahl_rpm", "moment_nm", "schnelllaufzahl", "blattmasse_kg",
                     "rotormasse_kg", "l_rb_m", "l_rt_m", "flaeche_blatt_m2", "luftdichte"):
            if getattr(self, name) <= 0:
                raise EingabeFehler(f"„{FELD_NAMEN[name]}“ muss größer als 0 sein.")
        if int(self.blattzahl) < 1:
            raise EingabeFehler("Die Blattzahl muss mindestens 1 sein.")
        if self.rotormasse_kg < self.blattzahl * self.blattmasse_kg:
            raise EingabeFehler("Die Rotormasse muss mindestens so groß sein wie die Masse aller Blätter.")


def berechne(e: LastEingaben) -> Ergebnis:
    e.pruefen()
    B = int(round(e.blattzahl))
    R = e.durchmesser_m / 2
    A = math.pi * R**2
    rho = e.luftdichte
    v_ref = KLASSEN[e.klasse]
    v_ave = 0.2 * v_ref
    v_e50 = 1.4 * v_ref
    w_n = e.drehzahl_rpm * 2 * math.pi / 60
    w_max = w_n * e.n_max_faktor
    Q = e.moment_nm
    lam = e.schnelllaufzahl
    m_b, m_r = e.blattmasse_kg, e.rotormasse_kg
    r_cog = e.r_cog_anteil * R
    i_b = 4 / 3 * m_b * r_cog**2           # Trägheit eines Blatts um die Rotorachse (Stab-Näherung)
    e_r = E_R_ANTEIL * R
    a_b = e.flaeche_blatt_m2

    # Lastfall A – Ermüdung (Schwingbreiten)
    dF_zB = 2 * m_b * r_cog * w_n**2
    dM_xB = Q / B + 2 * m_b * G * r_cog
    dM_yB = lam * Q / B
    dF_xs = 1.5 * lam * Q / R
    dM_xs = Q + 2 * m_r * G * e_r
    dM_s = 2 * m_r * G * e.l_rb_m + R / 6 * dF_xs
    # Lastfall B – Gieren
    w_gier = 3.0 if A <= 2 else max(0.0, 3.0 - 0.01 * (A - 2))
    M_yB_B = m_b * w_gier**2 * e.l_rt_m * r_cog + 2 * w_gier * i_b * w_n + R / 9 * dF_xs
    if B > 2:
        M_s_B = B * w_gier * w_n * i_b + m_r * G * e.l_rb_m + R / 6 * dF_xs
    else:
        M_s_B = 4 * w_gier * w_n * i_b + m_r * G * e.l_rb_m + R / 6 * dF_xs
    # Lastfall D – maximaler Schub
    F_x_D = C_T_MAX * 0.5 * rho * A * (2.5 * v_ave) ** 2
    # Lastfall E – maximale Drehzahl (unbelegt)
    F_zB_E = m_b * r_cog * w_max**2
    M_s_E = m_r * G * e.l_rb_m + m_r * e_r * w_max**2 * e.l_rb_m
    # Lastfall F – Kurzschluss am Generator (unbelegt)
    M_x_F = e.kurzschluss_faktor * Q
    # Lastfall H – stillstehender Rotor im Extremwind
    M_yB_H = C_D / 4 * rho * v_e50**2 * a_b * R
    F_x_H = B * C_D * 0.5 * rho * v_e50**2 * a_b

    gf = GAMMA_F_BRUCH
    bemessung = {
        "M_yB,d": max(M_yB_B, M_yB_H) * gf,
        "F_zB,d": F_zB_E * gf,
        "F_x,d": max(F_x_D, F_x_H) * gf,
        "M_x,d": max(M_x_F, Q) * gf,
        "M_shaft,d": max(M_s_B, M_s_E) * gf,
    }
    massgebend_schub = "D (maximaler Schub)" if F_x_D >= F_x_H else "H (Extremwind, Stillstand)"
    massgebend_blatt = "B (Gieren)" if M_yB_B >= M_yB_H else "H (Extremwind, Stillstand)"

    eingaben = [
        Groesse("Klasse", f"Anlagenklasse {e.klasse}: V_ref", v_ref, "m/s"),
        Groesse("R", "Rotorradius", R, "m"),
        Groesse("n_design", "Auslegungsdrehzahl", e.drehzahl_rpm, "1/min"),
        Groesse("Q_design", "Auslegungsdrehmoment", Q, "N·m"),
        Groesse("λ_design", "Auslegungs-Schnelllaufzahl", lam, "–"),
        Groesse("B", "Blattzahl", B, "–"),
        Groesse("m_B", "Masse eines Blatts (Annahme)", m_b, "kg"),
        Groesse("R_cog", "Schwerpunktradius Blatt", r_cog, "m"),
        Groesse("m_r", "Rotormasse (Annahme)", m_r, "kg"),
        Groesse("L_rb", "Abstand Rotor – erstes Lager", e.l_rb_m, "m"),
        Groesse("L_rt", "Abstand Rotor – Gierachse", e.l_rt_m, "m"),
        Groesse("A_proj,B", "Projizierte Blattfläche", a_b, "m²"),
        Groesse("n_max/n", "Drehzahlverhältnis (Annahme)", e.n_max_faktor, "–"),
        Groesse("G", "Kurzschluss-Faktor", e.kurzschluss_faktor, "–"),
        Groesse("ρ", "Luftdichte", rho, "kg/m³"),
    ]
    S = Schritt
    schritte = [
        S("Windgeschwindigkeiten der Klasse", "V_ave = 0,2·V_ref;  V_e50 = 1,4·V_ref",
          f"V_ave = 0,2·{f(v_ref)};  V_e50 = 1,4·{f(v_ref)} m/s", Groesse("V_e50", "50-Jahres-Extremwind", v_e50, "m/s")),
        S("Winkelgeschwindigkeit und Blattträgheit", "ω_n = 2π·n/60;  I_B ≈ 4/3·m_B·R_cog²  (schlanker Stab)",
          f"ω_n = 2π·{f(e.drehzahl_rpm)}/60;  I_B = 4/3·{f(m_b)} kg·{f(r_cog)}² m²",
          Groesse("ω_n", "Winkelgeschwindigkeit", w_n, "rad/s")),
        S("A: Fliehkraft-Schwingbreite am Blattfuß", "ΔF_zB = 2·m_B·R_cog·ω_n²",
          f"ΔF_zB = 2·{f(m_b)} kg·{f(r_cog)} m·{f(w_n)}² 1/s²", Groesse("ΔF_zB", "Schwingbreite Blatt-Zugkraft", dF_zB, "N")),
        S("A: Schwenkmoment-Schwingbreite am Blattfuß", "ΔM_xB = Q_design/B + 2·m_B·g·R_cog",
          f"ΔM_xB = {f(Q)}/{B} + 2·{f(m_b)}·9,81·{f(r_cog)}", Groesse("ΔM_xB", "Schwingbreite Schwenkmoment", dM_xB, "N·m")),
        S("A: Schlagmoment-Schwingbreite am Blattfuß", "ΔM_yB = λ_design·Q_design/B",
          f"ΔM_yB = {f(lam)}·{f(Q)}/{B}", Groesse("ΔM_yB", "Schwingbreite Schlagmoment", dM_yB, "N·m")),
        S("A: Schub-Schwingbreite an der Welle", "ΔF_x-shaft = 3/2·λ_design·Q_design/R",
          f"ΔF_x = 1,5·{f(lam)}·{f(Q)}/{f(R)}", Groesse("ΔF_x", "Schwingbreite Wellenschub", dF_xs, "N")),
        S("A: Drehmoment-Schwingbreite an der Welle", "ΔM_x-shaft = Q_design + 2·m_r·g·e_r;  e_r = 0,005·R",
          f"ΔM_x = {f(Q)} + 2·{f(m_r)}·9,81·{f(e_r)}", Groesse("ΔM_x", "Schwingbreite Wellendrehmoment", dM_xs, "N·m")),
        S("A: Biegemoment-Schwingbreite an der Welle", "ΔM_shaft = 2·m_r·g·L_rb + R/6·ΔF_x-shaft",
          f"ΔM_shaft = 2·{f(m_r)}·9,81·{f(e.l_rb_m)} + {f(R)}/6·{f(dF_xs)}",
          Groesse("ΔM_shaft", "Schwingbreite Wellenbiegung", dM_s, "N·m")),
        S("B: Maximale Giergeschwindigkeit", "ω_yaw,max = 3 rad/s (A ≤ 2 m²), sonst 3 − 0,01·(A − 2)",
          f"A = {f(A)} m²", Groesse("ω_yaw", "Max. Giergeschwindigkeit", w_gier, "rad/s")),
        S("B: Schlagmoment beim Gieren", "M_yB = m_B·ω_yaw²·L_rt·R_cog + 2·ω_yaw·I_B·ω_n + R/9·ΔF_x-shaft",
          f"M_yB = {f(m_b)}·{f(w_gier)}²·{f(e.l_rt_m)}·{f(r_cog)} + 2·{f(w_gier)}·{f(i_b)}·{f(w_n)} + {f(R)}/9·{f(dF_xs)}",
          Groesse("M_yB,B", "Schlagmoment Gieren", M_yB_B, "N·m")),
        S("B: Wellenbiegung beim Gieren (Kreiselmoment)",
          "M_shaft = B·ω_yaw·ω_n·I_B + m_r·g·L_rb + R/6·ΔF_x-shaft  (B > 2)",
          f"M_shaft = {B}·{f(w_gier)}·{f(w_n)}·{f(i_b)} + {f(m_r)}·9,81·{f(e.l_rb_m)} + {f(R)}/6·{f(dF_xs)}",
          Groesse("M_shaft,B", "Wellenbiegung Gieren", M_s_B, "N·m")),
        S("D: Maximaler Rotorschub", "F_x-shaft = C_T·½·ρ·A·(2,5·V_ave)²;  C_T = 0,5",
          f"F_x = 0,5·½·{f(rho)}·{f(A)} m²·(2,5·{f(v_ave)} m/s)²", Groesse("F_x,D", "Max. Schub", F_x_D, "N")),
        S("E: Fliehkraft bei Maximaldrehzahl  [unbelegt]", "F_zB = m_B·R_cog·ω_max²",
          f"ω_max = {f(e.n_max_faktor)}·{f(w_n)} = {f(w_max)} rad/s;  F_zB = {f(m_b)}·{f(r_cog)}·{f(w_max)}²",
          Groesse("F_zB,E", "Blatt-Zugkraft bei n_max", F_zB_E, "N")),
        S("E: Wellenbiegung bei Maximaldrehzahl  [unbelegt]", "M_shaft = m_r·g·L_rb + m_r·e_r·ω_max²·L_rb",
          f"M_shaft = {f(m_r)}·9,81·{f(e.l_rb_m)} + {f(m_r)}·{f(e_r)}·{f(w_max)}²·{f(e.l_rb_m)}",
          Groesse("M_shaft,E", "Wellenbiegung bei n_max", M_s_E, "N·m")),
        S("F: Kurzschluss am Generator  [unbelegt]", "M_x-shaft = G·Q_design",
          f"M_x = {f(e.kurzschluss_faktor)}·{f(Q)}", Groesse("M_x,F", "Wellendrehmoment Kurzschluss", M_x_F, "N·m")),
        S("H: Schlagmoment im Extremwind (Stillstand)", "M_yB = C_d/4·ρ·V_e50²·A_proj,B·R;  C_d = 1,5",
          f"M_yB = 1,5/4·{f(rho)}·{f(v_e50)}²·{f(a_b)}·{f(R)}", Groesse("M_yB,H", "Schlagmoment Extremwind", M_yB_H, "N·m")),
        S("H: Rotorschub im Extremwind (Stillstand)", "F_x-shaft = B·C_d·½·ρ·V_e50²·A_proj,B",
          f"F_x = {B}·1,5·½·{f(rho)}·{f(v_e50)}²·{f(a_b)}", Groesse("F_x,H", "Schub Extremwind", F_x_H, "N")),
        S("Bemessungslasten (Bruch)", "Last_d = γ_f · max(Lastfälle);  γ_f = 3,0 (vereinfachtes Lastmodell)",
          f"F_x,d = 3,0·max({f(F_x_D)}; {f(F_x_H)}) N", Groesse("F_x,d", "Bemessungsschub Welle", bemessung["F_x,d"], "N")),
    ]
    ergebnisse = [
        Groesse("F_x,d", "Bemessungsschub Rotorwelle (γ_f = 3)", bemessung["F_x,d"], "N"),
        Groesse("M_x,d", "Bemessungsdrehmoment Rotorwelle", bemessung["M_x,d"], "N·m"),
        Groesse("M_shaft,d", "Bemessungs-Biegemoment Rotorwelle", bemessung["M_shaft,d"], "N·m"),
        Groesse("M_yB,d", "Bemessungs-Schlagmoment Blattfuß", bemessung["M_yB,d"], "N·m"),
        Groesse("F_zB,d", "Bemessungs-Zugkraft Blattfuß", bemessung["F_zB,d"], "N"),
        Groesse("ΔM_shaft", "Ermüdung: Schwingbreite Wellenbiegung (γ_f = 1)", dM_s, "N·m"),
        Groesse("ΔM_x", "Ermüdung: Schwingbreite Wellendrehmoment", dM_xs, "N·m"),
        Groesse("ΔM_yB", "Ermüdung: Schwingbreite Schlagmoment Blatt", dM_yB, "N·m"),
        Groesse("V_e50", "50-Jahres-Extremwind", v_e50, "m/s"),
        Groesse("F_x,k", "Schub Rotorwelle charakteristisch (ohne γ_f)", max(F_x_D, F_x_H), "N"),
        Groesse("M_x,k", "Drehmoment Rotorwelle charakteristisch", max(M_x_F, Q), "N·m"),
        Groesse("M_shaft,k", "Biegemoment Rotorwelle charakteristisch", max(M_s_B, M_s_E), "N·m"),
        Groesse("γ_f", "Teilsicherheitsbeiwert Last (Bruch)", gf, "–"),
        Groesse("n_max", "Maximaldrehzahl (Annahme)", e.drehzahl_rpm * e.n_max_faktor, "1/min"),
        Groesse("V_ave", "Mittlerer Jahreswind der Klasse", v_ave, "m/s"),
    ]
    zeilen = [
        ["A", "Normalbetrieb (Ermüdung)", "ΔF_x-shaft", round(dF_xs, 1), "N", 1.0, round(dF_xs, 1), "belegt"],
        ["A", "", "ΔM_x-shaft", round(dM_xs, 1), "N·m", 1.0, round(dM_xs, 1), "belegt"],
        ["A", "", "ΔM_shaft", round(dM_s, 1), "N·m", 1.0, round(dM_s, 1), "belegt"],
        ["A", "", "ΔM_yB", round(dM_yB, 1), "N·m", 1.0, round(dM_yB, 1), "belegt"],
        ["B", "Gieren", "M_yB", round(M_yB_B, 1), "N·m", gf, round(M_yB_B * gf, 1), "belegt"],
        ["B", "", "M_shaft", round(M_s_B, 1), "N·m", gf, round(M_s_B * gf, 1), "belegt"],
        ["D", "Maximaler Schub", "F_x-shaft", round(F_x_D, 1), "N", gf, round(F_x_D * gf, 1), "belegt"],
        ["E", "Maximaldrehzahl", "F_zB", round(F_zB_E, 1), "N", gf, round(F_zB_E * gf, 1), "unbelegt"],
        ["E", "", "M_shaft", round(M_s_E, 1), "N·m", gf, round(M_s_E * gf, 1), "unbelegt"],
        ["F", "Kurzschluss", "M_x-shaft", round(M_x_F, 1), "N·m", gf, round(M_x_F * gf, 1), "unbelegt"],
        ["H", "Extremwind, Stillstand", "M_yB", round(M_yB_H, 1), "N·m", gf, round(M_yB_H * gf, 1), "belegt"],
        ["H", "", "F_x-shaft", round(F_x_H, 1), "N", gf, round(F_x_H * gf, 1), "belegt"],
    ]
    tabellen = [{"titel": "Lastfälle (charakteristisch, Teilsicherheitsbeiwert, Bemessung)",
                 "spalten": ["Fall", "Situation", "Größe", "Wert", "Einheit", "γ_f", "Bemessung", "Beleg"],
                 "zeilen": zeilen}]
    pruefungen: list[Pruefung] = []
    hinweise = [
        f"Maßgebend für den Wellenschub: Lastfall {massgebend_schub}; für den Blattfuß (Schlag): Lastfall "
        f"{massgebend_blatt}.",
        "Massen, Blattfläche und Lagerabstände sind Annahmen, bis die Konstruktion (MS6–MS8) die echten Werte liefert. "
        "Dann neu berechnen.",
        "Nicht enthalten: Lastfall C (Gierfehler), G (Bremsen; folgt mit der Bremse in MS5), I (Stillstand mit Fehler), "
        "J (Transport) und die Turm-/Gondel-Windlast (folgt mit Turm und Fundament in MS5).",
        "Die Teilsicherheitsbeiwerte für Werkstoffe (γ_m) werden in den Festigkeitsnachweisen in MS5 angesetzt.",
    ]
    unbelegt = [
        "Lastfall E (Maximaldrehzahl): Gleichungen aus dem Gedächtnis, Normtext prüfen.",
        "Lastfall F (Kurzschluss): G = 2,0 ohne Nachweis, aus dem Gedächtnis.",
        "Klassenwerte V_ref (50 / 42,5 / 37,5 / 30 m/s) aus dem Gedächtnis; Klasse III mit V_ave = 7,5 m/s "
        "ist durch eine Sekundärquelle bestätigt.",
    ]
    return Ergebnis(TITEL, TYP, eingaben, schritte, ergebnisse, pruefungen, QUELLEN, hinweise,
                    tabellen=tabellen, unbelegt=unbelegt)
