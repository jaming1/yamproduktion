"""Wartungsplan (Lastenheft S13): Tätigkeiten mit Intervall, Verschleißteile, Fälligkeit.

    {"start": "2026-11-04",                       # Inbetriebnahme – Bezug für die erste Fälligkeit
     "punkte": [{"id": "W1", "bauteil": "…", "taetigkeit": "…", "intervall": 12, "erstes": 1,
                 "verschleiss": false, "zuletzt": "", "quelle": "…"}]}

Intervalle in Monaten. „erstes“ = abweichendes erstes Intervall (z. B. Schrauben nach 1 Monat nachziehen).
Lagertausch aus der Lebensdauer L10h der Lagerberechnung und den Betriebsstunden je Jahr.
"""
from __future__ import annotations

import calendar
import math
from datetime import date

from ..berechnungen.basis import formatiere as f

STUNDEN_JAHR = 8760
LEBENSDAUER_JAHRE = 20     # Auslegungslebensdauer der Vorlage Kleinwindanlage
BETRIEB_ANTEIL = 0.7        # Anteil Betriebsstunden ohne Ertragsrechnung – Schätzwert, unbelegt
HINWEIS = ("Intervalle sind Richtwerte (Herstellerangaben von Lager, Bremse, Getriebe und Wechselrichter haben "
           "Vorrang), ungeprüft. Lagertausch aus L10h der Lagerberechnung und den Betriebsstunden je Jahr.")


def plus_monate(d: date, monate: int) -> date:
    m = d.month - 1 + int(monate)
    jahr, monat = d.year + m // 12, m % 12 + 1
    return date(jahr, monat, min(d.day, calendar.monthrange(jahr, monat)[1]))


def lesen(text: str) -> date | None:
    if not text:
        return None
    t = str(text).strip()
    try:
        if "." in t:
            tag, monat, jahr = (int(x) for x in t.split("."))
            return date(jahr, monat, tag)
        return date.fromisoformat(t)
    except ValueError:
        return None


def anzeigen(d: date | None) -> str:
    return d.strftime("%d.%m.%Y") if d else ""


def faellig(punkt: dict, start: str) -> date | None:
    """Nächste Fälligkeit: letzte Durchführung + Intervall, sonst Inbetriebnahme + erstes Intervall."""
    intervall = punkt.get("intervall")
    if not intervall:
        return None
    zuletzt = lesen(punkt.get("zuletzt", ""))
    if zuletzt:
        return plus_monate(zuletzt, intervall)
    s = lesen(start)
    return plus_monate(s, punkt.get("erstes") or intervall) if s else None


def _p(i, bauteil, taetigkeit, intervall, erstes=None, verschleiss=False, quelle="Richtwert") -> dict:
    return {"id": f"W{i}", "bauteil": bauteil, "taetigkeit": taetigkeit, "intervall": intervall, "erstes": erstes,
            "verschleiss": verschleiss, "zuletzt": "", "quelle": quelle}


def vorlage_kwa(werte: dict, start: str = "", mit_getriebe: bool = False) -> dict:
    """`werte`: Symbol → inbetriebnahme.Wert (L10h,A, L10h,B, t_unter, V)."""
    pk: list[dict] = []

    def neu(*a, **k):
        pk.append(_p(len(pk) + 1, *a, **k))

    neu("Schraubverbindungen (Nabe, Blätter, Turmflansch)", "Anzugsmomente kontrollieren, Lackstriche prüfen", 12,
        erstes=1, quelle="Richtwert: erstes Nachziehen nach 1 Monat (Setzen)")
    neu("Rotorblätter", "Sichtprüfung auf Risse, Erosion an der Vorderkante, Blitzschäden", 6)
    neu("Hauptlager", "Nachschmieren (Fettsorte und -menge nach Lagerhersteller)", 6)
    neu("Bremse", "Bremsbeläge messen, Bremsscheibe auf Riefen prüfen; Funktionstest", 6, verschleiss=True)
    neu("Bremsbeläge", "Tauschen bei Erreichen der Mindestdicke", 24, verschleiss=True,
        quelle="Schätzwert – nach Messung")
    if mit_getriebe:
        neu("Getriebe", "Ölstand und Dichtheit prüfen; Ölwechsel nach Hersteller", 12, verschleiss=True)
    neu("Generator und Kabel", "Isolationswiderstand messen, Klemmen nachziehen, Kabel im Turm auf Verdrillung prüfen", 12)
    neu("Wechselrichter / Steuerung", "Fehlerspeicher lesen, Lüfter und Filter reinigen, NA-Schutz testen", 12)
    neu("Sicherheitsfunktionen", "Not-Halt, Überdrehzahlschutz und Sturmabschaltung testen", 12)
    neu("Turm und Fundament", "Korrosion, Schweißnähte, Abspannungen, Fundamentanker prüfen", 12)
    stunden = STUNDEN_JAHR * BETRIEB_ANTEIL
    quelle_h = f"{f(BETRIEB_ANTEIL * 100)} % Betriebszeit (Schätzwert)"
    if "t_unter" in werte:
        anteil = (1 - werte["t_unter"].wert) * (werte["V"].wert if "V" in werte else 1.0)
        stunden = STUNDEN_JAHR * anteil
        quelle_h = f"{f(stunden)} Betriebsstunden/a aus {werte['t_unter'].quelle}"
    for sym, name in (("L10h,B", "Hauptlager B (rotorseitig)"), ("L10h,A", "Hauptlager A")):
        if sym in werte:
            x = werte[sym]
            jahre = x.wert / stunden
            if jahre > LEBENSDAUER_JAHRE:
                neu(name, f"Zustand prüfen (Laufgeräusch, Temperatur, Spiel); L10h = {f(x.wert)} h ≈ {f(jahre)} Jahre "
                          f"> {LEBENSDAUER_JAHRE} Jahre Auslegung – Tausch nur bei Befund", 12, verschleiss=True,
                    quelle=f"{x.quelle}, {quelle_h}")
            else:
                neu(name, f"Lager tauschen (L10h = {f(x.wert)} h ≈ {f(jahre)} Jahre)", max(int(jahre * 12), 1),
                    verschleiss=True, quelle=f"{x.quelle}, {quelle_h}")
    return {"start": start, "punkte": pk}


def faellige(plan: dict, heute: date) -> list[dict]:
    return [p for p in plan.get("punkte", []) if (d := faellig(p, plan.get("start", ""))) and d <= heute]


def verschleissteile(plan: dict) -> list[dict]:
    return [p for p in plan.get("punkte", []) if p.get("verschleiss")]


def naechste_id(plan: dict) -> str:
    vorhanden = {p["id"] for p in plan.get("punkte", [])}
    i = 1
    while f"W{i}" in vorhanden:
        i += 1
    return f"W{i}"
