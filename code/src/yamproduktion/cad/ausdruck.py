"""Sichere Formeln für die Parameter-Tabelle (Lastenheft M28): d = 80, l = 2*d + 5, r = sqrt(a**2 + b**2).

Erlaubt sind Zahlen (Komma oder Punkt), Parameternamen, + − · / ** ( ), die Funktionen unten und
ber("welle", "d") für das Ergebnis der neuesten gespeicherten Berechnung einer Art (in deren Einheit,
umgerechnet in mm, wenn möglich). Kein eval – nur ein kleiner Baumdurchlauf.
"""
from __future__ import annotations

import ast
import math
import re

FUNKTIONEN = {
    "sqrt": math.sqrt, "sin": lambda g: math.sin(math.radians(g)), "cos": lambda g: math.cos(math.radians(g)),
    "tan": lambda g: math.tan(math.radians(g)), "abs": abs, "min": min, "max": max, "round": round,
    "ceil": math.ceil, "floor": math.floor,
}
KONSTANTEN = {"pi": math.pi}
_NAME = re.compile(r"^[A-Za-z_ÄÖÜäöüß][A-Za-z0-9_ÄÖÜäöüß]*$")


class AusdruckFehler(ValueError):
    pass


def gueltiger_name(name: str) -> bool:
    return bool(_NAME.match(name)) and name not in FUNKTIONEN and name not in KONSTANTEN and name != "ber"


def _vorbereiten(text: str) -> str:
    # deutsches Dezimalkomma zwischen Ziffern → Punkt (Argumenttrenner brauchen Leerzeichen oder Semikolon)
    text = re.sub(r"(?<=\d),(?=\d)", ".", str(text).strip())
    return text.replace(";", ",").replace("·", "*").replace("×", "*").replace("−", "-")


def namen_in(text: str) -> set[str]:
    try:
        baum = ast.parse(_vorbereiten(text), mode="eval")
    except SyntaxError:
        return set()
    return {n.id for n in ast.walk(baum) if isinstance(n, ast.Name)} - set(FUNKTIONEN) - set(KONSTANTEN) - {"ber"}


def berechnungsbezuege(text: str) -> list[tuple[str, str]]:
    """Alle ber("typ", "symbol")-Aufrufe in einer Formel."""
    try:
        baum = ast.parse(_vorbereiten(text), mode="eval")
    except SyntaxError:
        return []
    treffer = []
    for n in ast.walk(baum):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "ber" and len(n.args) == 2 \
                and all(isinstance(a, ast.Constant) and isinstance(a.value, str) for a in n.args):
            treffer.append((n.args[0].value, n.args[1].value))
    return treffer


def auswerten(text, werte: dict[str, float] | None = None, ber=None) -> float:
    """Wertet eine Formel aus. `ber(typ, symbol)` liefert Berechnungswerte (oder None = nicht verfügbar)."""
    if isinstance(text, (int, float)):
        return float(text)
    werte = werte or {}
    try:
        baum = ast.parse(_vorbereiten(text), mode="eval")
    except SyntaxError:
        raise AusdruckFehler(f"„{text}“ ist keine gültige Formel.") from None

    def knoten(n):
        if isinstance(n, ast.Expression):
            return knoten(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return float(n.value)
        if isinstance(n, ast.Name):
            if n.id in werte:
                return float(werte[n.id])
            if n.id in KONSTANTEN:
                return KONSTANTEN[n.id]
            raise AusdruckFehler(f"Unbekannter Parameter „{n.id}“.")
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd)):
            v = knoten(n.operand)
            return -v if isinstance(n.op, ast.USub) else v
        if isinstance(n, ast.BinOp):
            a, b = knoten(n.left), knoten(n.right)
            if isinstance(n.op, ast.Add):
                return a + b
            if isinstance(n.op, ast.Sub):
                return a - b
            if isinstance(n.op, ast.Mult):
                return a * b
            if isinstance(n.op, ast.Div):
                if b == 0:
                    raise AusdruckFehler(f"Division durch 0 in „{text}“.")
                return a / b
            if isinstance(n.op, ast.Pow):
                return a ** b
            if isinstance(n.op, ast.Mod):
                return a % b
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
            if n.func.id == "ber":
                if ber is None or len(n.args) != 2 or not all(isinstance(a, ast.Constant) for a in n.args):
                    raise AusdruckFehler('ber("art", "größe") braucht zwei Texte, z. B. ber("welle", "d").')
                wert = ber(n.args[0].value, n.args[1].value)
                if wert is None:
                    raise AusdruckFehler(f"Keine gespeicherte Berechnung „{n.args[0].value}“ mit „{n.args[1].value}“.")
                return float(wert)
            if n.func.id in FUNKTIONEN:
                return float(FUNKTIONEN[n.func.id](*[knoten(a) for a in n.args]))
            raise AusdruckFehler(f"Unbekannte Funktion „{n.func.id}“.")
        raise AusdruckFehler(f"„{text}“ enthält etwas, das keine Rechnung ist.")

    try:
        wert = knoten(baum)
    except (TypeError, OverflowError, ValueError) as exc:
        if isinstance(exc, AusdruckFehler):
            raise
        raise AusdruckFehler(f"„{text}“ lässt sich nicht rechnen: {exc}") from None
    if math.isnan(wert) or math.isinf(wert):
        raise AusdruckFehler(f"„{text}“ ergibt keinen gültigen Wert.")
    return wert


def tabelle_auswerten(zeilen: list[dict], ber=None) -> dict[str, float]:
    """Parameter-Tabelle [{name, formel}] in Abhängigkeitsreihenfolge auswerten; erkennt Kreise."""
    formeln = {}
    for z in zeilen:
        name = z["name"].strip()
        if not gueltiger_name(name):
            raise AusdruckFehler(f"„{name}“ ist kein gültiger Parametername (Buchstabe am Anfang, keine Leerzeichen).")
        if name in formeln:
            raise AusdruckFehler(f"Der Parameter „{name}“ ist doppelt.")
        formeln[name] = z["formel"]
    werte: dict[str, float] = {}
    offen = dict(formeln)
    while offen:
        fortschritt = False
        for name, formel in list(offen.items()):
            fehlend = namen_in(str(formel)) - set(werte)
            if fehlend - set(formeln):
                raise AusdruckFehler(f"{name}: unbekannter Parameter „{sorted(fehlend - set(formeln))[0]}“.")
            if not fehlend:
                try:
                    werte[name] = auswerten(formel, werte, ber)
                except AusdruckFehler as exc:
                    raise AusdruckFehler(f"{name}: {exc}") from None
                del offen[name]
                fortschritt = True
        if not fortschritt:
            raise AusdruckFehler("Die Parameter verweisen im Kreis aufeinander: " + ", ".join(sorted(offen)) + ".")
    return werte
