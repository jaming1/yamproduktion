"""K5: CAM-Export – G-Code für Drehen (zwei Aufspannungen), Passfedernut, Bohrbild, Außenkontur; Prüfleser."""
import dataclasses
import math

import pytest

from yamproduktion.cad import geometrie as G, vorlagen as V
from yamproduktion.fertigung import arbeitsplan as A, cam, schnittdaten as S
from yamproduktion.modell import NEU_PRUEFEN, SCHEMA_VERSION, Projekt


def _welle():
    p = V.WelleParameter()
    form = V.erzeuge_welle(p)
    return form, A.vorschlag(form, p.werkstoff, "Hauptwelle", "welle")


def _saetze(text: str) -> list[str]:
    """Sätze ohne Satznummern und Kommentare."""
    out = []
    for z in text.splitlines():
        z = z.split("(")[0].strip()
        if z.startswith("N"):
            z = z.split(" ", 1)[1] if " " in z else ""
        if z and z != "%":
            out.append(z)
    return out


def test_welle_drehen_zwei_aufspannungen():
    form, plan = _welle()
    progs = cam.erzeugen(form, plan, None, "T-001 Hauptwelle")
    assert [p.schluessel for p in progs] == ["drehen_1", "drehen_2", "fraesen_nut"]
    d1, d2, nut = progs
    assert d1.maschine == "Drehmaschine" and nut.maschine == "Fräsmaschine"
    for p in progs:
        pr = cam.pruefen(p.text, p.art)
        assert pr.ok, pr.fehler
        assert p.zeilen[0] == "%" and p.zeilen[-1] == "%" and p.text.isascii()
        assert "M30" in p.text and "UNGEPRUEFT" in p.text
    s = _saetze(d1.text)
    # Rohteil Ø95 × 848, Teil 843 lang → 2,5 mm je Stirnseite; Plandrehen bis über die Mitte
    assert "G0 X99 Z4.5" in s and "G1 X-1.6 F0.25" in s
    # Schruppen: Ø95 → 90,6 (Aufmaß 0,3) bis zur Teilungsstelle in der Mitte des Ø90 (z = 550 → 293 mm)
    i = s.index("G0 X90.6")
    assert s[i + 1] == "G1 Z-293 F0.25"
    # Ø80,6 endet am Kegel/Absatz vor Ø90: Absatz bei w = 107,5 (Fase 1,5 mm) → bei Ø80,6 genau 106
    assert s[s.index("G0 X80.6") + 1] == "G1 Z-106"                 # F ist modal
    # Schlichtkontur von der Stirnfase bis zum Ø90
    assert "G1 X70 Z-1.5" in s and "G1 X90 Z-107.5" in s and "G1 X90 Z-293" in s
    # Drehzahl Schruppen: v_c 160 m/min an Ø95 (Vergütungsstahl), konstant G97
    n = round(S.drehzahl(160, 95, S.N_MAX_DREHEN))
    assert f"G97 S{n} M3" in s and "G95" in s
    # Schlanke Welle: Zentrierbohrung vor dem Schruppen, Halt zum Anstellen des Reitstocks
    assert s.index("T0303") < s.index("G0 X90.6") and "M0" in s
    assert any("Reitstock" in w for w in d1.warnungen)
    # Aufspannung 2 von der anderen Stirnseite: Ø75 und Ø80
    s2 = _saetze(d2.text)
    assert "G1 X75 Z-1.5" in s2 and "G1 X75 Z-100" in s2 and "G1 X80 Z-101.5" in s2
    assert "G1 Z-550 F0.25" in s2                        # Ø90,6 bis zur Teilungsstelle
    # Prüfer: Hauptzeit in der Größenordnung des Arbeitsplans (Längsdrehen + Plandrehen)
    kalk = A.kalkulieren(plan)
    th_plan = sum(g.th for g in kalk.gaenge if g.art in ("plandrehen", "laengsdrehen"))
    th_cam = cam.pruefen(d1.text, "drehen").zeit + cam.pruefen(d2.text, "drehen").zeit
    assert 0.3 * th_plan < th_cam < 3 * th_plan


def test_passfedernut():
    form, plan = _welle()
    nut = cam.erzeugen(form, plan)[-1]
    s = _saetze(nut.text)
    # Nut 20 × 90 (DIN 6885 für Ø75: t1 = 7,5), Enden bei z = 15 und 85; Fräser Ø20, eine Zustellung (≤ 0,5 D)
    n = S.drehzahl(140, 20, S.N_MAX_FRAESEN)
    vf = round(0.10 * 4 * n)
    assert "T1 M6" in s and f"G97 S{round(n)} M3" in s
    assert "G0 X15 Y0" in s and f"G1 Z-7.5 F{round(vf / 2)}" in s and f"G1 X85 F{vf}" in s
    assert "G17 G21 G40 G49 G80 G90 G94" in s
    pr = cam.pruefen(nut.text, "fraesen")
    assert pr.ok and abs(pr.weg_vorschub - (2 + 7.5 + 70)) < 1e-6      # Eintauchen ab Sicherheitsabstand


def test_flansch_bohrbild_und_ausdrehen():
    p = V.FlanschParameter()
    form = V.erzeuge_flansch(p)
    plan = A.vorschlag(form, p.werkstoff, "Turmfußflansch", "flansch")
    progs = cam.erzeugen(form, plan)
    assert [x.schluessel for x in progs] == ["drehen_1", "drehen_2", "bohren_1"]
    d1 = progs[0]
    # Ronde ist innen vorgebrannt → kein Bohrer, Bohrstange ab Ø380,4
    assert "T0404" not in d1.text and "T0505" in d1.text
    b = progs[-1]
    pr = cam.pruefen(b.text, "fraesen")
    assert pr.ok, pr.fehler
    bohr = [z for z in _saetze(b.text) if z.startswith("G0 X") and "Y" in z]
    lochkreis = {(round(float(z.split()[1][1:]), 1), round(float(z.split()[2][1:]), 1)) for z in bohr}
    assert len(lochkreis) == 16
    r = {round(math.hypot(x, y), 0) for x, y in lochkreis}
    assert len(r) == 1                                     # alle auf einem Lochkreis um die Drehachse
    # Durchgangsbohrung: Bohrtiefe = 30 + 0,3 · 26 + 1 Durchbruch
    assert any(z.startswith("G1 Z-38.8") for z in _saetze(b.text))
    assert "von -z" in b.titel                             # Bohrungen beginnen an der Unterseite (z = 0)


def test_zahnrad_nur_rohling_und_montageplatte():
    p = V.ZahnradParameter()
    form = V.erzeuge_zahnrad(p)
    plan = A.vorschlag(form, p.werkstoff, "Zahnrad", "zahnrad")
    progs = cam.erzeugen(form, plan)
    assert progs and progs[0].art == "drehen" and any("Verzahnung" in w for w in progs[0].warnungen)
    assert all(cam.pruefen(x.text, x.art).ok for x in progs)
    m = V.MontageplatteParameter()
    form = V.erzeuge_montageplatte(m)
    plan = A.vorschlag(form, "S235JR · warmgewalzt", "Vorrichtung", "montageplatte")
    progs = cam.erzeugen(form, plan)
    assert [x.schluessel for x in progs] == ["bohren_1"]
    assert any("nicht plattenförmig" in w for w in progs[0].warnungen)


def test_platte_aussenkontur():
    platte = G.abziehen(G.quader(0, 0, 0, 200, 120, 20), G.zylinder(18, 30, -5, 30, 30),
                        G.zylinder(18, 30, -5, 170, 30), G.zylinder(18, 30, -5, 170, 90))
    plan = A.vorschlag(platte, "S235JR · warmgewalzt", "Platte")
    assert [v["art"] for v in plan["vorgaenge"]][:3] == ["saegen", "fraesen", "bohren"]
    progs = cam.erzeugen(platte, plan)
    assert [x.schluessel for x in progs] == ["fraesen_kontur", "bohren_1"]
    k = progs[0]
    s = _saetze(k.text)
    # Fräser Ø20 außen um 200 × 120: Bahn mit Radius-Versatz, Tiefe 20,5 in 3 Zustellungen (≤ 10 mm)
    assert "G1 X-10 Y130" in s and "G1 X210 Y130" in s and "G1 X210 Y-10" in s
    assert sum(z.startswith("G1 Z-") for z in s) == 3 and any(z.startswith("G1 Z-20.5") for z in s)
    assert cam.pruefen(k.text, "fraesen").ok
    b = progs[1]
    bohr = {z for z in _saetze(b.text) if z.startswith("G0 X") and "Y" in z}
    assert {"G0 X30 Y30", "G0 X170 Y30", "G0 X170 Y90"} <= bohr


def test_dialekte_und_einstellungen():
    form, plan = _welle()
    din = cam.erzeugen(form, plan, {"dialekt": "din"})[0]
    fanuc = cam.erzeugen(form, plan, {"dialekt": "fanuc", "programmnummer": 2000})
    lcnc = cam.erzeugen(form, plan, {"dialekt": "linuxcnc", "kuehlung": False})[0]
    assert din.zeilen[2].startswith("N10 ")
    assert fanuc[0].zeilen[1].startswith("O2000") and fanuc[1].zeilen[1].startswith("O2001")
    assert "G99" in fanuc[0].text and "G95" not in fanuc[0].text
    assert not any(z.startswith(("N", "O")) for z in lcnc.zeilen) and " G7" in lcnc.text
    assert "M8" not in _saetze(lcnc.text)
    for p in (din, fanuc[0], lcnc):
        assert cam.pruefen(p.text, "drehen").ok
    feiner = cam.erzeugen(form, plan, {"schnitttiefe": 1.0})[0]
    assert len(feiner.zeilen) > len(din.zeilen)
    with pytest.raises(cam.CamFehler, match="Schnitttiefe"):
        cam.erzeugen(form, plan, {"schnitttiefe": 0})
    e = cam.Einstellungen.aus_dict({"aufmass": "0.5", "unbekannt": 1})
    assert e.aufmass == 0.5 and cam.Einstellungen.aus_dict(e.als_dict()) == e
    plan_gfk = {**plan, "rohteil": {**plan["rohteil"], "werkstoff": "GFK"}}
    with pytest.raises(cam.CamFehler, match="keine Schnittwerte"):
        cam.erzeugen(form, plan_gfk)


def test_pruefer_findet_fehler():
    p = cam.pruefen("G0 X0 Y0 Z5\nG1 Z-5\nM3\nG1 X10 F100\nG0 X20 Z-2\nG91\nQ7\n", "fraesen")
    text = " ".join(p.fehler)
    assert "ohne Vorschub F" in text and "ohne Drehzahl" in text and "Eilgang" in text
    assert "G91" in text and "„Q7“" not in text and "M30" in text
    ok = cam.pruefen("G0 X0 Y0 Z5\nS1000 M3\nG1 Z-5 F100\nG0 Z5\nG0 Z-4.5\nG1 Z-10\nG0 Z5\nM30\n", "fraesen")
    assert ok.ok, ok.fehler                                # Eilgang zurück in die eigene Bohrung ist erlaubt
    assert abs(ok.zeit - 10 / 100 - 5.5 / 100) < 1e-9
    dreh = cam.pruefen("G0 X50 Z2\nG95 G97 S500 M3\nG1 Z-100 F0.2\nG1 X-5\nM30\n", "drehen")
    assert abs(dreh.zeit - (102 / (0.2 * 500) + 27.5 / 100)) < 1e-9
    assert any("hinter der Drehmitte" in f for f in dreh.fehler)


def test_exportieren(tmp_path):
    form, plan = _welle()
    progs = cam.erzeugen(form, plan)
    pfade = cam.exportieren(progs, tmp_path / "nc", "T-001")
    assert [x.name for x in pfade] == ["T-001_drehen_1.nc", "T-001_drehen_2.nc", "T-001_fraesen_nut.nc"]
    assert pfade[0].read_text(encoding="ascii") == progs[0].text


def test_projekt_speichern_version_und_aenderung(tmp_path):
    projekt = Projekt.neu(tmp_path / "P", "Test", "")
    p = V.WelleParameter()
    t = projekt.teil_speichern("welle", "Hauptwelle", dataclasses.asdict(p))
    assert projekt.cam_von_teil(t["id"]) is None
    progs = projekt.cam_erzeugen(t["id"])                     # ohne gespeicherten Arbeitsplan: Vorschlag
    assert len(progs) == 3
    projekt.arbeitsplan_speichern(t["id"], projekt.arbeitsplan_vorschlag(t["id"]))
    nc = projekt.cam_speichern(t["id"], {"dialekt": "linuxcnc"})
    assert nc["nr"] == "NC-001" and nc["version"] == 1 and nc["daten"]["einstellungen"]["dialekt"] == "linuxcnc"
    assert [x["schluessel"] for x in nc["daten"]["programme"]] == ["drehen_1", "drehen_2", "fraesen_nut"]
    assert projekt.cam_speichern(t["id"])["version"] == 2
    # Bauteil ändern → Arbeitsplan und NC-Programm „neu prüfen“
    projekt.teil_speichern("welle", "Hauptwelle", {**t["parameter"], "l_ende": 120.0}, t["masse"], teil_id=t["id"])
    assert projekt.cam_von_teil(t["id"])["status"] == NEU_PRUEFEN
    assert any(b.typ == "ncprogramm" for b in projekt.neu_zu_pruefen())
    # wieder öffnen, Schema 14
    projekt.schliessen()
    p2 = Projekt.oeffnen(projekt.pfad)
    assert p2.meta("schema_version") == str(SCHEMA_VERSION) == "14"
    assert p2.cam_von_teil(t["id"])["version"] == 2
    p2.objekt_loeschen("teil", t["id"])
    assert p2.cam_von_teil(t["id"]) is None


def test_altes_projekt_bekommt_tabelle(tmp_path):
    projekt = Projekt.neu(tmp_path / "Alt", "Alt", "")
    projekt._db.execute("DROP TABLE ncprogramm")
    projekt._setze_meta("schema_version", "10")
    projekt._db.commit()
    projekt.schliessen()
    p = Projekt.oeffnen(projekt.pfad)
    assert p.meta("schema_version") == "14" and p._db.execute("SELECT COUNT(*) FROM ncprogramm").fetchone()[0] == 0
