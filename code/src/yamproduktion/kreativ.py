"""Kreativmethoden für die Ideenphase (K2): Brainstorming-Board, Methode 6-3-5, Mindmap.

Reine Logik ohne Datenbank und Oberfläche: Regeln, Ablauf von 6-3-5 (wer schreibt
wann auf welches Blatt), Anordnung der Mindmap und Auswertungen. Gespeichert wird
im Produktmodell (Tabellen ``kreativ`` und ``kreativ_eintrag``).

Quellen: A. F. Osborn, „Applied Imagination“ (1953) – Brainstorming-Regeln;
B. Rohrbach, „Kreativ nach Regeln – Methode 635“, Absatzwirtschaft 12 (1969);
T. Buzan, „The Mind Map Book“ (1993).
"""
from __future__ import annotations

import math

# Schlüssel → (Anzeigename, Kurzbeschreibung)
METHODEN = {
    "brainstorming": ("Brainstorming-Board",
                      "Ideen als Zettel sammeln, frei anordnen, zu Gruppen ordnen und mit Punkten bewerten."),
    "635": ("Methode 6-3-5",
            "6 Personen schreiben je 3 Ideen in 5 Minuten und reichen das Blatt weiter – "
            "jede Runde baut auf den Ideen der Vorgänger auf."),
    "mindmap": ("Mindmap",
                "Vom Thema in der Mitte aus Äste und Zweige bilden – zeigt Zusammenhänge auf einen Blick."),
}

REGELN_BRAINSTORMING = (
    "Keine Kritik während der Sammelphase – bewertet wird erst danach.",
    "Menge vor Güte: viele Ideen bringen die guten mit.",
    "Ungewöhnliche Ideen sind willkommen.",
    "Ideen anderer aufgreifen und weiterdenken.",
)

TEILNEHMER_635 = (2, 8)     # sinnvoller Bereich; klassisch 6
IDEEN_JE_RUNDE = 3
MINUTEN_635 = 5


class KreativFehler(ValueError):
    pass


def methode_name(methode: str) -> str:
    if methode not in METHODEN:
        raise KreativFehler(f"Die Methode „{methode}“ gibt es nicht.")
    return METHODEN[methode][0]


# ================================================================ 6-3-5
def pruefe_teilnehmer(n: int) -> int:
    lo, hi = TEILNEHMER_635
    if not lo <= int(n) <= hi:
        raise KreativFehler(f"Bei 6-3-5 sind {lo} bis {hi} Teilnehmende sinnvoll (klassisch 6).")
    return int(n)


def runden_635(n: int) -> int:
    """So viele Runden, bis jedes Blatt bei allen Teilnehmenden war."""
    return pruefe_teilnehmer(n)


def felder_635(n: int) -> int:
    """Anzahl Felder insgesamt: Blätter × Runden × 3 (bei 6 Personen 108)."""
    return n * runden_635(n) * IDEEN_JE_RUNDE


def schreiber(blatt: int, runde: int, n: int) -> int:
    """Wer schreibt in Runde ``runde`` auf Blatt ``blatt``? (Blatt k beginnt bei Person k, dann reihum.)"""
    _pruefe_blatt_runde(blatt, runde, n)
    return (blatt - 1 + runde - 1) % n + 1


def blatt_von(person: int, runde: int, n: int) -> int:
    """Welches Blatt hat Person ``person`` in Runde ``runde`` vor sich?"""
    _pruefe_blatt_runde(person, runde, n)
    return (person - 1 - (runde - 1)) % n + 1


def _pruefe_blatt_runde(blatt: int, runde: int, n: int) -> None:
    pruefe_teilnehmer(n)
    if not 1 <= blatt <= n:
        raise KreativFehler(f"Blatt bzw. Person {blatt} gibt es nicht (1 bis {n}).")
    if not 1 <= runde <= n:
        raise KreativFehler(f"Runde {runde} gibt es nicht (1 bis {n}).")


def stand_635(eintraege: list[dict], n: int) -> dict:
    """Fortschritt: gefüllte Felder, aktuelle Runde (erste nicht volle), fertig ja/nein."""
    gefuellt = {(e["blatt"], e["runde"], e["spalte"]) for e in eintraege
                if e.get("blatt") and e.get("text", "").strip()}
    runden = runden_635(n)
    aktuell = runden + 1
    for r in range(1, runden + 1):
        voll = all((b, r, s) in gefuellt for b in range(1, n + 1) for s in range(1, IDEEN_JE_RUNDE + 1))
        if not voll:
            aktuell = r
            break
    return {"gefuellt": len(gefuellt), "gesamt": felder_635(n), "runde": min(aktuell, runden),
            "fertig": aktuell > runden}


# ================================================================ Brainstorming
def gruppen(eintraege: list[dict]) -> list[tuple[str, list[dict]]]:
    """Zettel nach Gruppe (Reihenfolge des ersten Auftretens), ohne Gruppe zuletzt; je Gruppe nach Punkten."""
    reihenfolge: dict[str, list[dict]] = {}
    for e in sorted(eintraege, key=lambda e: e["id"]):
        reihenfolge.setdefault(e.get("gruppe", "").strip(), []).append(e)
    ohne = reihenfolge.pop("", None)
    ergebnis = [(g, sorted(l, key=lambda e: (-e.get("punkte", 0), e["id"]))) for g, l in reihenfolge.items()]
    if ohne:
        ergebnis.append(("", sorted(ohne, key=lambda e: (-e.get("punkte", 0), e["id"]))))
    return ergebnis


def beste(eintraege: list[dict], anzahl: int = 3) -> list[dict]:
    """Die Zettel mit den meisten Punkten (nur solche mit mindestens einem Punkt)."""
    mit = [e for e in eintraege if e.get("punkte", 0) > 0 and e.get("text", "").strip()]
    return sorted(mit, key=lambda e: (-e["punkte"], e["id"]))[:anzahl]


def freier_platz(eintraege: list[dict], breite: float = 180, hoehe: float = 110,
                 spalten: int = 6) -> tuple[float, float]:
    """Nächster freier Platz im Raster für einen neuen Zettel (damit nichts übereinander liegt)."""
    belegt = {(round(e.get("x") or 0), round(e.get("y") or 0)) for e in eintraege}
    i = 0
    while True:
        x, y = (i % spalten) * (breite + 20), (i // spalten) * (hoehe + 20)
        if (round(x), round(y)) not in belegt:
            return float(x), float(y)
        i += 1


# ================================================================ Mindmap
def kinder(knoten: list[dict], eltern_id: int | None) -> list[dict]:
    return sorted((k for k in knoten if k.get("eltern_id") == eltern_id), key=lambda k: k["id"])


def baum(knoten: list[dict]) -> list[tuple[int, dict]]:
    """Alle Knoten in Baumreihenfolge als (Tiefe, Knoten); Tiefe 1 = Hauptast."""
    ids = {k["id"] for k in knoten}
    waisen = [k for k in knoten if k.get("eltern_id") not in ids and k.get("eltern_id") is not None]
    ergebnis: list[tuple[int, dict]] = []

    def gehe(eltern, tiefe):
        for k in kinder(knoten, eltern):
            ergebnis.append((tiefe, k))
            gehe(k["id"], tiefe + 1)
    gehe(None, 1)
    for w in waisen:                       # verwaiste Knoten (Elternteil gelöscht) als Hauptast zeigen
        ergebnis.append((1, w))
        gehe(w["id"], 2)
    return ergebnis


def _blaetter(knoten: list[dict], id_: int) -> int:
    k = kinder(knoten, id_)
    return max(1, sum(_blaetter(knoten, c["id"]) for c in k))


def anordnung(knoten: list[dict], abstand: float = 190.0) -> dict[int, tuple[float, float]]:
    """Radiale Anordnung um das Thema (0, 0): jeder Ast bekommt einen Winkelbereich nach Zahl seiner Blätter.

    Ergebnis: Knoten-ID → (x, y). Das Thema selbst liegt bei (0, 0) und hat keine ID.
    """
    lagen: dict[int, tuple[float, float]] = {}
    ids = {k["id"] for k in knoten}
    wurzeln = [k for k in knoten if k.get("eltern_id") is None or k.get("eltern_id") not in ids]
    wurzeln.sort(key=lambda k: k["id"])
    gesamt = sum(_blaetter(knoten, w["id"]) for w in wurzeln) or 1

    def lege(k, von, bis, tiefe):
        winkel = (von + bis) / 2
        r = abstand * (1 + 0.85 * (tiefe - 1))
        lagen[k["id"]] = (r * math.cos(winkel), r * math.sin(winkel))
        unter = kinder(knoten, k["id"])
        summe = sum(_blaetter(knoten, c["id"]) for c in unter) or 1
        start = von
        for c in unter:
            teil = (bis - von) * _blaetter(knoten, c["id"]) / summe
            lege(c, start, start + teil, tiefe + 1)
            start += teil

    # erster Ast mittig oben, dann im Uhrzeigersinn (Qt: y zeigt nach unten)
    start = -math.pi / 2 - (math.pi * _blaetter(knoten, wurzeln[0]["id"]) / gesamt if wurzeln else 0)
    for w in wurzeln:
        teil = 2 * math.pi * _blaetter(knoten, w["id"]) / gesamt
        lege(w, start, start + teil, 1)
        start += teil
    return lagen


def gliederung(thema: str, knoten: list[dict]) -> str:
    """Mindmap als eingerückte Textgliederung (zum Kopieren in andere Programme)."""
    zeilen = [thema.strip() or "Thema"]
    for tiefe, k in baum(knoten):
        zeilen.append("  " * tiefe + "– " + k.get("text", "").strip())
    return "\n".join(zeilen)
