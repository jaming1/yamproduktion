"""Bibliothek-Seite mit Yamaktaba: suchen, fragen, Seite mit Original-PDF, Formel übernehmen, Projekt archivieren."""
import shutil

from yamproduktion.modell import Projekt
from yamproduktion.ui import thema

from test_oberflaeche import app, bild, fenster  # noqa: F401
from yamaktaba_beispiel import yamaktaba_bauen


def test_yamaktaba_in_der_bibliothek(fenster, tmp_path, app):  # noqa: F811
    ordner = yamaktaba_bauen(tmp_path / "ashamila")
    fenster.einst.setValue("yamaktaba_ordner", str(ordner))
    fenster.einst.setValue("bibliothek_ordner", str(tmp_path / "Bibliothek"))
    projekt = Projekt.neu(tmp_path / "KWA", "Kleinwindanlage KWA-5", "Mini-Windkraftanlage 5 kW", vorlage="kwa")
    fenster.projekt_laden(projekt)
    fenster.gehe_zu("bibliothek")
    w = fenster.bibliothek
    assert w.yk and w.quelle.currentData() == "yk" and "Verbunden: 1 Buch, davon 1 deutsch" in w.yk_info.text()
    w.suche.setText("Lebensdauer Wälzlager")
    w.suchen()
    assert w.treffer.count() == 1 and "in Yamaktaba" in w.antwort.text()
    assert w._ansicht == "yk" and "Übungsbuch Maschinenelemente" in w.seiten_info.text()
    assert not w.bild.pixmap().isNull() and "L_10" in w.text.toPlainText()
    w._blaettern(-1)
    assert w._yk_seite.seite_id == 3 and "Vergleichsspannung" in w.text.toPlainText()
    w.suche.setText("Wie groß ist das Biegemoment einer Welle bei mittiger Last?")
    w.fragen()
    assert "nicht geprüft" in w.antwort.text() and w._yk_seite.seite_id == 2
    bild(fenster, "96_yamaktaba_frage_hell")
    c = w.text.document().find("M_b = F · l / 4")
    w.text.setTextCursor(c)
    dlg = w.formel_dialog()
    assert dlg.formel.text() == "M_b = F · l / 4" and "aus Yamaktaba" in dlg.quelle.text()
    assert "11 Achsen und Wellen" in dlg.quelle.text()
    # Abnahme zählt die deutschen Yamaktaba-Bücher mit
    assert w.buecher_gesamt() == 1
    # Archivieren
    pdf = fenster.uebersicht.lastenheft_speichern(str(tmp_path / "Lastenheft.pdf"))
    assert pdf
    erg = fenster.projekt_archivieren(fragen=False)
    assert erg and len(erg["neu"]) == 1 and "archiviert" in fenster.statusBar().currentMessage()
    w.suche.setText("Kleinwindanlage")
    w.suchen()
    assert any("Kleinwindanlage" in w.treffer.itemWidget(w.treffer.item(i)).text() for i in range(w.treffer.count()))
    fenster.thema_setzen("dunkel")
    w.suche.setText("Lebensdauer Wälzlager")
    w.suchen()
    bild(fenster, "97_yamaktaba_dunkel")
    thema.anwenden(app, "hell")
    w.yk.schliessen()
    shutil.rmtree(tmp_path, ignore_errors=True)
