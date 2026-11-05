"""MS11: Inbetriebnahme-Checkliste (Soll/Ist), Leistungskurve, Abnahme, Wartungsplan, Rückmeldung."""
from datetime import date

from yamproduktion.berechnungen import ARTEN
from yamproduktion.betrieb import inbetriebnahme as IB, wartung as W
from yamproduktion.modell import NEU_PRUEFEN, Projekt


def _ber(p, typ, **werte):
    art = ARTEN[typ]
    e = art["eingaben"](**werte)
    return p.berechnung_speichern(art["berechne"](e).als_dict(), e.__dict__)


def test_bewertung_und_kurve():
    p = {"min": 200.0, "max": None, "ist": ""}
    assert IB.ergebnis(p) == IB.OFFEN
    assert IB.ergebnis({**p, "ist": "205"}) == IB.IO and IB.ergebnis({**p, "ist": "199,5"}) == IB.NIO
    assert IB.ergebnis({"min": None, "max": None, "ist": "i.O."}) == IB.IO
    assert IB.ergebnis({"min": None, "max": None, "ist": "nein"}) == IB.NIO
    assert IB.soll_text({"min": 5.0, "max": 5.0, "einheit": "kW"}) == "5 kW"
    assert IB.soll_text({"min": None, "max": 0.1, "einheit": "mm"}) == "≤ 0,1 mm"
    kurve = {"x": [0, 10, 20], "y": [0, 4, 5]}
    assert IB.kurve_soll(kurve, 5) == 2.0 and IB.kurve_soll(kurve, 15) == 4.5
    mp = IB.messung_auswerten({"soll_kurve": kurve, "messung": [{"v": 15, "p": 3.6}, {"v": 5, "p": 2.2}]})
    assert [m.v for m in mp] == [5, 15] and mp[0].ok and abs(mp[0].abweichung - 0.1) < 1e-9
    assert not mp[1].ok                       # 3,6 statt 4,5 kW = −20 % > ±15 %


def test_wartung_termine():
    assert W.plus_monate(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert W.plus_monate(date(2026, 11, 4), 14) == date(2028, 1, 4)
    pk = {"intervall": 12, "erstes": 1, "zuletzt": ""}
    assert W.faellig(pk, "2026-11-04") == date(2026, 12, 4)            # erstes Nachziehen nach 1 Monat
    assert W.faellig({**pk, "zuletzt": "2026-12-10"}, "2026-11-04") == date(2027, 12, 10)
    assert W.lesen("04.11.2026") == date(2026, 11, 4) and W.lesen("x") is None


def test_inbetriebnahme_wartung_im_projekt(tmp_path):
    p = Projekt.neu(tmp_path / "P", "KWA", "KWA", beispiel_kwa=True)
    for typ in ("rotorauslegung", "ertrag", "bremse", "lager"):
        _ber(p, typ)
    g = p.betrieb_grundlagen()
    assert {"n", "P_el", "t_Br", "v_ein", "v_ab", "L10h,A", "L10h,B", "t_unter"} <= set(g.werte) and g.kurve
    assert 0 < g.werte["t_unter"].wert < 1                              # % → Anteil
    ib = p.inbetriebnahme_neu(datum="2026-11-04")
    d = ib["daten"]
    assert ib["nr"] == "IB-001" and set(IB.GRUPPEN) == {x["gruppe"] for x in d["punkte"]}
    texte = " ".join(x["text"] for x in d["punkte"])
    for wort in ("Drehrichtung", "Bremse", "Überdrehzahl", "Sturmabschaltung", "Leistungskurve"):   # S12
        assert wort in texte
    n = g.werte["n"].wert
    ueber = next(x for x in d["punkte"] if x["text"].startswith("Überdrehzahl"))
    assert abs(ueber["max"] - round(1.2 * n, 1)) < 1e-9 and ueber["quelle"] == g.werte["n"].quelle
    sturm = next(x for x in d["punkte"] if x["text"].startswith("Sturm"))
    assert sturm["max"] == 25.0
    assert {b.typ for b in p.haengt_ab_von("inbetriebnahme", ib["id"])} == {"berechnung"}
    # alles i. O. → Abnahme; Leistungskurve setzt ihren Punkt selbst
    for x in d["punkte"]:
        x["ist"] = "i. O." if x["min"] is None and x["max"] is None else str(x["max"] if x["max"] is not None else x["min"])
    d["messung"] = [{"v": v, "p": IB.kurve_soll(d["soll_kurve"], v) * 1.05} for v in (4, 6, 8, 10, 12)]
    a = IB.auswerten(d)
    assert a["abgenommen"] and a["offen"] == 0 and len(a["messpunkte"]) == 5
    sturm["ist"] = "27"
    assert not IB.auswerten(d)["abgenommen"] and IB.maengel(d) == [sturm]
    ib = p.inbetriebnahme_speichern(ib["id"], d)
    assert ib["version"] == 2
    # Rückmeldung in die nächste Version (S14)
    idee = p.rueckmeldung("Sturmabschaltung zu spät", "Soll ≤ 25, Ist 27 m/s", "IB-001 P16")
    assert idee["nr"].startswith("I-") and "IB-001" in idee["beschreibung"]
    # Wartungsplan: Lager aus L10h, Verschleißteile, Fälligkeit
    wp = p.wartungsplan_neu(start="2026-11-04")
    punkte = wp["daten"]["punkte"]
    assert any(x["bauteil"].startswith("Hauptlager A") for x in punkte) and W.verschleissteile(wp["daten"])
    assert [x["bauteil"] for x in W.faellige(wp["daten"], date(2026, 12, 5))] == \
        ["Schraubverbindungen (Nabe, Blätter, Turmflansch)"]
    # Berechnung ändert sich → Checkliste und Wartungsplan „neu prüfen“
    b = next(x for x in p.berechnungen() if x.typ == "lager")
    p._wirkung_markieren("berechnung", b.id, "Test")
    assert p.wartungsplan(wp["id"])["status"] == NEU_PRUEFEN
    pfad = p.pfad
    from yamproduktion.pdf import abnahmeprotokoll_erstellen, messprotokoll_erstellen, wartungsplan_erstellen
    assert abnahmeprotokoll_erstellen(p.inbetriebnahme(ib["id"]), tmp_path / "a.pdf", "KWA").stat().st_size > 3000
    assert messprotokoll_erstellen(p.inbetriebnahme(ib["id"]), tmp_path / "m.pdf", "KWA").stat().st_size > 2000
    assert wartungsplan_erstellen(p.wartungsplan(wp["id"]), tmp_path / "w.pdf", "KWA").stat().st_size > 2000
    p.schliessen()
    p2 = Projekt.oeffnen(pfad)
    assert p2.meta("schema_version") == "9" and len(p2.inbetriebnahmen()) == 1
    p2.schliessen()
