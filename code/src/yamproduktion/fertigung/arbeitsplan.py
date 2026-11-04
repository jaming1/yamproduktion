"""Arbeitsplan, Rohteil und Kosten je Bauteil (Lastenheft M34–M37).

Ein Arbeitsplan ist ein JSON-Wörterbuch (im Projekt gespeichert, wie Teile und Baugruppen):

    {"rohteil": {"art": "Rundstahl", "d": 95, "l": 850, "werkstoff": "42CrMo4 · …"},
     "fertigung": "eigen" | "fremd", "losgroesse": 2, "preis_fremd": null,
     "vorgaenge": [{"nr": 10, "art": "saegen", "text": "Rohteil absägen", "maschine": "Säge", "tr": 5,
                    "p": {"flaeche": 7088}, "te": null}, …]}

`te` = null heißt: Stückzeit aus den Schnittdaten berechnen; eine Zahl überschreibt sie (Minuten).
Preise und Stundensätze sind Schätzwerte (unbelegt) und werden im Projekt durch Angebote ersetzt.
"""
from __future__ import annotations

import bisect
import copy
import math
from dataclasses import dataclass, field

from .. import werkstoffe
from . import schnittdaten as S

# Halbzeug-Abmessungen (Rundstahl EN 10060, Flachstahl/Blech EN 10058/10029) – Norm, ungeprüft
RUNDSTAHL = (10, 12, 14, 16, 18, 20, 22, 25, 28, 30, 32, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85, 90, 95, 100,
             105, 110, 115, 120, 125, 130, 140, 150, 160, 170, 180, 190, 200, 220, 240, 250, 260, 280, 300, 320,
             340, 350, 360, 380, 400, 450, 500)
DICKEN = (3, 4, 5, 6, 8, 10, 12, 15, 20, 25, 30, 35, 40, 45, 50, 60, 70, 80, 90, 100, 120, 150)
AUFMASS_RUND = 3.0       # mm auf den Durchmesser
AUFMASS_LAENGE = 5.0     # mm auf die Länge (Sägen + Plandrehen)
AUFMASS_GUSS = 3.0       # mm je Seite
AUFMASS_ZUSCHNITT = 3.0  # mm je Seite beim Brennen/Sägen von Platten

ARTEN = {   # Arbeitsgang-Art → (Anzeige, Maschine, Rüstzeit min – Richtwert)
    "saegen": ("Sägen", "Säge", 5),
    "brennschneiden": ("Brennschneiden", "Brennschneiden", 10),
    "plandrehen": ("Plandrehen", "Drehmaschine", 20),
    "laengsdrehen": ("Längsdrehen", "Drehmaschine", 30),
    "fraesen": ("Fräsen", "Fräsmaschine", 40),
    "bohren": ("Bohren", "Bohrmaschine", 15),
    "schweissen": ("Schweißen", "Schweißplatz", 15),
    "laminieren": ("Laminieren", "Handarbeitsplatz", 30),
    "manuell": ("Von Hand / Prüfen", "Handarbeitsplatz", 0),
    "guss": ("Gussrohteil (Gießerei)", "Zukauf", 0),
}
# Schätzwerte – unbelegt, im Projekt durch eigene Sätze und Angebote ersetzen
STUNDENSAETZE = {"Säge": 45.0, "Brennschneiden": 70.0, "Drehmaschine": 85.0, "Fräsmaschine": 95.0,
                 "Bohrmaschine": 55.0, "Schweißplatz": 65.0, "Handarbeitsplatz": 45.0, "Zukauf": 0.0}
MATERIALPREISE = {"Baustahl": 1.6, "Vergütungsstahl": 2.8, "Einsatzstahl": 3.0, "Nichtrostender Stahl": 6.5,
                  "Gusseisen mit Kugelgraphit": 4.5, "Aluminium": 6.0, "Faserverbund": 15.0}   # €/kg Rohteil
AUFSCHLAG_FREMD = 0.25   # Schätzung für Fremdfertigung ohne Angebot: Eigenkosten + 25 %
SCHAETZ_HINWEIS = ("Materialpreise, Stundensätze und Zukaufpreise sind Schätzwerte (unbelegt) – im Projekt unter "
                   "„Kosten“ durch eigene Sätze und Angebote ersetzen.")


def standard_saetze() -> dict:
    return {"stundensaetze": dict(STUNDENSAETZE), "materialpreise": dict(MATERIALPREISE), "zukauf": {}}


def _naechst(reihe, wert: float) -> float:
    i = bisect.bisect_left(reihe, wert - 1e-9)
    return float(reihe[i]) if i < len(reihe) else float(math.ceil(wert / 10) * 10)


def gruppe(werkstoff_text: str) -> str:
    try:
        return werkstoffe.nach_bezeichnung(werkstoff_text)["gruppe"]
    except KeyError:
        return ""


def dichte(werkstoff_text: str) -> float:
    try:
        return float(werkstoffe.nach_bezeichnung(werkstoff_text)["dichte"])
    except KeyError:
        return 7850.0


# ================================================================ Geometrie lesen
@dataclass
class Merkmale:
    drehteil: bool
    durchmesser: float          # größter Ø (Drehteil) – sonst 0
    laenge: float               # Länge entlang z
    groesse: tuple              # Hüllbox x, y, z
    volumen: float
    flaeche: float
    absaetze: list = field(default_factory=list)       # [(d, länge)] außen, entlang z sortiert
    bohrung_mitte: list = field(default_factory=list)  # [(d, länge)] Bohrungen auf der Achse
    loecher: list = field(default_factory=list)        # [(d, tiefe, anzahl)] parallel zur Achse, außermittig
    nuten: list = field(default_factory=list)          # [(breite, länge)] Passfedernuten (quer liegende Zylinder)


def merkmale(form) -> Merkmale:
    from ..cad.geometrie import eigenschaften
    from ..cad.zeichnung import zylinder_flaechen
    e = eigenschaften(form)
    gx, gy, gz = e.groesse
    zyl = zylinder_flaechen(form)
    mx, my = (e.minimum[0] + e.maximum[0]) / 2, (e.minimum[1] + e.maximum[1]) / 2

    def auf_achse(c):
        return abs(abs(c.achse[2]) - 1) < 1e-6 and math.hypot(c.ort[0] - mx, c.ort[1] - my) < 1e-3
    aussen = [c for c in zyl if auf_achse(c) and not c.innen]
    d_max = 2 * max((c.radius for c in aussen), default=0.0)
    drehteil = bool(aussen) and abs(gx - gy) < 1e-3 and abs(d_max - gx) < 0.01 * gx
    m = Merkmale(drehteil, d_max if drehteil else 0.0, gz, (gx, gy, gz), e.volumen, e.flaeche)
    if drehteil:
        m.absaetze = sorted(((2 * c.radius, c.bis - c.von, min(c.von, c.bis)) for c in aussen), key=lambda t: t[2])
        m.absaetze = [(d, l) for d, l, _ in m.absaetze if l > 1e-6]
    bereiche: dict = {}      # gleiche Bohrung kann in mehrere Flächen geteilt sein (Nut, Naht)
    for c in zyl:
        if auf_achse(c) and c.innen:
            k = round(2 * c.radius, 3)
            a, b = bereiche.get(k, (c.von, c.bis))
            bereiche[k] = (min(a, c.von), max(b, c.bis))
    m.bohrung_mitte = [(d, b - a) for d, (a, b) in sorted(bereiche.items())]
    loecher: dict = {}
    for c in zyl:
        if c.innen and abs(abs(c.achse[2]) - 1) < 1e-6 and not auf_achse(c):
            k = (round(2 * c.radius, 2), round(c.bis - c.von, 2))
            loecher[k] = loecher.get(k, 0) + 1
    m.loecher = [(d, t, n) for (d, t), n in sorted(loecher.items())]
    # Passfedernut: zwei halbe Zylinder quer zur Achse mit gleichem Radius → Breite = 2r, Länge aus dem Abstand
    quer = [c for c in zyl if c.innen and abs(c.achse[2]) < 1e-6]
    gruppen: dict = {}
    for c in quer:
        gruppen.setdefault(round(c.radius, 3), []).append(c.ort[2])
    for r, orte in gruppen.items():
        orte.sort()
        for a, b in zip(orte[0::2], orte[1::2]):
            if b - a > 0.5 * r:          # echte Nut mit zwei runden Enden
                m.nuten.append((2 * r, b - a + 2 * r))
    return m


# ================================================================ Vorschlag
def vorschlag(form, werkstoff_text: str, name: str = "", vorlage: str = "") -> dict:
    """Rohteil und Arbeitsgänge aus der Geometrie vorschlagen. Alles ist danach von Hand änderbar."""
    m = merkmale(form)
    g = gruppe(werkstoff_text)
    gx, gy, gz = m.groesse
    vg: list[dict] = []
    plan_fremd = False

    def neu(art, text, **p):
        anzeige, maschine, tr = ARTEN[art]
        vg.append({"nr": 10 * (len(vg) + 1), "art": art, "text": text, "maschine": maschine, "tr": tr, "p": p,
                   "te": None})

    if vorlage == "zahnrad":
        da = max(gx, gy)
        d_roh = _naechst(RUNDSTAHL, da + AUFMASS_RUND)
        rohteil = {"art": "Rundstahl", "d": d_roh, "l": gz + AUFMASS_LAENGE, "werkstoff": werkstoff_text}
        neu("saegen", f"Rundstahl Ø{d_roh:g} absägen", flaeche=math.pi / 4 * d_roh ** 2)
        neu("plandrehen", "Stirnseiten plandrehen", d=d_roh, seiten=2)
        neu("laengsdrehen", f"Kopfkreis Ø{da:.1f} drehen", abschnitte=[[d_roh, round(da, 2), gz]], schlichten=True)
        for d, l in m.bohrung_mitte:
            neu("bohren", f"Bohrung Ø{d:g} bohren", d=d, tiefe=l, anzahl=1)
        neu("manuell", "Verzahnen (Wälzfräsen) – Zeit/Preis beim Verzahner anfragen")
        plan_fremd = True
    elif g == "Faserverbund":
        rohteil = {"art": "Laminat", "werkstoff": werkstoff_text, "masse_aufschlag": 0.15}
        neu("laminieren", "Lagen zuschneiden, laminieren, aushärten (Zeit von Hand eintragen)")
        vg[-1]["te"] = 60.0
    elif m.drehteil and g == "Gusseisen mit Kugelgraphit":
        rohteil = {"art": "Guss", "d": m.durchmesser + 2 * AUFMASS_GUSS, "l": m.laenge + 2 * AUFMASS_GUSS,
                   "werkstoff": werkstoff_text}
        neu("guss", "Gussrohteil nach Zeichnung mit 3 mm Bearbeitungszugabe (Gießerei)")
        vg[-1]["te"] = 0.0
        _drehen(neu, m, rohteil["d"])
    elif m.drehteil and m.durchmesser > 250 and m.laenge < 0.3 * m.durchmesser:
        h = _naechst(DICKEN, m.laenge + 2)
        rohteil = {"art": "Blech", "d": m.durchmesser + 2 * AUFMASS_ZUSCHNITT, "h": h, "werkstoff": werkstoff_text}
        innen = [d for d, _ in m.bohrung_mitte if d > 100]
        umfang = math.pi * (rohteil["d"] + sum(d - 2 * AUFMASS_ZUSCHNITT for d in innen))
        neu("brennschneiden", "Ronde" + (" mit Innenausschnitt" if innen else "") + " aus Blech brennen",
            umfang=umfang, dicke=h)
        _drehen(neu, m, rohteil["d"], vorgebrannt=2 * AUFMASS_ZUSCHNITT)
    elif m.drehteil:
        d_roh = _naechst(RUNDSTAHL, m.durchmesser + AUFMASS_RUND)
        rohteil = {"art": "Rundstahl", "d": d_roh, "l": m.laenge + AUFMASS_LAENGE, "werkstoff": werkstoff_text}
        neu("saegen", f"Rundstahl Ø{d_roh:g} auf {rohteil['l']:g} mm absägen", flaeche=math.pi / 4 * d_roh ** 2)
        _drehen(neu, m, d_roh)
    else:
        dicke = min(m.groesse)
        h = _naechst(DICKEN, dicke + 2)
        aussen = sorted(v for v in m.groesse if v != dicke) + [0, 0]
        rohteil = {"art": "Flachstahl" if h <= 40 and aussen[1] <= 300 else "Blech",
                   "b": math.ceil(aussen[0] + 2 * AUFMASS_ZUSCHNITT), "l": math.ceil(aussen[1] + 2 * AUFMASS_ZUSCHNITT),
                   "h": h,
                   "werkstoff": werkstoff_text}
        if rohteil["art"] == "Flachstahl":
            neu("saegen", "Flachstahl absägen", flaeche=rohteil["b"] * h)
        else:
            neu("brennschneiden", "Zuschnitt aus Blech brennen", umfang=2 * (rohteil["b"] + rohteil["l"]), dicke=h)
        neu("fraesen", "Umfang und Flächen auf Maß fräsen", weg=2 * (aussen[0] + aussen[1]), tiefe=h, d_fraeser=20)
        for d, t, n in m.loecher:
            neu("bohren", f"{n}× Ø{d:g} bohren", d=d, tiefe=t, anzahl=n)
    if g != "Faserverbund":
        neu("manuell", "Entgraten, Maße prüfen")
        vg[-1]["te"] = 5.0
    return {"rohteil": rohteil, "fertigung": "fremd" if plan_fremd else "eigen", "losgroesse": 1, "preis_fremd": None, "vorgaenge": vg,
            "name": name}


def _drehen(neu, m: Merkmale, d_roh: float, vorgebrannt: float = 0.0):
    neu("plandrehen", "Stirnseiten plandrehen, zentrieren", d=d_roh, seiten=2)
    abschnitte = [[d_roh, d, l] for d, l in m.absaetze if d_roh - d > 0.01]
    if abschnitte:
        neu("laengsdrehen", "Außenkontur schruppen und schlichten", abschnitte=abschnitte, schlichten=True)
    for d, l in m.bohrung_mitte:
        if vorgebrannt and d > 100:
            neu("laengsdrehen", f"Bohrung Ø{d:g} ausdrehen", abschnitte=[[d - vorgebrannt, d, l]], schlichten=True)
        elif d <= 30:
            neu("bohren", f"Bohrung Ø{d:g} bohren", d=d, tiefe=l, anzahl=1)
        else:
            neu("bohren", "Vorbohren Ø30", d=30, tiefe=l, anzahl=1)
            neu("laengsdrehen", f"Bohrung Ø{d:g} ausdrehen", abschnitte=[[30, d, l]], schlichten=True)
    for d, t, n in m.loecher:
        neu("bohren", f"{n}× Ø{d:g} bohren (Lochkreis)", d=d, tiefe=t, anzahl=n)
    for b, l in m.nuten:
        neu("fraesen", f"Passfedernut {b:g} × {l:g} fräsen", weg=l - b, tiefe=0.6 * b, d_fraeser=b)


# ================================================================ Rechnen
@dataclass
class Gang:
    nr: int
    art: str
    text: str
    maschine: str
    tr: float
    th: float | None
    te: float | None
    rechenweg: list = field(default_factory=list)
    fehler: str = ""
    von_hand: bool = False


@dataclass
class Kalkulation:
    gaenge: list[Gang]
    rohteil_masse: float               # kg
    rohteil_text: str
    material: float                    # € je Stück
    fertigung: float                   # € je Stück (eigen, inkl. anteiliger Rüstkosten)
    stueck: float                      # € je Stück (eigen bzw. fremd)
    losgroesse: int
    fremd: bool
    fremd_geschaetzt: bool             # Fremdpreis ohne Angebot geschätzt
    te_summe: float                    # min je Stück
    tr_summe: float                    # min je Los
    fehler: list[str] = field(default_factory=list)

    @property
    def los(self) -> float:
        return self.stueck * self.losgroesse


def rohteil_masse(rohteil: dict, teil_volumen: float = 0.0, teil_flaeche: float = 0.0) -> float:
    rho = dichte(rohteil.get("werkstoff", ""))
    art = rohteil.get("art")
    if art in ("Rundstahl",):
        v = math.pi / 4 * rohteil["d"] ** 2 * rohteil["l"]
    elif art == "Blech" and "d" in rohteil:
        v = math.pi / 4 * rohteil["d"] ** 2 * rohteil["h"]
    elif art in ("Flachstahl", "Blech"):
        v = rohteil["b"] * rohteil["l"] * rohteil["h"]
    elif art == "Guss":
        v = teil_volumen + teil_flaeche * AUFMASS_GUSS
    else:   # Laminat, Zukauf …: Teilvolumen plus Verschnitt
        v = teil_volumen * (1 + float(rohteil.get("masse_aufschlag", 0.1)))
    return v * 1e-9 * rho


def rohteil_text(rohteil: dict) -> str:
    art = rohteil.get("art", "")
    w = rohteil.get("werkstoff", "").split(" · ")[0]
    if art == "Rundstahl":
        return f"Rundstahl Ø{rohteil['d']:g} × {rohteil['l']:g} {w}"
    if art == "Blech" and "d" in rohteil:
        return f"Ronde Ø{rohteil['d']:g} aus Blech {rohteil['h']:g} {w}"
    if art in ("Flachstahl", "Blech"):
        return f"{art} {rohteil['h']:g} × {rohteil['b']:g} × {rohteil['l']:g} {w}"
    if art == "Guss":
        return f"Gussrohteil {w} (≈ Ø{rohteil['d']:g} × {rohteil['l']:g})"
    return f"{art} {w}".strip()


def zeit(vorgang: dict, gruppe_: str) -> tuple[float | None, list[str]]:
    """Hauptzeit eines Arbeitsgangs aus den Schnittdaten (None bei Handarbeit)."""
    p = vorgang.get("p", {})
    art = vorgang["art"]
    if art == "saegen":
        z = S.saegen(gruppe_, p["flaeche"])
    elif art == "brennschneiden":
        z = S.brennschneiden(p["umfang"], p["dicke"])
    elif art == "plandrehen":
        z = S.plandrehen(gruppe_, p["d"], int(p.get("seiten", 2)))
    elif art == "laengsdrehen":
        z = S.laengsdrehen(gruppe_, p["abschnitte"], bool(p.get("schlichten", True)))
    elif art == "fraesen":
        z = S.fraesen(gruppe_, p["weg"], p["tiefe"], p["d_fraeser"])
    elif art == "bohren":
        z = S.bohren(gruppe_, p["d"], p["tiefe"], int(p.get("anzahl", 1)))
    else:
        return None, []
    return z.th, z.schritte


def kalkulieren(plan: dict, saetze: dict | None = None, teil_volumen: float = 0.0, teil_flaeche: float = 0.0
                ) -> Kalkulation:
    saetze = saetze or standard_saetze()
    roh = plan.get("rohteil", {})
    g = gruppe(roh.get("werkstoff", ""))
    los = max(1, int(plan.get("losgroesse") or 1))
    gaenge, fehler = [], []
    fertigung = te_summe = tr_summe = 0.0
    for v in plan.get("vorgaenge", []):
        gang = Gang(int(v.get("nr", 0)), v["art"], v.get("text", ""), v.get("maschine", ""), float(v.get("tr") or 0),
                    None, None)
        try:
            gang.th, gang.rechenweg = zeit(v, g)
        except (S.SchnittFehler, KeyError, TypeError, ValueError) as exc:
            gang.fehler = str(exc) if not isinstance(exc, KeyError) else f"Angabe {exc} fehlt"
        if v.get("te") not in (None, ""):
            gang.te, gang.von_hand = float(v["te"]), True
        elif gang.th is not None:
            gang.te = gang.th * (1 + S.ZUSCHLAG) + S.SPANNEN
        if gang.te is None:
            fehler.append(f"AG {gang.nr}: keine Stückzeit" + (f" ({gang.fehler})" if gang.fehler else ""))
            gang.te = 0.0
        satz = saetze["stundensaetze"].get(gang.maschine)
        if satz is None:
            fehler.append(f"AG {gang.nr}: kein Stundensatz für „{gang.maschine}“")
            satz = 0.0
        fertigung += (gang.tr / los + gang.te) / 60 * satz
        te_summe += gang.te
        tr_summe += gang.tr
        gaenge.append(gang)
    masse = rohteil_masse(roh, teil_volumen, teil_flaeche) if roh else 0.0
    preis_kg = saetze["materialpreise"].get(g)
    if preis_kg is None:
        fehler.append(f"Kein Materialpreis für die Gruppe „{g or '?'}“")
        preis_kg = 0.0
    material = masse * preis_kg
    fremd = plan.get("fertigung") == "fremd"
    geschaetzt = False
    if fremd:
        if plan.get("preis_fremd") not in (None, ""):
            stueck = float(plan["preis_fremd"])
        else:
            stueck, geschaetzt = (material + fertigung) * (1 + AUFSCHLAG_FREMD), True
    else:
        stueck = material + fertigung
    return Kalkulation(gaenge, masse, rohteil_text(roh) if roh else "", material, fertigung, stueck, los, fremd,
                       geschaetzt, te_summe, tr_summe, fehler)


# ================================================================ Baugruppe
@dataclass
class KostenZeile:
    pos: int
    menge: int
    benennung: str
    sachnummer: str
    art: str                 # Eigen / Fremd / Zukauf
    einzel: float | None
    hinweis: str = ""

    @property
    def gesamt(self) -> float | None:
        return None if self.einzel is None else self.einzel * self.menge


def baugruppe_kalkulieren(stueckliste, plan_kosten: dict, saetze: dict, anzahl: int = 1) -> tuple[list, float, list]:
    """plan_kosten: Sachnummer → Kalkulation des Bauteils. Liefert (Zeilen, Summe je Baugruppe, fehlende Preise)."""
    zeilen, fehlend, summe = [], [], 0.0
    for p in stueckliste:
        if p.art == "Bauteil":
            k = plan_kosten.get(p.sachnummer)
            if k is None:
                zeilen.append(KostenZeile(p.pos, p.menge, p.benennung, p.sachnummer, "–", None, "Arbeitsplan fehlt"))
                fehlend.append(p.sachnummer)
                continue
            hinweis = "Schätzung ohne Angebot" if k.fremd_geschaetzt else ""
            zeilen.append(KostenZeile(p.pos, p.menge, p.benennung, p.sachnummer, "Fremd" if k.fremd else "Eigen",
                                      k.stueck, hinweis))
        else:
            preis = saetze.get("zukauf", {}).get(p.sachnummer)
            zeilen.append(KostenZeile(p.pos, p.menge, p.benennung, p.sachnummer, "Zukauf", preis,
                                      "" if preis is not None else "Preis fehlt"))
            if preis is None:
                fehlend.append(p.sachnummer)
        if zeilen[-1].gesamt is not None:
            summe += zeilen[-1].gesamt
    return zeilen, summe * anzahl, fehlend


def plan_kopie(plan: dict) -> dict:
    return copy.deepcopy(plan)
