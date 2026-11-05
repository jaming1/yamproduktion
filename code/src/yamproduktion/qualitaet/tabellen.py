"""Tabellen-Dokumente der Qualität & Sicherheit (M44–M47): FMEA, Risikobeurteilung, Normen, Abweichungen.

Jedes Dokument speichert {"zeilen": [{…}], …}. Die Spalten beschreibt `ART[...]`; Oberfläche und PDF
werden daraus erzeugt. Bewertungsgrenzen sind Richtwerte – im Team festlegen.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

GRUEN, GELB, ROT, GRAU = "gruen", "gelb", "rot", "grau"


@dataclass
class Spalte:
    key: str
    titel: str
    breite: int = 120              # Pixel in der Oberfläche; 0 = dehnbar
    art: str = "text"              # text | zahl | wahl | berechnet
    wahl: tuple = ()
    tipp: str = ""
    fn: Callable | None = None     # für „berechnet“: zeile → Text
    pdf: float = 0                 # Breite im PDF in mm (0 = nicht im PDF)


@dataclass
class Art:
    typ: str
    titel: str
    praefix: str                   # Zeilen-Id, z. B. „F“ → F1, F2 …
    spalten: list[Spalte]
    bewerten: Callable             # zeile → (Text, Ampel)
    hinweis: str
    arten: tuple = ()              # Unterarten (z. B. Konstruktions-/Prozess-FMEA)
    leer: dict = field(default_factory=dict)


def ganz(wert) -> int | None:
    try:
        w = int(float(str(wert).replace(",", ".")))
    except (TypeError, ValueError):
        return None
    return w


def naechste_id(daten: dict, praefix: str) -> str:
    vorhanden = {z.get("id") for z in daten.get("zeilen", [])}
    i = 1
    while f"{praefix}{i}" in vorhanden:
        i += 1
    return f"{praefix}{i}"


def neue_zeile(art: "Art", daten: dict, **werte) -> dict:
    z = {s.key: "" for s in art.spalten if s.art != "berechnet"}
    z.update(art.leer)
    z.update(werte)
    z["id"] = naechste_id(daten, art.praefix)
    return z


def zaehlen(art: "Art", daten: dict) -> dict:
    zahlen = {GRUEN: 0, GELB: 0, ROT: 0, GRAU: 0}
    for z in daten.get("zeilen", []):
        zahlen[art.bewerten(z)[1]] += 1
    return zahlen


# ---------------------------------------------------------------- FMEA (M44)
FMEA_GRENZE_RPZ = 125     # Richtwert: Handlungsbedarf ab RPZ 125 …
FMEA_GRENZE_B = 9         # … oder Bedeutung ≥ 9 mit Auftreten ≥ 4
FMEA_HINWEIS = ("Bewertung B (Bedeutung), A (Auftreten), E (Entdeckung) je 1–10, RPZ = B·A·E. Handlungsbedarf ab "
                f"RPZ ≥ {FMEA_GRENZE_RPZ} oder B ≥ {FMEA_GRENZE_B} mit A ≥ 4 (Richtwert). Vorgeschlagene Bewertungen "
                "sind Schätzwerte – im Team prüfen. Nach der Maßnahme neu bewerten (B', A', E').")


def rpz(z: dict, nach: bool = False) -> int | None:
    s = "2" if nach else ""
    b, a, e = (ganz(z.get(k + s)) for k in ("B", "A", "E"))
    return b * a * e if None not in (b, a, e) else None


def _fmea_stufe(b, a, r) -> str:
    if r is None:
        return GRAU
    if r >= FMEA_GRENZE_RPZ or (b >= FMEA_GRENZE_B and a >= 4):
        return ROT
    if r >= 60 or b >= FMEA_GRENZE_B:
        return GELB
    return GRUEN


def fmea_bewerten(z: dict) -> tuple[str, str]:
    nach = rpz(z, True)
    if nach is not None:
        return f"nach Maßnahme RPZ {nach}", _fmea_stufe(ganz(z["B2"]), ganz(z["A2"]), nach)
    r = rpz(z)
    if r is None:
        return "nicht bewertet", GRAU
    stufe = _fmea_stufe(ganz(z["B"]), ganz(z["A"]), r)
    if stufe == ROT:
        return ("Maßnahme geplant" if z.get("massnahme") else "Handlungsbedarf"), ROT
    return ("beobachten" if stufe == GELB else "in Ordnung"), stufe


_B = tuple(str(i) for i in range(1, 11))
FMEA = Art(
    "fmea", "FMEA", "F",
    [Spalte("id", "Nr.", 44, pdf=9),
     Spalte("element", "Element / Schritt", 140, pdf=24),
     Spalte("fehler", "Fehlerart", 150, pdf=26),
     Spalte("folge", "Fehlerfolge", 150, pdf=26),
     Spalte("ursache", "Fehlerursache", 150, pdf=26),
     Spalte("vermeidung", "Vermeidung (heute)", 150, tipp="Konstruktive Absicherung, Nachweis, Arbeitsanweisung", pdf=28),
     Spalte("entdeckung", "Entdeckung (heute)", 140, tipp="Prüfung, Test, Kontrolle", pdf=24),
     Spalte("B", "B", 38, "wahl", _B, "Bedeutung 1–10", pdf=8),
     Spalte("A", "A", 38, "wahl", _B, "Auftreten 1–10", pdf=8),
     Spalte("E", "E", 38, "wahl", _B, "Entdeckung 1–10", pdf=8),
     Spalte("rpz", "RPZ", 46, "berechnet", fn=lambda z: str(rpz(z) or "–"), pdf=10),
     Spalte("massnahme", "Maßnahme", 170, pdf=28),
     Spalte("verantwortlich", "Wer", 70, pdf=12),
     Spalte("termin", "Termin", 100, pdf=15),
     Spalte("B2", "B'", 38, "wahl", ("",) + _B, "Bedeutung nach Maßnahme", pdf=8),
     Spalte("A2", "A'", 38, "wahl", ("",) + _B, "Auftreten nach Maßnahme", pdf=8),
     Spalte("E2", "E'", 38, "wahl", ("",) + _B, "Entdeckung nach Maßnahme", pdf=8),
     Spalte("rpz2", "RPZ'", 46, "berechnet", fn=lambda z: str(rpz(z, True) or "–"), pdf=10),
     Spalte("bewertung", "Bewertung", 0, "berechnet", fn=lambda z: fmea_bewerten(z)[0], pdf=0)],
    fmea_bewerten, FMEA_HINWEIS, arten=("Konstruktions-FMEA", "Prozess-FMEA"),
    leer={"B": "5", "A": "5", "E": "5", "B2": "", "A2": "", "E2": ""})


def _f(element, fehler, folge, ursache, vermeidung, entdeckung, b, a, e, massnahme="") -> dict:
    return {"element": element, "fehler": fehler, "folge": folge, "ursache": ursache, "vermeidung": vermeidung,
            "entdeckung": entdeckung, "B": str(b), "A": str(a), "E": str(e), "massnahme": massnahme,
            "verantwortlich": "", "termin": "", "B2": "", "A2": "", "E2": ""}


def fmea_vorlage(unterart: str, nachweise: dict[str, str], teile: list[str] = ()) -> dict:
    """KWA-Vorlage. `nachweise`: Berechnungsart → „B-005“; `teile`: Bauteilnamen aus dem Projekt."""
    def nw(typ, text):
        return f"{text} ({nachweise[typ]})" if typ in nachweise else f"{text} – Nachweis fehlt"
    if unterart == "Prozess-FMEA":
        zeilen = [
            _f("Drehen Lagersitze", "Passmaß außerhalb Toleranz", "Lager sitzt lose/zu fest, Lagerschaden",
               "Werkzeugverschleiß, Wärmegang", "Arbeitsplan mit Schlichtgang", "Prüfplan: Grenzrachenlehre 100 %",
               7, 4, 3),
            _f("Schweißen Turm/Flansch", "Bindefehler, Risse", "Dauerbruch des Turms, Umsturz",
               "Falsche Parameter, ungeeigneter Schweißer", "Qualifiziertes Verfahren (WPS)",
               "Sichtprüfung, Farbeindringprüfung", 10, 3, 5, "Prüfung durch Fachbetrieb, Durchstrahlung prüfen"),
            _f("Montage Schraubverbindungen", "Anzugsmoment falsch", "Lockern, Teile fallen herab",
               "Kein kalibrierter Drehmomentschlüssel", nw("schrauben", "Momente im Montageplan"),
               "Lackstrich, Kontrolle bei Abnahme", 9, 4, 4, "Drehmomentschlüssel kalibrieren, Zweitkontrolle"),
            _f("Montage Lager", "Lager beim Einpressen beschädigt", "Frühausfall Lager",
               "Kraft über Wälzkörper eingeleitet", "Montageanleitung mit Fügetemperatur",
               "Leichtgängigkeit von Hand prüfen", 7, 3, 5),
            _f("Rotor auswuchten", "Unwucht zu groß", "Schwingungen, Lagerschaden, Lärm",
               "Blätter ungleich schwer", "Blätter wiegen und paarweise zuordnen",
               "Schwingungsmessung bei Inbetriebnahme", 6, 4, 4),
            _f("Korrosionsschutz", "Beschichtung zu dünn", "Korrosion, Querschnittsverlust",
               "Oberfläche nicht vorbereitet", "Strahlen vor dem Beschichten", "Schichtdickenmessung", 7, 3, 4),
        ]
    else:
        zeilen = [
            _f("Rotorblatt", "Blattbruch", "Teile werden weggeschleudert", "Ermüdung, Fertigungsfehler, Blitz",
               nw("rotorauslegung", "Auslegung Rotor"), "Sichtprüfung bei Wartung", 10, 3, 6,
               "Blattlasten nach IEC 61400-2 nachweisen"),
            _f("Hauptwelle", "Dauerbruch am Absatz", "Rotor fällt herab", "Kerbwirkung, Biegewechsellast",
               nw("welle", "Festigkeitsnachweis Welle DIN 743"), "keine (verdeckt)", 10, 2, 8),
            _f("Hauptlager", "Ermüdung, Pitting", "Lärm, Blockieren des Rotors", "Last zu hoch, Schmierung fehlt",
               nw("lager", "Lebensdauer ISO 281"), "Geräusch- und Temperaturkontrolle", 6, 3, 4),
            _f("Schraubverbindungen Nabe/Turm", "Lösen, Bruch", "Rotor oder Gondel fällt herab",
               "Vorspannkraftverlust, Ermüdung", nw("schrauben", "Nachweis VDI 2230"), "Nachziehen bei Wartung",
               10, 3, 4),
            _f("Bremse", "Bremsmoment zu klein", "Überdrehzahl, Rotor geht durch", "Beläge verschlissen, Öl",
               nw("bremse", "Bremsmomentnachweis"), "Funktionstest bei Wartung", 9, 3, 4,
               "Zweites unabhängiges System (Pitch/Furling) prüfen"),
            _f("Turm", "Knicken, Umsturz", "Absturz der Anlage", "Sturmlast, Fundament zu klein",
               nw("turm", "Standsicherheit Turm"), "keine vor dem Ereignis", 10, 2, 9),
            _f("Steuerung", "Überdrehzahl nicht erkannt", "Rotor geht durch", "Sensorausfall",
               "Drehzahlüberwachung", "Test Überdrehzahlschutz bei Inbetriebnahme", 9, 3, 3),
        ]
        bekannt = {z["element"].split()[0].lower() for z in zeilen}
        for t in teile:
            if t.split()[0].lower() not in bekannt:
                zeilen.append(_f(t, "", "", "", "", "", "", "", ""))
                bekannt.add(t.split()[0].lower())
    daten = {"zeilen": []}
    for z in zeilen:
        daten["zeilen"].append(neue_zeile(FMEA, daten, **z))
    return daten


# ---------------------------------------------------------------- Risikobeurteilung (M46)
STUFEN = ("1 konstruktiv", "2 technisch", "3 Benutzerinformation")
PHASEN = ("Transport", "Montage", "Inbetriebnahme", "Betrieb", "Wartung", "Außerbetriebnahme")
RISIKO_HINWEIS = ("Vorgehen nach EN ISO 12100: Grenzen festlegen → Gefährdung erkennen → Risiko einschätzen "
                  "(S Schwere 1–4, W Wahrscheinlichkeit 1–4, R = S·W) → Maßnahme in der Rangfolge konstruktiv, "
                  "technisch, Benutzerinformation → Restrisiko (S', W'), gültig erst nach Umsetzung. R ≤ 4 akzeptabel, 5–8 weitere Maßnahme "
                  "prüfen, ≥ 9 nicht akzeptabel (Richtwert). Vorgeschlagene Einstufungen sind Schätzwerte. "
                  "Konformität nach Maschinenverordnung (EU) 2023/1230 erst nach Prüfung durch eine Fachperson.")
_S = ("1", "2", "3", "4")


def risiko(z: dict, nach: bool = False) -> int | None:
    s, w = (ganz(z.get(k + ("2" if nach else ""))) for k in ("S", "W"))
    return s * w if None not in (s, w) else None


def _risiko_stufe(r) -> str:
    if r is None:
        return GRAU
    return GRUEN if r <= 4 else (GELB if r <= 8 else ROT)


def risiko_bewerten(z: dict) -> tuple[str, str]:
    rest = risiko(z, True)
    if rest is not None and z.get("umgesetzt") != "ja":
        stufe = _risiko_stufe(risiko(z))
        if stufe != GRUEN:
            return "Maßnahme umsetzen", ROT if stufe == ROT else GELB
    if rest is not None:
        stufe = _risiko_stufe(rest)
        return {GRUEN: "Restrisiko akzeptabel", GELB: "Restrisiko prüfen",
                ROT: "Restrisiko nicht akzeptabel"}[stufe], stufe
    r = risiko(z)
    if r is None:
        return "nicht eingeschätzt", GRAU
    stufe = _risiko_stufe(r)
    return ({GRUEN: "akzeptabel", GELB: "Maßnahme prüfen", ROT: "Maßnahme nötig"}[stufe]), stufe


RISIKO = Art(
    "risiko", "Risikobeurteilung", "R",
    [Spalte("id", "Nr.", 44, pdf=9),
     Spalte("phase", "Lebensphase", 100, "wahl", PHASEN, pdf=20),
     Spalte("gefaehrdung", "Gefährdung", 160, tipp="Art nach EN ISO 12100 Anhang B", pdf=30),
     Spalte("situation", "Gefährdungssituation", 170, pdf=34),
     Spalte("S", "S", 38, "wahl", _S, "Schwere: 1 leicht, 2 ärztliche Hilfe, 3 bleibend, 4 tödlich", pdf=6),
     Spalte("W", "W", 38, "wahl", _S, "Wahrscheinlichkeit: 1 sehr selten … 4 häufig", pdf=6),
     Spalte("r", "R", 40, "berechnet", fn=lambda z: str(risiko(z) or "–"), pdf=7),
     Spalte("massnahme", "Schutzmaßnahme", 190, pdf=40),
     Spalte("stufe", "Stufe", 110, "wahl", STUFEN, "Rangfolge nach EN ISO 12100 Abschnitt 6", pdf=20),
     Spalte("S2", "S'", 38, "wahl", ("",) + _S, "Schwere nach Maßnahme", pdf=6),
     Spalte("W2", "W'", 38, "wahl", ("",) + _S, "Wahrscheinlichkeit nach Maßnahme", pdf=6),
     Spalte("r2", "R'", 40, "berechnet", fn=lambda z: str(risiko(z, True) or "–"), pdf=7),
     Spalte("umgesetzt", "Umgesetzt", 76, "wahl", ("nein", "ja"), "Restrisiko gilt erst, wenn die Maßnahme umgesetzt "
            "und geprüft ist", pdf=14),
     Spalte("nachweis", "Nachweis", 90, tipp="Berechnung, Prüfung oder Abschnitt der Anleitung", pdf=18),
     Spalte("bewertung", "Bewertung", 0, "berechnet", fn=lambda z: risiko_bewerten(z)[0], pdf=0)],
    risiko_bewerten, RISIKO_HINWEIS, leer={"phase": "Betrieb", "S": "2", "W": "2", "stufe": STUFEN[0],
                                           "umgesetzt": "nein"})


def _r(phase, gef, sit, s, w, mass, stufe, s2, w2, nachweis="") -> dict:
    return {"phase": phase, "gefaehrdung": gef, "situation": sit, "S": str(s), "W": str(w), "massnahme": mass,
            "stufe": STUFEN[stufe - 1], "S2": str(s2), "W2": str(w2), "umgesetzt": "nein", "nachweis": nachweis}


def risiko_vorlage(nachweise: dict[str, str]) -> dict:
    n = nachweise.get
    zeilen = [
        _r("Betrieb", "Mechanisch: drehender Rotor", "Person gerät in den Rotorkreis", 4, 2,
           "Mindesthöhe Blattspitze über Grund ≥ 2,5 m, Zugang zum Turm absperren", 1, 4, 1, "Aufstellplan"),
        _r("Betrieb", "Mechanisch: weggeschleuderte Teile", "Blattbruch oder Überdrehzahl", 4, 2,
           "Blattauslegung, zwei unabhängige Bremssysteme, Sicherheitsabstand", 1, 4, 1,
           n("rotorauslegung", "") or n("bremse", "")),
        _r("Betrieb", "Mechanisch: Eiswurf", "Eisansatz an den Blättern bei Frost", 3, 2,
           "Abschaltung bei Vereisung, Warnschild, Abstand zu Wegen", 2, 3, 1),
        _r("Betrieb", "Mechanisch: Umsturz", "Sturm über Auslegungswind", 4, 1,
           "Standsicherheit Turm/Fundament nachweisen, Sturmabschaltung", 1, 4, 1, n("turm", "")),
        _r("Betrieb", "Mechanisch: herabfallende Teile", "Lösen von Schrauben an Nabe/Gondel", 4, 2,
           "Schrauben nach VDI 2230, Sicherung, Nachziehintervall", 1, 4, 1, n("schrauben", "")),
        _r("Montage", "Absturz", "Arbeiten am Turmkopf", 4, 3,
           "Turm umlegbar (Montage am Boden), sonst Auffanggurt und Anschlagpunkt", 1, 4, 1, "Montageanleitung"),
        _r("Montage", "Mechanisch: schwebende Last", "Heben der Gondel mit Hebezeug", 4, 2,
           "Anschlagpunkte ausgelegt, Lastangabe in der Anleitung, Absperrbereich", 3, 4, 1, "Montageanleitung"),
        _r("Wartung", "Mechanisch: unerwarteter Anlauf", "Rotor dreht beim Arbeiten an der Gondel", 4, 3,
           "Rotorarretierung (formschlüssig), Bremse feststellen", 1, 4, 1),
        _r("Wartung", "Elektrisch: Stromschlag", "Generator erzeugt Spannung bei Drehung", 4, 2,
           "Kurzschlussschalter, Abdeckung, Arbeiten nur im spannungsfreien Zustand", 2, 4, 1, "EN 60204-1"),
        _r("Betrieb", "Elektrisch: Blitzschlag", "Gewitter", 3, 2, "Blitzschutz und Erdung des Turms", 2, 3, 1),
        _r("Wartung", "Thermisch: heiße Bremse", "Berühren nach einer Bremsung", 2, 3,
           "Abdeckung, Warnhinweis, Abkühlzeit in der Anleitung", 2, 2, 1),
        _r("Betrieb", "Lärm", "Dauerbetrieb nahe Wohnhaus", 1, 3, "Schallleistungspegel begrenzen, Abstand",
           1, 1, 2),
        _r("Betrieb", "Optisch: Schattenwurf", "Tief stehende Sonne", 1, 3, "Standortwahl, Abstand", 3, 1, 2),
    ]
    daten = {"zeilen": []}
    for z in zeilen:
        daten["zeilen"].append(neue_zeile(RISIKO, daten, **z))
    return daten


# ---------------------------------------------------------------- Normen-Checkliste (M47)
NORM_STATUS = ("offen", "in Arbeit", "erfüllt", "nicht anwendbar")
NORMEN_HINWEIS = ("Normenliste aus dem Gedächtnis zusammengestellt, ungeprüft – Ausgabestände und Anwendbarkeit "
                  "vor der Konformitätserklärung prüfen (Beuth, Amtsblatt der EU). „In Arbeit“ wird gesetzt, wenn im "
                  "Projekt ein passender Nachweis liegt; „erfüllt“ setzt nur der Mensch.")


def normen_bewerten(z: dict) -> tuple[str, str]:
    s = z.get("status", "offen")
    return s, {"erfüllt": GRUEN, "nicht anwendbar": GRAU, "in Arbeit": GELB}.get(s, ROT)


NORMEN = Art(
    "normen", "Normen-Checkliste", "N",
    [Spalte("id", "Nr.", 44, pdf=9),
     Spalte("norm", "Norm / Regel", 150, pdf=34),
     Spalte("titel", "Inhalt", 260, pdf=70),
     Spalte("bereich", "Bereich", 110, pdf=24),
     Spalte("status", "Status", 110, "wahl", NORM_STATUS, pdf=20),
     Spalte("nachweis", "Nachweis im Projekt", 0, pdf=60)],
    normen_bewerten, NORMEN_HINWEIS, leer={"status": "offen"})

# Norm, Inhalt, Bereich, Berechnungsarten/Objekte, die als Nachweis zählen
NORMEN_KWA = [
    ("IEC 61400-2", "Kleinwindenergieanlagen – Auslegungsanforderungen (vereinfachtes Lastmodell)", "Auslegung",
     ("lasten_iec", "rotorauslegung")),
    ("IEC 61400-12-1", "Leistungsverhalten – Messung der Leistungskurve", "Prüfung", ("inbetriebnahme",)),
    ("IEC 61400-11", "Schallmessverfahren", "Prüfung", ()),
    ("(EU) 2023/1230", "Maschinenverordnung – grundlegende Sicherheitsanforderungen, Konformität", "Recht",
     ("risiko",)),
    ("EN ISO 12100", "Risikobeurteilung und Risikominderung", "Sicherheit", ("risiko",)),
    ("EN 60204-1", "Elektrische Ausrüstung von Maschinen", "Elektrik", ()),
    ("2014/30/EU", "EMV-Richtlinie", "Recht", ()),
    ("2014/35/EU", "Niederspannungsrichtlinie (Wechselrichter, Steuerung)", "Recht", ()),
    ("VDE-AR-N 4105", "Erzeugungsanlagen am Niederspannungsnetz (NA-Schutz)", "Netz", ()),
    ("EN 1991-1-4", "Windlasten auf Tragwerke", "Statik", ("turm", "lasten_iec")),
    ("EN 1993-3-1", "Stahlbau – Türme und Maste", "Statik", ("turm",)),
    ("EN 1993-1-8", "Bemessung von Anschlüssen (Schweißnähte, Schrauben)", "Statik", ("schweissnaht",)),
    ("VDI 2230", "Systematische Berechnung hochbeanspruchter Schraubenverbindungen", "Berechnung", ("schrauben",)),
    ("DIN 743", "Tragfähigkeit von Wellen und Achsen", "Berechnung", ("welle",)),
    ("ISO 281", "Wälzlager – dynamische Tragzahl und Lebensdauer", "Berechnung", ("lager",)),
    ("DIN 7190", "Pressverbände", "Berechnung", ("pressverband",)),
    ("DIN 6892", "Passfederverbindungen", "Berechnung", ("passfeder",)),
    ("ISO 6336", "Tragfähigkeit von Stirnrädern", "Berechnung", ("getriebe",)),
    ("ISO 286 / ISO 2768", "Passungen und Allgemeintoleranzen", "Zeichnung", ("pruefplan",)),
    ("Landesbauordnung", "Baugenehmigung bzw. Verfahrensfreiheit je nach Höhe und Bundesland", "Recht", ()),
]


def normen_vorlage(nachweise: dict[str, list[str]]) -> dict:
    """`nachweise`: Berechnungsart oder Objektart → Liste von Nummern (B-003, RB-001 …)."""
    daten = {"zeilen": []}
    for norm, titel, bereich, quellen in NORMEN_KWA:
        nrn = [nr for q in quellen for nr in nachweise.get(q, [])]
        daten["zeilen"].append(neue_zeile(NORMEN, daten, norm=norm, titel=titel, bereich=bereich,
                                          status="in Arbeit" if nrn else "offen", nachweis=", ".join(nrn)))
    return daten


def normen_abgleichen(daten: dict, nachweise: dict[str, list[str]]) -> int:
    """Nachweise in einer bestehenden Liste ergänzen; Status nur von „offen“ auf „in Arbeit“. → Anzahl Änderungen."""
    quellen = {norm: q for norm, _, _, q in NORMEN_KWA}
    n = 0
    for z in daten.get("zeilen", []):
        nrn = [nr for q in quellen.get(z.get("norm"), ()) for nr in nachweise.get(q, [])]
        neu = [nr for nr in nrn if nr not in z.get("nachweis", "")]
        if neu:
            z["nachweis"] = ", ".join(x for x in [z.get("nachweis", "")] + neu if x)
            n += 1
        if nrn and z.get("status") == "offen":
            z["status"] = "in Arbeit"
    return n


# ---------------------------------------------------------------- Abweichungen (M45)
WIRKSAM = ("offen", "ja", "nein")
ABWEICHUNG_HINWEIS = ("Jede Abweichung bekommt Ursache, Maßnahme, Verantwortlichen und Termin. Abgeschlossen ist sie "
                      "erst, wenn die Wirksamkeit geprüft wurde (z. B. nächstes Los i. O.). n. i. O.-Punkte aus "
                      "Prüfplänen und Inbetriebnahme lassen sich übernehmen.")


def abweichung_bewerten(z: dict) -> tuple[str, str]:
    if z.get("wirksam") == "ja":
        return "abgeschlossen", GRUEN
    if z.get("wirksam") == "nein":
        return "unwirksam – neue Maßnahme", ROT
    if z.get("massnahme"):
        return "Maßnahme läuft", GELB
    return "offen", ROT


ABWEICHUNG = Art(
    "abweichung", "Abweichungen", "AW",
    [Spalte("id", "Nr.", 50, pdf=11),
     Spalte("datum", "Datum", 100, tipp="TT.MM.JJJJ", pdf=17),
     Spalte("bauteil", "Bauteil / Ort", 120, pdf=24),
     Spalte("beschreibung", "Abweichung", 180, pdf=38),
     Spalte("herkunft", "Herkunft", 100, pdf=20),
     Spalte("ursache", "Ursache", 160, pdf=34),
     Spalte("massnahme", "Maßnahme", 170, pdf=36),
     Spalte("verantwortlich", "Wer", 70, pdf=14),
     Spalte("termin", "Termin", 100, pdf=17),
     Spalte("wirksam", "Wirksam", 70, "wahl", WIRKSAM, "Wirksamkeit der Maßnahme geprüft?", pdf=14),
     Spalte("bewertung", "Status", 0, "berechnet", fn=lambda z: abweichung_bewerten(z)[0], pdf=0)],
    abweichung_bewerten, ABWEICHUNG_HINWEIS, leer={"wirksam": "offen"})

ART = {a.typ: a for a in (FMEA, RISIKO, NORMEN, ABWEICHUNG)}


def abweichungen_uebernehmen(daten: dict, funde: list[dict]) -> int:
    """`funde`: [{"schluessel", "datum", "bauteil", "beschreibung", "herkunft"}] – jeder Fund nur einmal."""
    vorhanden = {z.get("schluessel") for z in daten.get("zeilen", [])}
    n = 0
    for f in funde:
        if f["schluessel"] in vorhanden:
            continue
        daten.setdefault("zeilen", []).append(neue_zeile(ABWEICHUNG, daten, **f))
        vorhanden.add(f["schluessel"])
        n += 1
    return n
