"""MS5: Maschinenelemente — Welle, Lager, Schrauben, Passfeder, Pressverband, Schweißnaht, Getriebe, Turm, Bremse.

Prüfwerte: geschlossene Lösungen, Tabellenwerte und Handrechnungen (Lastenheft N5: Abweichung ≤ 1 %).
Wo ein Literatur-Rechenbeispiel (Roloff/Matek, Decker) noch fehlt, steht es im Test als offen.
"""
import math

import pytest

from yamproduktion import werkstoffe
from yamproduktion.berechnungen import (ARTEN, bremse, getriebe, lager, schrauben, schweissnaht, turm, welle,
                                       welle_nabe)
from yamproduktion.modell import Projekt


def test_alle_arten_rechnen_mit_standardwerten():
    for typ, art in ARTEN.items():
        e = art["berechne"](art["eingaben"]())
        assert e.typ == typ
        assert e.ergebnis(art["hauptergebnis"])
        assert e.quellen, typ


def test_maschinenelemente_standardbeispiel_erfuellt():
    """Das KWA-5-Beispiel ist so gewählt, dass alle Nachweise erfüllt sind."""
    for typ in ("welle", "lager", "schrauben", "passfeder", "pressverband", "schweissnaht", "getriebe", "turm", "bremse"):
        art = ARTEN[typ]
        e = art["berechne"](art["eingaben"]())
        assert e.alles_erfuellt, (typ, [p.titel for p in e.pruefungen if not p.erfuellt])


# ---------------------------------------------------------------- Welle
def test_welle_biegespannung_geschlossen():
    e = welle.berechne(welle.WelleEingaben(d_mm=60, m_b_d=2000))
    assert e.ergebnis("σ_b").wert == pytest.approx(32 * 2000e3 / (math.pi * 60**3), rel=1e-3)


def test_welle_durchbiegung_kragarm():
    """Durchbiegung am Kragende eines Trägers auf zwei Stützen: f = F·a²·(l + a)/(3EI)."""
    e = welle.berechne(welle.WelleEingaben(d_mm=80, masse_kg=100, a_m=0.3, l_m=0.5))
    F, a, l = 100 * 9.81, 300.0, 500.0
    I = math.pi * 80**4 / 64
    assert e.ergebnis("f").wert == pytest.approx(F * a**2 * (l + a) / (3 * 210000 * I), rel=1e-3)
    assert e.ergebnis("θ").wert == pytest.approx(F * a * l / (3 * 210000 * I) * 1000, rel=1e-3)


def test_welle_groesseneinfluss_ueber_tabellenbereich():
    assert welle.gueltig_bis_mm("+QT (vergütet), 40–100 mm") == 100
    assert welle.k1(150, 100, "Vergütungsstahl") < 1


# ---------------------------------------------------------------- Lager
def test_lager_lebensdauer_formel():
    """L10 = (C/P)³ für Kugellager, L10h = 10⁶·L10/(60·n)."""
    e = lager.berechne(lager.LagerEingaben())
    p_b = e.ergebnis("P_B").wert
    l10h = (30.7e3 / p_b) ** 3 * 1e6 / (60 * 263)
    assert e.ergebnis("L10h,B").wert == pytest.approx(l10h, rel=1e-6)


def test_lager_kraefte_gleichgewicht():
    """Fliegender Rotor: F_B = G·(l + a)/l, F_A = G·a/l (Momentengleichgewicht)."""
    e = lager.berechne(lager.LagerEingaben(masse_kg=45, a_m=0.3, l_m=0.4))
    G = 45 * 9.81
    assert e.ergebnis("F_rB").wert == pytest.approx(G * 0.7 / 0.4, rel=1e-6)
    assert e.ergebnis("F_rA").wert == pytest.approx(G * 0.3 / 0.4, rel=1e-6)


def test_lager_a1_iso281():
    assert lager.A1["90 %"] == 1.0 and lager.A1["99 %"] == pytest.approx(0.25)


# ---------------------------------------------------------------- Schrauben
def test_gewinde_spannungsquerschnitt_din13():
    """DIN 13: A_s = π/4·((d2 + d3)/2)²; M16 → 157 mm², M12 → 84,3 mm²."""
    assert schrauben.GEWINDE["M16"][1] == pytest.approx(157, rel=0.01)
    assert schrauben.GEWINDE["M12"][1] == pytest.approx(84.3, rel=0.01)


def test_vdi2230_montagevorspannkraft_m16_88():
    """VDI 2230 Tabelle A1, M16 8.8, μ_G = 0,12: F_M,zul ≈ 80,9 kN, M_A ≈ 210 N·m.
    Werte aus dem Gedächtnis, ungeprüft — Abgleich mit der Tabelle steht aus (siehe Bericht MS5)."""
    e = schrauben.berechne(schrauben.SchraubenEingaben(gewinde="M16", klasse="8.8"))
    assert e.ergebnis("F_Mzul").wert == pytest.approx(80.9e3, rel=0.01)
    assert e.ergebnis("M_A").wert == pytest.approx(210, rel=0.02)


# ---------------------------------------------------------------- Welle-Nabe
def test_passfeder_handrechnung():
    """d = 80 → DIN 6885: 22 × 14, t1 = 9;  p = 2T/(d·(h − t1)·(l − b))."""
    e = welle_nabe.berechne_passfeder(welle_nabe.PassfederEingaben(d_mm=80, t_nm=1290, l_mm=90))
    assert welle_nabe.passfeder(80) == (22, 14, 9)
    assert e.ergebnis("p").wert == pytest.approx(2 * 1290e3 / (80 * 5 * 68), rel=1e-6)


def test_pressverband_lame():
    """Vollwelle, gleiche E-Module: p = ξ·E·(1 − Q²)/2;  Q = 0,5, Ü_w = 62 µm, d = 80 → p = 61,0 MPa."""
    e = welle_nabe.berechne_press(welle_nabe.PressEingaben(d_f=80, d_a=160, ueber_um=70, rz_w=4, rz_n=6))
    xi = 62e-3 / 80
    p = xi * 210000 * (1 - 0.25) / 2
    assert e.ergebnis("p_F").wert == pytest.approx(p, rel=1e-6)
    assert e.ergebnis("T_ü").wert == pytest.approx(p * math.pi * 80**2 * 80 * 0.12 / 2 / 1000, rel=1e-6)


# ---------------------------------------------------------------- Schweißnaht
def test_schweissnaht_reine_torsion():
    """Nur Torsion: τ_∥ = T/W_t, σ_v = √3·τ_∥."""
    e = schweissnaht.berechne(schweissnaht.NahtEingaben(m_nm=0, n_n=0, q_n=0, t_nm=5000))
    D, a = 406.4, 7.0
    W = math.pi / 32 * ((D + 2 * a) ** 4 - D**4) / (D + 2 * a)
    tau = 5000e3 / (2 * W)
    assert e.ergebnis("τ_∥").wert == pytest.approx(tau, rel=1e-9)
    assert e.ergebnis("σ_v").wert == pytest.approx(math.sqrt(3) * tau, rel=1e-9)


def test_schweissnaht_grenzwert_eurocode():
    """S355: f_u = 470, β_w = 0,9, γ_M2 = 1,25 → 417,8 MPa (DIN EN 1993-1-8)."""
    e = schweissnaht.berechne(schweissnaht.NahtEingaben())
    assert e.ergebnis("σ_w,Rd").wert == pytest.approx(470 / (0.9 * 1.25), rel=1e-9)


# ---------------------------------------------------------------- Getriebe
def test_profilueberdeckung_z20_z20():
    """DIN 3960: z1 = z2 = 20, α = 20°, ohne Profilverschiebung → ε_α = 1,557."""
    assert getriebe.ueberdeckung(1, 20, 20, 20) == pytest.approx(1.557, abs=1e-3)


def test_zonenfaktor_20_grad():
    """DIN 3990: Z_H = 2,495 für α = 20°, β = 0, x = 0."""
    assert getriebe.z_h(20) == pytest.approx(2.495, abs=1e-3)


def test_planetenstufe_willis_und_montage():
    e = getriebe.berechne(getriebe.GetriebeEingaben(z1=21, z2=30, n_p=3))
    assert e.ergebnis("z_H").wert == 81
    assert e.ergebnis("i").wert == pytest.approx(1 + 81 / 21)
    assert all(p.erfuellt for p in e.pruefungen if p.titel == "Montagebedingung")
    e = getriebe.berechne(getriebe.GetriebeEingaben(z1=20, z2=30, n_p=3))   # (20 + 80)/3 nicht ganzzahlig
    assert not next(p for p in e.pruefungen if p.titel == "Montagebedingung").erfuellt


def test_stirnrad_flankenpressung_handrechnung():
    e = getriebe.berechne(getriebe.GetriebeEingaben(bauart=getriebe.BAUARTEN[0], m_n=3, z1=20, z2=60, b_mm=40,
                                                    t_r=900, k_a=1.0, k_v=1.0))   # T1 = 900/3 = 300 N·m
    d1, u = 60.0, 3.0
    Ft = 2 * 300e3 / d1
    eps = getriebe.ueberdeckung(3, 20, 60, 20)
    sh = 189.8 * 2.4946 * math.sqrt((4 - eps) / 3) * math.sqrt(Ft * (u + 1) / (d1 * 40 * u))
    assert e.ergebnis("σ_H").wert == pytest.approx(sh, rel=1e-3)
    assert e.ergebnis("i").wert == pytest.approx(3)


# ---------------------------------------------------------------- Turm & Fundament
def test_turm_spannung_und_flansch():
    e = turm.berechne(turm.TurmEingaben())
    D, t = 406.4, 10.0
    W = math.pi / 32 * (D**4 - (D - 2 * t) ** 4) / D
    M_d = e.ergebnis("M_d").wert
    assert e.ergebnis("F_A,Schraube").wert == pytest.approx(4 * M_d * 1000 / (16 * 480), rel=1e-9)
    N_d = e.ergebnis("N_d").wert
    A = math.pi / 4 * (D**2 - (D - 2 * t) ** 2)
    assert e.ergebnis("σ_d").wert == pytest.approx(M_d * 1000 / W + N_d / A, rel=1e-9)


def test_turm_eigenfrequenz_kragtraeger():
    """Ohne Turmmasse-Anteil: f0 = 1/(2π)·√(3EI/(m·H³)). Probe über sehr leichte Wand und große Kopfmasse."""
    e = turm.berechne(turm.TurmEingaben(m_kopf=1e5, t_mm=2, d_mm=400))
    I = math.pi / 64 * (400**4 - 396**4) * 1e-12
    m_t = 7850 * math.pi / 4 * (400**2 - 396**2) * 1e-6 * 12
    f0 = 1 / (2 * math.pi) * math.sqrt(3 * 210e9 * I / ((1e5 + 0.24 * m_t) * 12**3))
    assert e.ergebnis("f0").wert == pytest.approx(f0, rel=1e-9)


def test_fundament_trapez_und_klaffend():
    """e ≤ a/6: σ = N/a²·(1 + 6e/a);  e > a/6: σ = 2N/(3a·(a/2 − e))."""
    e = turm.berechne(turm.TurmEingaben(a_m=4.0, hf_m=1.5))
    ex = e.ergebnis("e").wert
    assert ex <= 4 / 6
    M_F = next(s.ergebnis.wert for s in e.schritte if s.ergebnis.symbol == "M_F")
    N = M_F / ex                                     # Normalkraft aus Ausmitte zurückgerechnet
    assert e.ergebnis("σ_Boden").wert == pytest.approx(N / 16 * (1 + 6 * ex / 4) / 1000, rel=1e-9)
    e = turm.berechne(turm.TurmEingaben(a_m=2.4, hf_m=1.0))
    ex = e.ergebnis("e").wert
    M_F = next(s.ergebnis.wert for s in e.schritte if s.ergebnis.symbol == "M_F")
    N = M_F / ex
    assert 2.4 / 6 < ex < 2.4 / 3
    assert e.ergebnis("σ_Boden").wert == pytest.approx(2 * N / (3 * 2.4 * (1.2 - ex)) / 1000, rel=1e-9)


def test_turm_resonanz_wird_erkannt():
    e = turm.berechne(turm.TurmEingaben())
    f0 = e.ergebnis("f0").wert
    e = turm.berechne(turm.TurmEingaben(n_rpm=f0 * 60))
    assert not next(p for p in e.pruefungen if p.titel == "Eigenfrequenz nicht bei 1P").erfuellt


# ---------------------------------------------------------------- Bremse
def test_bremse_energiebilanz():
    """Arbeit der Bremse = kinetische Energie + Arbeit des Rotormoments: M_Br·φ = ½Jω² + Q·φ."""
    e = bremse.berechne(bremse.BremsEingaben())
    w = 2 * math.pi * 395 / 60
    t = 120 * w / (800 - 190)
    assert e.ergebnis("t_Br").wert == pytest.approx(t, rel=1e-9)
    phi = e.ergebnis("U").wert * 2 * math.pi
    assert e.ergebnis("E").wert * 1000 == pytest.approx(800 * phi, rel=1e-9)


def test_bremse_zu_schwach():
    with pytest.raises(ValueError):
        bremse.berechne(bremse.BremsEingaben(m_br=100, q_nm=190))


# ---------------------------------------------------------------- Werkstoffe und Kette
def test_neuer_werkstoff_42crmo4_gross():
    w = werkstoffe.werkstoff("42CrMo4", "40–100")
    assert w["re"] == 650 and w["beleg"] == "Norm, ungeprüft"


def test_kette_lasten_turm_schrauben_schweissnaht(tmp_path):
    """Werte fließen über gespeicherte Berechnungen: Lasten → Turm → Flanschschrauben und Fußnaht."""
    p = Projekt.neu(tmp_path / "K", "K", "", beispiel_kwa=True)
    werte = {}
    for typ in ("rotorauslegung", "lasten_iec", "turm", "schrauben", "schweissnaht"):
        art = ARTEN[typ]
        eingaben = art["eingaben"]()
        for feld, (quelle_typ, symbol) in art["quellen"].items():
            if quelle_typ in werte:
                setattr(eingaben, feld, werte[quelle_typ][symbol])
        e = art["berechne"](eingaben)
        werte[typ] = {g.symbol: g.wert for g in e.eingaben + e.ergebnisse}
    assert werte["schrauben"]["F_A"] == pytest.approx(werte["turm"]["F_A,Schraube"])
    assert werte["schrauben"]["n"] == werte["turm"]["n_S"]
    assert werte["schweissnaht"]["M"] == pytest.approx(werte["turm"]["M_d"])
    assert werte["turm"]["F_x,k"] == pytest.approx(werte["lasten_iec"]["F_x,k"])
    p.schliessen()
