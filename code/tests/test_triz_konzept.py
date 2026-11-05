"""MS3: TRIZ, Ideen, Funktionsstruktur, morphologischer Kasten, Nutzwertanalyse."""
import json

import pytest

from yamproduktion import triz
from yamproduktion.modell import NEU_PRUEFEN, Projekt, ProjektFehler, SCHEMA_VERSION


# ---------------------------------------------------------------- TRIZ-Daten
def test_triz_daten_vollstaendig():
    assert len(triz.parameter()) == 39
    assert len(triz.prinzipien()) == 40
    assert triz.parameter_name(14) == "Festigkeit"
    assert triz.prinzip(1)["name"] == "Zerlegung"
    assert triz.prinzip(40)["name"] == "Verbundwerkstoffe"
    assert len(triz.trennungsprinzipien()) == 5
    assert "Altschuller" in triz.quelle()


def test_matrix_stichproben():
    """Feste Stichprobe aus der klassischen Altschuller-Matrix (zur Freigabe festgehalten)."""
    assert triz.empfehlung(1, 3) == [15, 8, 29, 34]     # Masse bewegt ↔ Länge bewegt
    assert triz.empfehlung(14, 9) == [8, 13, 26, 14]    # Festigkeit ↔ Geschwindigkeit (MATRIZ-Beispiel)
    assert triz.empfehlung(9, 14) == [8, 3, 26, 14]
    assert triz.empfehlung(5, 5) == []                  # gleicher Parameter → physikalischer Widerspruch


def test_matrix_nur_gueltige_prinzipien():
    daten = json.loads((triz._DATEI).read_text(encoding="utf-8"))
    assert len(daten["matrix"]) == 1248
    for schluessel, liste in daten["matrix"].items():
        a, b = map(int, schluessel.split("-"))
        assert 1 <= a <= 39 and 1 <= b <= 39 and a != b
        assert liste and all(1 <= n <= 40 for n in liste)


def test_ungueltiger_parameter():
    with pytest.raises(ValueError):
        triz.empfehlung(0, 40)


# ---------------------------------------------------------------- Ideen & Widersprüche
def projekt(tmp_path):
    return Projekt.neu(tmp_path / "KWA", "KWA-5", beispiel_kwa=True)


def test_idee_widerspruch_loesungsidee(tmp_path):
    p = projekt(tmp_path)
    i = p.objekt_neu("idee", titel="Kleinwindanlage für Inselbetrieb", problem="Kein Netzanschluss",
                     nutzen="Strom am Gartenhaus", ier="Die Anlage stellt sich selbst in den Wind")
    assert i["nr"] == "I-001" and p.phase("P1").status == "in Arbeit"
    w = p.widerspruch_neu("Großer Rotor für Leistung, aber hohe Last am Turm", 21, 14, idee_id=i["id"])
    assert w["nr"] == "W-001"
    assert json.loads(w["prinzipien"]) == triz.empfehlung(21, 14)
    l = p.loesungsidee_neu(w["id"], 15, "Blätter bei Sturm aus dem Wind drehen (Pitch)")
    assert [b.nr for b in p.wirkt_auf("idee", i["id"], rekursiv=True)] == ["W-001", "L-001"]
    # Änderung der Idee → Widerspruch und Lösungsidee neu prüfen
    p.objekt_aendern("idee", i["id"], problem="Kein Netzanschluss, häufig Sturm")
    assert p.objekt("loesungsidee", l["id"])["status"] == NEU_PRUEFEN
    assert any("I-001 geändert" in v.text for v in p.verlauf("loesungsidee", l["id"]))
    assert p.objekt("idee", i["id"])["version"] == 2


def test_physikalischer_widerspruch(tmp_path):
    p = projekt(tmp_path)
    w = p.physikalischer_widerspruch_neu("Rotor muss groß (Leistung) und klein (Sturm) sein")
    assert w["art"] == "physikalisch" and w["prinzipien"] == "[]"


def test_p1_braucht_eine_idee(tmp_path):
    p = projekt(tmp_path)
    assert "Es gibt noch keine Idee." in p.phase_hindernisse("P1")
    p.objekt_neu("idee", titel="X")
    assert p.phase_hindernisse("P1") == []
    p.phase_freigeben("P1")


# ---------------------------------------------------------------- Funktionsstruktur
def test_funktionsbaum_und_teilfunktionen(tmp_path):
    p = projekt(tmp_path)
    gesamt = p.funktion_neu("Windenergie in Strom wandeln")
    f1 = p.funktion_neu("Windenergie aufnehmen", gesamt["id"])
    f2 = p.funktion_neu("Drehzahl anpassen", gesamt["id"])
    f3 = p.funktion_neu("Strom erzeugen", gesamt["id"])
    baum = p.funktionsbaum()
    assert [(t, f["name"]) for t, f in baum][:2] == [(0, "Windenergie in Strom wandeln"), (1, "Windenergie aufnehmen")]
    assert [f["id"] for f in p.teilfunktionen()] == [f1["id"], f2["id"], f3["id"]]
    leistung = p.anforderung_suchen("nennleistung")
    p.anforderung_zu_funktion(leistung.id, f3["id"])
    p.anforderung_aendern(leistung.id, zielwert=10)
    assert p.objekt("funktion", f3["id"])["status"] == NEU_PRUEFEN
    p.objekt_loeschen("funktion", gesamt["id"])
    assert p.liste("funktion") == []


# ---------------------------------------------------------------- Konzept
def konzept(tmp_path):
    p = projekt(tmp_path)
    g = p.funktion_neu("Wind in Strom wandeln")
    drehzahl = p.funktion_neu("Drehzahl anpassen", g["id"])
    regelung = p.funktion_neu("Leistung begrenzen", g["id"])
    getriebe = p.loesung_neu(drehzahl["id"], "Stirnradgetriebe")
    direkt = p.loesung_neu(drehzahl["id"], "Direktantrieb (Vielpol-Generator)")
    w = p.widerspruch_neu("Leistung vs. Festigkeit", 21, 14)
    li = p.loesungsidee_neu(w["id"], 15, "Pitch-Verstellung")
    pitch = p.loesungsidee_als_loesung(li["id"], regelung["id"])
    stall = p.loesung_neu(regelung["id"], "Stall-Regelung")
    v1 = p.variante_neu("Getriebe + Pitch")
    v2 = p.variante_neu("Direktantrieb + Stall")
    p.variante_wahl_setzen(v1["id"], drehzahl["id"], getriebe)
    p.variante_wahl_setzen(v1["id"], regelung["id"], pitch)
    p.variante_wahl_setzen(v2["id"], drehzahl["id"], direkt)
    p.variante_wahl_setzen(v2["id"], regelung["id"], stall)
    k1 = p.kriterium_neu("Kosten", 3)
    k2 = p.kriterium_neu("Wartungsaufwand", 1)
    return p, v1, v2, k1, k2, li, pitch


def test_morphologischer_kasten_und_nutzwert(tmp_path):
    p, v1, v2, k1, k2, li, pitch = konzept(tmp_path)
    assert "(L-001)" in p.loesungen(p.teilfunktionen()[1]["id"])[0]["text"]
    assert [b.nr for b in p.wirkt_auf("loesungsidee", li["id"])] == ["V-001"]
    p.bewerten(v1["id"], k1, 6)
    p.bewerten(v1["id"], k2, 4)
    p.bewerten(v2["id"], k1, 5)
    p.bewerten(v2["id"], k2, 9)
    n = p.nutzwerte()
    assert n[v1["id"]] == pytest.approx((3 * 6 + 1 * 4) / 4)   # 5,5
    assert n[v2["id"]] == pytest.approx((3 * 5 + 1 * 9) / 4)   # 6,0
    with pytest.raises(ProjektFehler, match="0 \\(schlecht\\) bis 10"):
        p.bewerten(v1["id"], k1, 11)


def test_p3_phasentor_und_auswahl(tmp_path):
    p, v1, v2, k1, k2, *_ = konzept(tmp_path)
    h = p.phase_hindernisse("P3")
    assert any("nicht in allen Kriterien" in x for x in h) and any("keine Variante" in x for x in h)
    for v in (v1, v2):
        for k in (k1, k2):
            p.bewerten(v["id"], k, 5)
    with pytest.raises(ProjektFehler, match="begründen"):
        p.variante_auswaehlen(v2["id"], "  ")
    p.variante_auswaehlen(v2["id"], "Weniger Verschleißteile, wartungsarm")
    assert p.gewaehltes_konzept()["nr"] == "V-002"
    assert p.phase_hindernisse("P3") == []
    p.phase_freigeben("P3")
    assert p.objekt("variante", v2["id"])["status"] == "freigegeben"
    # Bewertung ändert sich → Auswahl muss neu geprüft werden, Phasentor öffnet sich
    p.bewerten(v1["id"], k1, 9)
    assert p.objekt("variante", v2["id"])["status"] == NEU_PRUEFEN
    assert p.phase("P3").status == "in Arbeit"


def test_variante_aendern_hebt_auswahl_auf(tmp_path):
    p, v1, v2, k1, k2, li, pitch = konzept(tmp_path)
    p.variante_auswaehlen(v1["id"], "Bewährt")
    regelung = p.teilfunktionen()[1]
    p.variante_wahl_setzen(v1["id"], regelung["id"], None)
    assert p.gewaehltes_konzept() is None


def test_loesung_aendern_markiert_variante(tmp_path):
    p, v1, v2, k1, k2, li, pitch = konzept(tmp_path)
    p.loesung_aendern(pitch, "Elektrische Pitch-Verstellung")
    assert p.objekt("variante", v1["id"])["status"] == NEU_PRUEFEN
    assert p.objekt("variante", v2["id"])["status"] == "Entwurf"


def test_schema2_wird_auf_3_umgestellt(tmp_path):
    import sqlite3
    p = projekt(tmp_path)
    p.schliessen()
    db = sqlite3.connect(tmp_path / "KWA.yamp")
    for t in ("idee", "widerspruch", "loesungsidee", "funktion", "loesung", "variante", "variante_wahl",
              "kriterium", "bewertung"):
        db.execute(f"DROP TABLE {t}")
    db.execute("UPDATE meta SET wert='2' WHERE schluessel='schema_version'")
    db.commit()
    db.close()
    p = Projekt.oeffnen(tmp_path / "KWA.yamp")
    assert p.meta("schema_version") == str(SCHEMA_VERSION)
    assert p.objekt_neu("idee", titel="neu")["nr"] == "I-001"
