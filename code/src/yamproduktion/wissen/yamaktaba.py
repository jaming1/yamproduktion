"""Anschluss an Yamaktaba (Yamines Bibliotheks-App, Ordner „ashamila“): Wissen suchen und Projekte archivieren.

Yamaktaba bringt ihre eigene Python-Schnittstelle mit (Paket `ashamila` in <ordner>/code/src). YamProduktion lädt
genau diese Schnittstelle – so passt der Zugriff immer zur Version der Datenbank.

- Suchen und Lesen: nur lesend (SQLite `mode=ro`), stört die laufende App nicht.
- Archivieren: Unterlagen eines Projekts werden eigene Bücher in Yamaktaba (Kategorie „99 Projekte & Medien“,
  Herkunft „yamproduktion“, je Projekt eine Sammlung); die Dateien liegen im Bibliotheksordner von Yamaktaba.
Buchscans aus Yamaktaba gelangen nie in eine YamProduktion-Projektdatei oder einen Export (M52).
"""
from __future__ import annotations

import hashlib
import importlib
import os
import re
import shutil
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

STANDARD_ORDNER = Path.home() / "Documents" / "ClaudeCodeFolder" / "Ashamila" / "ashamila"
APP_SKRIPT = Path("/Applications/Yamaktaba.app/Contents/MacOS/Yamaktaba")
ARCHIV_KATEGORIE = "99 Projekte & Medien"
ERSATZ_KATEGORIE = "YamProduktion"
QUELLE = "yamproduktion"
ARCHIV_ORDNER = "YamProduktion"            # unter dem Bibliotheksordner von Yamaktaba
SPRACHEN = {"": "alle Sprachen", "de": "Deutsch", "en": "Englisch", "fr": "Französisch", "ar": "Arabisch"}


class YamaktabaFehler(Exception):
    pass


def ordner_finden(einstellung: str | Path | None = None) -> Path | None:
    """Ordner „ashamila“ finden: Einstellung, dann der Ort aus der installierten App, dann der Standardort."""
    kandidaten = [Path(einstellung)] if einstellung else []
    try:
        m = re.search(r'HOME_DIR="([^"]+)"', APP_SKRIPT.read_text(encoding="utf-8", errors="ignore"))
        if m:
            kandidaten.append(Path(m.group(1)))
    except OSError:
        pass
    kandidaten.append(STANDARD_ORDNER)
    for k in kandidaten:
        if gueltig(k):
            return k
    return None


def gueltig(ordner: Path) -> bool:
    return (ordner / "code" / "src" / "ashamila" / "db.py").is_file() and (ordner / "daten" / "bibliothek.db").is_file()


@dataclass
class Fund:
    buch_id: int
    seite_id: int                 # interne Seite; bei PDFs = Seite im Original-PDF
    seite: int | None             # gedruckte Seitenzahl
    band: str | None
    titel: str
    autor: str
    ausschnitt: str               # mit <b>…</b> um die Fundwörter
    format: str = ""
    original: bool = False

    @property
    def fundstelle(self) -> str:
        wo = (f"Bd. {self.band}, S. {self.seite}" if self.band else f"S. {self.seite}") if self.seite else \
            f"Seite {self.seite_id}"
        return " · ".join(x for x in (self.titel, self.autor, wo) if x)


@dataclass
class Seite:
    buch_id: int
    seite_id: int
    text: str
    fussnoten: str
    seite: int | None
    band: str | None
    kapitel: str
    titel: str
    autor: str
    vorher: int | None
    nachher: int | None
    original: Path | None = None
    hinweise: list[str] = field(default_factory=list)

    @property
    def fundstelle(self) -> str:
        wo = (f"Bd. {self.band}, S. {self.seite}" if self.band else f"S. {self.seite}") if self.seite else ""
        return ", ".join(x for x in (self.titel + (f" ({self.autor})" if self.autor else ""), self.kapitel, wo) if x)


class Yamaktaba:
    def __init__(self, ordner: str | Path):
        self.ordner = Path(ordner)
        if not gueltig(self.ordner):
            raise YamaktabaFehler(f"Im Ordner {self.ordner} ist keine Yamaktaba-Bibliothek (code/ und daten/ fehlen).")
        self.daten = self.ordner / "daten"
        os.environ["ASHAMILA_DATA"] = str(self.daten)
        src = str(self.ordner / "code" / "src")
        if src not in sys.path:
            sys.path.insert(0, src)
        try:
            self.db = importlib.import_module("ashamila.db")
            self.normalize = importlib.import_module("ashamila.normalize")
        except ImportError as exc:
            raise YamaktabaFehler(f"Die Schnittstelle von Yamaktaba lässt sich nicht laden: {exc}") from exc
        self._lesen = None

    # ---------------------------------------------------------------- lesen (nur lesend)
    @property
    def con(self) -> sqlite3.Connection:
        if self._lesen is None:
            pfad = (self.daten / "bibliothek.db").as_posix()
            self._lesen = sqlite3.connect(f"file:{pfad}?mode=ro", uri=True, check_same_thread=False)
            self._lesen.row_factory = sqlite3.Row
            self._lesen.create_function("norm", 1, self.normalize.normalize, deterministic=True)
        return self._lesen

    def schliessen(self):
        if self._lesen is not None:
            self._lesen.close()
            self._lesen = None

    def anzahl_buecher(self, sprache: str = "") -> int:
        sql = "SELECT COUNT(*) FROM book WHERE imported > 0" + (" AND sprache=?" if sprache else "")
        return self.con.execute(sql, (sprache,) if sprache else ()).fetchone()[0]

    def suchen(self, text: str, sprache: str = "de", buch_id: int | None = None, grenze: int = 30,
               alle: bool = True) -> tuple[int, list[Fund]]:
        """Volltextsuche mit der Suche von Yamaktaba (Wortstamm, Umlaute, „…“, ODER, -Wort)."""
        anfrage = text if alle else " ODER ".join(text.split())
        try:
            r = self.db.search(self.con, anfrage, book=buch_id, limit=grenze,
                               extra={"sprache": sprache} if sprache else None)
        except sqlite3.Error as exc:
            raise YamaktabaFehler(f"Suche in Yamaktaba fehlgeschlagen: {exc}") from exc
        funde = [Fund(h["book"], h["pid"], h["num"], h["part"], h["book_name"] or "", h["author"] or "",
                      h["snippet"].replace("<mark>", "<b>").replace("</mark>", "</b>").replace("\n", " "),
                      h.get("format") or "", bool(h.get("datei"))) for h in r["hits"]]
        return r["total"], funde

    def frage(self, frage: str, sprache: str = "de", grenze: int = 8) -> tuple[list[str], list[Fund]]:
        """S19 offline: Stichwörter der Frage → beste Fundstellen in Yamaktaba (erst alle Wörter, dann jedes)."""
        from .bibliothek import STOPP
        woerter = [w for w in re.findall(r"[\wÄÖÜäöüß]+", frage) if w.lower() not in STOPP and len(w) >= 3]
        woerter = list(dict.fromkeys(woerter))
        if not woerter:
            return [], []
        _, funde = self.suchen(" ".join(woerter), sprache, grenze=grenze)
        if len(funde) < grenze and len(woerter) > 1:
            gesehen = {(f.buch_id, f.seite_id) for f in funde}
            for f in self.suchen(" ".join(woerter), sprache, grenze=grenze * 2, alle=False)[1]:
                if (f.buch_id, f.seite_id) not in gesehen and len(funde) < grenze:
                    funde.append(f)
                    gesehen.add((f.buch_id, f.seite_id))
        return woerter, funde

    def kapitel(self, buch_id: int, seite_id: int) -> str:
        """Kapitel aus dem Inhaltsverzeichnis; ohne Verzeichnis (viele PDFs) die letzte Überschrift wie „11 Wellen“
        auf dieser oder den 20 Seiten davor."""
        z = self.con.execute("SELECT title FROM toc WHERE book=? AND pid<=? ORDER BY pid DESC, tid DESC LIMIT 1",
                             (buch_id, seite_id)).fetchone()
        if z and (z[0] or "").strip():
            return z[0].strip()
        from .bibliothek import kapitel_aus_text
        for (body,) in self.con.execute("SELECT body FROM page WHERE book=? AND pid<=? AND pid>? ORDER BY pid DESC",
                                        (buch_id, seite_id, seite_id - 20)):
            k = kapitel_aus_text(self.normalize.strip_tags(self.db.unpack(body) or ""))
            if k:
                return k
        return ""

    def seite(self, buch_id: int, seite_id: int | None = None) -> Seite:
        p = self.db.page(self.con, int(buch_id), seite_id)
        if not p:
            raise YamaktabaFehler("Diese Seite gibt es in Yamaktaba nicht.")
        info = self.db.book_info(self.con, int(buch_id)) or {}
        strip = self.normalize.strip_tags
        original = self.db.original_path(self.con, buch_id)
        return Seite(int(buch_id), p["pid"], strip(p["body"] or "").strip(), strip(p["foot"] or "").strip(),
                     p["num"], p["part"], self.kapitel(buch_id, p["pid"]), info.get("name") or "",
                     info.get("author") or "", p["prev"], p["next"], Path(original) if original else None)

    # ---------------------------------------------------------------- archivieren (schreibend)
    def _schreiben(self):
        con = self.db.connect(str(self.daten / "bibliothek.db"))
        con.execute("PRAGMA busy_timeout=60000")
        return con

    def _kategorie(self, con) -> int:
        z = con.execute("SELECT id FROM category WHERE name=?", (ARCHIV_KATEGORIE,)).fetchone()
        if z:
            return z[0]
        z = con.execute("SELECT id FROM category WHERE own AND name=?", (ERSATZ_KATEGORIE,)).fetchone()
        return z[0] if z else self.db.save_category(con, ERSATZ_KATEGORIE)

    def archivieren(self, projekt, melde=lambda _t: None) -> dict:
        """Projekt in Yamaktaba ablegen: Archiv-ZIP und alle erzeugten PDFs als Dateien im Bibliotheksordner,
        jedes PDF zusätzlich als durchsuchbares Buch, alles in der Sammlung „YamProduktion: <Projekt>“.
        Schon archivierte, unveränderte PDFs (gleiche Prüfsumme) werden nicht doppelt aufgenommen."""
        ownbooks = importlib.import_module("ashamila.ownbooks")
        wurzel = Path(self.db.files_root())
        name = re.sub(r"[^\w\- ]+", "_", projekt.name).strip() or "Projekt"
        stand = datetime.now().strftime("%Y-%m-%d_%H-%M")
        ziel = wurzel / ARCHIV_ORDNER / name / stand
        ziel.mkdir(parents=True, exist_ok=True)
        melde("Projekt als Archiv packen …")
        zip_pfad = projekt.exportieren(ziel / f"{name}_{stand}.zip")
        pdfs = []
        for d in projekt.dokumente():
            q = Path(d["pfad"])
            if q.suffix.lower() == ".pdf" and q.is_file():
                kopie = ziel / q.name
                if not kopie.exists():
                    shutil.copy2(q, kopie)
                pdfs.append((d, kopie))
        con = self._schreiben()
        try:
            kat = self._kategorie(con)
            sammlung_name = f"YamProduktion: {projekt.name}"
            z = con.execute("SELECT id FROM collection WHERE name=?", (sammlung_name,)).fetchone()
            sammlung = z[0] if z else self.db.save_collection(con, sammlung_name)
            neu, gleich = [], []
            for d, kopie in pdfs:
                daten = kopie.read_bytes()
                pruef = hashlib.sha1(daten).hexdigest()
                da = con.execute("SELECT id FROM book WHERE hash=?", (pruef,)).fetchone()
                if da:
                    gleich.append(kopie.name)
                    self.db.set_in_collection(con, sammlung, da[0], True)
                    kopie.unlink()
                    continue
                titel = f"{projekt.name} – {_TITEL.get(d['art'], d['art'])}" + (f" {d['bezug']}" if d["bezug"] else "")
                melde(f"In Yamaktaba aufnehmen: {titel} …")
                try:
                    r = ownbooks.import_file(con, daten, kopie.name, title=f"{titel} ({stand[:10]})",
                                             author="YamProduktion", category=kat, quelle=QUELLE,
                                             datei=kopie.relative_to(wurzel).as_posix(), hsh=pruef)
                except Exception as exc:          # eine unlesbare Datei hält den Rest nicht auf
                    melde(f"{kopie.name} übersprungen: {exc}")
                    continue
                self.db.set_in_collection(con, sammlung, r["book"], True)
                neu.append({"buch_id": r["book"], "titel": r["title"], "seiten": r["pages"]})
            con.commit()
        finally:
            con.close()
        self.schliessen()                         # nächste Suche sieht die neuen Bücher
        projekt._setze_meta("yamaktaba_archiv", stand)
        projekt._protokollieren("projekt", 0, f"In Yamaktaba archiviert: {zip_pfad.name}, {len(neu)} Unterlagen neu"
                                + (f", {len(gleich)} unverändert" if gleich else ""))
        projekt._db.commit()
        return {"ordner": ziel, "zip": zip_pfad, "neu": neu, "unveraendert": gleich, "sammlung": sammlung_name}


_TITEL = {"lastenheft": "Produkt-Lastenheft", "protokoll": "Berechnung", "zeichnung_pdf": "Zeichnung",
          "stueckliste": "Stückliste", "kalkulation": "Kalkulation", "montageanleitung": "Montageanleitung",
          "abnahmeprotokoll": "Abnahmeprotokoll", "messprotokoll": "Messprotokoll",
          "technische_doku": "Technische Dokumentation", "abnahme_v1": "Abnahme Version 1"}
