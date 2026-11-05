"""K4-Oberfläche: Seite „Kollision & Schwerpunkt“ – Befunde, Ausnahmen mit Begründung, Masse und Schwerpunkt,
leerer Zustand. Die Seite wird einzeln als Fenster gezeigt (noch nicht im Hauptfenster eingebunden)."""
import dataclasses
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QScrollArea

from yamproduktion.cad import geometrie as G, kollision as K, vorlagen
from yamproduktion.modell import Projekt
from yamproduktion.ui import thema
from yamproduktion.ui.kollision_seite import LEER_TEXT, KollisionSeite

from test_oberflaeche import app, fenster  # noqa: F401

BILDER = Path(__file__).with_name("screenshots")


def _bild(widget, name):
    BILDER.mkdir(exist_ok=True)
    for _ in range(3):
        QApplication.processEvents()
    widget.grab().save(str(BILDER / f"{name}.png"))


def _ganz(seite, name):
    """Ganze Seite inklusive des Teils unterhalb der Bildschirmkante (zum Prüfen des Layouts)."""
    for _ in range(3):
        QApplication.processEvents()
    seite.findChild(QScrollArea).widget().grab().save(str(BILDER / f"{name}.png"))


@pytest.fixture
def seite(app):  # noqa: F811
    thema.anwenden(app, "hell")
    s = KollisionSeite()
    s.resize(1440, 900)
    s.show()
    app.processEvents()
    yield s
    s.close()
    s.deleteLater()             # Seite sofort abbauen, solange die QApplication noch lebt
    app.processEvents()
    thema.anwenden(app, "hell")


def _projekt(tmp_path):
    """KWA-Projekt mit Gondel: Welle, Nabe (ohne Nut), zwei Lager mit 0,5 mm Luft, Blattschrauben im Lochkreis
    (Kopf liegt an) und zwei Halteschrauben ohne Bohrung (stecken in der Nabe → Durchdringung)."""
    p = Projekt.neu(tmp_path / "KWA", "Kleinwindanlage KWA-5", "Mini-Windkraftanlage 5 kW", beispiel_kwa=True)
    wp = vorlagen.WelleParameter()
    e = G.eigenschaften(vorlagen.erzeuge_welle(wp))
    welle = p.teil_speichern("welle", "Hauptwelle", dataclasses.asdict(wp), e.masse(7850), e.volumen)
    np_ = vorlagen.NabeParameter(d_f=wp.d_nabe, mit_nut="nein")
    e = G.eigenschaften(vorlagen.erzeuge_nabe(np_))
    nabe = p.teil_speichern("nabe", "Rotornabe", dataclasses.asdict(np_), e.masse(7100), e.volumen)
    z_b = wp.l_nabe / 2 + wp.a_mm - wp.b_lager / 2          # Lager B auf dem Lagersitz
    d = {"parameter": [], "einbauten": [
        {"id": "E1", "art": "teil", "teil_id": welle["id"], "name": "Hauptwelle"},
        {"id": "E2", "art": "teil", "teil_id": nabe["id"], "name": "Rotornabe", "bezug": {"ziel": "E1", "abstand": "0"}},
        {"id": "E3", "art": "normteil", "norm": "6216", "name": "Loslager", "bezug": {"ziel": "E1", "abstand": f"{z_b:g}"}},
        {"id": "E4", "art": "normteil", "norm": "6216", "name": "Stützlager",
         "bezug": {"ziel": "E1", "abstand": f"{z_b - wp.b_lager - 0.5:g}"}},
        {"id": "E5", "art": "normteil", "norm": "ISO 4017 M16x60", "name": "Blattschraube",
         "bezug": {"ziel": "E1", "abstand": "0", "umdrehen": True}, "kreis": {"anzahl": "4", "radius": "150"}},
        {"id": "E6", "art": "normteil", "norm": "ISO 4762 M12x40", "name": "Halteschraube",
         "bezug": {"ziel": "E1", "abstand": "80"}, "kreis": {"anzahl": "2", "radius": "60"}},
    ]}
    r = p.baugruppe_bauen(d)
    assert r.ok, r.fehler
    g = p.baugruppe_speichern("Gondel – Triebstrang", d, r.masse)
    return p, g, r


def test_kollision_befunde_ausnahmen_masse(seite, tmp_path, app):  # noqa: F811
    projekt, g, r = _projekt(tmp_path)
    meldungen = []
    seite.meldung.connect(lambda text, fehler: meldungen.append((text, fehler)))
    seite.setze_projekt(projekt)
    assert seite.auswahl.count() == 1 and seite.baugruppe_id == g["id"] and seite.pruefung is None
    assert not seite.leer.isVisible() and "Noch nicht geprüft" in seite.status.text()

    # Mindestabstand wird je Baugruppe gemerkt
    seite.mindestabstand.setValue(1.0)
    seite.mindestabstand.editingFinished.emit()
    assert projekt.kollision_mindestabstand(g["id"]) == 1.0

    pr = seite.pruefen()
    assert pr is seite.pruefung and not pr.ok
    arten = [b.art for b in pr.befunde]
    assert arten.count(K.DURCHDRINGUNG) == 2 and arten.count(K.SPIEL) == 1 and K.BERUEHRUNG in arten
    assert seite.tabelle.rowCount() == len(pr.befunde)
    assert seite.tabelle.item(0, 0).text() == K.DURCHDRINGUNG and "Halteschraube" in seite.tabelle.item(0, 2).text()
    assert seite.tabelle.item(0, 5).text() == "offen"
    assert seite.status.objectName() == "Fehler" and "3 offene Befunde" in seite.status.text()
    spiel = next(i for i, b in enumerate(pr.befunde) if b.art == K.SPIEL)
    assert seite.tabelle.item(spiel, 4).text() == "0,5"
    # Hervorhebung: alle Teile mit offenem Befund, nach Klick nur die zwei des Befunds
    assert seite.markierte() == pr.betroffene()
    seite.tabelle.selectRow(spiel)
    b = pr.befunde[spiel]
    assert seite.markierte() == sorted([b.a, b.b])
    assert "Spiel zu klein" in seite.detail.text() and "0,5 mm Abstand" in seite.detail.text()
    seite.tabelle.clearSelection()
    assert seite.markierte() == pr.betroffene()

    # Masse und Schwerpunkt wie aus dem Aufbau der Baugruppe
    m = seite.massen
    assert abs(m.masse - r.masse) < 1e-9 and abs(m.masse - seite.ergebnis.masse) < 1e-9
    assert all(abs(a - b) < 1e-6 for a, b in zip(m.schwerpunkt, r.schwerpunkt))
    assert "Gesamtmasse" in seite.kennwerte.text() and "kg·m²" in seite.kennwerte.text()
    assert seite.masse_tabelle.rowCount() == 6
    assert seite.masse_tabelle.item(0, 1).text() == "Hauptwelle" and seite.masse_tabelle.item(0, 4).text().endswith("%")
    assert abs(sum(z.anteil for z in m.je_einbau) - 1) < 1e-9
    assert seite.ansicht.schwerpunkt_bild() is not None
    seite.ansicht.ansicht("Iso")
    _bild(seite, "120_kollision_befunde_hell")
    _ganz(seite, "126_kollision_ganze_seite_hell")
    thema.anwenden(app, "dunkel")
    seite.pruefen()
    _bild(seite, "121_kollision_befunde_dunkel")
    _ganz(seite, "127_kollision_ganze_seite_dunkel")
    thema.anwenden(app, "hell")
    seite.pruefen()

    # Ausnahme: gilt für beide Halteschrauben (gleiches Paar von Einbauten)
    assert not seite.ausnahme_setzen(0, "   ")                     # leere Begründung → nichts vermerkt
    assert seite.ausnahme_setzen(0, "Schraube vereinfacht, Gewindebohrung fehlt im Modell")
    pr = seite.pruefung
    assert pr.anzahl(K.DURCHDRINGUNG) == 0 and pr.fehler_anzahl == 1
    assert seite.tabelle.item(0, 5).text().startswith("✓ Schraube vereinfacht")
    assert seite.tabelle.item(1, 5).text().startswith("✓ Schraube vereinfacht")
    assert "1 offener Befund" in seite.status.text() and "2 als gewollt vermerkt" in seite.status.text()
    assert projekt.kollision_ausnahmen(g["id"]) == {("E2", "E6"): "Schraube vereinfacht, Gewindebohrung fehlt im Modell"}
    assert seite.ausnahme_setzen(spiel, "Lager liegen mit Distanzring an – Ring nicht modelliert")
    assert seite.pruefung.ok and seite.status.objectName() == "Ok" and seite.status.text().startswith("✓")
    assert seite.markierte() == sorted([b.a, b.b])                 # bearbeitete Zeile bleibt gewählt
    seite.tabelle.clearSelection()
    assert seite.markierte() == []                                 # nichts mehr offen
    seite.tabelle.selectRow(0)
    _bild(seite, "122_kollision_ausnahme_hell")
    thema.anwenden(app, "dunkel")
    seite.laden()
    seite.tabelle.selectRow(0)
    _bild(seite, "123_kollision_ausnahme_dunkel")
    thema.anwenden(app, "hell")

    # Bleibt nach laden() erhalten (neu geprüft, Ausnahmen aus dem Projekt)
    seite.laden()
    assert seite.pruefung is not pr and seite.pruefung.ok
    assert sum(1 for b in seite.pruefung.befunde if b.ausnahme) == 3
    assert seite.mindestabstand.value() == 1.0

    # Ausnahme aufheben → Befund zählt wieder
    zeile = next(i for i, b in enumerate(seite.pruefung.befunde) if b.art == K.SPIEL)
    assert seite.ausnahme_aufheben(zeile)
    assert seite.pruefung.fehler_anzahl == 1 and seite.tabelle.item(zeile, 5).text() == "offen"
    assert not seite.ausnahme_aufheben(zeile)                    # ist schon offen
    assert ("E3", "E4") not in projekt.kollision_ausnahmen(g["id"])
    seite.laden()
    assert seite.pruefung.fehler_anzahl == 1
    # Prüfbericht als PDF, als Unterlage gemerkt
    pdf = seite.bericht_speichern(str(tmp_path / "Kollision.pdf"))
    assert pdf and pdf.stat().st_size > 1000 and projekt.dokumente("kollisionsbericht")
    # ohne Zeile und ohne Auswahl: freundlicher Hinweis statt Absturz
    seite.tabelle.clearSelection()
    seite.tabelle.setCurrentCell(-1, -1)
    assert not seite.ausnahme_setzen(None, "x")
    assert any("anklicken" in t for t, _ in meldungen)

    # Mindestabstand 0 → kein „Spiel zu klein“ mehr
    seite.mindestabstand.setValue(0.0)
    pr0 = seite.pruefen()
    assert pr0.anzahl(K.SPIEL) == 0 and pr0.ok
    assert projekt.kollision_mindestabstand(g["id"]) == 0.0

    # Fehler verständlich, kein Absturz: Baugruppe zeigt auf ein gelöschtes Teil
    d = projekt.baugruppe(g["id"])["definition"]
    d["einbauten"][0]["teil_id"] = 9999
    projekt.baugruppe_speichern("Gondel – Triebstrang", d, None, g["id"])
    seite.laden()
    seite.pruefen()
    assert seite.status.objectName() == "Fehler"
    projekt.schliessen()


def test_kollision_leer(seite, tmp_path, app):  # noqa: F811
    projekt = Projekt.neu(tmp_path / "Leer", "Kleinwindanlage KWA-5", "Mini-Windkraftanlage 5 kW", beispiel_kwa=True)
    meldungen = []
    seite.meldung.connect(lambda text, fehler: meldungen.append((text, fehler)))
    seite.setze_projekt(projekt)
    assert seite.auswahl.count() == 0 and seite.leer.isVisible() and not seite.haupt.isVisible()
    assert not seite.pruefen_knopf.isEnabled()
    assert seite.pruefen() is None and meldungen[-1] == (LEER_TEXT, True)
    assert not seite.ausnahme_setzen(0, "x") and not seite.ausnahme_aufheben(0)
    _bild(seite, "124_kollision_leer_hell")
    thema.anwenden(app, "dunkel")
    _bild(seite, "125_kollision_leer_dunkel")
    projekt.schliessen()
    seite.setze_projekt(None)
    assert seite.leer.isVisible()


def test_kollision_im_hauptfenster(fenster, tmp_path):  # noqa: F811
    """Navigationseintrag „Kollision & Schwerpunkt“ öffnet die Seite mit den Baugruppen des Projekts."""
    from yamproduktion.ui.hauptfenster import NAVIGATION
    projekt = Projekt.neu(tmp_path / "H", "Haupt", "")
    projekt.baugruppe_speichern("Muttern", {"parameter": [], "einbauten": [
        {"id": "E1", "art": "normteil", "norm": "ISO 4032 M16", "name": "Mutter", "lage": {}},
        {"id": "E2", "art": "normteil", "norm": "ISO 4032 M16", "name": "Mutter 2", "lage": {"x": "5"}}]})
    fenster.projekt_laden(projekt)
    assert any(s == "kollision" for _, s in NAVIGATION)
    fenster.gehe_zu("kollision")
    assert fenster.stapel.currentWidget() is fenster.kollision
    assert fenster.kollision.auswahl.count() == 1
    assert fenster.kollision.pruefen().fehler_anzahl == 1
