"""Text aus PDF-Seiten lesen und – wenn keiner da ist – per Texterkennung (OCR) erzeugen.

Reihenfolge: 1) vorhandene Textebene (pypdf)  2) OCRmyPDF (erzeugt durchsuchbares PDF)  3) Tesseract je Seitenbild.
Beides gibt es auf dem Mac kostenlos über Homebrew:  brew install ocrmypdf tesseract-lang
Ohne diese Werkzeuge wird das Buch trotzdem übernommen (lesbar, aber nicht durchsuchbar).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

from pypdf import PdfReader

SPRACHEN = "deu+eng"
INSTALLIEREN = "Für die Texterkennung im Terminal einmal ausführen:  brew install ocrmypdf tesseract-lang"
_SUCHPFADE = ["/opt/homebrew/bin", "/usr/local/bin"]

# Für Tests austauschbar: f(pdf_pfad, melde) -> list[str] | None
ersatz_ocr: Callable | None = None


def werkzeug(name: str) -> str | None:
    pfad = shutil.which(name)
    if pfad:
        return pfad
    for ordner in _SUCHPFADE:
        p = Path(ordner) / name
        if p.exists():
            return str(p)
    return None


def verfuegbar() -> str:
    """Welche Texterkennung bereitsteht (Anzeige in der Oberfläche)."""
    if werkzeug("ocrmypdf"):
        return "OCRmyPDF"
    if werkzeug("tesseract"):
        return "Tesseract"
    return ""


def pdf_text(pfad: Path) -> list[str]:
    leser = PdfReader(str(pfad))
    texte = []
    for s in leser.pages:
        try:
            texte.append((s.extract_text() or "").strip())
        except Exception:                     # beschädigte Seite: leer lassen statt abbrechen
            texte.append("")
    return texte


def braucht_ocr(texte: list[str]) -> bool:
    """Mehr als ein Viertel der Seiten ohne lesbaren Text → Scan ohne Textebene."""
    if not texte:
        return False
    leer = sum(1 for t in texte if len(t) < 20)
    return leer / len(texte) > 0.25


def pdf_kapitel(pfad: Path, seiten: int) -> dict[int, str]:
    """Kapitel aus dem Inhaltsverzeichnis des PDFs (Lesezeichen): {Seite: Titel}."""
    try:
        leser = PdfReader(str(pfad))
        ergebnis: dict[int, str] = {}

        def durchgehen(eintraege):
            for e in eintraege:
                if isinstance(e, list):
                    durchgehen(e)
                    continue
                try:
                    nr = leser.get_destination_page_number(e) + 1
                except Exception:
                    continue
                if 1 <= nr <= seiten and nr not in ergebnis:
                    ergebnis[nr] = str(e.title).strip()

        durchgehen(leser.outline)
        return ergebnis
    except Exception:
        return {}


def bilder_zu_pdf(bilder: list[Path], ziel: Path):
    """Fotos/Scans (PNG, JPG, TIFF) in Dateireihenfolge zu einem PDF, jede Seite in Bildgröße."""
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(ziel))
    for b in sorted(bilder):
        bild = ImageReader(str(b))
        breite, hoehe = bild.getSize()
        massstab = 72 / 300                      # Scans meist 300 dpi
        c.setPageSize((breite * massstab, hoehe * massstab))
        c.drawImage(bild, 0, 0, breite * massstab, hoehe * massstab)
        c.showPage()
    c.save()


def erkennen(pdf: Path, melde: Callable[[str], None]) -> tuple[list[str], str] | None:
    """Texterkennung. Ersetzt das PDF durch die durchsuchbare Fassung (OCRmyPDF). None, wenn kein Werkzeug da ist."""
    if ersatz_ocr:
        texte = ersatz_ocr(pdf, melde)
        return (texte, "Texterkennung (Test)") if texte is not None else None
    ocrmypdf = werkzeug("ocrmypdf")
    if ocrmypdf:
        ausgabe = pdf.with_suffix(".ocr.pdf")
        r = subprocess.run([ocrmypdf, "-l", SPRACHEN, "--skip-text", "--rotate-pages", "--deskew",
                            "--output-type", "pdf", str(pdf), str(ausgabe)], capture_output=True, text=True)
        if r.returncode != 0:              # Drehen/Entzerren braucht Zusatzpakete → einfach ohne
            r = subprocess.run([ocrmypdf, "-l", SPRACHEN, "--skip-text", "--output-type", "pdf",
                                str(pdf), str(ausgabe)], capture_output=True, text=True)
        if r.returncode == 0 and ausgabe.exists():
            os.replace(ausgabe, pdf)
            return pdf_text(pdf), "OCRmyPDF"
        melde("OCRmyPDF meldet einen Fehler – versuche Tesseract je Seite.")
    tesseract = werkzeug("tesseract")
    if not tesseract:
        melde("Keine Texterkennung installiert. " + INSTALLIEREN)
        return None
    return _tesseract_seiten(pdf, tesseract, melde), "Tesseract"


def _tesseract_seiten(pdf: Path, tesseract: str, melde) -> list[str]:
    from PySide6.QtCore import QSize
    from PySide6.QtPdf import QPdfDocument

    dok = QPdfDocument()
    dok.load(str(pdf))
    texte = []
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(dok.pageCount()):
            melde(f"Texterkennung Seite {i + 1} von {dok.pageCount()} …")
            gr = dok.pagePointSize(i)
            bild = dok.render(i, QSize(int(gr.width() * 300 / 72), int(gr.height() * 300 / 72)))
            datei = Path(tmp) / f"s{i}.png"
            bild.save(str(datei))
            r = subprocess.run([tesseract, str(datei), "stdout", "-l", SPRACHEN], capture_output=True, text=True)
            texte.append(r.stdout.strip() if r.returncode == 0 else "")
    dok.close()
    return texte
