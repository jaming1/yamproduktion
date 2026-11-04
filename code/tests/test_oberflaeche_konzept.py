"""MS3-Oberfläche: Ideen & TRIZ → Funktionen → Konzept → Produkt-Lastenheft, mit Screenshots hell/dunkel."""
from pathlib import Path

from yamproduktion.modell import NEU_PRUEFEN, Projekt
from yamproduktion.ui import thema

from test_oberflaeche import app, bild, fenster  # noqa: F401  (Fixtures wiederverwenden)


def test_konzeptwahl_windkraftanlage(fenster, tmp_path, app):  # noqa: F811
    projekt = Projekt.neu(tmp_path / "KWA", "Kleinwindanlage KWA-5", "Mini-Windkraftanlage 5 kW", beispiel_kwa=True)
    fenster.projekt_laden(projekt)

    # ---------- Ideen & TRIZ
    fenster.gehe_zu("ideen")
    s = fenster.ideen
    assert fenster.stapel.currentWidget() is s
    s.neue_idee()
    s.felder["titel"].setText("Kleinwindanlage für Inselbetrieb")
    s._feld_speichern("titel")
    for feld, text in (("problem", "Gartenhaus ohne Netzanschluss braucht Strom."),
                       ("nutzen", "Eigener Strom, auch bei Stromausfall."),
                       ("ier", "Die Anlage dreht sich selbst in den Wind und schützt sich selbst vor Sturm."),
                       ("ressourcen", "Wind, Mast vorhanden, Werkstatt mit Drehbank.")):
        s.felder[feld].setPlainText(text)
        s._feld_speichern(feld)
    assert projekt.objekt("idee", s.idee_id)["ier"].startswith("Die Anlage")
    s.w_text.setText("Größerer Rotor bringt mehr Leistung, belastet aber Turm und Blätter stärker")
    s.setze_parameter(21, 14)           # Leistung ↑ / Festigkeit ↓
    assert s.empf_lay.count() == len(__import__("yamproduktion.triz").triz.empfehlung(21, 14))
    s.l_text.setText("Blätter bei Sturm aus dem Wind drehen (Pitch-Verstellung)")
    s.loesungsidee_notieren(15)         # Prinzip 15 Dynamisierung
    assert [l["nr"] for l in projekt.liste("loesungsidee")] == ["L-001"]
    assert s.baum.topLevelItem(0).childCount() == 1
    bild(fenster, "13_ideen_triz_hell")
    s.art.setCurrentIndex(1)
    assert s.empf_lay.count() == 5      # Trennungsprinzipien
    bild(fenster, "14_triz_physikalisch_hell")
    s.art.setCurrentIndex(0)

    # ---------- Funktionen
    fenster.gehe_zu("funktionen")
    fs = fenster.funktionen
    g = fs.funktion_anlegen(unter=False, name="Windenergie in elektrische Energie wandeln")
    for name in ("Windenergie aufnehmen", "Drehzahl anpassen", "Strom erzeugen", "Leistung begrenzen"):
        fs.baum.setCurrentItem(fs.baum.topLevelItem(0))
        fs.funktion_anlegen(unter=True, name=name)
    assert len(projekt.teilfunktionen()) == 4
    strom = next(f for f in projekt.teilfunktionen() if f["name"] == "Strom erzeugen")
    fs.auswaehlen(strom["id"])
    fs.anf_wahl.setCurrentIndex(fs.anf_wahl.findData(projekt.anforderung_suchen("nennleistung").id))
    fs.anforderung_verknuepfen()
    assert fs.baum.currentItem().text(2) == "A-001"
    bild(fenster, "15_funktionen_hell")

    # ---------- Konzept: morphologischer Kasten
    fenster.gehe_zu("konzept")
    k = fenster.konzept
    wege = {"Windenergie aufnehmen": ["3-Blatt-Rotor, Luvläufer", "2-Blatt-Rotor, Leeläufer"],
            "Drehzahl anpassen": ["Stirnradgetriebe 1:5", "Direktantrieb (Vielpol-Generator)"],
            "Strom erzeugen": ["Asynchrongenerator", "Permanentmagnet-Synchrongenerator"],
            "Leistung begrenzen": ["Stall-Regelung"]}
    for f in projekt.teilfunktionen():
        k.f_wahl.setCurrentIndex(k.f_wahl.findData(f["id"]))
        for text in wege[f["name"]]:
            k.loesung_text.setText(text)
            k.loesung_hinzufuegen()
    begrenzen = next(f for f in projekt.teilfunktionen() if f["name"] == "Leistung begrenzen")
    k.f_wahl.setCurrentIndex(k.f_wahl.findData(begrenzen["id"]))
    k.loesungsidee_uebernehmen()        # S3: TRIZ-Idee wird Lösungsweg
    for name in ("Getriebe + Asynchron", "Direktantrieb + PMSG"):
        k.v_name.setText(name)
        k.variante_hinzufuegen()
    assert k.kasten.columnCount() == 3 and k.kasten.rowCount() == 4
    # Variante 1: jeweils erster Weg, Variante 2: zweiter Weg (bei Begrenzen: TRIZ-Pitch)
    for z in range(4):
        for spalte, index in ((1, 1), (2, 2)):
            combo = k.kasten.cellWidget(z, spalte)
            combo.setCurrentIndex(min(index, combo.count() - 1))
    v1, v2 = projekt.liste("variante")
    assert len(projekt.variante_wahl(v1["id"])) == 4
    assert "V-002" in [b.nr for b in projekt.wirkt_auf("loesungsidee", projekt.liste("loesungsidee")[0]["id"])]

    # ---------- Nutzwertanalyse
    for name, gewicht in (("Kosten", 3), ("Wartungsaufwand", 2), ("Wirkungsgrad", 2), ("Selbstbau möglich", 3)):
        k.k_name.setText(name)
        k.k_gewicht.setValue(gewicht)
        k.kriterium_hinzufuegen()
    punkte = {0: (7, 4), 1: (4, 8), 2: (6, 8), 3: (8, 5)}
    for z, (a, b) in punkte.items():
        k.nwa.cellWidget(z, 2).setValue(a)
        k.nwa.cellWidget(z, 3).setValue(b)
    n = projekt.nutzwerte()
    assert round(n[v1["id"]], 2) == round((3 * 7 + 2 * 4 + 2 * 6 + 3 * 8) / 10, 2)
    assert "bester" in k.nwa.item(4, 2).text()           # V-001: 6,5 > 6,0
    k.v_wahl.setCurrentIndex(k.v_wahl.findData(v2["id"]))
    k.begruendung.setText("")
    k.auswaehlen()                                        # ohne Begründung → abgelehnt
    assert projekt.gewaehltes_konzept() is None
    k.begruendung.setText("Wartungsarm ohne Getriebe; etwas teurer, aber weniger Verschleißteile auf dem Mast")
    k.auswaehlen()
    assert projekt.gewaehltes_konzept()["nr"] == "V-002"
    assert "V-002" in k.konzept_text.text()
    k.zeige_variante(v2["id"])
    bild(fenster, "16_konzept_hell")

    # ---------- Phasen und Lastenheft
    fenster.gehe_zu("uebersicht")
    assert projekt.phase_hindernisse("P1") == []
    assert projekt.phase_hindernisse("P3") == []
    fenster.uebersicht._freigeben("P1")
    fenster.uebersicht._freigeben("P3")
    assert projekt.phase("P3").status == "freigegeben"
    pdf = fenster.uebersicht.lastenheft_speichern(str(tmp_path / "Lastenheft.pdf"))
    assert Path(pdf).stat().st_size > 5000
    ziel = Path(__file__).parent / "screenshots" / "Produkt-Lastenheft_Beispiel.pdf"
    ziel.write_bytes(Path(pdf).read_bytes())
    bild(fenster, "17_uebersicht_p1_p3_hell")

    # Bewertung ändert sich nach der Freigabe → neu prüfen, Warnung, Sprung ins Konzept
    fenster.gehe_zu("konzept")
    k.nwa.cellWidget(0, 3).setValue(9)
    assert projekt.objekt("variante", v2["id"])["status"] == NEU_PRUEFEN
    assert "neu prüfen" in k.konzept_text.text()
    fenster.gehe_zu("uebersicht")
    assert fenster.uebersicht.warnung.isVisible()
    fenster.uebersicht._erstes_offenes()
    assert fenster.stapel.currentWidget() is k

    # ---------- Dunkel
    fenster.thema_setzen("dunkel")
    bild(fenster, "18_konzept_neu_pruefen_dunkel")
    fenster.gehe_zu("ideen")
    bild(fenster, "19_ideen_triz_dunkel")
    fenster.gehe_zu("funktionen")
    bild(fenster, "20_funktionen_dunkel")
    fenster.gehe_zu("uebersicht")
    bild(fenster, "21_uebersicht_dunkel")
    thema.anwenden(app, "hell")


def test_sprung_aus_rueckverfolgung(fenster, tmp_path):  # noqa: F811
    projekt = Projekt.neu(tmp_path / "X", "X", beispiel_kwa=True)
    fenster.projekt_laden(projekt)
    i = projekt.objekt_neu("idee", titel="Idee")
    w = projekt.widerspruch_neu("W", 1, 3, i["id"])
    l = projekt.loesungsidee_neu(w["id"], 15, "L")
    fenster.gehe_zu_objekt("loesungsidee", l["id"])
    assert fenster.stapel.currentWidget() is fenster.ideen
    assert fenster.ideen.baum.currentItem().text(0) == "L-001"
    f = projekt.funktion_neu("F")
    fenster.gehe_zu_objekt("funktion", f["id"])
    assert fenster.funktionen.baum.currentItem().text(1) == "F-001"
