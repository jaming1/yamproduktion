"""MS10: Montageplan (Reihenfolge, Werkzeuge, Anzugsmomente, Prüfschritte), Montageplatte, Explosion, Anleitung."""
import dataclasses

import pytest

from yamproduktion.berechnungen import ARTEN, wert_aus_ergebnis
from yamproduktion.berechnungen import schrauben as S
from yamproduktion.cad import geometrie as G, vorlagen as V
from yamproduktion.modell import NEU_PRUEFEN, Projekt
from yamproduktion.montage import montageplan as M, szene as SZ


def _ber(p, typ, **werte):
    art = ARTEN[typ]
    e = art["eingaben"](**werte)
    return p.berechnung_speichern(art["berechne"](e).als_dict(), e.__dict__)


def test_anzugsmoment_und_fuegetemperatur():
    # gleiche Formel wie die Schraubenberechnung: 8.8, µ = 0,12, D_Km = (SW + Durchgangsloch)/2
    m, quelle, _ = M.anzugsmoment("ISO 4017 M16x60", [])
    e = S.SchraubenEingaben(gewinde="M16", klasse="8.8", d_km=(24 + 17.5) / 2)
    assert m == round(wert_aus_ergebnis(S.berechne(e).als_dict(), "M_A")[0])
    assert 200 <= m <= 215 and "Richtwert" in quelle          # Tabellenbuch (VDI 2230, µ 0,12): ≈ 206 N·m
    assert 80 <= M.anzugsmoment("ISO 4762 M12x40", [])[0] <= 90     # Tabellenbuch ≈ 84 N·m
    # passende Schraubenberechnung des Projekts hat Vorrang, andere Klasse → Hinweis
    rechnung = [{"nr": "B-007", "gewinde": "M16", "klasse": "8.8", "m_a": 199.0}]
    assert M.anzugsmoment("ISO 4017 M16x60", rechnung)[:2] == (199.0, "aus B-007 (Schraubenberechnung)")
    m2, _, h = M.anzugsmoment("ISO 4017 M16x60", [{"nr": "B-002", "gewinde": "M16", "klasse": "10.9", "m_a": 300.0}])
    assert m2 == m and "10.9" in h
    # Schrumpfen: ΔT = (Ü + 0,001·d)/(α·d) → (0,07 + 0,08)/(11e-6·80) = 170,5 K → 20 + 170,5 → 195 °C
    T, weg = M.fuegetemperatur(80.0, 0.070)
    assert T == 195 and "170,5 K" in weg
    assert M.drehmomentschluessel(210) == "Drehmomentschlüssel 60–340 N·m"


def test_montageplatte_vorlage():
    p = V.MontageplatteParameter()
    f = V.erzeuge_montageplatte(p)
    assert G.ist_gueltig(f)
    e = G.eigenschaften(f)
    assert abs(e.minimum[0] + p.achshoehe + p.dicke) < 1e-6 and abs(e.maximum[0]) < 1e-6   # Oberkante = Achse
    punkte = V.montageplatte_aufnahmepunkte(p)
    assert [a["name"] for a in punkte] == ["A1", "A2", "B1", "B2", "B3", "B4"]
    with pytest.raises(G.GeometrieFehler, match="Achshöhe"):
        V.erzeuge_montageplatte(dataclasses.replace(p, achshoehe=50))
    with pytest.raises(G.GeometrieFehler, match="Grundplatte"):
        V.erzeuge_montageplatte(dataclasses.replace(p, z_2=900))


def _gondel(tmp_path):
    p = Projekt.neu(tmp_path / "P", "Test", "Test")
    _ber(p, "pressverband")
    _ber(p, "schrauben")                       # rechnet M16 in 10.9 – Normteile sind 8.8
    w, n = V.WelleParameter(), V.NabeParameter()
    ew, en = G.eigenschaften(V.erzeuge_welle(w)), G.eigenschaften(V.erzeuge_nabe(n))
    tw = p.teil_speichern("welle", "Hauptwelle", dataclasses.asdict(w), ew.masse(7850), ew.volumen)
    tn = p.teil_speichern("nabe", "Rotornabe", dataclasses.asdict(n), en.masse(7100), en.volumen)
    d = {"parameter": [], "einbauten": [
        {"id": "E1", "art": "teil", "teil_id": tw["id"], "name": "Hauptwelle", "lage": {}},
        {"id": "E2", "art": "normteil", "norm": "ISO 4017 M16x60", "name": "Blattschraube",
         "bezug": {"ziel": "E1", "abstand": "0", "umdrehen": True}, "kreis": {"anzahl": "12", "radius": "150"}},
        {"id": "E3", "art": "teil", "teil_id": tn["id"], "name": "Rotornabe", "bezug": {"ziel": "E1", "abstand": "0"}},
        {"id": "E4", "art": "normteil", "norm": "22216 E", "name": "Lager", "bezug": {"ziel": "E1", "abstand": "337"}}]}
    return p, p.baugruppe_speichern("Gondel", d), tw, tn


def test_montageplan_gondel(tmp_path):
    p, g, tw, tn = _gondel(tmp_path)
    # Montageplatte: Auflagen am freien Bund Ø90 zwischen Lager und Wellenende, Achshöhe = R_max + 25
    werte, hinweise = p.montageplatte_vorschlag(g["id"])
    assert werte["d_auflage"] == 90.0 and 370 < werte["z_1"] < werte["z_2"] < 737
    assert werte["achshoehe"] == 205.0 and any("180 mm" in h for h in hinweise)
    platte = p.montageplatte_anlegen(g["id"])
    assert platte["vorlage"] == "montageplatte" and platte["masse"] > 10 and p.montageplatten() == [p.teil(platte["id"])]

    plan = p.montageplan_vorschlag(g["id"], platte["id"])
    titel = [s["titel"] for s in plan["schritte"]]
    # Reihenfolge: Vorrichtung → Grundteil → Lager → Nabe → Schrauben → Endkontrolle
    assert titel[0] == M.VORRICHTUNG_TITEL and titel[1].startswith("Grundteil Hauptwelle")
    assert titel[2].startswith("Lager 22216 E") and "Rotornabe" in titel[3] and "aufschrumpfen" in titel[3]
    assert titel[4].startswith("12× ISO 4017 M16x60") and titel[-1] == "Endkontrolle"
    assert [s["nr"] for s in plan["schritte"]] == list(range(1, 7))
    nabe = plan["schritte"][3]
    assert "195 °C" in nabe["text"] and "B-001" in nabe["text"] and "Hebezeug mit Rundschlinge" in nabe["werkzeuge"]
    schrauben = plan["schritte"][4]
    assert schrauben["momente"][0]["wert"] == M.anzugsmoment("ISO 4017 M16x60", [])[0]
    assert "Steckschlüssel SW 24" in schrauben["werkzeuge"] and any("Lackstrich" in q for q in schrauben["pruefung"])
    assert any("10.9" in h for h in plan["hinweise"]) and any("Passfeder fehlt" in h for h in plan["hinweise"])
    assert M.pruefen(plan, g["definition"]) == []
    assert M.gesamtzeit(plan) == 15 + 10 + 20 + 30 + (1.5 * 12 + 3) + 15
    assert "Induktions-Anwärmgerät" in M.werkzeugliste(plan)

    mp = p.montageplan_speichern(g["id"], plan)
    assert mp["nr"] == "M-001" and {b.nr for b in p.haengt_ab_von("montageplan", mp["id"])} == {g["nr"], platte["nr"]}
    # Explosion: Grundteil bleibt, Nabe wandert entlang der Achse nach −z, Schrauben noch weiter heraus
    erg = p.baugruppe_bauen(g["definition"])
    ex = M.explosion(g["definition"], erg, 1.0)
    ein = [x.einbau for x in erg.exemplare]
    v_nabe, v_schraube = ex[ein.index("E3")], ex[ein.index("E2")]
    assert not ex[0].any() and abs(v_nabe[0]) < 1e-9 and v_nabe[2] < -300 and v_schraube[2] < v_nabe[2]
    # Szene: Montagezustand je Schritt
    sz = SZ.aufbauen(erg, p.teil_form(platte["id"])["form"], erg.exemplare[0].matrix)
    assert sz.anzahl == len(erg.exemplare) + 1 and sz.vorrichtung == sz.anzahl - 1
    sichtbar, neu = SZ.schritt_ansicht(sz, plan, 5)
    assert sichtbar.all()
    assert len(neu) == 12
    sichtbar, neu = SZ.schritt_ansicht(sz, plan, 3)
    assert sichtbar.sum() == 3 and len(neu) == 1          # Platte, Welle, Lager
    n = sz.netz(None, sichtbar)
    assert len(sz.gruppen(neu, sichtbar)) == len(n.dreiecke) and (sz.gruppen(neu, sichtbar) == SZ.GRUPPE_NEU).any()

    # Änderungen wirken: Vorrichtung neu bemessen → Plan „neu prüfen“; Plan fehlt ein Einbau → Meldung
    p.montageplatte_anlegen(g["id"], teil_id=platte["id"])
    assert p.montageplan_von_baugruppe(g["id"])["status"] == NEU_PRUEFEN
    plan["schritte"].pop(2)
    assert any("Lager" in m and "keinem Schritt" in m for m in M.pruefen(plan, g["definition"]))
    # Baugruppe löschen → Montageplan weg; Schema 7
    p.baugruppe_loeschen(g["id"])
    assert p.montageplaene() == []
    pfad = p.pfad
    p.schliessen()
    p2 = Projekt.oeffnen(pfad)
    assert p2.meta("schema_version") == "7"
    p2.schliessen()
