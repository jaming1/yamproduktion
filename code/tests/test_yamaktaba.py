"""Anschluss an Yamaktaba: finden, lesend suchen und fragen, Seite mit Fundstelle, Projekt archivieren."""
import sqlite3

import pytest

from yamproduktion.modell import Projekt
from yamproduktion.wissen import yamaktaba as Y

from yamaktaba_beispiel import yamaktaba_bauen


@pytest.fixture
def yk(tmp_path):
    ordner = yamaktaba_bauen(tmp_path / "ashamila")
    y = Y.Yamaktaba(ordner)
    yield y
    y.schliessen()


def test_finden(tmp_path, monkeypatch):
    monkeypatch.setattr(Y, "APP_SKRIPT", tmp_path / "fehlt")
    monkeypatch.setattr(Y, "STANDARD_ORDNER", tmp_path / "auch_nicht")
    assert Y.ordner_finden() is None
    ordner = yamaktaba_bauen(tmp_path / "ashamila")
    assert Y.ordner_finden(ordner) == ordner
    skript = tmp_path / "Yamaktaba"
    skript.write_text(f'#!/bin/bash\nHOME_DIR="{ordner}"\n')
    monkeypatch.setattr(Y, "APP_SKRIPT", skript)
    assert Y.ordner_finden() == ordner                       # aus der installierten App gelesen
    with pytest.raises(Y.YamaktabaFehler):
        Y.Yamaktaba(tmp_path)


def test_suchen_lesen_fragen(yk):
    assert yk.anzahl_buecher() == 1 and yk.anzahl_buecher("de") == 1
    gesamt, funde = yk.suchen("Lebensdauer Wälzlager")
    assert gesamt == 1 and funde[0].seite_id == 4 and "<b>" in funde[0].ausschnitt
    assert funde[0].titel == "Übungsbuch Maschinenelemente" and funde[0].original
    s = yk.seite(funde[0].buch_id, funde[0].seite_id)
    assert "L_10 = (C / P)^p" in s.text and s.kapitel == "14 Wälzlager"
    assert s.original and s.original.name == "Uebungsbuch.pdf" and s.vorher == 3 and s.nachher == 5
    assert s.fundstelle.startswith("Übungsbuch Maschinenelemente (Muster), 14 Wälzlager, S. ")
    woerter, funde = yk.frage("Wie berechnet man die Biegespannung einer Welle?")
    assert "Biegespannung" in woerter and funde and funde[0].seite_id == 2
    assert yk.suchen("Zahnradpumpe")[0] == 0
    assert yk.suchen("Welle", sprache="ar")[0] == 0
    # nur lesend: Schreiben über die Leseverbindung ist unmöglich
    with pytest.raises(sqlite3.OperationalError):
        yk.con.execute("DELETE FROM book")


def test_archivieren(yk, tmp_path):
    p = Projekt.neu(tmp_path / "KWA", "Kleinwindanlage KWA-5", vorlage="kwa")
    from yamproduktion.pdf import lastenheft_erstellen
    pdf = lastenheft_erstellen(p, tmp_path / "Lastenheft.pdf")
    p.dokument_merken("lastenheft", pdf)
    meldungen = []
    erg = yk.archivieren(p, meldungen.append)
    assert len(erg["neu"]) == 1 and erg["zip"].is_file() and erg["zip"].parent == erg["ordner"]
    assert erg["ordner"].is_relative_to(yk.ordner / "bibliothek" / "YamProduktion")
    buch = erg["neu"][0]["buch_id"]
    gesamt, funde = yk.suchen("Kleinwindanlage")
    assert any(f.buch_id == buch for f in funde)
    info = yk.db.book_info(yk.con, buch)
    assert info["quelle"] == "yamproduktion" and info["category"] == 1033 and info["original"]
    z = yk.con.execute("SELECT c.name FROM collection c JOIN collection_book cb ON cb.collection=c.id "
                       "WHERE cb.book=?", (buch,)).fetchone()
    assert z[0] == "YamProduktion: Kleinwindanlage KWA-5"
    # zweites Archiv ohne Änderung: ZIP neu, PDF nicht doppelt
    erg2 = yk.archivieren(p)
    assert erg2["neu"] == [] and erg2["unveraendert"] == ["Lastenheft.pdf"]
    assert p.meta("yamaktaba_archiv")
    p.schliessen()
