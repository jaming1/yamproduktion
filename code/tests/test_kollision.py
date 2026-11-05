"""K4: Kollisionsprüfung, Masse, Schwerpunkt und Trägheit von Baugruppen; Ausnahmen im Projekt (Schema 13)."""
import math
import sqlite3

import numpy as np
import pytest

from yamproduktion.cad import baugruppe as BG, geometrie as G, kollision as K
from yamproduktion.modell import SCHEMA_VERSION, Projekt


def _quelle(formen: dict):
    """formen: teil_id → (form, dichte kg/m³ oder None)."""
    def q(tid):
        form, dichte = formen[tid]
        masse = None if dichte is None else G.eigenschaften(form).volumen * 1e-9 * dichte
        return dict(form=form, masse=masse, werkstoff="S235", nr=f"T-{tid:03d}", name=f"Teil {tid}")
    return q


def _zwei_quader(x2: float, dichte2=7850.0):
    """Zwei Würfel 10 mm, der zweite bei x = x2."""
    w = G.quader(0, 0, 0, 10, 10, 10)
    d = {"parameter": [], "einbauten": [
        {"id": "E1", "art": "teil", "teil_id": 1, "name": "A", "lage": {}},
        {"id": "E2", "art": "teil", "teil_id": 2, "name": "B", "lage": {"x": str(x2)}}]}
    return d, _quelle({1: (w, 7850.0), 2: (w, dichte2)})


@pytest.mark.parametrize("x2, art, volumen, abstand", [
    (5, K.DURCHDRINGUNG, 500.0, 0.0),
    (10, K.BERUEHRUNG, 0.0, 0.0),
    (10.5, K.SPIEL, 0.0, 0.5),
])
def test_arten(x2, art, volumen, abstand):
    d, q = _zwei_quader(x2)
    r = BG.bauen(d, q)
    pr = K.pruefen(r, d, mindestabstand=1.0)
    assert len(pr.befunde) == 1
    b = pr.befunde[0]
    assert b.art == art and abs(b.volumen - volumen) < 1e-6 and abs(b.abstand - abstand) < 1e-6
    assert (b.einbau_a, b.einbau_b) == ("E1", "E2") and b.name_a == "E1 A"
    assert pr.ok == (art == K.BERUEHRUNG)                 # Berührung ist kein Fehler
    if art == K.DURCHDRINGUNG:
        assert abs(b.ort[0] - 7.5) < 1e-6 and pr.betroffene() == [0, 1]


def test_weit_weg_und_vorfilter():
    d, q = _zwei_quader(30)
    pr = K.pruefen(BG.bauen(d, q), d, mindestabstand=5)
    assert pr.befunde == [] and pr.ok and pr.paare_geprueft == 0 and pr.paare_gesamt == 1
    assert pr.zusammenfassung() == "Keine Kollision gefunden."
    # ohne Mindestabstand ist knappes Spiel kein Befund
    d, q = _zwei_quader(10.5)
    assert K.pruefen(BG.bauen(d, q), d).befunde == []


def test_ausnahme_und_reihenfolge():
    d, q = _zwei_quader(5)
    r = BG.bauen(d, q)
    pr = K.pruefen(r, d, {K.paar("E2", "E1"): "Presspassung, gewollt"})
    assert pr.ok and pr.befunde[0].ausnahme == "Presspassung, gewollt" and not pr.befunde[0].ist_fehler
    assert pr.betroffene() == [] and "1 als gewollt vermerkt" in pr.zusammenfassung()
    assert pr.anzahl(K.DURCHDRINGUNG) == 0 and pr.anzahl(K.DURCHDRINGUNG, mit_ausnahmen=True) == 1


def test_lochkreis_und_lager_auf_welle():
    """Lager auf der Welle: Berührung (Passung). Lager auf dem dickeren Bund: Durchdringung.
    Schrauben eines Lochkreises im Lager: je Exemplar ein Befund, Ausnahme gilt für alle zusammen."""
    w = G.abgesetzt([(80, 100), (90, 30), (80, 300)])
    d = {"parameter": [], "einbauten": [
        {"id": "E1", "art": "teil", "teil_id": 1, "name": "Welle", "lage": {}},
        {"id": "E2", "art": "normteil", "norm": "22216 E", "name": "Lager A", "bezug": {"ziel": "E1", "abstand": "40"}},
        {"id": "E3", "art": "normteil", "norm": "22216 E", "name": "Lager B", "bezug": {"ziel": "E1", "abstand": "120"}},
        {"id": "E4", "art": "normteil", "norm": "ISO 4762 M12x40", "name": "Schraube",
         "bezug": {"ziel": "E1", "abstand": "130"}, "kreis": {"anzahl": "8", "radius": "70"}}]}
    r = BG.bauen(d, _quelle({1: (w, 7850.0)}))
    assert r.ok, r.fehler
    pr = K.pruefen(r, d)
    arten = {(b.einbau_a, b.einbau_b, b.art) for b in pr.befunde}
    assert ("E1", "E2", K.BERUEHRUNG) in arten and ("E1", "E3", K.DURCHDRINGUNG) in arten
    schrauben = [b for b in pr.befunde if b.paar == ("E3", "E4")]
    assert len(schrauben) == 8 and all(b.art == K.DURCHDRINGUNG for b in schrauben)
    assert schrauben[0].name_b.startswith("E4 Schraube (") and "/8)" in schrauben[0].name_b
    assert pr.befunde[0].art == K.DURCHDRINGUNG and pr.befunde[-1].art == K.BERUEHRUNG    # nach Schwere
    pr2 = K.pruefen(r, d, {("E3", "E4"): "Schrauben vereinfacht"})
    assert pr2.fehler_anzahl == pr.fehler_anzahl - 8


def test_massen_quader_analytisch():
    """Zwei 10-mm-Stahlwürfel nebeneinander: Schwerpunkt in der Mitte, Trägheit nach Steiner."""
    d, q = _zwei_quader(10)
    r = BG.bauen(d, q)
    m = K.massen(r, d)
    m1 = 1000 * 1e-9 * 7850
    assert abs(m.masse - 2 * m1) < 1e-12 and abs(m.masse - r.masse) < 1e-12
    assert np.allclose(m.schwerpunkt, (10, 5, 5)) and np.allclose(m.schwerpunkt, r.schwerpunkt)
    a = 10.0
    j = m1 * (a * a + a * a) / 12              # Würfel um eigene Achse
    erw = np.diag([2 * j, 2 * (j + m1 * 25), 2 * (j + m1 * 25)])
    assert np.allclose(m.traegheit, erw, rtol=1e-9)
    assert np.allclose(sorted(m.haupt), sorted(np.diag(erw)))
    assert [z.anteil for z in m.je_einbau] == pytest.approx([0.5, 0.5])


def test_massen_zylinder_gedreht_und_ohne_masse():
    """Zylinder gekippt (Achse in x): Ixx = m r²/2 (Ø 20 → r 10); Teil ohne Masse wird genannt und nicht gezählt."""
    z = G.zylinder(20, 100)
    d = {"parameter": [], "einbauten": [
        {"id": "E1", "art": "teil", "teil_id": 1, "name": "Rolle", "lage": {"ry": "90"}},
        {"id": "E2", "art": "teil", "teil_id": 2, "name": "Platzhalter", "lage": {"x": "500"}}]}
    r = BG.bauen(d, _quelle({1: (z, 7850.0), 2: (z, None)}))
    m = K.massen(r, d)
    v = math.pi * 10 ** 2 * 100
    mz = v * 1e-9 * 7850
    assert abs(m.masse - mz) < 1e-6 * mz
    assert abs(m.traegheit[0, 0] - mz * 10 ** 2 / 2) < 1e-4 * m.traegheit[0, 0]
    assert abs(m.traegheit[1, 1] - mz * (3 * 10 ** 2 + 100 ** 2) / 12) < 1e-4 * m.traegheit[1, 1]
    assert m.ohne_masse == ["Platzhalter"] and abs(m.traegheit_kgm2()[0, 0] - m.traegheit[0, 0] * 1e-6) < 1e-15
    assert K.massen(BG.Ergebnis(), {}).masse == 0.0


def test_projekt_ausnahmen_und_mindestabstand(tmp_path):
    p = Projekt.neu(tmp_path / "P", "Test", "")
    assert SCHEMA_VERSION >= 13
    d = {"parameter": [], "einbauten": [
        {"id": "E1", "art": "normteil", "norm": "ISO 4032 M16", "name": "Mutter", "lage": {}},
        {"id": "E2", "art": "normteil", "norm": "ISO 4032 M16", "name": "Mutter 2", "lage": {"x": "5"}}]}
    g = p.baugruppe_speichern("Muttern", d)
    erg, pr, m = p.kollision_pruefen(g["id"])
    assert pr.fehler_anzahl == 1 and abs(m.masse - erg.masse) < 1e-12
    p.kollision_ausnahme_setzen(g["id"], "E2", "E1", "nur Test")
    assert p.kollision_ausnahmen(g["id"]) == {("E1", "E2"): "nur Test"}
    assert p.kollision_pruefen(g["id"])[1].ok
    assert any("gewollt" in v.text for v in p.verlauf("baugruppe", g["id"]))
    p.kollision_mindestabstand_setzen(g["id"], 2.5)
    pfad = p.pfad
    p.schliessen()
    p = Projekt.oeffnen(pfad, sicherung=False)
    assert p.kollision_mindestabstand(g["id"]) == 2.5 and p.kollision_ausnahmen(g["id"])
    p.kollision_ausnahme_setzen(g["id"], "E1", "E2", "")
    assert p.kollision_ausnahmen(g["id"]) == {}
    p.kollision_ausnahme_setzen(g["id"], "E1", "E2", "wieder")
    p.baugruppe_loeschen(g["id"])
    assert p._db.execute("SELECT COUNT(*) FROM kollision_ausnahme").fetchone()[0] == 0
    p.schliessen()


def test_umstellung_von_schema_10(tmp_path):
    """Alte Projektdatei ohne Tabelle kollision_ausnahme wird beim Öffnen ergänzt."""
    p = Projekt.neu(tmp_path / "Alt", "Alt", "")
    pfad = p.pfad
    p.schliessen()
    db = sqlite3.connect(pfad)
    db.execute("DROP TABLE kollision_ausnahme")
    db.execute("UPDATE meta SET wert='10' WHERE schluessel='schema_version'")
    db.commit()
    db.close()
    p = Projekt.oeffnen(pfad, sicherung=False)
    assert p.meta("schema_version") == str(SCHEMA_VERSION)
    assert p.kollision_ausnahmen(1) == {}
    p.schliessen()


def test_bericht_pdf(tmp_path):
    from pypdf import PdfReader
    from yamproduktion.pdf import kollisionsbericht_erstellen
    d, q = _zwei_quader(5)
    r = BG.bauen(d, q)
    pr = K.pruefen(r, d, mindestabstand=1)
    ziel = kollisionsbericht_erstellen(pr, K.massen(r, d), tmp_path / "k.pdf", "Würfel", "G-001", "Test")
    text = "".join(s.extract_text() for s in PdfReader(ziel).pages)
    assert "Durchdringung" in text and "Gesamtmasse" in text and "G-001" in text
