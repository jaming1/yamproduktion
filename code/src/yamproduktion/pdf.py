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


def _dokument(ziel: Path, titel_: str, inhalt: list, quer: bool = False) -> Path:
    from reportlab.lib.pagesizes import landscape
    doc = SimpleDocTemplate(str(ziel), pagesize=landscape(A4) if quer else A4, leftMargin=18 * mm,
                            rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm, title=titel_,
                            author="YamProduktion")
    doc.build(inhalt)
    return ziel


def _euro(x) -> str:
    return "–" if x is None else f"{x:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def arbeitsplan_erstellen(teil: dict, plan: dict, kalk, ziel: str | Path, projekt: str = "") -> Path:
    """Arbeitsplan eines Bauteils (Lastenheft M34, M35, S10) mit Rechenweg der Zeiten und Kosten."""
    from .fertigung.arbeitsplan import ARTEN, SCHAETZ_HINWEIS
    from .fertigung.schnittdaten import HINWEIS as SCHNITT_HINWEIS, SPANNEN, ZUSCHLAG
    ziel = Path(ziel)
    s, tabelle = _werkzeug()
    P = lambda txt, st="text": Paragraph(txt, s[st])  # noqa: E731
    inhalt = [P(f"Arbeitsplan {_x(teil['nr'])} {_x(teil['name'])}", "h1"),
              P(f"Projekt: {_x(projekt)} &nbsp;·&nbsp; Stand: {datetime.now():%d.%m.%Y %H:%M} &nbsp;·&nbsp; "
                f"Losgröße {kalk.losgroesse} &nbsp;·&nbsp; "
                f"{'Fremdfertigung' if plan.get('fertigung') == 'fremd' else 'Eigenfertigung'}", "klein"),
              P("Rohteil", "h2"),
              P(f"{_x(kalk.rohteil_text)} &nbsp;·&nbsp; Werkstoff {_x(plan['rohteil'].get('werkstoff', ''))} "
                f"&nbsp;·&nbsp; Masse {formatiere(kalk.rohteil_masse)} kg"),
              P("Arbeitsgänge", "h2")]
    daten = [["AG", "Arbeitsgang", "Beschreibung", "Maschine", "t_r min", "t_e min"]]
    for g in kalk.gaenge:
        daten.append([str(g.nr), ARTEN.get(g.art, (g.art,))[0], P(_x(g.text)), g.maschine, formatiere(g.tr),
                      formatiere(g.te) + (" *" if g.von_hand else "")])
    daten.append(["", "", "Summe", "", formatiere(kalk.tr_summe), formatiere(kalk.te_summe)])
    inhalt.append(tabelle(daten, [10 * mm, 30 * mm, 60 * mm, 32 * mm, 16 * mm, 18 * mm]))
    inhalt.append(P(f"t_e = t_h · (1 + {formatiere(ZUSCHLAG)}) + {formatiere(SPANNEN)} min (Neben- und Verteilzeit, "
                    "Spannen – Richtwert). * = Zeit von Hand eingetragen.", "klein"))
    inhalt.append(P("Rechenweg der Hauptzeiten", "h2"))
    inhalt.append(P("n = v_c · 1000 / (π · d) &nbsp;·&nbsp; v_f = f · n (Fräsen: f_z · z · n) &nbsp;·&nbsp; "
                    "t_h = L · i / v_f", "text"))
    for g in kalk.gaenge:
        if g.rechenweg or g.fehler:
            inhalt.append(P(f"<b>AG {g.nr} {_x(g.text)}</b>"))
            for zeile in g.rechenweg:
                inhalt.append(P(_x(zeile), "klein"))
            if g.fehler:
                inhalt.append(P("⚠ " + _x(g.fehler), "klein"))
    inhalt.append(P("Kosten je Stück", "h2"))
    daten = [["Material", "Fertigung (inkl. Rüstanteil)", "Stückkosten", f"Los ({kalk.losgroesse} Stück)"],
             [_euro(kalk.material), _euro(kalk.fertigung), _euro(kalk.stueck), _euro(kalk.los)]]
    inhalt.append(tabelle(daten, [40 * mm, 50 * mm, 40 * mm, 40 * mm]))
    if kalk.fremd:
        inhalt.append(P("Fremdfertigung: " + ("Schätzung ohne Angebot (Eigenkosten + 25 %)." if kalk.fremd_geschaetzt
                                              else "Preis laut Angebot."), "klein"))
    for f in kalk.fehler:
        inhalt.append(P("⚠ " + _x(f), "klein"))
    inhalt += [Spacer(1, 6), P(_x(SCHNITT_HINWEIS), "klein"), P(_x(SCHAETZ_HINWEIS), "klein")]
    return _dokument(ziel, f"Arbeitsplan {teil['nr']}", inhalt)


def anfrageliste_erstellen(eintraege: list[dict], ziel: str | Path, projekt: str = "", absender: str = "") -> Path:
    """Anfrageliste für Fremdfertigung (Lastenheft M37): je Teil Zeichnungsnummer, Werkstoff, Rohteil, Menge."""
    ziel = Path(ziel)
    s, tabelle = _werkzeug()
    P = lambda txt, st="text": Paragraph(txt, s[st])  # noqa: E731
    inhalt = [P("Anfrage Fremdfertigung", "h1"),
              P(f"Projekt: {_x(projekt)} &nbsp;·&nbsp; Datum: {datetime.now():%d.%m.%Y}"
                + (f" &nbsp;·&nbsp; Anfragender: {_x(absender)}" if absender else ""), "klein"),
              Spacer(1, 4),
              P("Wir bitten um ein Angebot für die folgenden Teile nach beiliegender Zeichnung "
                "(Allgemeintoleranz ISO 2768-mK, sofern nicht anders angegeben). Bitte Preis je Stück, "
                "Lieferzeit und gegebenenfalls Mindermengenzuschlag angeben.")]
    daten = [["Pos", "Zeichnung", "Benennung", "Werkstoff", "Rohteil / Halbzeug", "Bearbeitung", "Menge",
              "Preis/Stück", "Lieferzeit"]]
    for i, e in enumerate(eintraege, 1):
        daten.append([str(i), e["nr"], P(_x(e["benennung"])), P(_x(e["werkstoff"])), P(_x(e["rohteil"])),
                      P(_x(e["verfahren"])), str(e["menge"]), "", ""])
    inhalt.append(tabelle(daten, [10 * mm, 18 * mm, 32 * mm, 34 * mm, 42 * mm, 58 * mm, 14 * mm, 22 * mm, 22 * mm]))
    inhalt += [Spacer(1, 10), P("Zeichnungen und STEP-Dateien liegen bei. Rückfragen bitte an den Anfragenden.",
                                "klein")]
    return _dokument(ziel, "Anfrage Fremdfertigung", inhalt, quer=True)


def kalkulation_erstellen(name: str, nr: str, zeilen: list, summe: float, fehlend: list, anzahl: int,
                          ziel: str | Path, projekt: str = "") -> Path:
    """Kostenkalkulation einer Baugruppe (Lastenheft M36)."""
    from .fertigung.arbeitsplan import SCHAETZ_HINWEIS
    ziel = Path(ziel)
    s, tabelle = _werkzeug()
    P = lambda txt, st="text": Paragraph(txt, s[st])  # noqa: E731
    inhalt = [P(f"Kostenkalkulation {_x(nr)} {_x(name)}", "h1"),
              P(f"Projekt: {_x(projekt)} &nbsp;·&nbsp; Stand: {datetime.now():%d.%m.%Y %H:%M} &nbsp;·&nbsp; "
                f"{anzahl} Baugruppe(n)", "klein"), Spacer(1, 4)]
    daten = [["Pos", "Menge", "Benennung", "Sachnummer", "Art", "Einzel", "Gesamt", "Hinweis"]]
    for z in zeilen:
        daten.append([str(z.pos), str(z.menge), P(_x(z.benennung)), P(_x(z.sachnummer)), z.art, _euro(z.einzel),
                      _euro(z.gesamt), P(_x(z.hinweis), "klein")])
    inhalt.append(tabelle(daten, [10 * mm, 12 * mm, 36 * mm, 30 * mm, 14 * mm, 20 * mm, 22 * mm, 30 * mm]))
    inhalt.append(Spacer(1, 6))
    inhalt.append(P(f"<b>Summe {_euro(summe)}</b>" + (f" für {anzahl} Baugruppen" if anzahl > 1 else " je Baugruppe")))
    if fehlend:
        inhalt.append(P("⚠ Ohne Preis (nicht in der Summe): " + _x(", ".join(fehlend)), "klein"))
    inhalt.append(P(_x(SCHAETZ_HINWEIS), "klein"))
    return _dokument(ziel, f"Kostenkalkulation {name}", inhalt)


def _bild(png: bytes, breite_mm: float):
    from io import BytesIO
    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import Image
    leser = ImageReader(BytesIO(png))
    w, h = leser.getSize()
    return Image(BytesIO(png), width=breite_mm * mm, height=breite_mm * mm * h / w)


def montageanleitung_erstellen(baugruppe: dict, plan: dict, bilder: dict, stueckliste: list, ziel: str | Path,
                               projekt: str = "", vorrichtung: dict | None = None,
                               aufnahmepunkte: list | None = None) -> Path:
    """Montageanleitung (Lastenheft M40, S11): Übersicht mit Explosionsdarstellung, Werkzeugliste, je Schritt ein
    Bild aus dem CAD (neu eingebaute Teile farbig), Anzugsmomente und Prüfschritte zum Abhaken.
    `bilder`: {"explosion": PNG, 1: PNG, 2: PNG, …} (Schritt-Nr → Bild)."""
    from reportlab.platypus import CondPageBreak, KeepTogether
    from .montage.montageplan import HINWEIS, gesamtzeit, werkzeugliste
    ziel = Path(ziel)
    s, tabelle = _werkzeug()
    P = lambda txt, st="text": Paragraph(txt, s[st])  # noqa: E731
    schritte = plan.get("schritte", [])
    inhalt = [P(f"Montageanleitung {_x(baugruppe['nr'])} {_x(baugruppe['name'])}", "h1"),
              P(f"Projekt: {_x(projekt)} &nbsp;·&nbsp; Stand: {datetime.now():%d.%m.%Y %H:%M} &nbsp;·&nbsp; "
                f"{len(schritte)} Schritte &nbsp;·&nbsp; Montagezeit ≈ {formatiere(gesamtzeit(plan))} min (Schätzwert)",
                "klein")]
    for h in plan.get("hinweise", []):
        inhalt.append(P("⚠ " + _x(h), "klein"))
    if "explosion" in bilder:
        inhalt += [P("Explosionsdarstellung", "h2"), _bild(bilder["explosion"], 150)]
    if stueckliste:
        inhalt.append(P("Teile", "h2"))
        daten = [["Pos", "Menge", "Benennung", "Sachnummer / Norm"]]
        for p in stueckliste:
            daten.append([str(p.pos), str(p.menge), P(_x(p.benennung)), P(_x(p.sachnummer))])
        inhalt.append(tabelle(daten, [12 * mm, 16 * mm, 70 * mm, 66 * mm]))
    inhalt.append(P("Werkzeuge und Hilfsmittel", "h2"))
    inhalt.append(P(" &nbsp;·&nbsp; ".join(_x(w) for w in werkzeugliste(plan)) or "–"))
    if vorrichtung:
        inhalt.append(P(f"Montagevorrichtung {_x(vorrichtung['nr'])} {_x(vorrichtung['name'])}", "h2"))
        if "vorrichtung" in bilder:
            inhalt.append(_bild(bilder["vorrichtung"], 110))
        if aufnahmepunkte:
            daten = [["Punkt", "Aufnahme / Befestigung", "Lage x, y, z (mm)"]]
            for a in aufnahmepunkte:
                daten.append([a["name"], P(_x(a["text"])), ", ".join(formatiere(v) for v in a["ort"])])
            inhalt.append(tabelle(daten, [14 * mm, 110 * mm, 40 * mm]))
    for st in schritte:
        block = [P(f"Schritt {st['nr']}: {_x(st['titel'])}", "h2")]
        if st["nr"] in bilder:
            block.append(_bild(bilder[st["nr"]], 120))
        block.append(P(_x(st.get("text", ""))))
        if st.get("werkzeuge"):
            block.append(P("<b>Werkzeuge:</b> " + ", ".join(_x(w) for w in st["werkzeuge"]), "klein"))
        teile = [m for m in st.get("momente", [])]
        if teile:
            daten = [["Verbindung", "M_A", "Quelle"]]
            for m in teile:
                wert = "von Hand eintragen" if m.get("wert") in (None, "") else f"{formatiere(float(m['wert']))} N·m"
                daten.append([P(_x(m.get("was", ""))), wert, P(_x(m.get("quelle", "")))])
            block.append(Spacer(1, 3))
            block.append(tabelle(daten, [55 * mm, 32 * mm, 80 * mm]))
        if st.get("pruefung"):
            daten = [["", "Prüfschritt", "i. O."]]
            for q in st["pruefung"]:
                daten.append(["☐", P(_x(q)), ""])
            block.append(Spacer(1, 3))
            block.append(tabelle(daten, [8 * mm, 139 * mm, 20 * mm]))
        block.append(P(f"Zeit ≈ {formatiere(float(st.get('zeit') or 0))} min (Schätzwert)", "klein"))
        inhalt += [CondPageBreak(90 * mm), KeepTogether(block[:2]), *block[2:]]
    inhalt.append(P("Freigabe", "h2"))
    inhalt.append(tabelle([["Montiert von", "Geprüft von", "Datum"], ["", "", ""]], [60 * mm, 60 * mm, 47 * mm]))
    inhalt += [Spacer(1, 6), P(_x(HINWEIS), "klein")]
    return _dokument(ziel, f"Montageanleitung {baugruppe['nr']}", inhalt)


def _datum(text: str) -> str:
    from .betrieb.wartung import anzeigen, lesen
    return anzeigen(lesen(text)) or text


def _kopf_betrieb(s, titel_: str, nr: str, projekt: str, zusatz: str = "") -> list:
    P = lambda txt, st="text": Paragraph(txt, s[st])  # noqa: E731
    return [P(f"{_x(titel_)} {_x(nr)}", "h1"),
            P(f"Projekt: {_x(projekt)} &nbsp;·&nbsp; Stand: {datetime.now():%d.%m.%Y %H:%M}"
              + (f" &nbsp;·&nbsp; {zusatz}" if zusatz else ""), "klein")]


def abnahmeprotokoll_erstellen(ib: dict, ziel: str | Path, projekt: str = "") -> Path:
    """Inbetriebnahme- und Abnahmeprotokoll (Lastenheft M41, M42): alle Prüfpunkte mit Soll, Ist, Ergebnis."""
    from .betrieb import inbetriebnahme as IB
    ziel = Path(ziel)
    s, tabelle = _werkzeug()
    P = lambda txt, st="text": Paragraph(txt, s[st])  # noqa: E731
    d = ib["daten"]
    a = IB.auswerten(d)
    inhalt = _kopf_betrieb(s, "Inbetriebnahme- und Abnahmeprotokoll", ib["nr"], projekt,
                           f"Datum der Prüfung: {_x(_datum(d.get('datum', '')))} &nbsp;·&nbsp; Ort: {_x(d.get('ort', '') or '–')}"
                           f" &nbsp;·&nbsp; Prüfer: {_x(d.get('pruefer', '') or '–')}")
    urteil = ("<b>Abgenommen</b> – alle Prüfpunkte in Ordnung." if a["abgenommen"] else
              f"<b>Nicht abgenommen</b> – {a['nio']} nicht in Ordnung, {a['offen']} offen.")
    inhalt.append(P(f"{urteil} &nbsp; ({a['io']} von {a['gesamt']} Punkten i. O.)"))
    farbe = {IB.IO: colors.HexColor("#E3F2E1"), IB.NIO: colors.HexColor("#FBE3E1")}
    for gruppe in IB.GRUPPEN:
        punkte = [p for p in d.get("punkte", []) if p["gruppe"] == gruppe]
        if not punkte:
            continue
        inhalt.append(P(gruppe, "h2"))
        daten = [["Nr", "Prüfpunkt", "Soll", "Ist", "Ergebnis", "Quelle"]]
        stil = []
        for i, p in enumerate(punkte, 1):
            erg = IB.ergebnis(p)
            text = _x(p["text"]) + (f"<br/><font size=7.5>{_x(p['bemerkung'])}</font>" if p.get("bemerkung") else "")
            daten.append([p["id"], P(text), P(_x(IB.soll_text(p))), P(_x(p.get("ist", ""))), erg,
                          P(f"<font size=7.5>{_x(p.get('quelle', ''))}</font>")])
            if erg in farbe:
                stil.append(("BACKGROUND", (4, i), (4, i), farbe[erg]))
        t = tabelle(daten, [11 * mm, 66 * mm, 30 * mm, 22 * mm, 17 * mm, 28 * mm])
        t.setStyle(TableStyle(stil))
        inhalt.append(t)
    mp = a["messpunkte"]
    if mp:
        inhalt.append(P(f"Leistungskurve: {len(mp)} Messpunkte, Einzelheiten im Messprotokoll.", "klein"))
    inhalt.append(P("Unterschriften", "h2"))
    inhalt.append(tabelle([["Prüfer", "Betreiber", "Datum"], ["\n\n", "", ""]], [62 * mm, 62 * mm, 50 * mm]))
    inhalt += [Spacer(1, 6), P(_x(IB.HINWEIS), "klein")]
    return _dokument(ziel, f"Abnahmeprotokoll {ib['nr']}", inhalt)


def messprotokoll_erstellen(ib: dict, ziel: str | Path, projekt: str = "") -> Path:
    """Messprotokoll Leistungskurve (M42): Messpunkte gegen die berechnete Kurve mit Diagramm."""
    from reportlab.graphics.charts.lineplots import LinePlot
    from reportlab.graphics.shapes import Drawing, String
    from reportlab.graphics.widgets.markers import makeMarker
    from .betrieb import inbetriebnahme as IB
    ziel = Path(ziel)
    s, tabelle = _werkzeug()
    P = lambda txt, st="text": Paragraph(txt, s[st])  # noqa: E731
    d = ib["daten"]
    mp = IB.messung_auswerten(d)
    kurve = d.get("soll_kurve") or {}
    inhalt = _kopf_betrieb(s, "Messprotokoll Leistungskurve", ib["nr"], projekt,
                           f"Messung am {_x(_datum(d.get('datum', '')))} &nbsp;·&nbsp; Sollkurve aus "
                           f"{_x(kurve.get('quelle', '–'))}")
    normal, _ = _schrift()
    z = Drawing(170 * mm, 85 * mm)
    plot = LinePlot()
    plot.x, plot.y, plot.width, plot.height = 14 * mm, 12 * mm, 150 * mm, 64 * mm
    reihen = []
    if kurve.get("x"):
        reihen.append(list(zip(kurve["x"], kurve["y"])))
    if mp:
        reihen.append([(m.v, m.p) for m in mp])
    if reihen:
        plot.data = reihen
        plot.lines[0].strokeColor = colors.HexColor("#1F6FB5")
        plot.lines[0].strokeWidth = 1.4
        if len(reihen) > 1:
            plot.lines[1].strokeColor = colors.HexColor("#D9822B")
            plot.lines[1].strokeWidth = 0
            plot.lines[1].symbol = makeMarker("FilledCircle", size=5, fillColor=colors.HexColor("#D9822B"))
        for achse in (plot.xValueAxis, plot.yValueAxis):
            achse.labels.fontName = normal
            achse.labels.fontSize = 7
        plot.xValueAxis.valueMin = 0
        plot.yValueAxis.valueMin = 0
        z.add(plot)
    z.add(String(14 * mm, 80 * mm, "Leistung P in kW über Wind v in m/s – Linie: Rechnung, Punkte: Messung",
                 fontName=normal, fontSize=9))
    inhalt.append(z)
    daten = [["v in m/s", "P gemessen kW", "P Rechnung kW", "Abweichung", "Ergebnis"]]
    for m in mp:
        daten.append([formatiere(m.v), formatiere(m.p), "–" if m.soll is None else formatiere(m.soll),
                      "–" if m.abweichung is None else f"{formatiere(m.abweichung * 100, 3)} %",
                      "–" if m.ok is None else (IB.IO if m.ok else IB.NIO)])
    inhalt.append(tabelle(daten, [26 * mm, 32 * mm, 32 * mm, 28 * mm, 24 * mm]))
    inhalt += [Spacer(1, 6), P(f"Toleranz ±{formatiere(IB.TOLERANZ_KURVE * 100)} % (Richtwert). Vereinfachte Messung "
                               "(Mittelwerte je Windklasse); eine normgerechte Messung nach IEC 61400-12-1 braucht "
                               "einen Messmast und längere Messdauer.", "klein")]
    return _dokument(ziel, f"Messprotokoll {ib['nr']}", inhalt)


def wartungsplan_erstellen(wp: dict, ziel: str | Path, projekt: str = "", heute=None) -> Path:
    """Wartungsplan (S13) mit Intervallen, Verschleißteilen und nächster Fälligkeit."""
    from datetime import date
    from .betrieb import wartung as W
    ziel = Path(ziel)
    heute = heute or date.today()
    s, tabelle = _werkzeug()
    P = lambda txt, st="text": Paragraph(txt, s[st])  # noqa: E731
    d = wp["daten"]
    inhalt = _kopf_betrieb(s, "Wartungsplan", wp["nr"], projekt,
                           f"Inbetriebnahme: {_x(W.anzeigen(W.lesen(d.get('start', ''))) or '–')}")
    daten = [["Bauteil", "Tätigkeit", "Intervall", "zuletzt", "fällig", "V"]]
    stil = []
    for i, p in enumerate(d.get("punkte", []), 1):
        f_ = W.faellig(p, d.get("start", ""))
        intervall = f"{p['intervall']} Mon." + (f" (erstes: {p['erstes']})" if p.get("erstes") else "")
        daten.append([P(_x(p["bauteil"])), P(_x(p["taetigkeit"]) + f"<br/><font size=7.5>{_x(p.get('quelle', ''))}"
                                              "</font>"),
                      P(intervall), W.anzeigen(W.lesen(p.get("zuletzt", ""))), W.anzeigen(f_),
                      "●" if p.get("verschleiss") else ""])
        if f_ and f_ <= heute:
            stil.append(("BACKGROUND", (4, i), (4, i), colors.HexColor("#FBE3E1")))
    t = tabelle(daten, [32 * mm, 64 * mm, 21 * mm, 23 * mm, 23 * mm, 9 * mm])
    t.setStyle(TableStyle(stil))
    inhalt.append(t)
    vt = W.verschleissteile(d)
    inhalt.append(P("● = Verschleißteil. Verschleißteile: " + ", ".join(_x(p["bauteil"]) for p in vt), "klein"))
    inhalt += [Spacer(1, 6), P(_x(W.HINWEIS), "klein")]
    return _dokument(ziel, f"Wartungsplan {wp['nr']}", inhalt)


# ================================================================ Qualität, Sicherheit & Normen (MS12)
def pruefprotokoll_erstellen(pp: dict, ziel: str | Path, projekt: str = "", teilname: str = "") -> Path:
    """Prüfplan und Prüfprotokoll eines Bauteils (M43, S15): Merkmale, Grenzmaße, Prüfmittel, Ist, Ergebnis."""
    from .betrieb import inbetriebnahme as IB
    from .qualitaet import pruefplan as PP
    ziel = Path(ziel)
    s, tabelle = _werkzeug()
    P = lambda txt, st="text": Paragraph(txt, s[st])  # noqa: E731
    d = pp["daten"]
    a = PP.auswerten(d)
    inhalt = _kopf_betrieb(s, "Prüfplan und Prüfprotokoll", pp["nr"], projekt,
                           f"Bauteil: {_x(d.get('teil', ''))} {_x(teilname)} &nbsp;·&nbsp; Zeichnung "
                           f"{_x(d.get('zeichnung', ''))} &nbsp;·&nbsp; Datum: {_x(_datum(d.get('datum', '')))}"
                           f" &nbsp;·&nbsp; Prüfer: {_x(d.get('pruefer', '') or '–')}"
                           f" &nbsp;·&nbsp; Los: {_x(d.get('los', '') or '–')}")
    z = a["zahlen"]
    urteil = {IB.IO: "<b>Bauteil i. O.</b> – alle Merkmale innerhalb der Grenzmaße.",
              IB.NIO: f"<b>Bauteil n. i. O.</b> – {z[IB.NIO]} Merkmal(e) außerhalb.",
              IB.OFFEN: f"<b>Prüfung offen</b> – {z[IB.OFFEN]} Merkmal(e) noch ohne Ist-Wert."}[a["gesamt"]]
    inhalt.append(P(f"{urteil} &nbsp; ({z[IB.IO]} von {len(d.get('merkmale', []))} i. O.)"))
    farbe = {IB.IO: colors.HexColor("#E3F2E1"), IB.NIO: colors.HexColor("#FBE3E1")}
    zelle = ParagraphStyle("z", parent=s["text"], fontSize=8.5, leading=10.5)
    Z_ = lambda txt: Paragraph(txt, zelle)  # noqa: E731
    daten = [[Z_(f"<b>{h}</b>") for h in ("Nr", "Merkmal", "Toleranz", "Grenzmaße mm", "Prüfmittel", "Umfang", "Ist",
                                           "Ergebnis")]]
    stil = []
    for i, m in enumerate(d.get("merkmale", []), 1):
        erg = PP.ergebnis(m)
        text = _x(m["merkmal"]) + (f"<br/><font size=7>{_x(m['bemerkung'])}</font>" if m.get("bemerkung") else "")
        daten.append([Z_(m["id"]), Z_(text), Z_(_x(m["toleranz"])), Z_(_x(PP.grenz_text(m))),
                      Z_(_x(m["pruefmittel"])), Z_(_x(m["umfang"])), Z_(_x(m.get("ist", ""))), Z_(erg)])
        if erg in farbe:
            stil.append(("BACKGROUND", (7, i), (7, i), farbe[erg]))
    t = tabelle(daten, [12 * mm, 24 * mm, 18 * mm, 27 * mm, 34 * mm, 22 * mm, 18 * mm, 19 * mm])
    t.setStyle(TableStyle(stil))
    inhalt.append(t)
    inhalt.append(P("Prüfmittel", "h2"))
    inhalt.append(tabelle([["Prüfmittel", "Merkmale", "Kalibriert bis"]] +
                          [[P(_x(n)), str(k), ""] for n, k in PP.pruefmittelliste(d)], [90 * mm, 22 * mm, 40 * mm]))
    inhalt.append(Spacer(1, 4 * mm))
    inhalt.append(P(_x(PP.HINWEIS), "klein"))
    inhalt.append(Spacer(1, 10 * mm))
    inhalt.append(tabelle([["Geprüft (Datum, Unterschrift)", "Freigabe (Datum, Unterschrift)"], ["\n\n", ""]],
                          [87 * mm, 87 * mm]))
    return _dokument(ziel, f"Prüfprotokoll {pp['nr']}", inhalt)


_AMPEL = {"gruen": "#E3F2E1", "gelb": "#FFF4D6", "rot": "#FBE3E1", "grau": "#EEEEEE"}


def qdok_erstellen(typ: str, dok: dict, ziel: str | Path, projekt: str = "") -> Path:
    """FMEA, Risikobeurteilung, Normen-Checkliste oder Abweichungsliste als Tabelle (A4 quer)."""
    from .qualitaet import tabellen as Q
    art = Q.ART[typ]
    ziel = Path(ziel)
    s, tabelle = _werkzeug()
    P = lambda txt, st="text": Paragraph(txt, s[st])  # noqa: E731
    zelle = ParagraphStyle("z", parent=s["text"], fontSize=7.5, leading=9.5)
    d = dok["daten"]
    titel_ = dok.get("art") if typ == "fmea" and dok.get("art") else art.titel
    inhalt = _kopf_betrieb(s, titel_, dok["nr"], projekt, f"{_x(dok['name'])} &nbsp;·&nbsp; Version {dok['version']}"
                                                          f" · {_x(dok['status'])}")
    g = d.get("grenzen")
    if g:
        inhalt.append(P("Grenzen der Maschine (EN ISO 12100, 5.3)", "h3"))
        inhalt.append(P(f"<b>Bestimmungsgemäße Verwendung:</b> {_x(g.get('verwendung', ''))}<br/>"
                        f"<b>Vorhersehbare Fehlanwendung:</b> {_x(g.get('fehlanwendung', ''))}<br/>"
                        f"<b>Lebensdauer:</b> {_x(g.get('lebensdauer', ''))}", "klein"))
    zahlen = Q.zaehlen(art, d)
    inhalt.append(P(f"{len(d.get('zeilen', []))} Einträge &nbsp;·&nbsp; rot {zahlen['rot']} &nbsp;·&nbsp; "
                    f"gelb {zahlen['gelb']} &nbsp;·&nbsp; grün {zahlen['gruen']}", "klein"))
    spalten = [sp for sp in art.spalten if sp.pdf]
    verfuegbar = 261 - 26
    faktor = verfuegbar / sum(sp.pdf for sp in spalten)
    kopf = [Paragraph(f"<b>{_x(sp.titel)}</b>", zelle) for sp in spalten] + [Paragraph("<b>Bewertung</b>", zelle)]
    daten, stil = [kopf], []
    for i, z in enumerate(d.get("zeilen", []), 1):
        text, ampel = art.bewerten(z)
        daten.append([Paragraph(_x(sp.fn(z) if sp.fn else z.get(sp.key, "")), zelle) for sp in spalten]
                     + [Paragraph(_x(text), zelle)])
        stil.append(("BACKGROUND", (len(spalten), i), (len(spalten), i), colors.HexColor(_AMPEL[ampel])))
    t = tabelle(daten, [sp.pdf * faktor * mm for sp in spalten] + [26 * mm])
    t.setStyle(TableStyle(stil + [("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                                  ("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 2)]))
    inhalt.append(t)
    inhalt.append(Spacer(1, 3 * mm))
    inhalt.append(P(_x(art.hinweis), "klein"))
    return _dokument(ziel, f"{titel_} {dok['nr']}", inhalt, quer=True)


def deckblatt_erstellen(ziel: str | Path, projekt: str, kapitel: list[tuple[str, int | None, str]],
                        ersteller: str = "") -> Path:
    """Deckblatt mit Inhaltsverzeichnis der technischen Dokumentation. kapitel: (Titel, Seite oder None, Hinweis)."""
    ziel = Path(ziel)
    s, tabelle = _werkzeug()
    P = lambda txt, st="text": Paragraph(txt, s[st])  # noqa: E731
    inhalt = [Spacer(1, 30 * mm), P("Technische Dokumentation", "h1"), P(_x(projekt), "h2"),
              P(f"Stand: {datetime.now():%d.%m.%Y}" + (f" &nbsp;·&nbsp; Ersteller: {_x(ersteller)}" if ersteller
                                                         else ""), "klein"),
              Spacer(1, 12 * mm), P("Inhalt", "h2")]
    zeilen = [["Kapitel", "Seite", "Hinweis"]]
    stil = []
    for i, (titel_, seite, hinweis) in enumerate(kapitel, 1):
        zeilen.append([P(_x(titel_)), "–" if seite is None else str(seite), P(f"<font size=8>{_x(hinweis)}</font>")])
        if seite is None:
            stil.append(("TEXTCOLOR", (0, i), (-1, i), colors.HexColor("#A33A2B")))
    t = tabelle(zeilen, [80 * mm, 16 * mm, 78 * mm])
    t.setStyle(TableStyle(stil))
    inhalt.append(t)
    inhalt.append(Spacer(1, 8 * mm))
    inhalt.append(P("Diese Zusammenstellung ersetzt keine Prüfung durch eine Fachperson. Werte mit „Richtwert“, "
                    "„Schätzwert“ oder „Norm, ungeprüft“ sind vor der Fertigung und der Konformitätserklärung zu "
                    "bestätigen. Rot markierte Kapitel fehlen noch.", "klein"))
    return _dokument(ziel, f"Technische Dokumentation {projekt}", inhalt)


# ================================================================ Projektmanagement (MS13)
def zeitplan_erstellen(aufgaben: list[dict], gantt_png: bytes, fortschritt: list, ziel: str | Path,
                       projekt: str = "", heute=None, objekte: dict | None = None) -> Path:
    """Zeitplan (S17): Gantt-Bild, Fortschritt je Phase (M49) und Aufgabenliste (M48), A4 quer."""
    from .betrieb.wartung import anzeigen, lesen
    from .planung import zeitplan as Z
    ziel = Path(ziel)
    s, tabelle = _werkzeug()
    P = lambda txt, st="text": Paragraph(txt, s[st])  # noqa: E731
    zelle = ParagraphStyle("z", parent=s["text"], fontSize=8, leading=10)
    heute = heute or datetime.now().date()
    objekte = objekte or {}
    inhalt = _kopf_betrieb(s, "Zeitplan", "", projekt, f"Stichtag {anzeigen(heute)}")
    kopf = [Paragraph(f"<b>{nr}</b> {_x(name)}", zelle) for nr, name, _ in fortschritt]
    inhalt.append(tabelle([kopf, [f"{p} %" for _, _, p in fortschritt]], [261 / len(fortschritt) * mm] * len(fortschritt)))
    inhalt.append(Spacer(1, 3 * mm))
    from io import BytesIO
    from reportlab.lib.utils import ImageReader
    bw, bh = ImageReader(BytesIO(gantt_png)).getSize()
    inhalt.append(_bild(gantt_png, min(261, 130 * bw / bh)))        # höchstens 130 mm hoch
    inhalt.append(P("Aufgaben und Meilensteine", "h2"))
    daten = [[Paragraph(f"<b>{h}</b>", zelle) for h in ("Nr", "Aufgabe", "Phase", "Wer", "Zeitraum", "Stand",
                                                         "Objekt", "Notiz")]]
    stil = []
    for i, a in enumerate(aufgaben, 1):
        spaet = Z.verzug(a, heute)
        daten.append([Paragraph(_x(a["nr"] + (" ◆" if a["meilenstein"] else "")), zelle),
                      Paragraph(_x(a["titel"]), zelle), Paragraph(_x(a["phase"]), zelle),
                      Paragraph(_x(a["verantwortlich"]), zelle), Paragraph(_x(Z.termin_text(a)), zelle),
                      Paragraph(_x(a["stand"] + (f" ({spaet} Tage über Termin)" if spaet else "")), zelle),
                      Paragraph(_x(objekte.get(a["id"], "")), zelle), Paragraph(_x(a["notiz"]), zelle)])
        if spaet:
            stil.append(("BACKGROUND", (5, i), (5, i), colors.HexColor(_AMPEL["rot"])))
        elif a["stand"] == "erledigt":
            stil.append(("BACKGROUND", (5, i), (5, i), colors.HexColor(_AMPEL["gruen"])))
    t = tabelle(daten, [mm * w for w in (18, 78, 15, 25, 42, 30, 18, 35)])
    t.setStyle(TableStyle(stil))
    inhalt.append(t)
    inhalt.append(Spacer(1, 3 * mm))
    inhalt.append(P(_x(Z.HINWEIS), "klein"))
    return _dokument(ziel, f"Zeitplan {projekt}", inhalt, quer=True)


def kostenuebersicht_erstellen(posten: list[dict], uebersicht: list[dict], aufgaben: list[dict], ziel: str | Path,
                               projekt: str = "") -> Path:
    """Kostenübersicht Plan/Ist (S18) je Kostenart, mit allen Posten und Aufgaben mit Kosten."""
    from .planung import kosten as K
    ziel = Path(ziel)
    s, tabelle = _werkzeug()
    P = lambda txt, st="text": Paragraph(txt, s[st])  # noqa: E731
    inhalt = _kopf_betrieb(s, "Kostenübersicht Plan/Ist", "", projekt)
    daten = [["Kostenart", "Plan", "Ist", "Abweichung", "Ist/Plan"]]
    stil = []
    for i, z in enumerate(uebersicht, 1):
        daten.append([z["kostenart"], _euro(z["plan"]), _euro(z["ist"]), _euro(z["abweichung"]),
                      f"{z['anteil'] * 100:.0f} %" if z["anteil"] is not None else "–"])
        if z["ueber"]:
            stil.append(("BACKGROUND", (3, i), (3, i), colors.HexColor(_AMPEL["rot"])))
    stil += [("ALIGN", (1, 0), (-1, -1), "RIGHT"), ("FONTNAME", (0, len(daten) - 1), (-1, len(daten) - 1),
                                                    _schrift()[1])]
    t = tabelle(daten, [62 * mm, 30 * mm, 30 * mm, 30 * mm, 22 * mm])
    t.setStyle(TableStyle(stil))
    inhalt.append(t)
    inhalt.append(P("Posten", "h2"))
    zeilen = [["Nr", "Kostenart", "Posten", "Plan", "Ist", "Quelle"]]
    for p in posten:
        zeilen.append([p["id"], P(_x(p["kostenart"])), P(_x(p["text"])), _euro(K.zahl(p.get("plan"))),
                       _euro(K.zahl(p.get("ist"))), P(f"<font size=7.5>{_x(p.get('quelle', ''))}</font>")])
    mit_kosten = [a for a in aufgaben if a.get("kosten_plan") is not None or a.get("kosten_ist") is not None]
    for a in mit_kosten:
        zeilen.append([a["nr"], P(K.AUFGABEN), P(_x(a["titel"])), _euro(a["kosten_plan"]), _euro(a["kosten_ist"]),
                       P("<font size=7.5>Aufgabe</font>")])
    t = tabelle(zeilen, [12 * mm, 32 * mm, 52 * mm, 24 * mm, 24 * mm, 30 * mm])
    t.setStyle(TableStyle([("ALIGN", (3, 0), (4, -1), "RIGHT")]))
    inhalt.append(t)
    inhalt.append(Spacer(1, 4 * mm))
    inhalt.append(P(_x(K.HINWEIS), "klein"))
    return _dokument(ziel, f"Kostenübersicht {projekt}", inhalt)


def abnahme_v1_erstellen(kriterien: list, ziel: str | Path, projekt: str = "", ersteller: str = "") -> Path:
    """MS15: Abnahmeprotokoll der App (Version 1) mit den 11 Kriterien aus dem Lastenheft, Nachweisen und Lücken."""
    from .abnahme import BESTAETIGEN, ERFUELLT, zusammenfassung
    ziel = Path(ziel)
    s, tabelle = _werkzeug()
    P = lambda txt, st="text": Paragraph(txt, s[st])  # noqa: E731
    zelle = ParagraphStyle("z", parent=s["text"], fontSize=8.5, leading=11)
    erfuellt, gesamt = zusammenfassung(kriterien)
    inhalt = _kopf_betrieb(s, "Abnahme YamProduktion – Version 1", "", projekt,
                           f"{erfuellt} von {gesamt} Kriterien erfüllt")
    farbe = {ERFUELLT: "gruen", BESTAETIGEN: "gelb"}
    daten, stil = [[Paragraph(f"<b>{t}</b>", zelle) for t in ("Nr", "Kriterium", "Nachweise / was fehlt", "Stand")]], []
    for i, k in enumerate(kriterien, 1):
        zeilen = [f"• {_x(n)}" for n in k.nachweise] + [f"<font color='#B3261E'>fehlt: {_x(f)}</font>" for f in k.fehlt]
        if k.stand == BESTAETIGEN:
            zeilen.append("Von Yamine zu bestätigen")
        daten.append([Paragraph(str(k.nr), zelle), Paragraph(_x(k.titel), zelle),
                      Paragraph("<br/>".join(zeilen) or "–", zelle), Paragraph(k.stand, zelle)])
        stil.append(("BACKGROUND", (3, i), (3, i), colors.HexColor(_AMPEL[farbe.get(k.stand, "rot")])))
    t = tabelle(daten, [10 * mm, 52 * mm, 88 * mm, 22 * mm])
    t.setStyle(TableStyle(stil + [("VALIGN", (0, 0), (-1, -1), "TOP")]))
    inhalt.append(t)
    inhalt.append(Spacer(1, 6 * mm))
    inhalt.append(P("Die App ist ein Werkzeug für Auslegung und Dokumentation. Für Genehmigung, Netzanschluss und "
                    "CE-Kennzeichnung der echten Anlage ist eine Prüfung durch Sachverständige vorzusehen.", "klein"))
    inhalt.append(Spacer(1, 14 * mm))
    unterschrift = tabelle([["Ort, Datum", "Unterschrift" + (f" ({_x(ersteller)})" if ersteller else "")]],
                           [80 * mm, 92 * mm])
    unterschrift.setStyle(TableStyle([("LINEABOVE", (0, 0), (-1, 0), 0.6, colors.black)]))
    inhalt.append(unterschrift)
    return _dokument(ziel, "Abnahme YamProduktion Version 1", inhalt)


def kollisionsbericht_erstellen(pruefung, massen, ziel: str | Path, name: str, nr: str = "", projekt: str = "") -> Path:
    """Prüfbericht einer Baugruppe (Lastenheft K4): Kollisionsbefunde mit Ausnahmen, Masse, Schwerpunkt, Trägheit."""
    ziel = Path(ziel)
    s, tabelle = _werkzeug()
    P = lambda txt, st="text": Paragraph(txt, s[st])  # noqa: E731
    inhalt = [P(f"Kollision &amp; Schwerpunkt {_x(nr)} {_x(name)}", "h1"),
              P(f"Projekt: {_x(projekt)} &nbsp;·&nbsp; Stand: {datetime.now():%d.%m.%Y %H:%M} &nbsp;·&nbsp; "
                f"Mindestabstand {formatiere(pruefung.mindestabstand)} mm", "klein"),
              P("Kollisionsprüfung", "h2"),
              P(f"<b>{_x(pruefung.zusammenfassung())}</b> &nbsp;·&nbsp; {pruefung.paare_geprueft} von "
                f"{pruefung.paare_gesamt} Paaren genau geprüft (übrige liegen weit auseinander)")]
    if pruefung.befunde:
        daten = [["Art", "Teil A", "Teil B", "Überschn. mm³", "Abstand mm", "Gewollt – Begründung"]]
        for b in pruefung.befunde:
            daten.append([b.art, P(_x(b.name_a)), P(_x(b.name_b)),
                          formatiere(b.volumen) if b.volumen else "–", formatiere(b.abstand),
                          P(_x(b.ausnahme) or ("offen" if b.ist_fehler else "–"))])
        inhalt.append(tabelle(daten, [27 * mm, 34 * mm, 34 * mm, 22 * mm, 19 * mm, 34 * mm]))
    sx, sy, sz = massen.schwerpunkt
    j1, j2, j3 = (w * 1e-6 for w in massen.haupt)
    inhalt += [P("Masse und Schwerpunkt", "h2"),
               P(f"<b>Gesamtmasse {formatiere(massen.masse)} kg</b> &nbsp;·&nbsp; Schwerpunkt x = {formatiere(sx)}, "
                 f"y = {formatiere(sy)}, z = {formatiere(sz)} mm"),
               P(f"Hauptträgheitsmomente um den Schwerpunkt: {formatiere(j1)} · {formatiere(j2)} · "
                 f"{formatiere(j3)} kg·m²")]
    daten = [["Einbau", "Menge", "Masse kg", "Anteil"]]
    for z in massen.je_einbau:
        daten.append([P(_x(f"{z.einbau} {z.name}")), str(z.menge), "–" if z.masse is None else formatiere(z.masse),
                      f"{z.anteil * 100:.1f} %".replace(".", ",")])
    inhalt.append(tabelle(daten, [90 * mm, 20 * mm, 30 * mm, 30 * mm]))
    if massen.ohne_masse:
        inhalt.append(P("Ohne Masse (nicht in der Summe): " + _x(", ".join(massen.ohne_masse)), "klein"))
    inhalt += [Spacer(1, 8),
               P("Befunde sind Hinweise, keine Urteile. Berührung ist oft gewollt (z. B. Lager auf Welle). Normteile "
                 "sind vereinfacht dargestellt (z. B. Schrauben ohne Gewinde, Gegenstück ohne Bohrung) – solche "
                 "Überdeckungen werden mit Begründung als gewollt vermerkt. Trägheit unter Annahme gleichmäßiger "
                 "Dichte je Teil.", "klein")]
    return _dokument(ziel, f"Kollision & Schwerpunkt {name}", inhalt)
