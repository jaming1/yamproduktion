"""MS6: Vorlagen-Teile, Geometrieprüfung gegen geschlossene Formeln, Export, Bauteile im Projekt."""
import math

import pytest

from yamproduktion.berechnungen import ARTEN
from yamproduktion.cad import geometrie as G
from yamproduktion.cad import vorlagen as V
from yamproduktion.modell import NEU_PRUEFEN, Projekt, ProjektFehler


def test_alle_vorlagen_gueltig():
    for typ, v in V.VORLAGEN.items():
        form = v.erzeuge(v.Eingaben())
        assert G.ist_gueltig(form), typ
        assert G.eigenschaften(form).volumen > 0


def test_welle_volumen_ohne_nut_und_fase():
    """Volumen = Σ π/4·d²·l der Absätze."""
    p = V.WelleParameter(fase=0, l_pf=0)
    z_b = p.l_nabe / 2 + p.a_mm
    abschnitte = [(p.d_nabe, p.l_nabe), (p.d_lager, z_b + p.b_lager / 2 - p.l_nabe), (p.d_mitte, p.l_mm - p.b_lager),
                  (p.d_lager, p.b_lager), (p.d_ende, p.l_ende)]
    soll = sum(math.pi / 4 * d * d * l for d, l in abschnitte)
    e = G.eigenschaften(V.erzeuge_welle(p))
    assert e.volumen == pytest.approx(soll, rel=1e-6)
    assert e.groesse[2] == pytest.approx(sum(l for _, l in abschnitte), rel=1e-9)


def test_welle_lagerabstand_und_ueberhang():
    """Die Lagermitten liegen bei z_B = l_Nabe/2 + a und z_A = z_B + l (aus der Wellenberechnung)."""
    p = V.WelleParameter(fase=0, l_pf=0, a_mm=250, l_mm=500)
    e = G.eigenschaften(V.erzeuge_welle(p))
    laenge = p.l_nabe / 2 + 250 + 500 + p.b_lager / 2 + p.l_ende
    assert e.groesse[2] == pytest.approx(laenge, rel=1e-9)


def test_passfedernut_volumen():
    """Nut Form A: Volumen liegt zwischen (l−b)·b·t1 + π/4·b²·t1 (eben) und dem Wert mit Kreisabschnitt."""
    p = V.WelleParameter(fase=0)
    ohne = G.eigenschaften(V.erzeuge_welle(V.WelleParameter(fase=0, l_pf=0))).volumen
    mit = G.eigenschaften(V.erzeuge_welle(p)).volumen
    b, h, t1 = V.passfeder(p.d_nabe)
    eben = ((p.l_pf - b) * b + math.pi / 4 * b * b) * t1
    assert 0.9 * eben < ohne - mit < 1.0 * eben


def test_fase_nimmt_material_weg():
    ohne = G.eigenschaften(V.erzeuge_welle(V.WelleParameter(fase=0))).volumen
    mit = G.eigenschaften(V.erzeuge_welle(V.WelleParameter(fase=2))).volumen
    assert 0 < ohne - mit < 0.01 * ohne


def test_flansch_volumen():
    p = V.FlanschParameter(h_stutzen=0)
    d_i = p.d_rohr - 2 * p.t_rohr
    d_loch = V.durchgangsloch(p.d_schraube)
    soll = math.pi / 4 * (p.d_a**2 - d_i**2) * p.dicke - int(p.n) * math.pi / 4 * d_loch**2 * p.dicke
    assert G.eigenschaften(V.erzeuge_flansch(p)).volumen == pytest.approx(soll, rel=1e-6)


def test_durchgangsloch_iso273_mittel():
    assert V.durchgangsloch(16) == 17.5 and V.durchgangsloch(24) == 26.0


def test_zahnrad_kopfkreis_und_flaeche():
    """Kopfkreis d_a = m·(z + 2); Volumen = Fläche des Evolventenprofils · b (Polygon als Gegenprobe)."""
    p = V.ZahnradParameter(m_n=3, z1=20, b_mm=25, d_bohrung=0)
    form = V.erzeuge_zahnrad(p)
    e = G.eigenschaften(form)
    assert e.groesse[0] == pytest.approx(3 * 22, abs=0.2)
    punkte = V.zahnprofil(3, 20, 20, punkte_je_flanke=40)
    flaeche = 0.5 * abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(punkte, punkte[1:] + punkte[:1])))
    assert e.volumen == pytest.approx(flaeche * 25, rel=2e-3)
    # Kontrolle der Größenordnung: zwischen Fußkreis- und Kopfkreisscheibe
    assert math.pi / 4 * (3 * 20 - 7.5) ** 2 * 25 < e.volumen < math.pi / 4 * 66**2 * 25


def test_evolvente_zahndicke_am_teilkreis():
    """Am Teilkreis ist die Zahndicke s = π·m/2 (ohne Profilverschiebung)."""
    m, z = 2.0, 30
    r = m * z / 2
    punkte = V.zahnprofil(m, z, 20, punkte_je_flanke=400)
    # Punkte des ersten Zahns nahe am Teilkreis: Winkelbreite · r = Zahndicke
    nahe = [(x, y) for x, y in punkte[:900] if abs(math.hypot(x, y) - r) < 0.02 and abs(math.atan2(y, x)) < 0.3]
    winkel = [math.atan2(y, x) for x, y in nahe]
    assert (max(winkel) - min(winkel)) * r == pytest.approx(math.pi * m / 2, rel=0.01)


def test_unmoegliche_masse_werden_erklaert():
    with pytest.raises(G.GeometrieFehler, match="Bund"):
        V.erzeuge_welle(V.WelleParameter(d_mitte=70))
    with pytest.raises(G.GeometrieFehler, match="Lochkreis"):
        V.erzeuge_flansch(V.FlanschParameter(d_l=420))
    with pytest.raises(G.GeometrieFehler, match="Bohrung"):
        V.erzeuge_zahnrad(V.ZahnradParameter(d_bohrung=40))


def test_schnitt_halbiert_rotationskoerper():
    form = V.erzeuge_welle(V.WelleParameter(l_pf=0))
    halb = G.schneiden(form, "x", 0.0)
    assert G.eigenschaften(halb).volumen == pytest.approx(G.eigenschaften(form).volumen / 2, rel=1e-4)


def test_netz_fuer_anzeige():
    n = G.netz(V.erzeuge_flansch(V.FlanschParameter()))
    assert len(n.dreiecke) > 100 and n.kanten
    assert n.punkte[n.dreiecke].shape[1:] == (3, 3)


def test_step_und_stl_export(tmp_path):
    form = V.erzeuge_welle(V.WelleParameter())
    step = G.step_schreiben(form, tmp_path / "welle.step", "Hauptwelle")
    assert step.read_text(errors="ignore").startswith("ISO-10303-21")
    zurueck = G.step_lesen(step)
    assert G.eigenschaften(zurueck).volumen == pytest.approx(G.eigenschaften(form).volumen, rel=1e-6)
    stl = G.stl_schreiben(form, tmp_path / "welle.stl")
    assert stl.stat().st_size > 84


# ---------------------------------------------------------------- Projekt: Teil aus Berechnung, Änderungskette
def _berechnung_speichern(p, typ, **werte):
    art = ARTEN[typ]
    e = art["eingaben"](**werte)
    return p.berechnung_speichern(art["berechne"](e).als_dict(), e.__dict__)


def test_hauptwelle_aus_berechnung_und_aenderung(tmp_path):
    """Abnahme MS6: Die Hauptwelle aus MS5 erscheint als 3D-Teil; ändert sich die Wellenberechnung,
    wird das Teil „neu prüfen“ und übernimmt beim Neu-Erzeugen den neuen Durchmesser."""
    p = Projekt.neu(tmp_path / "K", "K", "")
    w = _berechnung_speichern(p, "welle", d_mm=80)
    parameter = V.WelleParameter(d_lager=80, a_mm=300, l_mm=400).__dict__
    form = V.erzeuge_welle(V.WelleParameter(**parameter))
    e = G.eigenschaften(form)
    t = p.teil_speichern("welle", "Hauptwelle", parameter, e.masse(V.dichte(parameter["werkstoff"])), e.volumen,
                         {"d_lager": ("berechnung", w.id), "a_mm": ("berechnung", w.id), "l_mm": ("berechnung", w.id)})
    assert t["nr"] == "T-001" and t["masse"] == pytest.approx(e.volumen * 7.85e-6)
    assert {b.nr for b in p.haengt_ab_von("teil", t["id"])} == {w.nr}

    # Welle in der Berechnung dicker: B neu rechnen geht über die Anforderungskette; hier direkt neue Version
    p._db.execute("UPDATE berechnung SET eingaben=? WHERE id=?", ('{"d_mm": 85}', w.id))
    art = ARTEN["welle"]
    neu = art["berechne"](art["eingaben"](d_mm=85)).als_dict()
    import json
    p._db.execute("UPDATE berechnung SET ergebnis=? WHERE id=?", (json.dumps(neu), w.id))
    p._wirkung_markieren("berechnung", w.id, "Test: Durchmesser geändert")
    assert p.teil(t["id"])["status"] == NEU_PRUEFEN
    t2 = p.teil_neu_erzeugen(t["id"])
    assert t2["parameter"]["d_lager"] == pytest.approx(85)
    assert t2["version"] == 2 and t2["status"] == "Entwurf"
    assert t2["masse"] > t["masse"]
    assert any("80 → 85" in v.text for v in p.verlauf("teil", t["id"]))


def test_teil_neu_erzeugen_verweigert_bei_veralteter_quelle(tmp_path):
    p = Projekt.neu(tmp_path / "K", "K", "")
    w = _berechnung_speichern(p, "welle", d_mm=80)
    t = p.teil_speichern("welle", "W", V.WelleParameter().__dict__, quellen={"d_lager": ("berechnung", w.id)})
    p._db.execute("UPDATE berechnung SET status=? WHERE id=?", (NEU_PRUEFEN, w.id))
    with pytest.raises(ProjektFehler, match="Zuerst"):
        p.teil_neu_erzeugen(t["id"])


def test_alte_projektdatei_bekommt_bauteile(tmp_path):
    p = Projekt.neu(tmp_path / "Alt", "Alt", "")
    p._db.execute("DROP TABLE teil")
    p._setze_meta("schema_version", "3")
    p._db.commit()
    p.schliessen()
    p = Projekt.oeffnen(tmp_path / "Alt.yamp", sicherung=False)
    assert p.teile() == []
    assert p.meta("schema_version") == "9"
