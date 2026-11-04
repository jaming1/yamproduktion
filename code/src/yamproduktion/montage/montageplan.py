"""Montageplan (Lastenheft M38, M39, S11): Reihenfolge, Teile, Werkzeuge, Anzugsmomente, Prüfschritte.

Ein Montageplan gehört zu einer Baugruppe und ist ein JSON-Wörterbuch (wie Arbeitsplan, E20):

    {"vorrichtung": 7,                         # Teil-id der Montageplatte (oder None)
     "schritte": [{"nr": 1, "titel": "…", "text": "…", "einbauten": ["E2"], "werkzeuge": ["…"],
                   "momente": [{"was": "12× ISO 4017 M16x60", "wert": 210.0, "quelle": "…"}],
                   "pruefung": ["…"], "zeit": 20.0}],
     "hinweise": ["…"]}

Der Vorschlag ordnet die Einbauten nach Montagelogik: Vorrichtung → Grundteil → Passfedern → Lager → weitere
Bauteile → Scheiben → Schrauben → Muttern → Endkontrolle. Alles ist danach von Hand änderbar.
Anzugsmomente kommen aus einer passenden Schraubenberechnung des Projekts, sonst aus derselben Formel
(VDI 2230 vereinfacht) für Festigkeitsklasse 8.8 – als Richtwert gekennzeichnet.
Temperaturen und Zeiten sind Richt- bzw. Schätzwerte.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field

import numpy as np

from ..berechnungen import schrauben as S
from ..berechnungen.basis import formatiere as f
from ..cad import normteile
from ..cad.baugruppe import bewegen
from ..cad.geometrie import eigenschaften

ALPHA_STAHL = 11e-6           # 1/K Wärmeausdehnung Stahl/Guss – Richtwert
FUEGESPIEL = 0.001            # Fügespiel beim Schrumpfen ≈ 0,001·d_F – Richtwert
RAUM = 20.0                   # °C
LAGER_T = 110                 # °C Anwärmtemperatur Wälzlager – Herstellerrichtwert (höchstens 120 °C), ungeprüft
HEBEZEUG_AB = 20.0            # kg – darüber Hebezeug verwenden (Richtwert Arbeitsschutz, Einzelperson)
DREHMOMENTSCHLUESSEL = ((5, 25), (20, 100), (40, 200), (60, 340), (100, 500), (200, 800), (300, 1500))
HINWEIS = ("Anwärmtemperaturen, Fügespiel, Planlauf-Grenzen und Zeiten sind Richt- bzw. Schätzwerte, ungeprüft. "
           "Anzugsmomente ohne passende Schraubenberechnung: Richtwert nach VDI 2230 (vereinfacht), 8.8, "
           "µ_G = µ_K = 0,12 – vor der Montage mit der Berechnung bzw. dem Hersteller abgleichen.")
RICHTWERT_MOMENT = "Richtwert VDI 2230 (vereinfacht): 8.8, µ_G = µ_K = 0,12, ν = 0,9 – ungeprüft"


@dataclass
class Umfeld:
    """Was das Projekt zur Montage weiß (wird von modell.py gefüllt)."""
    teile: dict = field(default_factory=dict)          # teil_id → dict(vorlage, name, nr, parameter, masse)
    schrauben: list = field(default_factory=list)      # [dict(nr, gewinde, klasse, m_a)]
    pressverband: dict | None = None                   # dict(nr, d_f mm, ue mm)
    vorrichtung: dict | None = None                    # dict(id, nr, name)


def normteil_art(norm: str) -> str:
    if norm.startswith("ISO 4762"):
        return "schraube_is"
    if norm.startswith("ISO 4017"):
        return "schraube_sk"
    if norm.startswith("ISO 4032"):
        return "mutter"
    if norm.startswith("ISO 7089"):
        return "scheibe"
    if norm.startswith("DIN 6885"):
        return "passfeder"
    if norm in normteile.LAGER:
        return "lager"
    return ""


def _gewinde(norm: str) -> int | None:
    m = re.search(r"M(\d+)", norm)
    return int(m.group(1)) if m else None


def schluesselweite(norm: str) -> float | None:
    d = _gewinde(norm)
    art = normteil_art(norm)
    if art == "schraube_is":
        return normteile.ISO_4762.get(d, (None, None, None))[2]
    if art == "schraube_sk":
        return normteile.ISO_4017.get(d, (None, None))[0]
    if art == "mutter":
        return normteile.ISO_4032.get(d, (None, None))[0]
    return None


def drehmomentschluessel(m_a: float) -> str:
    for lo, hi in DREHMOMENTSCHLUESSEL:
        if lo <= m_a <= 0.9 * hi:
            return f"Drehmomentschlüssel {lo}–{hi} N·m"
    return f"Drehmomentschlüssel für {f(m_a)} N·m (Sonderbereich)"


def anzugsmoment(norm: str, schrauben: list) -> tuple[float | None, str, str]:
    """(M_A in N·m, Quelle, Hinweis). Normteile sind Festigkeitsklasse 8.8 (normteile.py)."""
    from ..cad.vorlagen import durchgangsloch
    d = _gewinde(norm)
    gewinde = f"M{d}"
    passend = next((b for b in schrauben if b["gewinde"] == gewinde and b["klasse"] == "8.8" and b.get("m_a")), None)
    if passend:
        return passend["m_a"], f"aus {passend['nr']} (Schraubenberechnung)", ""
    hinweis = ""
    andere = next((b for b in schrauben if b["gewinde"] == gewinde), None)
    if andere:
        hinweis = (f"{andere['nr']} rechnet {gewinde} in Festigkeitsklasse {andere['klasse']}, eingebaut sind "
                   f"Normteile 8.8 – Klasse angleichen (Anzugsmoment hier für 8.8).")
    if gewinde not in S.GEWINDE:
        return None, "", f"Für {gewinde} ist kein Gewinde hinterlegt – Anzugsmoment von Hand eintragen."
    p, a_s = S.GEWINDE[gewinde]
    kopf = schluesselweite(norm) or 1.5 * d
    if normteil_art(norm) == "schraube_is":
        kopf = normteile.ISO_4762[d][0]
    d_km = (kopf + durchgangsloch(d)) / 2
    fm = S.f_m_zul(d, p, a_s, S.rp02("8.8", d), 0.12)
    d2 = d - 0.6495 * p
    m_a = fm * (0.16 * p + 0.58 * d2 * 0.12 + d_km / 2 * 0.12) / 1000
    return round(m_a), RICHTWERT_MOMENT, hinweis


def fuegetemperatur(d_f: float, ue_mm: float) -> tuple[float, str]:
    """Schrumpfen: ΔT = (Ü + Fügespiel)/(α·d_F). Liefert (Temperatur °C, Rechenweg)."""
    spiel = FUEGESPIEL * d_f
    dT = (ue_mm + spiel) / (ALPHA_STAHL * d_f)
    T = math.ceil((RAUM + dT) / 5) * 5
    weg = (f"ΔT = (Ü + Fügespiel)/(α·d_F) = ({f(ue_mm * 1000)} µm + {f(spiel * 1000)} µm)/"
           f"(11·10⁻⁶ 1/K · {f(d_f)} mm) = {f(dT)} K → {T:g} °C")
    return T, weg


def basis_einbau(definition: dict) -> str | None:
    """Grundteil: Einbau ohne Verknüpfung, auf den sich die meisten anderen beziehen."""
    einbauten = definition.get("einbauten", [])
    if not einbauten:
        return None
    ziele = Counter(e["bezug"]["ziel"] for e in einbauten if e.get("bezug") and e["bezug"].get("ziel"))
    frei = [e for e in einbauten if not (e.get("bezug") and e["bezug"].get("ziel"))] or einbauten
    return max(frei, key=lambda e: (ziele.get(e["id"], 0), e.get("art") == "teil", -einbauten.index(e)))["id"]


_RANG = {"passfeder": 2, "lager": 3, "teil": 4, "scheibe": 5, "schraube_sk": 6, "schraube_is": 6, "mutter": 7, "": 4}


def _schritt(titel: str, text: str, einbauten=(), werkzeuge=(), pruefung=(), zeit=5.0, momente=()) -> dict:
    return {"titel": titel, "text": text, "einbauten": list(einbauten), "werkzeuge": list(werkzeuge),
            "momente": list(momente), "pruefung": list(pruefung), "zeit": float(zeit)}


VORRICHTUNG_TITEL = "Montageplatte bereitstellen"
AUFLAGE_PLATTE = "in die Auflagen der Montageplatte legen und mit Spanngurt sichern"
AUFLAGE_PRISMA = "in zwei Prismen auf einer ebenen Unterlage ablegen und gegen Wegrollen sichern"


def vorrichtung_umstellen(plan: dict, v: dict | None) -> dict:
    """Vorrichtung nachträglich setzen oder entfernen: erster Schritt und Text des Grundteil-Schritts passen sich an,
    alle anderen Änderungen im Plan bleiben erhalten."""
    schritte = plan.setdefault("schritte", [])
    hat = bool(schritte) and schritte[0]["titel"] == VORRICHTUNG_TITEL and not schritte[0]["einbauten"]
    if hat:
        schritte.pop(0)
    if v:
        schritte.insert(0, vorrichtung_schritt(v))
    alt, neu = (AUFLAGE_PRISMA, AUFLAGE_PLATTE) if v else (AUFLAGE_PLATTE, AUFLAGE_PRISMA)
    for s in schritte:
        if alt in s.get("text", ""):
            s["text"] = s["text"].replace(alt, neu)
            if v and "Spanngurt" not in s["werkzeuge"]:
                s["werkzeuge"].append("Spanngurt")
            elif not v and "Spanngurt" in s["werkzeuge"]:
                s["werkzeuge"].remove("Spanngurt")
    plan["vorrichtung"] = v["id"] if v else None
    return nummerieren(plan)


def vorrichtung_schritt(v: dict) -> dict:
    return _schritt(
        VORRICHTUNG_TITEL,
        f"Montageplatte {v['nr']} „{v['name']}“ auf Werkbank oder Nutentisch mit 4 Schrauben M16 befestigen. "
        "Auflagen säubern und mit Kunststoffstreifen (z. B. PE) belegen, damit keine Sitzflächen beschädigt werden.",
        werkzeuge=["Ringschlüssel SW 24", "Wasserwaage"],
        pruefung=["Platte liegt eben und fest (Wasserwaage)", "Auflagen sauber und belegt"], zeit=15)


def vorschlag(definition: dict, erg, umfeld: Umfeld) -> dict:
    """Montageplan aus einer gebauten Baugruppe vorschlagen (`erg` = cad.baugruppe.Ergebnis)."""
    einbauten = {e["id"]: e for e in definition.get("einbauten", [])}
    anzahl = Counter(x.einbau for x in erg.exemplare)
    basis = basis_einbau(definition)
    hinweise: list[str] = []
    schritte: list[dict] = []
    v = umfeld.vorrichtung

    def masse_teil(e) -> float:
        if e["art"] == "teil":
            return float(umfeld.teile.get(int(e["teil_id"]), {}).get("masse") or 0.0)
        try:
            return normteile.erzeugen(e["norm"]).masse
        except Exception:
            return 0.0

    def name(e) -> str:
        if e["art"] == "teil":
            t = umfeld.teile.get(int(e["teil_id"]), {})
            return f"{t.get('name') or e.get('name', '')} ({t.get('nr', '')})"
        return e["norm"]

    def heben(e, n=1) -> list[str]:
        return ["Hebezeug mit Rundschlinge"] if masse_teil(e) * n > HEBEZEUG_AB else []

    def last(e, n=1) -> str:
        m = masse_teil(e) * n
        return f" Masse ≈ {f(m)} kg – mit Hebezeug anheben." if m > HEBEZEUG_AB else ""

    if v:
        schritte.append(vorrichtung_schritt(v))
    if basis:
        e = einbauten[basis]
        auflage = AUFLAGE_PLATTE if v else AUFLAGE_PRISMA
        schritte.append(_schritt(
            f"Grundteil {name(e)} einlegen",
            f"{name(e)} {auflage}.{last(e)} Sitzflächen reinigen, entgraten und auf Beschädigungen prüfen.",
            einbauten=[basis], werkzeuge=heben(e) + ["Spanngurt"] if v else heben(e),
            pruefung=["Sitzflächen sauber, gratfrei, unbeschädigt",
                      "Lager- und Nabensitze nach Zeichnung gemessen (Bügelmessschraube)"], zeit=10))
        t = umfeld.teile.get(int(e["teil_id"]), {}) if e["art"] == "teil" else {}
        if t.get("vorlage") == "welle" and float(t.get("parameter", {}).get("l_pf", 0) or 0) > 0 and not any(
                x.get("art") == "normteil" and normteil_art(x["norm"]) == "passfeder" for x in einbauten.values()):
            hinweise.append("Die Welle hat eine Passfedernut, die Passfeder fehlt aber in der Baugruppe – als "
                            "Normteil DIN 6885 ergänzen.")

    rest = [e for eid, e in einbauten.items() if eid != basis]
    rest.sort(key=lambda e: (_RANG["teil"] if e["art"] == "teil" else _RANG[normteil_art(e["norm"])],
                             list(einbauten).index(e["id"])))
    for e in rest:
        n = anzahl.get(e["id"], 1)
        mal = f"{n}× " if n > 1 else ""
        if e["art"] == "teil":
            t = umfeld.teile.get(int(e["teil_id"]), {})
            par = t.get("parameter", {})
            pv = umfeld.pressverband
            if t.get("vorlage") == "nabe" and pv and abs(float(par.get("d_f", 0)) - pv["d_f"]) < 0.5:
                T, weg = fuegetemperatur(pv["d_f"], pv["ue"])
                nut = " Nabennut vorher zur Passfeder ausrichten." if par.get("mit_nut") == "ja" else ""
                schritte.append(_schritt(
                    f"{name(e)} warm aufschrumpfen",
                    f"Nabe im Ofen oder mit Induktion gleichmäßig auf {T:g} °C erwärmen (Fügetemperatur aus "
                    f"{pv['nr']}: {weg}; Fügespiel 0,001·d_F und α sind Richtwerte). Fügeflächen trocken und "
                    f"fettfrei.{nut} Nabe zügig bis zur Anlage aufschieben und bis zum Abkühlen andrücken.{last(e)}",
                    einbauten=[e["id"]],
                    werkzeuge=["Ofen oder Induktionsheizung", "Temperaturmessstift", "Hitzeschutzhandschuhe"] + heben(e),
                    pruefung=["Nabe liegt an der Wellenschulter an (Fühlerlehre 0,05 mm, nach dem Abkühlen)",
                              "Planlauf der Blattscheibe ≤ 0,1 mm (Messuhr, Richtwert)"], zeit=30))
            elif t.get("vorlage") == "nabe":
                schritte.append(_schritt(
                    f"{name(e)} aufschieben",
                    "Nabe auf den Nabensitz schieben (Passung laut Zeichnung), Nut zur Passfeder ausrichten. Ohne "
                    "Pressverband-Berechnung im Projekt ist keine Fügetemperatur bekannt." + last(e),
                    einbauten=[e["id"]], werkzeuge=["Kunststoffhammer"] + heben(e),
                    pruefung=["Nabe liegt an (Fühlerlehre 0,05 mm)"], zeit=15))
            else:
                schritte.append(_schritt(f"{mal}{name(e)} anbauen", f"{name(e)} lagerichtig ansetzen und ausrichten.{last(e, n)}",
                                         einbauten=[e["id"]], werkzeuge=heben(e, n),
                                         pruefung=["Lage nach Zeichnung geprüft"], zeit=10 * n))
            continue
        norm = e["norm"]
        art = normteil_art(norm)
        if art == "passfeder":
            schritte.append(_schritt(f"{mal}Passfeder {norm} einlegen",
                                     "Passfeder in die Wellennut einlegen und mit dem Kunststoffhammer bis zum "
                                     "Nutgrund eintreiben.", einbauten=[e["id"]], werkzeuge=["Kunststoffhammer"],
                                     pruefung=["Passfeder liegt am Nutgrund, steht seitlich nicht über"], zeit=5 * n))
        elif art == "lager":
            schritte.append(_schritt(
                f"{mal}Lager {norm} warm aufziehen",
                f"Lager mit dem Induktions-Anwärmgerät auf ca. {LAGER_T} °C erwärmen (höchstens 120 °C, "
                "Herstellerrichtwert, ungeprüft – nie mit offener Flamme). Zügig bis zur Wellenschulter aufschieben "
                "und bis zum Abkühlen gegen die Schulter halten.",
                einbauten=[e["id"]], werkzeuge=["Induktions-Anwärmgerät", "Temperaturmessstift",
                                                "Hitzeschutzhandschuhe"] + heben(e, 1),
                pruefung=["Lager liegt an der Schulter an (Fühlerlehre 0,05 mm, nach dem Abkühlen)",
                          "Lager dreht von Hand frei, ohne Geräusch"], zeit=20 * n))
        elif art == "scheibe":
            schritte.append(_schritt(f"{mal}Scheibe {norm} unterlegen", "Scheiben unter Schraubenkopf bzw. Mutter legen.",
                                     einbauten=[e["id"]], pruefung=["Anzahl vollständig"], zeit=max(1.0, 0.3 * n)))
        elif art in ("schraube_sk", "schraube_is", "mutter"):
            m_a, quelle, h = anzugsmoment(norm, umfeld.schrauben)
            if h and h not in hinweise:
                hinweise.append(h)
            sw = schluesselweite(norm)
            werkzeug = (f"Innensechskant-Einsatz SW {f(sw)}" if art == "schraube_is" else f"Steckschlüssel SW {f(sw)}")
            werkzeuge = [werkzeug] + ([drehmomentschluessel(m_a)] if m_a else [])
            if art == "mutter":
                werkzeuge.append(f"Ringschlüssel SW {f(sw)} zum Gegenhalten")
            moment_text = f"M_A = {f(m_a)} N·m" if m_a else "M_A (von Hand eintragen)"
            tun = "aufschrauben" if art == "mutter" else "einsetzen"
            kreuz = " über Kreuz" if n > 2 else ""
            schritte.append(_schritt(
                f"{mal}{norm} {tun} und anziehen",
                f"{'Muttern' if art == 'mutter' else 'Schrauben'} {tun}, Gewinde leicht ölen (µ ≈ 0,12 wie in der "
                f"Rechnung), zuerst handfest, dann{kreuz} in drei Stufen 30 % → 70 % → 100 % auf {moment_text} anziehen.",
                einbauten=[e["id"]], werkzeuge=werkzeuge,
                momente=[{"was": f"{mal}{norm}", "wert": m_a, "quelle": quelle}],
                pruefung=[f"Alle {n} mit {moment_text} im Uhrzeigersinn nachgezogen" if n > 1
                          else f"Mit {moment_text} nachgezogen", "Lackstrich (Torque-Mark) über Kopf und Bauteil"],
                zeit=1.5 * n + 3))
        else:
            schritte.append(_schritt(f"{mal}{norm} einbauen", "Normteil lagerichtig einbauen.", einbauten=[e["id"]],
                                     zeit=5 * n))
    if einbauten:
        schritte.append(_schritt(
            "Endkontrolle",
            "Baugruppe vollständig und sauber prüfen, Ergebnisse im Prüfprotokoll eintragen.",
            werkzeuge=["Messuhr mit Magnetstativ", "Fühlerlehre"],
            pruefung=["Triebstrang von Hand drehen: leichtgängig, ohne Klemmen und Geräusch",
                      "Rundlauf am Nabensitz bzw. Planlauf der Scheibe ≤ 0,1 mm (Richtwert)",
                      "Alle Schrauben mit Lackstrich markiert",
                      "Vollständigkeit gegen die Stückliste geprüft",
                      f"Masse der Baugruppe ≈ {f(erg.masse)} kg (Wägung, wenn möglich)"], zeit=15))
    for i, s in enumerate(schritte, 1):
        s["nr"] = i
    return {"vorrichtung": v["id"] if v else None, "schritte": schritte, "hinweise": hinweise}


def nummerieren(plan: dict) -> dict:
    for i, s in enumerate(plan.get("schritte", []), 1):
        s["nr"] = i
    return plan


def gesamtzeit(plan: dict) -> float:
    return sum(float(s.get("zeit") or 0) for s in plan.get("schritte", []))


def werkzeugliste(plan: dict) -> list[str]:
    alle: list[str] = []
    for s in plan.get("schritte", []):
        for w in s.get("werkzeuge", []):
            if w and w not in alle:
                alle.append(w)
    return sorted(alle, key=str.lower)


def pruefen(plan: dict, definition: dict) -> list[str]:
    """Widersprüche zwischen Plan und Baugruppe: fehlende, doppelte oder verschwundene Einbauten."""
    einbauten = {e["id"]: e for e in definition.get("einbauten", [])}
    gesehen: Counter = Counter(eid for s in plan.get("schritte", []) for eid in s.get("einbauten", []))
    meldungen = []
    for eid, e in einbauten.items():
        if not gesehen.get(eid):
            meldungen.append(f"„{e.get('name') or e.get('norm') or eid}“ ({eid}) kommt in keinem Schritt vor.")
        elif gesehen[eid] > 1:
            meldungen.append(f"„{e.get('name') or e.get('norm') or eid}“ ({eid}) wird in mehreren Schritten eingebaut.")
    for eid in gesehen:
        if eid not in einbauten:
            meldungen.append(f"Ein Schritt nennt {eid}, das es in der Baugruppe nicht mehr gibt.")
    for s in plan.get("schritte", []):
        for m in s.get("momente", []):
            if m.get("wert") in (None, ""):
                meldungen.append(f"Schritt {s['nr']}: Anzugsmoment für {m.get('was', '')} fehlt.")
    return meldungen


# ================================================================ Explosionsdarstellung (S11)
def _mitte(form) -> np.ndarray:
    e = eigenschaften(form)
    return (np.array(e.minimum) + np.array(e.maximum)) / 2


def explosion(definition: dict, erg, faktor: float = 1.0) -> list[np.ndarray]:
    """Verschiebung je Exemplar: weg von der Mitte des Grundteils (Abstand × Faktor); Schrauben zusätzlich
    entlang ihrer Achse zum Kopf hin heraus. Das Grundteil bleibt stehen."""
    basis = basis_einbau(definition)
    einbauten = {e["id"]: e for e in definition.get("einbauten", [])}
    mitten = [_mitte(x.form) for x in erg.exemplare]
    b = [m for x, m in zip(erg.exemplare, mitten) if x.einbau == basis]
    c0 = np.mean(b, axis=0) if b else np.zeros(3)
    achse = next((x.matrix[:3, 2] for x in erg.exemplare if x.einbau == basis), np.array([0.0, 0.0, 1.0]))
    out = []
    for x, m in zip(erg.exemplare, mitten):
        if x.einbau == basis:
            out.append(np.zeros(3))
            continue
        e = einbauten.get(x.einbau, {})
        d = m - c0
        if e.get("bezug") and e["bezug"].get("ziel"):       # koaxial verknüpft: nur entlang der Achse
            d = float(d @ achse) * achse
        v = faktor * d
        if e.get("art") == "normteil" and normteil_art(e["norm"]).startswith("schraube"):
            l = float(re.search(r"x(\d+(?:\.\d+)?)", e["norm"]).group(1))
            v = v + faktor * 1.5 * l * x.matrix[:3, 2]
        out.append(v)
    return out


# ================================================================ Montageplatte (M39)
def _frei(von: float, bis: float, belegt: list[tuple[float, float]]) -> list[tuple[float, float]]:
    stuecke = [(von, bis)]
    for a, b in belegt:
        neu = []
        for s, e in stuecke:
            if b <= s or a >= e:
                neu.append((s, e))
                continue
            if a > s:
                neu.append((s, a))
            if b < e:
                neu.append((b, e))
        stuecke = neu
    return stuecke


def platte_vorschlag(definition: dict, erg, b_bock: float = 40.0) -> tuple[dict, list[str]]:
    """Maße der Montageplatte aus der Baugruppe: Auflagen an der längsten freien Zylinderstelle des Grundteils,
    Achshöhe = größter Radius der Baugruppe + 25 mm. Liefert (Parameter, Hinweise) im Koordinatensystem des
    Grundteils (Achse z)."""
    from ..cad.vorlagen import MontageplatteParameter
    from ..cad.zeichnung import zylinder_flaechen
    basis = basis_einbau(definition)
    ex_b = next((x for x in erg.exemplare if x.einbau == basis), None)
    if ex_b is None:
        raise ValueError("Die Baugruppe hat kein Grundteil.")
    inv = np.linalg.inv(ex_b.matrix)
    lokal_b = bewegen(ex_b.form, inv)
    hinweise = []
    belegt, r_max = [], 0.0
    for x in erg.exemplare:
        e = eigenschaften(bewegen(x.form, inv) if x is not ex_b else lokal_b)
        r_max = max(r_max, *(abs(v) for v in (*e.minimum[:2], *e.maximum[:2])))
        if x.einbau != basis:
            belegt.append((e.minimum[2] - 2, e.maximum[2] + 2))
    aussen = [c for c in zylinder_flaechen(lokal_b) if not c.innen and abs(abs(c.achse[2]) - 1) < 1e-6
              and math.hypot(c.ort[0], c.ort[1]) < 1e-3]
    stellen = []      # (Länge, von, bis, d)
    for c in aussen:
        for a, b in _frei(c.von, c.bis, belegt):
            if b - a >= b_bock + 10:
                stellen.append((b - a, a, b, 2 * c.radius))
    stellen.sort(reverse=True)
    if not stellen:
        raise ValueError("Am Grundteil ist keine freie zylindrische Stelle für Auflagen – Maße von Hand eintragen.")
    laenge, a, b, d = stellen[0]
    if laenge >= 2 * b_bock + 60:
        z1, z2 = a + 0.25 * laenge, a + 0.75 * laenge
    else:
        zweite = next((s for s in stellen[1:] if abs(s[3] - d) < 0.01), None)
        if zweite is None:
            raise ValueError("Nur eine kurze freie Auflagestelle gefunden – Auflagen von Hand festlegen.")
        z1, z2 = sorted(((a + b) / 2, (zweite[1] + zweite[2]) / 2))
    if len({round(s[3], 1) for s in stellen}) > 1:
        hinweise.append(f"Auflagen am Ø{f(d)} (längste freie Stelle {f(laenge)} mm).")
    z1, z2 = round(z1 * 2) / 2, round(z2 * 2) / 2
    achshoehe = math.ceil((r_max + 25) / 5) * 5
    p_laenge = math.ceil((z2 - z1 + b_bock + 120) / 10) * 10
    z_start = round(((z1 + z2) / 2 - p_laenge / 2) * 2) / 2
    p = MontageplatteParameter()
    breite = max(math.ceil((d + 60 + 4 * p.d_befestigung + 10) / 10) * 10, 240)
    werte = {**p.__dict__, "d_auflage": round(d, 1), "z_1": z1, "z_2": z2, "achshoehe": float(achshoehe),
             "laenge": float(p_laenge), "z_start": z_start, "breite": float(breite), "b_bock": b_bock}
    hinweise.append(f"Achshöhe {f(achshoehe)} mm = größter Radius der Baugruppe {f(r_max)} mm + 25 mm Freiraum.")
    return werte, hinweise
