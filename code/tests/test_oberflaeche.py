"""Oberflächen-Test mit Screenshots (hell und dunkel), siehe Projekt-Standard."""
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from yamproduktion.modell import NEU_PRUEFEN, Projekt
from yamproduktion.ui import thema
from yamproduktion.ui.hauptfenster import Hauptfenster

BILDER = Path(__file__).parent / "screenshots"


@pytest.fixture(scope="module")
def app():
    a = QApplication.instance() or QApplication([])
    yield a


@pytest.fixture
def fenster(app, tmp_path):
    einst = QSettings(str(tmp_path / "einst.ini"), QSettings.IniFormat)
    thema.anwenden(app, "hell")
    f = Hauptfenster(einst)
    f.resize(1440, 900)
    f.show()
    app.processEvents()
    yield f
    f.close()


def bild(fenster, name):
    BILDER.mkdir(exist_ok=True)
    for _ in range(3):          # verschachtelte Layouts brauchen mehrere Durchläufe
        QApplication.processEvents()
    fenster.grab().save(str(BILDER / f"{name}.png"))


def test_ablauf_mit_screenshots(fenster, tmp_path, app):
    bild(fenster, "01_willkommen_hell")
    projekt = Projekt.neu(tmp_path / "KWA", "Kleinwindanlage KWA-5", "Mini-Windkraftanlage 5 kW", beispiel_kwa=True)
    fenster.projekt_laden(projekt)
    assert fenster.stapel.currentWidget() is fenster.uebersicht
    assert not fenster.uebersicht.warnung.isVisible()
    bild(fenster, "02_uebersicht_hell")

    # MS1: Rotorauslegung mit Werten aus den Anforderungen, PDF speichern → Verknüpfung entsteht
    fenster.gehe_zu("rotor")
    fenster.rotor.aus_anforderungen()
    assert fenster.rotor.eingaben["leistung_el_kw"].value() == 5
    bild(fenster, "03_rotor_hell")
    pdf = fenster.rotor.protokoll_speichern(str(tmp_path / "B-001.pdf"))
    assert Path(pdf).exists()
    b = projekt.berechnungen()[0]
    assert {q.nr for q in projekt.haengt_ab_von("berechnung", b.id)} == {"A-001", "A-002"}
    assert "Verknüpft mit A-001, A-002" in fenster.statusBar().currentMessage()

    # MS2: Anforderung 5 → 10 kW ändern
    fenster.gehe_zu("anforderungen")
    seite = fenster.anforderungen
    assert seite.tabelle.rowCount() == 7
    seite.tabelle.item(0, seite.SP_WERT).setText("10")
    assert projekt.anforderungen()[0].zielwert == 10
    assert projekt.berechnung(b.id).status == NEU_PRUEFEN
    assert "Neu prüfen: B-001" in fenster.statusBar().currentMessage()
    # falsche Einheit → Fehlermeldung, Wert bleibt
    seite.tabelle.item(0, seite.SP_EINHEIT).setText("Kilowattt")
    assert projekt.anforderungen()[0].einheit == "kW"
    assert "keine bekannte Einheit" in fenster.statusBar().currentMessage()
    seite.auswaehlen(projekt.anforderungen()[0].id)
    bild(fenster, "04_anforderungen_rueckverfolgung_hell")

    fenster.gehe_zu("uebersicht")
    assert fenster.uebersicht.warnung.isVisible()
    bild(fenster, "05_uebersicht_warnung_hell")

    # Sprung aus der Rückverfolgung zur Berechnung, dann neu berechnen
    fenster.gehe_zu_objekt("berechnung", b.id)
    assert fenster.stapel.currentWidget() is fenster.berechnungen
    bild(fenster, "06_berechnungen_neu_pruefen_hell")
    fenster.berechnungen.ausgewaehlte_neu_rechnen()
    b = projekt.berechnung(b.id)
    assert b.status == "Entwurf" and b.version == 2
    assert b.ergebnis["ergebnisse"][0]["wert"] == pytest.approx(6.778, rel=0.01)
    fenster.berechnungen._status("geprüft")
    assert projekt.berechnung(b.id).status == "geprüft"
    assert fenster.berechnungen.pdf_erzeugen(str(tmp_path / "B-001_v2.pdf")).exists()

    # Phasentore freigeben
    projekt.funktion_neu("Wind in Strom wandeln")
    fenster.gehe_zu("uebersicht")
    fenster.uebersicht._freigeben("P2")
    fenster.uebersicht._freigeben("P4")
    assert projekt.phase("P2").status == "freigegeben" and projekt.phase("P4").status == "freigegeben"
    assert not fenster.uebersicht.warnung.isVisible()
    bild(fenster, "07_uebersicht_freigegeben_hell")

    fenster.thema_setzen("dunkel")
    bild(fenster, "08_uebersicht_dunkel")
    fenster.gehe_zu("berechnungen")
    bild(fenster, "09_berechnungen_dunkel")
    fenster.gehe_zu("anforderungen")
    bild(fenster, "10_anforderungen_dunkel")
    fenster.gehe_zu("rotor")
    bild(fenster, "11_rotor_dunkel")

    # Seitenleiste einklappen und Zustand merken
    fenster.seitenleiste_umschalten()
    assert not fenster.seitenleiste.isVisible()
    assert fenster.einst.value("seitenleiste", type=bool) is False
    bild(fenster, "12_ohne_seitenleiste_dunkel")
    thema.anwenden(app, "hell")


def test_falsche_eingabe_wird_erkannt(fenster):
    fenster.rotor.eingaben["cp"].setValue(0.99)
    assert fenster.rotor.ergebnis is not None
    assert not fenster.rotor.ergebnis.alles_erfuellt
