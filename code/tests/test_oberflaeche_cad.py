"""MS6-Oberfläche: Hauptwelle, Flansch, Nabe und Zahnrad aus den Berechnungen; Schnitt; Export; Änderungskette."""
from pathlib import Path

from PySide6.QtWidgets import QScrollArea

from yamproduktion.cad import geometrie as G
from yamproduktion.modell import NEU_PRUEFEN, Projekt
from yamproduktion.ui import thema

from test_oberflaeche import app, bild, fenster  # noqa: F401

BEISPIELE = Path(__file__).with_name("screenshots")


def test_bauteile_aus_berechnungen(fenster, tmp_path, app):  # noqa: F811
    projekt = Projekt.neu(tmp_path / "KWA", "Kleinwindanlage KWA-5", "Mini-Windkraftanlage 5 kW", beispiel_kwa=True)
    fenster.projekt_laden(projekt)
    for schluessel in ("rotor", "lasten", "antrieb", "welle", "passfeder", "pressverband", "turm", "schrauben", "getriebe"):
        fenster.gehe_zu(schluessel)
        s = fenster.rechenseiten[schluessel]
        s.aus_anforderungen()
        assert s.protokoll_speichern(str(tmp_path / f"{schluessel}.pdf"))
    nr = {b.typ: b.nr for b in projekt.berechnungen()}

    fenster.gehe_zu("bauteile")
    s = fenster.bauteile
    assert fenster.stapel.currentWidget() is s

    # Hauptwelle: Durchmesser, Überhang, Lagerabstand aus der Wellenberechnung, Nabensitz aus der Passfeder
    s.vorlage.setCurrentIndex(s.vorlage.findData("welle"))
    s.aus_projekt()
    welle_b = next(b for b in projekt.berechnungen() if b.typ == "welle")
    assert s.werte()["d_lager"] == welle_b.eingaben["d_mm"]
    assert nr["welle"] in s.verknuepft.text() and nr["passfeder"] in s.verknuepft.text()
    assert s.werte()["a_mm"] == 300 and s.werte()["l_mm"] == 400
    s.name.setText("Hauptwelle")
    bild(fenster, "44_bauteil_welle_hell")
    welle = s.teil_speichern()
    assert welle["nr"] == "T-001" and welle["masse"] > 0
    assert {b.nr for b in projekt.haengt_ab_von("teil", welle["id"])} == {nr["welle"], nr["passfeder"]}
    step = s.exportieren("step", str(tmp_path / "Hauptwelle.step"))
    assert abs(G.eigenschaften(G.step_lesen(step)).volumen / G.eigenschaften(s.form).volumen - 1) < 1e-6
    BEISPIELE.joinpath("Hauptwelle_Beispiel.step").write_bytes(step.read_bytes())
    assert s.exportieren("stl", str(tmp_path / "Hauptwelle.stl")).stat().st_size > 84

    s.schnitt.setChecked(True)
    assert s.ansicht.schnittflaechen is not None and s.ansicht.schnittflaechen.any()
    bild(fenster, "45_bauteil_welle_schnitt_hell")
    s.schnitt.setChecked(False)

    # Turmflansch aus Turm und Schrauben
    s.vorlage.setCurrentIndex(s.vorlage.findData("flansch"))
    s.aus_projekt()
    assert nr["turm"] in s.verknuepft.text() and nr["schrauben"] in s.verknuepft.text()
    assert s.form is not None, s.fehler.text()
    s.name.setText("Turmfußflansch")
    s.ansicht.ansicht("Iso")
    bild(fenster, "46_bauteil_flansch_hell")
    s.teil_speichern()

    # Nabe aus dem Pressverband
    s.vorlage.setCurrentIndex(s.vorlage.findData("nabe"))
    s.aus_projekt()
    assert nr["pressverband"] in s.verknuepft.text()
    s.teil_speichern()

    # Sonnenrad aus der Getriebeberechnung
    s.vorlage.setCurrentIndex(s.vorlage.findData("zahnrad"))
    s.aus_projekt()
    assert nr["getriebe"] in s.verknuepft.text()
    s.name.setText("Sonnenrad")
    bild(fenster, "47_bauteil_zahnrad_hell")
    s.teil_speichern()
    assert len(projekt.teile()) == 4

    # Unmögliche Maße: klare Meldung statt Absturz
    s.eingaben["d_bohrung"].setValue(60)
    assert s.form is None and "Bohrung" in s.fehler.text()
    assert not s.speichern.isEnabled()
    s.eingaben["d_bohrung"].setValue(20)

    # Änderung 5 → 10 kW: Berechnungskette und Bauteile werden „neu prüfen“
    projekt.anforderung_aendern(projekt.anforderung_suchen("nennleistung").id, zielwert=10)
    assert projekt.teil(welle["id"])["status"] == NEU_PRUEFEN
    fenster.gehe_zu("berechnungen")
    fenster.berechnungen.alle_neu_rechnen()
    fenster.gehe_zu("bauteile")
    assert "neu prüfen" in s.tabelle.item(0, 5).text()
    rollen = s.findChild(QScrollArea).verticalScrollBar()
    rollen.setValue(rollen.maximum())
    bild(fenster, "48_bauteile_neu_pruefen_hell")
    rollen.setValue(0)
    s.neu_erzeugen(welle["id"])
    assert projekt.teil(welle["id"])["version"] == 2
    assert projekt.teil(welle["id"])["status"] != NEU_PRUEFEN

    # Sprung aus der Rückverfolgung
    fenster.gehe_zu("uebersicht")
    fenster.gehe_zu_objekt("teil", welle["id"])
    assert fenster.stapel.currentWidget() is s and s.teil_id == welle["id"]

    fenster.thema_setzen("dunkel")
    s.ansicht.update()
    bild(fenster, "49_bauteil_welle_dunkel")
    s.teil_laden(projekt.teile()[1]["id"])
    bild(fenster, "50_bauteil_flansch_dunkel")
    thema.anwenden(app, "hell")
