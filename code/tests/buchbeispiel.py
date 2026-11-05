"""Kleines Beispiel-„Fachbuch“ als PDF für Tests und Bildschirmfotos (eigener Text, kein Auszug aus einem Buch)."""
from pathlib import Path

from reportlab.lib.pagesizes import A5
from reportlab.pdfgen import canvas

SEITEN = [
    ("Vorwort", ["Dieses Übungsbuch fasst Grundlagen der Maschinenelemente zusammen.",
                 "Alle Zahlenwerte sind Beispiele und vor Gebrauch zu prüfen."]),
    ("11 Achsen und Wellen", ["11 Achsen und Wellen",
                              "Wellen übertragen Drehmomente und werden auf Biegung und Torsion beansprucht.",
                              "Bei mittiger Einzellast F auf einer Welle mit Lagerabstand l gilt:",
                              "M_b = F · l / 4",
                              "Die Biegespannung folgt aus dem Widerstandsmoment W = π · d³ / 32:",
                              "σ_b = M_b / W"]),
    (None, ["Für die Torsion gilt τ_t = T / W_t mit W_t = π · d³ / 16.",
            "Die Vergleichsspannung nach der Gestaltänderungsenergiehypothese:",
            "σ_v = sqrt(σ_b^2 + 3 · (α_0 · τ_t)^2)",
            "Das Anstrengungsverhältnis α_0 liegt meist zwischen 0,7 und 1,0."]),
    ("14 Wälzlager", ["14 Wälzlager",
                      "Die nominelle Lebensdauer eines Wälzlagers in Millionen Umdrehungen:",
                      "L_10 = (C / P)^p",
                      "Exponent p = 3 für Kugellager und p = 10/3 für Rollenlager.",
                      "Die Lebensdauer in Stunden: L_10h = L_10 · 10^6 / (60 · n)"]),
    (None, ["Bei schwankender Last wird eine äquivalente Lagerbelastung P gebildet.",
            "Pendelrollenlager gleichen Fluchtungsfehler der Rotorwelle aus."]),
]


def beispielbuch(pfad: Path, versatz: int = 1) -> Path:
    """PDF mit Inhaltsverzeichnis-Lesezeichen; gedruckte Seitenzahl = PDF-Seite − versatz."""
    c = canvas.Canvas(str(pfad), pagesize=A5)
    c.setTitle("Übungsbuch Maschinenelemente")
    breite, hoehe = A5
    for i, (kapitel, zeilen) in enumerate(SEITEN, 1):
        c.bookmarkPage(f"s{i}")
        if kapitel:
            c.addOutlineEntry(kapitel, f"s{i}")
        y = hoehe - 60
        for j, z in enumerate(zeilen):
            if j == 0 and kapitel and z == kapitel:
                c.setFont("Helvetica-Bold", 14)
            else:
                c.setFont("Helvetica", 10.5)
            c.drawString(40, y, z)
            y -= 24
        c.setFont("Helvetica", 9)
        c.drawCentredString(breite / 2, 30, str(i - versatz) if i > versatz else "")
        c.showPage()
    c.save()
    return pfad
