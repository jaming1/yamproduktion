"""K5-Oberfläche: NC-Programme (G-Code) für Hauptwelle und Turmfußflansch – Vorschau, Prüfung, Speichern, Export."""
import shutil

from PySide6.QtWidgets import QScrollArea

from yamproduktion.fertigung import cam
from yamproduktion.modell import NEU_PRUEFEN, Projekt
from yamproduktion.ui import thema

from test_oberflaeche import app, bild, fenster  # noqa: F401


def test_cam_seite(fenster, tmp_path, app):  # noqa: F811
    projekt = Projekt.neu(tmp_path / "KWA", "Kleinwindanlage KWA-5", "Mini-Windkraftanlage 5 kW", beispiel_kwa=True)
    fenster.projekt_laden(projekt)

    # ---- ohne Bauteile: freundlicher Hinweis, nichts zum Speichern
    fenster.gehe_zu("cam")
    c = fenster.cam
    assert fenster.stapel.currentWidget() is c
    assert "Zuerst ein Bauteil anlegen" in c.leer_text.text() and not c.speichern.isEnabled()
    assert c.hinweis.text() == cam.HINWEIS

    # ---- Bauteile mit Standardmaßen und gespeicherte Arbeitspläne
    s = fenster.bauteile
    fenster.gehe_zu("bauteile")
    for vorlage, name in (("welle", "Hauptwelle"), ("flansch", "Turmfußflansch")):
        s.vorlage.setCurrentIndex(s.vorlage.findData(vorlage))
        s.name.setText(name)
        assert s.teil_speichern()
    welle, flansch = projekt.teile()
    fenster.gehe_zu("arbeitsplaene")
    a = fenster.arbeitsplaene
    for t in (welle, flansch):
        a.teil_laden(t["id"])
        assert a.plan_speichern()

    # ---- Hauptwelle: zwei Aufspannungen Drehen + Passfedernut fräsen
    fenster.gehe_zu("cam")
    c.teil_laden(welle["id"])
    assert not c.fehler_text, c.fehler_text
    arten = [p.art for p in c.programme]
    assert len(c.programme) >= 2 and arten.count("drehen") >= 1 and "fraesen" in arten
    assert c.liste.count() == len(c.programme) and c.liste.currentRow() == 0
    text = c.code.toPlainText()
    assert "G0" in text and "G1" in text and "M30" in text
    assert all(pr.ok for pr in c.pruefungen.values()), {k: p.fehler for k, p in c.pruefungen.items()}
    assert "Keine Fehler gefunden" in c.pruef_ergebnis.text() and "Hauptzeit" in c.pruef_text.text()
    assert "Arbeitsplan t_h" in c.pruef_text.text()
    assert c.vorschau.segmente and c.vorschau.achsen() == ("Z", "X/2")
    assert "Noch nicht gespeichert" in c.status.text()
    bild(fenster, "130_cam_welle_hell")

    c.liste.setCurrentRow(arten.index("fraesen"))
    assert c.vorschau.achsen() == ("X", "Y") and c.code.toPlainText() == c.programme[arten.index("fraesen")].text
    bild(fenster, "131_cam_fraesen_hell")
    c.liste.setCurrentRow(0)

    # ---- Einstellungen erzeugen die Programme neu
    din = c.code.toPlainText()
    assert c.dialekt.count() == len(cam.DIALEKTE) and c.dialekt.currentData() == "din"
    c.setze_einstellung("dialekt", "fanuc")
    assert any(z.startswith("O") for z in c.code.toPlainText().splitlines())     # Fanuc: O-Nummer im Kopf
    c.setze_einstellung("dialekt", "linuxcnc")
    assert c.dialekt.currentData() == "linuxcnc"
    linux = c.code.toPlainText()
    assert linux != din and not any(z.startswith("O") for z in linux.splitlines())
    c.setze_einstellung("schnitttiefe", 2.0)
    assert c.mass_felder["schnitttiefe"].value() == 2.0 and c.einst.schnitttiefe == 2.0
    c.mass_felder["aufmass"].setValue(0.5)                # Bedienung über das Feld wirkt genauso
    assert c.einst.aufmass == 0.5
    c.kuehlung.setChecked(False)
    assert not c.einst.kuehlung

    # ---- Speichern → NC-001, Einstellungen bleiben erhalten
    nc = c.programme_speichern()
    assert nc["nr"] == "NC-001" and "NC-001" in c.status.text() and "✓" in c.teil_wahl.currentText()
    c.setze_projekt(projekt)
    c.teil_laden(welle["id"])
    assert c.einst.dialekt == "linuxcnc" and c.einst.schnitttiefe == 2.0 and not c.einst.kuehlung
    assert c.dialekt.currentData() == "linuxcnc"
    nc2 = c.programme_speichern()
    assert nc2["nr"] == "NC-001" and nc2["version"] == 2 and "Version 2" in c.status.text()

    # ---- Export in einen Ordner
    pfade = c.exportieren(str(tmp_path / "nc"))
    assert len(pfade) == len(c.programme)
    assert all(p.exists() and p.suffix == ".nc" and p.stat().st_size > 50 for p in pfade)

    # ---- Flansch: Bohrbild
    c.teil_laden(flansch["id"])
    assert not c.fehler_text, c.fehler_text
    assert any("bohr" in p.schluessel for p in c.programme)
    i = next(i for i, p in enumerate(c.programme) if "bohr" in p.schluessel)
    c.liste.setCurrentRow(i)
    assert "G0" in c.code.toPlainText()
    assert c.vorschau._hat_punkte()                         # Bohrungen als Punkte in der Vorschau
    bild(fenster, "132_cam_flansch_hell")
    leiste = c.findChild(QScrollArea).verticalScrollBar()
    leiste.setValue(leiste.maximum())                       # Prüfkarte und Hinweis unten
    bild(fenster, "135_cam_pruefung_hell")
    leiste.setValue(0)

    # ---- Bauteil ändern → NC-Programm „neu prüfen“
    projekt.teil_speichern("welle", "Hauptwelle", {**welle["parameter"], "l_ende": 120.0}, welle["masse"],
                           teil_id=welle["id"])
    assert projekt.cam_von_teil(welle["id"])["status"] == NEU_PRUEFEN
    fenster.gehe_zu("uebersicht")
    fenster.gehe_zu("cam")
    c.teil_laden(welle["id"])
    assert NEU_PRUEFEN in c.status.text() and "⚠" in c.teil_wahl.currentText()

    fenster.thema_setzen("dunkel")
    bild(fenster, "133_cam_welle_dunkel")
    c.teil_laden(flansch["id"])
    c.liste.setCurrentRow(next(i for i, p in enumerate(c.programme) if "bohr" in p.schluessel))
    bild(fenster, "134_cam_flansch_dunkel")
    thema.anwenden(app, "hell")
    shutil.rmtree(tmp_path, ignore_errors=True)
