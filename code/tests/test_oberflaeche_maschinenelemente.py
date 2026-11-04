"""MS5-Oberfläche: Maschinenelemente mit Werten aus Lasten und Turm; Screenshots hell/dunkel."""
from pathlib import Path

from yamproduktion.ui import thema

from test_oberflaeche import app, bild, fenster  # noqa: F401
from yamproduktion.modell import Projekt

BEISPIELE = Path(__file__).with_name("screenshots")


def test_maschinenelemente_windkraftanlage(fenster, tmp_path, app):  # noqa: F811
    projekt = Projekt.neu(tmp_path / "KWA", "Kleinwindanlage KWA-5", "Mini-Windkraftanlage 5 kW", beispiel_kwa=True)
    fenster.projekt_laden(projekt)

    # Gruppenüberschriften in der Seitenleiste sind nicht wählbar
    zeile = next(i for i in range(fenster.nav.count()) if fenster.nav.item(i).text() == "MASCHINENELEMENTE")
    assert not fenster.nav.item(zeile).flags() & fenster.nav.item(zeile).flags().ItemIsSelectable

    for schluessel in ("rotor", "lasten", "antrieb"):
        fenster.gehe_zu(schluessel)
        fenster.rechenseiten[schluessel].aus_anforderungen()
        fenster.rechenseiten[schluessel].protokoll_speichern(str(tmp_path / f"{schluessel}.pdf"))

    nummern = {}
    reihe = [("turm", "31_turm_hell"), ("schrauben", "32_schrauben_hell"), ("schweissnaht", "33_schweissnaht_hell"),
             ("welle", "34_welle_hell"), ("lager", "35_lager_hell"), ("passfeder", "36_passfeder_hell"),
             ("pressverband", None), ("getriebe", "37_getriebe_hell"), ("bremse", "38_bremse_hell")]
    for schluessel, name in reihe:
        fenster.gehe_zu(schluessel)
        s = fenster.rechenseiten[schluessel]
        assert fenster.stapel.currentWidget() is s
        s.aus_anforderungen()
        assert s.ergebnis is not None, schluessel
        if name:
            bild(fenster, name)
        pdf = s.protokoll_speichern(str(tmp_path / f"{schluessel}.pdf"))
        assert Path(pdf).exists()
        nummern[schluessel] = projekt.berechnungen()[0].nr
        if schluessel in ("turm", "schweissnaht", "getriebe"):
            BEISPIELE.joinpath(f"{schluessel.capitalize()}_Beispiel.pdf").write_bytes(Path(pdf).read_bytes())

    # Turm übernimmt Lasten (B-002), Schrauben und Schweißnaht übernehmen den Turm
    assert "B-002" in fenster.rechenseiten["turm"].verknuepft.text()
    assert nummern["turm"] in fenster.rechenseiten["schrauben"].verknuepft.text()
    assert nummern["turm"] in fenster.rechenseiten["schweissnaht"].verknuepft.text()
    turm_b = next(b for b in projekt.berechnungen() if b.nr == nummern["turm"])
    abh = {b.nr for b in projekt.wirkt_auf("berechnung", turm_b.id)}
    assert {nummern["schrauben"], nummern["schweissnaht"]} <= abh

    fenster.gehe_zu("berechnungen")
    bild(fenster, "39_berechnungen_liste_hell")

    fenster.thema_setzen("dunkel")
    for schluessel, name in (("turm", "40_turm_dunkel"), ("getriebe", "41_getriebe_dunkel"),
                             ("welle", "42_welle_dunkel"), ("bremse", "43_bremse_dunkel")):
        fenster.gehe_zu(schluessel)
        bild(fenster, name)
    thema.anwenden(app, "hell")
