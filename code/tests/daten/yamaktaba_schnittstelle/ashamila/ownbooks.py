"""Eigene Bücher aus Dateien übernehmen: TXT, Markdown, HTML, Word (DOCX, DOC), RTF, ODT, EPUB, iBooks,
PowerPoint (PPTX), Excel (XLSX), DjVu (mit djvutxt) und PDF mit Textebene.

Jede Datei wird zu einem Buch wie die aus Shamela: Seiten (durchsuchbar), Inhaltsverzeichnis
aus den Überschriften, Fußnoten getrennt vom Text. Gespeichert wird im selben Format wie
Shamela: Überschriften als <span data-type='title'>, Fußnotenmarken als (¬1).
Alles mit der Standardbibliothek, nur PDF braucht das kleine Paket pypdf.
"""
import json
import os
import posixpath
import re
import sys
import time
import unicodedata
import zipfile
from html.parser import HTMLParser
from xml.etree import ElementTree as ET

from . import db
from .importer import pack
from .normalize import normalize, western_digits

FORMATS = (".txt", ".md", ".markdown", ".html", ".htm", ".xhtml", ".docx", ".epub", ".pdf",
           ".doc", ".rtf", ".rtfd", ".odt", ".wordml", ".webarchive", ".ibooks", ".pptx", ".xlsx", ".xlsm",
           ".djvu", ".csv")
PAGE_CHARS = 1800          # Zielgröße einer Seite, wenn die Datei selbst keine Seiten kennt
_AR = re.compile(r"[؀-ۿ]")


class ImportError_(ValueError):
    """Verständliche Meldung, wenn eine Datei nicht gelesen werden kann."""


# ---------- Bausteine ----------

def _plain(text):
    # Spitze Klammern würden als Auszeichnung gelesen; Text sonst unverändert (wie bei Shamela)
    return text.replace("<", "‹").replace(">", "›")


def _title(text):
    return "<span data-type='title'>%s</span>" % _plain(" ".join(text.split()))


class Doc:
    """Sammelt Absätze, Überschriften und Fußnoten und teilt sie in Seiten."""

    def __init__(self):
        self.pages = []        # fertige Seiten: {"body", "foot", "num"}
        self.cur, self.cur_feet = [], []
        self.toc = []          # (Ebene, Titel, Seitenindex)
        self.foot_no = 0
        self.size = 0

    def heading(self, text, level=1):
        text = " ".join((text or "").split())
        if not text:
            return
        if self.size > PAGE_CHARS * 0.6:   # Kapitel beginnt möglichst auf neuer Seite
            self.page_break()
        self.toc.append((level, text, len(self.pages)))
        self.cur.append(_title(text))
        self.size += len(text)

    def para(self, text):
        text = (text or "").strip()
        if not text:
            return
        if len(text) > PAGE_CHARS:      # sehr lange Absätze an Zeilen oder Satzenden teilen
            parts = text.split("\n") if "\n" in text else re.split(r"(?<=[.!?؟。])\s+", text)
            if len(parts) > 1:
                for x in parts:
                    self.para(x)
                return
        if self.size + len(text) > PAGE_CHARS and self.size > PAGE_CHARS * 0.4:
            self.page_break()
        self.cur.append(_plain(text))
        self.size += len(text)

    def footnote(self, text):
        """Fußnote zur aktuellen Seite; gibt die Marke für den Text zurück."""
        self.foot_no += 1
        self.cur_feet.append("(%d) %s" % (self.foot_no, " ".join(text.split())))
        return "(¬%d)" % self.foot_no

    def page_break(self, num=None):
        if self.cur or self.cur_feet:
            self.pages.append({"body": "\n".join(self.cur), "foot": "\n".join(self.cur_feet) or None,
                               "num": num})
        self.cur, self.cur_feet, self.size, self.foot_no = [], [], 0, 0

    def finish(self):
        self.page_break()
        for i, p in enumerate(self.pages):
            if p["num"] is None:
                p["num"] = i + 1
        return self


def _decode(data):
    for enc in ("utf-8-sig", "utf-16"):
        try:
            text = data.decode(enc)
            if enc == "utf-16" and not data[:2] in (b"\xff\xfe", b"\xfe\xff"):
                continue
            return text
        except UnicodeDecodeError:
            continue
    return data.decode("cp1256", "replace")   # ältere arabische Textdateien (Windows)


def _clean(text):
    # Darstellungsformen (ﻻ, ﺍﻟ …) aus PDFs und alten Dateien in normale Buchstaben, Ziffern 0–9
    text = "".join(unicodedata.normalize("NFKC", ch) if 0xFB50 <= ord(ch) <= 0xFEFF else ch for ch in text)
    return western_digits(text.replace("\r\n", "\n").replace("\r", "\n"))


# ---------- Text und Markdown ----------

_MD_HEAD = re.compile(r"^(#{1,4})\s+(.+?)\s*#*\s*$")
_MD_FOOTDEF = re.compile(r"^\[\^([^\]]+)\]:\s*(.+)$")
_MD_INLINE = re.compile(r"(\*\*|__|\*|_|`)(.+?)\1")


def parse_text(text, markdown=False):
    d = Doc()
    text = _clean(text)
    feet = {}
    if markdown:
        lines = []
        for line in text.split("\n"):
            m = _MD_FOOTDEF.match(line.strip())
            if m:
                feet[m.group(1)] = m.group(2)
            else:
                lines.append(line)
        text = "\n".join(lines)
    for chunk in re.split(r"\f", text):            # Seitenvorschub = eigene Seite
        para = []

        def flush():
            if para:
                line = " ".join(x.strip() for x in para) if markdown else "\n".join(para)
                if markdown:
                    line = _MD_INLINE.sub(r"\2", line)
                    line = re.sub(r"\[\^([^\]]+)\]", lambda m: d.footnote(feet[m.group(1)]) if m.group(1) in feet else "", line)
                    line = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", line)
                d.para(line)
                para.clear()

        for line in chunk.split("\n"):
            m = _MD_HEAD.match(line) if markdown else None
            if m:
                flush()
                d.heading(m.group(2), len(m.group(1)))
            elif not line.strip():
                flush()
            else:
                para.append(line.lstrip("> ") if markdown else line.rstrip())
        flush()
        d.page_break()
    return d.finish()


# ---------- HTML (auch Kapitel aus EPUB) ----------

class _Html(HTMLParser):
    BLOCK = {"p", "div", "li", "blockquote", "tr", "section", "article", "dd", "dt", "pre", "table"}
    HEAD = {"h1": 1, "h2": 2, "h3": 3, "h4": 4}
    SKIP = {"script", "style", "head", "title", "nav"}

    def __init__(self, doc):
        super().__init__(convert_charrefs=True)
        self.d, self.buf, self.head, self.skip = doc, [], None, 0
        self.notes, self.in_note, self.note_buf = {}, None, []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in self.SKIP:
            self.skip += 1
        elif tag in self.HEAD:
            self.flush()
            self.head = (self.HEAD[tag], [])
        elif tag in self.BLOCK:
            self.flush()
        elif tag == "br":
            self.buf.append("\n")
        # EPUB-Fußnoten: <aside epub:type="footnote" id="n1">
        if "footnote" in (a.get("epub:type") or "") + (a.get("role") or "") and tag in ("aside", "div", "section", "li"):
            self.flush()
            self.in_note = a.get("id") or str(len(self.notes) + 1)
            self.note_buf = []

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self.skip = max(0, self.skip - 1)
        elif tag in self.HEAD and self.head:
            self.d.heading("".join(self.head[1]), self.head[0])
            self.head = None
        elif self.in_note and tag in ("aside", "div", "section", "li"):
            self.notes[self.in_note] = "".join(self.note_buf)
            self.in_note = None
        elif tag in self.BLOCK:
            self.flush()

    def handle_data(self, data):
        if self.skip:
            return
        if self.in_note:
            self.note_buf.append(data)
        elif self.head:
            self.head[1].append(data)
        else:
            self.buf.append(data)

    def flush(self):
        text = "".join(self.buf)
        self.buf = []
        for line in text.split("\n"):
            line = " ".join(line.split())
            if line:
                self.d.para(line)


def parse_html(text, doc=None):
    d = doc or Doc()
    p = _Html(d)
    p.feed(_clean(text))
    p.flush()
    for note in p.notes.values():        # gesammelte EPUB-Fußnoten ans Kapitelende
        d.cur_feet.append(" ".join(note.split()))
    return d if doc else d.finish()


# ---------- Word (.docx) ----------

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _heading_level(style, styles):
    name = (styles.get(style) or style or "").lower().replace(" ", "")
    if name == "title" or name.startswith("titre"):
        return 1
    m = re.match(r"(heading|überschrift|titre|عنوان)(\d)", name)
    return int(m.group(2)) if m else None


def parse_docx(data):
    import io
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        root = ET.fromstring(z.read("word/document.xml"))
    except (zipfile.BadZipFile, KeyError, ET.ParseError):
        raise ImportError_("Die Word-Datei ist beschädigt oder kein .docx (ältere .doc-Dateien bitte in Word als .docx sichern).")
    styles = {}
    if "word/styles.xml" in z.namelist():
        for s in ET.fromstring(z.read("word/styles.xml")).iter(W + "style"):
            n = s.find(W + "name")
            styles[s.get(W + "styleId")] = n.get(W + "val") if n is not None else ""
    feet = {}
    if "word/footnotes.xml" in z.namelist():
        for f in ET.fromstring(z.read("word/footnotes.xml")).iter(W + "footnote"):
            feet[f.get(W + "id")] = "".join(t.text or "" for t in f.iter(W + "t")).strip()
    d = Doc()
    for p in root.iter(W + "p"):
        sty = p.find(W + "pPr/" + W + "pStyle")
        level = _heading_level(sty.get(W + "val") if sty is not None else None, styles)
        parts = []
        for el in p.iter():
            if el.tag == W + "t":
                parts.append(el.text or "")
            elif el.tag == W + "tab":
                parts.append(" ")
            elif el.tag == W + "br" and el.get(W + "type") == "page":
                d.para(_clean("".join(parts)))
                parts = []
                d.page_break()
            elif el.tag == W + "br":
                parts.append("\n")
            elif el.tag == W + "footnoteReference" and feet.get(el.get(W + "id")):
                parts.append(d.footnote(_clean(feet[el.get(W + "id")])))
        text = _clean("".join(parts))
        if level and text.strip():
            d.heading(text, level)
        else:
            for line in text.split("\n"):
                d.para(line)
    return d.finish()


# ---------- EPUB ----------

def parse_epub(data):
    import io
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        container = ET.fromstring(z.read("META-INF/container.xml"))
        opf_path = next(e.get("full-path") for e in container.iter() if e.tag.endswith("rootfile"))
        opf = ET.fromstring(z.read(opf_path))
    except (zipfile.BadZipFile, KeyError, StopIteration, ET.ParseError):
        raise ImportError_("Die EPUB-Datei ist beschädigt oder geschützt (DRM).")
    base = posixpath.dirname(opf_path)
    items = {e.get("id"): e.get("href") for e in opf.iter() if e.tag.endswith("}item")}
    meta = {e.tag.split("}")[-1]: (e.text or "").strip() for e in opf.iter()
            if e.tag.startswith("{http://purl.org/dc/elements/1.1/}")}
    d = Doc()
    for ref in (e.get("idref") for e in opf.iter() if e.tag.endswith("}itemref")):
        href = items.get(ref)
        if not href:
            continue
        try:
            text = z.read(posixpath.normpath(posixpath.join(base, href))).decode("utf-8", "replace")
        except KeyError:
            continue
        parse_html(text, d)
        d.page_break()               # jedes Kapitel beginnt auf neuer Seite
    d.finish()
    d.meta = {"title": meta.get("title"), "author": meta.get("creator")}
    return d


# ---------- PDF ----------

_COMMON = ("الله", "على", "التي", "الذي", "هذا", "قال", "عن", "من", "في", "إلى", "ما", "لا", "أن", "كان")
_LTR_RUN = re.compile(r"[0-9A-Za-z][0-9A-Za-z.,:/%-]*")


def _score(text):
    """Wie „richtig herum“ ein arabischer Text aussieht: häufige Wörter und Artikel am Wortanfang zählen,
    Satzzeichen am Wortanfang (Zeichen für vertauschte Abschnitte) ziehen ab."""
    words = text.split()
    return (sum(w.strip(".,:;،؛!؟()") in _COMMON for w in words) + sum(w.startswith(("ال", "وال", "بال")) for w in words)
            - sum(w[0] in ".:;،؛!؟" for w in words))


def _unvisual(line):
    """Zeile in Anzeigereihenfolge (von links nach rechts gespeichert) in Lesereihenfolge bringen."""
    r = line[::-1]
    return _LTR_RUN.sub(lambda m: m.group(0)[::-1], r)


def _pdf_page_text(page):
    """Arabische PDFs speichern Text oft in Anzeigereihenfolge. Beide Lesarten von pypdf
    holen, rückwärts gespeicherte Zeilen umdrehen und die Fassung mit mehr echten Wörtern nehmen."""
    plain = _clean(page.extract_text() or "")
    if not _AR.search(plain):            # lateinische Seiten: die langsame Layout-Lesart ist unnötig
        return plain
    try:
        layout = _clean(page.extract_text(extraction_mode="layout") or "")
    except Exception:   # ältere pypdf-Versionen kennen den Modus nicht
        layout = ""
    fixed = []
    for line in layout.split("\n"):
        line = " ".join(line.split())
        if _AR.search(line) and _score(_unvisual(line)) > _score(line):
            line = _unvisual(line)
        fixed.append(line)
    layout = "\n".join(x for x in fixed if x)
    return layout if _score(layout) > _score(plain) else plain


_JXA = r"""
ObjC.import('Quartz');
function run(argv) {
  var d = $.PDFDocument.alloc.initWithURL($.NSURL.fileURLWithPath(argv[0]));
  if (!d || d.isNil() || d.isLocked) return "x";
  var out = [];
  for (var i = 0; i < d.pageCount; i++) {
    var s = d.pageAtIndex(i).string;
    out.push(s.isNil() ? "" : s.js);
  }
  $(out.join("\f")).writeToFileAtomicallyEncodingError(argv[1], true, $.NSUTF8StringEncoding, null);
  return String(d.pageCount);
}
"""


def _pdfkit_texts(data):
    """Text je Seite über PDFKit von macOS (osascript/JXA): vielfach schneller als pypdf, nichts zu installieren.
    None, wenn es nicht geht (kein Mac, gesperrte oder kaputte Datei) — dann liest pypdf."""
    import shutil
    import subprocess
    import tempfile
    if sys.platform != "darwin" or not shutil.which("osascript") or os.environ.get("YAMAKTABA_OHNE_PDFKIT"):
        return None
    with tempfile.TemporaryDirectory() as tmp:
        src, out = os.path.join(tmp, "d.pdf"), os.path.join(tmp, "d.txt")
        with open(src, "wb") as f:
            f.write(data)
        try:
            r = subprocess.run(["osascript", "-l", "JavaScript", "-e", _JXA, src, out],
                               capture_output=True, timeout=600)
        except (OSError, subprocess.SubprocessError):
            return None
        if r.returncode != 0 or not os.path.exists(out):
            return None
        with open(out, encoding="utf-8", errors="replace") as f:
            texts = [_clean(t) for t in f.read().split("\f")]
    joined = " ".join(texts)
    if len(_AR.findall(joined)) > len(re.findall(r"[A-Za-zÀ-ÿ]", joined)):
        return None                      # arabische PDFs: pypdf mit Prüfung der Leserichtung (siehe oben)
    return texts


def parse_pdf(data):
    texts = _pdfkit_texts(data)
    if texts is not None:
        if sum(len(t.strip()) for t in texts) < 20 * max(1, len(texts)) * 0.2:
            raise ImportError_("Diese PDF enthält fast keinen Text (wohl ein Scan). Scans brauchen Texterkennung, "
                               "die Yamaktaba noch nicht hat.")
        d = Doc()
        for i, t in enumerate(texts):
            for line in t.split("\n"):
                d.para(line.strip())
            d.page_break(num=i + 1)
        d.finish()
        d.meta = _pdf_meta(data)
        return d
    try:
        import pypdf
    except ImportError:
        raise ImportError_("Für PDF fehlt das Paket pypdf. Yamaktaba neu starten (es richtet sich dann ein) "
                           "oder im Terminal: python3 -m pip install --user pypdf")
    import io
    try:
        r = pypdf.PdfReader(io.BytesIO(data))
        if r.is_encrypted:
            r.decrypt("")
        texts = [_pdf_page_text(pg) for pg in r.pages]
    except Exception as e:  # pypdf meldet viele verschiedene Fehler
        raise ImportError_("Die PDF-Datei ließ sich nicht lesen (%s)." % e)
    if sum(len(t.strip()) for t in texts) < 20 * max(1, len(texts)) * 0.2:
        raise ImportError_("Diese PDF enthält fast keinen Text (wohl ein Scan). Scans brauchen Texterkennung, "
                           "die Yamaktaba noch nicht hat.")
    d = Doc()
    for i, t in enumerate(texts):
        for line in t.split("\n"):
            d.para(line.strip())
        d.page_break(num=i + 1)          # Seitenzahl wie im PDF
    d.finish()
    info = r.metadata or {}
    d.meta = {"title": info.get("/Title"), "author": info.get("/Author")}
    return d


def _pdf_meta(data):
    """Titel und Autor aus den PDF-Daten (nur der Info-Teil, schnell)."""
    try:
        import io
        import pypdf
        info = pypdf.PdfReader(io.BytesIO(data)).metadata or {}
        return {"title": info.get("/Title"), "author": info.get("/Author")}
    except Exception:
        return {}


# ---------- Weitere Formate (Yamaktaba, M11) ----------

def _textutil(data, ext):
    """Ältere Word-Dateien, RTF, ODT u. a. über das in macOS eingebaute textutil nach HTML wandeln."""
    import shutil
    import subprocess
    import tempfile
    tool = shutil.which("textutil")
    if not tool:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "datei" + ext)
        with open(src, "wb") as f:
            f.write(data)
        try:
            r = subprocess.run([tool, "-convert", "html", "-stdout", src], capture_output=True, timeout=300)
        except (OSError, subprocess.SubprocessError):
            return None
        return r.stdout.decode("utf-8", "replace") if r.returncode == 0 and r.stdout else None


def parse_odt(data):
    import io
    try:
        root = ET.fromstring(zipfile.ZipFile(io.BytesIO(data)).read("content.xml"))
    except (zipfile.BadZipFile, KeyError, ET.ParseError):
        raise ImportError_("Die ODT-Datei ist beschädigt.")
    d = Doc()
    T = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
    for el in root.iter():
        if el.tag in (T + "h", T + "p"):
            text = _clean(" ".join("".join(el.itertext()).split()))
            if el.tag == T + "h":
                d.heading(text, int(el.get(T + "outline-level") or 1))
            else:
                d.para(text)
    return d.finish()


def parse_rtf(data):
    """Einfache RTF-Lesung ohne textutil: Steuerwörter entfernen, \\uN und \\'xx wandeln."""
    t = data.decode("latin-1")
    t = re.sub(r"\\u(-?\d+)\??", lambda m: chr(int(m.group(1)) % 65536), t)
    t = re.sub(r"\\'([0-9a-fA-F]{2})", lambda m: bytes([int(m.group(1), 16)]).decode("cp1252", "replace"), t)
    t = re.sub(r"\\par[d]?\b", "\n\n", t)
    t = re.sub(r"\{\\\*[^{}]*\}|\\[a-zA-Z]+-?\d* ?|[{}]", "", t)
    return parse_text(t)


_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"


def parse_pptx(data):
    """Jede Folie wird eine Seite; der erste Absatz ist die Überschrift."""
    import io
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise ImportError_("Die PowerPoint-Datei ist beschädigt oder kein .pptx.")
    names = sorted((n for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)),
                   key=lambda n: int(re.search(r"(\d+)", n.rsplit("/", 1)[1]).group(1)))
    d = Doc()
    for i, n in enumerate(names, 1):
        paras = [" ".join("".join(t.text or "" for t in p.iter(_A + "t")).split())
                 for p in ET.fromstring(z.read(n)).iter(_A + "p")]
        paras = [_clean(x) for x in paras if x.strip()]
        d.heading(paras[0] if paras else "Folie %d" % i, 1)
        for x in paras[1:]:
            d.para(x)
        d.page_break(num=i)
    return d.finish()


def parse_xlsx(data):
    """Jede Tabelle wird ein Abschnitt, jede Zeile eine Textzeile (Zellen mit · getrennt)."""
    import io
    X = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            shared = ["".join(t.text or "" for t in si.iter(X + "t"))
                      for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(X + "si")]
        wb = ET.fromstring(z.read("xl/workbook.xml"))
    except (zipfile.BadZipFile, KeyError, ET.ParseError):
        raise ImportError_("Die Excel-Datei ist beschädigt oder kein .xlsx.")
    titles = [s.get("name") for s in wb.iter(X + "sheet")]
    sheets = sorted((n for n in z.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml$", n)),
                    key=lambda n: int(re.search(r"sheet(\d+)", n).group(1)))
    d = Doc()
    for i, n in enumerate(sheets):
        d.heading(titles[i] if i < len(titles) and titles[i] else "Tabelle %d" % (i + 1), 1)
        for row in ET.fromstring(z.read(n)).iter(X + "row"):
            cells = []
            for c in row.iter(X + "c"):
                v = c.find(X + "v")
                if c.get("t") == "s" and v is not None and v.text and v.text.isdigit() and int(v.text) < len(shared):
                    cells.append(shared[int(v.text)])
                elif c.get("t") == "inlineStr":
                    cells.append("".join(t.text or "" for t in c.iter(X + "t")))
                elif v is not None and v.text:
                    cells.append(v.text)
            line = " · ".join(x.strip() for x in cells if x and x.strip())
            if line:
                d.para(_clean(line))
        d.page_break()
    return d.finish()


def parse_djvu(data):
    import shutil
    import subprocess
    import tempfile
    tool = shutil.which("djvutxt")
    if not tool:
        raise ImportError_("Für DjVu fehlt das Programm djvutxt (Homebrew: brew install djvulibre).")
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "d.djvu")
        with open(src, "wb") as f:
            f.write(data)
        r = subprocess.run([tool, src], capture_output=True, timeout=600)
    d = Doc()
    for i, page in enumerate(r.stdout.decode("utf-8", "replace").split("\f"), 1):
        for line in page.split("\n"):
            d.para(_clean(line.strip()))
        d.page_break(num=i)
    return d.finish()


_STOP = {"de": {"der", "die", "und", "das", "ist", "nicht", "mit", "von", "für", "auf", "den", "eine", "sich"},
         "en": {"the", "and", "of", "to", "is", "in", "that", "with", "for", "this", "are", "which", "be"},
         "fr": {"le", "la", "les", "et", "des", "est", "une", "dans", "pour", "que", "qui", "pas", "sur"}}


def sprache(d):
    """Sprache aus den ersten Seiten schätzen: ar, de, en, fr (oder None)."""
    text = " ".join(re.sub(r"<[^>]+>", " ", p["body"]) for p in d.pages[:15])[:30000]
    ar = len(_AR.findall(text))
    lat = len(re.findall(r"[A-Za-zÀ-ÿ]", text))
    if ar > lat:
        return "ar"
    words = re.findall(r"[a-zà-ÿ]+", text.lower())
    score = {k: sum(w in v for w in words) for k, v in _STOP.items()}
    best = max(score, key=score.get)
    return best if score[best] >= 3 else None


# ---------- Einstieg ----------

def parse(data, filename):
    ext = os.path.splitext(filename.lower())[1]
    if ext not in FORMATS:
        raise ImportError_("Dieses Format kennt Yamaktaba nicht: %s. Möglich sind TXT, Markdown, HTML, RTF, ODT, PowerPoint, Excel, "
                           "Word (.docx), EPUB und PDF." % (ext or filename))
    if ext == ".docx":
        d = parse_docx(data)
    elif ext in (".epub", ".ibooks"):
        d = parse_epub(data)
    elif ext in (".doc", ".rtf", ".rtfd", ".odt", ".wordml", ".webarchive"):
        html_ = _textutil(data, ext)
        if html_:
            d = parse_html(html_)
        elif ext == ".odt":
            d = parse_odt(data)
        elif ext == ".rtf":
            d = parse_rtf(data)
        else:
            raise ImportError_("Dieses Format (%s) liest Yamaktaba nur auf dem Mac (über textutil)." % ext)
    elif ext == ".pptx":
        d = parse_pptx(data)
    elif ext in (".xlsx", ".xlsm"):
        d = parse_xlsx(data)
    elif ext == ".djvu":
        d = parse_djvu(data)
    elif ext == ".pdf":
        d = parse_pdf(data)
    elif ext in (".html", ".htm", ".xhtml"):
        d = parse_html(_decode(data))
    else:
        d = parse_text(_decode(data), markdown=ext in (".md", ".markdown"))
    if not any(p["body"].strip() for p in d.pages):
        raise ImportError_("In der Datei wurde kein Text gefunden.")
    d.meta = getattr(d, "meta", None) or {}
    t = (d.meta.get("title") or "").strip()
    # Titel wie „pdf.html“, „Untitled“ oder „Microsoft Word - x.docx“ sagen nichts über das Buch
    if re.search(r"\.\w{2,5}$|^untitled|^microsoft word|^document\d*$", t, re.I):
        t = ""
    if not t:
        t = next((x for _, x, _ in d.toc), None)
    if not t and ext == ".pdf":
        line = re.sub(r"<[^>]+>", "", d.pages[0]["body"]).strip().split("\n")[0].strip()
        t = line if 2 <= len(line) <= 60 else ""
    d.meta["title"] = t or os.path.splitext(os.path.basename(filename))[0]
    return d


def save(con, d, title, author=None, death=None, category=None, filename="", quelle=None, datei=None, hsh=None,
         index=True):
    """Geparstes Buch speichern; gibt die neue Buch-Nummer zurück.
    quelle: Herkunft (eigen, khizana, apple-books, gutenberg …); datei: Pfad der Originaldatei
    relativ zum Bibliotheksordner; hsh: Prüfsumme der Originaldatei (erkennt Doppelte)."""
    title = " ".join((title or d.meta.get("title") or "").split()) or "بدون عنوان"
    start = db.OWN_BOOK_START
    bid = max(start, (con.execute("SELECT MAX(id) FROM book").fetchone()[0] or 0) + 1)
    aid = None
    author = " ".join((author or d.meta.get("author") or "").split())
    if author:
        r = con.execute("SELECT id FROM author WHERE name=? ORDER BY id DESC", (author,)).fetchone()
        if r:
            aid = r[0]
        else:
            aid = max(start, (con.execute("SELECT MAX(id) FROM author").fetchone()[0] or 0) + 1)
            con.execute("INSERT INTO author (id, name, death, death_text) VALUES (?,?,?,?)",
                        (aid, author, int(death) if death else None, str(int(death)) if death else None))
    cat = int(category) if category else db.own_default_category(con)
    meta = json.dumps({"own": 1, "file": os.path.basename(filename), "added": time.strftime("%Y-%m-%d")},
                      ensure_ascii=False)
    cur = con.cursor()
    fmt = os.path.splitext(filename.lower())[1].lstrip(".") or None
    cur.execute("""INSERT INTO book (id, name, norm_name, category, orig_category, author_id, meta, pages, parts, imported,
                                     sprache, format, quelle, datei, hash)
                   VALUES (?,?,?,?,?,?,?,?,0,?,?,?,?,?,?)""",
                (bid, title, normalize(title), cat, cat, aid, meta, len(d.pages), int(time.time()),
                 sprache(d), fmt, quelle or "eigen", datei, hsh))
    terms = set()
    for i, p in enumerate(d.pages, 1):
        cur.execute("INSERT INTO page (book, pid, part, num, body, foot) VALUES (?,?,?,?,?,?)",
                    (bid, i, None, p["num"], pack(p["body"]), pack(p["foot"])))
        text = normalize(re.sub(r"<[^>]+>", " ", p["body"]) + " " + (p["foot"] or ""))
        if text and index:
            cur.execute("INSERT INTO page_fts (rowid, text) VALUES (?, ?)", (cur.lastrowid, text))
            terms.update(text.split())
    parents = {}
    for tid, (level, t, page) in enumerate(d.toc, 1):
        parents[level] = tid
        parent = next((parents[lv] for lv in range(level - 1, 0, -1) if lv in parents), 0)
        for lv in [x for x in parents if x > level]:
            del parents[lv]
        cur.execute("INSERT INTO toc (book, tid, pid, parent, title, norm_title) VALUES (?,?,?,?,?,?)",
                    (bid, tid, page + 1, parent, t, normalize(t)))
    # neue Wörter für die Wurzelsuche (ohne den ganzen Index neu zu rechnen)
    from .roots import root
    cur.executemany("INSERT OR IGNORE INTO word_root VALUES (?,?,1)",
                    [(w, root(w)) for w in terms if w.isalpha() and len(w) >= 3])
    con.commit()
    return bid


def import_file(con, data, filename, title=None, author=None, death=None, category=None, quelle=None, datei=None,
                hsh=None):
    d = parse(data, filename)
    bid = save(con, d, title, author, death, category, filename, quelle, datei, hsh)
    return {"book": bid, "pages": len(d.pages), "toc": len(d.toc), "title": db.book_info(con, bid)["name"]}


def own_books(con):
    return [dict(r) for r in con.execute("""
        SELECT b.id, b.name, b.pages, b.meta, a.name AS author, c.name AS category
        FROM book b LEFT JOIN author a ON a.id=b.author_id LEFT JOIN category c ON c.id=b.category
        WHERE b.id >= ? ORDER BY b.imported DESC""", (db.OWN_BOOK_START,))]


def delete(con, bid):
    """Eigenes Buch ganz entfernen (Seiten, Suchindex, Notizen dazu)."""
    bid = int(bid)
    if bid < db.OWN_BOOK_START:
        raise ValueError("Nur eigene Bücher lassen sich löschen.")
    for rowid, body, foot in con.execute("SELECT id, body, foot FROM page WHERE book=?", (bid,)).fetchall():
        text = normalize(re.sub(r"<[^>]+>", " ", db.unpack(body)) + " " + db.unpack(foot))
        if text:
            con.execute("INSERT INTO page_fts (page_fts, rowid, text) VALUES ('delete', ?, ?)", (rowid, text))
    for tbl in ("page", "toc", "bookmark", "note", "collection_book", "reading"):
        con.execute("DELETE FROM %s WHERE book=?" % tbl, (bid,))
    con.execute("DELETE FROM book WHERE id=?", (bid,))
    con.commit()
