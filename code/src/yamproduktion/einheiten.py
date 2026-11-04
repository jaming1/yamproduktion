"""Einheiten: jede Zahl im Programm hat eine Einheit (Lastenheft M6).

Wir nutzen Pint, damit Umrechnungen und unverträgliche Einheiten
zuverlässig erkannt werden, statt das selbst nachzubauen.
"""
from __future__ import annotations

import pint

ureg = pint.UnitRegistry()
Q_ = ureg.Quantity


class EinheitFehler(ValueError):
    """Verständlicher Fehler für falsche oder unverträgliche Einheiten."""


def pruefe_einheit(text: str) -> str:
    """Prüft eine Einheit wie 'kW', 'm/s' oder 'kg'. Leer = ohne Einheit.

    Gibt die Einheit unverändert zurück oder wirft EinheitFehler.
    """
    text = (text or "").strip()
    if not text or text == "-":
        return ""
    try:
        ureg.parse_units(text)
    except Exception as exc:  # Pint wirft verschiedene Fehlertypen
        raise EinheitFehler(
            f"„{text}“ ist keine bekannte Einheit. Beispiele: kW, m/s, mm, kg, N·m → N*m"
        ) from exc
    return text


def zahl_lesen(text: str) -> float | None:
    """Liest Zahlen in deutscher oder englischer Schreibweise: '5,5', '1.000,5', '5.5'. Leer = None."""
    text = (text or "").strip().replace(" ", "")
    if not text:
        return None
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    return float(text)  # wirft ValueError bei Unsinn


def umrechnen(wert: float, von: str, nach: str) -> float:
    """Rechnet einen Wert zwischen verträglichen Einheiten um."""
    try:
        return Q_(wert, von).to(nach).magnitude
    except pint.DimensionalityError as exc:
        raise EinheitFehler(
            f"{von} lässt sich nicht in {nach} umrechnen – die Einheiten passen nicht zusammen."
        ) from exc
