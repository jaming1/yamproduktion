"""TRIZ-Wissen: 39 technische Parameter, 40 innovative Prinzipien, Widerspruchsmatrix, Trennungsprinzipien.

Die Daten liegen in daten/triz.json mit Quellenangabe. Die Matrixwerte werden nur
nachgeschlagen, nie „erraten“ (Lastenheft N6).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_DATEI = Path(__file__).parent / "daten" / "triz.json"


@lru_cache(maxsize=1)
def _daten() -> dict:
    return json.loads(_DATEI.read_text(encoding="utf-8"))


def quelle() -> str:
    return _daten()["quelle"]


def hinweis() -> str:
    return _daten()["hinweis"]


def parameter() -> list[dict]:
    """Die 39 technischen Parameter: [{nr, name, name_en}]."""
    return _daten()["parameter"]


def parameter_name(nr: int) -> str:
    return parameter()[nr - 1]["name"]


def prinzipien() -> list[dict]:
    """Die 40 innovativen Prinzipien: [{nr, name, beschreibung, name_en}]."""
    return _daten()["prinzipien"]


def prinzip(nr: int) -> dict:
    if not 1 <= nr <= 40:
        raise ValueError(f"Prinzip {nr} gibt es nicht (1 bis 40).")
    return prinzipien()[nr - 1]


def trennungsprinzipien() -> list[dict]:
    """Für physikalische Widersprüche: [{id, name, frage, prinzipien}]."""
    return _daten()["trennungsprinzipien"]


def empfehlung(verbessern: int, verschlechtern: int) -> list[int]:
    """Prinzipien aus der Widerspruchsmatrix in der Reihenfolge der Tabelle.

    Leere Liste, wenn die Zelle leer ist oder beide Parameter gleich sind
    (dann liegt ein physikalischer Widerspruch vor → Trennungsprinzipien).
    """
    for nr in (verbessern, verschlechtern):
        if not 1 <= nr <= 39:
            raise ValueError(f"Parameter {nr} gibt es nicht (1 bis 39).")
    return list(_daten()["matrix"].get(f"{verbessern}-{verschlechtern}", []))
