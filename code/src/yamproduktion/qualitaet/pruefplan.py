"""Prüfplan je Bauteil (M43, S15): Prüfmerkmale aus der Zeichnung, Grenzmaße, Prüfmittel, Ist-Werte.

    {"teil": "T-001", "zeichnung": "V3", "datum": "2026-11-04", "pruefer": "", "los": "",
     "merkmale": [{"id": "PM1", "merkmal": "Ø80 k6", "art": "Durchmesser", "nenn": 80, "toleranz": "k6",
                   "min": 80.002, "max": 80.021, "pruefmittel": "…", "umfang": "100 %",
                   "ist": "", "ergebnis": "offen", "quelle": "…", "bemerkung": ""}]}

Prüfmittel nach der Faustregel „Messunsicherheit ≤ 1/10 der Toleranz“ – Richtwert.
"""
from __future__ import annotations

import re

from ..berechnungen.basis import formatiere as f
from ..betrieb.inbetriebnahme import IO, NIO, OFFEN, zahl
from . import toleranzen as T

HINWEIS = ("Grenzmaße nach ISO 286 / ISO 2768-m aus dem Gedächtnis (Norm, ungeprüft). Prüfmittel nach der Faustregel "
           "Messunsicherheit ≤ 1/10 der Toleranz (Richtwert); Prüfumfang festlegen, Prüfmittel kalibriert.")

_MASS = re.compile(r"^(?:(?P<anzahl>\d+)\s*×\s*)?(?P<lk>Lochkreis\s*)?(?P<d>[Ø⌀])?\s*(?P<nenn>\d+(?:[.,]\d+)?)"
                   r"(?:\s+(?P<tol>[A-Za-z]{1,2}\s*\d{1,2}))?\s*$")


def pruefmittel(toleranz: float | None, innen: bool, passung: str = "") -> str:
    if passung:
        return "Grenzlehrdorn " + passung if innen else "Grenzrachenlehre " + passung
    if toleranz is None:
        return "Sichtprüfung"
    if toleranz >= 0.2:
        return "Messschieber 0,02 mm" + (" (Innenmessschenkel)" if innen else "")
    if toleranz >= 0.02:
        return "Innenmessschraube 0,01 mm" if innen else "Bügelmessschraube 0,01 mm"
    return "Feinzeiger / Messuhr 0,001 mm mit Einstellmeister"


def merkmal_aus_text(text: str, innen: bool = False) -> dict | None:
    m = _MASS.match(text.strip())
    if not m:
        return None
    nenn = float(m.group("nenn").replace(",", "."))
    tol = (m.group("tol") or "").replace(" ", "")
    anzahl = int(m.group("anzahl")) if m.group("anzahl") else None
    if m.group("lk"):
        art = "Lochkreis"
    elif anzahl:
        art, innen = "Bohrungen", True
    elif m.group("d"):
        art = "Durchmesser"
    else:
        art = "Länge"
    if tol:
        innen = T.ist_bohrung(tol)
    abm = T.passung(nenn, tol) if tol else None
    if abm:
        unten, oben = abm
        quelle = T.QUELLE_286
    elif tol:
        unten = oben = None
        quelle = f"Passung {tol} nicht hinterlegt – Grenzmaße von Hand eintragen"
    else:
        a = T.allgemein(nenn)
        unten, oben = (-a, a) if a else (None, None)
        quelle = T.QUELLE_2768
    p = {"merkmal": text.strip(), "art": art, "nenn": nenn, "toleranz": tol or "ISO 2768-m",
         "min": None if unten is None else round(nenn + unten, 4), "max": None if oben is None else round(nenn + oben, 4),
         "innen": innen, "umfang": "100 %" if tol else "Erststück, dann 1 je Los",
         "ist": "", "ergebnis": OFFEN, "quelle": quelle, "bemerkung": ""}
    breite = None if unten is None else oben - unten
    p["pruefmittel"] = pruefmittel(breite, innen, tol)
    if anzahl:
        p["bemerkung"] = f"Anzahl {anzahl} Stück prüfen"
    return p


def aus_zeichnung(masse: list[dict]) -> list[dict]:
    """Prüfmerkmale aus den Maßtexten einer Zeichnung (jedes Maß einmal)."""
    out, gesehen = [], set()
    for mass in masse:
        text = mass["text"].strip()
        if text in gesehen:
            continue
        gesehen.add(text)
        p = merkmal_aus_text(text, mass.get("innen", False))
        if p:
            out.append(p)
    # Passmaße zuerst, dann Durchmesser, Längen
    rang = {"Durchmesser": 1, "Bohrungen": 2, "Lochkreis": 3, "Länge": 4}
    out.sort(key=lambda p: (p["toleranz"] == "ISO 2768-m", rang.get(p["art"], 9), -p["nenn"]))
    for i, p in enumerate(out, 1):
        p["id"] = f"PM{i}"
    return out


def grenz_text(p: dict) -> str:
    if p.get("min") is None or p.get("max") is None:
        return "–"
    return f"{f(p['min'], 6)} … {f(p['max'], 6)}"


def ergebnis(p: dict) -> str:
    """i. O. / n. i. O. aus Ist-Wert und Grenzmaßen; ohne Grenzen zählt die Handeingabe."""
    ist = zahl(p.get("ist"))
    if ist is None or p.get("min") is None or p.get("max") is None:
        return p.get("ergebnis") or OFFEN
    return IO if p["min"] - 1e-9 <= ist <= p["max"] + 1e-9 else NIO


def auswerten(plan: dict) -> dict:
    zahlen = {OFFEN: 0, IO: 0, NIO: 0}
    for p in plan.get("merkmale", []):
        p["ergebnis"] = ergebnis(p)
        zahlen[p["ergebnis"]] = zahlen.get(p["ergebnis"], 0) + 1
    gesamt = NIO if zahlen[NIO] else (OFFEN if zahlen[OFFEN] else IO)
    return {"zahlen": zahlen, "gesamt": gesamt}


def pruefmittelliste(plan: dict) -> list[tuple[str, int]]:
    """Prüfmittel mit Anzahl der Merkmale (S15)."""
    zaehler: dict[str, int] = {}
    for p in plan.get("merkmale", []):
        zaehler[p["pruefmittel"]] = zaehler.get(p["pruefmittel"], 0) + 1
    return sorted(zaehler.items(), key=lambda x: -x[1])


def naechste_id(plan: dict) -> str:
    vorhanden = {p["id"] for p in plan.get("merkmale", [])}
    i = 1
    while f"PM{i}" in vorhanden:
        i += 1
    return f"PM{i}"
