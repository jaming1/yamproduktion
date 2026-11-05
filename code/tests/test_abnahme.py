"""MS15: Abnahme Version 1 – der ganze Ablauf der Kleinwindanlage in der App bis „11 von 11 Kriterien erfüllt“,
Projekt-Export als Archiv (K1) und Vorlagen je Produkttyp (S1)."""
import shutil
import zipfile
from pathlib import Path

import pytest
from pypdf import PdfReader

from yamproduktion import abnahme as A
from yamproduktion.betrieb import inbetriebnahme as IB
from yamproduktion.modell import NEU_PRUEFEN, VORLAGEN, Projekt, ProjektFehler
from yamproduktion.ui import thema

from buchbeispiel import beispielbuch
from test_oberflaeche import BILDER, app, bild, fenster  # noqa: F401

BEISPIELE = BILDER
RECHNUNGEN = ("rotor", "ertrag", "lasten", "antrieb", "welle", "lager", "schrauben", "passfeder", "pressverband",
              "schweissnaht", "turm", "bremse")


def _alles_neu_pruefen(p: Projekt):
    """Nach einer Wertänderung: Berechnungen neu rechnen, Bauteile neu erzeugen, übrige Objekte prüfen."""
    for _ in range(6):
        offen = p.neu_zu_pruefen()
        if not offen:
            return
        ids = [b.id for b in offen if b.typ == "berechnung"]
        for bid in p.berechnungen_in_reihenfolge(ids):
            p.berechnung_neu_rechnen(bid)
        for b in p.neu_zu_pruefen():
            if b.typ == "teil":
                p.teil_neu_erzeugen(b.id)
            elif b.typ not in ("berechnung", "anforderung"):
                p.status_setzen(b.typ, b.id, "geprüft")
            elif b.typ == "anforderung":
                p.status_setzen(b.typ, b.id, "geprüft")
    assert p.neu_zu_pruefen() == []


def test_vorlagen_und_export(tmp_path):
    assert set(VORLAGEN) == {"kwa", "kwa_anforderungen", "leer"}
    leer = Projekt.neu(tmp_path / "leer", "Leer", vorlage="leer")
    assert leer.anforderungen() == [] and leer.aufgaben() == []
    kwa = Projekt.neu(tmp_path / "kwa", "KWA", vorlage="kwa")
    assert len(kwa.anforderungen()) >= 4 and len(kwa.aufgaben()) >= 15 and kwa.meta("vorlage") == "kwa"
    alt = Projekt.neu(tmp_path / "alt", "Alt", beispiel_kwa=True)            # alte Schreibweise
    assert alt.anforderungen() and not alt.aufgaben()
    with pytest.raises(ProjektFehler):
        Projekt.neu(tmp_path / "x", "X", vorlage="boot")
    # Export mit Unterlage, Buchtext darf nicht hinein
    pdf = tmp_path / "Lastenheft.pdf"
    pdf.write_bytes(b"%PDF-1.4 Test")
    kwa.dokument_merken("lastenheft", pdf)
    kwa.dokument_merken("lastenheft", pdf)                                   # nicht doppelt
    assert len(kwa.dokumente("lastenheft")) == 1
    archiv = kwa.exportieren(tmp_path / "Export" / "KWA")
    assert archiv.suffix == ".zip"
    namen = zipfile.ZipFile(archiv).namelist()
    assert set(namen) == {"kwa.yamp", "Unterlagen/Lastenheft.pdf", "LIESMICH.txt"}
    # Import an anderem Ort, Pfade der Unterlagen zeigen auf die Kopie
    neu = Projekt.importieren(archiv, tmp_path / "Mac2")
    assert neu.name == "KWA" and len(neu.anforderungen()) == len(kwa.anforderungen())
    assert Path(neu.dokumente("lastenheft")[0]["pfad"]).read_bytes() == b"%PDF-1.4 Test"
    with pytest.raises(ProjektFehler, match="schon"):
        Projekt.importieren(archiv, tmp_path / "Mac2")
    kaputt = tmp_path / "kaputt.zip"
    kaputt.write_bytes(b"kein zip")
    with pytest.raises(ProjektFehler, match="kein lesbares"):
        Projekt.importieren(kaputt, tmp_path / "Mac3")
    # Abnahme: Kriterien 10 und 11 nur von Hand
    k = {x.nr: x for x in A.pruefen(kwa)}
    assert k[11].stand == A.BESTAETIGEN and k[10].stand == A.OFFEN and k[1].stand == A.OFFEN
    kwa.abnahme_bestaetigen(11, True, "macOS 15, ganzer Ablauf ohne Absturz")
    assert A.pruefen(kwa)[10].stand == A.ERFUELLT
    kwa.abnahme_bestaetigen(11, False)
    assert A.pruefen(kwa)[10].stand == A.BESTAETIGEN
    for p in (leer, kwa, alt, neu):
        p.schliessen()


def test_ganzer_ablauf_bis_zur_abnahme(fenster, tmp_path, app):  # noqa: F811
    fenster.einst.setValue("bibliothek_ordner", str(tmp_path / "Bibliothek"))
    projekt = Projekt.neu(tmp_path / "KWA", "Kleinwindanlage KWA-5", "Mini-Windkraftanlage 5 kW", vorlage="kwa")
    fenster.projekt_laden(projekt)
    for a in projekt.aufgaben():                                    # Zeitplan hier nicht Gegenstand
        projekt.aufgabe_aendern(a["id"], stand="erledigt")
    fenster.gehe_zu("abnahme")
    ab = fenster.abnahme
    assert fenster.stapel.currentWidget() is ab and "0 von 11" in ab.stand.text()

    # ---- 1 Idee, TRIZ, Lastenheft
    i = projekt.objekt_neu("idee", titel="Kleinwindanlage für Inselbetrieb", problem="Gartenhaus ohne Netz")
    projekt.widerspruch_neu("Größerer Rotor bringt mehr Leistung, belastet aber den Turm", 21, 14, idee_id=i["id"])
    assert fenster.uebersicht.lastenheft_speichern(str(tmp_path / "Lastenheft.pdf"))

    # ---- 2 Konzept: morphologischer Kasten und Nutzwertanalyse
    wurzel = projekt.funktion_neu("Windenergie in elektrische Energie wandeln")
    for name, wege in (("Drehzahl anpassen", ["Stirnradgetriebe", "Direktantrieb"]),
                       ("Strom erzeugen", ["Asynchrongenerator", "PM-Synchrongenerator"])):
        f = projekt.funktion_neu(name, wurzel["id"])
        for w in wege:
            projekt.loesung_neu(f["id"], w)
    v1 = projekt.variante_neu("Getriebe + Asynchron")
    v2 = projekt.variante_neu("Direktantrieb + PMSG")
    for f in projekt.teilfunktionen():
        l1, l2 = projekt.loesungen(f["id"])
        projekt.variante_wahl_setzen(v1["id"], f["id"], l1["id"])
        projekt.variante_wahl_setzen(v2["id"], f["id"], l2["id"])
    for name, g in (("Kosten", 3), ("Wartung", 2)):
        k = projekt.kriterium_neu(name, g)
        projekt.bewerten(v1["id"], k, 6)
        projekt.bewerten(v2["id"], k, 8)
    projekt.variante_auswaehlen(v2["id"], "Wartungsarm ohne Getriebe")

    # ---- 3 alle Muss-Berechnungen mit Protokoll (Direktantrieb: Getriebe entfällt)
    for s in RECHNUNGEN:
        fenster.gehe_zu(s)
        fenster.rechenseiten[s].aus_anforderungen()
        assert fenster.rechenseiten[s].protokoll_speichern(str(tmp_path / f"{s}.pdf")), s
    ab.laden()
    k3 = ab.kriterien[2]
    assert k3.stand == A.ERFUELLT, k3.fehlt
    assert any("entfällt (Direktantrieb" in n for n in k3.nachweise)

    # ---- 4 Bauteile, Baugruppe, Zeichnung, Stückliste
    fenster.gehe_zu("bauteile")
    s = fenster.bauteile
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
    assert g.baugruppe_speichern()

    # ---- 5 Wertänderung 5 → 6 kW: Berechnungen, Bauteile und Baugruppe werden „neu prüfen“
    a = projekt.anforderung_suchen("nennleistung")
    projekt.anforderung_aendern(a.id, zielwert=6.0)
    offen = {b.typ for b in projekt.neu_zu_pruefen()}
    assert {"berechnung", "teil", "baugruppe"} <= offen
    ab.laden()
    assert ab.kriterien[4].stand == A.OFFEN and ab.kriterien[2].stand == A.OFFEN
    _alles_neu_pruefen(projekt)
    ab.laden()
    assert ab.kriterien[4].stand == A.ERFUELLT, ab.kriterien[4].fehlt
    welle, nabe = projekt.teile()

    g.stueckliste_exportieren(str(tmp_path / "Stueckliste.pdf"), "pdf")
    fenster.zeichnung_oeffnen("teil", welle["id"])
    assert fenster.zeichnungen.exportieren(str(tmp_path / "Welle.pdf"), "pdf")

    # ---- 6 Arbeitspläne mit Kosten, Kalkulation
    fenster.gehe_zu("arbeitsplaene")
    ap = fenster.arbeitsplaene
    ap.teil_laden(welle["id"])
    ap.plan_speichern()
    ap.teil_laden(nabe["id"])
    ap.fertigung.setCurrentIndex(ap.fertigung.findData("fremd"))
    ap._setze_plan("fertigung", "fremd")
    ap.preis_fremd.setText("410")
    ap.preis_fremd.editingFinished.emit()
    ap.plan_speichern()
    fenster.gehe_zu("kosten")
    assert fenster.kosten.kalkulation_pdf(str(tmp_path / "Kalkulation.pdf"))

    # ---- 7 Montageplan mit Montageplatte und Anleitung
    fenster.gehe_zu("montage")
    m = fenster.montage
    assert m.montageplatte_erzeugen()
    assert m.plan_speichern()
    assert m.pdf(str(tmp_path / "Montageanleitung.pdf"))

    # ---- 8 Inbetriebnahme abgenommen, Abnahmeprotokoll
    fenster.gehe_zu("inbetriebnahme")
    ib = fenster.inbetriebnahme
    ib.neu()
    for n, pkt in enumerate(ib.daten["punkte"]):
        if pkt["min"] is None and pkt["max"] is None:
            ib.setze_ist(n, "i. O.")
        else:
            ib.setze_ist(n, str(pkt["max"] if pkt["max"] is not None else pkt["min"]).replace(".", ","))
    for v in (4, 6, 8, 10, 12):
        ib.messpunkt_neu(v, round(IB.kurve_soll(ib.daten["soll_kurve"], v), 2))
    ib.speichern_()
    assert ib.pdf("abnahme", str(tmp_path / "Abnahmeprotokoll.pdf"))

    # ---- 9 FMEA, Risiko, Normen, technische Doku
    for typ in ("fmea", "risiko", "normen"):
        fenster.gehe_zu(typ)
        q = fenster.qseiten[typ]
        q.neu("Konstruktions-FMEA") if typ == "fmea" else q.neu()
        q.speichern_()
    fenster.gehe_zu("doku")
    assert fenster.doku.erstellen(str(tmp_path / "Technische_Doku.pdf"))

    # ---- 10 Buchsuche mit eigenem (hier: Übungs-)Buch, 11 Lauf auf dem Mac – beide von Hand bestätigt
    fenster.gehe_zu("bibliothek")
    w = fenster.bibliothek
    w.synchron = True
    w.importieren(str(beispielbuch(tmp_path / "Uebungsbuch.pdf")), "Übungsbuch")
    w.suche.setText("Lebensdauer Wälzlager")
    w.fragen()
    assert w._nr == 4

    fenster.gehe_zu("abnahme")
    stand = {k.nr: k for k in ab.kriterien}
    assert [n for n, k in stand.items() if k.stand == A.OFFEN] == [], {n: k.fehlt for n, k in stand.items() if k.fehlt}
    assert stand[10].stand == stand[11].stand == A.BESTAETIGEN and "9 von 11" in ab.stand.text()
    bild(fenster, "93_abnahme_offen_hell")
    ab.bestaetigen(10, True, "„Lebensdauer Wälzlager“ → Übungsbuch S. 3, Kapitel 14 Wälzlager")
    ab.bestaetigen(11, True, "Probelauf ganzer Ablauf")
    assert "11 von 11" in ab.stand.text() and "abgenommen" in ab.stand.text()
    bild(fenster, "94_abnahme_fertig_hell")
    pdf = ab.pdf(str(BEISPIELE / "Abnahme_Version_1_Beispiel.pdf"))
    assert "11 von 11" in PdfReader(str(pdf)).pages[0].extract_text()

    # ---- K1 Export: Projektdatei + alle erzeugten Unterlagen, kein Buch
    archiv = fenster.projekt_exportieren(str(tmp_path / "Export.zip"))
    namen = zipfile.ZipFile(archiv).namelist()
    assert "KWA.yamp" in namen and "Unterlagen/Technische_Doku.pdf" in namen and len(namen) >= 18
    assert not any("Uebungsbuch" in n or n.startswith("buecher") for n in namen)

    fenster.thema_setzen("dunkel")
    fenster.gehe_zu("abnahme")
    bild(fenster, "95_abnahme_dunkel")
    thema.anwenden(app, "hell")
    shutil.rmtree(tmp_path, ignore_errors=True)
