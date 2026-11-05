"""MS13: Aufgaben, Meilensteine, Fortschritt je Phase, Zeitplan-Vorlage, Kosten Plan/Ist, Phasentore P5–P9."""
from datetime import date

import pytest

from yamproduktion.modell import Projekt, ProjektFehler, SCHEMA_VERSION
from yamproduktion.planung import kosten as K, zeitplan as Z


def test_zeitplan_vorlage_und_verzug():
    v = Z.vorlage_kwa(date(2026, 11, 9))
    assert v[0]["start"] == "2026-11-09" and v[0]["termin"] == "2026-11-15"
    genehmigung = next(a for a in v if a["titel"].startswith("Baugenehmigung"))
    konzept = next(a for a in v if a["titel"].startswith("Konzept") and not a["meilenstein"])
    assert genehmigung["start"] == "2026-11-16" and konzept["start"] == "2026-11-23"   # parallel, schiebt nicht
    assert {a["titel"] for a in v if a["meilenstein"]} >= {"Konzept festgelegt", "Konstruktion freigegeben", "Abnahme"}
    a = {"start": "2026-11-01", "termin": "2026-11-10", "stand": "in Arbeit", "meilenstein": 0}
    assert Z.verzug(a, date(2026, 11, 15)) == 5 and Z.verzug({**a, "stand": "erledigt"}, date(2026, 11, 15)) == 0
    assert Z.termin_text(a) == "01.11.2026 – 10.11.2026"
    assert Z.fortschritt(1, 4) == 25 and Z.fortschritt(0, 0) == 0 and Z.fortschritt(0, 3, True) == 100


def test_kosten():
    assert K.zahl("1 234,50 €") == 1234.5 and K.zahl("1200.5") == 1200.5 and K.zahl("x") is None
    posten = []
    K.posten_neu(posten, "Genehmigung & Gutachten", "Statik Turm", 1200, 1350)
    K.posten_neu(posten, "Zukaufteile", "Lager", 300, 280)
    u = K.uebersicht(posten, [{"kosten_plan": 50.0, "kosten_ist": None}])
    zeilen = {z["kostenart"]: z for z in u}
    assert zeilen["Genehmigung & Gutachten"]["ueber"] and not zeilen["Zukaufteile"]["ueber"]
    assert zeilen["Summe"]["plan"] == 1550 and zeilen["Summe"]["ist"] == 1630 and zeilen["Aufgaben"]["plan"] == 50


def test_aufgaben_im_projekt(tmp_path):
    p = Projekt.neu(tmp_path / "P", "KWA", "KWA", beispiel_kwa=True)
    a = p.aufgabe_neu("Turmstatik beauftragen", verantwortlich="Yamine", start="10.11.2026", termin="30.11.2026",
                      phase="P5", kosten_plan=1200.0)
    assert a["nr"] == "AU-001" and a["start"] == "2026-11-10" and a["stand"] == "offen"
    with pytest.raises(ProjektFehler, match="Start liegt nach"):
        p.aufgabe_aendern(a["id"], start="01.12.2026")
    with pytest.raises(ProjektFehler, match="Stand"):
        p.aufgabe_aendern(a["id"], stand="fertig")
    with pytest.raises(ProjektFehler, match="TT.MM.JJJJ"):
        p.aufgabe_neu("x", termin="morgen")
    assert p.phase("P5").status == "offen"                      # Aufgaben öffnen keine Phase
    # Phasentor P5: Bauteil fehlt, Aufgabe offen
    h = p.phase_hindernisse("P5")
    assert any("kein Bauteil" in x for x in h) and any("AU-001" in x for x in h)
    assert p.phase_fortschritt("P5") == {"prozent": 0, "erledigt": 0, "gesamt": 1, "offene_aufgaben": [p.aufgabe(a["id"])]}
    a = p.aufgabe_aendern(a["id"], stand="erledigt", kosten_ist=1350.0)
    assert a["version"] == 2 and p.phase_fortschritt("P5")["prozent"] == 100
    assert not any("AU-001" in x for x in p.phase_hindernisse("P5"))
    # Fortschritt P2: Anforderungen der Vorlage geprüft zählen mit
    anf = p.anforderungen()
    p.status_setzen("anforderung", anf[0].id, "geprüft")
    f = p.phase_fortschritt("P2")
    assert f["erledigt"] == 1 and f["gesamt"] == len(anf) and 0 < f["prozent"] < 100
    # Vorlage, Kosten
    p.zeitplan_vorlage("09.11.2026")
    assert len(p.aufgaben()) == 1 + len(Z.vorlage_kwa(date(2026, 11, 9)))
    assert all(x["phase"] for x in p.aufgaben())
    zeilen = {z["kostenart"]: z for z in p.kosten_uebersicht()}
    assert zeilen["Aufgaben"]["plan"] == 1200 and zeilen["Aufgaben"]["ist"] == 1350 and zeilen["Summe"]["ueber"]
    posten = p.kosten_posten()
    K.posten_neu(posten, "Sonstiges", "Kran", 400)
    p.kosten_speichern(posten)
    assert p.kosten_posten()[0]["text"] == "Kran"
    p2 = Projekt.oeffnen(p.pfad)
    assert len(p2.aufgaben()) == len(p.aufgaben()) and p2.meta("schema_version") == str(SCHEMA_VERSION)
