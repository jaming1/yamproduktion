"""Gemeinsames Produktmodell: ein Projekt = eine SQLite-Datei (*.yamp).

- Jede Änderung wird sofort gespeichert (N8); beim Öffnen wird eine Sicherung angelegt (M7).
- Jedes Objekt hat Nummer, Version, Status und Verlauf (M3).
- Objekte sind verknüpft (M4). Ändert sich ein Wert, werden alle abhängigen
  Objekte als „neu prüfen“ markiert (M5).
- Jede Phase P1–P9 hat ein Phasentor (M2).
SQLite ist offen lesbar und braucht keine Installation (N10).
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from .berechnungen import ARTEN
from .berechnungen.basis import formatiere
from .einheiten import EinheitFehler, pruefe_einheit, umrechnen

DATEIENDUNG = ".yamp"
SCHEMA_VERSION = 4
PRIORITAETEN = ("Muss", "Soll", "Kann")
ARTEN_ANFORDERUNG = ("Anforderung", "Eigenschaft")
STATUS = ("Entwurf", "geprüft", "freigegeben")
NEU_PRUEFEN = "neu prüfen"
SICHERUNGEN_BEHALTEN = 10

PHASEN = [
    ("P1", "Ideenfindung"), ("P2", "Anforderungen"), ("P3", "Konzept"),
    ("P4", "Berechnung & Auslegung"), ("P5", "Konstruktion (CAD)"), ("P6", "Fertigung"),
    ("P7", "Montage"), ("P8", "Inbetriebnahme"), ("P9", "Betrieb"),
]
PHASE_STATUS = ("offen", "in Arbeit", "freigegeben")
# Alle Objektarten des Produktmodells: Tabelle = Typ, Nummernpräfix, Titelspalte, Phase, Anzeigename
OBJEKTE = {
    "idee":         ("I", "titel", "P1", "Idee"),
    "widerspruch":  ("W", "beschreibung", "P1", "TRIZ-Widerspruch"),
    "loesungsidee": ("L", "text", "P1", "Lösungsidee"),
    "anforderung":  ("A", "text", "P2", "Anforderung"),
    "funktion":     ("F", "name", "P2", "Funktion"),
    "variante":     ("V", "name", "P3", "Konzeptvariante"),
    "berechnung":   ("B", "titel", "P4", "Berechnung"),
    "teil":         ("T", "name", "P5", "Bauteil"),
}
PHASE_VON_TYP = {typ: info[2] for typ, info in OBJEKTE.items()}
TYP_NAME = {typ: info[3] for typ, info in OBJEKTE.items()}
_GEMEINSAM = """
    version     INTEGER NOT NULL DEFAULT 1,
    status      TEXT NOT NULL DEFAULT 'Entwurf',
    erstellt    TEXT NOT NULL,
    geaendert   TEXT NOT NULL"""

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    schluessel TEXT PRIMARY KEY,
    wert       TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS anforderung (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    nr          TEXT NOT NULL UNIQUE,
    text        TEXT NOT NULL DEFAULT '',
    zielwert    REAL,
    einheit     TEXT NOT NULL DEFAULT '',
    prioritaet  TEXT NOT NULL DEFAULT 'Muss',
    quelle      TEXT NOT NULL DEFAULT '',
    version     INTEGER NOT NULL DEFAULT 1,
    status      TEXT NOT NULL DEFAULT 'Entwurf',
    erstellt    TEXT NOT NULL,
    geaendert   TEXT NOT NULL,
    art         TEXT NOT NULL DEFAULT 'Anforderung'
);
CREATE TABLE IF NOT EXISTS berechnung (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    nr          TEXT NOT NULL UNIQUE,
    typ         TEXT NOT NULL,
    titel       TEXT NOT NULL,
    eingaben    TEXT NOT NULL,   -- JSON
    ergebnis    TEXT NOT NULL,   -- JSON (vollständiges Protokoll)
    erfuellt    INTEGER NOT NULL,
    erstellt    TEXT NOT NULL,
    version     INTEGER NOT NULL DEFAULT 1,
    status      TEXT NOT NULL DEFAULT 'Entwurf',
    geaendert   TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS phase (
    nr          TEXT PRIMARY KEY,
    status      TEXT NOT NULL DEFAULT 'offen',
    freigegeben TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS verknuepfung (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    quelle_typ  TEXT NOT NULL,      -- wovon abhängig (z. B. anforderung)
    quelle_id   INTEGER NOT NULL,
    ziel_typ    TEXT NOT NULL,      -- was davon abhängt (z. B. berechnung)
    ziel_id     INTEGER NOT NULL,
    feld        TEXT NOT NULL DEFAULT '',   -- welches Eingabefeld der Wert speist
    UNIQUE (quelle_typ, quelle_id, ziel_typ, ziel_id, feld)
);
CREATE TABLE IF NOT EXISTS verlauf (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    objekt_typ  TEXT NOT NULL,
    objekt_id   INTEGER NOT NULL,
    zeit        TEXT NOT NULL,
    text        TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS idee (
    id INTEGER PRIMARY KEY AUTOINCREMENT, nr TEXT NOT NULL UNIQUE,
    titel TEXT NOT NULL DEFAULT '', problem TEXT NOT NULL DEFAULT '', nutzen TEXT NOT NULL DEFAULT '',
    beschreibung TEXT NOT NULL DEFAULT '', ier TEXT NOT NULL DEFAULT '', ressourcen TEXT NOT NULL DEFAULT '',
    bild TEXT NOT NULL DEFAULT '',""" + _GEMEINSAM + """
);
CREATE TABLE IF NOT EXISTS widerspruch (
    id INTEGER PRIMARY KEY AUTOINCREMENT, nr TEXT NOT NULL UNIQUE,
    idee_id INTEGER, art TEXT NOT NULL DEFAULT 'technisch', beschreibung TEXT NOT NULL DEFAULT '',
    verbessern INTEGER, verschlechtern INTEGER, prinzipien TEXT NOT NULL DEFAULT '[]',""" + _GEMEINSAM + """
);
CREATE TABLE IF NOT EXISTS loesungsidee (
    id INTEGER PRIMARY KEY AUTOINCREMENT, nr TEXT NOT NULL UNIQUE,
    widerspruch_id INTEGER, prinzip INTEGER, text TEXT NOT NULL DEFAULT '',""" + _GEMEINSAM + """
);
CREATE TABLE IF NOT EXISTS funktion (
    id INTEGER PRIMARY KEY AUTOINCREMENT, nr TEXT NOT NULL UNIQUE,
    eltern_id INTEGER, name TEXT NOT NULL DEFAULT '', beschreibung TEXT NOT NULL DEFAULT '',
    reihenfolge INTEGER NOT NULL DEFAULT 0,""" + _GEMEINSAM + """
);
CREATE TABLE IF NOT EXISTS loesung (
    id INTEGER PRIMARY KEY AUTOINCREMENT, funktion_id INTEGER NOT NULL,
    text TEXT NOT NULL, loesungsidee_id INTEGER
);
CREATE TABLE IF NOT EXISTS variante (
    id INTEGER PRIMARY KEY AUTOINCREMENT, nr TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL DEFAULT '', beschreibung TEXT NOT NULL DEFAULT '',
    gewaehlt INTEGER NOT NULL DEFAULT 0, begruendung TEXT NOT NULL DEFAULT '',""" + _GEMEINSAM + """
);
CREATE TABLE IF NOT EXISTS variante_wahl (
    variante_id INTEGER NOT NULL, funktion_id INTEGER NOT NULL, loesung_id INTEGER NOT NULL,
    PRIMARY KEY (variante_id, funktion_id)
);
CREATE TABLE IF NOT EXISTS kriterium (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, gewicht REAL NOT NULL DEFAULT 1,
    reihenfolge INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS teil (
    id INTEGER PRIMARY KEY AUTOINCREMENT, nr TEXT NOT NULL UNIQUE,
    vorlage TEXT NOT NULL, name TEXT NOT NULL DEFAULT '', parameter TEXT NOT NULL DEFAULT '{}',
    werkstoff TEXT NOT NULL DEFAULT '', masse REAL, volumen REAL,""" + _GEMEINSAM + """
);
CREATE TABLE IF NOT EXISTS bewertung (
    variante_id INTEGER NOT NULL, kriterium_id INTEGER NOT NULL, punkte REAL NOT NULL,
    PRIMARY KEY (variante_id, kriterium_id)
);
"""

BEISPIEL_ANFORDERUNGEN_KWA = [
    ("Elektrische Nennleistung", 5.0, "kW", "Muss", "Anforderung"),
    ("Nennwindgeschwindigkeit", 11.0, "m/s", "Muss", "Anforderung"),
    ("Einschaltwindgeschwindigkeit", 3.0, "m/s", "Soll", "Anforderung"),
    ("Abschaltwindgeschwindigkeit (Sturm)", 25.0, "m/s", "Muss", "Anforderung"),
    ("Nabenhöhe", 12.0, "m", "Soll", "Eigenschaft"),
    ("Auslegungslebensdauer", 20.0, "a", "Muss", "Anforderung"),
    ("Schallleistungspegel", 45.0, "dB", "Kann", "Anforderung"),
]


class ProjektFehler(Exception):
    """Verständlicher Fehler beim Öffnen oder Bearbeiten eines Projekts."""


def _jetzt() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class Anforderung:
    id: int
    nr: str
    text: str
    zielwert: float | None
    einheit: str
    prioritaet: str
    quelle: str
    version: int
    status: str
    geaendert: str
    art: str


@dataclass
class GespeicherteBerechnung:
    id: int
    nr: str
    typ: str
    titel: str
    eingaben: dict
    ergebnis: dict
    erfuellt: bool
    erstellt: str
    version: int
    status: str
    geaendert: str


@dataclass
class Bezug:
    """Eine Verknüpfung, aus Sicht eines Objekts beschrieben."""
    typ: str
    id: int
    nr: str
    titel: str
    status: str
    feld: str


@dataclass
class Phase:
    nr: str
    name: str
    status: str
    freigegeben: str


@dataclass
class VerlaufEintrag:
    zeit: str
    text: str


_ANF_SPALTEN = "id, nr, text, zielwert, einheit, prioritaet, quelle, version, status, geaendert, art"
_BER_SPALTEN = "id, nr, typ, titel, eingaben, ergebnis, erfuellt, erstellt, version, status, geaendert"


class Projekt:
    """Ein geöffnetes Projekt. Alle Methoden schreiben sofort in die Datei."""

    def __init__(self, pfad: Path, verbindung: sqlite3.Connection):
        self.pfad = pfad
        self._db = verbindung
        self._db.execute("PRAGMA foreign_keys = ON")

    # ================================================================ Anlegen / Öffnen
    @classmethod
    def neu(cls, pfad: str | Path, name: str, produkt: str = "", beispiel_kwa: bool = False) -> "Projekt":
        pfad = Path(pfad)
        if pfad.suffix != DATEIENDUNG:
            pfad = pfad.with_suffix(DATEIENDUNG)
        if pfad.exists():
            raise ProjektFehler(f"Die Datei {pfad.name} gibt es schon. Bitte einen anderen Namen wählen.")
        if not name.strip():
            raise ProjektFehler("Bitte gib dem Projekt einen Namen.")
        pfad.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(pfad)
        db.executescript(SCHEMA)
        projekt = cls(pfad, db)
        projekt._setze_meta("schema_version", str(SCHEMA_VERSION))
        projekt._setze_meta("name", name.strip())
        projekt._setze_meta("produkt", produkt.strip())
        projekt._setze_meta("erstellt", _jetzt())
        projekt._phasen_anlegen()
        if beispiel_kwa:
            for text, wert, einheit, prio, art in BEISPIEL_ANFORDERUNGEN_KWA:
                projekt.anforderung_neu(text, wert, einheit, prio, quelle="Vorlage Kleinwindanlage", art=art)
        db.commit()
        return projekt

    @classmethod
    def oeffnen(cls, pfad: str | Path, sicherung: bool = True) -> "Projekt":
        pfad = Path(pfad)
        if not pfad.exists():
            raise ProjektFehler(f"Die Projektdatei {pfad} wurde nicht gefunden. Wurde sie verschoben?")
        try:
            db = sqlite3.connect(pfad)
            version = db.execute("SELECT wert FROM meta WHERE schluessel='schema_version'").fetchone()
        except sqlite3.DatabaseError as exc:
            raise ProjektFehler(f"{pfad.name} ist keine gültige YamProduktion-Projektdatei.") from exc
        if version is None:
            raise ProjektFehler(f"{pfad.name} ist keine gültige YamProduktion-Projektdatei.")
        if int(version[0]) > SCHEMA_VERSION:
            raise ProjektFehler("Diese Projektdatei stammt aus einer neueren Programmversion. "
                                "Bitte YamProduktion aktualisieren.")
        projekt = cls(pfad, db)
        if sicherung:
            projekt.sicherung_anlegen()          # vor jeder Umstellung sichern
        if int(version[0]) < SCHEMA_VERSION:
            projekt._umstellen(int(version[0]))
        return projekt

    def _umstellen(self, von: int) -> None:
        """Ältere Projektdateien auf das aktuelle Format bringen – ohne Datenverlust."""
        if von < 2:
            spalten_anf = {z[1] for z in self._db.execute("PRAGMA table_info(anforderung)")}
            if "art" not in spalten_anf:
                self._db.execute("ALTER TABLE anforderung ADD COLUMN art TEXT NOT NULL DEFAULT 'Anforderung'")
            spalten_ber = {z[1] for z in self._db.execute("PRAGMA table_info(berechnung)")}
            for spalte, definition in (("version", "INTEGER NOT NULL DEFAULT 1"),
                                       ("status", "TEXT NOT NULL DEFAULT 'Entwurf'"),
                                       ("geaendert", "TEXT NOT NULL DEFAULT ''")):
                if spalte not in spalten_ber:
                    self._db.execute(f"ALTER TABLE berechnung ADD COLUMN {spalte} {definition}")
            self._db.executescript(SCHEMA)
            self._phasen_anlegen()
            for typ in ("anforderung", "berechnung"):
                if self._db.execute(f"SELECT 1 FROM {typ} LIMIT 1").fetchone():
                    self._phase_in_arbeit(PHASE_VON_TYP[typ])
        if von < 4:
            self._db.executescript(SCHEMA)   # neue Tabellen (3: Ideen, TRIZ, Funktionen, Konzept; 4: Bauteile)
        self._setze_meta("schema_version", str(SCHEMA_VERSION))
        self._db.commit()

    def schliessen(self) -> None:
        self._db.close()

    # ================================================================ Sicherung (M7)
    @property
    def sicherungsordner(self) -> Path:
        return self.pfad.parent / f"{self.pfad.stem}_Sicherungen"

    def sicherung_anlegen(self) -> Path:
        """Kopie der Projektdatei anlegen; die letzten 10 Sicherungen werden behalten."""
        self.sicherungsordner.mkdir(exist_ok=True)
        ziel = self.sicherungsordner / f"{self.pfad.stem}_{datetime.now():%Y-%m-%d_%H-%M-%S}{DATEIENDUNG}"
        nummer = 1
        while ziel.exists():
            nummer += 1
            ziel = ziel.with_name(f"{self.pfad.stem}_{datetime.now():%Y-%m-%d_%H-%M-%S}_{nummer}{DATEIENDUNG}")
        kopie = sqlite3.connect(ziel)
        with kopie:
            self._db.backup(kopie)
        kopie.close()
        alle = sorted(self.sicherungsordner.glob(f"*{DATEIENDUNG}"), key=lambda p: p.stat().st_mtime)
        for alt in alle[:-SICHERUNGEN_BEHALTEN]:
            alt.unlink()
        return ziel

    # ================================================================ Metadaten
    def _setze_meta(self, schluessel: str, wert: str) -> None:
        self._db.execute(
            "INSERT INTO meta(schluessel, wert) VALUES(?, ?) "
            "ON CONFLICT(schluessel) DO UPDATE SET wert=excluded.wert",
            (schluessel, wert),
        )

    def meta(self, schluessel: str, standard: str = "") -> str:
        zeile = self._db.execute("SELECT wert FROM meta WHERE schluessel=?", (schluessel,)).fetchone()
        return zeile[0] if zeile else standard

    @property
    def name(self) -> str:
        return self.meta("name")

    @property
    def produkt(self) -> str:
        return self.meta("produkt")

    # ================================================================ Verlauf
    def _protokollieren(self, typ: str, id_: int, text: str) -> None:
        self._db.execute("INSERT INTO verlauf(objekt_typ, objekt_id, zeit, text) VALUES(?,?,?,?)",
                         (typ, id_, _jetzt(), text))

    def verlauf(self, typ: str, id_: int) -> list[VerlaufEintrag]:
        zeilen = self._db.execute("SELECT zeit, text FROM verlauf WHERE objekt_typ=? AND objekt_id=? "
                                  "ORDER BY id DESC", (typ, id_)).fetchall()
        return [VerlaufEintrag(*z) for z in zeilen]

    # ================================================================ Phasen (M2)
    def _phasen_anlegen(self) -> None:
        for nr, _ in PHASEN:
            self._db.execute("INSERT OR IGNORE INTO phase(nr) VALUES(?)", (nr,))

    def phasen(self) -> list[Phase]:
        namen = dict(PHASEN)
        zeilen = self._db.execute("SELECT nr, status, freigegeben FROM phase ORDER BY nr").fetchall()
        return [Phase(nr, namen[nr], status, frei) for nr, status, frei in zeilen]

    def phase(self, nr: str) -> Phase:
        for p in self.phasen():
            if p.nr == nr:
                return p
        raise ProjektFehler(f"Phase {nr} gibt es nicht.")

    def _phase_in_arbeit(self, nr: str, grund: str = "") -> None:
        alt = self.phase(nr)
        if alt.status == "in Arbeit":
            return
        self._db.execute("UPDATE phase SET status='in Arbeit', freigegeben='' WHERE nr=?", (nr,))
        if alt.status == "freigegeben":
            self._protokollieren("phase", int(nr[1:]), f"Phasentor wieder geöffnet: {grund}")

    def phase_hindernisse(self, nr: str) -> list[str]:
        """Was einer Freigabe der Phase noch im Weg steht (leer = freigabefähig)."""
        hindernisse = [f"{b.nr} muss neu geprüft werden." for b in self.neu_zu_pruefen()
                       if PHASE_VON_TYP[b.typ] == nr and b.typ not in ("anforderung", "berechnung")]
        if nr == "P1":
            if not self.liste("idee"):
                hindernisse.append("Es gibt noch keine Idee.")
        elif nr == "P3":
            varianten = self.liste("variante")
            if len(varianten) < 2:
                hindernisse.append("Es braucht mindestens zwei Konzeptvarianten zum Vergleich.")
            kriterien = self.kriterien()
            if len(kriterien) < 2:
                hindernisse.append("Es braucht mindestens zwei Bewertungskriterien.")
            bewertet = {(v, k) for v, k, _ in self._db.execute("SELECT * FROM bewertung")}
            for v in varianten:
                if any((v["id"], k["id"]) not in bewertet for k in kriterien):
                    hindernisse.append(f"{v['nr']} ist noch nicht in allen Kriterien bewertet.")
            gewaehlt = [v for v in varianten if v["gewaehlt"]]
            if not gewaehlt:
                hindernisse.append("Es ist noch keine Variante ausgewählt.")
            elif not gewaehlt[0]["begruendung"].strip():
                hindernisse.append(f"Für {gewaehlt[0]['nr']} fehlt die Begründung der Auswahl.")
        elif nr == "P2":
            if not self.liste("funktion"):
                hindernisse.append("Es gibt noch keine Funktionsstruktur.")
            liste = self.anforderungen()
            if not any(a.prioritaet == "Muss" and a.art == "Anforderung" for a in liste):
                hindernisse.append("Es gibt noch keine Muss-Anforderung.")
            for a in liste:
                if a.status == NEU_PRUEFEN:
                    hindernisse.append(f"{a.nr} muss neu geprüft werden.")
                if a.art == "Anforderung" and a.prioritaet == "Muss" and a.zielwert is None:
                    hindernisse.append(f"{a.nr} „{a.text}“ hat keinen Zielwert.")
        elif nr == "P4":
            liste = self.berechnungen()
            if not liste:
                hindernisse.append("Es gibt noch keine gespeicherte Berechnung.")
            for b in liste:
                if b.status == NEU_PRUEFEN:
                    hindernisse.append(f"{b.nr} muss neu berechnet werden.")
                elif not b.erfuellt:
                    hindernisse.append(f"{b.nr}: mindestens eine Prüfung ist nicht erfüllt.")
        if nr not in ("P1", "P2", "P3", "P4"):
            hindernisse.append("Diese Phase wird in einem späteren Meilenstein freigeschaltet.")
        return hindernisse

    def phase_freigeben(self, nr: str) -> Phase:
        hindernisse = self.phase_hindernisse(nr)
        if hindernisse:
            raise ProjektFehler("Phase kann noch nicht freigegeben werden:\n• " + "\n• ".join(hindernisse))
        self._db.execute("UPDATE phase SET status='freigegeben', freigegeben=? WHERE nr=?", (_jetzt(), nr))
        self._protokollieren("phase", int(nr[1:]), "Phase freigegeben")
        # Mit der Phase werden alle ihre Objekte freigegeben
        for typ, phase_nr in PHASE_VON_TYP.items():
            if phase_nr != nr:
                continue
            for (id_,) in self._db.execute(f"SELECT id FROM {typ} WHERE status != 'freigegeben'").fetchall():
                self._db.execute(f"UPDATE {typ} SET status='freigegeben' WHERE id=?", (id_,))
                self._protokollieren(typ, id_, f"freigegeben mit Phase {nr}")
        self._db.commit()
        return self.phase(nr)

    def phase_verlauf(self, nr: str) -> list[VerlaufEintrag]:
        return self.verlauf("phase", int(nr[1:]))

    # ================================================================ Nummern
    def _naechste_nr(self, tabelle: str, praefix: str) -> str:
        zahl = self._db.execute(f"SELECT COUNT(*) FROM {tabelle}").fetchone()[0] + 1
        while self._db.execute(f"SELECT 1 FROM {tabelle} WHERE nr=?", (f"{praefix}-{zahl:03d}",)).fetchone():
            zahl += 1
        return f"{praefix}-{zahl:03d}"

    # ================================================================ Anforderungen
    def anforderung_neu(self, text: str = "", zielwert: float | None = None, einheit: str = "",
                        prioritaet: str = "Muss", quelle: str = "", art: str = "Anforderung") -> Anforderung:
        einheit = pruefe_einheit(einheit)
        if prioritaet not in PRIORITAETEN:
            raise ProjektFehler(f"Priorität muss Muss, Soll oder Kann sein, nicht „{prioritaet}“.")
        if art not in ARTEN_ANFORDERUNG:
            raise ProjektFehler("Art muss „Anforderung“ oder „Eigenschaft“ sein.")
        jetzt = _jetzt()
        nr = self._naechste_nr("anforderung", "A")
        cur = self._db.execute(
            "INSERT INTO anforderung(nr, text, zielwert, einheit, prioritaet, quelle, erstellt, geaendert, art) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (nr, text, zielwert, einheit, prioritaet, quelle, jetzt, jetzt, art),
        )
        self._protokollieren("anforderung", cur.lastrowid, "angelegt")
        self._phase_in_arbeit("P2", f"{nr} angelegt")
        self._db.commit()
        return self.anforderung(cur.lastrowid)

    def anforderung(self, id_: int) -> Anforderung:
        zeile = self._db.execute(f"SELECT {_ANF_SPALTEN} FROM anforderung WHERE id=?", (id_,)).fetchone()
        if zeile is None:
            raise ProjektFehler("Diese Anforderung gibt es nicht mehr.")
        return Anforderung(*zeile)

    def anforderungen(self) -> list[Anforderung]:
        zeilen = self._db.execute(f"SELECT {_ANF_SPALTEN} FROM anforderung ORDER BY nr").fetchall()
        return [Anforderung(*z) for z in zeilen]

    def anforderung_aendern(self, id_: int, **felder) -> Anforderung:
        erlaubt = {"text", "zielwert", "einheit", "prioritaet", "quelle", "art"}
        unbekannt = set(felder) - erlaubt
        if unbekannt:
            raise ProjektFehler(f"Unbekannte Felder: {', '.join(sorted(unbekannt))}")
        if "einheit" in felder:
            felder["einheit"] = pruefe_einheit(felder["einheit"])
        if "prioritaet" in felder and felder["prioritaet"] not in PRIORITAETEN:
            raise ProjektFehler("Priorität muss Muss, Soll oder Kann sein.")
        if "art" in felder and felder["art"] not in ARTEN_ANFORDERUNG:
            raise ProjektFehler("Art muss „Anforderung“ oder „Eigenschaft“ sein.")
        alt = self.anforderung(id_)
        geaendert = {k: v for k, v in felder.items() if getattr(alt, k) != v}
        if not geaendert:
            return alt
        setz = ", ".join(f"{k}=?" for k in geaendert)
        # Eine inhaltliche Änderung macht eine Prüfung/Freigabe ungültig → zurück auf Entwurf
        self._db.execute(
            f"UPDATE anforderung SET {setz}, version=version+1, geaendert=?, status='Entwurf' WHERE id=?",
            (*geaendert.values(), _jetzt(), id_),
        )
        beschreibung = []
        for k, v in geaendert.items():
            if k == "zielwert":
                vorher = "–" if alt.zielwert is None else formatiere(alt.zielwert)
                nachher = "–" if v is None else formatiere(v)
                beschreibung.append(f"Zielwert {vorher} → {nachher} {alt.einheit}".rstrip())
            elif k == "einheit":
                beschreibung.append(f"Einheit {alt.einheit or '–'} → {v or '–'}")
            else:
                beschreibung.append(f"{k.capitalize()} geändert")
        self._protokollieren("anforderung", id_, f"Version {alt.version + 1}: " + ", ".join(beschreibung))
        self._phase_in_arbeit("P2", f"{alt.nr} geändert")
        if {"zielwert", "einheit"} & set(geaendert):
            self._wirkung_markieren("anforderung", id_, f"{alt.nr} geändert ({', '.join(beschreibung)})")
        self._db.commit()
        return self.anforderung(id_)

    def anforderung_loeschen(self, id_: int) -> None:
        a = self.anforderung(id_)
        self._wirkung_markieren("anforderung", id_, f"{a.nr} gelöscht")
        self._db.execute("DELETE FROM verknuepfung WHERE (quelle_typ='anforderung' AND quelle_id=?) "
                         "OR (ziel_typ='anforderung' AND ziel_id=?)", (id_, id_))
        self._db.execute("DELETE FROM anforderung WHERE id=?", (id_,))
        self._phase_in_arbeit("P2", f"{a.nr} gelöscht")
        self._db.commit()

    def anforderung_wert(self, text_enthaelt: str) -> tuple[float, str] | None:
        """Sucht den Zielwert einer Anforderung, deren Text den Suchbegriff enthält."""
        treffer = self.anforderung_suchen(text_enthaelt)
        return (treffer.zielwert, treffer.einheit) if treffer else None

    def anforderung_suchen(self, text_enthaelt: str) -> Anforderung | None:
        for a in self.anforderungen():
            if text_enthaelt.lower() in a.text.lower() and a.zielwert is not None:
                return a
        return None

    # ================================================================ Status (M3)
    def status_setzen(self, typ: str, id_: int, status: str) -> None:
        if status not in STATUS:
            raise ProjektFehler(f"Status muss {', '.join(STATUS)} sein.")
        if typ == "berechnung" and status != "Entwurf":
            b = self.berechnung(id_)
            if b.status == NEU_PRUEFEN:
                raise ProjektFehler(f"{b.nr} muss zuerst neu berechnet werden.")
        tabelle = self._tabelle(typ)
        alt = self._db.execute(f"SELECT status, nr FROM {tabelle} WHERE id=?", (id_,)).fetchone()
        if status != "Entwurf" and alt and alt[0] == NEU_PRUEFEN and typ != "anforderung":
            # Prüfen heißt hier: der Mensch bestätigt, dass die Änderung nichts verändert
            self._protokollieren(typ, id_, "nach Änderung geprüft")
        if alt is None or alt[0] == status:
            return
        self._db.execute(f"UPDATE {tabelle} SET status=? WHERE id=?", (status, id_))
        self._protokollieren(typ, id_, f"Status {alt[0]} → {status}")
        self._db.commit()

    @staticmethod
    def _tabelle(typ: str) -> str:
        if typ not in TYP_NAME:
            raise ProjektFehler(f"Unbekannter Objekttyp {typ}.")
        return typ

    def _nr_und_titel(self, typ: str, id_: int) -> tuple[str, str, str] | None:
        if typ not in OBJEKTE:
            return None
        spalte = OBJEKTE[typ][1]
        z = self._db.execute(f"SELECT nr, {spalte}, status FROM {typ} WHERE id=?", (id_,)).fetchone()
        return tuple(z) if z else None

    # ================================================================ Verknüpfungen (M4)
    def verknuepfen(self, quelle_typ: str, quelle_id: int, ziel_typ: str, ziel_id: int, feld: str = "") -> None:
        if (quelle_typ, quelle_id) == (ziel_typ, ziel_id):
            raise ProjektFehler("Ein Objekt kann nicht von sich selbst abhängen.")
        if (quelle_typ, quelle_id) in {(b.typ, b.id) for b in self.wirkt_auf(ziel_typ, ziel_id, rekursiv=True)}:
            raise ProjektFehler("Diese Verknüpfung würde einen Kreis erzeugen.")
        self._db.execute("INSERT OR IGNORE INTO verknuepfung(quelle_typ, quelle_id, ziel_typ, ziel_id, feld) "
                         "VALUES(?,?,?,?,?)", (quelle_typ, quelle_id, ziel_typ, ziel_id, feld))

    def _bezuege(self, sql: str, args: tuple) -> list[Bezug]:
        ergebnis = []
        for typ, id_, feld in self._db.execute(sql, args).fetchall():
            info = self._nr_und_titel(typ, id_)
            if info:
                ergebnis.append(Bezug(typ, id_, info[0], info[1], info[2], feld))
        return ergebnis

    def haengt_ab_von(self, typ: str, id_: int) -> list[Bezug]:
        """Direkte Quellen eines Objekts (z. B. die Anforderungen einer Berechnung)."""
        return self._bezuege("SELECT quelle_typ, quelle_id, feld FROM verknuepfung WHERE ziel_typ=? AND ziel_id=? "
                             "ORDER BY id", (typ, id_))

    def wirkt_auf(self, typ: str, id_: int, rekursiv: bool = False) -> list[Bezug]:
        """Objekte, die von diesem Objekt abhängen – auf Wunsch über alle Stufen."""
        sql = ("SELECT ziel_typ, ziel_id, feld FROM verknuepfung WHERE quelle_typ=? AND quelle_id=? ORDER BY id")
        direkt = self._bezuege(sql, (typ, id_))
        if not rekursiv:
            return direkt
        gesehen: dict[tuple[str, int], Bezug] = {}
        offen = list(direkt)
        while offen:
            b = offen.pop(0)
            if (b.typ, b.id) in gesehen:
                continue
            gesehen[(b.typ, b.id)] = b
            offen.extend(self._bezuege(sql, (b.typ, b.id)))
        return list(gesehen.values())

    # ================================================================ Änderungswirkung (M5)
    def _wirkung_markieren(self, typ: str, id_: int, grund: str) -> list[Bezug]:
        betroffen = self.wirkt_auf(typ, id_, rekursiv=True)
        for b in betroffen:
            tabelle = self._tabelle(b.typ)
            self._db.execute(f"UPDATE {tabelle} SET status=? WHERE id=?", (NEU_PRUEFEN, b.id))
            self._protokollieren(b.typ, b.id, f"Neu prüfen, weil {grund}")
            self._phase_in_arbeit(PHASE_VON_TYP[b.typ], f"{b.nr} muss neu geprüft werden")
        return betroffen

    def neu_zu_pruefen(self) -> list[Bezug]:
        """Alle Objekte im Projekt mit Status „neu prüfen“."""
        liste = []
        for typ, (_, spalte, _, _) in OBJEKTE.items():
            for id_, nr, titel in self._db.execute(
                    f"SELECT id, nr, {spalte} FROM {typ} WHERE status=? ORDER BY nr", (NEU_PRUEFEN,)):
                liste.append(Bezug(typ, id_, nr, titel, NEU_PRUEFEN, ""))
        return liste

    # ================================================================ Berechnungen
    def berechnung_speichern(self, ergebnis_dict: dict, eingaben: dict,
                             quellen: dict[str, int] | None = None) -> GespeicherteBerechnung:
        """Speichert eine Berechnung. `quellen`: Eingabefeld → id der Anforderung, die den Wert liefert,
        oder ("berechnung", id) für einen Wert aus einer anderen gespeicherten Berechnung."""
        nr = self._naechste_nr("berechnung", "B")
        erfuellt = all(p["erfuellt"] for p in ergebnis_dict.get("pruefungen", []))
        jetzt = _jetzt()
        cur = self._db.execute(
            "INSERT INTO berechnung(nr, typ, titel, eingaben, ergebnis, erfuellt, erstellt, geaendert) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (nr, ergebnis_dict["typ"], ergebnis_dict["titel"], json.dumps(eingaben),
             json.dumps(ergebnis_dict, ensure_ascii=False), int(erfuellt), jetzt, jetzt),
        )
        bid = cur.lastrowid
        nummern = []
        for feld, quelle in (quellen or {}).items():
            q_typ, q_id = quelle if isinstance(quelle, tuple) else ("anforderung", quelle)
            self.verknuepfen(q_typ, q_id, "berechnung", bid, feld)
            nr = self.anforderung(q_id).nr if q_typ == "anforderung" else self.berechnung(q_id).nr
            if nr not in nummern:
                nummern.append(nr)
        verweis = ", ".join(nummern)
        self._protokollieren("berechnung", bid, "berechnet" + (f" mit Werten aus {verweis}" if verweis else ""))
        self._phase_in_arbeit("P4", f"{nr} gespeichert")
        self._db.commit()
        return self.berechnung(bid)

    def berechnung(self, id_: int) -> GespeicherteBerechnung:
        liste = self.berechnungen(id_=id_)
        if not liste:
            raise ProjektFehler("Diese Berechnung gibt es nicht mehr.")
        return liste[0]

    def berechnungen(self, id_: int | None = None) -> list[GespeicherteBerechnung]:
        sql = f"SELECT {_BER_SPALTEN} FROM berechnung"
        args: tuple = ()
        if id_ is not None:
            sql += " WHERE id=?"
            args = (id_,)
        zeilen = self._db.execute(sql + " ORDER BY id DESC", args).fetchall()
        return [GespeicherteBerechnung(z[0], z[1], z[2], z[3], json.loads(z[4]), json.loads(z[5]), bool(z[6]),
                                       z[7], z[8], z[9], z[10]) for z in zeilen]

    def berechnung_loeschen(self, id_: int) -> None:
        self._db.execute("DELETE FROM verknuepfung WHERE (quelle_typ='berechnung' AND quelle_id=?) "
                         "OR (ziel_typ='berechnung' AND ziel_id=?)", (id_, id_))
        self._db.execute("DELETE FROM berechnung WHERE id=?", (id_,))
        self._db.commit()

    def berechnung_neu_rechnen(self, id_: int) -> GespeicherteBerechnung:
        """Rechnet mit den aktuellen Werten der verknüpften Anforderungen neu (neue Version)."""
        b = self.berechnung(id_)
        art = ARTEN.get(b.typ)
        if art is None:
            raise ProjektFehler(f"Die Berechnungsart „{b.typ}“ ist unbekannt.")
        eingaben = dict(b.eingaben)
        for q in self.haengt_ab_von("berechnung", id_):
            if q.typ == "berechnung" and q.feld:
                eingaben[q.feld] = self._wert_aus_berechnung(b, art, q)
                continue
            if q.typ != "anforderung" or not q.feld:
                continue
            a = self.anforderung(q.id)
            if a.zielwert is None:
                raise ProjektFehler(f"{a.nr} „{a.text}“ hat keinen Zielwert mehr.")
            ziel_einheit = art["feld_einheiten"].get(q.feld, "")
            try:
                wert = umrechnen(a.zielwert, a.einheit, ziel_einheit) if ziel_einheit else a.zielwert
            except EinheitFehler as exc:
                raise ProjektFehler(f"{a.nr}: {exc}") from exc
            eingaben[q.feld] = wert
        try:
            neu = art["berechne"](art["eingaben"](**eingaben))
        except ValueError as exc:
            raise ProjektFehler(f"{b.nr} lässt sich mit den neuen Werten nicht rechnen: {exc}") from exc
        neu_dict = neu.als_dict()
        haupt = art["hauptergebnis"]
        vorher = next((g for g in b.ergebnis["ergebnisse"] if g["symbol"] == haupt), None)
        nachher = neu.ergebnis(haupt)
        aenderung = (f"{haupt} {formatiere(vorher['wert'])} → {formatiere(nachher.wert)} {nachher.einheit}"
                     if vorher else "")
        self._db.execute(
            "UPDATE berechnung SET eingaben=?, ergebnis=?, erfuellt=?, version=version+1, status='Entwurf', "
            "geaendert=? WHERE id=?",
            (json.dumps(eingaben), json.dumps(neu_dict, ensure_ascii=False), int(neu.alles_erfuellt), _jetzt(), id_),
        )
        self._protokollieren("berechnung", id_, f"Version {b.version + 1}: neu berechnet ({aenderung})")
        self._wirkung_markieren("berechnung", id_, f"{b.nr} neu berechnet")
        self._phase_in_arbeit("P4", f"{b.nr} neu berechnet")
        self._db.commit()
        return self.berechnung(id_)

    def _wert_aus_berechnung(self, b, art: dict, q: Bezug) -> float:
        """Wert für das Feld q.feld aus der Quellberechnung q.id; `b` ist das abhängige Objekt (braucht .nr)."""
        from .berechnungen import wert_aus_ergebnis
        quelle = self.berechnung(q.id)
        if quelle.status == NEU_PRUEFEN:
            raise ProjektFehler(f"Zuerst {quelle.nr} „{quelle.titel}“ neu berechnen – {b.nr} übernimmt Werte daraus.")
        symbol = art["quellen"].get(q.feld, (None, None))[1]
        treffer = wert_aus_ergebnis(quelle.ergebnis, symbol) if symbol else None
        if treffer is None:
            raise ProjektFehler(f"{quelle.nr} enthält keinen Wert „{symbol}“ für {b.nr}.")
        wert, einheit = treffer
        ziel = art["feld_einheiten"].get(q.feld, "")
        if einheit and ziel and einheit != ziel:
            try:
                wert = umrechnen(wert, einheit, ziel)
            except EinheitFehler as exc:
                raise ProjektFehler(f"{quelle.nr}: {exc}") from exc
        return wert

    def berechnungen_in_reihenfolge(self, ids: list[int]) -> list[int]:
        """Sortiert Berechnungen so, dass Quellen vor den abhängigen Berechnungen kommen."""
        rest, fertig = list(ids), []
        while rest:
            for bid in rest:
                quellen = {q.id for q in self.haengt_ab_von("berechnung", bid) if q.typ == "berechnung"}
                if not quellen & set(rest) - {bid}:
                    fertig.append(bid)
                    rest.remove(bid)
                    break
            else:   # Kreis (sollte durch verknuepfen verhindert sein)
                fertig += rest
                break
        return fertig

    # ================================================================ Bauteile (MS6)
    def teil_speichern(self, vorlage: str, name: str, parameter: dict, masse: float | None = None,
                       volumen: float | None = None, quellen: dict | None = None, teil_id: int | None = None) -> dict:
        """Neues Bauteil anlegen oder (mit teil_id) als neue Version speichern.
        `quellen`: Parameter → ("berechnung", id) bzw. Anforderungs-id, aus der der Wert stammt."""
        werkstoff = str(parameter.get("werkstoff", ""))
        daten = json.dumps(parameter, ensure_ascii=False)
        if teil_id is None:
            t = self.objekt_neu("teil", vorlage=vorlage, name=name, parameter=daten, werkstoff=werkstoff,
                                masse=masse, volumen=volumen)
            tid = t["id"]
        else:
            alt = self.teil(teil_id)
            geaendert = [k for k, v in parameter.items() if alt["parameter"].get(k) != v]
            self._db.execute("UPDATE teil SET name=?, parameter=?, werkstoff=?, masse=?, volumen=?, version=version+1, "
                             "status='Entwurf', geaendert=? WHERE id=?",
                             (name, daten, werkstoff, masse, volumen, _jetzt(), teil_id))
            self._protokollieren("teil", teil_id, f"Version {alt['version'] + 1}: "
                                 + (f"{', '.join(geaendert)} geändert" if geaendert else "neu gespeichert"))
            self._db.execute("DELETE FROM verknuepfung WHERE ziel_typ='teil' AND ziel_id=?", (teil_id,))
            self._wirkung_markieren("teil", teil_id, f"{alt['nr']} geändert")
            self._phase_in_arbeit("P5", f"{alt['nr']} geändert")
            tid = teil_id
        nummern = []
        for feld, quelle in (quellen or {}).items():
            q_typ, q_id = quelle if isinstance(quelle, tuple) else ("anforderung", quelle)
            self.verknuepfen(q_typ, q_id, "teil", tid, feld)
            nr = self.anforderung(q_id).nr if q_typ == "anforderung" else self.berechnung(q_id).nr
            if nr not in nummern:
                nummern.append(nr)
        if nummern:
            self._protokollieren("teil", tid, "Maße aus " + ", ".join(nummern))
        self._db.commit()
        return self.teil(tid)

    def teil(self, id_: int) -> dict:
        t = self.objekt("teil", id_)
        t["parameter"] = json.loads(t["parameter"])
        return t

    def teile(self) -> list[dict]:
        liste = self.liste("teil")
        for t in liste:
            t["parameter"] = json.loads(t["parameter"])
        return liste

    def teil_neu_erzeugen(self, id_: int) -> dict:
        """Übernimmt die aktuellen Werte der verknüpften Berechnungen, erzeugt die Geometrie neu (neue Version)."""
        from .cad import geometrie, vorlagen
        t = self.teil(id_)
        if t["vorlage"] == "frei":
            return self._freies_teil_neu(t)
        vorlage = vorlagen.VORLAGEN.get(t["vorlage"])
        if vorlage is None:
            raise ProjektFehler(f"Die Vorlage „{t['vorlage']}“ ist unbekannt.")
        art = {"quellen": vorlage.BERECHNUNGS_QUELLEN, "feld_einheiten": vorlage.FELD_EINHEITEN}
        parameter = dict(t["parameter"])
        quellen = {}
        aenderung = []
        for q in self.haengt_ab_von("teil", id_):
            if q.typ == "berechnung" and q.feld:
                neu = self._wert_aus_berechnung(SimpleNamespace(nr=t["nr"]), art, q)
                if abs(neu - parameter.get(q.feld, neu)) > 1e-9:
                    aenderung.append(f"{vorlage.FELD_NAMEN.get(q.feld, q.feld)} {formatiere(parameter[q.feld])} → {formatiere(neu)}")
                parameter[q.feld] = neu
                quellen[q.feld] = ("berechnung", q.id)
        try:
            form = vorlage.erzeuge(vorlage.Eingaben(**parameter))
        except (ValueError, TypeError) as exc:
            raise ProjektFehler(f"{t['nr']} lässt sich mit den neuen Werten nicht erzeugen: {exc}") from exc
        e = geometrie.eigenschaften(form)
        masse = e.masse(vorlagen.dichte(parameter["werkstoff"])) if parameter.get("werkstoff") else None
        neu = self.teil_speichern(t["vorlage"], t["name"], parameter, masse, e.volumen, quellen, teil_id=id_)
        self._protokollieren("teil", id_, "neu erzeugt" + (f" ({'; '.join(aenderung)})" if aenderung else ""))
        self._db.commit()
        return neu

    # ---------- freie Teile (MS7): Werte aus Berechnungen über ber("typ", "symbol")
    def berechnungswert(self, typ: str, symbol: str, streng: bool = False) -> tuple[float, int] | None:
        """Wert `symbol` aus der neuesten gespeicherten Berechnung der Art `typ` – Längen in mm, Winkel in °.
        `streng`: Fehler, wenn diese Berechnung „neu prüfen“ ist."""
        from .berechnungen import wert_aus_ergebnis
        b = next((x for x in self.berechnungen() if x.typ == typ), None)
        if b is None:
            return None
        if streng and b.status == NEU_PRUEFEN:
            raise ProjektFehler(f"Zuerst {b.nr} „{b.titel}“ neu berechnen – das Teil übernimmt Werte daraus.")
        treffer = wert_aus_ergebnis(b.ergebnis, symbol)
        if treffer is None:
            return None
        wert, einheit = treffer
        for ziel in ("mm", "deg"):
            try:
                return umrechnen(wert, einheit, ziel), b.id
            except EinheitFehler:
                continue
        return wert, b.id

    def ber_funktion(self, streng: bool = False):
        """(ber, quellen): ber(typ, symbol) für den Modellierer; quellen sammelt "typ.symbol" → ("berechnung", id)."""
        quellen: dict[str, tuple[str, int]] = {}

        def ber(typ, symbol):
            r = self.berechnungswert(typ, symbol, streng)
            if r is None:
                return None
            quellen[f"{typ}.{symbol}"] = ("berechnung", r[1])
            return r[0]
        return ber, quellen

    def _freies_teil_neu(self, t: dict) -> dict:
        from .cad import geometrie, modellierer, vorlagen
        ber, quellen = self.ber_funktion(streng=True)
        r = modellierer.bauen(t["parameter"]["definition"], ber)
        if not r.ok:
            raise ProjektFehler(f"{t['nr']} lässt sich mit den neuen Werten nicht erzeugen: {r.fehler}")
        e = geometrie.eigenschaften(r.form)
        werkstoff = t["parameter"].get("werkstoff")
        masse = e.masse(vorlagen.dichte(werkstoff)) if werkstoff else None
        aenderung = ""
        if t.get("volumen") and abs(e.volumen - t["volumen"]) > 1e-6 * t["volumen"]:
            aenderung = f" (Volumen {formatiere(t['volumen'] / 1000)} → {formatiere(e.volumen / 1000)} cm³)"
        neu = self.teil_speichern("frei", t["name"], t["parameter"], masse, e.volumen, quellen, teil_id=t["id"])
        self._protokollieren("teil", t["id"], "neu erzeugt" + aenderung)
        self._db.commit()
        return neu

    def teil_loeschen(self, id_: int) -> None:
        self.objekt_loeschen("teil", id_)

    # ================================================================ Allgemeine Objekte (MS3)
    _FELDER = {
        "idee": {"titel", "problem", "nutzen", "beschreibung", "ier", "ressourcen", "bild"},
        "widerspruch": {"idee_id", "art", "beschreibung", "verbessern", "verschlechtern", "prinzipien"},
        "loesungsidee": {"widerspruch_id", "prinzip", "text"},
        "funktion": {"eltern_id", "name", "beschreibung", "reihenfolge"},
        "variante": {"name", "beschreibung"},
        "teil": {"vorlage", "name", "parameter", "werkstoff", "masse", "volumen"},
    }
    _FELD_NAMEN = {"titel": "Titel", "problem": "Problem", "nutzen": "Nutzen", "beschreibung": "Beschreibung",
                   "ier": "Ideales Endergebnis", "ressourcen": "Ressourcen", "bild": "Bild",
                   "verbessern": "Parameter verbessern", "verschlechtern": "Parameter verschlechtert sich",
                   "prinzip": "Prinzip", "text": "Text", "name": "Name", "eltern_id": "Einordnung",
                   "reihenfolge": "Reihenfolge", "art": "Art", "idee_id": "Idee", "widerspruch_id": "Widerspruch",
                   "prinzipien": "Prinzipien"}

    def _zeile(self, typ: str, zeile: sqlite3.Row | tuple | None, spalten: list[str]) -> dict | None:
        return dict(zip(spalten, zeile)) if zeile else None

    def _spalten(self, typ: str) -> list[str]:
        return [z[1] for z in self._db.execute(f"PRAGMA table_info({self._tabelle(typ)})")]

    def objekt(self, typ: str, id_: int) -> dict:
        spalten = self._spalten(typ)
        z = self._db.execute(f"SELECT * FROM {typ} WHERE id=?", (id_,)).fetchone()
        if z is None:
            raise ProjektFehler(f"{TYP_NAME[typ]} gibt es nicht mehr.")
        return dict(zip(spalten, z))

    def liste(self, typ: str, wo: str = "", args: tuple = (), ordnung: str = "nr") -> list[dict]:
        spalten = self._spalten(typ)
        sql = f"SELECT * FROM {typ}" + (f" WHERE {wo}" if wo else "") + f" ORDER BY {ordnung}"
        return [dict(zip(spalten, z)) for z in self._db.execute(sql, args).fetchall()]

    def objekt_neu(self, typ: str, **felder) -> dict:
        unbekannt = set(felder) - self._FELDER[typ]
        if unbekannt:
            raise ProjektFehler(f"Unbekannte Felder: {', '.join(sorted(unbekannt))}")
        praefix = OBJEKTE[typ][0]
        nr = self._naechste_nr(typ, praefix)
        jetzt = _jetzt()
        spalten = ["nr", "erstellt", "geaendert", *felder]
        cur = self._db.execute(
            f"INSERT INTO {typ}({', '.join(spalten)}) VALUES({', '.join('?' * len(spalten))})",
            (nr, jetzt, jetzt, *felder.values()))
        self._protokollieren(typ, cur.lastrowid, "angelegt")
        self._phase_in_arbeit(PHASE_VON_TYP[typ], f"{nr} angelegt")
        self._db.commit()
        return self.objekt(typ, cur.lastrowid)

    def objekt_aendern(self, typ: str, id_: int, **felder) -> dict:
        unbekannt = set(felder) - self._FELDER[typ]
        if unbekannt:
            raise ProjektFehler(f"Unbekannte Felder: {', '.join(sorted(unbekannt))}")
        alt = self.objekt(typ, id_)
        geaendert = {k: v for k, v in felder.items() if alt[k] != v}
        if not geaendert:
            return alt
        setz = ", ".join(f"{k}=?" for k in geaendert)
        self._db.execute(f"UPDATE {typ} SET {setz}, version=version+1, geaendert=?, status='Entwurf' WHERE id=?",
                         (*geaendert.values(), _jetzt(), id_))
        namen = ", ".join(self._FELD_NAMEN.get(k, k) for k in geaendert)
        self._protokollieren(typ, id_, f"Version {alt['version'] + 1}: {namen} geändert")
        self._phase_in_arbeit(PHASE_VON_TYP[typ], f"{alt['nr']} geändert")
        self._wirkung_markieren(typ, id_, f"{alt['nr']} geändert ({namen})")
        self._db.commit()
        return self.objekt(typ, id_)

    def objekt_loeschen(self, typ: str, id_: int) -> None:
        alt = self.objekt(typ, id_)
        self._wirkung_markieren(typ, id_, f"{alt['nr']} gelöscht")
        self._db.execute("DELETE FROM verknuepfung WHERE (quelle_typ=? AND quelle_id=?) OR (ziel_typ=? AND ziel_id=?)",
                         (typ, id_, typ, id_))
        if typ == "funktion":
            for kind in self.liste("funktion", "eltern_id=?", (id_,)):
                self.objekt_loeschen("funktion", kind["id"])
            self._db.execute("DELETE FROM variante_wahl WHERE funktion_id=?", (id_,))
            self._db.execute("DELETE FROM loesung WHERE funktion_id=?", (id_,))
        elif typ == "variante":
            self._db.execute("DELETE FROM variante_wahl WHERE variante_id=?", (id_,))
            self._db.execute("DELETE FROM bewertung WHERE variante_id=?", (id_,))
        elif typ == "widerspruch":
            for l in self.liste("loesungsidee", "widerspruch_id=?", (id_,)):
                self.objekt_loeschen("loesungsidee", l["id"])
        elif typ == "loesungsidee":
            self._db.execute("UPDATE loesung SET loesungsidee_id=NULL WHERE loesungsidee_id=?", (id_,))
        self._db.execute(f"DELETE FROM {typ} WHERE id=?", (id_,))
        self._phase_in_arbeit(PHASE_VON_TYP[typ], f"{alt['nr']} gelöscht")
        self._db.commit()

    # ================================================================ TRIZ (M9, S2, S3)
    def widerspruch_neu(self, beschreibung: str, verbessern: int, verschlechtern: int,
                        idee_id: int | None = None) -> dict:
        from . import triz
        prinzipien = triz.empfehlung(verbessern, verschlechtern)
        w = self.objekt_neu("widerspruch", beschreibung=beschreibung, verbessern=verbessern,
                            verschlechtern=verschlechtern, idee_id=idee_id, prinzipien=json.dumps(prinzipien))
        if idee_id:
            self.verknuepfen("idee", idee_id, "widerspruch", w["id"])
            self._db.commit()
        return w

    def physikalischer_widerspruch_neu(self, beschreibung: str, idee_id: int | None = None) -> dict:
        w = self.objekt_neu("widerspruch", beschreibung=beschreibung, art="physikalisch", idee_id=idee_id)
        if idee_id:
            self.verknuepfen("idee", idee_id, "widerspruch", w["id"])
            self._db.commit()
        return w

    def loesungsidee_neu(self, widerspruch_id: int | None, prinzip: int | None, text: str) -> dict:
        l = self.objekt_neu("loesungsidee", widerspruch_id=widerspruch_id, prinzip=prinzip, text=text)
        if widerspruch_id:
            self.verknuepfen("widerspruch", widerspruch_id, "loesungsidee", l["id"])
            self._db.commit()
        return l

    # ================================================================ Funktionsstruktur (M12)
    def funktion_neu(self, name: str, eltern_id: int | None = None, beschreibung: str = "") -> dict:
        anzahl = len(self.liste("funktion", "eltern_id IS ?", (eltern_id,)))
        return self.objekt_neu("funktion", name=name, eltern_id=eltern_id, beschreibung=beschreibung,
                               reihenfolge=anzahl)

    def funktionsbaum(self) -> list[tuple[int, dict]]:
        """Alle Funktionen in Baumreihenfolge als (Tiefe, Funktion)."""
        alle = self.liste("funktion", ordnung="reihenfolge, id")
        kinder: dict = {}
        for f in alle:
            kinder.setdefault(f["eltern_id"], []).append(f)
        ergebnis = []

        def besuche(eltern, tiefe):
            for f in kinder.get(eltern, []):
                ergebnis.append((tiefe, f))
                besuche(f["id"], tiefe + 1)
        besuche(None, 0)
        return ergebnis

    def teilfunktionen(self) -> list[dict]:
        """Funktionen ohne Unterfunktionen – die Zeilen des morphologischen Kastens."""
        eltern = {f["eltern_id"] for f in self.liste("funktion")}
        return [f for _, f in self.funktionsbaum() if f["id"] not in eltern]

    def anforderung_zu_funktion(self, anforderung_id: int, funktion_id: int) -> None:
        self.verknuepfen("anforderung", anforderung_id, "funktion", funktion_id)
        f = self.objekt("funktion", funktion_id)
        self._protokollieren("funktion", funktion_id, f"erfüllt {self.anforderung(anforderung_id).nr}")
        self._db.commit()
        return f

    # ================================================================ Morphologischer Kasten (M14)
    def loesung_neu(self, funktion_id: int, text: str, loesungsidee_id: int | None = None) -> int:
        if not text.strip():
            raise ProjektFehler("Bitte einen Lösungsweg eingeben.")
        cur = self._db.execute("INSERT INTO loesung(funktion_id, text, loesungsidee_id) VALUES(?,?,?)",
                               (funktion_id, text.strip(), loesungsidee_id))
        self._phase_in_arbeit("P3", "Lösungsweg ergänzt")
        self._db.commit()
        return cur.lastrowid

    def loesungsidee_als_loesung(self, loesungsidee_id: int, funktion_id: int) -> int:
        """S3: eine TRIZ-Lösungsidee als Lösungsweg in den morphologischen Kasten übernehmen."""
        l = self.objekt("loesungsidee", loesungsidee_id)
        return self.loesung_neu(funktion_id, f"{l['text']} ({l['nr']})", loesungsidee_id)

    def loesungen(self, funktion_id: int) -> list[dict]:
        zeilen = self._db.execute("SELECT id, text, loesungsidee_id FROM loesung WHERE funktion_id=? ORDER BY id",
                                  (funktion_id,)).fetchall()
        return [{"id": z[0], "text": z[1], "loesungsidee_id": z[2]} for z in zeilen]

    def loesung_aendern(self, loesung_id: int, text: str) -> None:
        if not text.strip():
            raise ProjektFehler("Ein Lösungsweg darf nicht leer sein.")
        self._db.execute("UPDATE loesung SET text=? WHERE id=?", (text.strip(), loesung_id))
        for (vid,) in self._db.execute("SELECT variante_id FROM variante_wahl WHERE loesung_id=?",
                                       (loesung_id,)).fetchall():
            self._wirkung_auf_variante(vid, "ein gewählter Lösungsweg wurde geändert")
        self._db.commit()

    def loesung_loeschen(self, loesung_id: int) -> None:
        for (vid,) in self._db.execute("SELECT variante_id FROM variante_wahl WHERE loesung_id=?",
                                       (loesung_id,)).fetchall():
            self._wirkung_auf_variante(vid, "ein gewählter Lösungsweg wurde gelöscht")
        self._db.execute("DELETE FROM variante_wahl WHERE loesung_id=?", (loesung_id,))
        self._db.execute("DELETE FROM loesung WHERE id=?", (loesung_id,))
        self._db.commit()

    def _wirkung_auf_variante(self, variante_id: int, grund: str) -> None:
        v = self.objekt("variante", variante_id)
        self._db.execute("UPDATE variante SET status=? WHERE id=?", (NEU_PRUEFEN, variante_id))
        self._protokollieren("variante", variante_id, f"Neu prüfen, weil {grund}")
        self._phase_in_arbeit("P3", f"{v['nr']} muss neu geprüft werden")

    def variante_neu(self, name: str, beschreibung: str = "") -> dict:
        return self.objekt_neu("variante", name=name, beschreibung=beschreibung)

    def variante_wahl_setzen(self, variante_id: int, funktion_id: int, loesung_id: int | None) -> None:
        v = self.objekt("variante", variante_id)
        alt = self._db.execute("SELECT loesung_id FROM variante_wahl WHERE variante_id=? AND funktion_id=?",
                               (variante_id, funktion_id)).fetchone()
        if (alt[0] if alt else None) == loesung_id:
            return
        if loesung_id is None:
            self._db.execute("DELETE FROM variante_wahl WHERE variante_id=? AND funktion_id=?",
                             (variante_id, funktion_id))
        else:
            self._db.execute("INSERT INTO variante_wahl VALUES(?,?,?) ON CONFLICT(variante_id, funktion_id) "
                             "DO UPDATE SET loesung_id=excluded.loesung_id", (variante_id, funktion_id, loesung_id))
            lid = self._db.execute("SELECT loesungsidee_id FROM loesung WHERE id=?", (loesung_id,)).fetchone()
            if lid and lid[0]:
                self.verknuepfen("loesungsidee", lid[0], "variante", variante_id)
        f = self.objekt("funktion", funktion_id)
        self._db.execute("UPDATE variante SET version=version+1, geaendert=?, status='Entwurf' WHERE id=?",
                         (_jetzt(), variante_id))
        self._protokollieren("variante", variante_id, f"Version {v['version'] + 1}: Lösungsweg für {f['nr']} {f['name']}")
        if v["gewaehlt"]:
            self._db.execute("UPDATE variante SET gewaehlt=0 WHERE id=?", (variante_id,))
            self._protokollieren("variante", variante_id, "Auswahl aufgehoben, weil die Variante geändert wurde")
        self._phase_in_arbeit("P3", f"{v['nr']} geändert")
        self._db.commit()

    def variante_wahl(self, variante_id: int) -> dict[int, int]:
        """Funktion → gewählter Lösungsweg."""
        return dict(self._db.execute("SELECT funktion_id, loesung_id FROM variante_wahl WHERE variante_id=?",
                                     (variante_id,)).fetchall())

    # ================================================================ Nutzwertanalyse (M15)
    def kriterium_neu(self, name: str, gewicht: float = 1.0) -> int:
        if not name.strip():
            raise ProjektFehler("Bitte einen Namen für das Kriterium eingeben.")
        if gewicht < 0:
            raise ProjektFehler("Das Gewicht darf nicht negativ sein.")
        n = self._db.execute("SELECT COUNT(*) FROM kriterium").fetchone()[0]
        cur = self._db.execute("INSERT INTO kriterium(name, gewicht, reihenfolge) VALUES(?,?,?)",
                               (name.strip(), gewicht, n))
        self._bewertung_geaendert("Kriterium „" + name.strip() + "“ ergänzt")
        return cur.lastrowid

    def kriterien(self) -> list[dict]:
        return [{"id": z[0], "name": z[1], "gewicht": z[2]}
                for z in self._db.execute("SELECT id, name, gewicht FROM kriterium ORDER BY reihenfolge, id")]

    def kriterium_aendern(self, kriterium_id: int, name: str | None = None, gewicht: float | None = None) -> None:
        if gewicht is not None and gewicht < 0:
            raise ProjektFehler("Das Gewicht darf nicht negativ sein.")
        if name is not None:
            if not name.strip():
                raise ProjektFehler("Der Name darf nicht leer sein.")
            self._db.execute("UPDATE kriterium SET name=? WHERE id=?", (name.strip(), kriterium_id))
        if gewicht is not None:
            self._db.execute("UPDATE kriterium SET gewicht=? WHERE id=?", (gewicht, kriterium_id))
        self._bewertung_geaendert("Kriterium geändert")

    def kriterium_loeschen(self, kriterium_id: int) -> None:
        self._db.execute("DELETE FROM bewertung WHERE kriterium_id=?", (kriterium_id,))
        self._db.execute("DELETE FROM kriterium WHERE id=?", (kriterium_id,))
        self._bewertung_geaendert("Kriterium gelöscht")

    def bewerten(self, variante_id: int, kriterium_id: int, punkte: float) -> None:
        if not 0 <= punkte <= 10:
            raise ProjektFehler("Punkte bitte von 0 (schlecht) bis 10 (sehr gut) vergeben.")
        self._db.execute("INSERT INTO bewertung VALUES(?,?,?) ON CONFLICT(variante_id, kriterium_id) "
                         "DO UPDATE SET punkte=excluded.punkte", (variante_id, kriterium_id, punkte))
        self._bewertung_geaendert("Bewertung geändert")

    def bewertungen(self) -> dict[tuple[int, int], float]:
        return {(v, k): p for v, k, p in self._db.execute("SELECT variante_id, kriterium_id, punkte FROM bewertung")}

    def _bewertung_geaendert(self, grund: str) -> None:
        """Ändert sich die Bewertung, muss eine getroffene Auswahl neu geprüft werden."""
        for v in self.liste("variante", "gewaehlt=1"):
            if v["status"] != NEU_PRUEFEN:
                self._db.execute("UPDATE variante SET status=? WHERE id=?", (NEU_PRUEFEN, v["id"]))
                self._protokollieren("variante", v["id"], f"Neu prüfen, weil {grund}")
        self._phase_in_arbeit("P3", grund)
        self._db.commit()

    def nutzwerte(self) -> dict[int, float]:
        """Gewichteter Nutzwert je Variante auf der Skala 0–10: Σ(Gewicht·Punkte) / ΣGewicht."""
        kriterien = self.kriterien()
        summe_g = sum(k["gewicht"] for k in kriterien)
        b = self.bewertungen()
        werte = {}
        for v in self.liste("variante"):
            if summe_g <= 0:
                werte[v["id"]] = 0.0
                continue
            werte[v["id"]] = sum(k["gewicht"] * b.get((v["id"], k["id"]), 0.0) for k in kriterien) / summe_g
        return werte

    def variante_auswaehlen(self, variante_id: int, begruendung: str) -> dict:
        if not begruendung.strip():
            raise ProjektFehler("Bitte kurz begründen, warum diese Variante gewählt wird.")
        v = self.objekt("variante", variante_id)
        self._db.execute("UPDATE variante SET gewaehlt=0")
        self._db.execute("UPDATE variante SET gewaehlt=1, begruendung=?, status='geprüft' WHERE id=?",
                         (begruendung.strip(), variante_id))
        wert = self.nutzwerte().get(variante_id, 0)
        self._protokollieren("variante", variante_id,
                             f"als Konzept ausgewählt (Nutzwert {formatiere(wert, 3)}): {begruendung.strip()}")
        self._phase_in_arbeit("P3", f"{v['nr']} ausgewählt")
        self._db.commit()
        return self.objekt("variante", variante_id)

    def gewaehltes_konzept(self) -> dict | None:
        gewaehlt = self.liste("variante", "gewaehlt=1")
        return gewaehlt[0] if gewaehlt else None
