"""Hauptfenster: einklappbare Seitenleiste + große Arbeitsfläche (N7)."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtCore import QUrl
from PySide6.QtGui import QAction, QActionGroup, QDesktopServices, QFont, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
    QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

from .. import APP_NAME, __version__
from ..modell import DATEIENDUNG, Projekt, ProjektFehler
from ..wissen import yamaktaba as Y
from . import thema
from .berechnungen_seite import BerechnungenSeite
from .cad_seite import BauteilSeite
from .arbeitsplan_seite import ArbeitsplanSeite
from .cam_seite import CamSeite
from .montage_seite import MontageSeite
from .betrieb_seiten import InbetriebnahmeSeite, WartungSeite
from .planung_seiten import AufgabenSeite, BudgetSeite
from .qualitaet_seiten import DokuSeite, PruefplanSeite, TabellenSeite
from .baugruppen_seite import BaugruppenSeite
from .kollision_seite import KollisionSeite
from .modellier_seite import ModellierSeite
from .kosten_seite import KostenSeite
from .konzept_seiten import FunktionenSeite, IdeenSeite, KonzeptSeite
from .rechen_seite import RechenSeite
from .seiten import AnforderungenSeite, NeuesProjektDialog, UebersichtSeite, WillkommenSeite
from .werkstoff_seite import WerkstoffSeite
from .wissen_seite import WissenSeite
from .abnahme_seite import AbnahmeSeite
from .zeichnung_seite import ZeichnungSeite

# (Text, Schlüssel); Schlüssel None = Gruppenüberschrift (nicht wählbar)
NAVIGATION = [
    ("Übersicht", "uebersicht"),
    ("Ideen & TRIZ", "ideen"),
    ("Anforderungen", "anforderungen"),
    ("Funktionen", "funktionen"),
    ("Konzept", "konzept"),
    ("Berechnungen", "berechnungen"),
    ("WINDKRAFT", None),
    ("   Rotorauslegung", "rotor"),
    ("   Leistungskurve & Ertrag", "ertrag"),
    ("   Lastannahmen", "lasten"),
    ("   Antriebsstrang", "antrieb"),
    ("   Rotorblatt (BEM)", "rotorblatt"),
    ("MASCHINENELEMENTE", None),
    ("   Welle", "welle"),
    ("   Lager", "lager"),
    ("   Schrauben", "schrauben"),
    ("   Passfeder", "passfeder"),
    ("   Pressverband", "pressverband"),
    ("   Schweißnaht", "schweissnaht"),
    ("   Getriebe", "getriebe"),
    ("   Turm & Fundament", "turm"),
    ("   Bremse", "bremse"),
    ("KONSTRUKTION", None),
    ("   Bauteile (3D)", "bauteile"),
    ("   Modellieren", "modellieren"),
    ("   Baugruppen", "baugruppen"),
    ("   Kollision & Schwerpunkt", "kollision"),
    ("   Zeichnungen", "zeichnungen"),
    ("FERTIGUNG", None),
    ("   Arbeitspläne", "arbeitsplaene"),
    ("   CAM-Export (G-Code)", "cam"),
    ("   Kosten & Anfragen", "kosten"),
    ("MONTAGE", None),
    ("   Montagepläne", "montage"),
    ("BETRIEB", None),
    ("   Inbetriebnahme", "inbetriebnahme"),
    ("   Wartung", "wartung"),
    ("QUALITÄT & SICHERHEIT", None),
    ("   Prüfpläne", "pruefplaene"),
    ("   FMEA", "fmea"),
    ("   Abweichungen", "abweichung"),
    ("   Risikobeurteilung", "risiko"),
    ("   Normen", "normen"),
    ("   Technische Doku", "doku"),
    ("PROJEKTMANAGEMENT", None),
    ("   Aufgaben & Zeitplan", "aufgaben"),
    ("   Kosten Plan/Ist", "budget"),
    ("   Abnahme Version 1", "abnahme"),
    ("WISSEN", None),
    ("   Bibliothek", "bibliothek"),
    ("Werkstoffe", "werkstoffe"),
]
RECHENSEITEN = {"rotor": "rotorauslegung", "ertrag": "ertrag", "lasten": "lasten_iec", "antrieb": "antrieb",
                "rotorblatt": "rotorblatt_bem",
                **{t: t for t in ("welle", "lager", "schrauben", "passfeder", "pressverband", "schweissnaht",
                                  "getriebe", "turm", "bremse")}}


class Hauptfenster(QMainWindow):
    def __init__(self, einstellungen: QSettings | None = None):
        super().__init__()
        self.einst = einstellungen or QSettings()
        self.projekt: Projekt | None = None
        self.setWindowTitle(APP_NAME)
        self.resize(1400, 900)

        # Seiten
        self.willkommen = WillkommenSeite()
        self.uebersicht = UebersichtSeite()
        self.anforderungen = AnforderungenSeite()
        self.rechenseiten = {k: RechenSeite(typ) for k, typ in RECHENSEITEN.items()}
        self.rotor = self.rechenseiten["rotor"]
        self.werkstoffe = WerkstoffSeite()
        self.bauteile = BauteilSeite()
        self.modellieren = ModellierSeite()
        self.baugruppen = BaugruppenSeite()
        self.kollision = KollisionSeite()
        self.zeichnungen = ZeichnungSeite()
        self.arbeitsplaene = ArbeitsplanSeite()
        self.cam = CamSeite()
        self.kosten = KostenSeite()
        self.montage = MontageSeite()
        self.inbetriebnahme = InbetriebnahmeSeite()
        self.wartung = WartungSeite()
        self.pruefplaene = PruefplanSeite()
        self.qseiten = {t: TabellenSeite(t) for t in ("fmea", "abweichung", "risiko", "normen")}
        self.doku = DokuSeite()
        self.aufgaben = AufgabenSeite()
        self.budget = BudgetSeite()
        self.bibliothek = WissenSeite(self.einst)
        self.abnahme = AbnahmeSeite(self.bibliothek.buecher_gesamt)
        self.berechnungen = BerechnungenSeite()
        self.ideen = IdeenSeite()
        self.funktionen = FunktionenSeite()
        self.konzept = KonzeptSeite()
        self.stapel = QStackedWidget()
        self.seiten = {"willkommen": self.willkommen, "uebersicht": self.uebersicht,
                       "anforderungen": self.anforderungen, "berechnungen": self.berechnungen,
                       "rotor": self.rotor, "ideen": self.ideen, "funktionen": self.funktionen,
                       "konzept": self.konzept, "werkstoffe": self.werkstoffe,
                       "bauteile": self.bauteile, "modellieren": self.modellieren,
                       "baugruppen": self.baugruppen, "kollision": self.kollision, "zeichnungen": self.zeichnungen,
                       "arbeitsplaene": self.arbeitsplaene, "cam": self.cam, "kosten": self.kosten, "montage": self.montage,
                       "inbetriebnahme": self.inbetriebnahme, "wartung": self.wartung,
                       "pruefplaene": self.pruefplaene, **self.qseiten, "doku": self.doku,
                       "aufgaben": self.aufgaben, "budget": self.budget,
                       "bibliothek": self.bibliothek, "abnahme": self.abnahme, **self.rechenseiten}
        for s in self.seiten.values():
            self.stapel.addWidget(s)

        # Seitenleiste
        self.seitenleiste = QFrame()
        self.seitenleiste.setObjectName("Seitenleiste")
        self.seitenleiste.setFixedWidth(260)
        sl = QVBoxLayout(self.seitenleiste)
        sl.setContentsMargins(0, 8, 0, 8)
        self.projekt_label = QLabel("Kein Projekt geöffnet")
        self.projekt_label.setObjectName("ProjektName")
        self.projekt_label.setWordWrap(True)
        sl.addWidget(self.projekt_label)
        self.nav = QListWidget()
        for text, schluessel in NAVIGATION:
            eintrag = QListWidgetItem(text.strip() if schluessel is None else text)
            if schluessel is None:
                eintrag.setFlags(Qt.NoItemFlags)
                schrift = eintrag.font()
                schrift.setPixelSize(11)
                schrift.setBold(True)
                schrift.setLetterSpacing(QFont.PercentageSpacing, 108)
                eintrag.setFont(schrift)
                eintrag.setData(Qt.AccessibleTextRole, f"Gruppe {text.strip()}")
            elif text.startswith("   "):
                schrift = eintrag.font()
                schrift.setPixelSize(14)
                eintrag.setFont(schrift)
            self.nav.addItem(eintrag)
        self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.nav.currentRowChanged.connect(self._nav_gewaehlt)
        sl.addWidget(self.nav, 1)

        # Kopfzeile
        kopf = QFrame()
        kopf.setObjectName("Kopfzeile")
        kl = QHBoxLayout(kopf)
        kl.setContentsMargins(8, 4, 12, 4)
        self.leisten_knopf = QPushButton("☰")
        self.leisten_knopf.setObjectName("Werkzeug")
        self.leisten_knopf.setToolTip("Seitenleiste ein-/ausblenden (⌘B)")
        self.leisten_knopf.clicked.connect(self.seitenleiste_umschalten)
        kl.addWidget(self.leisten_knopf)
        self.kopf_titel = QLabel(APP_NAME)
        kl.addWidget(self.kopf_titel, 1)
        self.thema_knopf = QPushButton("◐")
        self.thema_knopf.setObjectName("Werkzeug")
        self.thema_knopf.setToolTip("Hell / Dunkel umschalten (⌘⇧D)")
        self.thema_knopf.clicked.connect(self.thema_umschalten)
        kl.addWidget(self.thema_knopf)

        rechts = QWidget()
        rl = QVBoxLayout(rechts)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)
        rl.addWidget(kopf)
        rl.addWidget(self.stapel, 1)

        mitte = QWidget()
        ml = QHBoxLayout(mitte)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(0)
        ml.addWidget(self.seitenleiste)
        ml.addWidget(rechts, 1)
        self.setCentralWidget(mitte)

        # Verbindungen
        self.willkommen.neu_angefordert.connect(self.neues_projekt)
        self.willkommen.oeffnen_angefordert.connect(self.projekt_oeffnen)
        self.uebersicht.gehe_zu.connect(self.gehe_zu)
        self.uebersicht.gehe_zu_objekt.connect(self.gehe_zu_objekt)
        for seite in self._arbeitsseiten():
            seite.meldung.connect(self.melden)
        for seite in (self.ideen, self.funktionen, self.konzept):
            seite.geaendert.connect(self.uebersicht.aktualisieren)
            seite.gehe_zu_objekt.connect(self.gehe_zu_objekt)
        self.anforderungen.geaendert.connect(self.uebersicht.aktualisieren)
        self.berechnungen.geaendert.connect(self.uebersicht.aktualisieren)
        for seite in self.rechenseiten.values():
            seite.gespeichert.connect(self.uebersicht.aktualisieren)
            seite.gespeichert.connect(lambda: self.berechnungen.laden())
        self.berechnungen.neue_berechnung.connect(self._rechenseite_oeffnen)
        self.bauteile.gespeichert.connect(self.uebersicht.aktualisieren)
        self.bauteile.frei_oeffnen.connect(self._freies_teil_oeffnen)
        self.modellieren.gespeichert.connect(self.uebersicht.aktualisieren)
        self.baugruppen.gespeichert.connect(self.uebersicht.aktualisieren)
        self.baugruppen.zeichnung_oeffnen.connect(self.zeichnung_oeffnen)
        self.arbeitsplaene.gespeichert.connect(self.uebersicht.aktualisieren)
        self.cam.gespeichert.connect(self.uebersicht.aktualisieren)
        self.montage.gespeichert.connect(self.uebersicht.aktualisieren)
        self.inbetriebnahme.gespeichert.connect(self.uebersicht.aktualisieren)
        self.wartung.gespeichert.connect(self.uebersicht.aktualisieren)
        self.pruefplaene.gespeichert.connect(self.uebersicht.aktualisieren)
        for q in (*self.qseiten.values(), self.aufgaben, self.budget):
            q.gespeichert.connect(self.uebersicht.aktualisieren)
        self.aufgaben.gehe_zu_objekt.connect(self.gehe_zu_objekt)
        self.bibliothek.gespeichert.connect(lambda: self.berechnungen.laden())
        self.abnahme.gehe_zu.connect(self.gehe_zu)
        self.abnahme.exportieren.connect(lambda: self.projekt_exportieren())
        self.abnahme.archivieren.connect(lambda: self.projekt_archivieren())
        self.bibliothek.gespeichert.connect(self.uebersicht.aktualisieren)
        self.kosten.arbeitsplan_oeffnen.connect(self.arbeitsplan_oeffnen)
        self.anforderungen.gehe_zu_objekt.connect(self.gehe_zu_objekt)
        self.berechnungen.gehe_zu_objekt.connect(self.gehe_zu_objekt)

        self._menue()
        self.statusBar().showMessage("Bereit.")
        self.seitenleiste.setVisible(self.einst.value("seitenleiste", True, type=bool))
        self._projekt_zustand()

    def _arbeitsseiten(self):
        return (self.uebersicht, self.ideen, self.anforderungen, self.funktionen, self.konzept,
                *self.rechenseiten.values(), self.berechnungen, self.bauteile, self.modellieren,
                self.baugruppen, self.kollision, self.zeichnungen, self.arbeitsplaene, self.cam, self.kosten, self.montage,
                self.inbetriebnahme, self.wartung, self.pruefplaene, *self.qseiten.values(), self.doku,
                self.aufgaben, self.budget, self.bibliothek, self.abnahme)

    def _rechenseite_oeffnen(self, typ: str):
        for schluessel, t in RECHENSEITEN.items():
            if t == typ:
                self.gehe_zu(schluessel)

    # ---------- Menü & Tastenkürzel ----------
    def _menue(self):
        datei = self.menuBar().addMenu("Ablage")
        for text, kuerzel, funktion in (("Neues Projekt …", QKeySequence.New, self.neues_projekt),
                                        ("Projekt öffnen …", QKeySequence.Open, self.projekt_oeffnen),
                                        ("Projekt schließen", QKeySequence.Close, self.projekt_schliessen)):
            a = QAction(text, self)
            a.setShortcut(kuerzel)
            a.triggered.connect(funktion)
            datei.addAction(a)
        datei.addSeparator()
        self.export_aktion = QAction("Projekt exportieren (Archiv) …", self)
        self.export_aktion.setShortcut("Ctrl+E")
        self.export_aktion.triggered.connect(lambda: self.projekt_exportieren())
        datei.addAction(self.export_aktion)
        self.archiv_aktion = QAction("In Yamaktaba archivieren …", self)
        self.archiv_aktion.triggered.connect(lambda: self.projekt_archivieren())
        datei.addAction(self.archiv_aktion)
        imp = QAction("Projekt importieren …", self)
        imp.triggered.connect(lambda: self.projekt_importieren())
        datei.addAction(imp)
        datei.addSeparator()
        sichern = QAction("Sicherung jetzt anlegen", self)
        sichern.triggered.connect(self.sicherung_anlegen)
        datei.addAction(sichern)
        ordner = QAction("Sicherungen im Finder zeigen", self)
        ordner.triggered.connect(self.sicherungen_zeigen)
        datei.addAction(ordner)

        ansicht = self.menuBar().addMenu("Darstellung")
        leiste = QAction("Seitenleiste ein-/ausblenden", self)
        leiste.setShortcut("Ctrl+B")
        leiste.triggered.connect(self.seitenleiste_umschalten)
        ansicht.addAction(leiste)
        ansicht.addSeparator()
        gruppe = QActionGroup(self)
        aktuell = self.einst.value("thema", "auto")
        self.thema_aktionen = {}
        for text, modus in (("Automatisch (wie macOS)", "auto"), ("Hell", "hell"), ("Dunkel", "dunkel")):
            a = QAction(text, self, checkable=True)
            a.setChecked(modus == aktuell)
            a.triggered.connect(lambda _=False, m=modus: self.thema_setzen(m))
            gruppe.addAction(a)
            ansicht.addAction(a)
            self.thema_aktionen[modus] = a
        umschalten = QAction("Hell / Dunkel umschalten", self)
        umschalten.setShortcut("Ctrl+Shift+D")
        umschalten.triggered.connect(self.thema_umschalten)
        ansicht.addAction(umschalten)

        hilfe = self.menuBar().addMenu("Hilfe")
        info = QAction(f"Über {APP_NAME}", self)
        info.triggered.connect(lambda: QMessageBox.about(
            self, APP_NAME, f"{APP_NAME} {__version__}\nProduktentwicklung von der Idee bis zur Inbetriebnahme."))
        hilfe.addAction(info)

    # ---------- Darstellung ----------
    def seitenleiste_umschalten(self):
        sichtbar = not self.seitenleiste.isVisible()
        self.seitenleiste.setVisible(sichtbar)
        self.einst.setValue("seitenleiste", sichtbar)

    def thema_setzen(self, modus: str):
        self.einst.setValue("thema", modus)
        thema.anwenden(QApplication.instance(), modus)
        if modus in self.thema_aktionen:
            self.thema_aktionen[modus].setChecked(True)
        for seite in self.rechenseiten.values():
            seite.berechnen()  # Prüf-Hinweise mit neuen Farben neu aufbauen

    def thema_umschalten(self):
        jetzt = thema.aktuelles_schema(self.einst.value("thema", "auto"))
        self.thema_setzen("hell" if jetzt == "dunkel" else "dunkel")

    def melden(self, text: str, fehler: bool = False):
        self.statusBar().showMessage(("⚠️  " if fehler else "✓  ") + text, 0 if fehler else 6000)

    # ---------- Navigation ----------
    def _nav_gewaehlt(self, zeile: int):
        if zeile < 0 or not self.projekt:
            return
        text, schluessel = NAVIGATION[zeile]
        if schluessel is None:
            return
        self.stapel.setCurrentWidget(self.seiten[schluessel])
        self.kopf_titel.setText(f"{self.projekt.name}  ›  {text.strip()}")
        if schluessel == "anforderungen":
            self.anforderungen.laden()
        elif schluessel == "berechnungen":
            self.berechnungen.laden()
        elif schluessel == "uebersicht":
            self.uebersicht.aktualisieren()
        elif schluessel in ("ideen", "funktionen", "konzept"):
            self.seiten[schluessel].laden()
        elif schluessel == "bauteile":
            self.bauteile.laden()
        elif schluessel == "modellieren":
            self.modellieren.laden()
        elif schluessel in ("baugruppen", "kollision", "zeichnungen", "arbeitsplaene", "cam", "kosten", "montage", "inbetriebnahme", "wartung",
                            "pruefplaene", "fmea", "abweichung", "risiko", "normen", "doku", "aufgaben", "budget",
                            "bibliothek", "abnahme"):
            self.seiten[schluessel].laden()
        elif schluessel in RECHENSEITEN and self.projekt:
            self.seiten[schluessel]._verknuepfung_zeigen()

    def gehe_zu(self, schluessel: str):
        for i, (_, s) in enumerate(NAVIGATION):
            if s == schluessel:
                self.nav.setCurrentRow(i)

    def gehe_zu_objekt(self, typ: str, id_: int):
        """Sprung aus der Rückverfolgung zu einem verknüpften Objekt."""
        if typ == "anforderung":
            self.gehe_zu("anforderungen")
            self.anforderungen.auswaehlen(id_)
        elif typ == "berechnung":
            self.gehe_zu("berechnungen")
            self.berechnungen.auswaehlen(id_)
        elif typ in ("idee", "widerspruch", "loesungsidee"):
            self.gehe_zu("ideen")
            self.ideen.auswaehlen(typ, id_)
        elif typ == "funktion":
            self.gehe_zu("funktionen")
            self.funktionen.auswaehlen(id_)
        elif typ == "variante":
            self.gehe_zu("konzept")
            self.konzept.auswaehlen_objekt(typ, id_)
        elif typ == "arbeitsplan":
            self.arbeitsplan_oeffnen(self.projekt.arbeitsplan(id_)["teil_id"])
        elif typ in ("inbetriebnahme", "wartungsplan"):
            seite = self.inbetriebnahme if typ == "inbetriebnahme" else self.wartung
            self.gehe_zu("inbetriebnahme" if typ == "inbetriebnahme" else "wartung")
            seite.laden_id(id_)
        elif typ == "aufgabe":
            self.gehe_zu("aufgaben")
        elif typ == "pruefplan":
            self.gehe_zu("pruefplaene")
            self.pruefplaene.teil_laden(self.projekt.pruefplan(id_)["teil_id"])
        elif typ in self.qseiten:
            self.gehe_zu(typ)
            self.qseiten[typ].laden_id(id_)
        elif typ == "montageplan":
            self.gehe_zu("montage")
            self.montage.baugruppe_laden(self.projekt.montageplan(id_)["baugruppe_id"])
        elif typ == "baugruppe":
            self.gehe_zu("baugruppen")
            self.baugruppen.baugruppe_laden(id_)
        elif typ == "teil":
            if self.projekt and self.projekt.teil(id_)["vorlage"] == "frei":
                self._freies_teil_oeffnen(id_)
            else:
                self.gehe_zu("bauteile")
                self.bauteile.teil_laden(id_)

    def arbeitsplan_oeffnen(self, teil_id: int):
        self.gehe_zu("arbeitsplaene")
        self.arbeitsplaene.teil_laden(teil_id)

    def zeichnung_oeffnen(self, typ: str, id_: int):
        self.gehe_zu("zeichnungen")
        self.zeichnungen.oeffnen(typ, id_)

    def _freies_teil_oeffnen(self, id_: int):
        self.gehe_zu("modellieren")
        self.modellieren.teil_laden(id_)

    # ---------- Sicherung ----------
    def sicherung_anlegen(self):
        if not self.projekt:
            return
        try:
            ziel = self.projekt.sicherung_anlegen()
            self.melden(f"Sicherung angelegt: {ziel.name}")
        except OSError as exc:
            self.melden(f"Sicherung fehlgeschlagen: {exc}", True)

    def sicherungen_zeigen(self):
        if self.projekt:
            self.projekt.sicherungsordner.mkdir(exist_ok=True)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.projekt.sicherungsordner)))

    # ---------- Projekte ----------
    def _projekt_zustand(self):
        offen = self.projekt is not None
        self.nav.setVisible(offen)
        if not offen:
            self.stapel.setCurrentWidget(self.willkommen)
            self.projekt_label.setText("Kein Projekt geöffnet")
            self.kopf_titel.setText(APP_NAME)
            self.setWindowTitle(APP_NAME)

    def projekt_laden(self, projekt: Projekt):
        if self.projekt:
            self.projekt.schliessen()
        self.projekt = projekt
        for seite in self._arbeitsseiten():
            seite.setze_projekt(projekt)
        self.projekt_label.setText(f"PROJEKT\n{projekt.name}")
        self.setWindowTitle(f"{projekt.name} – {APP_NAME}")
        self.einst.setValue("letztes_projekt", str(projekt.pfad))
        self._projekt_zustand()
        self.nav.setCurrentRow(-1)
        self.nav.setCurrentRow(0)
        self.melden(f"Projekt „{projekt.name}“ geöffnet. Alles wird automatisch gespeichert.")

    def neues_projekt(self):
        dialog = NeuesProjektDialog(self)
        if dialog.exec() != NeuesProjektDialog.Accepted:
            return
        try:
            projekt = Projekt.neu(dialog.pfad(), dialog.name.text(), dialog.produkt.text(),
                                  vorlage=dialog.vorlage.currentData())
        except (ProjektFehler, OSError) as exc:
            QMessageBox.warning(self, "Projekt konnte nicht angelegt werden", str(exc))
            return
        self.projekt_laden(projekt)

    def projekt_oeffnen(self, pfad: str | None = None):
        if not pfad:
            start = self.einst.value("letztes_projekt", "")
            pfad, _ = QFileDialog.getOpenFileName(self, "Projekt öffnen", str(Path(start).parent) if start else "",
                                                  f"YamProduktion-Projekt (*{DATEIENDUNG})")
            if not pfad:
                return
        try:
            self.projekt_laden(Projekt.oeffnen(pfad))
        except ProjektFehler as exc:
            QMessageBox.warning(self, "Projekt konnte nicht geöffnet werden", str(exc))

    def projekt_exportieren(self, ziel: str | None = None) -> Path | None:
        """K1: ganzes Projekt als ZIP (Projektdatei + erzeugte Unterlagen, ohne Buchinhalte)."""
        if not self.projekt:
            return None
        if ziel is None:
            vorschlag = self.projekt.pfad.parent / f"{self.projekt.pfad.stem}_{date.today():%Y-%m-%d}.zip"
            ziel, _ = QFileDialog.getSaveFileName(self, "Projekt exportieren", str(vorschlag), "Archiv (*.zip)")
            if not ziel:
                return None
        try:
            pfad = self.projekt.exportieren(ziel)
        except (OSError, ProjektFehler) as exc:
            QMessageBox.warning(self, "Export fehlgeschlagen", str(exc))
            return None
        self.melden(f"Projekt exportiert: {pfad.name} – ohne Buchscans.")
        return pfad

    def projekt_archivieren(self, fragen: bool = True) -> dict | None:
        """Projekt in Yamaktaba ablegen: Archiv-ZIP und Unterlagen (durchsuchbar) in der Sammlung des Projekts."""
        if not self.projekt:
            return None
        self.bibliothek.yk_laden()
        yk = self.bibliothek.yk
        if not yk:
            QMessageBox.warning(self, "Yamaktaba nicht gefunden",
                                "Bitte unter Wissen › Bibliothek den Yamaktaba-Ordner (ashamila) wählen.")
            return None
        n = len([d for d in self.projekt.dokumente() if d["pfad"].lower().endswith(".pdf")])
        if fragen and QMessageBox.question(
                self, "In Yamaktaba archivieren",
                f"„{self.projekt.name}“ als Archiv (ZIP) und {n} Unterlagen als durchsuchbare Bücher in Yamaktaba "
                f"ablegen (Kategorie „{Y.ARCHIV_KATEGORIE}“, Sammlung „YamProduktion: {self.projekt.name}“)?"
                ) != QMessageBox.Yes:
            return None
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            erg = yk.archivieren(self.projekt, lambda t: (self.statusBar().showMessage(t),
                                                         QApplication.processEvents()))
        except Exception as exc:
            QMessageBox.warning(self, "Archivieren fehlgeschlagen", str(exc))
            return None
        finally:
            QApplication.restoreOverrideCursor()
        self.melden(f"In Yamaktaba archiviert: {len(erg['neu'])} Unterlagen neu"
                    + (f", {len(erg['unveraendert'])} unverändert" if erg["unveraendert"] else "")
                    + f" – Sammlung „{erg['sammlung']}“.")
        return erg

    def projekt_importieren(self, archiv: str | None = None, ordner: str | None = None):
        if archiv is None:
            archiv, _ = QFileDialog.getOpenFileName(self, "Projekt importieren", str(Path.home()), "Archiv (*.zip)")
            if not archiv:
                return None
        if ordner is None:
            ordner = QFileDialog.getExistingDirectory(self, "Wohin entpacken?", str(Path(archiv).parent))
            if not ordner:
                return None
        try:
            projekt = Projekt.importieren(archiv, ordner)
        except (OSError, ProjektFehler) as exc:
            QMessageBox.warning(self, "Import fehlgeschlagen", str(exc))
            return None
        self.projekt_laden(projekt)
        return projekt

    def projekt_schliessen(self):
        if self.projekt:
            self.projekt.schliessen()
            self.projekt = None
            self.einst.setValue("letztes_projekt", "")
        self._projekt_zustand()
        self.melden("Projekt geschlossen.")

    def letztes_projekt_oeffnen(self):
        pfad = self.einst.value("letztes_projekt", "")
        if pfad and Path(pfad).exists():
            QTimer.singleShot(0, lambda: self.projekt_oeffnen(pfad))

    def closeEvent(self, event):
        if self.projekt:
            self.projekt.schliessen()
        super().closeEvent(event)
