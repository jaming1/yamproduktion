"""MS7: Formeln, Skizzen-Löser, Feature-Baum und freie Teile im Projekt – geprüft gegen geschlossene Formeln."""
import math
from pathlib import Path

import pytest

from yamproduktion.cad import geometrie as G, modellierer as M, skizze as S
from yamproduktion.cad.ausdruck import AusdruckFehler, auswerten, berechnungsbezuege, tabelle_auswerten
from yamproduktion.modell import NEU_PRUEFEN, Projekt

BEISPIEL_STEP = Path(__file__).parents[2] / "daten" / "beispiele" / "T-001_Hauptwelle_KWA-5.step"


# ---------------------------------------------------------------- Formeln
def test_formeln():
    assert auswerten("2*d + 5", {"d": 80}) == 165
    assert auswerten("1,5 · 4") == 6                      # Dezimalkomma und Malpunkt
    assert auswerten("max(3; 7) + sqrt(16)") == 11
    assert abs(auswerten("cos(60)") - 0.5) < 1e-12        # Winkel in Grad
    assert auswerten('ber("welle", "d") / 2', ber=lambda t, s: 80.0) == 40
    assert berechnungsbezuege('ber("welle", "d") + ber("turm", "D")') == [("welle", "d"), ("turm", "D")]
    with pytest.raises(AusdruckFehler, match="Unbekannter Parameter"):
        auswerten("x + 1")
    with pytest.raises(AusdruckFehler):
        auswerten("__import__('os')")
    with pytest.raises(AusdruckFehler, match="Division durch 0"):
        auswerten("1/0")


def test_parameter_tabelle():
    werte = tabelle_auswerten([{"name": "l", "formel": "2*d"}, {"name": "d", "formel": "40"},
                               {"name": "r", "formel": "d/2"}])
    assert werte == {"d": 40, "l": 80, "r": 20}            # Reihenfolge egal
    with pytest.raises(AusdruckFehler, match="Kreis"):
        tabelle_auswerten([{"name": "a", "formel": "b"}, {"name": "b", "formel": "a"}])
    with pytest.raises(AusdruckFehler, match="doppelt"):
        tabelle_auswerten([{"name": "a", "formel": "1"}, {"name": "a", "formel": "2"}])
    with pytest.raises(AusdruckFehler, match="kein gültiger Parametername"):
        tabelle_auswerten([{"name": "2a", "formel": "1"}])


# ---------------------------------------------------------------- Skizzen
def _rechteck(b="b", h="h"):
    sk = S.leer()
    e = S.rechteck_neu(sk, 0, 0, 90, 40)
    S.bedingung(sk, "koinzident", a="p0", b=S.element(sk, e[0])["p"][0])
    S.bedingung(sk, "laenge", e=e[0], wert=b)
    S.bedingung(sk, "laenge", e=e[1], wert=h)
    return sk, e


def test_skizze_loest_bemassung():
    sk, e = _rechteck()
    l = S.loesen(sk, {"b": 100, "h": 50})
    assert l.ok
    xs = sorted({round(x, 6) for x, _ in l.punkte.values()})
    ys = sorted({round(y, 6) for _, y in l.punkte.values()})
    assert xs == [0, 100] and ys == [0, 50]
    # Widerspruch: zweite Länge für die Gegenseite
    S.bedingung(sk, "laenge", e=e[2], wert="90")
    l = S.loesen(sk, {"b": 100, "h": 50})
    assert not l.ok and "widersprechen" in l.meldung


def test_skizze_flaeche_mit_loch_und_langloch():
    sk, _ = _rechteck()
    m = S.punkt_neu(sk, 30, 20)
    k = S.kreis_neu(sk, m, 3)
    S.bedingung(sk, "durchmesser", e=k, wert="8")
    flaechen, _ = S.flaechen(sk, {"b": 50, "h": 30})
    assert len(flaechen) == 1
    assert abs(G.eigenschaften(flaechen[0]).flaeche - (50 * 30 - math.pi * 16)) < 1e-6
    # Langloch aus zwei Bögen und zwei Linien: 20 lang (Mittenabstand), Radius 5
    lk = S.leer()
    m1, m2 = S.punkt_neu(lk, 0, 0), S.punkt_neu(lk, 20, 0)
    a1, b1 = S.punkt_neu(lk, 0, -5), S.punkt_neu(lk, 0, 5)
    a2, b2 = S.punkt_neu(lk, 20, -5), S.punkt_neu(lk, 20, 5)
    S.bogen_neu(lk, m1, b1, a1)
    S.bogen_neu(lk, m2, a2, b2)
    S.linie_neu(lk, a1, a2)
    S.linie_neu(lk, b2, b1)
    flaechen, _ = S.flaechen(lk)
    assert abs(G.eigenschaften(flaechen[0]).flaeche - (20 * 10 + math.pi * 25)) < 1e-6


# ---------------------------------------------------------------- Features
def _platte():
    sk, _ = _rechteck()
    return {"parameter": [{"name": "b", "formel": "100"}, {"name": "h", "formel": "b/2"}, {"name": "t", "formel": "20"},
                          {"name": "d", "formel": "10"}],
            "features": [{"art": "skizze", "name": "Skizze1", "skizze": sk},
                         {"art": "extrusion", "name": "Extrusion1", "skizze": "Skizze1", "hoehe": "t", "operation": "neu"},
                         {"art": "bohrung", "name": "Bohrung1", "ebene": "XY", "versatz": "t", "x": "20", "y": "h/2",
                          "d": "d", "tiefe": "durch"},
                         {"art": "muster", "name": "Muster1", "feature": "Bohrung1", "muster": "linear", "anzahl": "3",
                          "abstand": "30", "richtung": "x"}]}


def test_extrusion_bohrung_muster():
    d = _platte()
    r = M.bauen(d)
    assert r.ok, r.fehler
    assert [s.ok for s in r.schritte] == [True] * 4
    v = G.eigenschaften(r.form).volumen
    assert abs(v - (100 * 50 * 20 - 3 * math.pi * 25 * 20)) < 1e-6 * v
    # Parameter ändern → Teil folgt
    d["parameter"][0]["formel"] = "120"
    v2 = G.eigenschaften(M.bauen(d).form).volumen
    assert abs(v2 - (120 * 60 * 20 - 3 * math.pi * 25 * 20)) < 1e-6 * v2


def test_sackloch_fase_und_fehlermeldungen():
    d = _platte()
    d["features"][2]["tiefe"] = "12"
    d["features"].append({"art": "fase", "name": "Fase1", "groesse": "1", "kanten": "unten"})
    r = M.bauen(d)
    assert r.ok, r.fehler
    e = G.eigenschaften(r.form)
    # Fase 1×45° am unteren Umfang: Prisma 0,5 mm² × 300 mm, an den 4 Ecken je 1/3 mm³ doppelt gezählt
    assert abs(e.volumen - (100 * 50 * 20 - 3 * math.pi * 25 * 12 - 300 * 0.5 + 4 / 3)) < 1e-6
    d["features"][-1]["groesse"] = "30"
    r = M.bauen(d)
    assert not r.ok and r.schritte[-1].ok is False and "Fase1" in r.fehler
    assert r.form is not None                       # alles davor bleibt sichtbar
    d["features"][-1]["groesse"] = "q"
    assert "Unbekannter Parameter" in M.bauen(d).fehler
    d["features"][1]["skizze"] = "gibtsnicht"
    assert "gibt es (davor) nicht" in M.bauen(d).fehler


def test_rotation_und_verrundung():
    sk = S.leer("XZ")
    pts = ["p0"] + [S.punkt_neu(sk, *xy) for xy in [(20, 0), (20, 50), (15, 50), (15, 80), (0, 80)]]
    for i in range(6):
        S.linie_neu(sk, pts[i], pts[(i + 1) % 6])
    d = {"parameter": [], "features": [{"art": "skizze", "name": "S", "skizze": sk},
                                       {"art": "rotation", "name": "R", "skizze": "S", "achse": "y", "winkel": "360"}]}
    r = M.bauen(d)
    assert abs(G.eigenschaften(r.form).volumen - math.pi * (20 ** 2 * 50 + 15 ** 2 * 30)) < 1e-3
    d["features"].append({"art": "verrundung", "name": "V", "groesse": "2", "kanten": "aussen"})
    r2 = M.bauen(d)
    assert r2.ok and G.eigenschaften(r2.form).volumen < G.eigenschaften(r.form).volumen
    d["features"][-1]["groesse"] = "40"
    assert "lässt sich an diesen Kanten nicht anbringen" in M.bauen(d).fehler


def test_kreismuster_und_step_import():
    sk = S.leer()
    k = S.kreis_neu(sk, "p0", 50)
    S.bedingung(sk, "durchmesser", e=k, wert="140")
    d = {"parameter": [], "features": [
        {"art": "skizze", "name": "S", "skizze": sk},
        {"art": "extrusion", "name": "E", "skizze": "S", "hoehe": "10", "operation": "neu"},
        {"art": "bohrung", "name": "B", "ebene": "XY", "versatz": "10", "x": "55", "y": "0", "d": "9", "tiefe": "durch"},
        {"art": "muster", "name": "M", "feature": "B", "muster": "kreis", "anzahl": "6", "achse": "z", "winkel": "360"}]}
    r = M.bauen(d)
    assert r.ok
    assert abs(G.eigenschaften(r.form).volumen - math.pi * 10 * (70 ** 2 - 6 * 4.5 ** 2)) < 1e-3
    # STEP-Import der Hauptwelle aus MS6
    if BEISPIEL_STEP.exists():
        text = BEISPIEL_STEP.read_text(encoding="utf-8")
        r = M.bauen({"parameter": [], "features": [{"art": "import", "name": "I", "step": text, "operation": "neu"}]})
        assert r.ok
        assert abs(G.eigenschaften(r.form).volumen / G.eigenschaften(G.step_lesen(BEISPIEL_STEP)).volumen - 1) < 1e-9


# ---------------------------------------------------------------- Freie Teile im Projekt
def test_freies_teil_folgt_der_berechnung(tmp_path):
    from yamproduktion.berechnungen import welle
    projekt = Projekt.neu(tmp_path / "P", "Test", "")
    e = welle.WelleEingaben(d_mm=80)
    b = projekt.berechnung_speichern(welle.berechne(e).als_dict(), e.__dict__)
    sk = S.leer()
    k = S.kreis_neu(sk, "p0", 30)
    S.bedingung(sk, "durchmesser", e=k, wert="d")
    definition = {"parameter": [{"name": "d", "formel": 'ber("welle", "d")'}],
                  "features": [{"art": "skizze", "name": "S", "skizze": sk},
                               {"art": "extrusion", "name": "E", "skizze": "S", "hoehe": "100", "operation": "neu"}]}
    ber, quellen = projekt.ber_funktion()
    r = M.bauen(definition, ber)
    assert r.ok and quellen == {"welle.d": ("berechnung", b.id)}
    d0 = b.eingaben["d_mm"]
    assert abs(G.eigenschaften(r.form).volumen - math.pi * d0 ** 2 / 4 * 100) < 1e-6 * d0 ** 2 * 100
    t = projekt.teil_speichern("frei", "Bolzen", {"definition": definition, "werkstoff": ""}, None,
                               G.eigenschaften(r.form).volumen, quellen)
    assert [q.nr for q in projekt.haengt_ab_von("teil", t["id"])] == [b.nr]
    # Berechnung ändert sich (größerer Durchmesser, neue Version) → Teil „neu prüfen“ → neu erzeugen
    eingaben = dict(b.eingaben, d_mm=d0 + 10)
    projekt._db.execute("UPDATE berechnung SET eingaben=? WHERE id=?", (__import__("json").dumps(eingaben), b.id))
    projekt.berechnung_neu_rechnen(b.id)
    assert projekt.teil(t["id"])["status"] == NEU_PRUEFEN
    neu = projekt.teil_neu_erzeugen(t["id"])
    assert neu["version"] == 2 and neu["status"] != NEU_PRUEFEN
    assert abs(neu["volumen"] - math.pi * (d0 + 10) ** 2 / 4 * 100) < 1e-6 * neu["volumen"]


def test_loeser_winkel_tangente_abstand():
    """Eigener Löser: Winkel, Tangente Linie–Kreis, Abstand Punkt–Linie, Bogen bleibt auf dem Radius."""
    sk = S.leer()
    p1, p2 = S.punkt_neu(sk, 50, 5), S.punkt_neu(sk, 40, 30)
    basis = S.linie_neu(sk, "p0", p1)
    schraeg = S.linie_neu(sk, "p0", p2)
    S.bedingung(sk, "horizontal", e=basis)
    S.bedingung(sk, "laenge", e=basis, wert="60")
    S.bedingung(sk, "winkel", a=basis, b=schraeg, wert="30")
    S.bedingung(sk, "laenge", e=schraeg, wert="40")
    m = S.punkt_neu(sk, 30, 25)
    k = S.kreis_neu(sk, m, 6)
    S.bedingung(sk, "tangential", a=basis, b=k)
    S.bedingung(sk, "radius", e=k, wert="8")
    S.bedingung(sk, "abstand_h", a="p0", b=m, wert="25")
    l = S.loesen(sk)
    assert l.ok, l.meldung
    x2, y2 = l.punkte[p2]
    assert abs(math.degrees(math.atan2(y2, x2)) - 30) < 1e-6 and abs(math.hypot(x2, y2) - 40) < 1e-6
    assert abs(l.punkte[p1][1]) < 1e-9 and abs(l.punkte[p1][0] - 60) < 1e-6
    assert abs(l.punkte[m][1] - 8) < 1e-6 and abs(l.punkte[m][0] - 25) < 1e-6 and abs(l.radien[k] - 8) < 1e-9
    assert l.freiheitsgrade == 0                       # vollständig bestimmt
    # Bogen: Endpunkt wird auf den Radius gezogen
    bg = S.leer()
    mm, a, b = S.punkt_neu(bg, 10, 0), S.punkt_neu(bg, 20, 0), S.punkt_neu(bg, 10, 13)
    bogen = S.bogen_neu(bg, mm, a, b)
    S.bedingung(bg, "radius", e=bogen, wert="12")
    l = S.loesen(bg)
    assert l.ok
    for q in (a, b):
        assert abs(math.hypot(l.punkte[q][0] - l.punkte[mm][0], l.punkte[q][1] - l.punkte[mm][1]) - 12) < 1e-6
    assert l.freiheitsgrade > 0                       # Lage und Öffnungswinkel noch frei
