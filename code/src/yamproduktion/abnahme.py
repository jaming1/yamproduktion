"""Abnahme Version 1 (MS15): die 11 Abnahmekriterien aus dem Lastenheft (Abschnitt 6) am Projekt prüfen.

Jedes Kriterium sagt, was erfüllt ist (Nachweise), was fehlt und wo man es erledigt. Zwei Kriterien
(Buchsuche mit den eigenen Scans, Lauf auf dem Mac) kann nur Yamine bestätigen.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .berechnungen import ARTEN
from .modell import NEU_PRUEFEN, Projekt

ERFUELLT, OFFEN, BESTAETIGEN = "erfüllt", "offen", "bestätigen"

# Lastenheft M18–M25 → Berechnungsarten
MUSS_BERECHNUNGEN = {
    "M18 Windkraft": ["rotorauslegung", "ertrag"],
    "M19 Lastannahmen": ["lasten_iec"],
    "M20 Antriebsstrang": ["antrieb"],
    "M21 Getriebe": ["getriebe"],
    "M22 Welle": ["welle"],
    "M23 Lager": ["lager"],
    "M24 Verbindungen": ["schrauben", "passfeder", "pressverband", "schweissnaht"],
    "M25 Turm & Fundament": ["turm"],
}
OHNE_ARBEITSPLAN = {"montageplatte"}       # Hilfsmittel, kein Teil der Anlage


@dataclass
class Kriterium:
    nr: int
    titel: str
    seite: str                                  # Navigationsschlüssel, wo es erledigt wird
    nachweise: list[str] = field(default_factory=list)
    fehlt: list[str] = field(default_factory=list)
    von_hand: bool = False                      # nur durch Yamine bestätigbar
    bestaetigt: str = ""                        # Datum der Bestätigung

    @property
    def stand(self) -> str:
        if self.fehlt:
            return OFFEN
        if self.von_hand and not self.bestaetigt:
            return BESTAETIGEN
        return ERFUELLT


def _doku(p: Projekt, art: str, bezug: str | None = None) -> dict | None:
    liste = [d for d in p.dokumente(art) if bezug is None or d["bezug"] == bezug]
    return liste[-1] if liste else None


def _anz(n: int, einzahl: str, mehrzahl: str) -> str:
    return f"{n} {einzahl if n == 1 else mehrzahl}"


def _datum(iso: str) -> str:
    d = iso[:10].split("-")
    return f"{d[2]}.{d[1]}.{d[0]}" if len(d) == 3 else iso


def _pdf_nachweis(k: Kriterium, p: Projekt, art: str, name: str, bezug: str | None = None):
    d = _doku(p, art, bezug)
    if d:
        k.nachweise.append(f"{name} erzeugt am {_datum(d['datum'])}: {d['datei']}")
    else:
        k.fehlt.append(f"{name} noch nicht als PDF erzeugt.")


def _verlauf_texte(p: Projekt, muster: str) -> list[tuple[str, int]]:
    return p._db.execute("SELECT objekt_typ, objekt_id FROM verlauf WHERE text LIKE ?", (muster,)).fetchall()


def pruefen(p: Projekt, buecher: int = 0) -> list[Kriterium]:
    """Alle 11 Kriterien. `buecher`: Anzahl Bücher in der Bibliothek (liegt außerhalb des Projekts)."""
    bestaetigt = p.abnahme_bestaetigungen()
    doku = _doku(p, "technische_doku")
    k: list[Kriterium] = []

    # 1 Idee, TRIZ, Anforderungen, Produkt-Lastenheft
    a = Kriterium(1, "Idee, TRIZ-Analyse und Anforderungen erfasst; Produkt-Lastenheft als PDF", "uebersicht")
    ideen, widersprueche = p.liste("idee"), p.liste("widerspruch")
    muss = [x for x in p.anforderungen() if x.art == "Anforderung" and x.prioritaet == "Muss"]
    (a.nachweise if ideen else a.fehlt).append(_anz(len(ideen), "Idee", "Ideen") if ideen else "Noch keine Idee erfasst.")
    (a.nachweise if widersprueche else a.fehlt).append(
        _anz(len(widersprueche), "technischer Widerspruch", "technische Widersprüche") + " (TRIZ)" if widersprueche else "Noch keine TRIZ-Analyse.")
    (a.nachweise if muss else a.fehlt).append(
        f"{len(muss)} Muss-Anforderungen" if muss else "Noch keine Muss-Anforderung.")
    _pdf_nachweis(a, p, "lastenheft", "Produkt-Lastenheft")
    k.append(a)

    # 2 Konzept mit morphologischem Kasten und Nutzwertanalyse
    a = Kriterium(2, "Konzept mit morphologischem Kasten und Nutzwertanalyse ausgewählt", "konzept")
    loesungen = p._db.execute("SELECT COUNT(*) FROM loesung").fetchone()[0]
    if loesungen:
        a.nachweise.append(f"Morphologischer Kasten mit {loesungen} Lösungen")
    else:
        a.fehlt.append("Der morphologische Kasten ist leer.")
    hindernisse = p.phase_hindernisse("P3")
    a.fehlt += [h for h in hindernisse if "Aufgabe" not in h]
    g = p.gewaehltes_konzept()
    if g:
        a.nachweise.append(f"Gewählt: {g['nr']} {g.get('name') or ''}".strip())
    k.append(a)

    # 3 Muss-Berechnungen mit Protokoll und erfüllten Sicherheiten
    a = Kriterium(3, "Alle Muss-Berechnungen (M18–M25) durchgeführt, Protokolle als PDF, Sicherheiten erfüllt",
                  "berechnungen")
    alle = p.berechnungen()
    direkt = any(b.typ == "antrieb" and "Direkt" in str(b.eingaben.get("bauart", "")) for b in alle)
    for gruppe, typen in MUSS_BERECHNUNGEN.items():
        for typ in typen:
            name = ARTEN[typ]["kurz"] if typ in ARTEN else typ
            if typ == "getriebe" and direkt:
                a.nachweise.append(f"{gruppe}: {name} entfällt (Direktantrieb gewählt)")
                continue
            liste = [b for b in alle if b.typ == typ]
            if not liste:
                a.fehlt.append(f"{gruppe}: {name} fehlt.")
                continue
            b = liste[-1]
            if b.status == NEU_PRUEFEN:
                a.fehlt.append(f"{b.nr} {name} muss neu berechnet werden.")
            elif not b.erfuellt:
                a.fehlt.append(f"{b.nr} {name}: mindestens eine Sicherheit ist nicht erfüllt.")
            elif not any(d and d["datum"] >= b.geaendert for d in (_doku(p, "protokoll", b.nr), doku)):
                a.fehlt.append(f"{b.nr} {name}: Protokoll der aktuellen Version noch nicht als PDF erzeugt.")
            else:
                a.nachweise.append(f"{gruppe}: {b.nr} {name} erfüllt")
    k.append(a)

    # 4 Eigenteile im CAD, Gesamtbaugruppe, Zeichnungen und Stückliste exportiert
    a = Kriterium(4, "Eigenteile im eigenen CAD, Gesamtbaugruppe, Zeichnungen und Stückliste exportiert", "bauteile")
    teile = [t for t in p.teile() if t["vorlage"] not in OHNE_ARBEITSPLAN]
    gruppen = p.baugruppen()
    (a.nachweise if teile else a.fehlt).append(_anz(len(teile), "Eigenteil", "Eigenteile") if teile else "Noch kein Eigenteil.")
    (a.nachweise if gruppen else a.fehlt).append(
        _anz(len(gruppen), "Baugruppe", "Baugruppen") if gruppen else "Noch keine Baugruppe.")
    a.fehlt += [f"{t['nr']} {t['name']} muss neu geprüft werden." for t in teile if t["status"] == NEU_PRUEFEN]
    zeichnungen = p.dokumente("zeichnung_pdf") + p.dokumente("zeichnung_dxf")
    if zeichnungen:
        a.nachweise.append(_anz(len(zeichnungen), "Zeichnung", "Zeichnungen") + " exportiert")
    elif doku:
        a.nachweise.append("Zeichnungen in der technischen Dokumentation")
    else:
        a.fehlt.append("Noch keine Zeichnung exportiert.")
    _pdf_nachweis(a, p, "stueckliste", "Stückliste")
    k.append(a)

    # 5 Wertänderung markiert betroffene Objekte
    a = Kriterium(5, "Eine Wertänderung markiert alle betroffenen Berechnungen, Bauteile und Pläne", "anforderungen")
    markiert = _verlauf_texte(p, "Neu prüfen, weil%")
    arten = {t for t, _ in markiert}
    if markiert:
        a.nachweise.append(f"{len(markiert)} Markierungen „neu prüfen“ ausgelöst ({', '.join(sorted(arten))})")
    else:
        a.fehlt.append("Noch keine Wertänderung durchgespielt (z. B. Nennleistung 5 → 10 kW).")
    offen = p.neu_zu_pruefen()
    if offen:
        a.fehlt.append(f"Noch {len(offen)} Objekte „neu prüfen“: " + ", ".join(b.nr for b in offen[:8])
                       + (" …" if len(offen) > 8 else ""))
    elif markiert:
        a.nachweise.append("Alle markierten Objekte wurden neu geprüft")
    k.append(a)

    # 6 Arbeitsplan mit Kosten je Eigenteil, Gesamtkosten
    a = Kriterium(6, "Arbeitsplan mit Kosten für jedes Eigenteil; Gesamtkosten berechnet", "arbeitsplaene")
    gut = 0
    for t in teile:
        ap = p.arbeitsplan_von_teil(t["id"])
        if not ap:
            a.fehlt.append(f"{t['nr']} {t['name']}: kein Arbeitsplan.")
        elif not ap.get("kosten"):
            a.fehlt.append(f"{ap['nr']} ({t['nr']}): keine Kosten.")
        else:
            gut += 1
    if gut:
        a.nachweise.append(f"{gut} von {len(teile)} Eigenteilen mit Arbeitsplan und Kosten")
    elif not teile:
        a.fehlt.append("Noch kein Eigenteil.")
    if _doku(p, "kalkulation"):
        a.nachweise.append("Gesamtkalkulation als PDF")
    elif any(x.get("kostenart") == "Bauteile" for x in p.kosten_posten()):
        a.nachweise.append("Gesamtkosten in Kosten Plan/Ist übernommen")
    else:
        a.fehlt.append("Gesamtkosten noch nicht berechnet (Kosten & Anfragen › Kalkulation).")
    k.append(a)

    # 7 Montageplan mit Montageplatte und Anleitung
    a = Kriterium(7, "Montageplan mit Montageplatte und Montageanleitung (PDF)", "montage")
    mps, platten = p.montageplaene(), p.montageplatten()
    (a.nachweise if mps else a.fehlt).append(_anz(len(mps), "Montageplan", "Montagepläne") if mps else "Noch kein Montageplan.")
    (a.nachweise if platten else a.fehlt).append(
        f"Montageplatte {platten[0]['nr']}" if platten else "Noch keine Montageplatte angelegt.")
    _pdf_nachweis(a, p, "montageanleitung", "Montageanleitung")
    k.append(a)

    # 8 Inbetriebnahme ausgefüllt, Abnahmeprotokoll
    a = Kriterium(8, "Inbetriebnahme-Checkliste ausgefüllt, Abnahmeprotokoll erzeugt", "inbetriebnahme")
    from .betrieb import inbetriebnahme as IB
    ibs = p.inbetriebnahmen()
    ab = [ib for ib in ibs if IB.auswerten(ib["daten"])["abgenommen"]]
    if ab:
        a.nachweise.append(f"{ab[0]['nr']} abgenommen")
    else:
        a.fehlt.append("Noch keine vollständig ausgefüllte und abgenommene Inbetriebnahme."
                       if ibs else "Noch keine Inbetriebnahme-Checkliste.")
    _pdf_nachweis(a, p, "abnahmeprotokoll", "Abnahmeprotokoll")
    k.append(a)

    # 9 FMEA, Risikobeurteilung, Normen, technische Doku
    a = Kriterium(9, "FMEA, Risikobeurteilung und Normen-Checkliste ausgefüllt; technische Dokumentation als PDF",
                  "doku")
    for typ, name in (("fmea", "FMEA"), ("risiko", "Risikobeurteilung"), ("normen", "Normen-Checkliste")):
        liste = p.liste(typ)
        (a.nachweise if liste else a.fehlt).append(f"{name}: {liste[0]['nr']}" if liste else f"{name} fehlt.")
    _pdf_nachweis(a, p, "technische_doku", "Technische Dokumentation")
    k.append(a)

    # 10 Buchsuche (nur mit den echten Scans prüfbar)
    a = Kriterium(10, "Die Buchsuche findet zu einer Fachfrage die richtige Seite in den eigenen Scans", "bibliothek",
                  von_hand=True)
    if buecher:
        a.nachweise.append(_anz(buecher, "Buch", "Bücher") + " in der Bibliothek")
    else:
        a.fehlt.append("Noch kein Buch in der Bibliothek.")
    k.append(a)

    # 11 Lauf auf dem Mac
    k.append(Kriterium(11, "Die App läuft offline auf Yamines Mac ohne Absturz durch den ganzen Ablauf",
                       "uebersicht", von_hand=True))

    for x in k:
        if x.von_hand and str(x.nr) in bestaetigt:
            b = bestaetigt[str(x.nr)]
            x.bestaetigt = _datum(b["datum"])
            x.nachweise.append(f"Bestätigt am {x.bestaetigt}" + (f": {b['notiz']}" if b.get("notiz") else ""))
    return k


def zusammenfassung(kriterien: list[Kriterium]) -> tuple[int, int]:
    """(erfüllt, gesamt)"""
    return sum(1 for x in kriterien if x.stand == ERFUELLT), len(kriterien)
