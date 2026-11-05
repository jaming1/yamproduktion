"""Lokale Bibliothek: Bücher (PDF), Text je Seite, Kapitel, Volltextsuche (SQLite FTS5) und Fragen (M50–M52, S19).

Ordner:  <bibliothek>/bibliothek.sqlite   – Text und Suchindex
         <bibliothek>/buecher/B001.pdf     – Kopie des Scans (bei Texterkennung: durchsuchbares PDF)
Nichts davon gelangt in die Projektdatei, die technische Dokumentation oder einen Export (M52).
"""
from __future__ import annotations

import re
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from . import texterkennung as T

STANDARD_ORDNER = Path.home() / "Documents" / "YamProduktion" / "Bibliothek"
HINWEIS_FRAGE = "Vorschlag, nicht geprüft – Fundstellen selbst im Buch nachlesen."

SCHEMA = """
CREATE TABLE IF NOT EXISTS buch (
    id INTEGER PRIMARY KEY AUTOINCREMENT, kurz TEXT NOT NULL UNIQUE, titel TEXT NOT NULL,
    autor TEXT NOT NULL DEFAULT '', datei TEXT NOT NULL, seiten INTEGER NOT NULL DEFAULT 0,
    versatz INTEGER NOT NULL DEFAULT 0, erkannt TEXT NOT NULL DEFAULT '', importiert TEXT NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS seite USING fts5(
    text, kapitel, buch_id UNINDEXED, nr UNINDEXED, tokenize = 'unicode61 remove_diacritics 2'
);
"""

# Häufige deutsche Wörter, die in einer Frage nichts zur Suche beitragen
STOPP = set("""
aber alle als also am an auch auf aus bei beim bin bis bitte da damit dann das dass dem den denn der des die
dies diese dieser dieses doch dort du durch ein eine einem einen einer eines er es etwa für gibt habe haben hat
ich ihr im in ist ja je kann kann man kein mal man mehr mit muss nach nicht noch nur ob oder ohne sein sich sie
sind so soll über um und uns unter viel vom von vor war was welche welcher welches wenn wer werden wie wieviel
wieso wird wo zu zum zur zwischen berechnet berechnen berechnung rechnen man welchen groß große großen
""".split())


class BibliothekFehler(Exception):
    pass


@dataclass
class Buch:
    id: int
    kurz: str
    titel: str
    autor: str
    datei: str
    seiten: int
    versatz: int
    erkannt: str          # "Textebene", "OCRmyPDF", "Tesseract", "ohne Text"
    importiert: str

    def buchseite(self, nr: int) -> int:
        """Gedruckte Seitenzahl aus der PDF-Seite (1-basiert)."""
        return nr - self.versatz


@dataclass
class Treffer:
    buch: Buch
    nr: int               # PDF-Seite, 1-basiert
    kapitel: str
    ausschnitt: str       # mit <b>…</b> um die Fundwörter
    rang: float

    @property
    def fundstelle(self) -> str:
        s = self.buch.buchseite(self.nr)
        teile = [self.buch.titel, self.kapitel, f"S. {s}" + (f" (PDF {self.nr})" if s != self.nr else "")]
        return " · ".join(t for t in teile if t)


def _stamm(wort: str) -> str:
    """Sehr einfache Grundform für die Suche (Wellen → Well*, Lagers → Lager*)."""
    w = wort.lower()
    for endung in ("ungen", "ung", "en", "er", "es", "e", "n", "s"):
        if len(w) - len(endung) >= 4 and w.endswith(endung):
            return w[: -len(endung)]
    return w


def suchausdruck(text: str, alle: bool = True) -> str:
    """Benutzereingabe → FTS5-Ausdruck. Wörter mit Präfixsuche, „…“ als Wortgruppe."""
    teile = []
    for phrase in re.findall(r'"([^"]+)"', text):
        teile.append('"' + phrase.replace('"', "") + '"')
    rest = re.sub(r'"[^"]*"', " ", text)
    for wort in re.findall(r"[\wÄÖÜäöüß]+", rest):
        if len(wort) >= 2:
            teile.append(f'"{wort}"*')
    return (" AND " if alle else " OR ").join(teile)


def kapitel_aus_text(text: str) -> str | None:
    """Kapitelüberschrift am Seitenanfang, z. B. „6.2 Wellen und Achsen“."""
    for zeile in text.splitlines()[:4]:
        z = zeile.strip()
        m = re.match(r"^(\d{1,2}(?:\.\d{1,2}){0,3})\.?\s+([A-ZÄÖÜ][^\d]{2,60})$", z)
        if m:
            return f"{m.group(1)} {m.group(2).strip()}"
    return None


class Bibliothek:
    def __init__(self, ordner: str | Path | None = None):
        self.ordner = Path(ordner) if ordner else STANDARD_ORDNER
        (self.ordner / "buecher").mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.ordner / "bibliothek.sqlite")
        self._db.executescript(SCHEMA)
        self._db.commit()

    def schliessen(self):
        self._db.close()

    # ---------- Bücher
    def buecher(self) -> list[Buch]:
        return [Buch(*z) for z in self._db.execute("SELECT * FROM buch ORDER BY titel")]

    def buch(self, id_: int) -> Buch:
        z = self._db.execute("SELECT * FROM buch WHERE id=?", (id_,)).fetchone()
        if not z:
            raise BibliothekFehler("Dieses Buch gibt es nicht mehr.")
        return Buch(*z)

    def pfad(self, buch: Buch) -> Path:
        return self.ordner / "buecher" / buch.datei

    def importieren(self, quelle: str | Path | list, titel: str = "", autor: str = "",
                    fortschritt: Callable[[str], None] | None = None, ocr: bool = True) -> Buch:
        """PDF oder Bilder (eine Liste = ein Buch) übernehmen, Text je Seite lesen, bei Bedarf Texterkennung."""
        melde = fortschritt or (lambda _t: None)
        quellen = [Path(q) for q in (quelle if isinstance(quelle, (list, tuple)) else [quelle])]
        for q in quellen:
            if not q.exists():
                raise BibliothekFehler(f"{q.name} wurde nicht gefunden.")
        nr = (self._db.execute("SELECT MAX(id) FROM buch").fetchone()[0] or 0) + 1
        kurz = f"B{nr:03d}"
        ziel = self.ordner / "buecher" / f"{kurz}.pdf"
        if len(quellen) == 1 and quellen[0].suffix.lower() == ".pdf":
            shutil.copy2(quellen[0], ziel)
        else:
            melde("Bilder zu einem PDF zusammenfügen …")
            T.bilder_zu_pdf(quellen, ziel)
        texte = T.pdf_text(ziel)
        art = "Textebene"
        if ocr and T.braucht_ocr(texte):
            melde("Texterkennung läuft – das dauert je Seite einige Sekunden …")
            erg = T.erkennen(ziel, melde)
            if erg:
                texte, art = erg
            else:
                art = "ohne Text"
        elif T.braucht_ocr(texte):
            art = "ohne Text"
        titel = titel.strip() or quellen[0].stem.replace("_", " ")
        kapitel = T.pdf_kapitel(ziel, len(texte))
        cur = self._db.execute("INSERT INTO buch(kurz, titel, autor, datei, seiten, erkannt, importiert) "
                               "VALUES(?,?,?,?,?,?,?)", (kurz, titel, autor, ziel.name, len(texte), art,
                                                         datetime.now().isoformat(timespec="seconds")))
        bid = cur.lastrowid
        aktuell = ""
        for i, text in enumerate(texte, 1):
            aktuell = kapitel.get(i) or kapitel_aus_text(text) or aktuell
            self._db.execute("INSERT INTO seite(text, kapitel, buch_id, nr) VALUES(?,?,?,?)", (text, aktuell, bid, i))
        self._db.commit()
        melde(f"{titel}: {len(texte)} Seiten übernommen ({art}).")
        return self.buch(bid)

    def aendern(self, id_: int, titel: str | None = None, autor: str | None = None, versatz: int | None = None):
        b = self.buch(id_)
        self._db.execute("UPDATE buch SET titel=?, autor=?, versatz=? WHERE id=?",
                         (b.titel if titel is None else titel.strip() or b.titel,
                          b.autor if autor is None else autor.strip(), b.versatz if versatz is None else int(versatz),
                          id_))
        self._db.commit()
        return self.buch(id_)

    def loeschen(self, id_: int):
        b = self.buch(id_)
        self._db.execute("DELETE FROM seite WHERE buch_id=?", (id_,))
        self._db.execute("DELETE FROM buch WHERE id=?", (id_,))
        self._db.commit()
        self.pfad(b).unlink(missing_ok=True)

    def seitentext(self, buch_id: int, nr: int) -> tuple[str, str]:
        z = self._db.execute("SELECT text, kapitel FROM seite WHERE buch_id=? AND nr=?", (buch_id, nr)).fetchone()
        return (z[0], z[1]) if z else ("", "")

    def ohne_text(self, buch_id: int) -> int:
        return self._db.execute("SELECT COUNT(*) FROM seite WHERE buch_id=? AND length(trim(text)) < 20",
                                (buch_id,)).fetchone()[0]

    # ---------- Suche (M50, M51)
    def suchen(self, text: str, buch_id: int | None = None, grenze: int = 50, alle: bool = True) -> list[Treffer]:
        ausdruck = suchausdruck(text, alle)
        if not ausdruck:
            return []
        sql = ("SELECT buch_id, nr, kapitel, snippet(seite, 0, '<b>', '</b>', ' … ', 24), bm25(seite) "
               "FROM seite WHERE seite MATCH ?")
        args: list = [ausdruck]
        if buch_id:
            sql += " AND buch_id=?"
            args.append(buch_id)
        sql += " ORDER BY bm25(seite) LIMIT ?"
        args.append(grenze)
        try:
            zeilen = self._db.execute(sql, args).fetchall()
        except sqlite3.OperationalError as exc:
            raise BibliothekFehler(f"Die Suche „{text}“ ist nicht lesbar: {exc}") from exc
        buecher = {b.id: b for b in self.buecher()}
        return [Treffer(buecher[int(b)], int(nr), k, a.replace("\n", " "), r) for b, nr, k, a, r in zeilen
                if int(b) in buecher]

    def frage(self, frage: str, grenze: int = 5) -> tuple[list[str], list[Treffer]]:
        """S19 offline: Stichwörter der Frage (ohne Füllwörter, Grundform) → die besten Fundstellen."""
        woerter = [w for w in re.findall(r"[\wÄÖÜäöüß]+", frage) if w.lower() not in STOPP and len(w) >= 3]
        staemme = list(dict.fromkeys(_stamm(w) for w in woerter))
        if not staemme:
            return [], []
        treffer = self.suchen(" ".join(staemme), grenze=grenze, alle=True)
        if len(treffer) < grenze and len(staemme) > 1:       # nicht alle Wörter auf einer Seite → jedes Wort zählt
            gesehen = {(t.buch.id, t.nr) for t in treffer}
            for t in self.suchen(" ".join(staemme), grenze=grenze * 3, alle=False):
                if (t.buch.id, t.nr) not in gesehen and len(treffer) < grenze:
                    treffer.append(t)
                    gesehen.add((t.buch.id, t.nr))
        return staemme, treffer
