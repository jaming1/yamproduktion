"""MS7-Oberfläche: Lagerdeckel frei modelliert – Skizze mit Bemaßung, Extrusion, Lochkreis, Fase,
Durchmesser aus der Wellenberechnung; Widerspruch in der Skizze; Änderungskette; STEP-Import."""
import math
from pathlib import Path

from yamproduktion.cad import geometrie as G
from yamproduktion.modell import NEU_PRUEFEN, Projekt
from yamproduktion.ui import thema

from test_oberflaeche import app, bild, fenster  # noqa: F401

BEISPIEL_STEP = Path(__file__).parents[2] / "daten" / "beispiele" / "T-001_Hauptwelle_KWA-5.step"


def test_lagerdeckel_frei_modelliert(fenster, tmp_path, app):  # noqa: F811
    projekt = Projekt.neu(tmp_path / "KWA", "Kleinwindanlage KWA-5", "Mini-Windkraftanlage 5 kW", beispiel_kwa=True)
    fenster.projekt_laden(projekt)
    for schluessel in ("rotor", "lasten", "antrieb", "welle"):
        fenster.gehe_zu(schluessel)
        s = fenster.rechenseiten[schluessel]
        s.aus_anforderungen()
        assert s.protokoll_speichern(str(tmp_path / f"{schluessel}.pdf"))
    welle = next(b for b in projekt.berechnungen() if b.typ == "welle")
    d_welle = welle.eingaben["d_mm"]

    fenster.gehe_zu("modellieren")
    m = fenster.modellieren
    assert fenster.stapel.currentWidget() is m
    m.name.setText("Lagerdeckel")
    m.parameter_neu("d", 'ber("welle", "d")', "Wellendurchmesser aus der Berechnung")
    m.parameter_neu("D", "d + 80", "Außendurchmesser")
    m.parameter_neu("t", "12", "Dicke")
    m.parameter_neu("d_LK", "(d + D) / 2 + 5", "Lochkreis")
    m.parameter_neu("n", "6", "Schrauben")
    werte = m.ergebnis.werte
    assert werte["d"] == d_welle and werte["D"] == d_welle + 80

    # Skizze: Außenkreis und Wellendurchgang, beide auf dem Ursprung, bemaßt mit Formeln
    m.feature_neu("skizze")
    assert m.stapel.currentWidget() is m.editor
    f = m.editor.flaeche
    f.setze_werkzeug("kreis")
    f.klick(0, 0)
    f.klick(60, 0)
    f.klick(0, 0)
    f.klick(30, 0)
    aussen, innen = [e["id"] for e in f.sk["elemente"]]
    f.setze_werkzeug("auswahl")
    f.klick(0, 60)
    assert f.auswahl == [aussen]
    assert f.bedingen("durchmesser", "D")
    f.klick(0, 30)
    assert f.bedingen("durchmesser", "d + 2")
    f.alles_zeigen()
    assert abs(f.sk["elemente"][0]["r"] - (d_welle + 80) / 2) < 1e-6
    assert f.status == "✓ Vollständig bestimmt"
    bild(fenster, "51_skizze_lagerdeckel_hell")
    m.skizze_fertig()
    assert m.stapel.currentIndex() == 0

    m.feature_neu("extrusion", hoehe="t")
    m.feature_neu("bohrung", versatz="t", x="d_LK / 2", y="0", d="9", tiefe="durch")
    m.feature_neu("muster", feature="Bohrung1", muster="kreis", anzahl="n")
    m.feature_neu("fase", groesse="1", kanten="oben")
    r = m.ergebnis
    assert r.ok, r.fehler
    flaeche = math.pi / 4 * ((d_welle + 80) ** 2 - (d_welle + 2) ** 2 - 6 * 9 ** 2)
    assert abs(G.eigenschaften(r.form).volumen / (flaeche * 12) - 1) < 0.01      # Fase knapp darunter
    assert "B-" in m.bezuege.text()
    m.ansicht.ansicht("Iso")
    bild(fenster, "52_lagerdeckel_hell")

    # Fehler im Baum: zu große Fase – Meldung, Teil davor bleibt sichtbar, Speichern gesperrt
    m.baum.setCurrentRow(4)
    m.setze_eigenschaft("groesse", "20")
    assert not m.ergebnis.ok and "Fase1" in m.fehler.text() and m.ergebnis.form is not None
    assert not m.speichern.isEnabled()
    bild(fenster, "53_feature_fehler_hell")
    m.setze_eigenschaft("groesse", "1")
    assert m.ergebnis.ok

    # Parameter ändern: 8 Schrauben
    m.setze_parameter("n", "8")
    assert m.ergebnis.ok
    t = m.teil_speichern()
    assert t and t["vorlage"] == "frei" and t["masse"] > 0
    assert [q.nr for q in projekt.haengt_ab_von("teil", t["id"])] == [welle.nr]
    assert m.exportieren(str(tmp_path / "Lagerdeckel.step")).stat().st_size > 1000

    # Widerspruch in einer Skizze wird abgewiesen, die Skizze bleibt lösbar
    m.neu()
    m.name.setText("Lasche")
    m.feature_neu("skizze")
    f = m.editor.flaeche
    f.setze_werkzeug("rechteck")
    f.klick(0, 0)
    f.klick(80, 30)
    unten, rechts, oben, links = [e["id"] for e in f.sk["elemente"]]
    f.setze_werkzeug("auswahl")
    f.klick(40, 0)
    assert f.bedingen("laenge", "100")
    f.klick(100, 15)                               # rechte Kante liegt jetzt bei x = 100
    assert f.bedingen("laenge", "40")
    f.klick(50, 40)
    assert not f.bedingen("laenge", "90")           # Gegenseite anders lang → Widerspruch
    assert len(f.sk["bedingungen"]) == 7 and not f.status.startswith("⚠")    # 4 × H/V, Ecke im Ursprung, 2 Längen
    f.setze_werkzeug("kreis")
    f.klick(20, 20)
    f.klick(25, 20)
    f.setze_werkzeug("auswahl")
    f.klick(25, 20)
    f.bedingen("durchmesser", "10")
    f.alles_zeigen()
    bild(fenster, "54_skizze_lasche_hell")
    m.skizze_fertig()
    m.feature_neu("extrusion", hoehe="8")
    m.feature_neu("verrundung", groesse="4", kanten="alle")
    assert "nicht anbringen" in m.ergebnis.fehler        # 2 × R4 an 8 mm Dicke stoßen zusammen
    m.setze_eigenschaft("kanten", "senkrecht")
    m.setze_eigenschaft("groesse", "10")
    assert m.ergebnis.ok, m.ergebnis.fehler
    v = G.eigenschaften(m.ergebnis.form).volumen
    assert abs(v - 8 * (100 * 40 - (4 - math.pi) * 100 - math.pi * 25)) < 1e-6 * v

    # STEP-Import: Hauptwelle aus MS6 als Feature
    if BEISPIEL_STEP.exists():
        m.neu()
        f_imp = m.step_importieren(str(BEISPIEL_STEP))
        assert f_imp and m.ergebnis.ok
        bild(fenster, "55_step_import_hell")

    # Änderung 5 → 10 kW: Wellendurchmesser wächst, der Lagerdeckel wird „neu prüfen“ und folgt
    projekt.anforderung_aendern(projekt.anforderung_suchen("nennleistung").id, zielwert=10)
    assert projekt.teil(t["id"])["status"] == NEU_PRUEFEN
    fenster.gehe_zu("berechnungen")
    fenster.berechnungen.alle_neu_rechnen()
    fenster.gehe_zu("bauteile")
    zeile = next(z for z in range(fenster.bauteile.tabelle.rowCount())
                 if fenster.bauteile.tabelle.item(z, 0).text() == t["nr"])
    assert fenster.bauteile.tabelle.item(zeile, 2).text() == "Frei modelliert"
    fenster.bauteile.neu_erzeugen(t["id"])
    neu = projekt.teil(t["id"])
    assert neu["version"] == 2 and neu["status"] != NEU_PRUEFEN
    d_neu = next(b for b in projekt.berechnungen() if b.typ == "welle").eingaben["d_mm"]
    # Öffnen aus der Bauteilliste springt zur Seite „Modellieren“
    fenster.gehe_zu_objekt("teil", t["id"])
    assert fenster.stapel.currentWidget() is m and m.teil_id == t["id"]
    assert m.ergebnis.werte["d"] == d_neu

    fenster.thema_setzen("dunkel")
    m.ansicht.update()
    bild(fenster, "56_lagerdeckel_dunkel")
    m.baum.setCurrentRow(0)
    m.skizze_bearbeiten()
    m.editor.flaeche.alles_zeigen()
    bild(fenster, "57_skizze_dunkel")
    m.skizze_fertig()
    thema.anwenden(app, "hell")
