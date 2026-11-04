"""MS4-Oberfläche: Rotor → Ertrag → Lasten → Antrieb, Werkstoffe; Kette bei Änderung; Screenshots hell/dunkel."""
from pathlib import Path

from yamproduktion.modell import NEU_PRUEFEN, Projekt
from yamproduktion.ui import thema

from test_oberflaeche import app, bild, fenster  # noqa: F401


def test_auslegung_windkraftanlage(fenster, tmp_path, app):  # noqa: F811
    projekt = Projekt.neu(tmp_path / "KWA", "Kleinwindanlage KWA-5", "Mini-Windkraftanlage 5 kW", beispiel_kwa=True)
    fenster.projekt_laden(projekt)

    fenster.gehe_zu("rotor")
    fenster.rotor.aus_anforderungen()
    assert fenster.rotor.protokoll_speichern(str(tmp_path / "B-001.pdf"))
    rotor_b = projekt.berechnungen()[0]

    # Ertrag: Werte aus Anforderungen (Nennleistung, Ein-/Abschaltwind, Nabenhöhe) und aus B-001 (D, cp, η, ρ)
    fenster.gehe_zu("ertrag")
    s = fenster.rechenseiten["ertrag"]
    s.aus_anforderungen()
    assert s.eingaben["h_nabe"].value() == 12
    assert abs(s.werte().durchmesser_m - rotor_b.ergebnis["ergebnisse"][0]["wert"]) < 1e-9   # exakt, nicht gerundet
    assert "B-001" in s.verknuepft.text() and "A-001" in s.verknuepft.text()
    assert s.diagramm.isVisible()
    bild(fenster, "22_ertrag_hell")
    pdf = s.protokoll_speichern(str(tmp_path / "B-002.pdf"))
    Path(__file__).with_name("screenshots").joinpath("Ertrag_Beispiel.pdf").write_bytes(Path(pdf).read_bytes())
    ertrag_b = projekt.berechnungen()[0]
    assert {b.nr for b in projekt.haengt_ab_von("berechnung", ertrag_b.id)} >= {"B-001", "A-001"}

    # Lasten
    fenster.gehe_zu("lasten")
    s = fenster.rechenseiten["lasten"]
    s.aus_anforderungen()
    assert s.unbelegt.isVisible()
    bild(fenster, "23_lasten_hell")
    pdf = s.protokoll_speichern(str(tmp_path / "B-003.pdf"))
    Path(__file__).with_name("screenshots").joinpath("Lasten_Beispiel.pdf").write_bytes(Path(pdf).read_bytes())

    # Antrieb: Bauart umschalten
    fenster.gehe_zu("antrieb")
    s = fenster.rechenseiten["antrieb"]
    s.aus_anforderungen()
    s.eingaben["bauart"].setCurrentIndex(1)
    assert s.ergebnis.ergebnis("i").wert > 1
    s.eingaben["bauart"].setCurrentIndex(0)
    assert s.ergebnis.ergebnis("p").wert >= 1
    bild(fenster, "24_antrieb_hell")
    s.protokoll_speichern(str(tmp_path / "B-004.pdf"))

    fenster.gehe_zu("werkstoffe")
    fenster.werkstoffe.suche.setText("welle")
    assert fenster.werkstoffe.tabelle.rowCount() >= 3
    bild(fenster, "25_werkstoffe_hell")
    fenster.werkstoffe.suche.setText("")

    # Änderung 5 → 10 kW: Rotor und alle Folgeberechnungen werden markiert und in Reihenfolge neu gerechnet
    projekt.anforderung_aendern(projekt.anforderung_suchen("nennleistung").id, zielwert=10)
    markiert = {b.nr for b in projekt.neu_zu_pruefen() if b.typ == "berechnung"}
    assert markiert == {"B-001", "B-002", "B-003", "B-004"}
    fenster.gehe_zu("berechnungen")
    bild(fenster, "26_berechnungen_kette_hell")
    fenster.berechnungen.alle_neu_rechnen()
    assert all(b.status != NEU_PRUEFEN for b in projekt.berechnungen())
    assert projekt.berechnung(ertrag_b.id).eingaben["leistung_nenn_kw"] == 10

    # Dunkel
    fenster.thema_setzen("dunkel")
    fenster.gehe_zu("ertrag")
    bild(fenster, "27_ertrag_dunkel")
    fenster.gehe_zu("lasten")
    bild(fenster, "28_lasten_dunkel")
    fenster.gehe_zu("antrieb")
    bild(fenster, "29_antrieb_dunkel")
    fenster.gehe_zu("werkstoffe")
    bild(fenster, "30_werkstoffe_dunkel")
    thema.anwenden(app, "hell")
