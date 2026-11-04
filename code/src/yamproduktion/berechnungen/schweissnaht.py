"""Kehlnaht Rohr an Platte, ringsum (z. B. Turmfuß an Flansch), richtungsbezogenes Verfahren DIN EN 1993-1-8, 4.5.3.2.

  Nahtquerschnitt: Ring mit Innendurchmesser D und Dicke a (Nahtdicke in die Anschlussfläche geklappt)
  σ_w = M/W_w + N/A_w   (senkrecht zur Anschlussfläche)
  Kehlnaht 45°:  σ_⊥ = τ_⊥ = σ_w/√2
  τ_∥ = 2·Q/A_w + T/W_t
  Nachweis:  √(σ_⊥² + 3·(τ_⊥² + τ_∥²)) ≤ f_u/(β_w·γ_M2)   und   σ_⊥ ≤ 0,9·f_u/γ_M2
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .. import werkstoffe
from .basis import Ergebnis, Feld, Groesse, Pruefung, Schritt, formatiere as f

TYP = "schweissnaht"
TITEL = "Schweißnaht (Kehlnaht Rohr an Platte)"
KURZ = "Schweißnaht"
BESCHREIBUNG = ("Ringsum laufende Kehlnaht, z. B. Turmrohr an Fußflansch: Spannungen aus Biegung, Normalkraft, "
                "Querkraft und Torsion, Nachweis nach dem richtungsbezogenen Verfahren des Eurocode 3.")
HAUPT = "η_w"
WERKSTOFFE = werkstoffe.auswahl(("Baustahl",))
GAMMA_M2 = 1.25
BETA_W = {"S235": 0.80, "S355": 0.90}

QUELLEN = [
    "DIN EN 1993-1-8, 4.5.3.2 (richtungsbezogenes Verfahren): √(σ⊥² + 3(τ⊥² + τ∥²)) ≤ f_u/(β_w·γ_M2) und σ⊥ ≤ 0,9·f_u/γ_M2",
    "DIN EN 1993-1-8, Tabelle 4.1: Korrelationsbeiwert β_w = 0,80 (S235), 0,90 (S355); Tabelle 2.1: γ_M2 = 1,25",
    "DIN EN 1993-1-8, 4.5.2: wirksame Nahtdicke a ≥ 3 mm",
]

FELDER = [
    Feld("d_mm", "Rohraußendurchmesser D", "mm", 20, 3000, 1, 1, "aus der Turmberechnung"),
    Feld("a_mm", "Nahtdicke a", "mm", 3, 30, 0.5, 1, "a ≥ 3 mm; meist a ≈ 0,7·t"),
    Feld("werkstoff", "Grundwerkstoff", "", auswahl=WERKSTOFFE),
    Feld("m_nm", "Biegemoment (Bemessung)", "N*m", 0, 1e8, 100, 1, ""),
    Feld("n_n", "Normalkraft (Bemessung, Druck positiv)", "N", -1e7, 1e7, 100, 1, "Druck entlastet die Naht"),
    Feld("q_n", "Querkraft (Bemessung)", "N", 0, 1e7, 100, 1, ""),
    Feld("t_nm", "Torsionsmoment (Bemessung)", "N*m", 0, 1e8, 100, 1, "z. B. Giermoment"),
]
FELD_EINHEITEN = {x.attr: x.einheit for x in FELDER if not x.auswahl}
FELD_NAMEN = {x.attr: x.name for x in FELDER}
FELD_SUCHBEGRIFFE: dict = {}
BERECHNUNGS_QUELLEN = {
    "d_mm": ("turm", "D"),
    "m_nm": ("turm", "M_d"),
    "n_n": ("turm", "N_d"),
    "q_n": ("turm", "Q_d"),
}


class EingabeFehler(ValueError):
    pass


@dataclass
class NahtEingaben:
    d_mm: float = 406.4
    a_mm: float = 7.0
    werkstoff: str = werkstoffe.bezeichnung(werkstoffe.werkstoff("S355J2"))
    m_nm: float = 130000.0
    n_n: float = 25000.0
    q_n: float = 11000.0
    t_nm: float = 0.0

    def pruefen(self) -> None:
        if self.werkstoff not in WERKSTOFFE:
            raise EingabeFehler("Bitte einen Baustahl wählen.")
        if self.a_mm <= 0 or self.d_mm <= 0:
            raise EingabeFehler("Durchmesser und Nahtdicke müssen positiv sein.")


def beta_w(name: str) -> float:
    for k, v in BETA_W.items():
        if name.startswith(k):
            return v
    raise EingabeFehler(f"Für {name} ist kein Korrelationsbeiwert β_w hinterlegt.")


def berechne(e: NahtEingaben) -> Ergebnis:
    e.pruefen()
    w_ = werkstoffe.nach_bezeichnung(e.werkstoff)
    fu = float(w_["rm"])
    bw = beta_w(w_["name"])
    D, a = e.d_mm, e.a_mm
    Da = D + 2 * a
    A_w = math.pi / 4 * (Da**2 - D**2)
    I_w = math.pi / 64 * (Da**4 - D**4)
    W_w = I_w / (Da / 2)
    W_t = 2 * W_w
    sigma_w = e.m_nm * 1000 / W_w - e.n_n / A_w          # Zug aus Biegung, Druck entlastet
    sigma_w = max(sigma_w, 0.0)
    s_perp = t_perp = sigma_w / math.sqrt(2)
    t_par = 2 * e.q_n / A_w + e.t_nm * 1000 / W_t
    sigma_v = math.sqrt(s_perp**2 + 3 * (t_perp**2 + t_par**2))
    grenze = fu / (bw * GAMMA_M2)
    grenze2 = 0.9 * fu / GAMMA_M2
    eta = max(sigma_v / grenze, s_perp / grenze2)

    eingaben = [
        Groesse("D", "Rohraußendurchmesser", D, "mm"), Groesse("a", "Nahtdicke", a, "mm"),
        Groesse("f_u", f"Zugfestigkeit {w_['name']}", fu, "MPa"), Groesse("β_w", "Korrelationsbeiwert", bw, "–"),
        Groesse("γ_M2", "Teilsicherheitsbeiwert Naht", GAMMA_M2, "–"),
        Groesse("M", "Biegemoment", e.m_nm, "N·m"), Groesse("N", "Normalkraft (Druck +)", e.n_n, "N"),
        Groesse("Q", "Querkraft", e.q_n, "N"), Groesse("T", "Torsionsmoment", e.t_nm, "N·m"),
    ]
    S = Schritt
    schritte = [
        S("Nahtquerschnitt (Ring)", "A_w = π/4·((D+2a)² − D²);  W_w = π/64·((D+2a)⁴ − D⁴)/((D+2a)/2)",
          f"A_w = {f(A_w)} mm²", Groesse("W_w", "Widerstandsmoment Naht", W_w, "mm³")),
        S("Spannung senkrecht zur Anschlussfläche", "σ_w = M/W_w − N/A_w",
          f"σ_w = {f(e.m_nm)}·10³/{f(W_w)} − {f(e.n_n)}/{f(A_w)}", Groesse("σ_w", "Nahtspannung", sigma_w, "MPa")),
        S("Aufteilung auf die 45°-Kehlnahtfläche", "σ_⊥ = τ_⊥ = σ_w/√2", f"σ_⊥ = {f(sigma_w)}/√2",
          Groesse("σ_⊥", "Normalspannung auf Nahtfläche", s_perp, "MPa")),
        S("Schubspannung längs der Naht", "τ_∥ = 2·Q/A_w + T/(2·W_w)",
          f"τ_∥ = 2·{f(e.q_n)}/{f(A_w)} + {f(e.t_nm)}·10³/{f(W_t)}", Groesse("τ_∥", "Schub längs", t_par, "MPa")),
        S("Vergleichsspannung", "σ_v = √(σ_⊥² + 3·(τ_⊥² + τ_∥²))", f"σ_v = √({f(s_perp)}² + 3·({f(t_perp)}² + {f(t_par)}²))",
          Groesse("σ_v", "Vergleichsspannung Naht", sigma_v, "MPa")),
        S("Grenzwert", "f_u/(β_w·γ_M2)", f"{f(fu)}/({f(bw)}·{f(GAMMA_M2)})", Groesse("σ_w,Rd", "Grenzspannung", grenze, "MPa")),
    ]
    ergebnisse = [
        Groesse("η_w", "Ausnutzung Naht (≤ 1)", eta, "–"),
        Groesse("σ_v", "Vergleichsspannung Naht", sigma_v, "MPa"),
        Groesse("σ_w,Rd", "Grenzspannung", grenze, "MPa"),
        Groesse("σ_⊥", "Normalspannung auf Nahtfläche", s_perp, "MPa"),
        Groesse("τ_∥", "Schub längs der Naht", t_par, "MPa"),
        Groesse("A_w", "Nahtfläche", A_w, "mm²"),
    ]
    pruefungen = [
        Pruefung("Vergleichsspannung", f"σ_v = {f(sigma_v)} ≤ {f(grenze)} MPa", sigma_v <= grenze),
        Pruefung("Normalspannung", f"σ_⊥ = {f(s_perp)} ≤ 0,9·f_u/γ_M2 = {f(grenze2)} MPa", s_perp <= grenze2),
        Pruefung("Mindestnahtdicke", f"a = {f(a)} ≥ 3 mm", a >= 3),
    ]
    hinweise = [
        "Statischer Nachweis. Eine Windenergieanlage belastet die Naht wechselnd: der Ermüdungsnachweis "
        "(DIN EN 1993-1-9, Kerbfall) ist zusätzlich nötig und folgt mit den Lastkollektiven.",
        "Vereinfachung: Naht als Ring außen am Rohr. Bei beidseitiger Naht oder durchgeschweißter Naht anders rechnen.",
    ]
    return Ergebnis(TITEL, TYP, eingaben, schritte, ergebnisse, pruefungen, QUELLEN, hinweise,
                    unbelegt=["Ermüdungsnachweis fehlt noch (Kerbfall nach DIN EN 1993-1-9)."])
