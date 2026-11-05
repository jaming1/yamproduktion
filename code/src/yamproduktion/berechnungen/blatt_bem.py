"""Rotorblatt-Auslegung nach der Blattelementmethode (Lastenheft K3).

Das Blatt wird in N gleich breite Ringe (Blattelemente) zwischen Nabe und Spitze geteilt.

Rechenweg:
  1. Winkelgeschwindigkeit           ω = λ·v / R;   örtliche Schnelllaufzahl λ_r = λ·r / R
  2. Optimaler Anströmwinkel         φ_opt = ⅔ · arctan(1 / λ_r)                      (Schmitz)
  3. Blatttiefe (Sehne)              c = 16·π·r / (B·cA) · sin²(φ_opt / 2)          (Schmitz)
  4. Verwindung                      θ = φ_opt − α_A
  5. Nachrechnung je Element (BEM)   φ = arctan((1−a)·v / ((1+a')·ω·r)),  α = φ − θ,
                                     cn = cA·cos φ + cW·sin φ,  ct = cA·sin φ − cW·cos φ,
                                     F  = 2/π · arccos(exp(−B·(R−r) / (2·r·sin φ)))   (Prandtl)
                                     a  = 1 / (4·F·sin²φ / (σ·cn) + 1)   (über a = 0,4: Korrektur nach Buhl)
                                     a' = 1 / (4·F·sin φ·cos φ / (σ·ct) − 1),   σ = B·c / (2·π·r)
  6. Kräfte je Element               dT = ½·ρ·B·c·w²·cn·dr,   dM = ½·ρ·B·c·w²·ct·r·dr
  7. Leistung und Beiwerte           P = ω·ΣdM,  cp = P / (½·ρ·π·R²·v³),  cT = ΣdT / (½·ρ·π·R²·v²)

Die Profilwerte (cA, α_A, Gleitzahl, cA,max) hängen vom gewählten Profil und der Reynoldszahl ab und
sind deshalb als unbelegt markiert, bis sie mit einem Profilkatalog geprüft sind.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .basis import Ergebnis, Feld, Groesse, Pruefung, Schritt, formatiere as f

TYP = "rotorblatt_bem"
TITEL = "Rotorblatt-Auslegung nach Blattelementmethode"
KURZ = "Rotorblatt (BEM)"
BESCHREIBUNG = ("Form des Rotorblatts bestimmen: Blatttiefe und Verwindung an jeder Stelle des Blatts (Auslegung "
                "nach Schmitz) und anschließend nachrechnen, welche Leistung das Blatt wirklich liefert "
                "(Blattelementmethode mit Spitzenverlust und Profilwiderstand).")
HAUPT = "cp"

BETZ_GRENZE = 16 / 27
NU_LUFT = 1.4607e-5              # kinematische Zähigkeit der Luft in m²/s, Normatmosphäre ISO 2533 (15 °C, Meereshöhe)
MIT_VERLUST = "mit Spitzenverlust (Prandtl)"
OHNE_VERLUST = "ohne Spitzenverlust"

FELDER = [
    Feld("durchmesser_m", "Rotordurchmesser", "m", 0.5, 30, 0.1, 2, "aus der Rotorauslegung"),
    Feld("blattzahl", "Anzahl der Blätter", "", 1, 6, 1, 0, "Kleinwindanlagen meist 3"),
    Feld("schnelllaufzahl", "Auslegungs-Schnelllaufzahl λ", "", 1, 12, 0.5, 1,
         "Blattspitzengeschwindigkeit / Windgeschwindigkeit, aus der Rotorauslegung"),
    Feld("wind_ms", "Auslegungswindgeschwindigkeit", "m/s", 1, 30, 0.5, 1, "meist der Nennwind"),
    Feld("luftdichte", "Luftdichte", "kg/m^3", 0.5, 1.5, 0.005, 3, "1,225 auf Meereshöhe bei 15 °C"),
    Feld("nabe_anteil", "Nabenradius / Rotorradius", "", 0.02, 0.5, 0.01, 2,
         "Ab hier beginnt das tragende Blatt (typisch 0,10–0,20)"),
    Feld("elemente", "Anzahl Blattelemente", "", 5, 60, 1, 0, "Mehr Elemente = feinere Rechnung (15–30 genügen)"),
    Feld("ca_auslegung", "Auftriebsbeiwert im Auslegungspunkt cA", "", 0.2, 2.0, 0.05, 2,
         "Aus der Profilpolare beim besten Gleitverhältnis – UNBELEGT, mit Profilkatalog prüfen"),
    Feld("alpha_auslegung", "Anstellwinkel im Auslegungspunkt α_A", "deg", -5, 20, 0.5, 1,
         "Gehört zu cA aus der Profilpolare – UNBELEGT"),
    Feld("gleitzahl", "Gleitzahl E = cA / cW", "", 5, 200, 5, 0,
         "Kleinwindanlagen mit kleiner Reynoldszahl eher 40–80 – UNBELEGT"),
    Feld("ca_max", "Höchster Auftriebsbeiwert cA,max", "", 0.3, 2.5, 0.05, 2,
         "Darüber reißt die Strömung ab – UNBELEGT"),
    Feld("cp_ziel", "Geforderter Leistungsbeiwert cp", "", 0.05, 0.59, 0.01, 2,
         "Wert, mit dem die Rotorauslegung gerechnet hat"),
    Feld("spitzenverlust", "Verluste an der Blattspitze", "", auswahl=(MIT_VERLUST, OHNE_VERLUST),
         tipp="Mit Spitzenverlust ist die Rechnung näher an der Wirklichkeit"),
]

FELD_EINHEITEN = {x.attr: x.einheit for x in FELDER}
FELD_NAMEN = {x.attr: x.name for x in FELDER}
FELD_SUCHBEGRIFFE = {"wind_ms": "nennwind", "blattzahl": "blattzahl"}
# Feld ← (Berechnungsart, Symbol) aus einer gespeicherten Rotorauslegung
BERECHNUNGS_QUELLEN = {
    "durchmesser_m": ("rotorauslegung", "D"),
    "schnelllaufzahl": ("rotorauslegung", "λ"),
    "wind_ms": ("rotorauslegung", "v"),
    "luftdichte": ("rotorauslegung", "ρ"),
    "cp_ziel": ("rotorauslegung", "cp"),
}

QUELLEN = [
    "F. W. Schmitz: Aerodynamik des Flugmodells, 1942 – optimale Blattform mit Drall; dargestellt in "
    "R. Gasch, J. Twele: Windkraftanlagen (Kap. Auslegung von Rotorblättern nach Betz und Schmitz)",
    "M. O. L. Hansen: Aerodynamics of Wind Turbines, 2. Aufl., Earthscan 2008, Kap. 6: "
    "BEM-Algorithmus mit Prandtl-Spitzenverlust",
    "S. A. Ning: A simple solution method for the blade element momentum equations with guaranteed "
    "convergence, Wind Energy 17 (2014) – Lösung nach dem Anströmwinkel φ",
    "M. L. Buhl: A New Empirical Relationship between Thrust Coefficient and Induction Factor for the "
    "Turbulent Windmill State, NREL/TP-500-36834, 2005 – Korrektur für a > 0,4",
    "H. Glauert: Airplane Propellers, in W. F. Durand (Hrsg.): Aerodynamic Theory, Bd. IV, 1935 – Blattelementtheorie",
    "Auftriebsanstieg 2π je rad (Theorie dünner Profile): J. D. Anderson: Fundamentals of Aerodynamics, Kap. 4",
    "Kinematische Zähigkeit der Luft ν = 1,4607·10⁻⁵ m²/s: Normatmosphäre ISO 2533 (Meereshöhe, 15 °C)",
]

UNBELEGT = [
    "Profilwerte cA, α_A, Gleitzahl und cA,max: Beispielwerte, keinem geprüften Profilkatalog entnommen. "
    "Für das gewählte Profil bei der angezeigten Reynoldszahl aus der Profilpolare ablesen "
    "(z. B. Abbott/von Doenhoff, Theory of Wing Sections, oder Windkanalmessungen bei kleiner Reynoldszahl).",
    "Vereinfachte Polare: cA steigt linear mit 2π je rad um den Auslegungspunkt und bleibt über cA,max konstant; "
    "cW = cA/E ist konstant. Außerhalb des Auslegungspunkts (andere λ) nur als Abschätzung verwenden.",
]


class EingabeFehler(ValueError):
    """Ungültige Eingabe mit verständlicher Erklärung."""


@dataclass
class Eingaben:
    durchmesser_m: float = 4.8
    blattzahl: float = 3
    schnelllaufzahl: float = 6.0
    wind_ms: float = 11.0
    luftdichte: float = 1.225
    nabe_anteil: float = 0.15
    elemente: float = 20
    ca_auslegung: float = 1.0
    alpha_auslegung: float = 5.0
    gleitzahl: float = 60.0
    ca_max: float = 1.4
    cp_ziel: float = 0.40
    spitzenverlust: str = MIT_VERLUST

    def pruefen(self) -> None:
        if self.durchmesser_m <= 0:
            raise EingabeFehler("Der Rotordurchmesser muss größer als 0 m sein.")
        if self.blattzahl < 1 or self.blattzahl != int(self.blattzahl):
            raise EingabeFehler("Die Anzahl der Blätter muss eine ganze Zahl ab 1 sein.")
        if not 0.5 <= self.schnelllaufzahl <= 15:
            raise EingabeFehler("Die Schnelllaufzahl liegt üblicherweise zwischen 1 und 10 (Dreiblatt: 6–8).")
        if self.wind_ms <= 0:
            raise EingabeFehler("Die Windgeschwindigkeit muss größer als 0 m/s sein.")
        if not 0.5 <= self.luftdichte <= 1.5:
            raise EingabeFehler("Die Luftdichte liegt üblicherweise zwischen 0,9 und 1,3 kg/m³.")
        if not 0 < self.nabe_anteil < 0.9:
            raise EingabeFehler("Der Nabenradius muss kleiner als der Rotorradius sein (Anteil zwischen 0 und 0,9).")
        if self.elemente < 3 or self.elemente != int(self.elemente):
            raise EingabeFehler("Bitte mindestens 3 Blattelemente (ganze Zahl) wählen.")
        if self.ca_auslegung <= 0:
            raise EingabeFehler("Der Auftriebsbeiwert im Auslegungspunkt muss größer als 0 sein.")
        if self.gleitzahl <= 0:
            raise EingabeFehler("Die Gleitzahl muss größer als 0 sein (typisch 40 bis 120).")
        if self.ca_max < self.ca_auslegung:
            raise EingabeFehler("cA,max muss mindestens so groß sein wie der Auftriebsbeiwert im Auslegungspunkt.")
        if self.spitzenverlust not in (MIT_VERLUST, OHNE_VERLUST):
            raise EingabeFehler("Bitte wählen, ob mit oder ohne Spitzenverlust gerechnet wird.")


# ---------------------------------------------------------------- Auslegung (Schmitz)
def schmitz_winkel(lambda_r: float) -> float:
    """Optimaler Anströmwinkel φ in rad nach Schmitz."""
    return 2 / 3 * math.atan(1 / lambda_r)


def schmitz_sehne(r: float, lambda_r: float, blattzahl: int, ca: float) -> float:
    """Blatttiefe c in m nach Schmitz: c = 16·π·r / (B·cA) · sin²(φ_opt/2)."""
    return 16 * math.pi * r / (blattzahl * ca) * math.sin(schmitz_winkel(lambda_r) / 2) ** 2


@dataclass
class Element:
    r: float               # Radius der Elementmitte in m
    dr: float              # Breite in m
    sehne: float           # m
    verwindung: float      # θ in rad (Winkel zwischen Profilsehne und Drehebene)
    phi: float = 0.0
    alpha: float = 0.0
    a: float = 0.0
    a_s: float = 0.0       # tangentialer Induktionsfaktor a'
    f: float = 1.0
    ca: float = 0.0
    cw: float = 0.0
    w: float = 0.0         # Anströmgeschwindigkeit am Profil in m/s
    dT: float = 0.0
    dM: float = 0.0
    konvergiert: bool = False
    abgerissen: bool = False
    korrigiert: bool = False   # Buhl-Korrektur aktiv (a > 0,4)


def blatt_auslegen(e: Eingaben) -> list[Element]:
    """Schmitz-Blatt: Sehne und Verwindung in der Mitte jedes Elements."""
    radius = e.durchmesser_m / 2
    r_nabe = e.nabe_anteil * radius
    n = int(e.elemente)
    dr = (radius - r_nabe) / n
    elemente = []
    for i in range(n):
        r = r_nabe + (i + 0.5) * dr
        lam_r = e.schnelllaufzahl * r / radius
        phi = schmitz_winkel(lam_r)
        elemente.append(Element(r, dr, schmitz_sehne(r, lam_r, int(e.blattzahl), e.ca_auslegung),
                                phi - math.radians(e.alpha_auslegung)))
    return elemente


# ---------------------------------------------------------------- Nachrechnung (BEM)
def polare(alpha: float, e: Eingaben) -> tuple[float, float, bool]:
    """Vereinfachte Profilpolare: (cA, cW, abgerissen) beim Anstellwinkel alpha in rad."""
    ca = e.ca_auslegung + 2 * math.pi * (alpha - math.radians(e.alpha_auslegung))
    abgerissen = ca > e.ca_max
    ca = min(ca, e.ca_max)
    return ca, e.ca_auslegung / e.gleitzahl, abgerissen


def _induktion(phi: float, el: Element, e: Eingaben, lambda_r: float, mit_verlust: bool) -> tuple:
    """a, a', F, cA, cW, abgerissen, Buhl-Korrektur und Residuum beim Anströmwinkel phi (Ning 2014)."""
    radius = e.durchmesser_m / 2
    b = int(e.blattzahl)
    sigma = b * el.sehne / (2 * math.pi * el.r)
    sin_p, cos_p = math.sin(phi), math.cos(phi)
    ca, cw, abgerissen = polare(phi - el.verwindung, e)
    cn = ca * cos_p + cw * sin_p
    ct = ca * sin_p - cw * cos_p
    fak = 1.0
    if mit_verlust:
        fak = 2 / math.pi * math.acos(min(1.0, math.exp(-b * (radius - el.r) / (2 * el.r * sin_p))))
        fak = max(fak, 1e-6)
    k = sigma * cn / (4 * fak * sin_p**2)
    korrigiert = k > 2 / 3          # entspricht a > 0,4 → empirische Korrektur nach Buhl
    if not korrigiert:
        a = k / (1 + k)
    else:
        g1 = 2 * fak * k - (10 / 9 - fak)
        g2 = max(0.0, 2 * fak * k - fak * (4 / 3 - fak))
        g3 = 2 * fak * k - (25 / 9 - 2 * fak)
        a = 1 - 1 / (2 * math.sqrt(g2)) if abs(g3) < 1e-6 else (g1 - math.sqrt(g2)) / g3
    kp = sigma * ct / (4 * fak * sin_p * cos_p)
    a_s = kp / (1 - kp) if abs(1 - kp) > 1e-12 else 1e6
    residuum = sin_p / (1 - a) - cos_p * (1 - kp) / lambda_r if abs(1 - a) > 1e-12 else 1e6
    return a, a_s, fak, ca, cw, abgerissen, korrigiert, residuum


def element_rechnen(el: Element, e: Eingaben, schnelllaufzahl: float, mit_verlust: bool) -> Element:
    """BEM-Gleichungen eines Elements lösen (Hansen, Kap. 6).

    Gelöst wird nach dem Anströmwinkel φ mit Intervallhalbierung (Ning 2014): Das Verfahren findet
    sicher eine Lösung, wenn es im Windturbinenbereich 0 < φ ≤ 90° eine gibt. Gibt es mehrere,
    gilt die dem Schmitz-Winkel nächste.
    """
    radius = e.durchmesser_m / 2
    v = e.wind_ms
    omega = schnelllaufzahl * v / radius
    lambda_r = omega * el.r / v
    def res(x: float) -> float:
        return _induktion(x, el, e, lambda_r, mit_verlust)[-1]

    # Vorzeichenwechsel auf einem Raster suchen; Polstellen (Sprung statt Nullstelle) werden verworfen.
    # Geprüft wird zuerst das Intervall, das dem Schmitz-Winkel am nächsten liegt.
    raster = [1e-4 + (math.pi / 2 - 1e-4) * k / 45 for k in range(46)]
    werte = [res(x) for x in raster]
    kandidaten = [(raster[k], raster[k + 1], werte[k]) for k in range(45) if werte[k] * werte[k + 1] <= 0]
    referenz = schmitz_winkel(lambda_r)
    kandidaten.sort(key=lambda kd: abs(0.5 * (kd[0] + kd[1]) - referenz))
    phi = referenz
    el.konvergiert = False
    for lo, hi, r_lo in kandidaten:
        for _ in range(60):
            mitte = 0.5 * (lo + hi)
            r_m = res(mitte)
            if (r_m < 0) == (r_lo < 0):
                lo, r_lo = mitte, r_m
            else:
                hi = mitte
        mitte = 0.5 * (lo + hi)
        if abs(res(mitte)) < 1e-6:
            phi = mitte
            el.konvergiert = True
            break
    a, a_s, fak, ca, cw, abgerissen, korrigiert, _ = _induktion(phi, el, e, lambda_r, mit_verlust)
    el.phi, el.alpha = phi, phi - el.verwindung
    el.a, el.a_s, el.f, el.ca, el.cw, el.abgerissen, el.korrigiert = a, a_s, fak, ca, cw, abgerissen, korrigiert
    el.w = math.hypot((1 - a) * v, (1 + a_s) * omega * el.r)
    cn = ca * math.cos(phi) + cw * math.sin(phi)
    ct = ca * math.sin(phi) - cw * math.cos(phi)
    q = 0.5 * e.luftdichte * el.w**2 * int(e.blattzahl) * el.sehne * el.dr
    el.dT = q * cn
    el.dM = q * ct * el.r
    return el


def nachrechnen(e: Eingaben, elemente: list[Element], schnelllaufzahl: float) -> dict:
    """Leistung, Schub und Beiwerte des Blatts bei der Schnelllaufzahl λ."""
    radius = e.durchmesser_m / 2
    mit_verlust = e.spitzenverlust == MIT_VERLUST
    gerechnet = [element_rechnen(Element(x.r, x.dr, x.sehne, x.verwindung), e, schnelllaufzahl, mit_verlust)
                 for x in elemente]
    omega = schnelllaufzahl * e.wind_ms / radius
    moment = sum(x.dM for x in gerechnet)
    schub = sum(x.dT for x in gerechnet)
    flaeche = math.pi * radius**2
    p = omega * moment
    return {
        "elemente": gerechnet,
        "omega": omega,
        "M": moment,
        "T": schub,
        "P": p,
        "cp": p / (0.5 * e.luftdichte * flaeche * e.wind_ms**3),
        "cT": schub / (0.5 * e.luftdichte * flaeche * e.wind_ms**2),
    }


def cp_kurve(e: Eingaben, elemente: list[Element]) -> tuple[list[float], list[float]]:
    """cp über der Schnelllaufzahl bei fester Blattform (Kennlinie)."""
    xs, ys = [], []
    lam = 1.0
    ende = max(2.0, 1.8 * e.schnelllaufzahl)
    while lam <= ende + 1e-9:
        xs.append(round(lam, 3))
        ys.append(max(0.0, nachrechnen(e, elemente, lam)["cp"]))
        lam += 0.5
    return xs, ys


def berechne(e: Eingaben) -> Ergebnis:
    e.pruefen()
    radius = e.durchmesser_m / 2
    b = int(e.blattzahl)
    lam, v, rho = e.schnelllaufzahl, e.wind_ms, e.luftdichte
    elemente = blatt_auslegen(e)
    res = nachrechnen(e, elemente, lam)
    gerechnet = res["elemente"]
    omega = res["omega"]
    n_min = omega * 60 / (2 * math.pi)

    # Beispielelement für den Rechenweg: nächstes an 0,7·R (üblicher Bezugsradius)
    k = min(range(len(gerechnet)), key=lambda i: abs(gerechnet[i].r - 0.7 * radius))
    bsp = gerechnet[k]
    lam_r = lam * bsp.r / radius
    phi_opt = schmitz_winkel(lam_r)
    re_07 = bsp.w * bsp.sehne / NU_LUFT

    innen, aussen = gerechnet[0], gerechnet[-1]
    verwindung_gesamt = math.degrees(innen.verwindung - aussen.verwindung)
    alle_konvergiert = all(x.konvergiert for x in gerechnet)
    abgerissen = [x for x in gerechnet if x.abgerissen]
    korrigiert = [x for x in gerechnet if x.korrigiert]
    sigma = b * bsp.sehne / (2 * math.pi * bsp.r)
    mit_verlust = e.spitzenverlust == MIT_VERLUST

    eingaben = [
        Groesse("D", "Rotordurchmesser", e.durchmesser_m, "m"),
        Groesse("B", "Anzahl der Blätter", b, "–"),
        Groesse("λ", "Auslegungs-Schnelllaufzahl", lam, "–"),
        Groesse("v", "Auslegungswindgeschwindigkeit", v, "m/s"),
        Groesse("ρ", "Luftdichte", rho, "kg/m³"),
        Groesse("r_N/R", "Nabenradius / Rotorradius", e.nabe_anteil, "–"),
        Groesse("N", "Anzahl Blattelemente", int(e.elemente), "–"),
        Groesse("cA", "Auftriebsbeiwert im Auslegungspunkt (unbelegt)", e.ca_auslegung, "–"),
        Groesse("α_A", "Anstellwinkel im Auslegungspunkt (unbelegt)", e.alpha_auslegung, "°"),
        Groesse("E", "Gleitzahl cA/cW (unbelegt)", e.gleitzahl, "–"),
        Groesse("cA,max", "Höchster Auftriebsbeiwert (unbelegt)", e.ca_max, "–"),
        Groesse("cp_ziel", "Geforderter Leistungsbeiwert", e.cp_ziel, "–"),
    ]

    schritte = [
        Schritt("Winkelgeschwindigkeit und örtliche Schnelllaufzahl (Element bei r ≈ 0,7·R)",
                "ω = λ·v / R;   λ_r = λ·r / R",
                f"ω = {f(lam)}·{f(v)} m/s / {f(radius)} m = {f(omega)} 1/s;   "
                f"λ_r = {f(lam)}·{f(bsp.r)} m / {f(radius)} m = {f(lam_r)}",
                Groesse("n", "Drehzahl", n_min, "1/min")),
        Schritt("Optimaler Anströmwinkel nach Schmitz",
                "φ_opt = ⅔ · arctan(1 / λ_r)",
                f"φ_opt = ⅔ · arctan(1 / {f(lam_r)})",
                Groesse("φ_opt", "Optimaler Anströmwinkel bei 0,7·R", math.degrees(phi_opt), "°")),
        Schritt("Blatttiefe nach Schmitz",
                "c = 16·π·r / (B·cA) · sin²(φ_opt / 2)",
                f"c = 16·π·{f(bsp.r)} m / ({b}·{f(e.ca_auslegung)}) · sin²({f(math.degrees(phi_opt))}° / 2)",
                Groesse("c_0,7", "Blatttiefe bei 0,7·R", bsp.sehne * 1000, "mm")),
        Schritt("Verwindung (Einstellwinkel der Profilsehne zur Drehebene)",
                "θ = φ_opt − α_A",
                f"θ = {f(math.degrees(phi_opt))}° − {f(e.alpha_auslegung)}°",
                Groesse("θ_0,7", "Verwindung bei 0,7·R", math.degrees(bsp.verwindung), "°")),
        Schritt("Nachrechnung: Induktionsfaktoren iterativ (Blattelementmethode)",
                "φ = arctan((1−a)·v / ((1+a')·ω·r));  α = φ − θ;  σ = B·c / (2·π·r);  "
                "F = 2/π·arccos(exp(−B·(R−r) / (2·r·sin φ)));  a = 1 / (4·F·sin²φ / (σ·cn) + 1);  "
                "a' = 1 / (4·F·sin φ·cos φ / (σ·ct) − 1)",
                f"bei r = {f(bsp.r)} m: σ = {f(sigma)};  gelöst nach φ (Intervallhalbierung):  a = {f(bsp.a)},  "
                f"a' = {f(bsp.a_s)},  F = {f(bsp.f)},  φ = {f(math.degrees(bsp.phi))}°,  "
                f"α = {f(math.degrees(bsp.alpha))}°,  cA = {f(bsp.ca)}",
                Groesse("a_0,7", "Axialer Induktionsfaktor bei 0,7·R", bsp.a, "–")),
        Schritt("Kräfte je Element und Summe über das Blatt",
                "dT = ½·ρ·B·c·w²·cn·dr;   dM = ½·ρ·B·c·w²·ct·r·dr;   M = Σ dM;   T = Σ dT",
                f"Σ über {len(gerechnet)} Elemente zu je dr = {f(bsp.dr * 1000)} mm  →  "
                f"M = {f(res['M'])} N·m,  T = {f(res['T'])} N",
                Groesse("M", "Rotordrehmoment", res["M"], "N·m")),
        Schritt("Leistung und Leistungsbeiwert",
                "P = ω·M;   cp = P / (½·ρ·π·R²·v³);   cT = T / (½·ρ·π·R²·v²)",
                f"P = {f(omega)} 1/s · {f(res['M'])} N·m = {f(res['P'])} W;   "
                f"cp = {f(res['P'])} W / (½·{f(rho)}·π·{f(radius)}²·{f(v)}³)",
                Groesse("cp", "Leistungsbeiwert nach BEM", res["cp"], "–")),
    ]

    ergebnisse = [
        Groesse("cp", "Leistungsbeiwert nach BEM", res["cp"], "–"),
        Groesse("P_mech", "Mechanische Rotorleistung", res["P"] / 1000, "kW"),
        Groesse("M", "Rotordrehmoment", res["M"], "N·m"),
        Groesse("T", "Rotorschub", res["T"], "N"),
        Groesse("cT", "Schubbeiwert", res["cT"], "–"),
        Groesse("n", "Drehzahl", n_min, "1/min"),
        Groesse("c_innen", "Blatttiefe am inneren Element", innen.sehne * 1000, "mm"),
        Groesse("c_aussen", "Blatttiefe am äußeren Element", aussen.sehne * 1000, "mm"),
        Groesse("θ_innen", "Verwindung am inneren Element", math.degrees(innen.verwindung), "°"),
        Groesse("θ_aussen", "Verwindung am äußeren Element", math.degrees(aussen.verwindung), "°"),
        Groesse("Δθ", "Verwindung über das Blatt", verwindung_gesamt, "°"),
        Groesse("Re_0,7", "Reynoldszahl bei 0,7·R", re_07, "–"),
    ]

    pruefungen = [
        Pruefung("Betz-Grenze", f"cp = {f(res['cp'])} ≤ 16/27 ≈ 0,593", res["cp"] <= BETZ_GRENZE,
                 "" if res["cp"] <= BETZ_GRENZE else "Physikalisch unmöglich – Eingaben prüfen."),
        Pruefung("Leistungsbeiwert der Rotorauslegung erreicht", f"cp = {f(res['cp'])} ≥ cp_ziel = {f(e.cp_ziel)}",
                 res["cp"] >= e.cp_ziel,
                 "" if res["cp"] >= e.cp_ziel else
                 "Das Blatt liefert weniger als angenommen: in der Rotorauslegung cp verringern (größerer Rotor) "
                 "oder ein Profil mit besserer Gleitzahl wählen."),
        Pruefung("Rechnung an allen Elementen aufgegangen", f"{sum(x.konvergiert for x in gerechnet)} von "
                 f"{len(gerechnet)} Elementen konvergiert", alle_konvergiert,
                 "" if alle_konvergiert else "Mehr Elemente oder andere Profilwerte versuchen."),
        Pruefung("Keine Strömungsablösung im Auslegungspunkt",
                 f"cA ≤ cA,max = {f(e.ca_max)} an allen Elementen", not abgerissen,
                 "" if not abgerissen else f"Abriss an {len(abgerissen)} Elementen (innen) – Verwindung prüfen."),
    ]

    zeilen = [[x.r, x.r / radius, x.sehne * 1000, math.degrees(x.verwindung), math.degrees(x.alpha), x.ca, x.a]
              for x in gerechnet]
    tabellen = [{
        "titel": "Blattform und Anströmung je Element (Mitte des Elements)",
        "spalten": ["Radius r [m]", "r/R", "Blatttiefe c [mm]", "Verwindung θ [°]", "Anstellwinkel α [°]",
                    "Auftrieb cA", "Induktion a"],
        "zeilen": zeilen,
    }]
    xs, ys = cp_kurve(e, elemente)
    diagramm = {"titel": "Leistungsbeiwert cp über der Schnelllaufzahl (Blattform fest)",
                "x_name": "Schnelllaufzahl λ", "y_name": "cp", "x": xs, "y": ys}

    hinweise = [
        "Auslegung nach Schmitz berücksichtigt den Drall der Nachlaufströmung, aber weder Profilwiderstand noch "
        "Spitzenverlust; beide sind in der Nachrechnung enthalten.",
        f"Reynoldszahl bei 0,7·R ≈ {f(re_07, 3)}: Profilwerte für diese Reynoldszahl verwenden.",
        "Innen wird das Schmitz-Blatt sehr breit und stark verwunden; für die Fertigung wird die Blatttiefe "
        "dort meist begrenzt oder linearisiert, was cp nur wenig verringert.",
        ("Mit Spitzenverlust nach Prandtl gerechnet." if mit_verlust else
         "Ohne Spitzenverlust gerechnet – das Ergebnis ist zu günstig."),
    ]
    if korrigiert:
        hinweise.append(f"{len(korrigiert)} Elemente sind hoch belastet (a > 0,4, meist an der Spitze); dort gilt die "
                        "einfache Impulstheorie nicht mehr und es wurde mit der Korrektur nach Buhl gerechnet.")

    return Ergebnis(TITEL, TYP, eingaben, schritte, ergebnisse, pruefungen, QUELLEN, hinweise,
                    tabellen=tabellen, diagramm=diagramm, unbelegt=list(UNBELEGT))
