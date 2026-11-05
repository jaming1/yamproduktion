"""K2 Kreativmethoden: Logik (6-3-5-Ablauf, Mindmap-Anordnung, Bewertung) und Speicherung im Produktmodell."""
import math

import pytest

from yamproduktion import kreativ
from yamproduktion.modell import NEU_PRUEFEN, Projekt, ProjektFehler


# ================================================================ reine Logik
def test_635_reihum_jedes_blatt_bei_jeder_person():
    n = 6
    assert kreativ.felder_635(n) == 108                      # 6 Personen × 6 Runden × 3 Ideen
    for blatt in range(1, n + 1):
        personen = [kreativ.schreiber(blatt, r, n) for r in range(1, n + 1)]
        assert sorted(personen) == list(range(1, n + 1))    # jedes Blatt war bei allen genau einmal
        assert personen[0] == blatt                         # Blatt k beginnt bei Person k
    for r in range(1, n + 1):
        blaetter = [kreativ.blatt_von(p, r, n) for p in range(1, n + 1)]
        assert sorted(blaetter) == list(range(1, n + 1))    # in jeder Runde hat jede Person ein anderes Blatt
        for p in range(1, n + 1):
            assert kreativ.schreiber(kreativ.blatt_von(p, r, n), r, n) == p
    with pytest.raises(kreativ.KreativFehler):
        kreativ.schreiber(7, 1, 6)
    with pytest.raises(kreativ.KreativFehler):
        kreativ.pruefe_teilnehmer(1)


def test_635_stand():
    n = 2
    voll_r1 = [{"blatt": b, "runde": 1, "spalte": s, "text": "x"} for b in (1, 2) for s in (1, 2, 3)]
    assert kreativ.stand_635([], n) == {"gefuellt": 0, "gesamt": 12, "runde": 1, "fertig": False}
    st = kreativ.stand_635(voll_r1 + [{"blatt": 1, "runde": 2, "spalte": 1, "text": " "}], n)
    assert st["gefuellt"] == 6 and st["runde"] == 2 and not st["fertig"]
    alle = voll_r1 + [{"blatt": b, "runde": 2, "spalte": s, "text": "y"} for b in (1, 2) for s in (1, 2, 3)]
    assert kreativ.stand_635(alle, n)["fertig"]


def test_mindmap_anordnung_radial_und_ohne_ueberlappung_der_aeste():
    knoten = [{"id": 1, "eltern_id": None}, {"id": 2, "eltern_id": None}, {"id": 3, "eltern_id": None},
              {"id": 4, "eltern_id": 1}, {"id": 5, "eltern_id": 1}, {"id": 6, "eltern_id": 4}]
    lage = kreativ.anordnung(knoten, abstand=200)
    assert set(lage) == {1, 2, 3, 4, 5, 6}
    for i in (1, 2, 3):
        assert math.hypot(*lage[i]) == pytest.approx(200)  # Hauptäste auf dem ersten Ring
    assert math.hypot(*lage[6]) > math.hypot(*lage[4]) > 200
    assert lage[1][1] < 0                                  # erster Ast liegt oben (Qt: y nach unten)
    assert [k["id"] for _, k in kreativ.baum(knoten)] == [1, 4, 6, 5, 2, 3]
    assert [t for t, _ in kreativ.baum(knoten)] == [1, 2, 3, 2, 1, 1]
    text = kreativ.gliederung("Energie speichern", [dict(k, text=f"K{k['id']}") for k in knoten])
    assert text.splitlines()[0] == "Energie speichern" and "      – K6" in text


def test_brainstorming_gruppen_beste_und_freier_platz():
    z = [{"id": 1, "text": "a", "gruppe": "Rotor", "punkte": 1, "x": 0, "y": 0},
         {"id": 2, "text": "b", "gruppe": "", "punkte": 4, "x": 200, "y": 0},
         {"id": 3, "text": "c", "gruppe": "Rotor", "punkte": 3, "x": 400, "y": 0},
         {"id": 4, "text": "d", "gruppe": "Turm", "punkte": 0, "x": 0, "y": 130}]
    gr = kreativ.gruppen(z)
    assert [g for g, _ in gr] == ["Rotor", "Turm", ""]
    assert [e["id"] for e in gr[0][1]] == [3, 1]           # innerhalb der Gruppe nach Punkten
    assert [e["id"] for e in kreativ.beste(z)] == [2, 3, 1]
    assert kreativ.freier_platz(z) == (600.0, 0.0)


# ================================================================ Produktmodell
@pytest.fixture
def projekt(tmp_path):
    p = Projekt.neu(tmp_path / "KWA", "Kleinwindanlage KWA-5", beispiel_kwa=True)
    yield p
    p.schliessen()


def test_brainstorming_speichern_bewerten_und_als_idee_uebernehmen(projekt):
    s = projekt.kreativ_neu("brainstorming", frage="Wie schützt sich die Anlage vor Sturm?")
    assert s["nr"] == "KS-001" and s["titel"] == "Brainstorming-Board"
    a = projekt.kreativ_eintrag_neu(s["id"], "Blätter aus dem Wind drehen", gruppe="Rotor")
    b = projekt.kreativ_eintrag_neu(s["id"], "Rotor seitlich wegklappen", gruppe="Rotor")
    assert (a["x"], a["y"]) != (b["x"], b["y"])           # nicht übereinander
    projekt.kreativ_punkt(a["id"])
    projekt.kreativ_punkt(a["id"])
    assert projekt.kreativ_punkt(b["id"], -1)["punkte"] == 0   # nie unter 0
    assert projekt.kreativ_eintrag(a["id"])["punkte"] == 2
    with pytest.raises(ProjektFehler):
        projekt.kreativ_eintrag_neu(s["id"], "  ")
    with pytest.raises(ProjektFehler):
        projekt.kreativ_eintrag_aendern(a["id"], farbe="rot")

    i = projekt.kreativ_als_idee(a["id"])
    assert i["nr"] == "I-001" and i["titel"] == "Blätter aus dem Wind drehen"
    assert "Herkunft: KS-001" in i["beschreibung"]
    assert "I-001" in [x.nr for x in projekt.wirkt_auf("kreativ", s["id"])]
    assert projekt.kreativ_eintrag(a["id"])["idee_id"] == i["id"]
    with pytest.raises(ProjektFehler, match="schon I-001"):
        projekt.kreativ_als_idee(a["id"])
    assert any("als I-001 übernommen" in v.text for v in projekt.verlauf("kreativ", s["id"]))
    assert projekt.phase("P1").status == "in Arbeit"

    # Leitfrage geändert → übernommene Idee neu prüfen (Rückverfolgung M5)
    projekt.objekt_aendern("kreativ", s["id"], frage="Wie übersteht die Anlage Orkanböen?")
    assert projekt.objekt("idee", i["id"])["status"] == NEU_PRUEFEN


def test_sitzung_zu_idee_und_kreis_verhindert(projekt):
    idee = projekt.objekt_neu("idee", titel="Inselbetrieb")
    s = projekt.kreativ_neu("mindmap", idee_id=idee["id"])
    assert "KS-001" in [x.nr for x in projekt.wirkt_auf("idee", idee["id"])]
    k = projekt.kreativ_eintrag_neu(s["id"], "Batteriespeicher")
    neu = projekt.kreativ_als_idee(k["id"])
    with pytest.raises(ProjektFehler, match="Kreis"):
        projekt.kreativ_idee_setzen(s["id"], neu["id"])      # I-002 stammt aus der Sitzung
    assert projekt.objekt("kreativ", s["id"])["idee_id"] == idee["id"]
    projekt.kreativ_idee_setzen(s["id"], None)
    assert "KS-001" not in [x.nr for x in projekt.wirkt_auf("idee", idee["id"])]


def test_635_felder_und_mindmap_baum(projekt):
    s = projekt.kreativ_neu("635", teilnehmer=3)
    with pytest.raises(ProjektFehler):
        projekt.kreativ_neu("635", teilnehmer=12)
    with pytest.raises(ProjektFehler):
        projekt.feld_635_setzen(s["id"], 4, 1, 1, "zu viele Blätter")
    e = projekt.feld_635_setzen(s["id"], 2, 1, 3, "Vertikalachsen-Rotor")
    assert projekt.blatt_635(s["id"], 2)[(1, 3)]["id"] == e["id"]
    assert projekt.feld_635_setzen(s["id"], 2, 1, 3, "Savonius-Rotor")["id"] == e["id"]   # gleiches Feld
    assert projekt.feld_635_setzen(s["id"], 2, 1, 3, "") is None
    assert projekt.kreativ_eintraege(s["id"]) == []
    m = projekt.kreativ_neu("mindmap", frage="Energie speichern")
    with pytest.raises(ProjektFehler):
        projekt.feld_635_setzen(m["id"], 1, 1, 1, "falsche Methode")
    ast = projekt.kreativ_eintrag_neu(m["id"], "Elektrisch")
    zweig = projekt.kreativ_eintrag_neu(m["id"], "Akku", eltern_id=ast["id"])
    blatt = projekt.kreativ_eintrag_neu(m["id"], "LiFePO4", eltern_id=zweig["id"])
    with pytest.raises(ProjektFehler, match="unter sich selbst"):
        projekt.kreativ_eintrag_aendern(ast["id"], eltern_id=blatt["id"])
    with pytest.raises(ProjektFehler):
        projekt.kreativ_eintrag_neu(s["id"], "fremder Elternknoten", eltern_id=ast["id"])
    projekt.kreativ_eintrag_loeschen(zweig["id"])            # mit allen Zweigen darunter
    assert [e["text"] for e in projekt.kreativ_eintraege(m["id"])] == ["Elektrisch"]
    projekt.objekt_loeschen("kreativ", m["id"])
    assert projekt.kreativ_eintraege(m["id"]) == [] and len(projekt.kreativ_sitzungen()) == 1


def test_als_loesungsweg_in_den_morphologischen_kasten(projekt):
    f = projekt.funktion_neu("Leistung begrenzen")
    s = projekt.kreativ_neu("brainstorming")
    e = projekt.kreativ_eintrag_neu(s["id"], "Seitliches Herausdrehen aus dem Wind")
    lid = projekt.kreativ_als_loesung(e["id"], f["id"])
    assert projekt.loesungen(f["id"]) == [{"id": lid, "text": "Seitliches Herausdrehen aus dem Wind (KS-001)",
                                           "loesungsidee_id": None}]
    assert projekt.kreativ_eintrag(e["id"])["loesung_id"] == lid


def test_alte_projektdatei_bekommt_kreativ_tabellen(tmp_path):
    p = Projekt.neu(tmp_path / "Alt", "Alt")
    pfad = p.pfad
    p._db.execute("DROP TABLE kreativ")
    p._db.execute("DROP TABLE kreativ_eintrag")
    p._setze_meta("schema_version", "10")
    p._db.commit()
    p.schliessen()
    p = Projekt.oeffnen(pfad)
    assert p.meta("schema_version") == "11"
    assert p.kreativ_neu("brainstorming")["nr"] == "KS-001"
    p.schliessen()
