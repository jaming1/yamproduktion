"""MS12: Grenzmaße, Prüfmerkmale aus der Zeichnung, FMEA, Risikobeurteilung, Normen, Abweichungen, Doku-Paket."""
import dataclasses

import pytest
from pypdf import PdfReader

from yamproduktion.berechnungen import ARTEN
from yamproduktion.betrieb import inbetriebnahme as IB
from yamproduktion.cad import geometrie as G, vorlagen as V
from yamproduktion.modell import NEU_PRUEFEN, Projekt, ProjektFehler
from yamproduktion.qualitaet import dokumentation as D, pruefplan as PP, tabellen as Q, toleranzen as T


def _ber(p, typ, **werte):
    art = ARTEN[typ]
    e = art["eingaben"](**werte)
    return p.berechnung_speichern(art["berechne"](e).als_dict(), e.__dict__)


def test_grenzmasse_und_merkmale():
    assert T.passung(80, "k6") == pytest.approx((0.002, 0.021))       # Ø80 k6: +2/+21 µm
    assert T.passung(140, "H7") == pytest.approx((0.0, 0.040))
    assert T.passung(30, "g6") == pytest.approx((-0.020, -0.007))
    assert T.passung(50, "f7") == pytest.approx((-0.050, -0.025))
    assert T.passung(25, "js6") == pytest.approx((-0.0065, 0.0065))
    assert T.passung(30, "G7") == pytest.approx((0.007, 0.028))
    assert T.passung(30, "X7") is None and T.passung(600, "H7") is None
    assert T.allgemein(120) == 0.3 and T.allgemein(121) == 0.5 and T.allgemein(0.3) is None
    m = PP.merkmal_aus_text("Ø80 k6")
    assert (m["min"], m["max"], m["innen"]) == (80.002, 80.021, False) and m["pruefmittel"] == "Grenzrachenlehre k6"
    m = PP.merkmal_aus_text("Ø140 H7")
    assert m["innen"] and m["pruefmittel"] == "Grenzlehrdorn H7"
    m = PP.merkmal_aus_text("6× Ø13,5")
    assert m["art"] == "Bohrungen" and m["min"] == 13.3 and "6 Stück" in m["bemerkung"]
    assert PP.merkmal_aus_text("Lochkreis Ø100")["art"] == "Lochkreis"
    assert PP.merkmal_aus_text("Ø30 X7")["min"] is None
    assert PP.pruefmittel(0.05, False) == "Bügelmessschraube 0,01 mm" and PP.pruefmittel(0.01, True).startswith("Fein")
    assert PP.ergebnis({**PP.merkmal_aus_text("120"), "ist": "120,25"}) == IB.IO
    assert PP.ergebnis({**PP.merkmal_aus_text("120"), "ist": "120,35"}) == IB.NIO
    assert Projekt.passmasse_lesen("Ø80 k6; Ø13,5 H7, Ø140 H7") == {"80": "k6", "13,5": "H7", "140": "H7"}


def test_bewertungen():
    z = {"B": "10", "A": "2", "E": "8", "B2": "", "A2": "", "E2": ""}
    assert Q.rpz(z) == 160 and Q.fmea_bewerten(z) == ("Handlungsbedarf", Q.ROT)
    z.update(B2="10", A2="2", E2="3")
    assert Q.fmea_bewerten(z) == ("nach Maßnahme RPZ 60", Q.GELB)
    r = {"S": "4", "W": "3", "S2": "4", "W2": "1", "umgesetzt": "nein"}
    assert Q.risiko(r) == 12 and Q.risiko_bewerten(r) == ("Maßnahme umsetzen", Q.ROT)
    assert Q.risiko_bewerten({**r, "umgesetzt": "ja"}) == ("Restrisiko akzeptabel", Q.GRUEN)
    assert Q.abweichung_bewerten({"massnahme": "x", "wirksam": "offen"})[1] == Q.GELB
    assert Q.abweichung_bewerten({"wirksam": "ja"}) == ("abgeschlossen", Q.GRUEN)


def test_qualitaet_im_projekt(tmp_path):
    p = Projekt.neu(tmp_path / "P", "KWA", "KWA", beispiel_kwa=True)
    w_ber = _ber(p, "welle")
    for typ in ("schrauben", "lager", "turm"):
        _ber(p, typ)
    w = V.WelleParameter()
    e = G.eigenschaften(V.erzeuge_welle(w))
    t = p.teil_speichern("welle", "Hauptwelle", dataclasses.asdict(w), e.masse(7850), e.volumen,
                         {"d_lager": ("berechnung", w_ber.id)})
    p.passmasse_speichern("teil", t["id"], f"Ø{w.d_lager:g} k6")
    assert p.passmasse("teil", t["id"]) == f"Ø{w.d_lager:g} k6"
    # Prüfplan aus der Zeichnung (M43): Passmaß zuerst, Grenzmaße nach ISO 286
    pp = p.pruefplan_neu(t["id"])
    mm = pp["daten"]["merkmale"]
    assert pp["nr"] == "PP-001" and mm[0]["merkmal"] == f"Ø{w.d_lager:g} k6" and len(mm) >= 6
    assert all(m["pruefmittel"] for m in mm) and {b.nr for b in p.haengt_ab_von("pruefplan", pp["id"])} == {t["nr"]}
    with pytest.raises(ProjektFehler):
        p.pruefplan_neu(t["id"])
    mm[0]["ist"] = "80,030"
    mm[1]["ist"] = f"{mm[1]['nenn']:g}"
    pp = p.pruefplan_speichern(pp["id"], pp["daten"])
    assert PP.auswerten(pp["daten"])["gesamt"] == IB.NIO and pp["daten"]["merkmale"][1]["ergebnis"] == IB.IO
    # Zeichnung ändert sich (neues Passmaß) → aktualisieren, Ist-Werte bleiben
    p.passmasse_speichern("teil", t["id"], f"Ø{w.d_lager:g} m6")
    pp, neu, weg = p.pruefplan_aktualisieren(pp["id"])
    assert (neu, weg) == (1, 1) and pp["daten"]["merkmale"][1]["ist"]
    assert pp["daten"]["merkmale"][0]["min"] == pytest.approx(w.d_lager + 0.011)        # m6: +11/+30 µm
    pp["daten"]["merkmale"][0]["ist"] = f"{w.d_lager + 0.05:g}"
    pp = p.pruefplan_speichern(pp["id"], pp["daten"])
    # Teil ändert sich → Prüfplan „neu prüfen“
    p._wirkung_markieren("teil", t["id"], "Test")
    assert p.pruefplan(pp["id"])["status"] == NEU_PRUEFEN
    # FMEA, Risiko, Normen (M44, M46, M47): Nachweise aus den Berechnungen, verknüpft
    fm = p.qdok_neu("fmea")
    welle = next(z for z in fm["daten"]["zeilen"] if z["element"] == "Hauptwelle")
    assert w_ber.nr in welle["vermeidung"] and fm["name"] == "Konstruktions-FMEA"
    assert w_ber.nr in {b.nr for b in p.haengt_ab_von("fmea", fm["id"])}
    pf = p.qdok_neu("fmea", "Prozess-FMEA")
    assert pf["art"] == "Prozess-FMEA" and any("Schweißen" in z["element"] for z in pf["daten"]["zeilen"])
    rb = p.qdok_neu("risiko")
    assert len(rb["daten"]["zeilen"]) >= 12 and rb["daten"]["grenzen"]["lebensdauer"]
    assert {z["phase"] for z in rb["daten"]["zeilen"]} >= {"Betrieb", "Montage", "Wartung"}
    nl = p.qdok_neu("normen")
    norm = {z["norm"]: z for z in nl["daten"]["zeilen"]}
    assert norm["DIN 743"]["status"] == "in Arbeit" and w_ber.nr in norm["DIN 743"]["nachweis"]
    assert norm["EN ISO 12100"]["nachweis"] == rb["nr"] and norm["IEC 61400-2"]["status"] == "offen"
    _ber(p, "lasten_iec")
    nl, n = p.normen_abgleichen(nl["id"])
    assert n >= 1 and {z["norm"]: z for z in nl["daten"]["zeilen"]}["IEC 61400-2"]["status"] == "in Arbeit"
    # Abweichungen (M45): n. i. O. aus dem Prüfplan übernehmen, nicht doppelt
    qa = p.qdok_neu("abweichung")
    qa, n = p.abweichungen_uebernehmen(qa["id"])
    assert n == 1 and qa["daten"]["zeilen"][0]["herkunft"] == "PP-001"
    assert p.abweichungen_uebernehmen(qa["id"])[1] == 0
    # Technische Dokumentation (S16): ein PDF mit Lesezeichen, fehlende Kapitel markiert
    ziel, inhalt = D.erstellen(p, tmp_path / "Doku.pdf", "Test")
    r = PdfReader(str(ziel))
    kapitel = {k: s for k, s, _ in inhalt}
    assert kapitel["Lastenheft"] == 2 and kapitel["Montageanleitungen"] is None
    assert len(r.pages) >= 15 and [o.title for o in r.outline if not isinstance(o, list)][:3] == \
        ["Deckblatt und Inhalt", "Lastenheft", "Normen-Checkliste"]
    # Löschen des Teils entfernt den Prüfplan
    p.teil_loeschen(t["id"])
    assert p.pruefplaene() == []
