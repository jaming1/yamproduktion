"""Werkstoffdatenbank (Lastenheft M26): Festigkeit, E-Modul, Dichte für gängige Werkstoffe."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_DATEI = Path(__file__).parent / "daten" / "werkstoffe.json"


@lru_cache(maxsize=1)
def _daten() -> dict:
    return json.loads(_DATEI.read_text(encoding="utf-8"))


def alle() -> list[dict]:
    return _daten()["werkstoffe"]


def hinweis() -> str:
    return _daten()["hinweis"]


def suchen(text: str) -> list[dict]:
    t = text.strip().lower()
    if not t:
        return alle()
    return [w for w in alle() if any(t in str(w[k]).lower() for k in ("name", "nr", "gruppe", "zustand", "verwendung"))]


def werkstoff(name: str, zustand: str | None = None) -> dict:
    for w in alle():
        if w["name"] == name and (zustand is None or zustand in w["zustand"]):
            return w
    raise KeyError(f"Werkstoff „{name}“ ist nicht in der Datenbank.")


def bezeichnung(w: dict) -> str:
    """Eindeutige Anzeige, z. B. „42CrMo4 · +QT (vergütet), 16–40 mm“."""
    return f"{w['name']} · {w['zustand']}"


def auswahl(gruppen: tuple[str, ...] = ()) -> tuple[str, ...]:
    return tuple(bezeichnung(w) for w in alle() if not gruppen or w["gruppe"] in gruppen)


def nach_bezeichnung(text: str) -> dict:
    for w in alle():
        if bezeichnung(w) == text:
            return w
    raise KeyError(f"Werkstoff „{text}“ ist nicht in der Datenbank.")
