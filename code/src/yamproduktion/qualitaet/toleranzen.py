"""Grenzmaße aus ISO 286 (Passungen) und ISO 2768-m (Allgemeintoleranzen).

Tabellenwerte aus dem Gedächtnis übernommen – „Norm, ungeprüft“: vor der Fertigung mit der Norm
oder einem Tabellenbuch vergleichen. Nur Nennmaße bis 500 mm.
"""
from __future__ import annotations

import re

QUELLE_286 = "ISO 286 (Norm, ungeprüft)"
QUELLE_2768 = "ISO 2768-m (Norm, ungeprüft)"

# Nennmaßbereiche „über … bis“ in mm (obere Grenze gehört zum Bereich)
_BIS = (3, 6, 10, 18, 30, 50, 80, 120, 180, 250, 315, 400, 500)

# Grundtoleranzen IT in µm
IT = {
    5: (4, 5, 6, 8, 9, 11, 13, 15, 18, 20, 23, 25, 27),
    6: (6, 8, 9, 11, 13, 16, 19, 22, 25, 29, 32, 36, 40),
    7: (10, 12, 15, 18, 21, 25, 30, 35, 40, 46, 52, 57, 63),
    8: (14, 18, 22, 27, 33, 39, 46, 54, 63, 72, 81, 89, 97),
    9: (25, 30, 36, 43, 52, 62, 74, 87, 100, 115, 130, 140, 155),
    10: (40, 48, 58, 70, 84, 100, 120, 140, 160, 185, 210, 230, 250),
    11: (60, 75, 90, 110, 130, 160, 190, 220, 250, 290, 320, 360, 400),
}
# Grundabmaße Welle in µm: unteres Abmaß ei (k, m, n, p) bzw. oberes Abmaß es (f, g, h)
_EI_WELLE = {
    "k": (0, 1, 1, 1, 2, 2, 2, 3, 3, 4, 4, 4, 5),
    "m": (2, 4, 6, 7, 8, 9, 11, 13, 15, 17, 20, 21, 23),
    "n": (4, 8, 10, 12, 15, 17, 20, 23, 27, 31, 34, 37, 40),
    "p": (6, 12, 15, 18, 22, 26, 32, 37, 43, 50, 56, 62, 68),
}
_ES_WELLE = {
    "f": (-6, -10, -13, -16, -20, -25, -30, -36, -43, -50, -56, -62, -68),
    "g": (-2, -4, -5, -6, -7, -9, -10, -12, -14, -15, -17, -18, -20),
    "h": (0,) * 13,
}
# ISO 2768-m: Grenzabmaße für Längenmaße in mm
_ALLGEMEIN = ((0.5, None), (6, 0.1), (30, 0.2), (120, 0.3), (400, 0.5), (1000, 0.8), (2000, 1.2), (4000, 2.0))


def bereich(nenn: float) -> int | None:
    if nenn <= 0 or nenn > _BIS[-1]:
        return None
    for i, b in enumerate(_BIS):
        if nenn <= b:
            return i
    return None


def allgemein(nenn: float) -> float | None:
    """± Grenzabmaß nach ISO 2768-m in mm (unter 0,5 mm: Angabe am Maß nötig)."""
    for bis, abmass in _ALLGEMEIN:
        if nenn <= bis:
            return abmass
    return None


def passung(nenn: float, kurz: str) -> tuple[float, float] | None:
    """Abmaße (unten, oben) in mm für z. B. „k6“, „H7“, „js6“; None wenn nicht hinterlegt."""
    t = re.fullmatch(r"\s*([A-Za-z]{1,2})\s*(\d{1,2})\s*", kurz or "")
    i = bereich(nenn)
    if not t or i is None:
        return None
    feld, grad = t.group(1), int(t.group(2))
    if grad not in IT:
        return None
    it = IT[grad][i]
    if feld in ("js", "JS"):
        return -it / 2000, it / 2000
    if feld == "H":
        return 0.0, it / 1000
    if feld in ("F", "G"):                      # Bohrung: EI = −es der Welle
        ei = -_ES_WELLE[feld.lower()][i]
        return ei / 1000, (ei + it) / 1000
    if feld in _ES_WELLE:
        es = _ES_WELLE[feld][i]
        return (es - it) / 1000, es / 1000
    if feld in _EI_WELLE:
        if feld == "k" and not 4 <= grad <= 7 and i > 0:
            return None                         # k außerhalb IT4…IT7: ei = 0 – nicht hinterlegt
        ei = _EI_WELLE[feld][i]
        return ei / 1000, (ei + it) / 1000
    return None


def ist_bohrung(kurz: str) -> bool:
    return bool(kurz) and kurz.strip()[:1].isupper()
