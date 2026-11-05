"""Yamaktaba-Datenbank: Schema und Abfragen (von App und MCP-Server gemeinsam genutzt)."""
import json
import os
import sqlite3
import zlib

from .normalize import (normalize, normalize_with_map, strip_tags, western_digits,
                        word_variants)

SCHEMA = """
CREATE TABLE IF NOT EXISTS category (id INTEGER PRIMARY KEY, name TEXT, ord INTEGER);
CREATE TABLE IF NOT EXISTS author (id INTEGER PRIMARY KEY, name TEXT, death INTEGER, death_text TEXT);
CREATE TABLE IF NOT EXISTS book (
  id INTEGER PRIMARY KEY, name TEXT, norm_name TEXT, category INTEGER, author_id INTEGER,
  authors TEXT, date INTEGER, meta TEXT, pages INTEGER, parts INTEGER, imported INTEGER);
CREATE TABLE IF NOT EXISTS page (
  id INTEGER PRIMARY KEY, book INTEGER NOT NULL, pid INTEGER NOT NULL,
  part TEXT, num INTEGER, hadith INTEGER, body BLOB, foot BLOB);
CREATE UNIQUE INDEX IF NOT EXISTS page_book ON page (book, pid);
CREATE TABLE IF NOT EXISTS toc (
  book INTEGER, tid INTEGER, pid INTEGER, parent INTEGER, title TEXT,
  PRIMARY KEY (book, tid)) WITHOUT ROWID;
CREATE VIRTUAL TABLE IF NOT EXISTS page_fts USING fts5(
  text, content='', columnsize=0, tokenize='unicode61 remove_diacritics 0');
CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS bookmark (
  id INTEGER PRIMARY KEY, book INTEGER NOT NULL, pid INTEGER NOT NULL, note TEXT, created INTEGER);
CREATE UNIQUE INDEX IF NOT EXISTS bookmark_page ON bookmark (book, pid);
CREATE TABLE IF NOT EXISTS reading (book INTEGER PRIMARY KEY, pid INTEGER, updated INTEGER);
CREATE TABLE IF NOT EXISTS word_root (term TEXT PRIMARY KEY, root TEXT, docs INTEGER) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS word_root_root ON word_root (root);
CREATE TABLE IF NOT EXISTS note (
  id INTEGER PRIMARY KEY, book INTEGER NOT NULL, pid INTEGER NOT NULL,
  field TEXT, start INTEGER, end INTEGER, quote TEXT, color TEXT, note TEXT, norm TEXT,
  created INTEGER, updated INTEGER);
CREATE INDEX IF NOT EXISTS note_page ON note (book, pid);
CREATE TABLE IF NOT EXISTS quran (id INTEGER PRIMARY KEY, sura INTEGER, aya INTEGER, text TEXT, norm TEXT);
CREATE TABLE IF NOT EXISTS collection (id INTEGER PRIMARY KEY, name TEXT NOT NULL, created INTEGER);
CREATE TABLE IF NOT EXISTS collection_book (
  collection INTEGER NOT NULL, book INTEGER NOT NULL, added INTEGER,
  PRIMARY KEY (collection, book)) WITHOUT ROWID;
"""


def default_path():
    base = os.environ.get("ASHAMILA_DATA") or os.path.expanduser("~/Library/Application Support/Ashamila")
    return os.path.join(base, "bibliothek.db")


def files_root():
    """Ordner der Originaldateien (Yamaktaba): ashamila/bibliothek neben ashamila/daten."""
    return os.path.abspath(os.environ.get("YAMAKTABA_DATEIEN") or
                           os.path.join(os.path.dirname(default_path()), os.pardir, "bibliothek"))


def original_path(con, book_id):
    """Absoluter Pfad der Originaldatei eines Buches (oder None); nie außerhalb des Bibliotheksordners."""
    r = con.execute("SELECT datei FROM book WHERE id=?", (int(book_id),)).fetchone()
    if not r or not r[0]:
        return None
    root = files_root()
    p = os.path.abspath(os.path.join(root, r[0]))
    return p if p.startswith(root + os.sep) and os.path.isfile(p) else None


def connect(path=None, create=False):
    path = path or default_path()
    if not create and not os.path.exists(path):
        raise FileNotFoundError(
            "Noch keine Bibliothek gefunden (%s). Bitte zuerst Bücher übernehmen." % path)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    con = sqlite3.connect(path, check_same_thread=False)
    con.row_factory = sqlite3.Row
    try:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA journal_size_limit=67108864")   # Zwischendatei nach großen Übernahmen wieder klein
    except sqlite3.OperationalError:
        pass  # z. B. auf Netz- oder geteilten Laufwerken: Standard-Journal genügt
    con.executescript(SCHEMA)  # legt auch neue Tabellen in älteren Bibliotheken an
    con.create_function("norm", 1, normalize, deterministic=True)
    _migrate(con)
    return con


def ensure_roots(con, log=lambda *_: None):
    """Wurzeltabelle einmalig bauen, falls sie fehlt (Bibliotheken aus älteren Versionen)."""
    if con.execute("SELECT 1 FROM page LIMIT 1").fetchone() and \
            not con.execute("SELECT 1 FROM word_root LIMIT 1").fetchone():
        from .roots import build_root_table
        build_root_table(con, log)


def _migrate(con):
    """Spalten nachrüsten, die ältere Bibliotheken noch nicht haben."""
    if "bio" not in {r[1] for r in con.execute("PRAGMA table_info(author)")}:
        con.execute("ALTER TABLE author ADD COLUMN bio TEXT")   # Biografie aus Shamela (M7)
        con.commit()
    # M9: eigene Kategorien (own=1) und verschobene Bücher (orig_category = Shamelas Kategorie)
    ccols = {r[1] for r in con.execute("PRAGMA table_info(category)")}
    if "own" not in ccols:
        con.execute("ALTER TABLE category ADD COLUMN own INTEGER")
        con.commit()
    if "parent" not in ccols:   # Oberkategorie (eine Ebene), z. B. „Westen“ → „Philosophie“
        con.execute("ALTER TABLE category ADD COLUMN parent INTEGER")
        con.commit()
    bcols = {r[1] for r in con.execute("PRAGMA table_info(book)")}
    if "orig_category" not in bcols:
        con.execute("ALTER TABLE book ADD COLUMN orig_category INTEGER")
        con.execute("ALTER TABLE book ADD COLUMN moved INTEGER")
        con.execute("UPDATE book SET orig_category = category")
        con.commit()
    if "sprache" not in bcols:   # Yamaktaba (M11): Herkunft, Format, Sprache, Originaldatei, Prüfsumme
        for c in ("sprache", "format", "quelle", "datei", "hash"):
            con.execute("ALTER TABLE book ADD COLUMN %s TEXT" % c)
        con.execute("UPDATE book SET sprache='ar', quelle='shamela' WHERE id < ?", (OWN_BOOK_START,))
        con.execute("""UPDATE book SET quelle='gutenberg', format='html',
                       sprache=COALESCE(json_extract(meta, '$.sprache'), 'en')
                       WHERE id >= ? AND meta LIKE '%"gutenberg"%'""", (OWN_BOOK_START,))
        for bid, meta in con.execute("SELECT id, meta FROM book WHERE id >= ? AND quelle IS NULL",
                                     (OWN_BOOK_START,)).fetchall():
            f = (json.loads(meta or "{}").get("file") or "")
            con.execute("UPDATE book SET quelle='eigen', format=? WHERE id=?",
                        (os.path.splitext(f)[1].lstrip(".").lower() or None, bid))
        con.commit()
    con.execute("CREATE INDEX IF NOT EXISTS book_hash ON book (hash)")
    cols = {r[1] for r in con.execute("PRAGMA table_info(toc)")}
    if "norm_title" not in cols:
        con.execute("ALTER TABLE toc ADD COLUMN norm_title TEXT")
        con.execute("UPDATE toc SET norm_title = norm(title)")
        con.commit()


def unpack(blob):
    return zlib.decompress(blob).decode("utf-8") if blob else ""


def _death(row):
    return row["death"] if row["death"] and row["death"] < 99999 else None


# ---------- Katalog ----------

OWN_BOOK_START = 10_000_000   # eigene (importierte) Bücher und Autoren; Shamela-Nummern sind viel kleiner
OWN_CAT_START = 1000          # eigene Kategorien

def _tree(rows):
    """Unterkategorien direkt unter ihre Oberkategorie stellen (depth 1); die Oberkategorie zählt ihre Bücher mit."""
    rows = [dict(r) | {"own": bool(r["own"]), "depth": 0} for r in rows]
    ids = {r["id"] for r in rows}
    kids = {}
    for r in rows:
        if r.get("parent") in ids:
            kids.setdefault(r["parent"], []).append(r | {"depth": 1})
    out = []
    for r in rows:
        if r.get("parent") in ids:
            continue
        sub = kids.get(r["id"], [])
        r["books"] += sum(k["books"] for k in sub)
        r["has_children"] = bool(sub)
        out += [r] + sub
    return out


def category_ids(con, cid):
    """Eine Kategorie samt ihren Unterkategorien (für Filter und Suche)."""
    return [int(cid)] + [r[0] for r in con.execute("SELECT id FROM category WHERE parent = ?", (int(cid),))]


def _in(ids):
    return "(%s)" % ",".join(str(int(i)) for i in ids)


def categories(con):
    """Kategorien mit übernommenen Büchern; eigene Kategorien immer (auch leer, als Ziel zum Verschieben)."""
    return _tree(con.execute("""
        SELECT c.id, c.name, c.own, c.parent, COUNT(b.id) AS books
        FROM category c LEFT JOIN book b ON b.category = c.id AND b.imported > 0
        GROUP BY c.id HAVING books > 0 OR c.own ORDER BY c.own IS NOT NULL, c.ord, c.name"""))


SORTS = {
    "title": "b.name",
    "death": "CASE WHEN a.death IS NULL OR a.death >= 99999 THEN 1 ELSE 0 END, a.death, b.name",
    "author": "a.name, b.name",
}


def books(con, category=None, query=None, author=None, death_from=None, death_to=None,
          sort="title", limit=3000, collection=None):
    """Bücher filtern: Kategorie, Sammlung, Titel/Autor-Text, Autor, Sterbejahr (von–bis, Hidschra)."""
    sql = """SELECT b.id, b.name, b.category, b.pages, b.parts, a.id AS author_id,
                    a.name AS author, a.death
             FROM book b LEFT JOIN author a ON a.id = b.author_id
             WHERE b.imported > 0"""
    args = []
    if death_from is not None:
        sql += " AND a.death >= ?"
        args.append(int(death_from))
    if death_to is not None:
        sql += " AND a.death <= ?"
        args.append(int(death_to))
    if category:
        sql += " AND b.category IN " + _in(category_ids(con, category))
    if author:
        sql += " AND b.author_id = ?"
        args.append(int(author))
    if collection:
        sql += " AND b.id IN (SELECT book FROM collection_book WHERE collection = ?)"
        args.append(int(collection))
    if query:
        for t in normalize(query).split():
            sql += " AND (b.norm_name LIKE ? OR norm(a.name) LIKE ?)"
            args += ["%" + t + "%", "%" + t + "%"]
    sql += " ORDER BY " + SORTS.get(sort, SORTS["title"]) + " LIMIT ?"
    args.append(limit)
    return [dict(r) | {"death": _death(r)} for r in con.execute(sql, args)]


def book_info(con, book_id):
    r = con.execute("""SELECT b.*, a.name AS author, a.death, a.death_text, c.name AS category_name
                       FROM book b LEFT JOIN author a ON a.id = b.author_id
                       LEFT JOIN category c ON c.id = b.category WHERE b.id = ?""", (book_id,)).fetchone()
    if not r:
        return None
    info = {k: r[k] for k in ("id", "name", "category", "category_name", "author_id", "author",
                              "death_text", "pages", "parts", "orig_category")}
    info["own"] = r["id"] >= OWN_BOOK_START
    info["death"] = _death(r)
    keys = r.keys()
    for k in ("sprache", "format", "quelle"):
        info[k] = r[k] if k in keys else None
    info["original"] = bool("datei" in keys and r["datei"])
    first = con.execute("SELECT MIN(pid) FROM page WHERE book=?", (book_id,)).fetchone()[0]
    info["first_pid"] = first
    info["volumes"] = [x[0] for x in con.execute(
        "SELECT part FROM page WHERE book=? AND part IS NOT NULL GROUP BY part ORDER BY MIN(pid)",
        (book_id,))]
    return info


def author_info(con, author_id):
    r = con.execute("SELECT * FROM author WHERE id=?", (author_id,)).fetchone()
    if not r:
        return None
    others = con.execute("""SELECT b.id, b.name, c.name AS category FROM book b
                            LEFT JOIN category c ON c.id = b.category
                            WHERE b.author_id = ? AND (b.imported IS NULL OR b.imported <= 0)
                            ORDER BY b.name""", (author_id,)).fetchall()
    return {"id": r["id"], "name": r["name"], "death": _death(r), "death_text": r["death_text"],
            "bio": western_digits(r["bio"] or "") or None,
            "books": books(con, author=author_id, sort="title"),
            "other_books": [dict(x) for x in others]}


# ---------- Eigene Kategorien und Verschieben (M9) ----------

def all_categories(con):
    """Alle Kategorien für die Verwaltung: eigene zuerst, dann Shamelas mit übernommenen Büchern."""
    return _tree(con.execute("""
        SELECT c.id, c.name, c.own, c.parent, COUNT(b.id) AS books,
               SUM(CASE WHEN b.id >= ? THEN 1 ELSE 0 END) AS own_books
        FROM category c LEFT JOIN book b ON b.category = c.id AND b.imported > 0
        GROUP BY c.id HAVING books > 0 OR c.own ORDER BY c.own IS NULL, c.ord, c.name""", (OWN_BOOK_START,)))


def save_category(con, name, cid=None, parent=None):
    """Eigene Kategorie anlegen oder umbenennen; Shamelas Kategorien bleiben unverändert.
    parent: eigene Oberkategorie (nur eine Ebene), 0 = keine, None = unverändert."""
    name = " ".join((name or "").split())
    if not name:
        raise ValueError("Bitte einen Namen angeben.")
    clash = con.execute("SELECT id FROM category WHERE name = ? AND id IS NOT ?", (name, cid)).fetchone()
    if clash:
        raise ValueError("Diese Kategorie gibt es schon.")
    if cid:
        if not con.execute("SELECT 1 FROM category WHERE id=? AND own", (cid,)).fetchone():
            raise ValueError("Nur eigene Kategorien lassen sich umbenennen.")
        con.execute("UPDATE category SET name=? WHERE id=?", (name, cid))
    else:
        cid = max(OWN_CAT_START, (con.execute("SELECT MAX(id) FROM category").fetchone()[0] or 0) + 1)
        con.execute("INSERT INTO category (id, name, ord, own) VALUES (?,?,?,1)", (cid, name, cid))
    if parent is not None:
        parent = int(parent) or None
        if parent:
            ok = con.execute("SELECT 1 FROM category WHERE id=? AND own AND parent IS NULL", (parent,)).fetchone()
            if not ok or parent == cid:
                raise ValueError("Oberkategorie muss eine eigene Kategorie der obersten Ebene sein.")
            if con.execute("SELECT 1 FROM category WHERE parent=?", (cid,)).fetchone():
                raise ValueError("Eine Kategorie mit Unterkategorien kann nicht selbst darunter stehen.")
        con.execute("UPDATE category SET parent=? WHERE id=?", (parent, cid))
    con.commit()
    return cid


def own_default_category(con, name="كتبي"):
    """Kategorie für eigene Bücher ohne Angabe (wird bei Bedarf angelegt)."""
    r = con.execute("SELECT id FROM category WHERE own AND name=?", (name,)).fetchone()
    return r[0] if r else save_category(con, name)


def delete_category(con, cid):
    """Eigene Kategorie löschen. Shamela-Bücher kehren in ihre Shamela-Kategorie zurück,
    eigene Bücher in „كتبي“ (die selbst nur leer gelöscht werden kann)."""
    r = con.execute("SELECT name FROM category WHERE id=? AND own", (cid,)).fetchone()
    if not r:
        raise ValueError("Nur eigene Kategorien lassen sich löschen.")
    if con.execute("SELECT 1 FROM category WHERE parent=?", (cid,)).fetchone():
        raise ValueError("Diese Kategorie hat Unterkategorien. Bitte zuerst sie löschen oder verschieben.")
    own_books = con.execute("SELECT COUNT(*) FROM book WHERE category=? AND id >= ?", (cid, OWN_BOOK_START)).fetchone()[0]
    if own_books:
        target = own_default_category(con)
        if target == cid:
            raise ValueError("Diese Kategorie enthält eigene Bücher. Bitte sie zuerst verschieben.")
        con.execute("UPDATE book SET category=?, orig_category=? WHERE category=? AND id >= ?",
                    (target, target, cid, OWN_BOOK_START))
    con.execute("UPDATE book SET category = orig_category, moved = NULL WHERE category = ?", (cid,))
    con.execute("DELETE FROM category WHERE id=?", (cid,))
    con.commit()


def move_books(con, books, cid):
    """Bücher in eine Kategorie verschieben. Zurück in die Shamela-Kategorie hebt die Verschiebung auf."""
    if not con.execute("SELECT 1 FROM category WHERE id=?", (cid,)).fetchone():
        raise ValueError("Unbekannte Kategorie.")
    ids = [int(b) for b in books]
    for b in ids:
        if b >= OWN_BOOK_START:   # eigene Bücher: die neue Kategorie ist ihre einzige
            con.execute("UPDATE book SET category=?, orig_category=?, moved=NULL WHERE id=?", (cid, cid, b))
        else:
            con.execute("UPDATE book SET category=?, moved = CASE WHEN orig_category IS ? THEN NULL ELSE 1 END "
                        "WHERE id=?", (cid, cid, b))
    con.commit()
    return len(ids)


# ---------- Lesezeichen und Lesefortschritt ----------

def _page_label(part, num):
    return ("%s/%s" % (part, num)) if part else (str(num) if num is not None else "")


def bookmarks(con):
    return [dict(r) | {"where": _page_label(r["part"], r["num"])} for r in con.execute("""
        SELECT m.id, m.book, m.pid, m.note, m.created, b.name AS book_name, p.part, p.num
        FROM bookmark m JOIN book b ON b.id = m.book
        LEFT JOIN page p ON p.book = m.book AND p.pid = m.pid
        ORDER BY m.created DESC""")]


def toggle_bookmark(con, book_id, pid, note=None):
    """Lesezeichen setzen oder entfernen. Rückgabe: True, wenn jetzt gesetzt."""
    cur = con.execute("DELETE FROM bookmark WHERE book=? AND pid=?", (book_id, pid))
    if cur.rowcount:
        con.commit()
        return False
    con.execute("INSERT INTO bookmark (book, pid, note, created) VALUES (?,?,?,strftime('%s','now'))",
                (book_id, pid, note))
    con.commit()
    return True


def is_bookmarked(con, book_id, pid):
    return con.execute("SELECT 1 FROM bookmark WHERE book=? AND pid=?", (book_id, pid)).fetchone() is not None


def save_progress(con, book_id, pid):
    con.execute("INSERT OR REPLACE INTO reading VALUES (?, ?, strftime('%s','now'))", (book_id, pid))
    con.commit()


def recent(con, limit=12):
    """Zuletzt gelesene Bücher mit Fortschritt in Prozent."""
    out = []
    for r in con.execute("""
            SELECT r.book, r.pid, r.updated, b.name AS book_name, a.name AS author, p.part, p.num,
                   (SELECT COUNT(*) FROM page x WHERE x.book = r.book AND x.pid <= r.pid) AS done,
                   (SELECT COUNT(*) FROM page x WHERE x.book = r.book) AS total
            FROM reading r JOIN book b ON b.id = r.book LEFT JOIN author a ON a.id = b.author_id
            LEFT JOIN page p ON p.book = r.book AND p.pid = r.pid
            ORDER BY r.updated DESC LIMIT ?""", (limit,)):
        d = dict(r)
        d["percent"] = round(100 * d["done"] / d["total"]) if d["total"] else 0
        d["where"] = _page_label(d["part"], d["num"])
        out.append(d)
    return out


def last_position(con, book_id):
    r = con.execute("SELECT pid FROM reading WHERE book=?", (book_id,)).fetchone()
    return r[0] if r else None


def toc(con, book_id):
    return [dict(r) for r in con.execute(
        "SELECT tid, pid, parent, title FROM toc WHERE book=? ORDER BY tid", (book_id,))]


def page(con, book_id, pid=None, part=None, num=None):
    """Eine Seite holen: über interne Nummer (pid) oder über Band/Seite der Druckausgabe."""
    if pid is None and num is not None:
        sql = "SELECT pid FROM page WHERE book=? AND num>=?"
        args = [book_id, int(num)]
        if part:
            sql += " AND part=?"
            args.append(str(part))
        row = con.execute(sql + " ORDER BY pid LIMIT 1", args).fetchone()
        pid = row[0] if row else None
    if pid is None:
        pid = con.execute("SELECT MIN(pid) FROM page WHERE book=?", (book_id,)).fetchone()[0]
    r = con.execute("SELECT * FROM page WHERE book=? AND pid=?", (book_id, pid)).fetchone()
    if not r:
        return None
    prev_ = con.execute("SELECT MAX(pid) FROM page WHERE book=? AND pid<?", (book_id, pid)).fetchone()[0]
    next_ = con.execute("SELECT MIN(pid) FROM page WHERE book=? AND pid>?", (book_id, pid)).fetchone()[0]
    total = con.execute("SELECT COUNT(*) FROM page WHERE book=?", (book_id,)).fetchone()[0]
    done = con.execute("SELECT COUNT(*) FROM page WHERE book=? AND pid<=?", (book_id, pid)).fetchone()[0]
    # letzte gedruckte Seitenzahl im selben Band, für die Anzeige „von …“ neben der Seitenwahl
    last = con.execute("SELECT MAX(num) FROM page WHERE book=? AND part IS ?", (book_id, r["part"])).fetchone()[0]
    return {"book": book_id, "pid": pid, "part": r["part"], "num": r["num"], "last": last,
            "percent": round(100 * done / total) if total else 0,
            "bookmarked": is_bookmarked(con, book_id, pid),
            "notes": page_notes(con, book_id, pid),
            "body": western_digits(unpack(r["body"])), "foot": western_digits(unpack(r["foot"])),
            "prev": prev_, "next": next_}


def citation(con, book_id, pid):
    """Fertige Quellenangabe, z. B.: المصنف، عبد الرزاق الصنعاني (ت 211هـ)، 1/45"""
    info = book_info(con, book_id)
    p = con.execute("SELECT part, num FROM page WHERE book=? AND pid=?", (book_id, pid)).fetchone()
    if not info or not p:
        return ""
    who = info["author"] or ""
    if info["death"]:
        who += " (ت %dهـ)" % info["death"]
    where = ("%s/%s" % (p["part"], p["num"])) if p["part"] else ("ص %s" % p["num"] if p["num"] else "")
    return "، ".join(x for x in (info["name"], who, where) if x)


# ---------- Suche ----------
#
# Schreibweise der Suchanfrage:
#   wort1 wort2        beide Wörter müssen vorkommen (UND)
#   wort1 ODER wort2   eines davon (auch: OR, أو, |)
#   -wort              Seiten mit diesem Wort ausschließen (NICHT)
#   "genaue wendung"   Wendung genau so
# Modus „wurzel“: jedes Wort steht für alle Wörter mit derselben Wurzel.
# Wortnähe (near=n): alle Wörter höchstens n Wörter voneinander entfernt.

OR_WORDS = {"oder", "or", "ou", "او", "|"}
MAX_ROOT_FORMS = 120


def parse_query(query):
    """Anfrage in Gruppen zerlegen: [(negiert, [Begriff, …]), …]; Begriffe einer Gruppe sind ODER-verknüpft."""
    import re
    groups, pending_or = [], False
    for phrase, word in re.findall(r'"([^"]+)"|(\S+)', query or ""):
        raw = phrase or word
        neg = bool(word) and raw.startswith("-") and len(raw) > 1
        term = normalize(raw[1:] if neg else raw)
        if not phrase and normalize(raw) in OR_WORDS or raw == "|":
            pending_or = bool(groups)
            continue
        if not term:
            continue
        if pending_or and not neg and not groups[-1][0]:
            groups[-1][1].append(term)
        else:
            groups.append((neg, [term]))
        pending_or = False
    return groups


def root_forms(con, term):
    """Alle Wörter im Index mit derselben Wurzel wie term (häufigste zuerst)."""
    from .roots import root
    r = root(term)
    forms = [x[0] for x in con.execute(
        "SELECT term FROM word_root WHERE root=? ORDER BY docs DESC LIMIT ?", (r, MAX_ROOT_FORMS))]
    return forms or [term], r


def _fts_item(con, term, mode, highlights, roots):
    if " " in term:
        highlights.append(term)
        return '"%s"' % term
    if mode == "root":
        forms, r = root_forms(con, term)
        roots.append(r)
    elif _latin(term):
        stem = latin_stem(term)          # Deutsch/Englisch: Getriebe, Getrieben, Getriebes …
        highlights.append(stem)
        return '("%s" OR "%s"*)' % (term, stem)
    else:
        forms = word_variants(term)
    highlights.extend(forms if mode == "root" else [term])
    return "(" + " OR ".join('"%s"' % f for f in forms) + ")"


_LATIN_ENDINGS = ("ungen", "ingen", "heiten", "keiten", "ungen", "ions", "ings", "ness", "ment", "heit", "keit",
                  "ern", "ing", "ung", "ion", "ies", "ied", "est", "ers", "en", "er", "es", "em", "ed", "ly",
                  "e", "s", "n")


def _latin(term):
    return any("a" <= c <= "z" or "à" <= c <= "ÿ" for c in term) and not any("\u0600" <= c <= "\u06ff" for c in term)


def latin_stem(word):
    """Leichter Wortstamm für Deutsch und Englisch (für die Präfixsuche), mindestens 4 Buchstaben."""
    w = word.lower()
    for e in _LATIN_ENDINGS:
        if w.endswith(e) and len(w) - len(e) >= 4:
            return w[:-len(e)]
    return w


def build_match(con, query, mode="words", near=None):
    """FTS5-Ausdruck, Hervorhebungsbegriffe und erkannte Wurzeln."""
    groups = parse_query(query)
    pos = [g for neg, g in groups if not neg]
    negs = [g for neg, g in groups if neg]
    if not pos:
        return None, [], []
    highlights, roots = [], []
    singles = [g[0] for g in pos if len(g) == 1 and " " not in g[0]]
    if near and mode != "root" and len(pos) > 1 and len(singles) == len(pos):
        expr = "NEAR(%s, %d)" % (" ".join('"%s"' % w for w in singles), int(near))
        highlights.extend(singles)
    else:
        expr = " AND ".join("(" + " OR ".join(_fts_item(con, t, mode, highlights, roots) for t in g) + ")"
                            for g in pos)
    for g in negs:
        forms = [f for t in g for f in ([t] if " " in t else word_variants(t))]
        expr = "(%s) NOT (%s)" % (expr, " OR ".join('"%s"' % f for f in forms))
    return expr, highlights, roots


_MARKS = set(range(0x064B, 0x0660)) | {0x0670} | set(range(0x06D6, 0x06EE))


def _snippet(text, terms, width=90):
    """Ausschnitt um den ersten Treffer, Treffer mit <mark> markiert (HTML-sicher)."""
    import html
    plain = strip_tags(text)
    norm, pos = normalize_with_map(plain)
    hits = []
    for t in terms:
        start = 0
        while True:
            i = norm.find(t, start)
            if i < 0:
                break
            e = pos[i + len(t) - 1] + 1
            while e < len(plain) and ord(plain[e]) in _MARKS:   # Vokalzeichen am Wortende mitnehmen
                e += 1
            hits.append((pos[i], e))
            start = i + len(t)
    hits.sort()
    if not hits:
        return html.escape(plain[: width * 2]), 0
    a = max(0, hits[0][0] - width)
    b = min(len(plain), hits[0][1] + width)
    while a > 0 and not plain[a - 1].isspace():
        a -= 1
    out, cur = [], a
    for s, e in hits:
        if s < cur or e > b:
            continue
        out.append(html.escape(plain[cur:s]))
        out.append("<mark>" + html.escape(plain[s:e]) + "</mark>")
        cur = e
    out.append(html.escape(plain[cur:b]))
    return ("… " if a else "") + "".join(out) + (" …" if b < len(plain) else ""), len(hits)


FILTER_COLS = ("sprache", "format", "quelle")


def _filters(category, book, con=None, extra=None):
    """extra: {"sprache": "de", "format": "pdf", "quelle": "khizana"} schränkt zusätzlich ein."""
    sql, args = "", []
    for k, v in (extra or {}).items():
        if k in FILTER_COLS and v:
            sql += " AND b.%s = ?" % k
            args.append(str(v))
    if book:
        sql += " AND p.book = ?"
        args.append(int(book))
    if category:
        sql += " AND b.category IN " + _in(category_ids(con, category))
    return sql, args


def search(con, query, category=None, book=None, limit=200, mode="words", near=None, extra=None):
    """Volltextsuche. mode: words | root | titles | files. Ergebnis mit Treffern, Zahl und Treffern je Buch.
    extra: Filter nach Sprache, Format, Quelle (siehe _filters)."""
    if mode == "titles":
        return search_titles(con, query, category, book, limit)
    if mode == "files":
        return search_files(con, query, category, limit, extra)
    try:
        expr, terms, roots = build_match(con, query, mode, near)
    except Exception:
        expr = None
    if not expr:
        return {"query": query, "total": 0, "hits": [], "books": [], "terms": [], "roots": []}
    where, fargs = _filters(category, book, con, extra)
    base = """FROM page_fts f JOIN page p ON p.id = f.rowid JOIN book b ON b.id = p.book
              WHERE page_fts MATCH ?""" + where
    args = [expr] + fargs
    rows = con.execute("""SELECT p.book, p.pid, p.part, p.num, p.body, p.foot, b.name AS book_name,
                                 b.sprache, b.format, b.datei, a.name AS author, a.death """ + base.replace(
        "JOIN book b ON b.id = p.book", "JOIN book b ON b.id = p.book LEFT JOIN author a ON a.id = b.author_id") +
        " ORDER BY f.rank LIMIT ?", args + [limit]).fetchall()
    hl = sorted(set(terms), key=len, reverse=True)
    hits = []
    for r in rows:
        snip, n = _snippet(unpack(r["body"]), hl)
        if n == 0 and r["foot"]:
            snip, n = _snippet(unpack(r["foot"]), hl)
        hits.append({"book": r["book"], "book_name": r["book_name"], "author": r["author"],
                     "sprache": r["sprache"], "format": r["format"], "datei": bool(r["datei"]),
                     "death": r["death"] if r["death"] and r["death"] < 99999 else None,
                     "pid": r["pid"], "part": r["part"], "num": r["num"],
                     "snippet": western_digits(snip)})
    per_book = [dict(x) for x in con.execute(
        "SELECT p.book, b.name, COUNT(*) AS n " + base + " GROUP BY p.book ORDER BY n DESC LIMIT 40", args)]
    total = con.execute("SELECT COUNT(*) " + base, args).fetchone()[0]
    return {"query": query, "terms": hl[:200], "roots": roots, "total": total, "hits": hits, "books": per_book}


def find_pages(con, query, book, mode="words", near=None):
    """Alle Seiten eines Buches mit Treffern, in Buchreihenfolge (für „nächster/vorheriger Treffer“)."""
    try:
        expr, terms, _ = build_match(con, query, mode, near)
    except Exception:
        expr = None
    if not expr or mode == "titles":
        return {"pids": [], "terms": []}
    where, fargs = _filters(None, book)
    rows = con.execute("""SELECT p.pid FROM page_fts f JOIN page p ON p.id = f.rowid JOIN book b ON b.id = p.book
                          WHERE page_fts MATCH ?""" + where + " ORDER BY p.pid LIMIT 20000", [expr] + fargs)
    return {"pids": [r[0] for r in rows], "terms": sorted(set(terms), key=len, reverse=True)[:200]}


def search_files(con, query, category=None, limit=200, extra=None):
    """Suche in Buchtiteln und Dateinamen (auch Bücher, deren Text nicht lesbar ist)."""
    words = normalize(query or "").split()
    if not words:
        return {"query": query, "total": 0, "hits": [], "books": [], "terms": [], "roots": []}
    sql = """SELECT b.id, b.name, b.sprache, b.format, b.datei, a.name AS author,
             (SELECT MIN(pid) FROM page WHERE book = b.id) AS first FROM book b
             LEFT JOIN author a ON a.id = b.author_id WHERE b.imported > 0"""
    args = []
    for w in words:
        sql += " AND (b.norm_name LIKE ? OR lower(b.datei) LIKE ?)"
        args += ["%" + w + "%", "%" + w + "%"]
    for k, v in (extra or {}).items():
        if k in FILTER_COLS and v:
            sql += " AND b.%s = ?" % k
            args.append(str(v))
    if category:
        sql += " AND b.category IN " + _in(category_ids(con, category))
    rows = con.execute(sql + " LIMIT ?", args + [limit]).fetchall()
    import html
    hits = [{"book": r["id"], "book_name": r["name"], "author": r["author"], "pid": r["first"], "part": None, "num": 1,
             "sprache": r["sprache"], "format": r["format"], "datei": bool(r["datei"]),
             "snippet": html.escape(os.path.basename(r["datei"] or ""))} for r in rows]
    return {"query": query, "terms": words, "roots": [], "total": len(hits), "hits": hits,
            "books": [{"book": h["book"], "name": h["book_name"], "n": 1} for h in hits[:40]]}


def search_titles(con, query, category=None, book=None, limit=200):
    """Suche nur in Kapitelüberschriften (Inhaltsverzeichnissen)."""
    groups = parse_query(query)
    pos = [g for neg, g in groups if not neg]
    if not pos:
        return {"query": query, "total": 0, "hits": [], "books": [], "terms": [], "roots": []}
    sql = """SELECT t.book, t.pid, t.title, b.name AS book_name, p.part, p.num
             FROM toc t JOIN book b ON b.id = t.book AND b.imported > 0
             LEFT JOIN page p ON p.book = t.book AND p.pid = t.pid WHERE 1"""
    args = []
    for g in pos:
        sql += " AND (" + " OR ".join("t.norm_title LIKE ?" for _ in g) + ")"
        args += ["%" + x + "%" for x in g]
    for neg, g in groups:
        if neg:
            for x in g:
                sql += " AND t.norm_title NOT LIKE ?"
                args.append("%" + x + "%")
    if book:
        sql += " AND t.book = ?"
        args.append(int(book))
    if category:
        sql += " AND b.category IN " + _in(category_ids(con, category))
    rows = con.execute(sql + " LIMIT ?", args + [limit]).fetchall()
    terms = [x for g in pos for x in g]
    hits = [{"book": r["book"], "book_name": r["book_name"], "pid": r["pid"], "part": r["part"],
             "num": r["num"], "snippet": western_digits(_snippet(r["title"] or "", terms)[0])} for r in rows]
    counts = {}
    for h in hits:
        counts.setdefault(h["book"], [h["book_name"], 0])[1] += 1
    books_ = sorted(({"book": k, "name": v[0], "n": v[1]} for k, v in counts.items()), key=lambda x: -x["n"])
    return {"query": query, "terms": terms, "roots": [], "total": len(hits), "hits": hits, "books": books_[:40]}


# ---------- Markierungen und Notizen ----------
#
# Eine Notiz gehört zu einer Seite. Markierungen merken sich die Textstelle als Zeichenbereich
# (field = body oder foot, start–end im angezeigten Text) und zusätzlich den Wortlaut (quote),
# damit sie auch wiedergefunden wird, falls sich die Darstellung einmal ändert.
# Ohne quote ist es eine Notiz zur ganzen Seite.

COLORS = ("yellow", "green", "blue", "red")
NOTE_COLS = "id, book, pid, field, start, end, quote, color, note, created, updated"


def page_notes(con, book_id, pid):
    return [dict(r) for r in con.execute(
        "SELECT " + NOTE_COLS + " FROM note WHERE book=? AND pid=? ORDER BY field, start", (book_id, pid))]


def save_note(con, d):
    """Markierung/Notiz anlegen (ohne id) oder ändern (mit id). Gibt die gespeicherte Notiz zurück."""
    color = d.get("color") if d.get("color") in COLORS else None
    note = (d.get("note") or "").strip() or None
    if d.get("id"):
        nid = int(d["id"])
        old = con.execute("SELECT quote FROM note WHERE id=?", (nid,)).fetchone()
        if not old:
            raise ValueError("Diese Notiz gibt es nicht mehr.")
        con.execute("UPDATE note SET color=?, note=?, norm=?, updated=strftime('%s','now') WHERE id=?",
                    (color, note, normalize((old[0] or "") + " " + (note or "")), nid))
    else:
        quote = (d.get("quote") or "").strip() or None
        if not quote and not note:
            raise ValueError("Leere Notiz.")
        cur = con.execute(
            "INSERT INTO note (book, pid, field, start, end, quote, color, note, norm, created, updated) "
            "VALUES (?,?,?,?,?,?,?,?,?,strftime('%s','now'),strftime('%s','now'))",
            (int(d["book"]), int(d["pid"]), d.get("field") if d.get("field") in ("body", "foot") else None,
             d.get("start"), d.get("end"), quote, color or ("yellow" if quote else None), note,
             normalize((quote or "") + " " + (note or ""))))
        nid = cur.lastrowid
    con.commit()
    return dict(con.execute("SELECT " + NOTE_COLS + " FROM note WHERE id=?", (nid,)).fetchone())


def delete_note(con, nid):
    con.execute("DELETE FROM note WHERE id=?", (int(nid),))
    con.commit()


def notes(con, query=None, book=None, color=None, collection=None, limit=2000):
    """Alle Notizen, neueste zuerst; filterbar nach Text (normalisiert), Buch, Farbe, Sammlung."""
    sql = """SELECT n.id, n.book, n.pid, n.field, n.start, n.end, n.quote, n.color, n.note,
                    n.created, n.updated, b.name AS book_name, a.name AS author, a.death, p.part, p.num
             FROM note n JOIN book b ON b.id = n.book LEFT JOIN author a ON a.id = b.author_id
             LEFT JOIN page p ON p.book = n.book AND p.pid = n.pid WHERE 1"""
    args = []
    for t in normalize(query or "").split():
        if t.startswith("ال") and len(t) > 4:
            t = t[2:]  # „المرسل“ findet auch „للمرسل“ und „والمرسل“
        sql += " AND n.norm LIKE ?"
        args.append("%" + t + "%")
    if book:
        sql += " AND n.book = ?"
        args.append(int(book))
    if color in COLORS:
        sql += " AND n.color = ?"
        args.append(color)
    if collection:
        sql += " AND n.book IN (SELECT book FROM collection_book WHERE collection = ?)"
        args.append(int(collection))
    sql += " ORDER BY n.updated DESC, n.id DESC LIMIT ?"
    args.append(limit)
    out = []
    for r in con.execute(sql, args):
        d = dict(r)
        d["death"] = _death(r)
        d["where"] = _page_label(d["part"], d["num"])
        out.append(d)
    return out


# ---------- Sammlungen (eigene Bücherlisten) ----------

def collections(con, book=None):
    """Sammlungen mit Anzahl der Bücher; mit book zusätzlich, ob das Buch darin ist."""
    return [dict(r) | ({"has": bool(r["has"])} if book else {}) for r in con.execute("""
        SELECT c.id, c.name, COUNT(cb.book) AS books""" + (
        ", MAX(cb.book = ?) AS has" if book else "") + """
        FROM collection c LEFT JOIN collection_book cb ON cb.collection = c.id
        GROUP BY c.id ORDER BY c.name""", (int(book),) if book else ())]


def save_collection(con, name, cid=None):
    name = (name or "").strip()
    if not name:
        raise ValueError("Die Sammlung braucht einen Namen.")
    if cid:
        con.execute("UPDATE collection SET name=? WHERE id=?", (name, int(cid)))
    else:
        cid = con.execute("INSERT INTO collection (name, created) VALUES (?, strftime('%s','now'))",
                          (name,)).lastrowid
    con.commit()
    return int(cid)


def delete_collection(con, cid):
    con.execute("DELETE FROM collection_book WHERE collection=?", (int(cid),))
    con.execute("DELETE FROM collection WHERE id=?", (int(cid),))
    con.commit()


def set_in_collection(con, cid, book_id, on=True):
    if on:
        con.execute("INSERT OR IGNORE INTO collection_book VALUES (?, ?, strftime('%s','now'))",
                    (int(cid), int(book_id)))
    else:
        con.execute("DELETE FROM collection_book WHERE collection=? AND book=?", (int(cid), int(book_id)))
    con.commit()


def stats(con):
    r = con.execute("SELECT COUNT(*), COALESCE(SUM(pages),0) FROM book WHERE imported > 0").fetchone()
    return {"books": r[0], "pages": r[1]}


def get_state(con, key, default=None):
    r = con.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
    return json.loads(r[0]) if r else default


def set_state(con, key, value):
    con.execute("INSERT OR REPLACE INTO state VALUES (?, ?)", (key, json.dumps(value, ensure_ascii=False)))
    con.commit()
