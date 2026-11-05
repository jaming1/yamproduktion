"""Aufgaben, Meilensteine und Zeitplan (M48, M49, S17).

Eine Aufgabe hat Start und Termin (ISO-Datum); ein Meilenstein nur einen Termin. Die Vorlage
„Kleinwindanlage“ legt je Phase eine Aufgabe mit geschätzter Dauer an (Schätzwerte, anpassen).
"""
from __future__ import annotations

from datetime import date, timedelta

from ..betrieb.wartung import anzeigen, lesen

STAENDE = ("offen", "in Arbeit", "erledigt")
HINWEIS = ("Dauern der Vorlage sind Schätzwerte für ein Ein-Personen-Projekt nach Feierabend – an die eigene Zeit "
           "anpassen. Fortschritt je Phase = Anteil erledigter Aufgaben und geprüfter/freigegebener Objekte; "
           "eine freigegebene Phase zählt 100 %.")

# Phase, Titel, Dauer in Wochen, parallel zum Vorgänger (Wochen Versatz), Meilenstein danach
_VORLAGE = [
    ("P1", "Idee, Problem und TRIZ-Widersprüche festhalten", 1, None, ""),
    ("P2", "Anforderungen und Funktionen festlegen", 1, None, "Lastenheft freigegeben"),
    ("P2", "Baugenehmigung / Verfahrensfreiheit bei der Gemeinde klären", 8, 0, ""),
    ("P3", "Konzeptvarianten bewerten und auswählen", 2, None, "Konzept festgelegt"),
    ("P4", "Rotor, Lasten, Maschinenelemente, Turm berechnen", 3, None, ""),
    ("P5", "Bauteile, Baugruppen und Zeichnungen erstellen", 4, None, "Konstruktion freigegeben"),
    ("P5", "Risikobeurteilung und FMEA", 2, -2, ""),
    ("P6", "Angebote Fremdfertigung und Zukaufteile einholen", 2, None, ""),
    ("P6", "Teile fertigen und nach Prüfplan prüfen", 6, None, "Alle Teile i. O."),
    ("P7", "Gondel und Rotor montieren", 2, None, ""),
    ("P8", "Anlage beim Netzbetreiber anmelden", 4, -4, ""),
    ("P8", "Inbetriebnahme und Leistungskurve messen", 1, None, "Abnahme"),
    ("P9", "Erste Wartung (Schrauben nachziehen)", 1, 3, ""),
]


def vorlage_kwa(start: date) -> list[dict]:
    """Aufgaben und Meilensteine der Kleinwindanlage ab `start` (Schätzwerte)."""
    out: list[dict] = []
    ende_vorher = start
    start_vorher = start
    for phase, titel, wochen, versatz, meilenstein in _VORLAGE:
        if versatz is None:
            beginn = ende_vorher
        elif versatz <= 0:
            beginn = start_vorher if versatz == 0 else ende_vorher + timedelta(weeks=versatz)
        else:
            beginn = ende_vorher + timedelta(weeks=versatz)
        ende = beginn + timedelta(weeks=wochen) - timedelta(days=1)
        out.append({"titel": titel, "phase": phase, "start": beginn.isoformat(), "termin": ende.isoformat(),
                    "meilenstein": 0, "notiz": "Dauer Schätzwert"})
        if versatz is None or versatz > 0:          # Kette; parallele Aufgaben verschieben den Nachfolger nicht
            start_vorher, ende_vorher = beginn, ende + timedelta(days=1)
        if meilenstein:
            out.append({"titel": meilenstein, "phase": phase, "start": "", "termin": ende.isoformat(),
                        "meilenstein": 1, "notiz": "Termin Schätzwert"})
    return out


def zeitraum(a: dict) -> tuple[date | None, date | None]:
    ende = lesen(a.get("termin", ""))
    beginn = ende if a.get("meilenstein") else (lesen(a.get("start", "")) or ende)
    return beginn, ende


def verzug(a: dict, heute: date) -> int:
    """Tage über dem Termin (0 = im Plan oder erledigt)."""
    _, ende = zeitraum(a)
    if a.get("stand") == "erledigt" or ende is None:
        return 0
    return max((heute - ende).days, 0)


def gesamt_zeitraum(aufgaben: list[dict]) -> tuple[date, date] | None:
    tage = [d for a in aufgaben for d in zeitraum(a) if d]
    return (min(tage), max(tage)) if tage else None


def termin_text(a: dict) -> str:
    beginn, ende = zeitraum(a)
    if a.get("meilenstein"):
        return anzeigen(ende)
    return f"{anzeigen(beginn)} – {anzeigen(ende)}" if beginn and beginn != ende else anzeigen(ende)


def fortschritt(erledigt: int, gesamt: int, freigegeben: bool = False) -> int:
    if freigegeben:
        return 100
    return round(100 * erledigt / gesamt) if gesamt else 0
