"""Rotorauslegung gegen Handrechnung prüfen (N5: Abweichung höchstens 1 %)."""
import math

import pytest

from yamproduktion.berechnungen import rotor


def test_handrechnung_5kw():
    # Handrechnung: A = 2·5000 / (1,225·0,40·0,85·11³) = 18,039 m²; D = 4,7925 m
    # n = 6·11 / (π·4,7925) = 4,3836 1/s = 263,0 1/min; M = 5882,35 W / (2π·4,3836 1/s) = 213,57 N·m
    e = rotor.berechne(rotor.RotorEingaben())
    assert e.ergebnis("A").wert == pytest.approx(18.039, rel=0.01)
    assert e.ergebnis("D").wert == pytest.approx(4.7925, rel=0.01)
    assert e.ergebnis("n").wert == pytest.approx(263.0, rel=0.01)
    assert e.ergebnis("M").wert == pytest.approx(213.57, rel=0.01)
    assert e.alles_erfuellt


def test_energiebilanz_geht_auf():
    e = rotor.berechne(rotor.RotorEingaben(leistung_el_kw=10, wind_nenn_ms=12, cp=0.42, wirkungsgrad=0.9))
    p_wind = e.ergebnis("P_wind").wert
    assert p_wind * 0.42 * 0.9 == pytest.approx(10.0, rel=1e-9)


def test_doppelte_leistung_heisst_wurzel2_durchmesser():
    d5 = rotor.berechne(rotor.RotorEingaben(leistung_el_kw=5)).ergebnis("D").wert
    d10 = rotor.berechne(rotor.RotorEingaben(leistung_el_kw=10)).ergebnis("D").wert
    assert d10 / d5 == pytest.approx(math.sqrt(2))


def test_betz_grenze_wird_erkannt():
    e = rotor.berechne(rotor.RotorEingaben(cp=0.65))
    betz = [p for p in e.pruefungen if p.titel == "Betz-Grenze"][0]
    assert not betz.erfuellt
    assert not e.alles_erfuellt


def test_unsinnige_eingabe_verstaendlicher_fehler():
    with pytest.raises(rotor.EingabeFehler, match="Nennleistung"):
        rotor.berechne(rotor.RotorEingaben(leistung_el_kw=0))
