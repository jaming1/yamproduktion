"""Kostenübersicht Plan/Ist (S18).

Posten mit Kostenart, Plan und Ist; dazu die Plan- und Ist-Kosten der Aufgaben. Der Plan für Bauteile und
Zukaufteile kann aus der Kalkulation (MS9) übernommen werden – deren Sätze und Preise sind Schätzwerte.
"""
from __future__ import annotations

KOSTENARTEN = ("Bauteile", "Zukaufteile", "Prüfung & Zertifizierung", "Genehmigung & Gutachten",
               "Werkzeuge & Vorrichtungen", "Sonstiges")
AUFGABEN = "Aufgaben"
HINWEIS = ("Plan aus der Kalkulation beruht auf geschätzten Stundensätzen und Preisen (Seite Kosten & Anfragen). "
           "Ist-Kosten aus Rechnungen eintragen. Abweichung = Ist − Plan; rot ab +10 % (Richtwert).")
GRENZE = 0.10


def zahl(text) -> float | None:
    if text in (None, ""):
        return None
    if isinstance(text, (int, float)):
        return float(text)
    t = str(text).replace("€", "").replace(" ", "").replace("\u202f", "")
    t = t.replace(".", "").replace(",", ".") if "," in t else t
    try:
        return float(t)
    except ValueError:
        return None


def naechste_id(posten: list[dict]) -> str:
    vorhanden = {p["id"] for p in posten}
    i = 1
    while f"K{i}" in vorhanden:
        i += 1
    return f"K{i}"


def posten_neu(posten: list[dict], kostenart: str = "Sonstiges", text: str = "", plan=None, ist=None,
               quelle: str = "von Hand") -> dict:
    p = {"id": naechste_id(posten), "kostenart": kostenart, "text": text, "plan": plan, "ist": ist,
         "quelle": quelle}
    posten.append(p)
    return p


def aus_kalkulation(nr: str, name: str, zeilen) -> list[tuple[str, str, float, str]]:
    """(Kostenart, Text, Plan, Quelle) je Baugruppe aus den Kalkulationszeilen."""
    teile = sum(z.gesamt or 0 for z in zeilen if z.art in ("Eigen", "Fremd"))
    zukauf = sum(z.gesamt or 0 for z in zeilen if z.art == "Zukauf")
    fehlt = sum(1 for z in zeilen if z.gesamt is None)
    quelle = f"Kalkulation {nr} (Schätzwerte)" + (f", {fehlt} Preise fehlen" if fehlt else "")
    out = []
    if teile:
        out.append(("Bauteile", f"Bauteile {nr} {name}", round(teile, 2), quelle))
    if zukauf:
        out.append(("Zukaufteile", f"Zukaufteile {nr} {name}", round(zukauf, 2), quelle))
    return out


def uebersicht(posten: list[dict], aufgaben: list[dict]) -> list[dict]:
    """Je Kostenart: plan, ist, abweichung, anteil (Ist/Plan); letzte Zeile = Summe."""
    summen: dict[str, list[float]] = {k: [0.0, 0.0] for k in KOSTENARTEN}
    summen[AUFGABEN] = [0.0, 0.0]
    for p in posten:
        s = summen.setdefault(p.get("kostenart") or "Sonstiges", [0.0, 0.0])
        s[0] += zahl(p.get("plan")) or 0
        s[1] += zahl(p.get("ist")) or 0
    for a in aufgaben:
        summen[AUFGABEN][0] += a.get("kosten_plan") or 0
        summen[AUFGABEN][1] += a.get("kosten_ist") or 0
    zeilen = []
    for art, (plan, ist) in summen.items():
        if plan or ist:
            zeilen.append(_zeile(art, plan, ist))
    zeilen.append(_zeile("Summe", sum(z["plan"] for z in zeilen), sum(z["ist"] for z in zeilen)))
    return zeilen


def _zeile(art, plan, ist) -> dict:
    ab = ist - plan
    return {"kostenart": art, "plan": plan, "ist": ist, "abweichung": ab,
            "anteil": ist / plan if plan else None, "ueber": plan > 0 and ab > GRENZE * plan}
