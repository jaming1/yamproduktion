import pytest

from yamproduktion.einheiten import EinheitFehler, umrechnen, zahl_lesen
from yamproduktion.modell import Projekt, ProjektFehler


def test_projekt_anlegen_und_wieder_oeffnen(tmp_path):
    p = Projekt.neu(tmp_path / "KWA", "Kleinwindanlage KWA-5", "Mini-WKA", beispiel_kwa=True)
    assert p.pfad.suffix == ".yamp"
    assert len(p.anforderungen()) == 7
    p.schliessen()
    p2 = Projekt.oeffnen(tmp_path / "KWA.yamp")
    assert p2.name == "Kleinwindanlage KWA-5"
    assert p2.anforderung_wert("nennleistung") == (5.0, "kW")


def test_aenderung_erhoeht_version(tmp_path):
    p = Projekt.neu(tmp_path / "x", "X")
    a = p.anforderung_neu("Nennleistung", 5, "kW")
    assert a.nr == "A-001" and a.version == 1
    a = p.anforderung_aendern(a.id, zielwert=10)
    assert a.version == 2 and a.zielwert == 10
    a = p.anforderung_aendern(a.id, zielwert=10)   # keine echte Änderung
    assert a.version == 2


def test_falsche_einheit_wird_abgelehnt(tmp_path):
    p = Projekt.neu(tmp_path / "x", "X")
    with pytest.raises(EinheitFehler):
        p.anforderung_neu("Masse", 5, "kilogrammm")


def test_nummern_bleiben_eindeutig_nach_loeschen(tmp_path):
    p = Projekt.neu(tmp_path / "x", "X")
    a1 = p.anforderung_neu("a")
    p.anforderung_neu("b")
    p.anforderung_loeschen(a1.id)
    assert p.anforderung_neu("c").nr == "A-003"


def test_keine_fremde_datei_oeffnen(tmp_path):
    f = tmp_path / "kaputt.yamp"
    f.write_text("kein sqlite")
    with pytest.raises(ProjektFehler):
        Projekt.oeffnen(f)


def test_vorhandene_datei_nicht_ueberschreiben(tmp_path):
    Projekt.neu(tmp_path / "x", "X")
    with pytest.raises(ProjektFehler):
        Projekt.neu(tmp_path / "x", "X")


def test_einheiten_und_zahlen():
    assert umrechnen(5, "kW", "W") == 5000
    assert umrechnen(36, "km/h", "m/s") == pytest.approx(10)
    with pytest.raises(EinheitFehler):
        umrechnen(1, "kg", "m")
    assert zahl_lesen("5,5") == 5.5
    assert zahl_lesen("1.000,5") == 1000.5
    assert zahl_lesen("5.5") == 5.5
    assert zahl_lesen("") is None
