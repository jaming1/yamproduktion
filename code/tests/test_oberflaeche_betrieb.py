"""MS11-Oberfläche: Inbetriebnahme der Kleinwindanlage mit Messung, Abnahme, Wartungsplan und Rückmeldung."""
import shutil
from datetime import date
from pathlib import Path

from yamproduktion.betrieb import inbetriebnahme as IB
from yamproduktion.modell import Projekt
from yamproduktion.ui import thema

from test_oberflaeche import app, bild, fenster  # noqa: F401

BEISPIELE = Path(__file__).with_name("screenshots")


def test_inbetriebnahme_und_wartung(fenster, tmp_path, app):  # noqa: F811
    projekt = Projekt.neu(tmp_path / "KWA", "Kleinwindanlage KWA-5", "Mini-Windkraftanlage 5 kW", beispiel_kwa=True)
    fenster.projekt_laden(projekt)
    for schluessel in ("rotor", "ertrag", "lasten", "antrieb", "welle", "lager", "bremse", "schrauben"):
        fenster.gehe_zu(schluessel)
        fenster.rechenseiten[schluessel].aus_anforderungen()
        assert fenster.rechenseiten[schluessel].protokoll_speichern(str(tmp_path / f"{schluessel}.pdf"))

    # ---- Inbetriebnahme
    fenster.gehe_zu("inbetriebnahme")
    s = fenster.inbetriebnahme
    assert fenster.stapel.currentWidget() is s and s.iid is None and "Noch keine" in s.status.text()
    ib = s.neu()
    assert ib["nr"] == "IB-001" and s.tabelle.rowCount() == len(ib["daten"]["punkte"]) >= 18
    s.f_pruefer.setText("Yamine")
    s.f_pruefer.editingFinished.emit()
    s.f_ort.setText("Werkstatt / Probestand")
    s.f_ort.editingFinished.emit()
    # Ist-Werte eintragen: Messwerte innerhalb der Grenzen, Sichtprüfungen i. O.
    for i, p in enumerate(s.daten["punkte"]):
        if p["text"].startswith("Leistungskurve"):
            continue
        if p["min"] is None and p["max"] is None:
            s.setze_ist(i, "i. O.")
        else:
            s.setze_ist(i, str(p["max"] if p["max"] is not None else p["min"]).replace(".", ","))
    for v, faktor in ((4, 1.1), (6, 0.95), (8, 1.02), (10, 0.97), (12, 1.0)):
        s.messpunkt_neu(v, round(IB.kurve_soll(s.daten["soll_kurve"], v) * faktor, 2))
    assert s.messung.rowCount() == 5 and s.messung.item(0, 4).text() == IB.IO
    assert "Abnahme möglich" in s.urteil.text()
    # ein Mangel: Lagertemperatur zu hoch
    zeile = next(i for i, p in enumerate(s.daten["punkte"]) if p["text"].startswith("Lagertemperatur"))
    s.setze_ist(zeile, "92")
    s.tabelle.item(zeile, 6).setText("Lager B läuft warm – Fettmenge prüfen")
    assert s.tabelle.item(zeile, 5).text() == IB.NIO and "1 nicht in Ordnung" in s.urteil.text()
    s.speichern_()
    s.tabelle.scrollToTop()
    bild(fenster, "71_inbetriebnahme_hell")
    neu = s.maengel_uebernehmen()
    assert len(neu) == 1 and "Lagertemperatur" in neu[0]["titel"] and s.daten["punkte"][zeile]["idee"] == neu[0]["nr"]
    assert s.maengel_uebernehmen() == []                                     # nicht doppelt
    s.erfahrung.setText("Bremse quietscht bei Frost")
    idee = s.erfahrung_uebernehmen()
    assert idee and idee["titel"] == "Bremse quietscht bei Frost"
    assert {i["titel"] for i in projekt.liste("idee")} >= {idee["titel"], neu[0]["titel"]}
    assert s.pdf("abnahme", str(BEISPIELE / "Abnahmeprotokoll_Beispiel.pdf")).stat().st_size > 5000
    assert s.pdf("messung", str(BEISPIELE / "Messprotokoll_Leistungskurve_Beispiel.pdf")).stat().st_size > 3000

    # ---- Wartung
    fenster.gehe_zu("wartung")
    w = fenster.wartung
    w.heute = date(2026, 12, 10)
    wp = w.neu()
    assert wp["nr"] == "WP-001" and w.tabelle.rowCount() >= 10
    w.start.setText("04.11.2026")
    w.start.editingFinished.emit()
    assert "1 fällig" in w.zusammenfassung.text() and "Schraubverbindungen" in w.zusammenfassung.text()
    w.erledigt(0)
    assert "Nichts fällig" in w.zusammenfassung.text() and w.tabelle.item(0, 6).text() == "10.12.2027"
    w.tabelle.item(3, 2).setText("3")                                         # Bremse öfter prüfen
    assert w.daten["punkte"][3]["intervall"] == 3
    neu_p = w.punkt_neu("Gondelverkleidung", "Befestigung und Risse prüfen", 12)
    assert neu_p["id"] == f"W{w.tabelle.rowCount()}"
    w.speichern_()
    bild(fenster, "72_wartung_hell")
    assert w.pdf(str(BEISPIELE / "Wartungsplan_Beispiel.pdf")).stat().st_size > 3000

    fenster.thema_setzen("dunkel")
    fenster.gehe_zu("inbetriebnahme")
    bild(fenster, "73_inbetriebnahme_dunkel")
    fenster.gehe_zu("wartung")
    bild(fenster, "74_wartung_dunkel")
    thema.anwenden(app, "hell")
    shutil.rmtree(tmp_path, ignore_errors=True)
