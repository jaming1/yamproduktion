"""MS13-Oberfläche: Zeitplan der Kleinwindanlage mit Aufgaben, Meilensteinen, Gantt, Fortschritt je Phase und
Kosten Plan/Ist."""
import shutil
from datetime import date, timedelta
from pathlib import Path

from yamproduktion.ui import thema
from yamproduktion.modell import Projekt

from test_oberflaeche import app, bild, fenster  # noqa: F401

BEISPIELE = Path(__file__).with_name("screenshots")


def test_projektmanagement(fenster, tmp_path, app):  # noqa: F811
    projekt = Projekt.neu(tmp_path / "KWA", "Kleinwindanlage KWA-5", "Mini-Windkraftanlage 5 kW", beispiel_kwa=True)
    fenster.projekt_laden(projekt)
    for schluessel in ("rotor", "welle"):
        fenster.gehe_zu(schluessel)
        fenster.rechenseiten[schluessel].aus_anforderungen()
        assert fenster.rechenseiten[schluessel].protokoll_speichern(str(tmp_path / f"{schluessel}.pdf"))
    s = fenster.bauteile
    fenster.gehe_zu("bauteile")
    s.vorlage.setCurrentIndex(s.vorlage.findData("welle"))
    s.aus_projekt()
    s.name.setText("Hauptwelle")
    s.teil_speichern()
    welle = projekt.teile()[0]
    fenster.gehe_zu("baugruppen")
    g = fenster.baugruppen
    g.name.setText("Gondel – Triebstrang")
    g.teil_einbauen(welle["id"])
    g.normteil_einbauen("22216 E", bezug={"abstand": "300"})
    assert g.baugruppe_speichern()
    fenster.gehe_zu("arbeitsplaene")
    fenster.arbeitsplaene.teil_laden(welle["id"])
    assert fenster.arbeitsplaene.plan_speichern()

    # ---- Aufgaben & Zeitplan (M48, M49, S17)
    fenster.gehe_zu("aufgaben")
    a = fenster.aufgaben
    start = date(2026, 11, 9)
    a.heute = start + timedelta(days=24)                      # Stichtag 03.12.2026
    assert fenster.stapel.currentWidget() is a and a.vorlage.isEnabled() and a.tabelle.rowCount() == 0
    neu = a.aus_vorlage(start.isoformat())
    assert len(neu) >= 15 and not a.vorlage.isEnabled() and a.tabelle.rowCount() == len(neu)
    assert a.aus_vorlage() == []                              # nicht doppelt
    # Stand ändern, Verantwortlich eintragen, mit Objekt verknüpfen
    idee = next(i for i, x in enumerate(a._sichtbar()) if x["phase"] == "P1")
    a.setze(idee, "stand", "erledigt")
    a.setze(idee, "verantwortlich", "Yamine")
    zeile = next(i for i, x in enumerate(a._sichtbar()) if x["titel"].startswith("Anforderungen"))
    a.setze(zeile, "stand", "in Arbeit")
    assert projekt.aufgaben("P1")[0]["stand"] == "erledigt" and a.balken["P1"].value() == 100
    assert "überfällig" in a.zusammenfassung.text()            # Anforderungen bis 22.11. – Stichtag 03.12.
    eigene = a.neu("Turmstatik beim Tragwerksplaner beauftragen", phase="P5", start="2026-12-01",
                   termin="2027-01-15", kosten_plan=1200.0)
    zeile = next(i for i, x in enumerate(a._sichtbar()) if x["id"] == eigene["id"])
    a.setze(zeile, "objekt", welle["nr"])
    a.setze(zeile, "kosten_ist", "1 350,00")
    e = projekt.aufgabe(eigene["id"])
    assert (e["objekt_typ"], e["objekt_id"], e["kosten_ist"]) == ("teil", welle["id"], 1350.0)
    a.setze(zeile, "start", "01.02.2027")                     # nach dem Termin → Meldung, unverändert
    assert projekt.aufgabe(eigene["id"])["start"] == "2026-12-01"
    a.tabelle.selectRow(zeile)
    a.zum_objekt()
    assert fenster.stapel.currentWidget() is fenster.bauteile
    fenster.gehe_zu("aufgaben")
    assert "Meilensteine: 0 von" in a.meilensteine.text() and "Lastenheft freigegeben" in a.meilensteine.text()
    a.tabelle.scrollToTop()
    bild(fenster, "83_aufgaben_hell")
    from PySide6.QtWidgets import QScrollArea
    a.findChild(QScrollArea).ensureWidgetVisible(a.gantt, 0, 0)
    bild(fenster, "88_gantt_hell")
    a.findChild(QScrollArea).verticalScrollBar().setValue(0)
    assert a.pdf(str(BEISPIELE / "Zeitplan_Beispiel.pdf")).stat().st_size > 5000
    a.filter.setCurrentIndex(a.filter.findData("P5"))
    assert all(x["phase"] == "P5" for x in a._sichtbar()) and a.tabelle.rowCount() == len(a._sichtbar())
    a.filter.setCurrentIndex(0)

    # ---- Übersicht zeigt Fortschritt je Phase, Phasentore P5–P9 mit Prüfungen
    fenster.gehe_zu("uebersicht")
    assert "noch nicht erledigt" in " ".join(projekt.phase_hindernisse("P5"))
    bild(fenster, "84_uebersicht_fortschritt_hell")

    # ---- Kosten Plan/Ist (S18)
    fenster.gehe_zu("budget")
    k = fenster.budget
    assert k.aus_kalkulation() >= 1
    assert any(p["kostenart"] == "Bauteile" and p["plan"] > 0 for p in k.posten)
    k.neu("Genehmigung & Gutachten", "Bauantrag und Gebühren", 800)
    k.setze(len(k.posten) - 1, "ist", "950")
    k.neu("Prüfung & Zertifizierung", "Elektrofachkraft: Anschluss und Prüfung", 600, 540)
    zeilen = {k.uebersicht.item(i, 0).text(): i for i in range(k.uebersicht.rowCount())}
    assert {"Bauteile", "Genehmigung & Gutachten", "Aufgaben", "Summe"} <= set(zeilen)
    assert k.uebersicht.item(zeilen["Genehmigung & Gutachten"], 3).text().startswith("+150")
    bild(fenster, "85_kosten_plan_ist_hell")
    assert k.pdf(str(BEISPIELE / "Kosten_Plan_Ist_Beispiel.pdf")).stat().st_size > 3000

    fenster.thema_setzen("dunkel")
    fenster.gehe_zu("aufgaben")
    bild(fenster, "86_aufgaben_dunkel")
    fenster.gehe_zu("budget")
    bild(fenster, "87_kosten_plan_ist_dunkel")
    thema.anwenden(app, "hell")
    shutil.rmtree(tmp_path, ignore_errors=True)
