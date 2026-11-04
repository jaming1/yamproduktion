"""Schnittdaten und Hauptzeiten (Lastenheft S10).

Formeln (Tabellenbuch Metall, Abschnitt Fertigungstechnik):
    Drehzahl            n  = v_c · 1000 / (π · d)              [1/min]   (v_c in m/min, d in mm)
    Vorschubgeschw.     v_f = f · n  (Drehen, Bohren)  bzw.  v_f = f_z · z · n  (Fräsen)   [mm/min]
    Hauptzeit           t_h = L · i / v_f                      [min]     (L Vorschubweg mit An-/Überlauf, i Schnitte)

Die Richtwerte für v_c, f und f_z sind typische Mittelwerte für Hartmetall (Drehen, Fräsen) bzw. HSS (Bohren)
aus dem Tabellenbuch – **Richtwert, ungeprüft**: vor der Fertigung mit den Werkzeugherstellerangaben abgleichen.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

HINWEIS = ("Schnittwerte sind Richtwerte (Hartmetall drehen/fräsen, HSS bohren) aus dem Tabellenbuch, ungeprüft – "
           "mit den Angaben des Werkzeugherstellers abgleichen.")

# Werkstoffgruppe → Richtwerte
RICHTWERTE = {
    #                        Drehen v_c, f   Fräsen v_c, f_z   Bohren v_c   Sägen cm²/min
    "Baustahl":             dict(vc_d=220, f_d=0.30, vc_f=180, fz=0.12, vc_b=30, saege=20),
    "Vergütungsstahl":      dict(vc_d=160, f_d=0.25, vc_f=140, fz=0.10, vc_b=20, saege=15),
    "Einsatzstahl":         dict(vc_d=180, f_d=0.25, vc_f=150, fz=0.10, vc_b=25, saege=16),
    "Nichtrostender Stahl": dict(vc_d=140, f_d=0.20, vc_f=110, fz=0.08, vc_b=12, saege=10),
    "Gusseisen mit Kugelgraphit": dict(vc_d=160, f_d=0.25, vc_f=140, fz=0.12, vc_b=22, saege=15),
    "Aluminium":            dict(vc_d=500, f_d=0.25, vc_f=400, fz=0.12, vc_b=80, saege=60),
}
AP_SCHRUPPEN = 3.0       # mm Schnitttiefe je Schruppschnitt (Drehen)
F_SCHLICHTEN = 0.10      # mm Vorschub beim Schlichten
N_MAX_DREHEN = 3000      # 1/min
N_MAX_FRAESEN = 6000
ZAEHNE_FRAESER = 4
ANLAUF = 2.0             # mm An- und Überlauf je Seite
ZUSCHLAG = 0.25          # Neben- und Verteilzeit als Anteil der Hauptzeit (Richtwert)
SPANNEN = 1.0            # min je Arbeitsgang zum Spannen/Messen (Richtwert)


class SchnittFehler(ValueError):
    pass


def richtwerte(gruppe: str) -> dict:
    if gruppe not in RICHTWERTE:
        raise SchnittFehler(f"Für „{gruppe}“ sind keine Zerspanungs-Richtwerte hinterlegt – Zeiten von Hand eintragen.")
    return RICHTWERTE[gruppe]


def drehzahl(vc: float, d: float, n_max: float) -> float:
    if d <= 0 or vc <= 0:
        raise SchnittFehler("Durchmesser und Schnittgeschwindigkeit müssen positiv sein.")
    return min(vc * 1000 / (math.pi * d), n_max)


@dataclass
class Zeit:
    th: float                       # Hauptzeit min
    schritte: list[str] = field(default_factory=list)   # Rechenweg in Worten

    @property
    def te(self) -> float:
        """Stückzeit = Hauptzeit + Zuschlag für Neben- und Verteilzeit + Spannen."""
        return self.th * (1 + ZUSCHLAG) + SPANNEN


def _f(x: float, n: int = 3) -> str:
    text = f"{x:.0f}" if abs(x) >= 10 ** n else f"{x:.{n}g}"
    return text.replace(".", ",")


def laengsdrehen(gruppe: str, abschnitte: list, schlichten: bool = True) -> Zeit:
    """abschnitte: [(d_von, d_bis, länge)] – Außen (d_von > d_bis) oder innen (d_von < d_bis)."""
    r = richtwerte(gruppe)
    z = Zeit(0.0)
    for d_von, d_bis, l in abschnitte:
        if l <= 0:
            continue
        aufmass = abs(d_von - d_bis) / 2
        i = max(1, math.ceil(aufmass / AP_SCHRUPPEN - 1e-9)) if aufmass > 0 else 0
        d_n = max(d_von, d_bis)
        n = drehzahl(r["vc_d"], d_n, N_MAX_DREHEN)
        L = l + ANLAUF
        th = L * i / (r["f_d"] * n) if i else 0.0
        z.schritte.append(f"Ø{_f(d_von)}→Ø{_f(d_bis)} auf {_f(l)} mm: n = {_f(n)} 1/min, {i} Schnitt(e) à "
                          f"a_p ≤ {_f(AP_SCHRUPPEN)} mm, f = {_f(r['f_d'])} mm → t_h = {_f(th)} min")
        if schlichten:
            n_s = drehzahl(r["vc_d"] * 1.2, min(d_von, d_bis) or d_n, N_MAX_DREHEN)
            th_s = L / (F_SCHLICHTEN * n_s)
            z.schritte.append(f"  schlichten f = {_f(F_SCHLICHTEN)} mm, n = {_f(n_s)} 1/min → t_h = {_f(th_s)} min")
            th += th_s
        z.th += th
    return z


def plandrehen(gruppe: str, d: float, seiten: int = 2) -> Zeit:
    r = richtwerte(gruppe)
    n = drehzahl(r["vc_d"], d, N_MAX_DREHEN)       # konstante Drehzahl beim größten Ø (sichere Seite)
    th = seiten * (d / 2 + ANLAUF) / (r["f_d"] * n)
    return Zeit(th, [f"Plandrehen Ø{_f(d)}, {seiten} Seite(n): n = {_f(n)} 1/min, f = {_f(r['f_d'])} mm → "
                     f"t_h = {_f(th)} min"])


def fraesen(gruppe: str, weg: float, tiefe: float, d_fraeser: float) -> Zeit:
    r = richtwerte(gruppe)
    n = drehzahl(r["vc_f"], d_fraeser, N_MAX_FRAESEN)
    vf = r["fz"] * ZAEHNE_FRAESER * n
    i = max(1, math.ceil(tiefe / (0.5 * d_fraeser) - 1e-9))
    L = weg + d_fraeser + 2 * ANLAUF
    th = L * i / vf
    return Zeit(th, [f"Fräser Ø{_f(d_fraeser)}, z = {ZAEHNE_FRAESER}: n = {_f(n)} 1/min, v_f = {_f(vf)} mm/min, "
                     f"{i} Zustellung(en), L = {_f(L)} mm → t_h = {_f(th)} min"])


def bohren(gruppe: str, d: float, tiefe: float, anzahl: int = 1) -> Zeit:
    r = richtwerte(gruppe)
    n = drehzahl(r["vc_b"], d, N_MAX_FRAESEN)
    f = min(0.4, max(0.05, 0.015 * d))              # Vorschub HSS ≈ 0,015 · d (Richtwert)
    L = tiefe + 0.3 * d + ANLAUF                    # Bohrerspitze 118°: Anschnitt ≈ 0,3 · d
    th = anzahl * L / (f * n)
    return Zeit(th, [f"{anzahl}× Ø{_f(d)} tief {_f(tiefe)}: n = {_f(n)} 1/min, f = {_f(f)} mm, L = {_f(L)} mm → "
                     f"t_h = {_f(th)} min"])


def saegen(gruppe: str, flaeche_mm2: float) -> Zeit:
    leistung = RICHTWERTE.get(gruppe, {"saege": 15})["saege"]
    th = flaeche_mm2 / 100 / leistung
    return Zeit(th, [f"Querschnitt {_f(flaeche_mm2 / 100)} cm² bei {leistung} cm²/min → t_h = {_f(th)} min"])


def brennschneiden(umfang_mm: float, dicke: float) -> Zeit:
    v = max(150.0, 700.0 - 12 * dicke)              # mm/min, Autogen/Plasma grob – Richtwert, unbelegt
    th = umfang_mm / v
    return Zeit(th, [f"Schnittlänge {_f(umfang_mm)} mm bei ≈ {_f(v)} mm/min (Dicke {_f(dicke)} mm) → "
                     f"t_h = {_f(th)} min"])
