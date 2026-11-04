"""MS8: Normteile, Baugruppen (Ausrichtung, Masse, Schwerpunkt, Stückliste), technische Zeichnung, PDF/DXF."""
import dataclasses
import math

import pytest

from yamproduktion.cad import baugruppe as BG, geometrie as G, normteile as N, vorlagen, zeichnung as Z
from yamproduktion.modell import NEU_PRUEFEN, Projekt


def test_normteile():
    s = N.erzeugen("ISO 4762 M12x40")
    assert G.ist_gueltig(s.form) and abs(s.masse - 0.0546) < 0.002          # Tabellenbuch ≈ 54 g
    e = G.eigenschaften(s.form)
    assert abs(e.maximum[2] - 12) < 1e-6 and abs(e.minimum[2] + 40) < 1e-6   # Kopf oben, Schaft nach −z
    lager = N.erzeugen("22216 E")
    assert lager.benennung == "Pendelrollenlager" and 1.4 < lager.masse < 1.9   # Katalog ≈ 1,6 kg
    assert N.erzeugen("ISO 4032 M16").masse > 0 and N.erzeugen("ISO 7089 16").masse > 0
    assert N.erzeugen("DIN 6885 A 22x14x80").masse > 0
    assert N.erzeugen("ISO  4017  M16×60").norm == "ISO 4017 M16x60"          # Schreibweise vereinheitlicht
    with pytest.raises(G.GeometrieFehler, match="nicht hinterlegt"):
        N.erzeugen("ISO 4762 M14x40")
    with pytest.raises(G.GeometrieFehler, match="kenne ich nicht"):
        N.erzeugen("Schraube groß")
    assert all(N.katalog().values())


def _welle_quelle():
    w = G.abgesetzt([(80, 100), (90, 30), (80, 300)])
    masse = G.eigenschaften(w).volumen * 7.85e-6
    return w, masse, lambda _id: dict(form=w, masse=masse, werkstoff="42CrMo4", nr="T-001", name="Hauptwelle")


def test_baugruppe_ausrichtung_masse_stueckliste():
    w, m_w, quelle = _welle_quelle()
    d = {"parameter": [{"name": "a", "formel": "300"}], "einbauten": [
        {"id": "E1", "art": "teil", "teil_id": 1, "name": "Welle", "lage": {"z": "0"}},
        {"id": "E2", "art": "normteil", "norm": "22216 E", "bezug": {"ziel": "E1", "abstand": "40"}},
        {"id": "E3", "art": "normteil", "norm": "22216 E", "bezug": {"ziel": "E1", "abstand": "a + 40", "umdrehen": True}},
        {"id": "E4", "art": "normteil", "norm": "ISO 4762 M12x40", "bezug": {"ziel": "E1", "abstand": "130"},
         "kreis": {"anzahl": "8", "radius": "70"}},
    ]}
    r = BG.bauen(d, quelle)
    assert r.ok, r.fehler
    assert len(r.exemplare) == 1 + 2 + 8
    menge = {p.sachnummer: p.menge for p in r.stueckliste}
    assert menge == {"T-001": 1, "22216 E": 2, "ISO 4762 M12x40": 8}
    assert [p.pos for p in r.stueckliste] == [1, 2, 3] and r.stueckliste[0].art == "Bauteil"
    lager, schraube = N.erzeugen("22216 E"), N.erzeugen("ISO 4762 M12x40")
    assert abs(r.masse - (m_w + 2 * lager.masse + 8 * schraube.masse)) < 1e-9
    # Schwerpunkt auf der Achse (Lochkreis symmetrisch), z als gewichtetes Mittel
    assert abs(r.schwerpunkt[0]) < 1e-6 and abs(r.schwerpunkt[1]) < 1e-6
    z_s = G.eigenschaften(schraube.form).schwerpunkt[2]
    z_erw = (m_w * G.eigenschaften(w).schwerpunkt[2] + lager.masse * (40 + 16.5) + lager.masse * (340 - 16.5)
             + 8 * schraube.masse * (130 + z_s)) / r.masse
    assert abs(r.schwerpunkt[2] - z_erw) < 1e-6
    # Lage: zweites Lager umgedreht – liegt bei z 307 … 340
    e3 = G.eigenschaften(r.exemplare[2].form)
    assert abs(e3.minimum[2] - 307) < 1e-6 and abs(e3.maximum[2] - 340) < 1e-6
    # Schrauben auf dem Lochkreis Ø140
    for x in r.exemplare[3:]:
        s = G.eigenschaften(x.form).schwerpunkt
        assert abs(math.hypot(s[0], s[1]) - 70) < 1e-6
    csv = BG.stueckliste_csv(r.stueckliste)
    assert csv.splitlines()[2].startswith("2;2;Pendelrollenlager;22216 E;") and "," in csv.splitlines()[1]
    assert [p for p, _ in r.positionspunkte()] == [1, 2, 3]

    # Verknüpfung folgt dem Ziel: Welle verschoben → Lager wandern mit
    d["einbauten"][0]["lage"]["z"] = "50"
    r2 = BG.bauen(d, quelle)
    assert abs(G.eigenschaften(r2.exemplare[1].form).minimum[2] - 90) < 1e-6

    # Fehler: Kreis in den Bezügen, unbekanntes Normteil – klare Meldung, Rest bleibt
    d["einbauten"][0]["bezug"] = {"ziel": "E2"}
    assert "im Kreis" in BG.bauen(d, quelle).fehler
    del d["einbauten"][0]["bezug"]
    d["einbauten"][1]["norm"] = "22216 X"
    r3 = BG.bauen(d, quelle)
    assert not r3.ok and "E2" in r3.meldungen and len(r3.exemplare) == 1 + 1 + 8
    assert BG.naechste_id(d) == "E5"


def test_zeichnung_welle_und_scheibe(tmp_path):
    w = G.abgesetzt([(70, 80), (80, 120), (90, 30), (80, 200)], fase=1)
    z = Z.zeichnung_erstellen(w, {"benennung": "Hauptwelle", "sachnummer": "T-001", "werkstoff": "42CrMo4"},
                              toleranzen={"80": "k6"})
    texte = [e.text for e in z.elemente if isinstance(e, Z.Text)]
    assert "430" in texte and "Ø80 k6" in texte and "Ø70" in texte and "Ø90" in texte
    assert ["80", "120", "30", "200"] == [t for t in texte if t in ("80", "120", "30", "200")]   # Absätze ohne Fasen
    assert z.massstab == 0.5 and "1:2" in texte and "ISO 2768-mK" in texte
    assert not any(isinstance(e, Z.Linie) and e.art == "schraffur" for e in z.elemente)   # Wellen nicht geschnitten
    for e in z.elemente:                                                                   # alles auf dem Blatt
        if isinstance(e, Z.Linie):
            assert 0 <= min(e.x0, e.x1) and max(e.x0, e.x1) <= 420 and 0 <= min(e.y0, e.y1) and max(e.y0, e.y1) <= 297

    scheibe = G.abziehen(G.zylinder(220, 20), G.zylinder(82, 30, -5),
                         *[G.zylinder(13.5, 30, -5, 90 * math.cos(i * math.pi / 4), 90 * math.sin(i * math.pi / 4))
                           for i in range(8)])
    z = Z.zeichnung_erstellen(scheibe, {"benennung": "Lagerdeckel"}, toleranzen={"Ø82": "H8"})
    texte = [e.text for e in z.elemente if isinstance(e, Z.Text)]
    assert "8× Ø13,5 auf Lochkreis Ø180" in texte and "Ø82 H8" in texte and "A–A" in texte
    assert sum(isinstance(e, Z.Linie) and e.art == "schraffur" for e in z.elemente) > 10
    pdf = Z.als_pdf(z, tmp_path / "d.pdf")
    assert pdf.read_bytes()[:5] == b"%PDF-" and pdf.stat().st_size > 5000
    dxf = Z.als_dxf(z, tmp_path / "d.dxf").read_text(encoding="cp1252").splitlines()
    assert len(dxf) % 2 == 0 and dxf[-1] == "EOF" and dxf.count("LINE") > 100
    assert "SICHTBAR" in dxf and "MITTE" in dxf and "8× Ø13,5 auf Lochkreis Ø180" in dxf


def test_baugruppe_im_projekt(tmp_path):
    p = Projekt.neu(tmp_path / "P", "Test", "Test")
    par = dataclasses.asdict(vorlagen.WelleParameter())
    form = vorlagen.erzeuge_welle(vorlagen.WelleParameter())
    e = G.eigenschaften(form)
    t = p.teil_speichern("welle", "Hauptwelle", par, e.masse(7850), e.volumen)
    assert abs(G.eigenschaften(p.teil_form(t["id"])["form"]).volumen - e.volumen) < 1e-6
    d = {"parameter": [], "einbauten": [
        {"id": "E1", "art": "teil", "teil_id": t["id"], "name": "Welle"},
        {"id": "E2", "art": "normteil", "norm": "6216", "bezug": {"ziel": "E1", "abstand": "400"}}]}
    r = p.baugruppe_bauen(d)
    assert r.ok
    g = p.baugruppe_speichern("Triebstrang", d, r.masse)
    assert g["nr"] == "G-001" and g["definition"] == d
    assert [b.nr for b in p.haengt_ab_von("baugruppe", g["id"])] == [t["nr"]]
    # Teil geändert → Baugruppe „neu prüfen“
    p.teil_speichern("welle", "Hauptwelle", {**par, "d_lager": 85.0}, teil_id=t["id"])
    assert p.baugruppe(g["id"])["status"] == NEU_PRUEFEN
    g2 = p.baugruppe_speichern("Triebstrang", d, r.masse, g["id"])
    assert g2["version"] == 2 and g2["status"] != NEU_PRUEFEN
    # Schema 5 beim erneuten Öffnen
    pfad = p.pfad
    p.schliessen()
    p2 = Projekt.oeffnen(pfad)
    assert len(p2.baugruppen()) == 1
    p2.schliessen()
