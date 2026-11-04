"""MS9: Schnittdaten und Hauptzeiten, Rohteil, Arbeitsplan-Vorschlag, Kalkulation, Anfrageliste, PDFs."""
import dataclasses
import math

import pytest

from yamproduktion.cad import baugruppe as BG, geometrie as G, vorlagen as V
from yamproduktion.fertigung import arbeitsplan as A, schnittdaten as S
from yamproduktion.modell import NEU_PRUEFEN, Projekt


def test_schnittdaten_handrechnung():
    # n = v_c · 1000 / (π d): 200 m/min an Ø100 → 636,6 1/min
    assert abs(S.drehzahl(200, 100, 5000) - 636.62) < 0.01
    assert S.drehzahl(200, 5, 3000) == 3000                       # Grenze der Maschine
    # Längsdrehen Vergütungsstahl Ø95 → Ø80 auf 100 mm: 7,5 mm Aufmaß → 3 Schnitte, n bei Ø95
    z = S.laengsdrehen("Vergütungsstahl", [[95, 80, 100]], schlichten=False)
    n = 160 * 1000 / (math.pi * 95)
    assert abs(z.th - (100 + S.ANLAUF) * 3 / (0.25 * n)) < 1e-9
    assert abs(z.te - (z.th * 1.25 + 1.0)) < 1e-12
    # Bohren Baustahl 4 × Ø18 tief 30: f = 0,27 mm, L = 30 + 5,4 + 2
    z = S.bohren("Baustahl", 18, 30, 4)
    n = 30 * 1000 / (math.pi * 18)
    assert abs(z.th - 4 * 37.4 / (0.27 * n)) < 1e-9
    # Fräsen: v_f = f_z · z · n, Zustellungen nach Tiefe / (0,5 · D)
    z = S.fraesen("Baustahl", 100, 12, 20)
    n = 180 * 1000 / (math.pi * 20)
    assert abs(z.th - (100 + 20 + 4) * 2 / (0.12 * 4 * n)) < 1e-9
    assert abs(S.saegen("Baustahl", 2000).th - 1.0) < 1e-12     # 20 cm² bei 20 cm²/min
    with pytest.raises(S.SchnittFehler, match="keine Zerspanungs-Richtwerte"):
        S.richtwerte("Faserverbund")


def test_vorschlag_welle_nabe_flansch():
    p = V.WelleParameter()
    welle = V.erzeuge_welle(p)
    plan = A.vorschlag(welle, p.werkstoff, "Hauptwelle", "welle")
    r = plan["rohteil"]
    assert r["art"] == "Rundstahl" and r["d"] == 95 and abs(r["l"] - (G.eigenschaften(welle).groesse[2] + 5)) < 1e-6
    assert [v["art"] for v in plan["vorgaenge"]] == ["saegen", "plandrehen", "laengsdrehen", "fraesen", "manuell"]
    assert "Passfedernut 20 × 90" in plan["vorgaenge"][3]["text"]          # Nut b = 20, l = 90 erkannt
    k = A.kalkulieren(plan)
    masse = math.pi / 4 * 95 ** 2 * r["l"] * 1e-9 * 7850
    assert abs(k.rohteil_masse - masse) < 1e-9 and abs(k.material - masse * 2.8) < 1e-9
    fertigung = sum((g.tr + g.te) / 60 * A.STUNDENSAETZE[g.maschine] for g in k.gaenge)
    assert abs(k.fertigung - fertigung) < 1e-9 and abs(k.stueck - k.material - k.fertigung) < 1e-9
    assert not k.fehler and 20 < k.te_summe < 120

    # Los von 10: Rüstkosten verteilt
    plan["losgroesse"] = 10
    k10 = A.kalkulieren(plan)
    assert k10.stueck < k.stueck and abs(k10.los - 10 * k10.stueck) < 1e-9

    # Fremdfertigung ohne Angebot = Eigenkosten + 25 %, mit Angebot = Angebot
    plan["fertigung"] = "fremd"
    kf = A.kalkulieren(plan)
    assert kf.fremd_geschaetzt and abs(kf.stueck - 1.25 * (kf.material + kf.fertigung)) < 1e-9
    plan["preis_fremd"] = 180.0
    assert A.kalkulieren(plan).stueck == 180.0

    pn = V.NabeParameter()
    plan = A.vorschlag(V.erzeuge_nabe(pn), pn.werkstoff, "Nabe", "nabe")
    assert plan["rohteil"]["art"] == "Guss" and plan["vorgaenge"][0]["art"] == "guss"
    assert any("12× Ø17.5" in v["text"] for v in plan["vorgaenge"])
    assert sum("Ø80 ausdrehen" in v["text"] for v in plan["vorgaenge"]) == 1     # geteilte Bohrfläche nur einmal

    pf = V.FlanschParameter()
    plan = A.vorschlag(V.erzeuge_flansch(pf), pf.werkstoff, "Flansch", "flansch")
    assert plan["rohteil"]["art"] == "Blech" and "Innenausschnitt" in plan["vorgaenge"][0]["text"]
    assert any("16× Ø26" in v["text"] for v in plan["vorgaenge"])

    pz = V.ZahnradParameter()
    plan = A.vorschlag(V.erzeuge_zahnrad(pz), pz.werkstoff, "Ritzel", "zahnrad")
    assert plan["fertigung"] == "fremd" and any("Verzahnen" in v["text"] for v in plan["vorgaenge"])
    k = A.kalkulieren(plan)
    assert any("keine Stückzeit" in f for f in k.fehler)                # Verzahnzeit muss erfragt werden

    # Handzeit überschreibt die Rechnung; unbekannte Maschine → Hinweis
    plan["vorgaenge"][-1]["te"] = 12.0
    plan["vorgaenge"][0]["maschine"] = "Laserzelle"
    k = A.kalkulieren(plan)
    assert k.gaenge[-1].te == 12.0 and k.gaenge[-1].von_hand
    assert any("Laserzelle" in f for f in k.fehler)


def test_baugruppe_kalkulieren():
    liste = [BG.Position(1, 1, "Welle", "T-001", "42CrMo4", 36.0, "Bauteil"),
             BG.Position(2, 2, "Lager", "22216 E", "100Cr6", 1.7, "Normteil"),
             BG.Position(3, 12, "Schraube", "ISO 4017 M16x60", "8.8", 0.12, "Normteil"),
             BG.Position(4, 1, "Nabe", "T-002", "GJS", 22.0, "Bauteil")]
    k = A.kalkulieren(A.vorschlag(V.erzeuge_welle(V.WelleParameter()), V.WelleParameter().werkstoff))
    saetze = A.standard_saetze()
    saetze["zukauf"] = {"22216 E": 95.0}
    zeilen, summe, fehlend = A.baugruppe_kalkulieren(liste, {"T-001": k}, saetze, anzahl=2)
    assert fehlend == ["ISO 4017 M16x60", "T-002"]
    assert abs(summe - 2 * (k.stueck + 2 * 95.0)) < 1e-9
    assert zeilen[1].gesamt == 190.0 and zeilen[3].hinweis == "Arbeitsplan fehlt"


def test_arbeitsplan_im_projekt(tmp_path):
    p = Projekt.neu(tmp_path / "P", "Test", "Test")
    par = dataclasses.asdict(V.WelleParameter())
    e = G.eigenschaften(V.erzeuge_welle(V.WelleParameter()))
    t = p.teil_speichern("welle", "Hauptwelle", par, e.masse(7850), e.volumen)
    plan = p.arbeitsplan_vorschlag(t["id"])
    ap = p.arbeitsplan_speichern(t["id"], plan)
    assert ap["nr"] == "AP-001" and ap["kosten"] > 0 and ap["name"] == "T-001 Hauptwelle"
    assert [b.nr for b in p.haengt_ab_von("arbeitsplan", ap["id"])] == ["T-001"]
    # eigene Sätze → neue Kosten
    s = p.kostensaetze()
    s["stundensaetze"]["Drehmaschine"] = 120.0
    p.kostensaetze_speichern(s)
    assert p.kalkulation_teil(t["id"]).stueck > ap["kosten"]
    assert p.kostensaetze()["materialpreise"]["Baustahl"] == A.MATERIALPREISE["Baustahl"]
    # Fremd → Anfrageliste
    plan["fertigung"] = "fremd"
    plan["losgroesse"] = 2
    p.arbeitsplan_speichern(t["id"], plan)
    e1 = p.anfrage_eintraege()
    assert len(e1) == 1 and e1[0]["menge"] == 2 and "Längsdrehen" in e1[0]["verfahren"]
    assert e1[0]["rohteil"].startswith("Rundstahl Ø95")
    # Teil ändert sich → Arbeitsplan „neu prüfen“
    p.teil_speichern("welle", "Hauptwelle", {**par, "l_ende": 100.0}, teil_id=t["id"])
    assert p.arbeitsplan_von_teil(t["id"])["status"] == NEU_PRUEFEN
    # PDFs
    from yamproduktion.pdf import anfrageliste_erstellen, arbeitsplan_erstellen
    k = p.kalkulation_teil(t["id"])
    assert arbeitsplan_erstellen(p.teil(t["id"]), plan, k, tmp_path / "ap.pdf").stat().st_size > 3000
    assert anfrageliste_erstellen(e1, tmp_path / "an.pdf", "Test").stat().st_size > 2000
    # Teil löschen → Arbeitsplan weg
    p.teil_loeschen(t["id"])
    assert p.arbeitsplaene() == []
    pfad = p.pfad
    p.schliessen()
    p2 = Projekt.oeffnen(pfad)
    assert p2.meta("schema_version") == "8"
    p2.schliessen()
