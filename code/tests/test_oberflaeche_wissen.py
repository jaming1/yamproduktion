"""MS14-Oberfläche: Bibliothek mit Beispielbuch – Suche, Frage, Seitenansicht, Formel als Berechnung."""
import shutil

from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication

from yamproduktion.modell import Projekt
from yamproduktion.ui import thema

from buchbeispiel import beispielbuch
from test_oberflaeche import BILDER, app, bild, fenster  # noqa: F401


def test_bibliothek(fenster, tmp_path, app):  # noqa: F811
    fenster.einst.setValue("bibliothek_ordner", str(tmp_path / "Bibliothek"))
    projekt = Projekt.neu(tmp_path / "KWA", "Kleinwindanlage KWA-5", "Mini-Windkraftanlage 5 kW", beispiel_kwa=True)
    fenster.projekt_laden(projekt)
    fenster.gehe_zu("bibliothek")
    w = fenster.bibliothek
    assert fenster.stapel.currentWidget() is w and w.buecher.count() == 0
    w.synchron = True
    w.importieren(str(beispielbuch(tmp_path / "Uebungsbuch.pdf")), "Übungsbuch Maschinenelemente")
    assert w.buecher.count() == 1 and w._buch.seiten == 5 and "übernommen" in w.fortschritt.text()
    w.versatz.setValue(1)
    w._buch_aendern()
    assert w._buch.versatz == 1

    # Suche (M50) → Fundstelle mit Kapitel und Seite, Seite öffnet sich (M51)
    w.suche.setText("Lebensdauer Wälzlager")
    w.suchen()
    assert w.treffer.count() >= 1 and w._nr == 4
    assert "S. 3 (PDF 4)" in w.seiten_info.text() and "14 Wälzlager" in w.seiten_info.text()
    assert w.text.extraSelections() and not w.bild.pixmap().isNull()
    bild(fenster, "89_bibliothek_suche_hell")

    # Frage (S19) → Vorschlag mit Fundstellen, deutlich als ungeprüft markiert
    w.suche.setText("Wie groß ist das Biegemoment einer Welle bei mittiger Last?")
    w.fragen()
    assert "nicht geprüft" in w.antwort.text() and w._nr in (2, 3)
    w.seite_zeigen(2)
    bild(fenster, "90_bibliothek_frage_hell")

    # Formel markieren → Berechnung mit Quelle (S20)
    doc = w.text.document()
    c = doc.find("M_b = F · l / 4")
    assert not c.isNull()
    w.text.setTextCursor(c)
    dlg = w.formel_dialog()
    assert dlg.formel.text() == "M_b = F · l / 4"
    assert dlg.quelle.text() == "Übungsbuch Maschinenelemente, 11 Achsen und Wellen, S. 1"
    assert dlg.werte.rowCount() == 2
    dlg.name.setText("Biegemoment Rotorwelle")
    dlg.werte.item(0, 1).setText("2000")
    dlg.werte.item(0, 2).setText("N")
    dlg.werte.item(1, 1).setText("300")
    dlg.werte.item(1, 2).setText("mm")
    dlg.einheit.setText("N·m")
    assert dlg.berechnen() and "150 N·m" in dlg.vorschau.text()
    dlg.resize(640, 560)
    dlg.show()
    QApplication.processEvents()
    dlg.grab().save(str(BILDER / "91_formel_uebernehmen_hell.png"))
    dlg._speichern()
    b = dlg.gespeichert
    assert b and b.typ == "formel" and "11 Achsen und Wellen" in b.ergebnis["quellen"][0]
    fenster.gehe_zu("berechnungen")
    zeilen = [fenster.berechnungen.tabelle.item(i, 2).text() for i in range(fenster.berechnungen.tabelle.rowCount())]
    assert any(z.startswith("M_b = 150") for z in zeilen)

    fenster.thema_setzen("dunkel")
    fenster.gehe_zu("bibliothek")
    w.suche.setText("Vergleichsspannung")
    w.suchen()
    bild(fenster, "92_bibliothek_dunkel")
    thema.anwenden(app, "hell")
    shutil.rmtree(tmp_path, ignore_errors=True)
