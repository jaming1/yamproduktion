"""PDF-Berechnungsprotokoll (Lastenheft M17)."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .berechnungen.basis import formatiere

# Schrift mit Unicode-Zeichen (ρ, λ, η, ², √). Auf dem Mac ist Arial Unicode vorhanden;
# sonst DejaVu (Linux). Fallback: Helvetica (dann können Sonderzeichen fehlen).
_SCHRIFT_KANDIDATEN = [
    ("/System/Library/Fonts/Supplemental/Arial Unicode.ttf", None),
    ("/Library/Fonts/Arial Unicode.ttf", None),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
]


def _schrift() -> tuple[str, str]:
    for normal, fett in _SCHRIFT_KANDIDATEN:
        if Path(normal).exists():
            try:
                pdfmetrics.registerFont(TTFont("YamSans", normal))
                fett_name = "YamSans"
                if fett and Path(fett).exists():
                    pdfmetrics.registerFont(TTFont("YamSans-Bold", fett))
                    fett_name = "YamSans-Bold"
                # Familie registrieren, damit <b> in Absätzen funktioniert
                pdfmetrics.registerFontFamily("YamSans", normal="YamSans", bold=fett_name,
                                              italic="YamSans", boldItalic=fett_name)
                return "YamSans", fett_name
            except Exception:
                continue
    return "Helvetica", "Helvetica-Bold"


def _diagramm(d: dict, schrift: str):
    """Liniendiagramm (z. B. Leistungskurve) für das PDF."""
    from reportlab.graphics.charts.lineplots import LinePlot
    from reportlab.graphics.shapes import Drawing, String
    zeichnung = Drawing(170 * mm, 70 * mm)
    plot = LinePlot()
    plot.x, plot.y = 14 * mm, 10 * mm
    plot.width, plot.height = 150 * mm, 52 * mm
    plot.data = [list(zip(d["x"], d["y"]))]
    plot.lines[0].strokeColor = colors.HexColor("#1F6FB5")
    plot.lines[0].strokeWidth = 1.6
    for achse in (plot.xValueAxis, plot.yValueAxis):
        achse.labels.fontName = schrift
        achse.labels.fontSize = 7
    plot.xValueAxis.valueMin = 0
    plot.yValueAxis.valueMin = 0
    zeichnung.add(plot)
    zeichnung.add(String(14 * mm, 65 * mm, f"{d.get('titel', '')}  ({d.get('y_name', '')} über {d.get('x_name', '')})",
                         fontName=schrift, fontSize=9))
    return zeichnung


def protokoll_erstellen(ergebnis: dict, ziel: str | Path, projekt: str = "", nr: str = "") -> Path:
    ziel = Path(ziel)
    normal, fett = _schrift()
    basis = getSampleStyleSheet()
    s_text = ParagraphStyle("t", parent=basis["Normal"], fontName=normal, fontSize=10, leading=14, alignment=TA_LEFT)
    s_klein = ParagraphStyle("k", parent=s_text, fontSize=8.5, leading=11, textColor=colors.HexColor("#555555"))
    s_h1 = ParagraphStyle("h1", parent=s_text, fontName=fett, fontSize=16, leading=20, spaceAfter=4)
    s_h2 = ParagraphStyle("h2", parent=s_text, fontName=fett, fontSize=12, leading=16, spaceBefore=10, spaceAfter=4)

    def tabelle(daten, breiten, kopf=True):
        t = Table(daten, colWidths=breiten, hAlign="LEFT")
        stil = [
            ("FONTNAME", (0, 0), (-1, -1), normal),
            ("FONTSIZE", (0, 0), (-1, -1), 9.5),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#BBBBBB")),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]
        if kopf:
            stil += [("FONTNAME", (0, 0), (-1, 0), fett), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EEF4"))]
        t.setStyle(TableStyle(stil))
        return t

    P = lambda txt, st=s_text: Paragraph(str(txt), st)  # noqa: E731
    inhalt = []
    inhalt.append(P(f"Berechnungsprotokoll {nr}".strip(), s_h1))
    inhalt.append(P(ergebnis["titel"], s_h2))
    inhalt.append(P(f"Projekt: {projekt or '–'} &nbsp;&nbsp;·&nbsp;&nbsp; Erstellt: "
                    f"{datetime.now():%d.%m.%Y %H:%M} &nbsp;&nbsp;·&nbsp;&nbsp; Programm: YamProduktion", s_klein))

    inhalt.append(P("1. Eingaben", s_h2))
    daten = [["Größe", "Bezeichnung", "Wert", "Einheit"]]
    daten += [[g["symbol"], P(g["name"]), formatiere(g["wert"]), g["einheit"]] for g in ergebnis["eingaben"]]
    inhalt.append(tabelle(daten, [22 * mm, 85 * mm, 30 * mm, 25 * mm]))

    inhalt.append(P("2. Rechenweg", s_h2))
    for i, s in enumerate(ergebnis["schritte"], 1):
        g = s["ergebnis"]
        inhalt.append(P(f"<b>2.{i} {s['titel']}</b>"))
        inhalt.append(P(f"Formel: {s['formel']}"))
        inhalt.append(P(f"Eingesetzt: {s['einsetzen']}"))
        inhalt.append(P(f"Ergebnis: <b>{g['symbol']} = {formatiere(g['wert'])} {g['einheit']}</b>"))
        inhalt.append(Spacer(1, 4))

    inhalt.append(P("3. Ergebnisse", s_h2))
    daten = [["Größe", "Bezeichnung", "Wert", "Einheit"]]
    daten += [[g["symbol"], P(g["name"]), formatiere(g["wert"]), g["einheit"]] for g in ergebnis["ergebnisse"]]
    inhalt.append(tabelle(daten, [22 * mm, 85 * mm, 30 * mm, 25 * mm]))

    if ergebnis.get("diagramm"):
        inhalt.append(_diagramm(ergebnis["diagramm"], normal))
    for t in ergebnis.get("tabellen", []):
        inhalt.append(P(t["titel"], s_h2))
        daten = [[P(f"<b>{x}</b>", s_klein) for x in t["spalten"]]]
        for zeile in t["zeilen"]:
            daten.append([formatiere(w) if isinstance(w, (int, float)) and not isinstance(w, bool) else P(str(w), s_klein)
                          for w in zeile])
        breite = 170 * mm / len(t["spalten"])
        inhalt.append(tabelle(daten, [breite] * len(t["spalten"])))

    if ergebnis.get("pruefungen"):
        inhalt.append(P("4. Prüfungen", s_h2))
        daten = [["Prüfung", "Bedingung", "Ergebnis"]]
        for p in ergebnis["pruefungen"]:
            text = "erfüllt" if p["erfuellt"] else "NICHT erfüllt"
            if p.get("hinweis"):
                text += f" – {p['hinweis']}"
            daten.append([P(p["titel"]), P(p["bedingung"]), P(text)])
        t = tabelle(daten, [50 * mm, 52 * mm, 60 * mm])
        for zeile, p in enumerate(ergebnis["pruefungen"], 1):
            farbe = "#E3F4E1" if p["erfuellt"] else "#FBE3E1"
            t.setStyle(TableStyle([("BACKGROUND", (2, zeile), (2, zeile), colors.HexColor(farbe))]))
        inhalt.append(t)
        gesamt = all(p["erfuellt"] for p in ergebnis["pruefungen"])
        inhalt.append(Spacer(1, 4))
        inhalt.append(P(f"<b>Gesamtbewertung: {'alle Prüfungen erfüllt' if gesamt else 'mindestens eine Prüfung nicht erfüllt'}</b>"))

    if ergebnis.get("hinweise"):
        inhalt.append(P("5. Hinweise", s_h2))
        for h in ergebnis["hinweise"]:
            inhalt.append(P(f"• {h}"))

    if ergebnis.get("unbelegt"):
        inhalt.append(P("Unbelegt – vor dem Bau mit der Quelle prüfen", s_h2))
        t = Table([[P("<br/>".join("• " + x for x in ergebnis["unbelegt"]))]], colWidths=[170 * mm], hAlign="LEFT")
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FFF4D6")),
                               ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#D9A400"))]))
        inhalt.append(t)

    inhalt.append(P("6. Quellen", s_h2))
    for q in ergebnis.get("quellen", []):
        inhalt.append(P(f"• {q}"))

    inhalt.append(Spacer(1, 10))
    inhalt.append(P("Dieses Protokoll ist ein Auslegungswerkzeug. Vor dem Bau sind die Ergebnisse fachlich zu prüfen.", s_klein))

    doc = SimpleDocTemplate(str(ziel), pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
                            topMargin=18 * mm, bottomMargin=18 * mm,
                            title=f"Berechnungsprotokoll {nr} – {ergebnis['titel']}", author="YamProduktion")
    doc.build(inhalt)
    return ziel


# ================================================================ Produkt-Lastenheft (M13)
def _werkzeug():
    normal, fett = _schrift()
    basis = getSampleStyleSheet()
    s = {}
    s["text"] = ParagraphStyle("t", parent=basis["Normal"], fontName=normal, fontSize=10, leading=14)
    s["klein"] = ParagraphStyle("k", parent=s["text"], fontSize=8.5, leading=11, textColor=colors.HexColor("#555555"))
    s["h1"] = ParagraphStyle("h1", parent=s["text"], fontName=fett, fontSize=18, leading=22, spaceAfter=4)
    s["h2"] = ParagraphStyle("h2", parent=s["text"], fontName=fett, fontSize=13, leading=17, spaceBefore=12, spaceAfter=4)
    s["h3"] = ParagraphStyle("h3", parent=s["text"], fontName=fett, fontSize=10.5, leading=14, spaceBefore=6, spaceAfter=2)

    def tabelle(daten, breiten):
        t = Table(daten, colWidths=breiten, hAlign="LEFT", repeatRows=1)
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), normal), ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("VALIGN", (0, 0), (-1, -1), "TOP"), ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#BBBBBB")),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("FONTNAME", (0, 0), (-1, 0), fett), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EEF4")),
        ]))
        return t
    return s, tabelle


def _x(text) -> str:
    """Text für Paragraph absichern (& < > sind Steuerzeichen)."""
    return str(text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def lastenheft_erstellen(projekt, ziel: str | Path) -> Path:
    """Produkt-Lastenheft aus dem Produktmodell: Ideen, Anforderungen, Eigenschaften, Funktionen, Konzept."""
    from . import triz
    ziel = Path(ziel)
    s, tabelle = _werkzeug()
    P = lambda txt, st="text": Paragraph(txt, s[st])  # noqa: E731
    p = projekt
    inhalt = [P(f"Produkt-Lastenheft – {_x(p.produkt or p.name)}", "h1"),
              P(f"Projekt: {_x(p.name)} &nbsp;·&nbsp; Stand: {datetime.now():%d.%m.%Y %H:%M} "
                f"&nbsp;·&nbsp; Programm: YamProduktion", "klein")]
    phasen = " &nbsp;·&nbsp; ".join(f"{ph.nr} {ph.status}" for ph in p.phasen()[:4])
    inhalt.append(P(f"Phasen: {phasen}", "klein"))

    # 1. Ideen
    inhalt.append(P("1. Idee und Ziel", "h2"))
    ideen = p.liste("idee")
    if not ideen:
        inhalt.append(P("– noch keine Idee erfasst –", "klein"))
    for i in ideen:
        inhalt.append(P(f"{i['nr']} {_x(i['titel'])}", "h3"))
        for feld, name in (("problem", "Problem"), ("nutzen", "Nutzen"), ("ier", "Ideales Endergebnis"),
                           ("ressourcen", "Vorhandene Ressourcen"), ("beschreibung", "Beschreibung")):
            if i[feld].strip():
                inhalt.append(P(f"<b>{name}:</b> {_x(i[feld])}"))

    # 2. Anforderungen nach Priorität, 3. Eigenschaften
    def anf_tabelle(liste):
        daten = [["Nr", "Beschreibung", "Zielwert", "Einheit", "Status"]]
        for a in liste:
            wert = formatiere(a.zielwert) if a.zielwert is not None else "–"
            daten.append([a.nr, P(_x(a.text)), wert, a.einheit, a.status])
        return tabelle(daten, [16 * mm, 90 * mm, 22 * mm, 18 * mm, 24 * mm])

    alle = p.anforderungen()
    inhalt.append(P("2. Anforderungen", "h2"))
    for prio in ("Muss", "Soll", "Kann"):
        liste = [a for a in alle if a.art == "Anforderung" and a.prioritaet == prio]
        if liste:
            inhalt.append(P(f"{prio}-Anforderungen", "h3"))
            inhalt.append(anf_tabelle(liste))
    inhalt.append(P("3. Eigenschaften und Attribute", "h2"))
    eig = [a for a in alle if a.art != "Anforderung"]
    inhalt.append(anf_tabelle(eig) if eig else P("– keine –", "klein"))

    # 4. Funktionsstruktur
    inhalt.append(P("4. Funktionsstruktur", "h2"))
    baum = p.funktionsbaum()
    if not baum:
        inhalt.append(P("– noch keine Funktionen –", "klein"))
    for tiefe, f in baum:
        erfuellt = [b.nr for b in p.haengt_ab_von("funktion", f["id"]) if b.typ == "anforderung"]
        zusatz = f" <font size=8 color='#555555'>(erfüllt {', '.join(erfuellt)})</font>" if erfuellt else ""
        st = ParagraphStyle(f"f{tiefe}", parent=s["text"], leftIndent=tiefe * 8 * mm)
        inhalt.append(Paragraph(f"{f['nr']} {'<b>' if tiefe == 0 else ''}{_x(f['name'])}{'</b>' if tiefe == 0 else ''}"
                                f"{zusatz}", st))

    # 5. TRIZ
    widersprueche = p.liste("widerspruch")
    if widersprueche:
        inhalt.append(P("5. Widersprüche und Lösungsideen (TRIZ)", "h2"))
        for w in widersprueche:
            if w["art"] == "technisch" and w["verbessern"]:
                kopf = (f"{w['nr']} {_x(w['beschreibung'])} – verbessern: {_x(triz.parameter_name(w['verbessern']))}, "
                        f"verschlechtert sich: {_x(triz.parameter_name(w['verschlechtern']))}")
            else:
                kopf = f"{w['nr']} {_x(w['beschreibung'])} – physikalischer Widerspruch"
            inhalt.append(P(kopf, "h3"))
            for l in p.liste("loesungsidee", "widerspruch_id=?", (w["id"],)):
                prinzip = f"Prinzip {l['prinzip']} {_x(triz.prinzip(l['prinzip'])['name'])}: " if l["prinzip"] else ""
                inhalt.append(P(f"• {l['nr']} {prinzip}{_x(l['text'])}"))
        inhalt.append(P(f"Quelle: {_x(triz.quelle())}", "klein"))

    # 6. Konzept
    inhalt.append(P("6. Konzept", "h2"))
    varianten = p.liste("variante")
    teil = p.teilfunktionen()
    if varianten and teil:
        inhalt.append(P("Morphologischer Kasten", "h3"))
        loes = {l["id"]: l["text"] for f in teil for l in p.loesungen(f["id"])}
        breite = (170 - 40) / len(varianten)
        daten = [["Teilfunktion"] + [f"{v['nr']}{' ★' if v['gewaehlt'] else ''}" for v in varianten]]
        wahl = {v["id"]: p.variante_wahl(v["id"]) for v in varianten}
        for f in teil:
            daten.append([P(_x(f["name"]))] + [P(_x(loes.get(wahl[v["id"]].get(f["id"]), "–"))) for v in varianten])
        inhalt.append(tabelle(daten, [40 * mm] + [breite * mm] * len(varianten)))
    kriterien = p.kriterien()
    if varianten and kriterien:
        inhalt.append(P("Nutzwertanalyse (Punkte 0 bis 10, gewichtet)", "h3"))
        b = p.bewertungen()
        n = p.nutzwerte()
        breite = (170 - 55 - 18) / len(varianten)
        daten = [["Kriterium", "Gewicht"] + [v["nr"] for v in varianten]]
        for k in kriterien:
            daten.append([P(_x(k["name"])), formatiere(k["gewicht"], 3)] +
                         [formatiere(b[(v["id"], k["id"])], 3) if (v["id"], k["id"]) in b else "–" for v in varianten])
        daten.append(["Nutzwert", ""] + [formatiere(n[v["id"]], 3) for v in varianten])
        t = tabelle(daten, [55 * mm, 18 * mm] + [breite * mm] * len(varianten))
        t.setStyle(TableStyle([("BACKGROUND", (0, len(daten) - 1), (-1, len(daten) - 1), colors.HexColor("#F2F2F2"))]))
        inhalt.append(t)
    k = p.gewaehltes_konzept()
    inhalt.append(Spacer(1, 6))
    if k:
        inhalt.append(P(f"<b>Gewähltes Konzept: {k['nr']} {_x(k['name'])}</b> (Status: {k['status']})"))
        inhalt.append(P(f"<b>Begründung:</b> {_x(k['begruendung'])}"))
    elif not varianten:
        inhalt.append(P("– noch keine Konzeptvarianten –", "klein"))
    else:
        inhalt.append(P("Es ist noch keine Variante ausgewählt.", "klein"))

    inhalt.append(Spacer(1, 10))
    inhalt.append(P("Erzeugt aus dem Produktmodell. Maßgeblich ist der Stand im Projekt; Objekte mit Status "
                    "„neu prüfen“ sind noch nicht abgesichert.", "klein"))
    doc = SimpleDocTemplate(str(ziel), pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
                            topMargin=18 * mm, bottomMargin=18 * mm,
                            title=f"Produkt-Lastenheft – {p.produkt or p.name}", author="YamProduktion")
    doc.build(inhalt)
    return ziel


def stueckliste_erstellen(ergebnis, ziel: str | Path, name: str, nr: str = "", projekt: str = "") -> Path:
    """Stückliste einer Baugruppe als PDF (Lastenheft M32): Positionen, Massen, Schwerpunkt, Hinweise."""
    ziel = Path(ziel)
    s, tabelle = _werkzeug()
    P = lambda txt, st="text": Paragraph(txt, s[st])  # noqa: E731
    inhalt = [P(f"Stückliste {_x(nr)} {_x(name)}", "h1"),
              P(f"Projekt: {_x(projekt)} &nbsp;·&nbsp; Stand: {datetime.now():%d.%m.%Y %H:%M}", "klein"),
              Spacer(1, 6)]
    daten = [["Pos", "Menge", "Benennung", "Sachnummer / Norm", "Werkstoff", "Einzel kg", "Gesamt kg"]]
    for p in ergebnis.stueckliste:
        daten.append([str(p.pos), str(p.menge), P(_x(p.benennung)), P(_x(p.sachnummer)), P(_x(p.werkstoff)),
                      formatiere(p.einzelmasse) if p.einzelmasse is not None else "–",
                      formatiere(p.gesamtmasse) if p.gesamtmasse is not None else "–"])
    inhalt.append(tabelle(daten, [10 * mm, 13 * mm, 42 * mm, 38 * mm, 31 * mm, 18 * mm, 18 * mm]))
    sx, sy, sz = ergebnis.schwerpunkt
    inhalt += [Spacer(1, 8),
               P(f"<b>Gesamtmasse {formatiere(ergebnis.masse)} kg</b> &nbsp;·&nbsp; Schwerpunkt "
                 f"x = {formatiere(sx)}, y = {formatiere(sy)}, z = {formatiere(sz)} mm")]
    if ergebnis.ohne_masse:
        inhalt.append(P("Ohne Masse (nicht in der Summe): " + _x(", ".join(ergebnis.ohne_masse)), "klein"))
    if any(p.art == "Normteil" for p in ergebnis.stueckliste):
        inhalt.append(P("Normteile: Maße aus dem Tabellenbuch, nicht geprüft – vor der Bestellung mit dem Katalog "
                        "abgleichen. Lagermassen genähert.", "klein"))
    doc = SimpleDocTemplate(str(ziel), pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
                            topMargin=18 * mm, bottomMargin=18 * mm, title=f"Stückliste {name}",
                            author="YamProduktion")
    doc.build(inhalt)
    return ziel
