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

from .berechnungen import ARTEN, formel
from .berechnungen.basis import formatiere
from .einheiten import EinheitFehler, pruefe_einheit, umrechnen

DATEIENDUNG = ".yamp"
# Vorlagen je Produkttyp (S1): Schlüssel → (Anzeige, Beschreibung)
VORLAGEN = {
    "kwa": ("Kleinwindanlage 5–10 kW",
            "Typische Anforderungen (Leistung, Windzone, Lebensdauer …) und Zeitplan mit Aufgaben und Meilensteinen"),
    "kwa_anforderungen": ("Kleinwindanlage – nur Anforderungen", "Typische Anforderungen, ohne Zeitplan"),
    "leer": ("Leeres Projekt", "Ohne Vorgaben – für ein anderes Produkt"),
}
SCHEMA_VERSION = 13
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
    "baugruppe":    ("G", "name", "P5", "Baugruppe"),
    "arbeitsplan":  ("AP", "name", "P6", "Arbeitsplan"),
    "montageplan":  ("M", "name", "P7", "Montageplan"),
    "inbetriebnahme": ("IB", "name", "P8", "Inbetriebnahme"),
    "wartungsplan": ("WP", "name", "P9", "Wartungsplan"),
    "pruefplan":    ("PP", "name", "P6", "Prüfplan"),
    "fmea":         ("FM", "name", "P5", "FMEA"),
    "risiko":       ("RB", "name", "P5", "Risikobeurteilung"),
    "normen":       ("NL", "name", "P2", "Normen-Checkliste"),
    "abweichung":   ("QA", "name", "P6", "Abweichungsliste"),
    "aufgabe":      ("AU", "titel", "", "Aufgabe"),          # Querschnitt: Phase steht in der Aufgabe
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
CREATE TABLE IF NOT EXISTS baugruppe (
    id INTEGER PRIMARY KEY AUTOINCREMENT, nr TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL DEFAULT '', definition TEXT NOT NULL DEFAULT '{}', masse REAL,""" + _GEMEINSAM + """
);
CREATE TABLE IF NOT EXISTS arbeitsplan (
    id INTEGER PRIMARY KEY AUTOINCREMENT, nr TEXT NOT NULL UNIQUE, teil_id INTEGER NOT NULL UNIQUE,
    name TEXT NOT NULL DEFAULT '', daten TEXT NOT NULL DEFAULT '{}', kosten REAL,""" + _GEMEINSAM + """
);
CREATE TABLE IF NOT EXISTS montageplan (
    id INTEGER PRIMARY KEY AUTOINCREMENT, nr TEXT NOT NULL UNIQUE, baugruppe_id INTEGER NOT NULL UNIQUE,
    name TEXT NOT NULL DEFAULT '', daten TEXT NOT NULL DEFAULT '{}',""" + _GEMEINSAM + """
);
CREATE TABLE IF NOT EXISTS inbetriebnahme (
    id INTEGER PRIMARY KEY AUTOINCREMENT, nr TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL DEFAULT '', daten TEXT NOT NULL DEFAULT '{}',""" + _GEMEINSAM + """
);
CREATE TABLE IF NOT EXISTS wartungsplan (
    id INTEGER PRIMARY KEY AUTOINCREMENT, nr TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL DEFAULT '', daten TEXT NOT NULL DEFAULT '{}',""" + _GEMEINSAM + """
);
CREATE TABLE IF NOT EXISTS pruefplan (
    id INTEGER PRIMARY KEY AUTOINCREMENT, nr TEXT NOT NULL UNIQUE, teil_id INTEGER NOT NULL UNIQUE,
    name TEXT NOT NULL DEFAULT '', daten TEXT NOT NULL DEFAULT '{}',""" + _GEMEINSAM + """
);
""" + "".join(f"""CREATE TABLE IF NOT EXISTS {_t} (
    id INTEGER PRIMARY KEY AUTOINCREMENT, nr TEXT NOT NULL UNIQUE, art TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL DEFAULT '', daten TEXT NOT NULL DEFAULT '{{}}',""" + _GEMEINSAM + """
);
""" for _t in ("fmea", "risiko", "normen", "abweichung")) + """CREATE TABLE IF NOT EXISTS aufgabe (
    id INTEGER PRIMARY KEY AUTOINCREMENT, nr TEXT NOT NULL UNIQUE,
    titel TEXT NOT NULL DEFAULT '', verantwortlich TEXT NOT NULL DEFAULT '', start TEXT NOT NULL DEFAULT '',
    termin TEXT NOT NULL DEFAULT '', stand TEXT NOT NULL DEFAULT 'offen', phase TEXT NOT NULL DEFAULT '',
    objekt_typ TEXT NOT NULL DEFAULT '', objekt_id INTEGER, meilenstein INTEGER NOT NULL DEFAULT 0,
    kosten_plan REAL, kosten_ist REAL, notiz TEXT NOT NULL DEFAULT '',""" + _GEMEINSAM + """
);
CREATE TABLE IF NOT EXISTS bewertung (
    variante_id INTEGER NOT NULL, kriterium_id INTEGER NOT NULL, punkte REAL NOT NULL,
    PRIMARY KEY (variante_id, kriterium_id)
);
"""

# K4 (Schema 13): gewollte Kollisionen je Baugruppe – Paar von Einbauten mit Begründung (E41)
SCHEMA_KOLLISION = """CREATE TABLE IF NOT EXISTS kollision_ausnahme (
    baugruppe_id INTEGER NOT NULL, einbau_a TEXT NOT NULL, einbau_b TEXT NOT NULL,
    begruendung TEXT NOT NULL, erstellt TEXT NOT NULL,
    PRIMARY KEY (baugruppe_id, einbau_a, einbau_b)
);
"""
SCHEMA = SCHEMA + SCHEMA_KOLLISION

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
    def neu(cls, pfad: str | Path, name: str, produkt: str = "", beispiel_kwa: bool = False,
            vorlage: str = "") -> "Projekt":
        """Neues Projekt. `vorlage`: Schlüssel aus VORLAGEN (S1); beispiel_kwa=True entspricht „kwa_anforderungen“."""
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
        vorlage = vorlage or ("kwa_anforderungen" if beispiel_kwa else "leer")
        if vorlage not in VORLAGEN:
            raise ProjektFehler(f"Die Vorlage „{vorlage}“ gibt es nicht.")
        if vorlage != "leer":
            for text, wert, einheit, prio, art in BEISPIEL_ANFORDERUNGEN_KWA:
                projekt.anforderung_neu(text, wert, einheit, prio, quelle="Vorlage Kleinwindanlage", art=art)
        if vorlage == "kwa":
            projekt.zeitplan_vorlage()
        if vorlage != "leer":
            projekt._setze_meta("vorlage", vorlage)
        db.commit()
        return projekt

    # ================================================================ Export / Import (K1)
    def exportieren(self, ziel: str | Path, unterlagen: bool = True) -> Path:
        """Ganzes Projekt als ZIP-Archiv: Projektdatei (konsistente Kopie) und die erzeugten Unterlagen.
        Bücher und Buchtexte aus der Bibliothek sind nie enthalten (M52)."""
        import tempfile
        import zipfile
        ziel = Path(ziel)
        if ziel.suffix.lower() != ".zip":
            ziel = ziel.with_suffix(".zip")
        ziel.parent.mkdir(parents=True, exist_ok=True)
        self._db.commit()
        mitgenommen, fehlend = [], []
        with tempfile.TemporaryDirectory() as tmp:
            kopie = Path(tmp) / f"{self.pfad.stem}{DATEIENDUNG}"
            ziel_db = sqlite3.connect(kopie)
            self._db.backup(ziel_db)
            ziel_db.close()
            with zipfile.ZipFile(ziel, "w", zipfile.ZIP_DEFLATED) as z:
                z.write(kopie, kopie.name)
                if unterlagen:
                    namen = set()
                    for d in self.dokumente():
                        quelle = Path(d["pfad"])
                        if not quelle.is_file():
                            fehlend.append(d["datei"])
                            continue
                        name = quelle.name
                        while name in namen:
                            name = f"{quelle.stem}_{len(namen)}{quelle.suffix}"
                        namen.add(name)
                        z.write(quelle, f"Unterlagen/{name}")
                        mitgenommen.append(name)
                z.writestr("LIESMICH.txt", (
                    f"YamProduktion – Projekt „{self.name}“\n"
                    f"Exportiert am {datetime.now():%d.%m.%Y %H:%M}\n\n"
                    f"{kopie.name}: die Projektdatei (SQLite). In YamProduktion über Ablage › Projekt importieren "
                    "öffnen oder mit jedem SQLite-Programm lesen.\n"
                    f"Unterlagen/: {len(mitgenommen)} erzeugte PDFs und Exporte.\n"
                    + (f"Nicht mehr vorhanden: {', '.join(fehlend)}\n" if fehlend else "")
                    + "Buchscans und Buchtexte sind bewusst nicht enthalten.\n"))
        self._protokollieren("projekt", 0, f"Projekt exportiert: {ziel.name} ({len(mitgenommen)} Unterlagen)")
        self._db.commit()
        return ziel

    @classmethod
    def importieren(cls, archiv: str | Path, ordner: str | Path) -> "Projekt":
        """Archiv aus exportieren() in `ordner` entpacken und das Projekt öffnen. Überschreibt nichts."""
        import zipfile
        archiv, ordner = Path(archiv), Path(ordner)
        try:
            z = zipfile.ZipFile(archiv)
        except (zipfile.BadZipFile, OSError) as exc:
            raise ProjektFehler(f"{archiv.name} ist kein lesbares Projektarchiv.") from exc
        with z:
            dateien = [n for n in z.namelist() if n.endswith(DATEIENDUNG) and "/" not in n]
            if len(dateien) != 1:
                raise ProjektFehler(f"In {archiv.name} steckt keine Projektdatei ({DATEIENDUNG}).")
            ziel = ordner / dateien[0]
            if ziel.exists():
                raise ProjektFehler(f"{ziel.name} gibt es in {ordner} schon. Bitte einen anderen Ordner wählen.")
            ordner.mkdir(parents=True, exist_ok=True)
            for n in z.namelist():
                teile = Path(n).parts
                if not teile or ".." in teile or Path(n).is_absolute():
                    continue                          # nichts außerhalb des Zielordners schreiben
                if n == dateien[0] or (teile[0] == "Unterlagen" and not n.endswith("/")):
                    zielname = ordner / (f"{ziel.stem}_Unterlagen/{teile[-1]}" if teile[0] == "Unterlagen" else n)
                    zielname.parent.mkdir(parents=True, exist_ok=True)
                    zielname.write_bytes(z.read(n))
        projekt = cls.oeffnen(ziel, sicherung=False)
        neu = []
        for d in projekt.dokumente():                  # Pfade der Unterlagen auf den neuen Ort umstellen
            kopie = ordner / f"{ziel.stem}_Unterlagen" / Path(d["pfad"]).name
            neu.append({**d, "pfad": str(kopie)} if kopie.exists() else d)
        projekt._setze_meta("dokumente", json.dumps(neu, ensure_ascii=False))
        projekt._protokollieren("projekt", 0, f"Projekt importiert aus {archiv.name}")
        projekt._db.commit()
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
        if von < 10:
            # neue Tabellen (3: Ideen, TRIZ, Funktionen, Konzept; 4: Bauteile; 5: Baugruppen; 6: Arbeitspläne;
            # 7: Montagepläne; 8: Inbetriebnahme, Wartungspläne; 9: Prüfpläne, FMEA, Risiko, Normen, Abweichungen;
            # 10: Aufgaben)
            self._db.executescript(SCHEMA)
        if von < 13:
            self._db.executescript(SCHEMA_KOLLISION)        # K4: Ausnahmen der Kollisionsprüfung
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
        if not nr:                                   # Querschnittsobjekte (Aufgaben) gehören zu keiner Phase
            return
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
        elif nr == "P5":
            if not self.teile():
                hindernisse.append("Es gibt noch kein Bauteil.")
        elif nr == "P6":
            if not self.liste("arbeitsplan"):
                hindernisse.append("Es gibt noch keinen Arbeitsplan.")
        elif nr == "P7":
            if not self.liste("montageplan"):
                hindernisse.append("Es gibt noch keinen Montageplan.")
        elif nr == "P8":
            from .betrieb import inbetriebnahme as IB
            if not any(IB.auswerten(ib["daten"])["abgenommen"] for ib in self.inbetriebnahmen()):
                hindernisse.append("Es gibt noch keine abgenommene Inbetriebnahme.")
        elif nr == "P9":
            if not self.liste("wartungsplan"):
                hindernisse.append("Es gibt noch keinen Wartungsplan.")
        for a in self.aufgaben(nr):
            if a["stand"] != "erledigt":
                hindernisse.append(f"{a['nr']} „{a['titel']}“ ist noch nicht erledigt.")
        return hindernisse

    def phase_fortschritt(self, nr: str) -> dict:
        """Fortschritt in % (M49): erledigte Aufgaben und geprüfte/freigegebene Objekte der Phase."""
        from .planung.zeitplan import fortschritt
        erledigt = gesamt = 0
        for typ, ph in PHASE_VON_TYP.items():
            if ph != nr:
                continue
            for (status,) in self._db.execute(f"SELECT status FROM {typ}").fetchall():
                gesamt += 1
                erledigt += status in ("geprüft", "freigegeben")
        aufgaben = self.aufgaben(nr)
        gesamt += len(aufgaben)
        erledigt += sum(a["stand"] == "erledigt" for a in aufgaben)
        frei = self.phase(nr).status == "freigegeben"
        return {"prozent": fortschritt(erledigt, gesamt, frei), "erledigt": erledigt, "gesamt": gesamt,
                "offene_aufgaben": [a for a in aufgaben if a["stand"] != "erledigt"]}

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

    def formel_speichern(self, eingaben: "formel.FormelEingaben") -> GespeicherteBerechnung:
        """S20: Berechnung aus einer Buchformel speichern; die Fundstelle steht als Quelle in der Berechnung."""
        from dataclasses import asdict
        try:
            ergebnis = formel.berechne(eingaben)
        except ValueError as exc:
            raise ProjektFehler(str(exc)) from exc
        return self.berechnung_speichern(ergebnis.als_dict(), asdict(eingaben))

    def berechnung_neu_rechnen(self, id_: int) -> GespeicherteBerechnung:
        """Rechnet mit den aktuellen Werten der verknüpften Anforderungen neu (neue Version)."""
        b = self.berechnung(id_)
        art = ARTEN.get(b.typ)
        if b.typ == formel.TYP:           # Formel aus Buch (S20): Hauptergebnis ist die linke Seite
            art = {"berechne": formel.berechne, "eingaben": formel.FormelEingaben, "feld_einheiten": {},
                   "hauptergebnis": b.ergebnis["ergebnisse"][0]["symbol"]}
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

    def teil_form(self, id_: int) -> dict:
        """Geometrie eines gespeicherten Teils (aus Vorlage oder Feature-Baum) – wird nicht gespeichert, sondern
        jedes Mal aus den Parametern erzeugt (E14). Liefert dict(form, masse, werkstoff, nr, name)."""
        from .cad import modellierer, vorlagen
        t = self.teil(id_)
        if t["vorlage"] == "frei":
            ber, _ = self.ber_funktion()
            r = modellierer.bauen(t["parameter"]["definition"], ber)
            if not r.ok:
                raise ProjektFehler(f"{t['nr']}: {r.fehler}")
            form = r.form
        else:
            v = vorlagen.VORLAGEN.get(t["vorlage"])
            if v is None:
                raise ProjektFehler(f"Die Vorlage „{t['vorlage']}“ ist unbekannt.")
            felder = v.Eingaben.__dataclass_fields__
            form = v.erzeuge(v.Eingaben(**{k: w for k, w in t["parameter"].items() if k in felder}))
        return {"form": form, "masse": t["masse"], "werkstoff": t["werkstoff"], "nr": t["nr"], "name": t["name"]}

    # ================================================================ Baugruppen (MS8)
    def baugruppe_bauen(self, definition: dict):
        """Baugruppe aus ihrer Definition zusammensetzen (Geometrie, Masse, Schwerpunkt, Stückliste)."""
        from .cad import baugruppe
        ber, _ = self.ber_funktion()
        cache: dict = {}

        def quelle(teil_id):
            if teil_id not in cache:
                try:
                    cache[teil_id] = self.teil_form(int(teil_id))
                except ProjektFehler as exc:
                    raise baugruppe.GeometrieFehler(str(exc)) from exc
            return cache[teil_id]
        return baugruppe.bauen(definition, quelle, ber)

    def baugruppe_speichern(self, name: str, definition: dict, masse: float | None = None,
                            baugruppe_id: int | None = None) -> dict:
        """Neue Baugruppe anlegen oder als neue Version speichern. Die eingebauten Teile werden verknüpft:
        ändert sich ein Teil, wird die Baugruppe „neu prüfen“."""
        daten = json.dumps(definition, ensure_ascii=False)
        if baugruppe_id is None:
            gid = self.objekt_neu("baugruppe", name=name, definition=daten, masse=masse)["id"]
        else:
            alt = self.baugruppe(baugruppe_id)
            self._db.execute("UPDATE baugruppe SET name=?, definition=?, masse=?, version=version+1, "
                             "status='Entwurf', geaendert=? WHERE id=?", (name, daten, masse, _jetzt(), baugruppe_id))
            self._protokollieren("baugruppe", baugruppe_id, f"Version {alt['version'] + 1}: gespeichert")
            self._db.execute("DELETE FROM verknuepfung WHERE ziel_typ='baugruppe' AND ziel_id=?", (baugruppe_id,))
            self._wirkung_markieren("baugruppe", baugruppe_id, f"{alt['nr']} geändert")
            gid = baugruppe_id
        for tid in sorted({int(e["teil_id"]) for e in definition.get("einbauten", []) if e.get("art") == "teil"}):
            self.verknuepfen("teil", tid, "baugruppe", gid, "Einbau")
        self._db.commit()
        return self.baugruppe(gid)

    def baugruppe(self, id_: int) -> dict:
        g = self.objekt("baugruppe", id_)
        g["definition"] = json.loads(g["definition"])
        return g

    def baugruppen(self) -> list[dict]:
        liste = self.liste("baugruppe")
        for g in liste:
            g["definition"] = json.loads(g["definition"])
        return liste

    def baugruppe_loeschen(self, id_: int) -> None:
        self.objekt_loeschen("baugruppe", id_)
        self._db.execute("DELETE FROM kollision_ausnahme WHERE baugruppe_id=?", (id_,))
        self._db.commit()

    # ================================================================ Kollision, Masse, Schwerpunkt (K4)
    def kollision_ausnahmen(self, baugruppe_id: int) -> dict:
        """Gewollte Kollisionen: {(einbau_a, einbau_b): Begründung}."""
        zeilen = self._db.execute("SELECT einbau_a, einbau_b, begruendung FROM kollision_ausnahme "
                                  "WHERE baugruppe_id=? ORDER BY einbau_a, einbau_b", (baugruppe_id,))
        return {(a, b): t for a, b, t in zeilen}

    def kollision_ausnahme_setzen(self, baugruppe_id: int, einbau_a: str, einbau_b: str,
                                  begruendung: str | None) -> None:
        """Paar als gewollt festhalten (mit Begründung) oder – bei leerer Begründung – wieder aufheben."""
        from .cad.kollision import paar
        a, b = paar(einbau_a, einbau_b)
        self.baugruppe(baugruppe_id)          # gibt es sie?
        text = (begruendung or "").strip()
        if text:
            self._db.execute("INSERT INTO kollision_ausnahme VALUES(?,?,?,?,?) ON CONFLICT(baugruppe_id, einbau_a, "
                             "einbau_b) DO UPDATE SET begruendung=excluded.begruendung, erstellt=excluded.erstellt",
                             (baugruppe_id, a, b, text, _jetzt()))
            self._protokollieren("baugruppe", baugruppe_id, f"Kollision {a}/{b} als gewollt vermerkt: {text}")
        else:
            self._db.execute("DELETE FROM kollision_ausnahme WHERE baugruppe_id=? AND einbau_a=? AND einbau_b=?",
                             (baugruppe_id, a, b))
            self._protokollieren("baugruppe", baugruppe_id, f"Kollision {a}/{b}: Ausnahme aufgehoben")
        self._db.commit()

    def kollision_mindestabstand(self, baugruppe_id: int) -> float:
        try:
            return float(self.meta(f"kollision_mindestabstand_{baugruppe_id}", "0"))
        except ValueError:
            return 0.0

    def kollision_mindestabstand_setzen(self, baugruppe_id: int, wert: float) -> None:
        self._setze_meta(f"kollision_mindestabstand_{baugruppe_id}", str(max(0.0, float(wert))))
        self._db.commit()

    def kollision_pruefen(self, baugruppe_id: int, mindestabstand: float | None = None):
        """Gespeicherte Baugruppe bauen und prüfen → (Ergebnis, Pruefung, Massen)."""
        from .cad import kollision
        g = self.baugruppe(baugruppe_id)
        erg = self.baugruppe_bauen(g["definition"])
        abstand = self.kollision_mindestabstand(baugruppe_id) if mindestabstand is None else mindestabstand
        pr = kollision.pruefen(erg, g["definition"], self.kollision_ausnahmen(baugruppe_id), abstand)
        return erg, pr, kollision.massen(erg, g["definition"])

    # ================================================================ Zeichnungen (MS8, für MS12 wiederverwendbar)
    def passmasse(self, typ: str, id_: int) -> str:
        """Passmaße einer Zeichnung, z. B. „Ø80 k6; Ø140 H7“ (werden je Teil/Baugruppe gemerkt)."""
        return self.meta(f"passmasse:{typ}:{id_}", "") or ""

    def passmasse_speichern(self, typ: str, id_: int, text: str) -> None:
        if text != self.passmasse(typ, id_):
            self._setze_meta(f"passmasse:{typ}:{id_}", text)
            self._db.commit()

    @staticmethod
    def passmasse_lesen(text: str) -> dict:
        """„Ø80 k6; Ø13,5 H7“ → {"80": "k6", "13,5": "H7"} (Schlüssel wie auf der Zeichnung formatiert)."""
        import re
        out = {}
        for teil in re.split(r";|,\s+", text or ""):
            worte = teil.split()
            if len(worte) >= 2:
                try:
                    schluessel = formatiere(float(worte[0].lstrip("Ø⌀").replace(",", ".")))
                except ValueError:
                    continue
                out[schluessel] = " ".join(worte[1:])
        return out

    def zeichnung(self, typ: str, id_: int, ersteller: str = "", schnitt=None, massstab=None):
        """Technische Zeichnung eines Teils oder einer Baugruppe mit den gemerkten Passmaßen."""
        from .cad import zeichnung as Z
        felder = {"projekt": self.name, "ersteller": ersteller}
        stueckliste = positionen = None
        if typ == "teil":
            t = self.teil(id_)
            form = self.teil_form(id_)["form"]
            felder.update(benennung=t["name"], sachnummer=t["nr"], werkstoff=t["werkstoff"],
                          masse=f"{formatiere(t['masse'])} kg" if t["masse"] else "",
                          version=f"V{t['version']} · {t['status']}")
        else:
            g = self.baugruppe(id_)
            r = self.baugruppe_bauen(g["definition"])
            if not r.ok:
                raise ProjektFehler(r.fehler)
            form = r.gesamtform()
            stueckliste, positionen = r.stueckliste, r.positionspunkte()
            felder.update(benennung=g["name"], sachnummer=g["nr"], werkstoff="siehe Stückliste",
                          masse=f"{formatiere(r.masse)} kg", version=f"V{g['version']} · {g['status']}")
        return Z.zeichnung_erstellen(form, felder, schnitt=schnitt,
                                     toleranzen=self.passmasse_lesen(self.passmasse(typ, id_)),
                                     massstab=massstab, stueckliste=stueckliste, positionen=positionen)

    # ================================================================ Montage (MS10)
    def montageplan_von_baugruppe(self, baugruppe_id: int) -> dict | None:
        z = self._db.execute("SELECT id FROM montageplan WHERE baugruppe_id=?", (baugruppe_id,)).fetchone()
        return self.montageplan(z[0]) if z else None

    def montageplan(self, id_: int) -> dict:
        m = self.objekt("montageplan", id_)
        m["daten"] = json.loads(m["daten"])
        return m

    def montageplaene(self) -> list[dict]:
        liste = self.liste("montageplan")
        for m in liste:
            m["daten"] = json.loads(m["daten"])
        return liste

    def montage_umfeld(self, vorrichtung_id: int | None = None):
        """Was der Montageplan-Vorschlag aus dem Projekt braucht: Teile, Schrauben- und Pressverbandrechnungen."""
        from .berechnungen import wert_aus_ergebnis
        from .montage.montageplan import Umfeld
        u = Umfeld()
        for t in self.teile():
            u.teile[t["id"]] = {k: t[k] for k in ("vorlage", "name", "nr", "parameter", "masse")}
        for b in self.berechnungen():                       # neueste zuerst
            if b.typ == "schrauben":
                m = wert_aus_ergebnis(b.ergebnis, "M_A")
                u.schrauben.append({"nr": b.nr, "gewinde": b.eingaben.get("gewinde"), "klasse": b.eingaben.get("klasse"),
                                    "m_a": round(m[0], 1) if m else None})
            elif b.typ == "pressverband" and u.pressverband is None:
                d = wert_aus_ergebnis(b.ergebnis, "d_F")
                ue = wert_aus_ergebnis(b.ergebnis, "Ü")
                if d and ue:
                    u.pressverband = {"nr": b.nr, "d_f": umrechnen(d[0], d[1], "mm"), "ue": umrechnen(ue[0], ue[1], "mm")}
        if vorrichtung_id:
            t = self.teil(vorrichtung_id)
            u.vorrichtung = {"id": t["id"], "nr": t["nr"], "name": t["name"]}
        return u

    def montageplan_vorschlag(self, baugruppe_id: int, vorrichtung_id: int | None = None) -> dict:
        from .montage import montageplan as M
        g = self.baugruppe(baugruppe_id)
        erg = self.baugruppe_bauen(g["definition"])
        if erg.fehler and not erg.exemplare:
            raise ProjektFehler(erg.fehler)
        return M.vorschlag(g["definition"], erg, self.montage_umfeld(vorrichtung_id))

    def montageplan_speichern(self, baugruppe_id: int, daten: dict) -> dict:
        """Montageplan einer Baugruppe anlegen oder als neue Version speichern. Verknüpft mit der Baugruppe und
        der Vorrichtung: ändert sich eine davon, wird der Plan „neu prüfen“."""
        g = self.baugruppe(baugruppe_id)
        name = f"{g['nr']} {g['name']}"
        text = json.dumps(daten, ensure_ascii=False)
        alt = self.montageplan_von_baugruppe(baugruppe_id)
        if alt is None:
            mid = self.objekt_neu("montageplan", baugruppe_id=baugruppe_id, name=name, daten=text)["id"]
        else:
            mid = alt["id"]
            self._db.execute("UPDATE montageplan SET name=?, daten=?, version=version+1, status='Entwurf', "
                             "geaendert=? WHERE id=?", (name, text, _jetzt(), mid))
            self._protokollieren("montageplan", mid, f"Version {alt['version'] + 1}: gespeichert")
            self._db.execute("DELETE FROM verknuepfung WHERE ziel_typ='montageplan' AND ziel_id=?", (mid,))
        self.verknuepfen("baugruppe", baugruppe_id, "montageplan", mid, "Baugruppe")
        if daten.get("vorrichtung"):
            self.verknuepfen("teil", int(daten["vorrichtung"]), "montageplan", mid, "Vorrichtung")
        self._db.commit()
        return self.montageplan(mid)

    def montageplatte_vorschlag(self, baugruppe_id: int) -> tuple[dict, list[str]]:
        from .montage import montageplan as M
        g = self.baugruppe(baugruppe_id)
        try:
            return M.platte_vorschlag(g["definition"], self.baugruppe_bauen(g["definition"]))
        except ValueError as exc:
            raise ProjektFehler(str(exc)) from exc

    def montageplatte_anlegen(self, baugruppe_id: int, teil_id: int | None = None) -> dict:
        """Montageplatte (Vorlage „montageplatte“) aus der Baugruppe vorschlagen und als Bauteil speichern
        (mit teil_id: vorhandene Platte neu bemessen)."""
        from .cad import geometrie, vorlagen
        werte, _ = self.montageplatte_vorschlag(baugruppe_id)
        form = vorlagen.erzeuge_montageplatte(vorlagen.MontageplatteParameter(**werte))
        e = geometrie.eigenschaften(form)
        g = self.baugruppe(baugruppe_id)
        return self.teil_speichern("montageplatte", f"Montageplatte {g['name']}"[:60], werte,
                                   e.masse(vorlagen.dichte(werte["werkstoff"])), e.volumen, teil_id=teil_id)

    def montageplatten(self) -> list[dict]:
        return [t for t in self.teile() if t["vorlage"] == "montageplatte"]

    # ================================================================ Erzeugte Unterlagen und Abnahme (MS15)
    def dokument_merken(self, art: str, pfad, bezug: str = ""):
        """Merkt, dass eine Unterlage (PDF, DXF, CSV) erzeugt wurde – Nachweis für die Abnahme."""
        liste = [d for d in self.dokumente() if not (d["art"] == art and d["bezug"] == bezug)]
        liste.append({"art": art, "bezug": bezug, "datei": Path(pfad).name, "pfad": str(pfad), "datum": _jetzt()})
        self._setze_meta("dokumente", json.dumps(liste, ensure_ascii=False))
        self._db.commit()

    def dokumente(self, art: str | None = None) -> list[dict]:
        liste = json.loads(self.meta("dokumente") or "[]")
        return [d for d in liste if art is None or d["art"] == art]

    def abnahme_bestaetigungen(self) -> dict:
        return json.loads(self.meta("abnahme") or "{}")

    def abnahme_bestaetigen(self, nr: int, ja: bool, notiz: str = ""):
        """Kriterien, die nur der Mensch prüfen kann (Buchsuche mit echten Scans, Lauf auf dem Mac)."""
        daten = self.abnahme_bestaetigungen()
        if ja:
            daten[str(nr)] = {"datum": _jetzt(), "notiz": notiz.strip()}
        else:
            daten.pop(str(nr), None)
        self._setze_meta("abnahme", json.dumps(daten, ensure_ascii=False))
        self._protokollieren("projekt", 0, f"Abnahmekriterium {nr} " + ("bestätigt" if ja else "zurückgenommen")
                             + (f": {notiz.strip()}" if notiz.strip() else ""))
        self._db.commit()

    # ================================================================ Inbetriebnahme & Betrieb (MS11)
    _BETRIEB_WERTE = (("rotorauslegung", "n"), ("rotorauslegung", "P_el"), ("bremse", "t_Br"),
                      ("ertrag", "v_ein"), ("ertrag", "v_ab"), ("ertrag", "t_unter"), ("ertrag", "V"),
                      ("lager", "L10h,A"), ("lager", "L10h,B"), ("schrauben", "M_A"))

    def betrieb_grundlagen(self):
        """Sollwerte für Inbetriebnahme und Wartung aus den neuesten Berechnungen und den Montageplänen."""
        from .berechnungen import wert_aus_ergebnis
        from .betrieb.inbetriebnahme import Grundlagen, Wert
        g = Grundlagen()
        neueste: dict = {}
        for b in self.berechnungen():                       # neueste zuerst
            neueste.setdefault(b.typ, b)
        for typ, sym in self._BETRIEB_WERTE:
            b = neueste.get(typ)
            treffer = wert_aus_ergebnis(b.ergebnis, sym) if b else None
            if treffer:
                wert, einheit = treffer
                if einheit == "%":
                    wert, einheit = wert / 100, "–"
                g.werte[sym] = Wert(float(wert), einheit, b.nr, ("berechnung", b.id))
        # Fallback aus den Anforderungen (Vorlage Kleinwindanlage)
        for a in self.anforderungen():
            for sym, wort in (("v_ein", "Einschaltwind"), ("v_ab", "Abschaltwind"), ("P_el", "Nennleistung")):
                if sym not in g.werte and wort.lower() in a.text.lower() and a.zielwert is not None:
                    g.werte[sym] = Wert(float(a.zielwert), a.einheit, a.nr, ("anforderung", a.id))
        for mp in self.montageplaene():
            for st in mp["daten"].get("schritte", []):
                for m in st.get("momente", []):
                    if m.get("wert") not in (None, ""):
                        g.momente.append((m["was"], float(m["wert"]), mp["nr"], ("montageplan", mp["id"])))
        b = neueste.get("ertrag")
        if b and b.ergebnis.get("diagramm"):
            d = b.ergebnis["diagramm"]
            g.kurve = {"x": d["x"], "y": d["y"], "quelle": b.nr}
        return g

    def _betrieb_verknuepfen(self, typ: str, id_: int, refs) -> None:
        self._db.execute("DELETE FROM verknuepfung WHERE ziel_typ=? AND ziel_id=?", (typ, id_))
        for r in {tuple(r) for r in refs if r}:
            try:
                self.verknuepfen(r[0], int(r[1]), typ, id_, "Sollwert")
            except ProjektFehler:
                pass

    def _betrieb_speichern(self, typ: str, id_: int, daten: dict, name: str | None = None) -> None:
        alt = self.objekt(typ, id_)
        self._db.execute(f"UPDATE {typ} SET name=?, daten=?, version=version+1, status='Entwurf', geaendert=? "
                         "WHERE id=?", (name or alt["name"], json.dumps(daten, ensure_ascii=False), _jetzt(), id_))
        self._protokollieren(typ, id_, f"Version {alt['version'] + 1}: gespeichert")
        self._phase_in_arbeit(PHASE_VON_TYP[typ], f"{alt['nr']} geändert")

    def _betrieb_laden(self, typ: str, id_: int) -> dict:
        o = self.objekt(typ, id_)
        o["daten"] = json.loads(o["daten"])
        return o

    def inbetriebnahme_neu(self, name: str = "Inbetriebnahme", datum: str = "") -> dict:
        """Checkliste aus der Vorlage „Kleinwindanlage“ mit Sollwerten aus dem Projekt anlegen."""
        from .betrieb import inbetriebnahme as IB
        daten = IB.vorlage_kwa(self.betrieb_grundlagen(), datum or datetime.now().date().isoformat())
        iid = self.objekt_neu("inbetriebnahme", name=name, daten=json.dumps(daten, ensure_ascii=False))["id"]
        self._betrieb_verknuepfen("inbetriebnahme", iid, [p.get("ref") for p in daten["punkte"]])
        self._db.commit()
        return self.inbetriebnahme(iid)

    def inbetriebnahme(self, id_: int) -> dict:
        return self._betrieb_laden("inbetriebnahme", id_)

    def inbetriebnahmen(self) -> list[dict]:
        return [self.inbetriebnahme(o["id"]) for o in self.liste("inbetriebnahme")]

    def inbetriebnahme_speichern(self, id_: int, daten: dict, name: str | None = None) -> dict:
        self._betrieb_speichern("inbetriebnahme", id_, daten, name)
        self._betrieb_verknuepfen("inbetriebnahme", id_, [p.get("ref") for p in daten.get("punkte", [])])
        self._db.commit()
        return self.inbetriebnahme(id_)

    def wartungsplan_neu(self, name: str = "Wartungsplan", start: str = "") -> dict:
        from .betrieb import wartung as W
        g = self.betrieb_grundlagen()
        mit_getriebe = any(b.typ == "getriebe" for b in self.berechnungen())
        daten = W.vorlage_kwa(g.werte, start or datetime.now().date().isoformat(), mit_getriebe)
        wid = self.objekt_neu("wartungsplan", name=name, daten=json.dumps(daten, ensure_ascii=False))["id"]
        refs = [g.werte[s].ref for s in ("L10h,A", "L10h,B", "t_unter") if s in g.werte]
        self._betrieb_verknuepfen("wartungsplan", wid, refs)
        self._db.commit()
        return self.wartungsplan(wid)

    def wartungsplan(self, id_: int) -> dict:
        return self._betrieb_laden("wartungsplan", id_)

    def wartungsplaene(self) -> list[dict]:
        return [self.wartungsplan(o["id"]) for o in self.liste("wartungsplan")]

    def wartungsplan_speichern(self, id_: int, daten: dict) -> dict:
        self._betrieb_speichern("wartungsplan", id_, daten)
        self._db.commit()
        return self.wartungsplan(id_)

    def rueckmeldung(self, titel_: str, problem: str = "", herkunft: str = "") -> dict:
        """Erfahrung oder Mangel aus Inbetriebnahme/Betrieb als Idee für die nächste Version (Lastenheft S14)."""
        if not titel_.strip():
            raise ProjektFehler("Bitte kurz beschreiben, was verbessert werden soll.")
        return self.objekt_neu("idee", titel=titel_.strip()[:120], problem=problem,
                               beschreibung=f"Rückmeldung aus dem Betrieb{': ' + herkunft if herkunft else ''}. "
                                            "Für die nächste Version prüfen.")

    # ================================================================ Projektmanagement (MS13)
    _STAENDE = ("offen", "in Arbeit", "erledigt")

    def _aufgabe_pruefen(self, felder: dict) -> dict:
        from .betrieb.wartung import lesen
        if "stand" in felder and felder["stand"] not in self._STAENDE:
            raise ProjektFehler("Stand muss offen, in Arbeit oder erledigt sein.")
        if felder.get("phase") and felder["phase"] not in dict(PHASEN):
            raise ProjektFehler(f"Phase {felder['phase']} gibt es nicht.")
        for k in ("start", "termin"):
            if k in felder and felder[k]:
                d = lesen(felder[k])
                if d is None:
                    raise ProjektFehler("Datum bitte als TT.MM.JJJJ eingeben.")
                felder[k] = d.isoformat()
        start, termin = felder.get("start"), felder.get("termin")
        if start and termin and start > termin:
            raise ProjektFehler("Der Start liegt nach dem Termin.")
        return felder

    def aufgabe_neu(self, titel_: str, **felder) -> dict:
        """Aufgabe oder Meilenstein (M48): Verantwortlich, Start, Termin, Stand, Phase, Objekt, Kosten."""
        if not titel_.strip():
            raise ProjektFehler("Bitte der Aufgabe einen Titel geben.")
        return self.objekt_neu("aufgabe", titel=titel_.strip(), **self._aufgabe_pruefen(felder))

    def aufgabe(self, id_: int) -> dict:
        return self.objekt("aufgabe", id_)

    def aufgaben(self, phase: str | None = None) -> list[dict]:
        wo, args = ("phase=?", (phase,)) if phase else ("", ())
        liste = self.liste("aufgabe", wo, args)
        return sorted(liste, key=lambda a: (a["start"] or a["termin"] or "9999", a["termin"] or "9999", a["nr"]))

    def aufgabe_aendern(self, id_: int, **felder) -> dict:
        alt = self.aufgabe(id_)
        neu = self._aufgabe_pruefen(dict(felder))
        pruef = {"start": alt["start"], "termin": alt["termin"], **neu}
        if pruef["start"] and pruef["termin"] and pruef["start"] > pruef["termin"] and not alt["meilenstein"]:
            raise ProjektFehler("Der Start liegt nach dem Termin.")
        return self.objekt_aendern("aufgabe", id_, **neu)

    def zeitplan_vorlage(self, start: str = "") -> list[dict]:
        """Aufgaben und Meilensteine der Kleinwindanlage ab `start` anlegen (Dauern sind Schätzwerte)."""
        from .betrieb.wartung import lesen
        from .planung import zeitplan as Z
        beginn = lesen(start) if start else datetime.now().date()
        return [self.aufgabe_neu(a.pop("titel"), **a) for a in Z.vorlage_kwa(beginn)]

    def kosten_posten(self) -> list[dict]:
        return json.loads(self.meta("kosten", "[]") or "[]")

    def kosten_speichern(self, posten: list[dict]) -> None:
        self._setze_meta("kosten", json.dumps(posten, ensure_ascii=False))
        self._db.commit()

    def kosten_aus_kalkulation(self) -> tuple[list[dict], int]:
        """Plan je Baugruppe aus der Kalkulation übernehmen; vorhandene Posten derselben Baugruppe werden ersetzt."""
        from .planung import kosten as K
        posten = self.kosten_posten()
        n = 0
        for g in self.baugruppen():
            zeilen, _, _, _ = self.kalkulation_baugruppe(g["id"])
            for art, text, plan, quelle in K.aus_kalkulation(g["nr"], g["name"], zeilen):
                alt = next((p for p in posten if p["text"] == text), None)
                if alt:
                    alt.update(kostenart=art, plan=plan, quelle=quelle)
                else:
                    K.posten_neu(posten, art, text, plan, None, quelle)
                n += 1
        self.kosten_speichern(posten)
        return posten, n

    def kosten_uebersicht(self, posten: list[dict] | None = None) -> list[dict]:
        from .planung import kosten as K
        return K.uebersicht(self.kosten_posten() if posten is None else posten, self.aufgaben())

    # ================================================================ Qualität, Sicherheit & Normen (MS12)
    def _nachweise(self) -> dict[str, list[str]]:
        """Berechnungsart bzw. Objektart → Nummern, die als Nachweis gelten (neueste Berechnung je Art)."""
        out: dict[str, list[str]] = {}
        for b in self.berechnungen():                       # neueste zuerst
            out.setdefault(b.typ, [b.nr])
        for typ in ("risiko", "pruefplan", "inbetriebnahme"):
            nrn = [o["nr"] for o in self.liste(typ)]
            if nrn:
                out[typ] = nrn
        return out

    # ---------- Prüfpläne (M43, S15)
    def pruefplan_von_teil(self, teil_id: int) -> dict | None:
        z = self._db.execute("SELECT id FROM pruefplan WHERE teil_id=?", (teil_id,)).fetchone()
        return self.pruefplan(z[0]) if z else None

    def pruefplan(self, id_: int) -> dict:
        return self._betrieb_laden("pruefplan", id_)

    def pruefplaene(self) -> list[dict]:
        return [self.pruefplan(o["id"]) for o in self.liste("pruefplan")]

    def _pruefmerkmale(self, teil_id: int) -> list[dict]:
        from .qualitaet import pruefplan as PP
        return PP.aus_zeichnung(self.zeichnung("teil", teil_id).masse)

    def pruefplan_neu(self, teil_id: int) -> dict:
        """Prüfplan aus den Maßen und Passmaßen der Zeichnung des Bauteils (je Bauteil einer)."""
        if self.pruefplan_von_teil(teil_id):
            raise ProjektFehler("Für dieses Bauteil gibt es schon einen Prüfplan.")
        t = self.teil(teil_id)
        daten = {"teil": t["nr"], "zeichnung": f"V{t['version']}", "datum": datetime.now().date().isoformat(),
                 "pruefer": "", "los": "", "merkmale": self._pruefmerkmale(teil_id)}
        pid = self.objekt_neu("pruefplan", teil_id=teil_id, name=f"Prüfplan {t['name']}",
                              daten=json.dumps(daten, ensure_ascii=False))["id"]
        self.verknuepfen("teil", teil_id, "pruefplan", pid, "Zeichnung")
        self._db.commit()
        return self.pruefplan(pid)

    def pruefplan_aktualisieren(self, id_: int) -> tuple[dict, int, int]:
        """Merkmale neu aus der Zeichnung lesen; Ist-Werte bleiben erhalten. → (Plan, neu, entfallen)."""
        alt = self.pruefplan(id_)
        bisher = {m["merkmal"]: m for m in alt["daten"].get("merkmale", [])}
        neu = self._pruefmerkmale(alt["teil_id"])
        for m in neu:
            b = bisher.get(m["merkmal"])
            if b:
                for k in ("ist", "bemerkung", "pruefmittel", "umfang"):
                    m[k] = b.get(k, m[k])
                if m.get("min") is None:
                    m["min"], m["max"] = b.get("min"), b.get("max")
        zahl_neu = sum(1 for m in neu if m["merkmal"] not in bisher)
        entfallen = len(set(bisher) - {m["merkmal"] for m in neu})
        daten = dict(alt["daten"], merkmale=neu, zeichnung=f"V{self.teil(alt['teil_id'])['version']}")
        return self.pruefplan_speichern(id_, daten), zahl_neu, entfallen

    def pruefplan_speichern(self, id_: int, daten: dict) -> dict:
        from .qualitaet import pruefplan as PP
        PP.auswerten(daten)
        self._betrieb_speichern("pruefplan", id_, daten)
        self._db.commit()
        return self.pruefplan(id_)

    # ---------- FMEA, Risikobeurteilung, Normen, Abweichungen (M44–M47)
    def qdok_neu(self, typ: str, art: str = "", name: str = "") -> dict:
        """Neues Tabellen-Dokument mit Vorlage „Kleinwindanlage“ und Nachweisen aus dem Projekt."""
        from .qualitaet import tabellen as Q
        nachweise = self._nachweise()
        neueste = {k: v[0] for k, v in nachweise.items()}
        if typ == "fmea":
            art = art or Q.FMEA.arten[0]
            daten = Q.fmea_vorlage(art, neueste, [t["name"] for t in self.teile()])
        elif typ == "risiko":
            daten = Q.risiko_vorlage(neueste)
            daten["grenzen"] = {"verwendung": "Netzgekoppelte Kleinwindanlage zur Stromerzeugung, Aufstellung im "
                                              "Freien, Bedienung durch eingewiesene Personen",
                                "fehlanwendung": "Besteigen des Turms im Betrieb, Betrieb ohne Bremse",
                                "lebensdauer": "20 Jahre (Auslegung)"}
        elif typ == "normen":
            daten = Q.normen_vorlage(nachweise)
        elif typ == "abweichung":
            daten = {"zeilen": []}
        else:
            raise ProjektFehler(f"Unbekannte Dokumentart {typ}.")
        name = name or (art if typ == "fmea" else Q.ART[typ].titel)
        qid = self.objekt_neu(typ, art=art, name=name, daten=json.dumps(daten, ensure_ascii=False))["id"]
        self._qdok_verknuepfen(typ, qid, daten)
        self._db.commit()
        return self.qdok(typ, qid)

    def _qdok_verknuepfen(self, typ: str, id_: int, daten: dict) -> None:
        """Berechnungen, die im Dokument als Nachweis genannt sind, verknüpfen (Änderung → „neu prüfen“)."""
        import re
        nrn = set()
        for z in daten.get("zeilen", []):
            for k in ("vermeidung", "nachweis"):
                nrn |= set(re.findall(r"\bB-\d{3}\b", str(z.get(k, ""))))
        refs = [("berechnung", b.id) for b in self.berechnungen() if b.nr in nrn]
        self._betrieb_verknuepfen(typ, id_, refs)

    def qdok(self, typ: str, id_: int) -> dict:
        return self._betrieb_laden(typ, id_)

    def qdoks(self, typ: str) -> list[dict]:
        return [self.qdok(typ, o["id"]) for o in self.liste(typ)]

    def qdok_speichern(self, typ: str, id_: int, daten: dict, name: str | None = None) -> dict:
        self._betrieb_speichern(typ, id_, daten, name)
        self._qdok_verknuepfen(typ, id_, daten)
        self._db.commit()
        return self.qdok(typ, id_)

    def normen_abgleichen(self, id_: int) -> tuple[dict, int]:
        from .qualitaet import tabellen as Q
        d = self.qdok("normen", id_)
        n = Q.normen_abgleichen(d["daten"], self._nachweise())
        return (self.qdok_speichern("normen", id_, d["daten"]) if n else d), n

    def abweichungen_funde(self) -> list[dict]:
        """n. i. O. aus Prüfplänen und Inbetriebnahmen als Vorschläge für die Abweichungsliste."""
        from .betrieb import inbetriebnahme as IB
        from .qualitaet import pruefplan as PP
        funde = []
        for pp in self.pruefplaene():
            for m in pp["daten"].get("merkmale", []):
                if PP.ergebnis(m) == IB.NIO:
                    funde.append({"schluessel": f"{pp['nr']}/{m['id']}", "datum": pp["daten"].get("datum", ""),
                                  "bauteil": pp["daten"].get("teil", ""),
                                  "beschreibung": f"{m['merkmal']}: Ist {m.get('ist', '')} außerhalb "
                                                  f"{PP.grenz_text(m)}", "herkunft": pp["nr"]})
        for ib in self.inbetriebnahmen():
            for p in IB.maengel(ib["daten"]):
                funde.append({"schluessel": f"{ib['nr']}/{p['id']}", "datum": ib["daten"].get("datum", ""),
                              "bauteil": p.get("gruppe", ""),
                              "beschreibung": f"{p['text']}: Ist {p.get('ist', '') or 'n. i. O.'}",
                              "herkunft": ib["nr"]})
        return funde

    def abweichungen_uebernehmen(self, id_: int) -> tuple[dict, int]:
        from .qualitaet import tabellen as Q
        d = self.qdok("abweichung", id_)
        n = Q.abweichungen_uebernehmen(d["daten"], self.abweichungen_funde())
        return (self.qdok_speichern("abweichung", id_, d["daten"]) if n else d), n

    # ================================================================ Fertigung & Kosten (MS9)
    def kostensaetze(self) -> dict:
        """Stundensätze, Materialpreise (€/kg) und Zukaufpreise (€/Stück) des Projekts – Vorgabe: Schätzwerte."""
        from .fertigung import arbeitsplan as A
        saetze = A.standard_saetze()
        gespeichert = json.loads(self.meta("kostensaetze", "{}") or "{}")
        for k in saetze:
            saetze[k].update(gespeichert.get(k, {}))
        return saetze

    def kostensaetze_speichern(self, saetze: dict) -> None:
        self._setze_meta("kostensaetze", json.dumps(saetze, ensure_ascii=False))
        self._db.commit()

    def arbeitsplan_von_teil(self, teil_id: int) -> dict | None:
        z = self._db.execute("SELECT id FROM arbeitsplan WHERE teil_id=?", (teil_id,)).fetchone()
        return self.arbeitsplan(z[0]) if z else None

    def arbeitsplan(self, id_: int) -> dict:
        a = self.objekt("arbeitsplan", id_)
        a["daten"] = json.loads(a["daten"])
        return a

    def arbeitsplaene(self) -> list[dict]:
        liste = self.liste("arbeitsplan")
        for a in liste:
            a["daten"] = json.loads(a["daten"])
        return liste

    def arbeitsplan_vorschlag(self, teil_id: int) -> dict:
        from .fertigung import arbeitsplan as A
        t = self.teil(teil_id)
        return A.vorschlag(self.teil_form(teil_id)["form"], t["werkstoff"], t["name"], t["vorlage"])

    def kalkulation_teil(self, teil_id: int, daten: dict | None = None):
        """Kalkulation eines Bauteils aus seinem (oder dem übergebenen) Arbeitsplan."""
        from .cad.geometrie import eigenschaften
        from .fertigung import arbeitsplan as A
        if daten is None:
            a = self.arbeitsplan_von_teil(teil_id)
            if a is None:
                return None
            daten = a["daten"]
        roh = daten.get("rohteil", {})
        vol = fl = 0.0
        if roh.get("art") not in ("Rundstahl", "Flachstahl", "Blech"):
            e = eigenschaften(self.teil_form(teil_id)["form"])
            vol, fl = e.volumen, e.flaeche
        return A.kalkulieren(daten, self.kostensaetze(), vol, fl)

    def arbeitsplan_speichern(self, teil_id: int, daten: dict) -> dict:
        """Arbeitsplan eines Bauteils anlegen oder als neue Version speichern (verknüpft mit dem Teil)."""
        t = self.teil(teil_id)
        k = self.kalkulation_teil(teil_id, daten)
        kosten = k.stueck if k else None
        name = f"{t['nr']} {t['name']}"
        text = json.dumps(daten, ensure_ascii=False)
        alt = self.arbeitsplan_von_teil(teil_id)
        if alt is None:
            aid = self.objekt_neu("arbeitsplan", teil_id=teil_id, name=name, daten=text, kosten=kosten)["id"]
            self.verknuepfen("teil", teil_id, "arbeitsplan", aid, "Bauteil")
        else:
            aid = alt["id"]
            self._db.execute("UPDATE arbeitsplan SET name=?, daten=?, kosten=?, version=version+1, status='Entwurf', "
                             "geaendert=? WHERE id=?", (name, text, kosten, _jetzt(), aid))
            self._protokollieren("arbeitsplan", aid, f"Version {alt['version'] + 1}: gespeichert")
        self._db.commit()
        return self.arbeitsplan(aid)

    def anfrage_eintraege(self) -> list[dict]:
        """Alle Teile mit Fremdfertigung für die Anfrageliste (Lastenheft M37)."""
        from .fertigung import arbeitsplan as A
        out = []
        for ap in self.arbeitsplaene():
            d = ap["daten"]
            if d.get("fertigung") != "fremd":
                continue
            t = self.teil(ap["teil_id"])
            verfahren = ", ".join(A.ARTEN.get(v["art"], (v["art"],))[0] for v in d.get("vorgaenge", [])
                                  if v["art"] not in ("manuell",)) or "nach Zeichnung"
            out.append({"nr": t["nr"], "benennung": t["name"], "werkstoff": t["werkstoff"],
                        "rohteil": A.rohteil_text(d.get("rohteil", {})), "verfahren": verfahren,
                        "menge": int(d.get("losgroesse") or 1), "teil_id": t["id"]})
        return out

    def kalkulation_baugruppe(self, baugruppe_id: int, anzahl: int = 1):
        """(Zeilen, Summe, fehlende Preise, Kalkulationen je Bauteil) für eine gespeicherte Baugruppe."""
        from .fertigung import arbeitsplan as A
        g = self.baugruppe(baugruppe_id)
        r = self.baugruppe_bauen(g["definition"])
        kalk = {}
        for t in self.teile():
            k = self.kalkulation_teil(t["id"])
            if k is not None:
                kalk[t["nr"]] = k
        zeilen, summe, fehlend = A.baugruppe_kalkulieren(r.stueckliste, kalk, self.kostensaetze(), anzahl)
        return zeilen, summe, fehlend, kalk

    # ================================================================ Allgemeine Objekte (MS3)
    _FELDER = {
        "idee": {"titel", "problem", "nutzen", "beschreibung", "ier", "ressourcen", "bild"},
        "widerspruch": {"idee_id", "art", "beschreibung", "verbessern", "verschlechtern", "prinzipien"},
        "loesungsidee": {"widerspruch_id", "prinzip", "text"},
        "funktion": {"eltern_id", "name", "beschreibung", "reihenfolge"},
        "variante": {"name", "beschreibung"},
        "teil": {"vorlage", "name", "parameter", "werkstoff", "masse", "volumen"},
        "baugruppe": {"name", "definition", "masse"},
        "arbeitsplan": {"teil_id", "name", "daten", "kosten"},
        "montageplan": {"baugruppe_id", "name", "daten"},
        "inbetriebnahme": {"name", "daten"},
        "wartungsplan": {"name", "daten"},
        "pruefplan": {"teil_id", "name", "daten"},
        "fmea": {"art", "name", "daten"},
        "risiko": {"art", "name", "daten"},
        "normen": {"art", "name", "daten"},
        "abweichung": {"art", "name", "daten"},
        "aufgabe": {"titel", "verantwortlich", "start", "termin", "stand", "phase", "objekt_typ", "objekt_id",
                    "meilenstein", "kosten_plan", "kosten_ist", "notiz"},
    }
    _FELD_NAMEN = {"titel": "Titel", "problem": "Problem", "nutzen": "Nutzen", "beschreibung": "Beschreibung",
                   "ier": "Ideales Endergebnis", "ressourcen": "Ressourcen", "bild": "Bild",
                   "verbessern": "Parameter verbessern", "verschlechtern": "Parameter verschlechtert sich",
                   "prinzip": "Prinzip", "text": "Text", "name": "Name", "eltern_id": "Einordnung",
                   "reihenfolge": "Reihenfolge", "art": "Art", "idee_id": "Idee", "widerspruch_id": "Widerspruch",
                   "prinzipien": "Prinzipien", "verantwortlich": "Verantwortlich", "start": "Start",
                   "termin": "Termin", "stand": "Stand", "phase": "Phase", "kosten_plan": "Kosten Plan",
                   "kosten_ist": "Kosten Ist", "notiz": "Notiz", "meilenstein": "Meilenstein"}

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
        elif typ == "teil":
            ap = self.arbeitsplan_von_teil(id_)
            if ap:
                self.objekt_loeschen("arbeitsplan", ap["id"])
            pp = self.pruefplan_von_teil(id_)
            if pp:
                self.objekt_loeschen("pruefplan", pp["id"])
        elif typ == "baugruppe":
            mp = self.montageplan_von_baugruppe(id_)
            if mp:
                self.objekt_loeschen("montageplan", mp["id"])
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
