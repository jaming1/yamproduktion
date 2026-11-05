"""K2-Oberfläche: Kreativmethoden (Brainstorming-Board, 6-3-5, Mindmap) mit Übernahme, Screenshots hell/dunkel 100–109."""
from yamproduktion.modell import Projekt

from test_oberflaeche import app, bild, fenster  # noqa: F401  (Fixtures wiederverwenden)


def test_kreativmethoden(fenster, tmp_path, app):  # noqa: F811
    projekt = Projekt.neu(tmp_path / "KWA", "Kleinwindanlage KWA-5", "Mini-Windkraftanlage 5 kW", beispiel_kwa=True)
    fenster.projekt_laden(projekt)
    fenster.gehe_zu("kreativ")
    k = fenster.kreativ
    assert fenster.stapel.currentWidget() is k
    assert k.stapel.currentWidget() is k.leer_hinweis
    bild(fenster, "100_kreativ_leer_hell")

    # ---------- Brainstorming-Board
    s = k.neue_sitzung("brainstorming", "Sturmschutz", "Wie schützt sich die Anlage selbst vor Sturm?")
    assert s["nr"] == "KS-001" and k.stapel.currentWidget() is k.ansichten["brainstorming"]
    b = k.ansichten["brainstorming"]
    for text, gruppe in (("Blätter aus dem Wind drehen (Pitch)", "Rotor"), ("Rotor seitlich wegklappen", "Rotor"),
                         ("Strömungsabriss gezielt nutzen (Stall)", "Rotor"), ("Kurzschlussbremse am Generator",
                         "Elektrik"), ("Mast umlegbar", "Turm"), ("Fliehkraftbremse", "")):
        b.zettel_hinzufuegen(text, gruppe)
    assert len(b.zettel) == 6
    pitch = next(e["id"] for e in b.eintraege if e["text"].startswith("Blätter"))
    b.waehle(pitch)
    for _ in range(3):
        b.punkt(1)
    assert projekt.kreativ_eintrag(pitch)["punkte"] == 3
    b.nach_gruppen_ordnen()
    assert k.als_idee.isEnabled()
    i = k.als_idee_uebernehmen()
    assert i["nr"] == "I-001" and i["titel"] == "Blätter aus dem Wind drehen (Pitch)"
    assert "ist I-001" in k.auswahl_text.text()
    assert "I-001" in [x.nr for x in projekt.wirkt_auf("kreativ", s["id"])]
    bild(fenster, "101_brainstorming_hell")

    # ---------- 6-3-5
    s2 = k.neue_sitzung("635", "Leiser Rotor", "Wie wird der Rotor leiser?")
    f = k.ansichten["635"]
    assert k.teilnehmer.isVisible() and k.teilnehmer.isEnabled()
    for spalte, text in enumerate(("Sägezahn-Hinterkante", "Drehzahl senken", "Blattspitze mit Winglet"), 1):
        f.feld_setzen(1, spalte, text)
    f.zeige_blatt(2)
    f.feld_setzen(1, 1, "Dickeres Profil an der Wurzel")
    f.zeige_blatt(1)
    f.feld_setzen(2, 1, "Sägezahn nur außen – weniger Kosten")
    assert len(projekt.kreativ_eintraege(s2["id"])) == 5
    assert not k.teilnehmer.isEnabled()          # Teilnehmerzahl fest, sobald Felder gefüllt sind
    f.waehle_feld(1, 2)
    assert f.ausgewaehlt() and "Drehzahl senken" in k.auswahl_text.text()
    bild(fenster, "102_635_hell")

    # Lösungsweg in den morphologischen Kasten
    ast = projekt.funktion_neu("Strom erzeugen")
    begrenzen = projekt.funktion_neu("Leistung begrenzen", eltern_id=ast["id"])
    k.laden(s2["id"])
    k.funktion_wahl.setCurrentIndex(k.funktion_wahl.findData(begrenzen["id"]))
    f.waehle_feld(1, 2)
    lid = k.als_loesung_uebernehmen()
    assert lid and projekt.loesungen(begrenzen["id"])[0]["text"] == "Drehzahl senken (KS-002)"
    assert "im Konzept" in k.auswahl_text.text()

    # ---------- Mindmap
    s3 = k.neue_sitzung("mindmap", "Speicher", "Wie speichern wir den Strom?")
    m = k.ansichten["mindmap"]
    assert m.thema() == "Wie speichern wir den Strom?"
    elektrisch = m.ast_hinzufuegen("Elektrisch")
    m.waehle(elektrisch["id"])
    m.zweig_hinzufuegen("Akku LiFePO4")
    m.zweig_hinzufuegen("Superkondensator")
    m.waehle(None)
    waerme = m.ast_hinzufuegen("Wärme")
    m.waehle(waerme["id"])
    m.zweig_hinzufuegen("Heizstab im Pufferspeicher")
    m.waehle(None)
    m.ast_hinzufuegen("Mechanisch")
    assert len(m.knoten_items) == 6
    assert m.als_text().splitlines()[:3] == ["Wie speichern wir den Strom?", "  – Elektrisch", "    – Akku LiFePO4"]
    m.waehle(waerme["id"])
    assert m.loeschen()                      # mit Unterzweig (Rückfrage wird im Test bejaht)
    assert len(projekt.kreativ_eintraege(s3["id"])) == 4
    k.frage.setText("Wie speichern wir überschüssigen Strom?")
    k._feld_speichern("frage")
    assert m.thema() == "Wie speichern wir überschüssigen Strom?"
    bild(fenster, "103_mindmap_hell")

    # Rückverfolgung: Idee → Sitzung
    fenster.gehe_zu_objekt("kreativ", s["id"])
    assert fenster.stapel.currentWidget() is k and k.sitzung["id"] == s["id"]
    assert k.sitzung_wahl.count() == 3

    # ---------- Dunkel
    fenster.thema_setzen("dunkel")
    bild(fenster, "104_brainstorming_dunkel")
    k.laden(s2["id"])
    bild(fenster, "105_635_dunkel")
    k.laden(s3["id"])
    bild(fenster, "106_mindmap_dunkel")
    fenster.thema_setzen("hell")

    # Sitzung löschen: übernommene Idee bleibt
    k.laden(s["id"])
    k._sitzung_loeschen()
    assert len(projekt.kreativ_sitzungen()) == 2 and projekt.objekt("idee", i["id"])
