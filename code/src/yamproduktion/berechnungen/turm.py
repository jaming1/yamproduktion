"""Turm (Stahlrohr) und Blockfundament (Lastenheft M25).

  1. Windlast Turm          w = ½·ρ·V_e50²·c_f·D;  F_T = w·H;  M_T = w·H²/2
  2. Kippmoment Turmfuß     M_k = F_x,k·H + M_T;   Bemessung M_d = γ_f·M_k
  3. Spannung Turmfuß       σ_d = M_d/W + N_d/A ≤ f_y/γ_M0;   Querschnittsklasse D/t ≤ 90·ε²
  4. Kopfauslenkung         f = F_x,k·H³/(3·E·I) + w·H⁴/(8·E·I)
  5. Eigenfrequenz          f0 = 1/(2π)·√(3·E·I / ((m_Kopf + 0,24·m_Turm)·H³));  Abstand zu 1P und 3P ≥ 10 %
  6. Flanschschrauben       F_A = 4·M_d/(n·D_L)  (je Schraube, Zug)
  7. Fundament              e = M_F/N;  klaffende Fuge e ≤ a/3;  Bodenpressung;  Kippsicherheit
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .. import werkstoffe
from .basis import Ergebnis, Feld, Groesse, Pruefung, Schritt, formatiere as f

TYP = "turm"
TITEL = "Turm und Fundament"
KURZ = "Turm & Fundament"
BESCHREIBUNG = ("Stahlrohrturm: Kippmoment, Biegespannung, Kopfauslenkung, Eigenfrequenz gegenüber der Rotordrehzahl, "
                "Kraft je Flanschschraube. Blockfundament: Bodenpressung und Standsicherheit.")
HAUPT = "η_σ"
WERKSTOFFE = werkstoffe.auswahl(("Baustahl",))
E_STAHL = 210000.0
RHO_STAHL = 7850.0
GAMMA_BETON = 25.0     # kN/m³ Stahlbeton
GAMMA_M0 = 1.0

QUELLEN = [
    "DIN EN 1993-1-1 (Eurocode 3): Querschnittsnachweis σ ≤ f_y/γ_M0, γ_M0 = 1,0; Grenze Querschnittsklasse 3 "
    "für Rohre D/t ≤ 90·ε², ε = √(235/f_y)",
    "Eigenfrequenz Kragträger mit Kopfmasse (Rayleigh, 0,24-fache Turmmasse am Kopf): Gasch/Twele, Kap. Turm",
    "IEC 61400-2 Abschnitt 7.4: Windlast auf Turm F = ½·ρ·V_e50²·c_f·A_proj (Gl. IEC43), γ_f = 3",
    "DIN 1054 / Grundbau: Lage der Resultierenden, klaffende Fuge, Bodenpressung bei Teilauflast",
]

FELDER = [
    Feld("h_m", "Turmhöhe (≈ Nabenhöhe)", "m", 2, 60, 0.5, 1, "aus den Anforderungen"),
    Feld("d_mm", "Rohraußendurchmesser D", "mm", 50, 2000, 1, 1, ""),
    Feld("t_mm", "Wanddicke t", "mm", 2, 50, 0.5, 1, ""),
    Feld("werkstoff", "Werkstoff", "", auswahl=WERKSTOFFE),
    Feld("f_x_k", "Rotorschub charakteristisch F_x,k", "N", 0, 1e7, 10, 1, "aus Lastannahmen (ohne γ_f)"),
    Feld("gamma_f", "Teilsicherheitsbeiwert Last γ_f", "", 1, 5, 0.05, 2, "vereinfachtes Lastmodell: 3,0"),
    Feld("v_e50", "Extremwind V_e50", "m/s", 10, 90, 0.5, 1, "aus Lastannahmen"),
    Feld("c_f", "Kraftbeiwert Rohr c_f", "", 0.3, 2, 0.05, 2, "Kreiszylinder ≈ 0,7 (Richtwert)"),
    Feld("m_kopf", "Kopfmasse (Rotor + Gondel)", "kg", 1, 1e5, 1, 1, "ANNAHME bis zur Konstruktion"),
    Feld("n_rpm", "Rotordrehzahl (Nenn)", "1/min", 10, 2000, 5, 1, "aus der Rotorauslegung"),
    Feld("blattzahl", "Blattzahl", "", 1, 6, 1, 0, ""),
    Feld("n_s", "Anzahl Flanschschrauben", "", 4, 200, 1, 0, ""),
    Feld("d_l_mm", "Lochkreis Flansch D_L", "mm", 50, 3000, 1, 1, ""),
    Feld("a_m", "Fundament Kantenlänge a (quadratisch)", "m", 0.5, 10, 0.05, 2, ""),
    Feld("hf_m", "Fundament Höhe", "m", 0.2, 5, 0.05, 2, ""),
    Feld("sigma_zul", "Zulässige Bodenpressung", "kPa", 50, 1000, 10, 0, "Baugrund; ohne Gutachten vorsichtig 150–200"),
    Feld("luftdichte", "Luftdichte", "kg/m^3", 0.5, 1.5, 0.005, 3, ""),
]
FELD_EINHEITEN = {x.attr: x.einheit for x in FELDER if not x.auswahl}
FELD_NAMEN = {x.attr: x.name for x in FELDER}
FELD_SUCHBEGRIFFE = {"h_m": "nabenhöhe"}
BERECHNUNGS_QUELLEN = {
    "f_x_k": ("lasten_iec", "F_x,k"),
    "gamma_f": ("lasten_iec", "γ_f"),
    "v_e50": ("lasten_iec", "V_e50"),
    "n_rpm": ("rotorauslegung", "n"),
}


class EingabeFehler(ValueError):
    pass


@dataclass
class TurmEingaben:
    h_m: float = 12.0
    d_mm: float = 406.4
    t_mm: float = 10.0
    werkstoff: str = werkstoffe.bezeichnung(werkstoffe.werkstoff("S355J2"))
    f_x_k: float = 3420.0
    gamma_f: float = 3.0
    v_e50: float = 52.5
    c_f: float = 0.7
    m_kopf: float = 150.0
    n_rpm: float = 263.0
    blattzahl: float = 3
    n_s: float = 16
    d_l_mm: float = 480.0
    a_m: float = 2.6
    hf_m: float = 1.2
    sigma_zul: float = 200.0
    luftdichte: float = 1.225

    def pruefen(self) -> None:
        if self.werkstoff not in WERKSTOFFE:
            raise EingabeFehler("Bitte einen Baustahl wählen.")
        if self.t_mm * 2 >= self.d_mm:
            raise EingabeFehler("Die Wanddicke ist zu groß für den Durchmesser.")
        if self.d_l_mm <= self.d_mm * 0.5:
            raise EingabeFehler("Der Lochkreis muss größer als der halbe Rohrdurchmesser sein.")


def berechne(e: TurmEingaben) -> Ergebnis:
    e.pruefen()
    w_ = werkstoffe.nach_bezeichnung(e.werkstoff)
    fy = float(w_["re"])
    H = e.h_m
    D, t = e.d_mm, e.t_mm
    d_i = D - 2 * t
    A = math.pi / 4 * (D**2 - d_i**2)                  # mm²
    I = math.pi / 64 * (D**4 - d_i**4)                 # mm⁴
    W = I / (D / 2)                                     # mm³
    m_turm = RHO_STAHL * A * 1e-6 * H                   # kg
    # Wind auf den Turm
    w = 0.5 * e.luftdichte * e.v_e50**2 * e.c_f * D / 1000      # N/m
    F_T = w * H
    M_T = w * H**2 / 2
    M_k = e.f_x_k * H + M_T                             # N·m
    M_d = e.gamma_f * M_k
    N_k = (e.m_kopf + m_turm) * 9.81
    N_d = e.gamma_f * N_k
    sigma = M_d * 1000 / W + N_d / A
    eta = sigma / (fy / GAMMA_M0)
    eps2 = 235 / fy
    klasse_ok = D / t <= 90 * eps2
    # Verformung und Eigenfrequenz
    EI = E_STAHL * 1e6 * I * 1e-12                      # N·m²
    f_kopf = (e.f_x_k * H**3 / (3 * EI) + w * H**4 / (8 * EI)) * 1000   # mm
    f0 = 1 / (2 * math.pi) * math.sqrt(3 * EI / ((e.m_kopf + 0.24 * m_turm) * H**3))
    f1p = e.n_rpm / 60
    fbp = f1p * int(round(e.blattzahl))
    abstand_1p = abs(f0 - f1p) / f1p
    abstand_bp = abs(f0 - fbp) / fbp
    # Flansch
    n_s = int(round(e.n_s))
    F_A = 4 * M_d * 1000 / (n_s * e.d_l_mm)             # N
    # Fundament
    G_F = GAMMA_BETON * e.a_m**2 * e.hf_m * 1000         # N
    N_F = N_k + G_F
    M_F = M_k + (e.f_x_k + F_T) * e.hf_m
    ex = M_F / N_F
    a = e.a_m
    if ex <= a / 6:
        s_max = N_F / a**2 * (1 + 6 * ex / a) / 1000     # kPa
    elif ex < a / 2:
        s_max = 2 * N_F / (3 * a * (a / 2 - ex)) / 1000
    else:
        s_max = float("inf")
    kipp = N_F * a / 2 / M_F if M_F else float("inf")
    beton = a**2 * e.hf_m

    eingaben = [
        Groesse("H", "Turmhöhe", H, "m"), Groesse("D", "Rohraußendurchmesser", D, "mm"), Groesse("t", "Wanddicke", t, "mm"),
        Groesse("f_y", f"Streckgrenze {w_['name']}", fy, "MPa"), Groesse("F_x,k", "Rotorschub charakteristisch", e.f_x_k, "N"),
        Groesse("γ_f", "Teilsicherheitsbeiwert Last", e.gamma_f, "–"), Groesse("V_e50", "Extremwind", e.v_e50, "m/s"),
        Groesse("c_f", "Kraftbeiwert Rohr (Richtwert)", e.c_f, "–"), Groesse("m_Kopf", "Kopfmasse (Annahme)", e.m_kopf, "kg"),
        Groesse("n", "Rotordrehzahl", e.n_rpm, "1/min"), Groesse("n_S", "Anzahl Flanschschrauben", n_s, "–"),
        Groesse("D_L", "Lochkreis", e.d_l_mm, "mm"), Groesse("a", "Fundament Kantenlänge", a, "m"),
        Groesse("h_F", "Fundament Höhe", e.hf_m, "m"), Groesse("σ_zul", "Zul. Bodenpressung", e.sigma_zul, "kPa"),
    ]
    S = Schritt
    schritte = [
        S("Querschnittswerte Rohr", "A = π/4·(D² − d²);  I = π/64·(D⁴ − d⁴);  W = I/(D/2)",
          f"d = {f(d_i)} mm;  A = {f(A)} mm²;  I = {f(I)} mm⁴", Groesse("W", "Widerstandsmoment", W, "mm³")),
        S("Windlast auf den Turm", "w = ½·ρ·V_e50²·c_f·D;  M_T = w·H²/2",
          f"w = ½·{f(e.luftdichte)}·{f(e.v_e50)}²·{f(e.c_f)}·{f(D / 1000)} m = {f(w)} N/m", Groesse("M_T", "Moment aus Turmwind", M_T, "N·m")),
        S("Kippmoment am Turmfuß", "M_k = F_x,k·H + M_T;  M_d = γ_f·M_k",
          f"M_k = {f(e.f_x_k)}·{f(H)} + {f(M_T)} = {f(M_k)} N·m;  M_d = {f(e.gamma_f)}·{f(M_k)}", Groesse("M_d", "Bemessungs-Kippmoment", M_d, "N·m")),
        S("Spannung am Turmfuß", "σ_d = M_d/W + γ_f·N/A", f"σ_d = {f(M_d)}·10³/{f(W)} + {f(N_d)}/{f(A)}",
          Groesse("σ_d", "Bemessungsspannung", sigma, "MPa")),
        S("Ausnutzung", "η = σ_d/(f_y/γ_M0)", f"η = {f(sigma)}/({f(fy)}/1,0)", Groesse("η_σ", "Ausnutzung Turmfuß", eta, "–")),
        S("Kopfauslenkung (charakteristisch)", "f = F_x,k·H³/(3EI) + w·H⁴/(8EI)", f"EI = {f(EI)} N·m²",
          Groesse("f", "Kopfauslenkung", f_kopf, "mm")),
        S("Erste Eigenfrequenz", "f0 = 1/(2π)·√(3EI/((m_Kopf + 0,24·m_Turm)·H³))",
          f"m_Turm = {f(m_turm)} kg;  f0 = 1/(2π)·√(3·{f(EI)}/(({f(e.m_kopf)} + 0,24·{f(m_turm)})·{f(H)}³))",
          Groesse("f0", "Erste Eigenfrequenz Turm", f0, "Hz")),
        S("Anregung durch den Rotor", "1P = n/60;  3P = B·n/60", f"1P = {f(f1p)} Hz;  {int(round(e.blattzahl))}P = {f(fbp)} Hz",
          Groesse("1P", "Drehfrequenz", f1p, "Hz")),
        S("Zugkraft je Flanschschraube (Bemessung)", "F_A = 4·M_d/(n·D_L)", f"F_A = 4·{f(M_d)}·10³/({n_s}·{f(e.d_l_mm)})",
          Groesse("F_A,Schraube", "Zugkraft je Flanschschraube", F_A, "N")),
        S("Fundament: Gewicht und Moment in der Sohle", "G_F = 25 kN/m³·a²·h;  M_F = M_k + (F_x,k + F_T)·h",
          f"G_F = 25·{f(a)}²·{f(e.hf_m)} kN;  M_F = {f(M_k)} + ({f(e.f_x_k)} + {f(F_T)})·{f(e.hf_m)}", Groesse("M_F", "Moment in der Sohle", M_F, "N·m")),
        S("Lage der Resultierenden", "e = M_F/N;  N = G_F + (m_Kopf + m_Turm)·g", f"e = {f(M_F)}/{f(N_F)}",
          Groesse("e", "Ausmitte", ex, "m")),
        S("Größte Bodenpressung", "e ≤ a/6: σ = N/a²·(1 + 6e/a);  sonst σ = 2N/(3a·(a/2 − e))", f"a/6 = {f(a / 6)} m",
          Groesse("σ_Boden", "Größte Bodenpressung", s_max, "kPa")),
        S("Kippsicherheit (charakteristisch)  [Richtwert]", "η_K = N·a/2 / M_F", f"η_K = {f(N_F)}·{f(a / 2)}/{f(M_F)}",
          Groesse("η_K", "Kippsicherheit", kipp, "–")),
    ]
    ergebnisse = [
        Groesse("η_σ", "Ausnutzung Turmfuß (≤ 1)", eta, "–"),
        Groesse("M_d", "Bemessungs-Kippmoment Turmfuß", M_d, "N·m"),
        Groesse("M_k", "Kippmoment charakteristisch", M_k, "N·m"),
        Groesse("σ_d", "Bemessungsspannung Turmfuß", sigma, "MPa"),
        Groesse("f", "Kopfauslenkung", f_kopf, "mm"),
        Groesse("f0", "Erste Eigenfrequenz Turm", f0, "Hz"),
        Groesse("F_A,Schraube", "Zugkraft je Flanschschraube (Bemessung)", F_A, "N"),
        Groesse("n_S", "Anzahl Flanschschrauben", n_s, "–"),
        Groesse("σ_Boden", "Größte Bodenpressung", s_max, "kPa"),
        Groesse("η_K", "Kippsicherheit Fundament", kipp, "–"),
        Groesse("e", "Ausmitte der Resultierenden", ex, "m"),
        Groesse("V_Beton", "Betonvolumen", beton, "m³"),
        Groesse("m_Turm", "Turmmasse", m_turm, "kg"),
        Groesse("N_d", "Normalkraft Bemessung", N_d, "N"),
        Groesse("Q_d", "Querkraft Turmfuß Bemessung", e.gamma_f * (e.f_x_k + F_T), "N"),
    ]
    pruefungen = [
        Pruefung("Spannung Turmfuß", f"η = {f(eta, 3)} ≤ 1", eta <= 1, "" if eta <= 1 else "Durchmesser oder Wanddicke vergrößern."),
        Pruefung("Querschnittsklasse ≤ 3 (kein örtliches Beulen)", f"D/t = {f(D / t, 3)} ≤ 90·ε² = {f(90 * eps2, 3)}", klasse_ok),
        Pruefung("Eigenfrequenz nicht bei 1P", f"|f0 − 1P|/1P = {f(abstand_1p * 100, 3)} % ≥ 10 %", abstand_1p >= 0.10,
                 "" if abstand_1p >= 0.10 else "Resonanzgefahr: Turm steifer oder weicher auslegen."),
        Pruefung(f"Eigenfrequenz nicht bei {int(round(e.blattzahl))}P", f"|f0 − {int(round(e.blattzahl))}P|/{int(round(e.blattzahl))}P = {f(abstand_bp * 100, 3)} % ≥ 10 %",
                 abstand_bp >= 0.10, "" if abstand_bp >= 0.10 else "Resonanzgefahr mit der Blattfrequenz."),
        Pruefung("Klaffende Fuge höchstens bis zum Schwerpunkt", f"e = {f(ex, 3)} m ≤ a/3 = {f(a / 3, 3)} m", ex <= a / 3,
                 "" if ex <= a / 3 else "Fundament breiter oder schwerer."),
        Pruefung("Bodenpressung", f"σ = {f(s_max)} kPa ≤ {f(e.sigma_zul)} kPa", s_max <= e.sigma_zul),
        Pruefung("Kippsicherheit (Richtwert)", f"η_K = {f(kipp, 3)} ≥ 1,5", kipp >= 1.5),
    ]
    hinweise = [
        "Die Eigenfrequenz gilt bei Nenndrehzahl. Eine drehzahlvariable Anlage durchfährt einen Drehzahlbereich: "
        "f0 sollte außerhalb des ganzen Bereichs von 1P und 3P liegen (Campbell-Diagramm).",
        "Flanschschrauben: Zugkraft aus dem Bemessungsmoment (γ_f enthalten), Hebelkräfte (Prying) nicht berücksichtigt. "
        "Weiter in der Berechnung „Schrauben“.",
        "Fundament: Nachweise mit charakteristischen Lasten; Bewehrung und Bodengutachten sind nicht Teil der Rechnung. "
        "Für den Bau ist eine Baugenehmigung mit Standsicherheitsnachweis durch einen Tragwerksplaner nötig.",
    ]
    unbelegt = [
        "Kraftbeiwert c_f = 0,7 und Kippsicherheit 1,5 sind Richtwerte aus dem Gedächtnis.",
        "Teilsicherheitsbeiwert γ_f auch auf das Eigengewicht angesetzt (konservativ, nicht normgerecht kombiniert).",
    ]
    return Ergebnis(TITEL, TYP, eingaben, schritte, ergebnisse, pruefungen, QUELLEN, hinweise, unbelegt=unbelegt)
