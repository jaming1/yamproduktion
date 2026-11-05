"""Arabische Normalisierung für Suche und Anzeige.

Suche: Taschkil, Tatweel und Schreibvarianten (Hamza, Alif, Ta marbuta,
Alif maqsura) werden vereinheitlicht, damit „الصبر“ auch „الصَّبْر“ findet.
Anzeige: indische Ziffern ٠–٩ werden immer zu 0–9.
"""
import re

# Taschkil, Koran-Zeichen und Tatweel: werden bei der Suche entfernt.
_DROP = set(range(0x064B, 0x0660)) | {0x0670, 0x0640} | set(range(0x06D6, 0x06EE))

_MAP = {
    "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ٲ": "ا", "ٳ": "ا",
    "ة": "ه", "ى": "ي", "ی": "ي", "ئ": "ي", "ؤ": "و", "ک": "ك",
}
for _i in range(10):
    _MAP[chr(0x0660 + _i)] = str(_i)  # ٠–٩
    _MAP[chr(0x06F0 + _i)] = str(_i)  # ۰–۹ (persisch)

_DIGITS = str.maketrans({chr(0x0660 + i): str(i) for i in range(10)} |
                        {chr(0x06F0 + i): str(i) for i in range(10)})

_TAG = re.compile(r"<[^>]+>")
_NON_WORD = re.compile(r"[^\w]+")


def western_digits(text):
    """٠–٩ → 0–9 (Pflicht für jede Anzeige)."""
    return text.translate(_DIGITS) if text else text


def strip_tags(text):
    return _TAG.sub(" ", text) if text else ""


def normalize_char(ch):
    """Ein Zeichen normalisieren; '' heißt: Zeichen fällt weg."""
    if ord(ch) in _DROP:
        return ""
    ch = _MAP.get(ch, ch)
    return ch.lower()


def normalize(text):
    """Text für den Suchindex: ohne Tags und Taschkil, nur Wörter, Leerzeichen getrennt."""
    if not text:
        return ""
    out = "".join(normalize_char(c) for c in strip_tags(text))
    return _NON_WORD.sub(" ", out).strip()


def normalize_with_map(text):
    """Normalisierte Fassung plus Positionsliste zurück in den Originaltext.

    Wird für die hervorgehobene Trefferanzeige gebraucht: Treffer werden im
    normalisierten Text gefunden und im Original markiert.
    """
    norm, pos = [], []
    for i, c in enumerate(text):
        n = normalize_char(c)
        if not n:
            continue
        if not (n.isalnum() or n == "_"):
            if norm and norm[-1] == " ":
                continue  # mehrere Trennzeichen wie eines behandeln (wie im Suchindex)
            n = " "
        for ch in n:
            norm.append(ch)
            pos.append(i)
    return "".join(norm), pos


def query_terms(query):
    """Suchanfrage in Begriffe zerlegen; Text in Anführungszeichen bleibt eine Phrase."""
    terms = []
    for phrase, word in re.findall(r'"([^"]+)"|(\S+)', query or ""):
        n = normalize(phrase or word)
        if n:
            terms.append(n)
    return terms


def word_variants(word):
    """Ein Wort mit den häufigsten angehängten Vorsilben (و ف ب ك ل),
    damit „الصبر“ auch „والصبر“, „بالصبر“ und „للصبر“ findet."""
    forms = {word}
    if word.startswith("ال") and len(word) > 3:
        forms |= {"ب" + word, "ك" + word, "لل" + word[2:]}
    elif len(word) >= 2:
        forms |= {"ب" + word, "ل" + word, "ك" + word}
    forms |= {p + f for f in list(forms) for p in ("و", "ف")}
    return sorted(forms)


def fts_query(terms):
    """Begriffe als sichere FTS5-Abfrage: alle Begriffe müssen vorkommen,
    einzelne Wörter auch mit Vorsilben, Phrasen genau."""
    groups = []
    for t in terms:
        t = t.replace('"', "")
        if " " in t:
            groups.append('"' + t + '"')
        else:
            groups.append("(" + " OR ".join('"' + v + '"' for v in word_variants(t)) + ")")
    return " AND ".join(groups)
