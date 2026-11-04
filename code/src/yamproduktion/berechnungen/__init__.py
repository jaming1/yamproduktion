"""Verzeichnis aller Berechnungsarten.

Jede Art ist ein Modul mit: TYP, TITEL, KURZ, BESCHREIBUNG, HAUPT, FELDER, Eingabe-Klasse, berechne(),
FELD_EINHEITEN, FELD_NAMEN, FELD_SUCHBEGRIFFE (Werte aus Anforderungen) und BERECHNUNGS_QUELLEN
(Werte aus anderen gespeicherten Berechnungen).
"""
from . import (antrieb, bremse, ertrag, getriebe, lager, lasten, rotor, schrauben, schweissnaht, turm, welle,
               welle_nabe)

# Windkraft (MS4) und Maschinenelemente (MS5); welle_nabe liefert zwei Arten als Objekte
WINDKRAFT = [rotor, ertrag, lasten, antrieb]
MASCHINENELEMENTE = [welle, lager, schrauben, welle_nabe.passfeder_art, welle_nabe.press_art, schweissnaht,
                     getriebe, turm, bremse]
MODULE = WINDKRAFT + MASCHINENELEMENTE
_KLASSEN = {rotor.TYP: rotor.RotorEingaben, ertrag.TYP: ertrag.ErtragEingaben,
            lasten.TYP: lasten.LastEingaben, antrieb.TYP: antrieb.AntriebEingaben,
            welle.TYP: welle.WelleEingaben, lager.TYP: lager.LagerEingaben, schrauben.TYP: schrauben.SchraubenEingaben,
            schweissnaht.TYP: schweissnaht.NahtEingaben, getriebe.TYP: getriebe.GetriebeEingaben,
            turm.TYP: turm.TurmEingaben, bremse.TYP: bremse.BremsEingaben}

ARTEN = {
    m.TYP: {
        "modul": m,
        "titel": m.TITEL,
        "kurz": m.KURZ,
        "eingaben": _KLASSEN.get(m.TYP) or m.Eingaben,
        "berechne": m.berechne,
        "hauptergebnis": m.HAUPT,
        "feld_einheiten": m.FELD_EINHEITEN,
        "quellen": getattr(m, "BERECHNUNGS_QUELLEN", {}),
    }
    for m in MODULE
}

# Lesbare Feldnamen aller Berechnungsarten
FELD_NAMEN = {}
for _m in MODULE:
    FELD_NAMEN.update(_m.FELD_NAMEN)


def einheit_normal(text: str) -> str:
    """Anzeige-Einheit (N·m, m², –) in Pint-Schreibweise (N*m, m^2, '')."""
    return (text or "").replace("·", "*").replace("²", "^2").replace("³", "^3").replace("–", "").strip()


def wert_aus_ergebnis(ergebnis: dict, symbol: str) -> tuple[float, str] | None:
    """Wert und Einheit einer Größe aus einer gespeicherten Berechnung (Ergebnisse, sonst Eingaben)."""
    for liste in ("ergebnisse", "eingaben"):
        for g in ergebnis.get(liste, []):
            if g["symbol"] == symbol:
                return g["wert"], einheit_normal(g["einheit"])
    return None
