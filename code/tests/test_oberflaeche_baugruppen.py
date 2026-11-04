"""MS8-Oberfläche: Gondel-Baugruppe der KWA (Hauptwelle, Nabe, Lager, Blattschrauben), Stückliste,
Zeichnungen von Teil und Baugruppe, Export PDF/DXF/CSV, Änderungskette Teil → Baugruppe."""
import math
import shutil
from pathlib import Path

from yamproduktion.cad import geometrie as G, normteile as N
from yamproduktion.modell import NEU_PRUEFEN, Projekt
from yamproduktion.ui import thema

from test_oberflaeche import app, bild, fenster  # noqa: F401

BEISPIELE = Path(__file__).with_name("screenshots")


def _lager_fuer(d: float) -> str:
    passend = [n for n, (di, _, _, art) in N.LAGER.items() if abs(di - d) < 1e-6]
    passend.sort(key=lambda n: N.LAGER[n][3] != "Pendelrollenlager")
    return passend[0] if passend else min(N.LAGER, key=lambda n: abs(N.LAGER[n][0] - d))


def test_gondel_baugruppe(fenster, tmp_path, app):  # noqa: F811
    projekt = Projekt.neu(tmp_path / "KWA", "Kleinwindanlage KWA-5", "Mini-Windkraftanlage 5 kW", beispiel_kwa=True)
    fenster.projekt_laden(projekt)
    for schluessel in ("rotor", "lasten", "antrieb", "welle", "passfeder", "pressverband"):
        fenster.gehe_zu(schluessel)
        s = fenster.rechenseiten[schluessel]
        s.aus_anforderungen()
        assert s.protokoll_speichern(str(tmp_path / f"{schluessel}.pdf"))
    fenster.gehe_zu("bauteile")
    s = fenster.bauteile
    s.vorlage.setCurrentIndex(s.vorlage.findData("welle"))
    s.aus_projekt()
    s.name.setText("Hauptwelle")
    welle = s.teil_speichern()
    s.vorlage.setCurrentIndex(s.vorlage.findData("nabe"))
    s.aus_projekt()
    s.name.setText("Rotornabe")
    nabe = s.teil_speichern()
    w, n = welle["parameter"], nabe["parameter"]
    lager = _lager_fuer(w["d_lager"])
    b = N.LAGER[lager][2]

    # ---- Baugruppe zusammenbauen
    fenster.gehe_zu("baugruppen")
    g = fenster.baugruppen
    assert fenster.stapel.currentWidget() is g
    g.name.setText("Gondel – Triebstrang")
    g.teil_einbauen(welle["id"])
    e_nabe = g.teil_einbauen(nabe["id"])
    assert e_nabe["bezug"]["ziel"] == "E1"                       # neue Teile zuerst koaxial zum ersten
    z_b = w["l_nabe"] / 2 + w["a_mm"]
    g.normteil_einbauen(lager, name="Loslager B", bezug={"abstand": f"{z_b - b / 2:g}"})
    g.normteil_einbauen(lager, name="Festlager A", bezug={"abstand": f"{z_b + w['l_mm'] - b / 2:g}"})
    schraube = "ISO 4017 M16x60"
    g.normteil_einbauen(schraube, name="Blattschraube", bezug={"abstand": "0", "umdrehen": True},
                        kreis={"anzahl": f"{n['n_loecher']:g}", "radius": f"{n['d_lk'] / 2:g}"})
    g.normteil_einbauen("ISO 4032 M16", name="Mutter", bezug={"abstand": f"{n['dicke_scheibe']:g}"},
                        kreis={"anzahl": f"{n['n_loecher']:g}", "radius": f"{n['d_lk'] / 2:g}"})
    r = g.ergebnis
    assert r.ok, r.fehler
    anzahl = int(round(n["n_loecher"]))
    assert len(r.exemplare) == 4 + 2 * anzahl
    menge = {p.sachnummer: p.menge for p in r.stueckliste}
    assert menge == {welle["nr"]: 1, nabe["nr"]: 1, lager: 2, schraube: anzahl, "ISO 4032 M16": anzahl}
    assert g.tabelle.rowCount() == 5 and "Tabellenbuch" in g.hinweis.text()
    soll = welle["masse"] + nabe["masse"] + 2 * N.erzeugen(lager).masse + anzahl * (
        N.erzeugen(schraube).masse + N.erzeugen("ISO 4032 M16").masse)
    assert abs(r.masse - soll) < 1e-9
    massen = [welle["masse"], nabe["masse"]] + [N.erzeugen(lager).masse] * 2 + \
        [N.erzeugen(schraube).masse] * anzahl + [N.erzeugen("ISO 4032 M16").masse] * anzahl
    for i in range(3):     # Schwerpunkt = massengewichtetes Mittel der Einzelschwerpunkte (Nuten: knapp neben der Achse)
        soll_i = sum(m * G.eigenschaften(x.form).schwerpunkt[i] for m, x in zip(massen, r.exemplare)) / soll
        assert abs(r.schwerpunkt[i] - soll_i) < 1e-6
    assert abs(r.schwerpunkt[0]) < 0.5 and abs(r.schwerpunkt[1]) < 0.5 and r.schwerpunkt[2] > 0
    # Lager sitzt auf dem Lagersitz: Bohrung = Wellendurchmesser, Mitte bei z_B
    e_l = G.eigenschaften(r.exemplare[2].form)
    assert abs((e_l.minimum[2] + e_l.maximum[2]) / 2 - z_b) < 1e-6
    # Schrauben auf dem Lochkreis der Nabe, Kopf vorn (z < 0)
    sp = G.eigenschaften(r.exemplare[4].form)
    assert abs(math.hypot((sp.minimum[0] + sp.maximum[0]) / 2, (sp.minimum[1] + sp.maximum[1]) / 2) - n["d_lk"] / 2) < 1e-6
    assert sp.minimum[2] < 0
    g.liste.setCurrentRow(4)
    g.ansicht.ansicht("Iso")
    bild(fenster, "58_baugruppe_gondel_hell")

    # Lage über die Eigenschaften ändern: Formel, Fehler, zurück
    g.setze("bezug", "abstand", "a_unbekannt")
    assert not g.ergebnis.ok and "E5" in g.ergebnis.meldungen and not g.speichern.isEnabled()
    g.setze("bezug", "abstand", "0")
    assert g.ergebnis.ok

    gespeichert = g.baugruppe_speichern()
    assert gespeichert["nr"] == "G-001" and abs(gespeichert["masse"] - soll) < 1e-9
    assert {x.nr for x in projekt.haengt_ab_von("baugruppe", gespeichert["id"])} == {welle["nr"], nabe["nr"]}
    csv = g.stueckliste_exportieren(str(tmp_path / "Gondel.csv"), "csv")
    assert csv.read_text(encoding="utf-8-sig").count("\n") == 6
    pdf = g.stueckliste_exportieren(str(tmp_path / "Gondel_Stueckliste.pdf"), "pdf")
    assert pdf.stat().st_size > 2000
    shutil.copy(pdf, BEISPIELE / "Gondel_Stueckliste_Beispiel.pdf")
    assert g.step_exportieren(str(tmp_path / "Gondel.step")).stat().st_size > 10000

    # ---- Zeichnung der Baugruppe mit Stückliste und Positionsnummern
    g.zeichnung_knopf.click()
    z = fenster.zeichnungen
    assert fenster.stapel.currentWidget() is z and z.zeichnung is not None
    texte = [e.text for e in z.zeichnung.elemente if hasattr(e, "text") and isinstance(e.text, str)]
    assert "G-001" in texte and {"1", "2", "3", "4", "5"} <= set(texte) and "Menge" in texte
    bild(fenster, "59_zeichnung_gondel_hell")
    assert z.exportieren(str(BEISPIELE / "Gondel_Zeichnung_Beispiel.pdf"), "pdf").stat().st_size > 5000
    assert z.exportieren(str(tmp_path / "Gondel.dxf"), "dxf").stat().st_size > 5000

    # ---- Werkstattzeichnung der Hauptwelle mit Passmaßen
    z.wahl.setCurrentIndex(z.wahl.findData(f"teil:{welle['id']}"))
    z._gewaehlt()
    z.toleranzen.setText(f"Ø{w['d_lager']:g} k6")
    z.ersteller.setText("Yamine")
    z.erstellen()
    texte = [e.text for e in z.zeichnung.elemente if hasattr(e, "text") and isinstance(e.text, str)]
    assert f"Ø{w['d_lager']:g} k6" in texte and "Yamine" in texte and welle["nr"] in texte
    bild(fenster, "60_zeichnung_welle_hell")
    assert z.exportieren(str(BEISPIELE / "Hauptwelle_Zeichnung_Beispiel.pdf"), "pdf").stat().st_size > 5000
    assert z.exportieren(str(BEISPIELE / "Hauptwelle_Zeichnung_Beispiel.dxf"), "dxf").stat().st_size > 5000

    # ---- Änderung an der Welle → Baugruppe „neu prüfen“
    projekt.teil_speichern("welle", "Hauptwelle", {**w, "l_ende": w["l_ende"] + 20}, welle["masse"],
                           teil_id=welle["id"])
    assert projekt.baugruppe(gespeichert["id"])["status"] == NEU_PRUEFEN
    fenster.gehe_zu_objekt("baugruppe", gespeichert["id"])
    assert fenster.stapel.currentWidget() is g and g.baugruppe_id == gespeichert["id"]
    assert "⚠" in g.auswahl.currentText()
    assert g.baugruppe_speichern()["version"] == 2

    fenster.thema_setzen("dunkel")
    g.ansicht.update()
    bild(fenster, "61_baugruppe_dunkel")
    fenster.zeichnung_oeffnen("baugruppe", gespeichert["id"])
    bild(fenster, "62_zeichnung_dunkel")
    thema.anwenden(app, "hell")
