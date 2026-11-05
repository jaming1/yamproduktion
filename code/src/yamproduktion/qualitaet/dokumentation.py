"""Technische Dokumentation als ein PDF-Paket (S16).

Jedes Kapitel wird mit den vorhandenen PDF-Funktionen einzeln erzeugt und dann mit pypdf zu einer Datei mit
Lesezeichen zusammengefügt. Fehlende Kapitel stehen rot im Inhaltsverzeichnis.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Callable

REIHENFOLGE = ("Lastenheft", "Normen-Checkliste", "Risikobeurteilung", "FMEA", "Berechnungen", "Zeichnungen",
               "Stücklisten", "Prüfpläne", "Montageanleitungen", "Inbetriebnahme und Abnahme", "Wartungsplan")


def kapitel_planen(p) -> list[tuple[str, list[tuple[str, Callable[[Path], Path]]], str]]:
    """[(Kapitel, [(Unterpunkt, erzeuge(ziel) → Pfad)], Hinweis wenn leer)]"""
    from .. import pdf as PDF
    from ..cad import zeichnung as Z
    name = p.name
    k = []
    k.append(("Lastenheft", [("Anforderungen", lambda z: PDF.lastenheft_erstellen(p, z))], ""))
    for typ, titel_, leer in (("normen", "Normen-Checkliste", "keine Normen-Checkliste angelegt"),
                              ("risiko", "Risikobeurteilung", "keine Risikobeurteilung angelegt (EN ISO 12100)"),
                              ("fmea", "FMEA", "keine FMEA angelegt")):
        k.append((titel_, [(f"{d['nr']} {d['name']}", lambda z, d=d, typ=typ: PDF.qdok_erstellen(typ, d, z, name))
                           for d in p.qdoks(typ)], leer))
    neueste = {}
    for b in p.berechnungen():                           # neueste zuerst: je Art und Titel die aktuelle
        neueste.setdefault((b.typ, b.titel), b)
    k.append(("Berechnungen", [(f"{b.nr} {b.titel}", lambda z, b=b: PDF.protokoll_erstellen(
        b.ergebnis, z, name, f"{b.nr} (Version {b.version})")) for b in sorted(neueste.values(), key=lambda b: b.nr)],
        "keine Berechnungen gespeichert"))
    zeichnungen = [(f"{t['nr']} {t['name']}", lambda z, t=t: Z.als_pdf(p.zeichnung("teil", t["id"]), z))
                   for t in p.teile()]
    zeichnungen += [(f"{g['nr']} {g['name']}", lambda z, g=g: Z.als_pdf(p.zeichnung("baugruppe", g["id"]), z))
                    for g in p.baugruppen()]
    k.append(("Zeichnungen", zeichnungen, "keine Bauteile angelegt"))

    def stueckliste(z, g):
        r = p.baugruppe_bauen(g["definition"])
        return PDF.stueckliste_erstellen(r, z, g["name"], g["nr"], name)
    k.append(("Stücklisten", [(f"{g['nr']} {g['name']}", lambda z, g=g: stueckliste(z, g)) for g in p.baugruppen()],
              "keine Baugruppen angelegt"))
    k.append(("Prüfpläne", [(f"{pp['nr']} {pp['name']}", lambda z, pp=pp: PDF.pruefprotokoll_erstellen(
        pp, z, name, p.teil(pp["teil_id"])["name"])) for pp in p.pruefplaene()], "keine Prüfpläne angelegt"))
    k.append(("Montageanleitungen", [(f"{mp['nr']} {mp['name']}", lambda z, mp=mp: montage(p, mp, z))
                                     for mp in p.montageplaene()], "keine Montagepläne angelegt"))
    ib = []
    for x in p.inbetriebnahmen():
        ib.append((f"{x['nr']} Abnahmeprotokoll", lambda z, x=x: PDF.abnahmeprotokoll_erstellen(x, z, name)))
        if x["daten"].get("messung"):
            ib.append((f"{x['nr']} Messprotokoll", lambda z, x=x: PDF.messprotokoll_erstellen(x, z, name)))
    k.append(("Inbetriebnahme und Abnahme", ib, "keine Inbetriebnahme angelegt"))
    k.append(("Wartungsplan", [(f"{w['nr']} {w['name']}", lambda z, w=w: PDF.wartungsplan_erstellen(w, z, name))
                               for w in p.wartungsplaene()], "kein Wartungsplan angelegt"))
    return k


montage: Callable = None     # (projekt, montageplan, ziel) → Pfad; setzt die Oberfläche (braucht 3D-Bilder)


def _montage_ohne_bilder(p, mp, ziel):
    from .. import pdf as PDF
    from ..montage import montageplan as M
    g = p.baugruppe(mp["baugruppe_id"])
    r = p.baugruppe_bauen(g["definition"])
    return PDF.montageanleitung_erstellen(g, M.nummerieren(mp["daten"]), {}, r.stueckliste, ziel, p.name)


def erstellen(p, ziel: str | Path, ersteller: str = "", fortschritt: Callable[[str], None] | None = None,
              montage_pdf: Callable | None = None) -> tuple[Path, list[tuple[str, int | None, str]]]:
    """Gesamt-PDF erzeugen. → (Pfad, Inhaltsverzeichnis [(Titel, Seite, Hinweis)])."""
    from pypdf import PdfReader, PdfWriter
    from .. import pdf as PDF
    global montage
    montage = montage_pdf or _montage_ohne_bilder
    ziel = Path(ziel)
    plan = kapitel_planen(p)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        teile: list[tuple[str, str, Path]] = []
        fehler: dict[str, list[str]] = {}
        for kapitel, punkte, _ in plan:
            for i, (titel_, erzeuge) in enumerate(punkte):
                if fortschritt:
                    fortschritt(f"{kapitel}: {titel_}")
                datei = tmp / f"{len(teile):03d}_{i}.pdf"
                try:
                    teile.append((kapitel, titel_, Path(erzeuge(datei))))
                except Exception as exc:          # ein defektes Kapitel darf das Paket nicht verhindern
                    fehler.setdefault(kapitel, []).append(f"{titel_}: {exc}")
        # Seitenzahlen: Deckblatt hat eine Seite (bei sehr vielen Kapiteln zwei – dann neu zählen)
        seiten = [len(PdfReader(str(d)).pages) for _, _, d in teile]
        for deckblatt_seiten in (1, 2, 3):
            inhalt, seite, n = [], deckblatt_seiten + 1, 0
            for kapitel, punkte, leer in plan:
                eigene = [(t, s) for (k, t, _), s in zip(teile, seiten) if k == kapitel]
                if not eigene:
                    hinweis = leer
                elif len(eigene) == 1:
                    hinweis = eigene[0][0]
                else:
                    hinweis = f"{len(eigene)} Dokumente: " + ", ".join(t.split()[0] for t, _ in eigene)
                hinweis = "; ".join(fehler.get(kapitel, [])) or hinweis
                inhalt.append((kapitel, seite if eigene else None, ("Fehler: " if kapitel in fehler else "") + hinweis))
                seite += sum(s for _, s in eigene)
                n += len(eigene)
            deck = PDF.deckblatt_erstellen(tmp / "deckblatt.pdf", p.name, inhalt, ersteller)
            if len(PdfReader(str(deck)).pages) == deckblatt_seiten:
                break
        w = PdfWriter()
        w.append(str(deck), outline_item="Deckblatt und Inhalt")
        letztes = None
        oben = None
        for (kapitel, titel_, datei) in teile:
            start = len(w.pages)
            w.append(str(datei))
            if kapitel != letztes:
                oben = w.add_outline_item(kapitel, start)
                letztes = kapitel
            w.add_outline_item(titel_, start, parent=oben)
        w.add_metadata({"/Title": f"Technische Dokumentation {p.name}", "/Author": ersteller or "YamProduktion"})
        with open(ziel, "wb") as f:
            w.write(f)
    return ziel, inhalt
