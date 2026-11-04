"""MS4: Rotorschub, Leistungskurve/Ertrag, Lastannahmen IEC 61400-2, Antriebsstrang, Werkstoffe.

Prüfwerte aus der Literatur bzw. geschlossenen Lösungen (Lastenheft N5: Abweichung ≤ 1 %).
"""
import math

import pytest

from yamproduktion import werkstoffe
from yamproduktion.berechnungen import antrieb, ertrag, lasten, rotor
from yamproduktion.modell import NEU_PRUEFEN, Projekt, ProjektFehler


# ---------------------------------------------------------------- Rotor
def test_betz_optimum_induktion_und_schub():
    """Impulstheorie: bei cp = 16/27 ist a = 1/3 und cT = 8/9 (Betz)."""
    assert rotor.induktion_aus_cp(16 / 27) == pytest.approx(1 / 3, rel=1e-6)
    e = rotor.berechne(rotor.RotorEingaben(cp=16 / 27))
    assert e.ergebnis("cT").wert == pytest.approx(8 / 9, rel=1e-6)
    a = e.ergebnis("A").wert
    assert e.ergebnis("T").wert == pytest.approx(0.5 * 1.225 * a * 11**2 * 8 / 9, rel=1e-6)


def test_schub_bei_cp_040():
    # cp = 0,40 → a = 0,1199 (aus 4a(1−a)² = 0,4), cT = 4a(1−a) = 0,4221
    a = rotor.induktion_aus_cp(0.40)
    assert 4 * a * (1 - a) ** 2 == pytest.approx(0.40, rel=1e-9)
    assert 4 * a * (1 - a) == pytest.approx(0.4609, abs=5e-4)


# ---------------------------------------------------------------- Ertrag
def test_rayleigh_energiemusterfaktor():
    """Rayleigh: Mittelwert von v³ = (6/π)·v̄³ (Gasch/Twele, Hau)."""
    v_m = 5.0
    c = v_m / math.gamma(1.5)
    assert ertrag.mittelwert(lambda v: v**3, c, 2.0) == pytest.approx(6 / math.pi * v_m**3, rel=0.01)


def test_weibull_drittes_moment():
    """Weibull: Mittelwert von v³ = c³·Γ(1 + 3/k)."""
    c, k = 7.0, 1.8
    assert ertrag.mittelwert(lambda v: v**3, c, k, v_max=80) == pytest.approx(c**3 * math.gamma(1 + 3 / k), rel=0.01)


def test_skalenparameter_rayleigh():
    # v̄ = 6 m/s, k = 2 → c = 6 / Γ(1,5) = 6 / 0,8862 = 6,770 m/s
    e = ertrag.berechne(ertrag.ErtragEingaben(v_mess=6.0, h_mess=10, h_nabe=10))
    assert e.ergebnis("c").wert == pytest.approx(6.770, abs=0.001)


def test_ertrag_ohne_begrenzung_gleich_analytisch():
    e_in = ertrag.ErtragEingaben(durchmesser_m=5, leistung_nenn_kw=100, v_ein=0.5, v_ab=40, v_mess=5,
                                 h_mess=10, h_nabe=10, verfuegbarkeit=1.0)
    e = ertrag.berechne(e_in)
    flaeche = math.pi * 25 / 4
    erwartet = 0.5 * 1.225 * flaeche * 0.40 * 0.85 * 6 / math.pi * 125 / 1000   # kW
    assert e.ergebnis("P_m").wert == pytest.approx(erwartet, rel=0.01)
    assert e.ergebnis("E").wert == pytest.approx(erwartet * 8760, rel=0.01)


def test_hellmann_und_kennzahlen():
    e = ertrag.berechne(ertrag.ErtragEingaben(v_mess=4.5, h_mess=10, h_nabe=20, hellmann=0.2))
    assert e.ergebnis("v_N").wert == pytest.approx(4.5 * 2**0.2, rel=1e-9)
    ein = ertrag.ErtragEingaben()
    r = ertrag.berechne(ein)
    assert r.ergebnis("t_VL").wert == pytest.approx(r.ergebnis("E").wert / 5, rel=1e-9)
    assert r.tabellen[0]["zeilen"][24][0] == 25
    assert max(r.diagramm["y"]) == pytest.approx(5.0)


def test_ertrag_eingabefehler():
    with pytest.raises(ertrag.EingabeFehler, match="Einschalt"):
        ertrag.berechne(ertrag.ErtragEingaben(v_ein=30, v_ab=25))


# ---------------------------------------------------------------- Lasten
def test_lastfall_d_und_h_handrechnung():
    e = lasten.berechne(lasten.LastEingaben(klasse="III", durchmesser_m=4.8, blattzahl=3, flaeche_blatt_m2=0.45))
    zeilen = {(z[0], z[2]): z[3] for z in e.tabellen[0]["zeilen"]}
    # D: F = C_T·½·ρ·A·(2,5·V_ave)², V_ave = 0,2·37,5 = 7,5 m/s
    f_d = 0.5 * 0.5 * 1.225 * math.pi * 2.4**2 * (2.5 * 7.5) ** 2
    assert zeilen[("D", "F_x-shaft")] == pytest.approx(f_d, abs=0.1)
    assert f_d == pytest.approx(1948.3, abs=0.1)   # Handrechnung: 0,25·1,225·18,096·351,56
    # H: F = B·C_d·½·ρ·V_e50²·A_proj,B, V_e50 = 1,4·37,5 = 52,5 m/s
    f_h = 3 * 1.5 * 0.5 * 1.225 * 52.5**2 * 0.45
    assert zeilen[("H", "F_x-shaft")] == pytest.approx(f_h, abs=0.1)
    assert e.ergebnis("F_x,d").wert == pytest.approx(3.0 * max(f_d, f_h), rel=1e-9)
    assert e.ergebnis("V_e50").wert == pytest.approx(52.5)


def test_lastfall_a_handrechnung():
    q, lam, R = 215.0, 6.0, 2.4
    e = lasten.berechne(lasten.LastEingaben(durchmesser_m=2 * R, moment_nm=q, schnelllaufzahl=lam, blattzahl=3,
                                            rotormasse_kg=45, l_rb_m=0.3))
    z = {(r[0], r[2]): r[3] for r in e.tabellen[0]["zeilen"]}
    df = 1.5 * lam * q / R
    assert z[("A", "ΔF_x-shaft")] == pytest.approx(df, abs=0.1)
    assert z[("A", "ΔM_yB")] == pytest.approx(lam * q / 3, abs=0.1)
    assert z[("A", "ΔM_shaft")] == pytest.approx(2 * 45 * 9.81 * 0.3 + R / 6 * df, abs=0.1)
    assert z[("A", "ΔM_x-shaft")] == pytest.approx(q + 2 * 45 * 9.81 * 0.005 * R, abs=0.1)


def test_giergeschwindigkeit():
    klein = lasten.berechne(lasten.LastEingaben(durchmesser_m=1.5))      # A = 1,77 m² ≤ 2
    gross = lasten.berechne(lasten.LastEingaben(durchmesser_m=4.8))      # A = 18,1 m²
    w = lambda e: next(s.ergebnis.wert for s in e.schritte if s.ergebnis.symbol == "ω_yaw")  # noqa: E731
    assert w(klein) == 3.0
    assert w(gross) == pytest.approx(3 - 0.01 * (math.pi * 2.4**2 - 2), rel=1e-9)


def test_lasten_unbelegt_gekennzeichnet():
    e = lasten.berechne(lasten.LastEingaben())
    assert any("Lastfall E" in u for u in e.unbelegt)
    assert {z[7] for z in e.tabellen[0]["zeilen"] if z[0] in ("E", "F")} == {"unbelegt"}


def test_lasten_eingabefehler():
    with pytest.raises(lasten.EingabeFehler, match="Rotormasse"):
        lasten.berechne(lasten.LastEingaben(blattmasse_kg=20, rotormasse_kg=30))


# ---------------------------------------------------------------- Antrieb
def test_direktantrieb_polpaarzahl():
    e = antrieb.berechne(antrieb.AntriebEingaben(drehzahl_rotor=263.0, frequenz_hz=50))
    assert e.ergebnis("p").wert == math.ceil(60 * 50 / 263)          # 12
    assert e.ergebnis("η_ges").wert == pytest.approx(0.90 * 0.95)
    p_r = 5000 / (0.90 * 0.95)
    assert e.ergebnis("M_R").wert == pytest.approx(p_r / (2 * math.pi * 263 / 60), rel=1e-9)


def test_getriebe():
    e = antrieb.berechne(antrieb.AntriebEingaben(bauart=antrieb.BAUARTEN[1], drehzahl_rotor=250, drehzahl_gen=1500))
    assert e.ergebnis("i").wert == pytest.approx(6.0)
    assert e.ergebnis("z").wert == 1
    m_r = e.ergebnis("M_R").wert
    assert e.ergebnis("M_Gen").wert == pytest.approx(m_r * 0.96 / 6)
    e2 = antrieb.berechne(antrieb.AntriebEingaben(bauart=antrieb.BAUARTEN[1], drehzahl_rotor=100, drehzahl_gen=1500))
    assert e2.ergebnis("z").wert == 2


def test_wirkungsgrad_abgleich_mit_rotor():
    e = antrieb.berechne(antrieb.AntriebEingaben(eta_rotor_annahme=0.70))
    assert not e.pruefungen[0].erfuellt
    assert "neu rechnen" in e.pruefungen[0].hinweis


# ---------------------------------------------------------------- Werkstoffe
def test_werkstoffe():
    assert len(werkstoffe.alle()) >= 12
    w = werkstoffe.werkstoff("S235JR")
    assert (w["re"], w["e"], w["dichte"]) == (235, 210, 7850)
    assert any(x["name"] == "42CrMo4" for x in werkstoffe.suchen("welle"))
    assert all(x["gruppe"] == "Aluminium" for x in werkstoffe.suchen("aluminium"))
    with pytest.raises(KeyError):
        werkstoffe.werkstoff("Unobtainium")


# ---------------------------------------------------------------- Kette Anforderung → Rotor → Ertrag/Lasten
def test_kette_neu_rechnen_in_reihenfolge(tmp_path):
    p = Projekt.neu(tmp_path / "K", "KWA", beispiel_kwa=True)
    leistung = p.anforderung_suchen("nennleistung")
    re = rotor.RotorEingaben()
    r = p.berechnung_speichern(rotor.berechne(re).als_dict(), re.__dict__, {"leistung_el_kw": leistung.id})
    d = r.ergebnis["ergebnisse"][0]["wert"]
    ee = ertrag.ErtragEingaben(durchmesser_m=d)
    e = p.berechnung_speichern(ertrag.berechne(ee).als_dict(), ee.__dict__,
                               {"durchmesser_m": ("berechnung", r.id), "leistung_nenn_kw": leistung.id})
    assert {b.nr for b in p.haengt_ab_von("berechnung", e.id)} == {"A-001", r.nr}
    ertrag_alt = e.ergebnis["ergebnisse"][0]["wert"]

    p.anforderung_aendern(leistung.id, zielwert=10)
    assert p.berechnung(r.id).status == NEU_PRUEFEN
    assert p.berechnung(e.id).status == NEU_PRUEFEN
    with pytest.raises(ProjektFehler, match="Zuerst B-001"):
        p.berechnung_neu_rechnen(e.id)
    assert p.berechnungen_in_reihenfolge([e.id, r.id]) == [r.id, e.id]
    p.berechnung_neu_rechnen(r.id)
    neu = p.berechnung_neu_rechnen(e.id)
    d_neu = p.berechnung(r.id).ergebnis["ergebnisse"][0]["wert"]
    assert neu.eingaben["durchmesser_m"] == pytest.approx(d_neu)
    assert neu.eingaben["leistung_nenn_kw"] == 10
    assert neu.ergebnis["ergebnisse"][0]["wert"] > ertrag_alt * 1.5
    assert p.neu_zu_pruefen() == []
