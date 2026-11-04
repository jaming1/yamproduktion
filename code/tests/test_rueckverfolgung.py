"""MS2: Produktmodell, Rückverfolgung, Änderungswirkung, Phasentore, Sicherung, Umstellung."""
import json
import sqlite3

import pytest

from yamproduktion.berechnungen import rotor
from yamproduktion.modell import NEU_PRUEFEN, Projekt, ProjektFehler


def kwa_mit_berechnung(tmp_path):
    p = Projekt.neu(tmp_path / "KWA", "KWA-5", beispiel_kwa=True)
    leistung = p.anforderung_suchen("nennleistung")
    wind = p.anforderung_suchen("nennwind")
    e = rotor.RotorEingaben(leistung_el_kw=leistung.zielwert, wind_nenn_ms=wind.zielwert)
    b = p.berechnung_speichern(rotor.berechne(e).als_dict(), e.__dict__,
                               {"leistung_el_kw": leistung.id, "wind_nenn_ms": wind.id})
    return p, leistung, wind, b


def test_verknuepfung_in_beide_richtungen(tmp_path):
    p, leistung, wind, b = kwa_mit_berechnung(tmp_path)
    assert {q.nr for q in p.haengt_ab_von("berechnung", b.id)} == {leistung.nr, wind.nr}
    assert [z.nr for z in p.wirkt_auf("anforderung", leistung.id)] == [b.nr]
    assert "mit Werten aus A-001, A-002" in p.verlauf("berechnung", b.id)[0].text


def test_aenderung_5_auf_10_kw_markiert_berechnung(tmp_path):
    """Abnahmekriterium 5 aus dem Lastenheft."""
    p, leistung, _, b = kwa_mit_berechnung(tmp_path)
    p.status_setzen("berechnung", b.id, "geprüft")
    p.anforderung_aendern(leistung.id, zielwert=10)
    b = p.berechnung(b.id)
    assert b.status == NEU_PRUEFEN
    assert [x.nr for x in p.neu_zu_pruefen()] == [b.nr]
    assert "Zielwert 5 → 10 kW" in p.verlauf("berechnung", b.id)[0].text
    # Textänderung allein wirkt nicht auf die Berechnung
    p2, l2, _, b2 = kwa_mit_berechnung(tmp_path / "zwei")
    p2.anforderung_aendern(l2.id, text="Elektrische Nennleistung am Netz")
    assert p2.berechnung(b2.id).status == "Entwurf"


def test_neu_rechnen_uebernimmt_neuen_wert(tmp_path):
    p, leistung, _, b = kwa_mit_berechnung(tmp_path)
    d_alt = b.ergebnis["ergebnisse"][0]["wert"]
    p.anforderung_aendern(leistung.id, zielwert=10)
    b = p.berechnung_neu_rechnen(b.id)
    assert b.status == "Entwurf" and b.version == 2
    assert b.eingaben["leistung_el_kw"] == 10
    assert b.ergebnis["ergebnisse"][0]["wert"] == pytest.approx(d_alt * 2 ** 0.5)
    assert "D 4,792 → 6,778 m" in p.verlauf("berechnung", b.id)[0].text
    assert p.neu_zu_pruefen() == []


def test_neu_rechnen_rechnet_einheiten_um(tmp_path):
    p, leistung, _, b = kwa_mit_berechnung(tmp_path)
    p.anforderung_aendern(leistung.id, zielwert=8000, einheit="W")
    b = p.berechnung_neu_rechnen(b.id)
    assert b.eingaben["leistung_el_kw"] == pytest.approx(8.0)


def test_neu_rechnen_mit_falscher_einheit_meldet_fehler(tmp_path):
    p, leistung, _, b = kwa_mit_berechnung(tmp_path)
    p.anforderung_aendern(leistung.id, einheit="kg")
    with pytest.raises(ProjektFehler, match="A-001"):
        p.berechnung_neu_rechnen(b.id)


def test_status_geprueft_erst_nach_neu_rechnen(tmp_path):
    p, leistung, _, b = kwa_mit_berechnung(tmp_path)
    p.anforderung_aendern(leistung.id, zielwert=10)
    with pytest.raises(ProjektFehler, match="neu berechnet"):
        p.status_setzen("berechnung", b.id, "geprüft")


def test_kreis_wird_verhindert(tmp_path):
    p, leistung, _, b = kwa_mit_berechnung(tmp_path)
    with pytest.raises(ProjektFehler, match="Kreis"):
        p.verknuepfen("berechnung", b.id, "anforderung", leistung.id)


def test_phasentor(tmp_path):
    p, leistung, _, b = kwa_mit_berechnung(tmp_path)
    assert p.phase("P2").status == "in Arbeit"
    assert p.phase("P1").status == "offen"
    assert p.phase_hindernisse("P2") == ["Es gibt noch keine Funktionsstruktur."]
    p.funktion_neu("Wind in Strom wandeln")
    assert p.phase_hindernisse("P2") == []
    p.phase_freigeben("P2")
    p.phase_freigeben("P4")
    assert p.phase("P4").status == "freigegeben"
    assert p.berechnung(b.id).status == "freigegeben"
    assert all(a.status == "freigegeben" for a in p.anforderungen())
    # Änderung öffnet die Phasentore wieder
    p.anforderung_aendern(leistung.id, zielwert=10)
    assert p.phase("P2").status == "in Arbeit"
    assert p.phase("P4").status == "in Arbeit"
    assert p.anforderung(leistung.id).status == "Entwurf"
    assert "wieder geöffnet" in p.phase_verlauf("P4")[0].text
    with pytest.raises(ProjektFehler, match="neu berechnet"):
        p.phase_freigeben("P4")
    with pytest.raises(ProjektFehler, match="späteren Meilenstein"):
        p.phase_freigeben("P5")


def test_muss_anforderung_ohne_zielwert_blockiert_p2(tmp_path):
    p = Projekt.neu(tmp_path / "x", "X")
    a = p.anforderung_neu("Leistung", None, "", "Muss")
    assert any("keinen Zielwert" in h for h in p.phase_hindernisse("P2"))
    p.anforderung_aendern(a.id, zielwert=5)
    p.funktion_neu("Hauptfunktion")
    assert p.phase_hindernisse("P2") == []


def test_sicherung_beim_oeffnen(tmp_path):
    p, *_ = kwa_mit_berechnung(tmp_path)
    p.schliessen()
    for _ in range(12):
        Projekt.oeffnen(tmp_path / "KWA.yamp").schliessen()
    sicherungen = list((tmp_path / "KWA_Sicherungen").glob("*.yamp"))
    assert len(sicherungen) == 10
    kopie = Projekt.oeffnen(sicherungen[0], sicherung=False)
    assert len(kopie.anforderungen()) == 7


def test_altes_projekt_wird_umgestellt(tmp_path):
    """Eine Projektdatei aus MS1 (Schema 1) öffnet ohne Datenverlust."""
    pfad = tmp_path / "alt.yamp"
    db = sqlite3.connect(pfad)
    db.executescript("""
        CREATE TABLE meta (schluessel TEXT PRIMARY KEY, wert TEXT NOT NULL);
        CREATE TABLE anforderung (id INTEGER PRIMARY KEY AUTOINCREMENT, nr TEXT NOT NULL UNIQUE,
            text TEXT NOT NULL DEFAULT '', zielwert REAL, einheit TEXT NOT NULL DEFAULT '',
            prioritaet TEXT NOT NULL DEFAULT 'Muss', quelle TEXT NOT NULL DEFAULT '',
            version INTEGER NOT NULL DEFAULT 1, status TEXT NOT NULL DEFAULT 'Entwurf',
            erstellt TEXT NOT NULL, geaendert TEXT NOT NULL);
        CREATE TABLE berechnung (id INTEGER PRIMARY KEY AUTOINCREMENT, nr TEXT NOT NULL UNIQUE,
            typ TEXT NOT NULL, titel TEXT NOT NULL, eingaben TEXT NOT NULL, ergebnis TEXT NOT NULL,
            erfuellt INTEGER NOT NULL, erstellt TEXT NOT NULL);
        INSERT INTO meta VALUES ('schema_version', '1'), ('name', 'Alt');
        INSERT INTO anforderung(nr, text, zielwert, einheit, erstellt, geaendert)
            VALUES ('A-001', 'Elektrische Nennleistung', 5, 'kW', 'x', 'x');
    """)
    e = rotor.RotorEingaben()
    db.execute("INSERT INTO berechnung(nr, typ, titel, eingaben, ergebnis, erfuellt, erstellt) VALUES(?,?,?,?,?,?,?)",
               ("B-001", rotor.TYP, rotor.TITEL, json.dumps(e.__dict__),
                json.dumps(rotor.berechne(e).als_dict()), 1, "x"))
    db.commit()
    db.close()
    p = Projekt.oeffnen(pfad)
    assert p.meta("schema_version") == "5"
    assert p.anforderungen()[0].art == "Anforderung"
    assert p.berechnungen()[0].version == 1
    assert p.phase("P2").status == "in Arbeit" and p.phase("P4").status == "in Arbeit"
    assert (tmp_path / "alt_Sicherungen").exists()
