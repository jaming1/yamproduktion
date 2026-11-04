"""MS9-Oberfläche: Arbeitspläne für Hauptwelle und Nabe der Gondel, Kosten der Baugruppe, Anfrageliste."""
import shutil
from pathlib import Path

from yamproduktion.fertigung import arbeitsplan as A
from yamproduktion.modell import NEU_PRUEFEN, Projekt
from yamproduktion.ui import thema

from test_oberflaeche import app, bild, fenster  # noqa: F401

BEISPIELE = Path(__file__).with_name("screenshots")


def test_fertigung_gondel(fenster, tmp_path, app):  # noqa: F811
    projekt = Projekt.neu(tmp_path / "KWA", "Kleinwindanlage KWA-5", "Mini-Windkraftanlage 5 kW", beispiel_kwa=True)
    fenster.projekt_laden(projekt)
    for schluessel in ("rotor", "lasten", "antrieb", "welle", "passfeder", "pressverband"):
        fenster.gehe_zu(schluessel)
        fenster.rechenseiten[schluessel].aus_anforderungen()
        assert fenster.rechenseiten[schluessel].protokoll_speichern(str(tmp_path / f"{schluessel}.pdf"))
    s = fenster.bauteile
    fenster.gehe_zu("bauteile")
    for vorlage, name in (("welle", "Hauptwelle"), ("nabe", "Rotornabe")):
        s.vorlage.setCurrentIndex(s.vorlage.findData(vorlage))
        s.aus_projekt()
        s.name.setText(name)
        s.teil_speichern()
    welle, nabe = projekt.teile()
    fenster.gehe_zu("baugruppen")
    g = fenster.baugruppen
    g.name.setText("Gondel – Triebstrang")
    g.teil_einbauen(welle["id"])
    g.teil_einbauen(nabe["id"])
    g.normteil_einbauen("22216 E", bezug={"abstand": "300"})
    g.normteil_einbauen("ISO 4017 M16x60", bezug={"abstand": "0", "umdrehen": True},
                        kreis={"anzahl": "12", "radius": f"{nabe['parameter']['d_lk'] / 2:g}"})
    gruppe = g.baugruppe_speichern()
    assert gruppe

    # ---- Arbeitsplan Hauptwelle: Vorschlag aus der Geometrie
    fenster.gehe_zu("arbeitsplaene")
    a = fenster.arbeitsplaene
    assert fenster.stapel.currentWidget() is a
    a.teil_laden(welle["id"])
    assert a.plan["rohteil"]["art"] == "Rundstahl" and a.tabelle.rowCount() == 5
    assert "Noch nicht gespeichert" in a.status.text()
    assert a.kalk.stueck > 0 and "Stückkosten" in a.kosten.text()
    a.tabelle.setCurrentCell(2, 2)                       # Längsdrehen: Rechenweg sichtbar
    assert "Rechenweg AG 30" in a.rechenweg.text() and "1/min" in a.rechenweg.text()
    bild(fenster, "63_arbeitsplan_welle_hell")
    vorher = a.kalk.stueck
    a.setze_rohteil("d", 100.0)                          # größeres Rohteil → teurer
    assert a.kalk.stueck > vorher and "Ø100" in a.roh_text.text()
    a.setze_rohteil("d", 95.0)
    a.tabelle.item(4, 6).setText("8")                    # Prüfzeit von Hand
    assert a.kalk.gaenge[4].te == 8.0 and a.kalk.gaenge[4].von_hand
    a.gang_neu("manuell", text="Härteprüfung", te=3.0)
    assert a.tabelle.rowCount() == 6
    a.losgroesse.setValue(2)
    ap = a.plan_speichern()
    assert ap["nr"] == "AP-001" and abs(ap["kosten"] - a.kalk.stueck) < 1e-9 and "✓" in a.teil_wahl.itemText(0)
    assert a.pdf(str(BEISPIELE / "Arbeitsplan_Hauptwelle_Beispiel.pdf")).stat().st_size > 3000

    # ---- Nabe: Guss, fremd gefertigt mit Angebot
    a.teil_laden(nabe["id"])
    assert a.plan["rohteil"]["art"] == "Guss"
    a.fertigung.setCurrentIndex(a.fertigung.findData("fremd"))
    a._setze_plan("fertigung", "fremd")
    assert a.kalk.fremd_geschaetzt and "Schätzung" in a.kosten.text()
    a.preis_fremd.setText("410")
    a.preis_fremd.editingFinished.emit()
    assert a.kalk.stueck == 410.0 and not a.kalk.fremd_geschaetzt
    a.plan_speichern()

    # ---- Kosten der Baugruppe
    fenster.gehe_zu("kosten")
    k = fenster.kosten
    assert k.baugruppe.currentData() == gruppe["id"]
    assert set(k.fehlend) == {"22216 E", "ISO 4017 M16x60"}           # Zukaufpreise fehlen noch
    k.zukaufpreis("22216 E", 95.0)
    k.zukaufpreis("ISO 4017 M16x60", 0.9)
    assert not k.fehlend
    soll = projekt.kalkulation_teil(welle["id"]).stueck + 410.0 + 95.0 + 12 * 0.9
    assert abs(k.summe - soll) < 1e-6 and "Herstellkosten" in k.summe_text.text()
    k.anzahl.setValue(3)
    assert abs(k.summe - 3 * soll) < 1e-6
    # eigener Stundensatz wirkt sofort
    zeile = next(i for i in range(k.stunden.rowCount()) if k.stunden.item(i, 0).text() == "Drehmaschine")
    k.stunden.item(zeile, 1).setText("100")
    assert projekt.kostensaetze()["stundensaetze"]["Drehmaschine"] == 100.0 and k.summe > 3 * soll
    assert k.anfragen.rowCount() == 1 and k.anfragen.item(0, 0).text() == nabe["nr"]
    k.absender.setText("Yamine")
    bild(fenster, "64_kosten_gondel_hell")
    assert k.kalkulation_pdf(str(BEISPIELE / "Kalkulation_Gondel_Beispiel.pdf")).stat().st_size > 3000
    assert k.anfrage_pdf(str(BEISPIELE / "Anfrage_Fremdfertigung_Beispiel.pdf")).stat().st_size > 2000

    # Doppelklick auf ein Bauteil öffnet seinen Arbeitsplan
    k._zeile_doppelklick(0, 0)
    assert fenster.stapel.currentWidget() is a and a.teil_id == welle["id"]

    # ---- Änderung an der Welle → Arbeitsplan „neu prüfen“, Hinweis auf der Seite
    projekt.teil_speichern("welle", "Hauptwelle", {**welle["parameter"], "l_ende": 120.0}, welle["masse"],
                           teil_id=welle["id"])
    assert projekt.arbeitsplan_von_teil(welle["id"])["status"] == NEU_PRUEFEN
    a.laden()
    a.teil_laden(welle["id"])
    assert "bitte prüfen" in a.status.text() and "⚠" in a.teil_wahl.currentText()

    fenster.thema_setzen("dunkel")
    a.tabelle.setCurrentCell(2, 2)
    bild(fenster, "65_arbeitsplan_dunkel")
    fenster.gehe_zu("kosten")
    bild(fenster, "66_kosten_dunkel")
    thema.anwenden(app, "hell")
    assert A.SCHAETZ_HINWEIS
    shutil.rmtree(tmp_path, ignore_errors=True)
