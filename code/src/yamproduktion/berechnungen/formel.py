"""Berechnung aus einer Buchformel (S20): Formel übernehmen, Werte mit Einheiten einsetzen, Quelle eintragen.

Die Formel wird nicht mit eval() ausgeführt, sondern Zeichen für Zeichen geprüft: erlaubt sind Zahlen,
Variablen, + − · / ^ und wenige Funktionen. Einheiten rechnet Pint mit; so fällt „N + m“ sofort auf.
"""
from __future__ import annotations

import ast
import math
import re
from dataclasses import dataclass, field

from ..einheiten import EinheitFehler, Q_, ureg
from .basis import Ergebnis, Groesse, Schritt, formatiere

TYP = "formel"
TITEL = "Formel aus Buch"
HINWEIS = "Formel aus einem Buch übernommen – Formel, Gültigkeitsbereich und Einheiten selbst prüfen."

_FUNKTIONEN = {"sqrt": lambda x: x ** 0.5, "wurzel": lambda x: x ** 0.5, "abs": abs,
               "sin": None, "cos": None, "tan": None, "exp": None, "ln": None, "log": None, "log10": None}
_KONSTANTEN = {"pi": math.pi, "π": math.pi, "e": math.e, "g": 9.81}


class FormelFehler(ValueError):
    pass


def normalisieren(text: str) -> str:
    """Schreibweisen aus Büchern in Python-Rechenzeichen: · × → *, ÷ : → /, ^ → **, ² ³ → **2, Komma → Punkt."""
    t = text.strip()
    for alt, neu in (("·", "*"), ("×", "*"), ("⋅", "*"), ("÷", "/"), ("−", "-"), ("–", "-"),
                     ("²", "**2"), ("³", "**3"), ("√", "sqrt"), ("^", "**")):
        t = t.replace(alt, neu)
    t = re.sub(r"(\d),(\d)", r"\1.\2", t)
    return t


def zerlegen(formel: str) -> tuple[str, ast.expr]:
    """„M_b = F*l/4“ → ("M_b", Ausdruck). Ohne linke Seite heißt das Ergebnis „x“."""
    t = normalisieren(formel)
    if t.count("=") > 1:
        raise FormelFehler("Bitte genau eine Gleichung eingeben, z. B. M_b = F * l / 4.")
    links, rechts = (t.split("=") if "=" in t else ("x", t))
    links = links.strip()
    if not links.isidentifier():
        raise FormelFehler(f"Links vom „=“ muss ein einzelner Name stehen, nicht „{links}“.")
    try:
        baum = ast.parse(rechts.strip(), mode="eval").body
    except SyntaxError as exc:
        raise FormelFehler(f"Die Formel ist nicht lesbar: {exc.msg}") from exc
    _pruefen(baum)
    return links, baum


def _pruefen(knoten):
    erlaubt = (ast.BinOp, ast.UnaryOp, ast.Constant, ast.Name, ast.Call, ast.Load,
               ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.USub, ast.UAdd)
    for k in ast.walk(knoten):
        if not isinstance(k, erlaubt):
            raise FormelFehler(f"„{type(k).__name__}“ ist in einer Formel nicht erlaubt.")
        if isinstance(k, ast.Constant) and not isinstance(k.value, (int, float)):
            raise FormelFehler("In der Formel sind nur Zahlen erlaubt, kein Text.")
        if isinstance(k, ast.Call):
            if not isinstance(k.func, ast.Name) or k.func.id not in _FUNKTIONEN or len(k.args) != 1 or k.keywords:
                raise FormelFehler("Erlaubte Funktionen: " + ", ".join(sorted(_FUNKTIONEN)) + " (je ein Wert).")


def variablen(formel: str) -> list[str]:
    """Die einzusetzenden Größen in der Reihenfolge ihres Auftretens."""
    _, baum = zerlegen(formel)
    namen = []
    for k in ast.walk(baum):
        if isinstance(k, ast.Name) and k.id not in _FUNKTIONEN and k.id not in _KONSTANTEN and k.id not in namen:
            namen.append(k.id)
    funktionen = {k.func.id for k in ast.walk(baum) if isinstance(k, ast.Call)}
    return [n for n in namen if n not in funktionen]


def _rechnen(k, werte):
    if isinstance(k, ast.Constant):
        return k.value
    if isinstance(k, ast.Name):
        if k.id in werte:
            return werte[k.id]
        if k.id in _KONSTANTEN:
            return _KONSTANTEN[k.id]
        raise FormelFehler(f"Für „{k.id}“ fehlt ein Wert.")
    if isinstance(k, ast.UnaryOp):
        w = _rechnen(k.operand, werte)
        return -w if isinstance(k.op, ast.USub) else w
    if isinstance(k, ast.BinOp):
        a, b = _rechnen(k.left, werte), _rechnen(k.right, werte)
        op = type(k.op)
        if op is ast.Pow:
            if hasattr(b, "magnitude"):
                if not b.dimensionless:
                    raise FormelFehler("Ein Exponent muss ohne Einheit sein.")
                b = b.to("").magnitude
            return a ** b
        return {ast.Add: lambda: a + b, ast.Sub: lambda: a - b, ast.Mult: lambda: a * b,
                ast.Div: lambda: a / b}[op]()
    if isinstance(k, ast.Call):
        name = k.func.id
        w = _rechnen(k.args[0], werte)
        if _FUNKTIONEN[name]:
            return _FUNKTIONEN[name](w)
        if hasattr(w, "magnitude"):
            if not w.dimensionless:
                raise FormelFehler(f"{name}() braucht einen Wert ohne Einheit (Winkel in rad oder °).")
            w = w.to("").magnitude
        f = {"ln": math.log, "log": math.log, "log10": math.log10}.get(name) or getattr(math, name)
        return f(w)
    raise FormelFehler("Unbekannter Formelteil.")


@dataclass
class FormelEingaben:
    formel: str
    werte: dict = field(default_factory=dict)     # Name → [Zahl, Einheit]
    einheit: str = ""                             # gewünschte Ergebniseinheit (leer: wie berechnet)
    name: str = ""                                # Bezeichnung, z. B. „Biegemoment Wellenmitte“
    quelle: str = ""                              # „Roloff/Matek · 11 Achsen und Wellen · S. 312“


def berechne(e: FormelEingaben) -> Ergebnis:
    symbol, baum = zerlegen(e.formel)
    namen = variablen(e.formel)
    werte, eingaben = {}, []
    for n in namen:
        if n not in e.werte or e.werte[n][0] in (None, ""):
            raise FormelFehler(f"Für „{n}“ fehlt ein Wert.")
        zahl, einheit = e.werte[n]
        try:
            werte[n] = Q_(float(zahl), _einheit(einheit))
        except (EinheitFehler, ValueError, Exception) as exc:
            raise FormelFehler(f"„{einheit}“ bei {n} ist keine bekannte Einheit.") from exc
        eingaben.append(Groesse(n, n, float(zahl), einheit or "–"))
    try:
        erg = _rechnen(baum, werte)
    except FormelFehler:
        raise
    except ZeroDivisionError as exc:
        raise FormelFehler("Division durch null – ein Wert ist 0.") from exc
    except Exception as exc:                    # meist Pint: Einheiten passen nicht zusammen
        raise FormelFehler(f"Die Einheiten passen nicht zusammen: {exc}") from exc
    if not hasattr(erg, "magnitude"):
        erg = Q_(erg, "")
    if e.einheit.strip():
        try:
            erg = erg.to(_einheit(e.einheit))
        except Exception as exc:
            raise FormelFehler(f"Das Ergebnis lässt sich nicht in „{e.einheit}“ umrechnen "
                               f"(berechnet: {erg.units:~P}).") from exc
    else:
        erg = erg.to_reduced_units()
    einheit_text = e.einheit.strip().replace("*", "·") or (f"{erg.units:~P}" if not erg.dimensionless else "–")
    rechts = e.formel.split("=", 1)[-1].strip()
    eingesetzt = rechts
    for n in sorted(namen, key=len, reverse=True):
        zahl, einheit = e.werte[n]
        eingesetzt = re.sub(rf"(?<![\w]){re.escape(n)}(?![\w])", f"{formatiere(float(zahl))} {einheit}".strip(),
                            eingesetzt)
    g = Groesse(symbol, e.name or symbol, float(erg.magnitude), einheit_text)
    return Ergebnis(
        titel=e.name or f"Formel {symbol}", typ=TYP, eingaben=eingaben,
        schritte=[Schritt(e.name or symbol, f"{symbol} = {rechts}", f"{symbol} = {eingesetzt}", g)],
        ergebnisse=[g], quellen=[e.quelle] if e.quelle else [],
        hinweise=[HINWEIS], unbelegt=[] if e.quelle else [f"{symbol} = {rechts} (ohne Quellenangabe)"])


def _einheit(text: str) -> str:
    t = (text or "").strip().replace("·", "*").replace("²", "^2").replace("³", "^3").replace("–", "")
    t = t.replace("°", "degree") if t == "°" else t
    ureg.parse_units(t) if t else None        # wirft bei Unsinn
    return t


def aus_dict(eingaben: dict) -> FormelEingaben:
    return FormelEingaben(**eingaben)
