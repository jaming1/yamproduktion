"""Rotorblatt nach Blattelementmethode (K3) gegen Handrechnung und Glauert-Optimum prüfen."""
import math

import pytest

from yamproduktion.berechnungen import ARTEN, blatt_bem as bem


def glauert_cp(lam: float, n: int = 2000) -> float:
    """Höchster cp mit Drall nach Glauert, unabhängig von bem gerechnet.

    Optimum je Ring: λ_r² = (1−a)(4a−1)² / (1−3a),  a' = (1−3a)/(4a−1),
    cp = 8/λ² · ∫ a'(1−a) λ_r³ dλ_r  (Glauert 1935; Manwell/McGowan/Rogers: Wind Energy Explained, Kap. 3).
    Vergleichswerte der Tabelle dort: λ = 1 → 0,416; λ = 2 → 0,512; λ = 5 → 0,570.
    """
    def a_aus(x):
        lo, hi = 0.25, 1 / 3
        for _ in range(100):
            m = (lo + hi) / 2
            lo, hi = (m, hi) if (1 - m) * (4 * m - 1) ** 2 / (1 - 3 * m) < x * x else (lo, m)
        return (lo + hi) / 2

    summe = 0.0
    for i in range(n):
        x = (i + 0.5) * lam / n
        a = a_aus(x)
        summe += (1 - 3 * a) / (4 * a - 1) * (1 - a) * x**3 * lam / n
    return 8 / lam**2 * summe


def test_glauert_referenz_stimmt_mit_tabelle():
    assert glauert_cp(1) == pytest.approx(0.416, abs=0.002)
    assert glauert_cp(2) == pytest.approx(0.512, abs=0.002)
    assert glauert_cp(5) == pytest.approx(0.570, abs=0.002)


@pytest.mark.parametrize("lam", [4, 6, 8])
def test_ideales_schmitz_blatt_erreicht_glauert_optimum(lam):
    # Ohne Widerstand und Spitzenverlust muss das Schmitz-Blatt das theoretische Optimum (±1 %) erreichen
    e = bem.Eingaben(schnelllaufzahl=lam, gleitzahl=1e9, spitzenverlust=bem.OHNE_VERLUST, nabe_anteil=0.02,
                     elemente=60)
    cp = bem.nachrechnen(e, bem.blatt_auslegen(e), lam)["cp"]
    assert cp == pytest.approx(glauert_cp(lam), rel=0.01)
    assert cp < bem.BETZ_GRENZE


def test_schmitz_sehne_handrechnung():
    # r = 1,68 m, R = 2,4 m, λ = 6 → λ_r = 4,2; φ = ⅔·arctan(1/4,2) = ⅔·13,3925° = 8,9283°
    # c = 16·π·1,68 / (3·1,0) · sin²(4,4642°) = 28,149 · 0,0060584 = 0,17054 m
    assert math.degrees(bem.schmitz_winkel(4.2)) == pytest.approx(8.9283, rel=1e-4)
    assert bem.schmitz_sehne(1.68, 4.2, 3, 1.0) == pytest.approx(0.17054, rel=1e-3)


def test_standardbeispiel_kwa5():
    e = bem.berechne(bem.Eingaben())
    cp = e.ergebnis("cp").wert
    assert 0.40 <= cp <= 0.50            # realistische Spanne mit Widerstand und Spitzenverlust
    assert e.alles_erfuellt, [p.titel for p in e.pruefungen if not p.erfuellt]
    # Energiebilanz: P = cp · ½ρAv³ und P = ω·M
    radius = 2.4
    p_wind = 0.5 * 1.225 * math.pi * radius**2 * 11**3
    assert e.ergebnis("P_mech").wert * 1000 == pytest.approx(cp * p_wind, rel=1e-9)
    omega = 6 * 11 / radius
    assert e.ergebnis("P_mech").wert * 1000 == pytest.approx(omega * e.ergebnis("M").wert, rel=1e-9)
    # Blatt wird nach außen schmaler und weniger verwunden
    assert e.ergebnis("c_innen").wert > e.ergebnis("c_aussen").wert
    assert e.ergebnis("θ_innen").wert > e.ergebnis("θ_aussen").wert
    assert len(e.tabellen[0]["zeilen"]) == 20
    assert e.unbelegt and e.quellen
    # Kennlinie hat ihr Maximum in der Nähe der Auslegungsschnelllaufzahl
    xs, ys = e.diagramm["x"], e.diagramm["y"]
    assert 5 <= xs[ys.index(max(ys))] <= 7


def test_spitzenverlust_und_widerstand_senken_cp():
    ideal = bem.berechne(bem.Eingaben(gleitzahl=1e9, spitzenverlust=bem.OHNE_VERLUST)).ergebnis("cp").wert
    mit_widerstand = bem.berechne(bem.Eingaben(spitzenverlust=bem.OHNE_VERLUST)).ergebnis("cp").wert
    mit_beidem = bem.berechne(bem.Eingaben()).ergebnis("cp").wert
    assert ideal > mit_widerstand > mit_beidem


def test_feinere_teilung_aendert_wenig():
    grob = bem.berechne(bem.Eingaben(elemente=20)).ergebnis("cp").wert
    fein = bem.berechne(bem.Eingaben(elemente=60)).ergebnis("cp").wert
    assert grob == pytest.approx(fein, rel=0.01)


@pytest.mark.parametrize("lam,blattzahl,gleitzahl,nabe", [(1, 1, 5, 0.02), (2, 6, 200, 0.05), (12, 2, 60, 0.3),
                                                         (9, 3, 5, 0.02)])
def test_extreme_eingaben_rechnen_ueberall(lam, blattzahl, gleitzahl, nabe):
    e = bem.berechne(bem.Eingaben(schnelllaufzahl=lam, blattzahl=blattzahl, gleitzahl=gleitzahl, nabe_anteil=nabe,
                                  elemente=30))
    konvergiert = [p for p in e.pruefungen if p.titel.startswith("Rechnung")][0]
    assert konvergiert.erfuellt
    assert e.ergebnis("cp").wert <= bem.BETZ_GRENZE


def test_zu_kleines_cp_wird_gemeldet():
    e = bem.berechne(bem.Eingaben(cp_ziel=0.55))
    ziel = [p for p in e.pruefungen if p.titel.startswith("Leistungsbeiwert")][0]
    assert not ziel.erfuellt and "Profil" in ziel.hinweis


def test_verstaendliche_fehler():
    with pytest.raises(bem.EingabeFehler, match="Blätter"):
        bem.berechne(bem.Eingaben(blattzahl=2.5))
    with pytest.raises(bem.EingabeFehler, match="cA,max"):
        bem.berechne(bem.Eingaben(ca_max=0.8))


def test_ist_als_berechnungsart_registriert():
    art = ARTEN[bem.TYP]
    assert art["quellen"]["durchmesser_m"] == ("rotorauslegung", "D")
    assert art["berechne"](art["eingaben"]()).typ == bem.TYP
