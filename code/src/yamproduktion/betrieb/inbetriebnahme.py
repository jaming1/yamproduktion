"""Inbetriebnahme-Checkliste (Lastenheft M41, M42, S12): Prüfpunkte mit Soll/Ist, Messprotokoll, Abnahme.

Eine Checkliste ist ein JSON-Wörterbuch (wie Arbeits- und Montageplan):

    {"datum": "2026-11-04", "ort": "", "pruefer": "",
     "punkte": [{"id": "P1", "gruppe": "Mechanisch", "text": "…", "min": 210.0, "max": None, "einheit": "N·m",
                 "soll_text": "", "ist": "", "bemerkung": "", "quelle": "M-001", "idee": ""}],
     "messung": [{"v": 5.0, "p": 0.6}],                 # Leistungskurve: Wind m/s, elektrische Leistung kW
     "soll_kurve": {"x": [...], "y": [...], "quelle": "B-003"}}

Ein Punkt mit min/max ist ein Messwert (Ergebnis aus dem Ist-Wert), sonst eine Sichtprüfung (Ist „i. O.“/„n. i. O.“).
Sollwerte kommen aus den Berechnungen und Montageplänen des Projekts; Grenzen ohne Quelle sind Richtwerte.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..berechnungen.basis import formatiere as f

OFFEN, IO, NIO = "offen", "i. O.", "n. i. O."
GRUPPEN = ("Mechanisch", "Elektrisch", "Sicherheitsfunktionen", "Messungen")
TOLERANZ_KURVE = 0.15        # ±15 % Abweichung von der berechneten Leistungskurve – Richtwert, ungeprüft
UEBERDREHZAHL = 1.20         # Auslösung Überdrehzahlschutz ≤ 1,2 · Nenndrehzahl – Richtwert, ungeprüft
HINWEIS = ("Grenzen ohne Berechnungsquelle (Rundlauf, Lagertemperatur, Isolationswiderstand, Überdrehzahl 1,2·n, "
           "Toleranz der Leistungskurve ±15 %) sind Richtwerte, ungeprüft – mit Herstellerangaben und Normen "
           "(z. B. DIN VDE 0100-600, IEC 61400-2, IEC 61400-12-1) abgleichen.")
_JA = {"i. o.", "i.o.", "io", "ok", "ja", "✓", "x", "erfüllt"}
_NEIN = {"n. i. o.", "n.i.o.", "nio", "nein", "✗", "nicht erfüllt", "fehler"}


@dataclass
class Wert:
    wert: float
    einheit: str
    quelle: str = ""                 # Nummer der Berechnung bzw. des Montageplans
    ref: tuple | None = None         # ("berechnung", id) / ("montageplan", id) für die Verknüpfung


@dataclass
class Grundlagen:
    """Sollwerte aus dem Projekt (von modell.py gefüllt). Fehlt ein Wert, entfällt der Grenzwert (von Hand)."""
    werte: dict = field(default_factory=dict)          # Symbol → Wert
    momente: list = field(default_factory=list)        # [(Text, M_A, Quelle, ref)] aus Montageplänen
    kurve: dict | None = None                          # {"x", "y", "quelle", "ref"}


def zahl(text) -> float | None:
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text)
    t = str(text).replace(" ", "").replace(",", ".").strip()
    for zeichen in ("≤", "≥", "<", ">", "="):
        t = t.replace(zeichen, "")
    try:
        return float(t)
    except ValueError:
        return None


def ergebnis(p: dict) -> str:
    ist = str(p.get("ist", "") or "").strip()
    if not ist:
        return OFFEN
    if p.get("min") is None and p.get("max") is None:
        t = ist.lower()
        if t in _JA:
            return IO
        if t in _NEIN:
            return NIO
        return OFFEN
    x = zahl(ist)
    if x is None:
        return OFFEN
    if p.get("min") is not None and x < float(p["min"]) - 1e-9:
        return NIO
    if p.get("max") is not None and x > float(p["max"]) + 1e-9:
        return NIO
    return IO


def soll_text(p: dict) -> str:
    e = f" {p['einheit'].replace('*', '·')}" if p.get("einheit") else ""
    lo, hi = p.get("min"), p.get("max")
    if lo is not None and hi is not None and abs(float(lo) - float(hi)) < 1e-12:
        return f"{f(lo)}{e}"
    if lo is not None and hi is not None:
        return f"{f(lo)} … {f(hi)}{e}"
    if lo is not None:
        return f"≥ {f(lo)}{e}"
    if hi is not None:
        return f"≤ {f(hi)}{e}"
    return p.get("soll_text") or "i. O."


def _punkt(i, gruppe, text, min_=None, max_=None, einheit="", soll="", quelle="", ref=None) -> dict:
    return {"id": f"P{i}", "gruppe": gruppe, "text": text, "min": min_, "max": max_, "einheit": einheit,
            "soll_text": soll, "ist": "", "bemerkung": "", "quelle": quelle, "ref": list(ref) if ref else None,
            "idee": ""}


def vorlage_kwa(g: Grundlagen, datum: str = "") -> dict:
    """Vorlage „Kleinwindanlage“ (S12): mechanisch, elektrisch, Sicherheitsfunktionen, Messungen."""
    w = g.werte
    pk: list[dict] = []

    def neu(*a, **k):
        pk.append(_punkt(len(pk) + 1, *a, **k))

    # ---- Mechanisch
    for text, m_a, quelle, ref in g.momente:
        neu("Mechanisch", f"Anzugsmoment kontrollieren: {text} (Drehmomentschlüssel, Lackstrich unverändert)",
            m_a, None, "N·m", quelle=quelle, ref=ref)
    if "M_A" in w:
        x = w["M_A"]
        neu("Mechanisch", "Anzugsmoment Turmflansch-Schrauben kontrollieren", round(x.wert, 1), None, "N·m",
            quelle=x.quelle, ref=x.ref)
    neu("Mechanisch", "Rotor von Hand drehen: leichtgängig, ohne Schleifen und Geräusch", soll="leichtgängig")
    neu("Mechanisch", "Planlauf der Blattanschlussscheibe", None, 0.1, "mm", quelle="Richtwert")
    neu("Mechanisch", "Blätter: Spitzenabstand zum Turm, Blattwinkel gleich, keine Schäden", soll="gleich, unbeschädigt")
    neu("Mechanisch", "Lagertemperatur nach 1 h Betrieb", None, 80.0, "°C", quelle="Richtwert")
    neu("Mechanisch", "Schwingungen und Geräusche im Betrieb unauffällig", soll="unauffällig")
    # ---- Elektrisch
    neu("Elektrisch", "Isolationswiderstand Generatorwicklung gegen Erde (500 V DC)", 1.0, None, "MΩ",
        quelle="Richtwert (DIN VDE 0100-600)")
    neu("Elektrisch", "Schutzleiter durchgängig, Turm und Gondel geerdet", soll="durchgängig")
    neu("Elektrisch", "Drehfeld / Phasenfolge am Wechselrichter", soll="rechts (L1-L2-L3)")
    if "P_el" in w:
        x = w["P_el"]
        neu("Elektrisch", "Wechselrichter auf Nennleistung parametriert", x.wert, x.wert, x.einheit, quelle=x.quelle,
            ref=x.ref)
    neu("Elektrisch", "Netz- und Anlagenschutz (NA-Schutz) ausgelöst und wieder zugeschaltet", soll="löst aus")
    # ---- Sicherheitsfunktionen
    neu("Sicherheitsfunktionen", "Drehrichtung des Rotors (von vorn gesehen)", soll="im Uhrzeigersinn")
    if "t_Br" in w:
        x = w["t_Br"]
        neu("Sicherheitsfunktionen", "Bremse bei Nenndrehzahl auslösen: Zeit bis Stillstand", None, round(x.wert, 1), "s",
            quelle=x.quelle, ref=x.ref)
    else:
        neu("Sicherheitsfunktionen", "Bremse bei Nenndrehzahl auslösen: Rotor kommt zum Stillstand", soll="Stillstand")
    neu("Sicherheitsfunktionen", "Bremse hält den Rotor im Stillstand (Feststellbremse)", soll="hält")
    if "n" in w:
        x = w["n"]
        neu("Sicherheitsfunktionen", f"Überdrehzahlschutz: Auslösedrehzahl (≤ {f(UEBERDREHZAHL)} · n_N, Richtwert)",
            None, round(UEBERDREHZAHL * x.wert, 1), "1/min", quelle=x.quelle, ref=x.ref)
    else:
        neu("Sicherheitsfunktionen", "Überdrehzahlschutz löst aus", soll="löst aus")
    if "v_ab" in w:
        x = w["v_ab"]
        neu("Sicherheitsfunktionen", "Sturmabschaltung: Abschaltwind (Mittel 10 min)", None, x.wert, "m/s",
            quelle=x.quelle, ref=x.ref)
    neu("Sicherheitsfunktionen", "Not-Halt: Anlage geht in sicheren Zustand (Bremse fällt ein)", soll="sicherer Zustand")
    # ---- Messungen
    if "v_ein" in w:
        x = w["v_ein"]
        neu("Messungen", "Einschaltwind: Anlage speist ab", None, x.wert, "m/s", quelle=x.quelle, ref=x.ref)
    if "n" in w:
        x = w["n"]
        neu("Messungen", "Rotordrehzahl bei Nennwind", round(0.9 * x.wert, 1), round(1.1 * x.wert, 1), "1/min",
            quelle=f"{x.quelle} ±10 % (Richtwert)", ref=x.ref)
    neu("Messungen", "Leistungskurve gemessen (siehe Messprotokoll)", soll=f"±{f(TOLERANZ_KURVE * 100)} % zur Rechnung")
    return {"datum": datum, "ort": "", "pruefer": "", "punkte": pk, "messung": [],
            "soll_kurve": dict(g.kurve) if g.kurve else None}


def kurve_soll(kurve: dict | None, v: float) -> float | None:
    """Lineare Interpolation der berechneten Leistungskurve (kW) bei Wind v."""
    if not kurve or not kurve.get("x"):
        return None
    xs, ys = kurve["x"], kurve["y"]
    if v <= xs[0]:
        return ys[0]
    if v >= xs[-1]:
        return ys[-1]
    for i in range(1, len(xs)):
        if v <= xs[i]:
            t = (v - xs[i - 1]) / (xs[i] - xs[i - 1])
            return ys[i - 1] + t * (ys[i] - ys[i - 1])
    return None


@dataclass
class Messpunkt:
    v: float
    p: float
    soll: float | None
    abweichung: float | None         # relativ, z. B. −0,08
    ok: bool | None


def messung_auswerten(liste: dict) -> list[Messpunkt]:
    out = []
    kurve = liste.get("soll_kurve")
    for m in sorted(liste.get("messung", []), key=lambda m: m["v"]):
        s = kurve_soll(kurve, m["v"])
        if s is None or s < 1e-6:
            out.append(Messpunkt(m["v"], m["p"], s, None, None))
            continue
        d = (m["p"] - s) / s
        out.append(Messpunkt(m["v"], m["p"], s, d, abs(d) <= TOLERANZ_KURVE + 1e-9))
    return out


def auswerten(liste: dict) -> dict:
    """Zählt die Ergebnisse; die Messung der Leistungskurve setzt ihren Punkt selbst."""
    punkte = liste.get("punkte", [])
    mp = messung_auswerten(liste)
    bewertet = [m for m in mp if m.ok is not None]
    for p in punkte:
        if p["text"].startswith("Leistungskurve gemessen") and bewertet:
            p["ist"] = IO if all(m.ok for m in bewertet) else NIO
            p["bemerkung"] = (f"{len(bewertet)} Messpunkte, größte Abweichung "
                              f"{f(max(abs(m.abweichung) for m in bewertet) * 100, 3)} %")
    zaehler = {IO: 0, NIO: 0, OFFEN: 0}
    for p in punkte:
        zaehler[ergebnis(p)] += 1
    abgenommen = bool(punkte) and zaehler[NIO] == 0 and zaehler[OFFEN] == 0
    return {"io": zaehler[IO], "nio": zaehler[NIO], "offen": zaehler[OFFEN], "gesamt": len(punkte),
            "abgenommen": abgenommen, "messpunkte": mp}


def maengel(liste: dict) -> list[dict]:
    return [p for p in liste.get("punkte", []) if ergebnis(p) == NIO]


def naechste_id(liste: dict) -> str:
    vorhanden = {p["id"] for p in liste.get("punkte", [])}
    i = 1
    while f"P{i}" in vorhanden:
        i += 1
    return f"P{i}"
