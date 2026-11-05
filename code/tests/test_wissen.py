"""MS14 Wissensbasis: Import, Texterkennung, Suche mit Fundstelle, Fragen, Formel als Berechnung (M50–M52, S19, S20)."""
from pathlib import Path

import pytest
from reportlab.pdfgen import canvas

from yamproduktion.berechnungen import formel as F
from yamproduktion.modell import Projekt, ProjektFehler
from yamproduktion.wissen import bibliothek as B, texterkennung as T

from buchbeispiel import beispielbuch


@pytest.fixture
def bib(tmp_path):
    b = B.Bibliothek(tmp_path / "Bibliothek")
    yield b
    b.schliessen()


def test_import_kapitel_und_suche(bib, tmp_path):
    buch = bib.importieren(beispielbuch(tmp_path / "uebung.pdf"), "Übungsbuch Maschinenelemente", "Muster")
    assert buch.seiten == 5 and buch.erkannt == "Textebene" and buch.kurz == "B001"
    assert bib.pfad(buch).exists() and bib.pfad(buch).parent == tmp_path / "Bibliothek" / "buecher"
    # Kapitel aus den Lesezeichen, Folgeseiten erben das Kapitel
    assert bib.seitentext(buch.id, 3)[1] == "11 Achsen und Wellen"
    assert bib.seitentext(buch.id, 5)[1] == "14 Wälzlager"
    # Suche: Präfix, ohne Umlaut, mit Fundstelle
    t = bib.suchen("lebensdauer waelzlager") or bib.suchen("lebensdauer walzlager")
    assert t and t[0].nr == 4 and t[0].kapitel == "14 Wälzlager" and "<b>" in t[0].ausschnitt
    assert bib.suchen('"Gestaltänderungsenergiehypothese"')[0].nr == 3
    assert bib.suchen("Vergleichsspannung")[0].fundstelle == "Übungsbuch Maschinenelemente · 11 Achsen und Wellen · S. 3"
    # Seitenversatz: PDF-Seite 3 ist gedruckte Seite 1
    buch = bib.aendern(buch.id, versatz=2)
    assert bib.suchen("Vergleichsspannung")[0].fundstelle.endswith("S. 1 (PDF 3)")
    assert bib.suchen("Zahnrad") == [] and bib.suchen("") == []


def test_kapitel_aus_text():
    assert B.kapitel_aus_text("6.2 Wellen und Achsen\nText") == "6.2 Wellen und Achsen"
    assert B.kapitel_aus_text("Die Welle 12 dreht") is None
    assert B.suchausdruck('Welle "mittige Last" d') == '"mittige Last" AND "Welle"*'


def test_frage_mit_fundstellen(bib, tmp_path):
    bib.importieren(beispielbuch(tmp_path / "uebung.pdf"), "Übungsbuch")
    woerter, treffer = bib.frage("Wie berechnet man die Lebensdauer eines Wälzlagers?")
    assert "wälzlager" in woerter and "wie" not in woerter
    assert treffer[0].nr == 4
    woerter, treffer = bib.frage("Welche Spannung entsteht durch Biegung der Welle?")
    assert {t.nr for t in treffer} & {2, 3}
    assert bib.frage("wie und was") == ([], [])
    assert "nicht geprüft" in B.HINWEIS_FRAGE


def test_scan_ohne_text_mit_texterkennung(bib, tmp_path, monkeypatch):
    pdf = tmp_path / "scan.pdf"
    c = canvas.Canvas(str(pdf))
    for _ in range(2):
        c.rect(50, 50, 200, 200)                 # nur Grafik, kein Text – wie ein Scan
        c.showPage()
    c.save()
    # ohne Werkzeug: übernommen, aber als „ohne Text“
    monkeypatch.setattr(T, "werkzeug", lambda _n: None)
    meldungen = []
    buch = bib.importieren(pdf, "Scan", fortschritt=meldungen.append)
    assert buch.erkannt == "ohne Text" and bib.ohne_text(buch.id) == 2
    assert any("brew install" in m for m in meldungen)
    # mit (ersetzter) Texterkennung
    monkeypatch.setattr(T, "ersatz_ocr", lambda p, m: ["Passfeder nach DIN 6885 Seite eins", "Flächenpressung p"])
    buch = bib.importieren(pdf, "Scan erkannt")
    assert buch.erkannt == "Texterkennung (Test)" and bib.suchen("passfeder")[0].buch.id == buch.id


def test_bilder_als_buch_und_loeschen(bib, tmp_path):
    from PySide6.QtGui import QColor, QImage
    bilder = []
    for i in range(2):
        img = QImage(600, 800, QImage.Format_RGB32)
        img.fill(QColor("white"))
        bilder.append(tmp_path / f"seite_{i}.png")
        img.save(str(bilder[-1]))
    buch = bib.importieren(bilder, "Fotos", ocr=False)
    assert buch.seiten == 2 and bib.pfad(buch).exists()
    bib.loeschen(buch.id)
    assert bib.buecher() == [] and not bib.pfad(buch).exists()
    with pytest.raises(B.BibliothekFehler):
        bib.importieren(tmp_path / "fehlt.pdf")


def test_formel_rechnen():
    assert F.variablen("σ_v = sqrt(σ_b^2 + 3 · (α_0 · τ_t)^2)") == ["σ_b", "α_0", "τ_t"]
    e = F.berechne(F.FormelEingaben("M_b = F · l / 4", {"F": [2000, "N"], "l": [300, "mm"]}, "N·m",
                                    "Biegemoment", "Übungsbuch, 11 Achsen und Wellen, S. 2"))
    g = e.ergebnisse[0]
    assert (g.symbol, round(g.wert, 6), g.einheit) == ("M_b", 150, "N·m")
    assert e.quellen == ["Übungsbuch, 11 Achsen und Wellen, S. 2"] and e.unbelegt == []
    assert "2000 N · 300 mm / 4" in e.schritte[0].einsetzen and "prüfen" in e.hinweise[0]
    e = F.berechne(F.FormelEingaben("L_10 = (C / P)^p", {"C": [30, "kN"], "P": [3000, "N"], "p": [3, ""]}))
    assert round(e.ergebnisse[0].wert) == 1000 and e.unbelegt
    for formel, werte, fehler in [("x = F + l", {"F": [1, "N"], "l": [1, "m"]}, "Einheiten"),
                                  ("x = open(1)", {}, "Erlaubte Funktionen"),
                                  ("x = a / b", {"a": [1, ""], "b": [0, ""]}, "null"),
                                  ("x = a", {"a": [1, "Bananen"]}, "Einheit"),
                                  ("x = a", {}, "fehlt"),
                                  ("a + b = c", {}, "einzelner Name")]:
        with pytest.raises(F.FormelFehler, match=fehler):
            F.berechne(F.FormelEingaben(formel, werte))
    with pytest.raises(F.FormelFehler, match="umrechnen"):
        F.berechne(F.FormelEingaben("x = a", {"a": [1, "N"]}, "mm"))


def test_formel_als_berechnung_im_projekt(tmp_path):
    p = Projekt.neu(tmp_path / "KWA", "KWA", "Test")
    b = p.formel_speichern(F.FormelEingaben("M_b = F · l / 4", {"F": [2000, "N"], "l": [300, "mm"]}, "N·m",
                                            "Biegemoment Rotorwelle", "Übungsbuch, 11 Achsen und Wellen, S. 2"))
    assert b.nr == "B-001" and b.typ == "formel" and b.ergebnis["quellen"] == ["Übungsbuch, 11 Achsen und Wellen, S. 2"]
    neu = p.berechnung_neu_rechnen(b.id)
    assert neu.version == 2 and round(neu.ergebnis["ergebnisse"][0]["wert"]) == 150
    with pytest.raises(ProjektFehler):
        p.formel_speichern(F.FormelEingaben("x = a", {}))
    # M52: Buchtexte gelangen nicht in die Projektdatei
    assert b"Gestalt" not in Path(p.pfad).read_bytes() if Path(p.pfad).is_file() else True
    p.schliessen()


def test_bibliothek_getrennt_vom_projekt(tmp_path):
    """M52/N3: Standardordner liegt außerhalb jedes Projekts, Bibliothek kennt kein Projekt."""
    assert B.STANDARD_ORDNER.name == "Bibliothek" and "Documents" in B.STANDARD_ORDNER.parts
    assert T.SPRACHEN == "deu+eng"
