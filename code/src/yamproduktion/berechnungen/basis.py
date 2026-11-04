"""Gemeinsamer Aufbau jeder Berechnung (Lastenheft M16).

Jede Berechnung liefert: Eingaben, Rechenschritte mit Formel,
Ergebnisse, Prüfungen (erfüllt / nicht erfüllt) und die Quelle.
So bleibt jedes Ergebnis nachvollziehbar (N6).
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict


@dataclass
class Groesse:
    symbol: str
    name: str
    wert: float
    einheit: str

    def text(self, stellen: int = 4) -> str:
        return f"{self.symbol} = {formatiere(self.wert, stellen)} {self.einheit}".strip()


@dataclass
class Schritt:
    titel: str
    formel: str          # Formel in Textform, z. B. "A = 2·P / (ρ·cp·η·v³)"
    einsetzen: str       # Formel mit eingesetzten Zahlen
    ergebnis: Groesse


@dataclass
class Pruefung:
    titel: str
    bedingung: str       # z. B. "cp ≤ 16/27 (Betz-Grenze)"
    erfuellt: bool
    hinweis: str = ""


@dataclass
class Ergebnis:
    titel: str
    typ: str
    eingaben: list[Groesse]
    schritte: list[Schritt]
    ergebnisse: list[Groesse]
    pruefungen: list[Pruefung] = field(default_factory=list)
    quellen: list[str] = field(default_factory=list)
    hinweise: list[str] = field(default_factory=list)
    # Zusätzliche Tabellen: [{"titel", "spalten": [...], "zeilen": [[...], ...]}]
    tabellen: list[dict] = field(default_factory=list)
    # Optionales Diagramm: {"titel", "x_name", "y_name", "x": [...], "y": [...]}
    diagramm: dict | None = None
    # Gleichungen/Werte ohne gesicherte Quelle (Lastenheft N6: belegt und unbelegt getrennt)
    unbelegt: list[str] = field(default_factory=list)

    @property
    def alles_erfuellt(self) -> bool:
        return all(p.erfuellt for p in self.pruefungen)

    def als_dict(self) -> dict:
        return asdict(self)

    def ergebnis(self, symbol: str) -> Groesse:
        for g in self.ergebnisse:
            if g.symbol == symbol:
                return g
        raise KeyError(symbol)


def formatiere(wert: float, stellen: int = 4) -> str:
    """Deutsche Zahlendarstellung mit `stellen` gültigen Ziffern (Komma, Tausenderpunkt)."""
    if wert == 0:
        return "0"
    if abs(wert) >= 10 ** stellen:
        return f"{wert:,.0f}".replace(",", ".")
    text = f"{wert:.{stellen}g}"
    if "e" in text:  # sehr kleine Zahlen
        text = f"{wert:.{stellen}f}".rstrip("0").rstrip(".")
        if text in ("0", "-0"):
            text = "< " + f"{10 ** -stellen:.{stellen}f}"
    return text.replace(".", ",")


@dataclass
class Feld:
    """Beschreibung eines Eingabefelds für die Oberfläche."""
    attr: str
    name: str
    einheit: str            # Pint-Einheit oder "" (ohne Einheit)
    minimum: float = 0.0
    maximum: float = 1e9
    schritt: float = 1.0
    stellen: int = 2
    tipp: str = ""
    auswahl: tuple[str, ...] = ()   # nicht leer → Auswahlliste statt Zahl

    @property
    def anzeige_einheit(self) -> str:
        return {"kg/m^3": "kg/m³", "m^2": "m²", "N*m": "N·m", "deg": "°", "um": "µm", "kg*m^2": "kg·m²"}.get(self.einheit, self.einheit)
