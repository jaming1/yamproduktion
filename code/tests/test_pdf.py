from yamproduktion.berechnungen import rotor
from yamproduktion.modell import Projekt
from yamproduktion.pdf import protokoll_erstellen


def test_protokoll_wird_erstellt_und_gespeichert(tmp_path):
    p = Projekt.neu(tmp_path / "x", "KWA-5")
    e = rotor.berechne(rotor.RotorEingaben())
    eintrag = p.berechnung_speichern(e.als_dict(), rotor.RotorEingaben().__dict__)
    assert eintrag.nr == "B-001" and eintrag.erfuellt
    ziel = protokoll_erstellen(e.als_dict(), tmp_path / "B-001.pdf", p.name, eintrag.nr)
    daten = ziel.read_bytes()
    assert daten.startswith(b"%PDF") and len(daten) > 5000
