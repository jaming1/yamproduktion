"""MS12-Oberfläche: Prüfplan aus der Zeichnung, FMEA, Abweichungen, Risikobeurteilung, Normen und das
PDF-Paket der technischen Dokumentation für die Kleinwindanlage."""
import shutil
from pathlib import Path

from pypdf import PdfReader

from yamproduktion.betrieb import inbetriebnahme as IB
from yamproduktion.modell import Projekt
from yamproduktion.qualitaet import tabellen as Q
from yamproduktion.ui import thema

from test_oberflaeche import app, bild, fenster  # noqa: F401

BEISPIELE = Path(__file__).with_name("screenshots")


def test_qualitaet_und_doku(fenster, tmp_path, app):  # noqa: F811
    projekt = Projekt.neu(tmp_path / "KWA", "Kleinwindanlage KWA-5", "Mini-Windkraftanlage 5 kW", beispiel_kwa=True)
    fenster.projekt_laden(projekt)
    for schluessel in ("rotor", "lasten", "welle", "lager", "schrauben", "pressverband", "bremse", "turm"):
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
    g.normteil_einbauen("ISO 4017 M16x60", bezug={"abstand": "0", "umdrehen": True},
                        kreis={"anzahl": "12", "radius": f"{nabe['parameter']['d_lk'] / 2:g}"})
    assert g.baugruppe_speichern()
    fenster.gehe_zu("montage")
    assert fenster.montage.plan_speichern()

    # ---- Passmaß auf der Zeichnung wird je Bauteil gemerkt
    d = welle["parameter"]["d_lager"]
    fenster.zeichnung_oeffnen("teil", welle["id"])
    z = fenster.zeichnungen
    z.toleranzen.setText(f"Ø{d:g} k6")
    z.erstellen()
    assert projekt.passmasse("teil", welle["id"]) == f"Ø{d:g} k6"
    z.oeffnen("teil", nabe["id"])
    z.oeffnen("teil", welle["id"])
    assert z.toleranzen.text() == f"Ø{d:g} k6"

    # ---- Prüfplan (M43, S15)
    fenster.gehe_zu("pruefplaene")
    pp = fenster.pruefplaene
    assert fenster.stapel.currentWidget() is pp and pp.teil_id == welle["id"] and "Noch kein Prüfplan" in pp.status.text()
    plan = pp.aus_zeichnung()
    assert plan and pp.tabelle.rowCount() == len(plan["daten"]["merkmale"]) >= 6
    assert pp.tabelle.item(0, 1).text() == f"Ø{d:g} k6" and pp.tabelle.item(0, 4).text() == "Grenzrachenlehre k6"
    pp.felder["pruefer"].setText("Yamine")
    pp.felder["pruefer"].editingFinished.emit()
    pp.felder["los"].setText("Erststück")
    pp.felder["los"].editingFinished.emit()
    for i, m in enumerate(pp.daten["merkmale"]):
        pp.setze_ist(i, f"{(m['min'] + m['max']) / 2:.3f}".replace(".", ","))
    pp.setze_ist(0, f"{d + 0.025:.3f}".replace(".", ","))              # Lagersitz zu groß
    assert pp.tabelle.item(0, 7).text() == IB.NIO and "n. i. O." in pp.zusammenfassung.text()
    pp.tabelle.item(0, 8).setText("Schlichtzugabe zu groß – nachschleifen")
    pp.merkmal_neu("Rundlauf Lagersitz ≤ 0,02")
    pp.setze_ist(pp.tabelle.rowCount() - 1, "i. O.")
    assert pp.daten["merkmale"][-1]["ergebnis"] == IB.IO
    assert pp.speichern_()
    assert pp.wahl.currentText().endswith("✓")
    bild(fenster, "75_pruefplan_hell")
    assert pp.pdf(str(BEISPIELE / "Pruefprotokoll_Beispiel.pdf")).stat().st_size > 3000

    # ---- FMEA (M44)
    fenster.gehe_zu("fmea")
    f = fenster.qseiten["fmea"]
    assert "Noch nichts" in f.status.text()
    fm = f.neu("Konstruktions-FMEA")
    assert fm["nr"] == "FM-001" and f.tabelle.rowCount() >= 7
    zeile = next(i for i, z_ in enumerate(f.daten["zeilen"]) if z_["element"] == "Hauptwelle")
    f.setze(zeile, "massnahme", "Kerbradius am Absatz vergrößern, Rissprüfung bei Wartung")
    f.setze(zeile, "E2", "5")
    f.setze(zeile, "B2", "10")
    f.setze(zeile, "A2", "2")
    assert f.daten["zeilen"][zeile]["E2"] == "5" and "RPZ 100" in f.tabelle.item(zeile, 18).text()
    f.speichern_()
    bild(fenster, "76_fmea_hell")
    assert f.pdf(str(BEISPIELE / "FMEA_Beispiel.pdf")).stat().st_size > 3000
    f.neu("Prozess-FMEA")
    assert f.wahl.count() == 2

    # ---- Abweichungen (M45)
    fenster.gehe_zu("abweichung")
    a = fenster.qseiten["abweichung"]
    a.neu()
    assert a.uebernehmen() == 1 and a.uebernehmen() == 0
    a.setze(0, "ursache", "Schleifscheibe nicht nachgerichtet")
    a.setze(0, "massnahme", "Abrichten vor jedem Los, Messung nach erstem Teil")
    a.setze(0, "verantwortlich", "Yamine")
    a.setze(0, "termin", "20.11.2026")
    assert a.daten["zeilen"][0]["termin"] == "20.11.2026" and a.tabelle.item(0, 10).text() == "Maßnahme läuft"
    a.zeile_neu(bauteil="Rotornabe", beschreibung="Lackschaden am Flansch beim Transport", herkunft="Wareneingang",
                ursache="Keine Kantenschutzleisten", massnahme="Kantenschutz im Packplan", wirksam="ja")
    assert a.tabelle.item(1, 10).text() == "abgeschlossen"
    a.speichern_()
    bild(fenster, "77_abweichungen_hell")

    # ---- Risikobeurteilung (M46)
    fenster.gehe_zu("risiko")
    r = fenster.qseiten["risiko"]
    rb = r.neu()
    assert rb["nr"] == "RB-001" and r.tabelle.rowCount() >= 12 and r.grenzen["lebensdauer"].text()
    for i in range(3):
        r.setze(i, "umgesetzt", "ja")
    assert r.daten["zeilen"][0]["umgesetzt"] == "ja" and Q.risiko_bewerten(r.daten["zeilen"][0])[1] == Q.GRUEN
    r.speichern_()
    bild(fenster, "78_risiko_hell")
    assert r.pdf(str(BEISPIELE / "Risikobeurteilung_Beispiel.pdf")).stat().st_size > 3000

    # ---- Normen (M47)
    fenster.gehe_zu("normen")
    n = fenster.qseiten["normen"]
    nl = n.neu()
    norm = {z_["norm"]: i for i, z_ in enumerate(n.daten["zeilen"])}
    assert n.daten["zeilen"][norm["EN ISO 12100"]]["nachweis"] == "RB-001"
    assert n.daten["zeilen"][norm["ISO 286 / ISO 2768"]]["status"] == "in Arbeit"
    n.setze(norm["IEC 61400-11"], "status", "nicht anwendbar")
    assert nl and n.abgleichen() == 0
    n.speichern_()
    bild(fenster, "79_normen_hell")

    # ---- Technische Dokumentation (S16)
    fenster.gehe_zu("doku")
    dk = fenster.doku
    assert dk.tabelle.rowCount() == 11 and "fehlen" in dk.zusammenfassung.text()
    dk.ersteller.setText("Yamine")
    ziel = dk.erstellen(str(BEISPIELE / "Technische_Dokumentation_Beispiel.pdf"))
    leser = PdfReader(str(ziel))
    titel_ = [o.title for o in leser.outline if not isinstance(o, list)]
    assert len(leser.pages) >= 30 and "Montageanleitungen" in titel_ and "Prüfpläne" in titel_
    bild(fenster, "80_doku_hell")

    fenster.thema_setzen("dunkel")
    fenster.gehe_zu("pruefplaene")
    bild(fenster, "81_pruefplan_dunkel")
    fenster.gehe_zu("risiko")
    bild(fenster, "82_risiko_dunkel")
    thema.anwenden(app, "hell")
    shutil.rmtree(tmp_path, ignore_errors=True)
