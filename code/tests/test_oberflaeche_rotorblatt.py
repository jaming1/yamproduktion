"""K3-Oberfläche: Rotorblatt nach BEM mit Werten aus der Rotorauslegung; Kette bei Änderung; Screenshots 110–119."""
from pathlib import Path

from PySide6.QtWidgets import QApplication, QScrollArea

from yamproduktion.modell import NEU_PRUEFEN, Projekt
from yamproduktion.ui import thema

from test_oberflaeche import app, bild, fenster  # noqa: F401


def nach_unten(seite, anteil: float):
    """Seite scrollen, damit Tabelle und Diagramm im Screenshot zu sehen sind."""
    leiste = seite.findChild(QScrollArea).verticalScrollBar()
    leiste.setValue(int(leiste.maximum() * anteil))
    QApplication.processEvents()


def test_rotorblatt_bem(fenster, tmp_path, app):  # noqa: F811
    projekt = Projekt.neu(tmp_path / "KWA", "Kleinwindanlage KWA-5", "Mini-Windkraftanlage 5 kW", beispiel_kwa=True)
    fenster.projekt_laden(projekt)

    fenster.gehe_zu("rotor")
    fenster.rotor.aus_anforderungen()
    assert fenster.rotor.protokoll_speichern(str(tmp_path / "B-001.pdf"))
    rotor_b = projekt.berechnungen()[0]
    durchmesser = rotor_b.ergebnis["ergebnisse"][0]["wert"]

    fenster.gehe_zu("rotorblatt")
    s = fenster.rechenseiten["rotorblatt"]
    assert fenster.stapel.currentWidget() is s
    s.aus_anforderungen()
    assert abs(s.werte().durchmesser_m - durchmesser) < 1e-9          # exakt übernommen, nicht gerundet
    assert "B-001" in s.verknuepft.text()
    assert s.ergebnis.alles_erfuellt, [p.titel for p in s.ergebnis.pruefungen if not p.erfuellt]
    assert s.unbelegt.isVisible() and s.diagramm.isVisible() and s.tabellen_box.isVisible()
    bild(fenster, "110_rotorblatt_hell")
    nach_unten(s, 0.45)
    bild(fenster, "111_rotorblatt_kennlinie_hell")
    nach_unten(s, 0.75)
    bild(fenster, "112_rotorblatt_tabelle_hell")
    nach_unten(s, 0)

    # Profil mit schlechter Gleitzahl: Prüfung gegen cp der Rotorauslegung schlägt an
    s.eingaben["gleitzahl"].setValue(10)
    assert not s.ergebnis.alles_erfuellt
    bild(fenster, "113_rotorblatt_pruefung_hell")
    s.eingaben["gleitzahl"].setValue(60)
    assert s.ergebnis.alles_erfuellt

    pdf = s.protokoll_speichern(str(tmp_path / "B-002.pdf"))
    assert pdf and Path(pdf).stat().st_size > 5000
    Path(__file__).with_name("screenshots").joinpath("Rotorblatt_Beispiel.pdf").write_bytes(Path(pdf).read_bytes())
    blatt_b = projekt.berechnungen()[0]
    assert blatt_b.typ == "rotorblatt_bem"
    assert "B-001" in {b.nr for b in projekt.haengt_ab_von("berechnung", blatt_b.id)}

    # Nennleistung 5 → 10 kW: Rotorauslegung und Rotorblatt werden markiert und neu gerechnet
    projekt.anforderung_aendern(projekt.anforderung_suchen("nennleistung").id, zielwert=10)
    markiert = {b.nr for b in projekt.neu_zu_pruefen() if b.typ == "berechnung"}
    assert {"B-001", "B-002"} <= markiert
    fenster.gehe_zu("berechnungen")
    bild(fenster, "114_rotorblatt_kette_hell")
    fenster.berechnungen.alle_neu_rechnen()
    assert all(b.status != NEU_PRUEFEN for b in projekt.berechnungen())
    neu = projekt.berechnung(blatt_b.id)
    assert neu.eingaben["durchmesser_m"] > durchmesser

    # Dunkel
    fenster.thema_setzen("dunkel")
    fenster.gehe_zu("rotorblatt")
    bild(fenster, "115_rotorblatt_dunkel")
    nach_unten(s, 0.45)
    bild(fenster, "116_rotorblatt_kennlinie_dunkel")
    nach_unten(s, 0.75)
    bild(fenster, "117_rotorblatt_tabelle_dunkel")
    nach_unten(s, 0)
    thema.anwenden(app, "hell")
