"""MS10-Oberfläche: Montageplan der Gondel mit Montageplatte, Explosionsdarstellung und Montageanleitung (PDF)."""
import shutil
from pathlib import Path

from yamproduktion.modell import NEU_PRUEFEN, Projekt
from yamproduktion.montage import montageplan as M
from yamproduktion.ui import thema

from test_oberflaeche import app, bild, fenster  # noqa: F401

BEISPIELE = Path(__file__).with_name("screenshots")


def test_montage_gondel(fenster, tmp_path, app):  # noqa: F811
    projekt = Projekt.neu(tmp_path / "KWA", "Kleinwindanlage KWA-5", "Mini-Windkraftanlage 5 kW", beispiel_kwa=True)
    fenster.projekt_laden(projekt)
    for schluessel in ("rotor", "lasten", "antrieb", "welle", "passfeder", "pressverband", "schrauben"):
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

    # ---- Vorschlag ohne Vorrichtung
    fenster.gehe_zu("montage")
    m = fenster.montage
    assert fenster.stapel.currentWidget() is m and m.gid == gruppe["id"]
    assert "Noch nicht gespeichert" in m.status.text() and m.liste.count() == 5
    assert m.liste.item(0).text().startswith("1. Grundteil Hauptwelle")
    assert "Prismen" in m.plan["schritte"][0]["text"]
    # ---- Montageplatte aus der Baugruppe: eigenes Bauteil, erster Schritt kommt dazu
    platte = m.montageplatte_erzeugen()
    assert platte and platte["vorlage"] == "montageplatte" and m.plan["vorrichtung"] == platte["id"]
    assert m.liste.count() == 6 and m.plan["schritte"][0]["titel"] == M.VORRICHTUNG_TITEL
    assert "Aufnahmepunkte" in m.aufnahme.text() and m.szene.vorrichtung is not None
    assert "Auflagen der Montageplatte" in m.plan["schritte"][1]["text"] and "Spanngurt" in m.plan["schritte"][1]["werkzeuge"]
    # Nabe: aufschrumpfen mit Temperatur aus dem Pressverband, im Bild farbig
    m.liste.setCurrentRow(3)
    assert "aufschrumpfen" in m.f_titel.text() and "°C" in m.f_text.toPlainText()
    assert (m.ansicht.gruppen == 1).any()
    bild(fenster, "67_montage_schritt_hell")
    # Schrauben: Anzugsmoment von Hand ändern
    m.liste.setCurrentRow(4)
    assert m.f_momente.rowCount() == 1 and "Steckschlüssel SW 24" in m.f_werkzeuge.toPlainText()
    m.setze_moment(0, 205.0)
    assert m.plan["schritte"][4]["momente"][0] == {"was": "12× ISO 4017 M16x60", "wert": 205.0,
                                                   "quelle": "von Hand eingetragen"}
    assert "M_A = 205 N·m" in m.f_text.toPlainText() and "210 N·m" not in m.plan["schritte"][4]["text"]
    assert any("10.9" in h for h in m.plan["hinweise"]) and "⚠" in m.meldungen.text()
    # Schritt einfügen, verschieben, löschen
    neu = m.schritt_neu("Lager abschmieren", text="Lager mit Fett füllen (Menge nach Hersteller).", zeit=5)
    assert m.liste.count() == 7 and m.plan["schritte"][5] is neu
    m.schritt_schieben(-1)
    assert m.plan["schritte"][4] is neu and m.liste.currentItem().text() == "5. Lager abschmieren"
    m.schritt_loeschen()
    assert m.liste.count() == 6
    mp = m.plan_speichern()
    assert mp["nr"] == "M-001" and "✓" in m.gruppe_wahl.currentText()
    assert mp["daten"]["schritte"][4]["momente"][0]["wert"] == 205.0
    # ---- Explosionsdarstellung
    m.nur_bis.setChecked(False)
    m.explosion.setValue(100)
    assert m.ansicht.netz.punkte[:, 2].min() < -300
    bild(fenster, "68_montage_explosion_hell")
    pfad = m.pdf(str(BEISPIELE / "Montageanleitung_Gondel_Beispiel.pdf"))
    assert pfad.stat().st_size > 60000
    # ---- Änderung an der Welle → Montageplan „neu prüfen“ (über die Baugruppe)
    projekt.teil_speichern("welle", "Hauptwelle", {**welle["parameter"], "l_ende": 120.0}, welle["masse"],
                           teil_id=welle["id"])
    assert projekt.montageplan_von_baugruppe(gruppe["id"])["status"] == NEU_PRUEFEN
    m.laden()
    assert "bitte prüfen" in m.status.text() and "⚠" in m.gruppe_wahl.currentText()
    # Sprung aus der Rückverfolgung
    fenster.gehe_zu("uebersicht")
    fenster.gehe_zu_objekt("montageplan", mp["id"])
    assert fenster.stapel.currentWidget() is m

    fenster.thema_setzen("dunkel")
    m.explosion.setValue(0)
    m.nur_bis.setChecked(True)
    m.liste.setCurrentRow(3)
    bild(fenster, "69_montage_schritt_dunkel")
    m.nur_bis.setChecked(False)
    m.explosion.setValue(100)
    bild(fenster, "70_montage_explosion_dunkel")
    thema.anwenden(app, "hell")
    shutil.rmtree(tmp_path, ignore_errors=True)
