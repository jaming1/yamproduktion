"""Übernahme von Büchern aus Shamela in die eigene Yamaktaba-Datenbank.

Shamela wird nur gelesen. Der Katalog kommt aus master.db, Seitennummern
und Kapitel aus book/NNN/<id>.db, die Texte über ShamelaExport (Java)
aus dem Lucene-Index. Bereits übernommene Bücher werden übersprungen.

Aufruf:
  python3 -m ashamila.importer --shamela <database-Ordner> --kategorien 10,6,7
"""
import argparse
import glob
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import zlib

from . import db as store
from .normalize import normalize

CODE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LIB_DIR = os.path.join(CODE_DIR, "lib")
FOOT_SEPARATOR = "_________"


def java_major(java):
    """Hauptversion einer Java-Laufzeit (8, 11, 21 …) oder 0, wenn sie nicht startet."""
    try:
        out = subprocess.run([java, "-version"], capture_output=True, timeout=20, check=True).stderr.decode("utf-8", "replace")
    except (OSError, subprocess.SubprocessError):
        return 0
    m = re.search(r'version "(\d+)(?:\.(\d+))?', out)
    if not m:
        return 0
    major = int(m.group(1))
    return int(m.group(2) or 0) if major == 1 else major   # „1.8“ ist Java 8


def find_java():
    """Java suchen: eigene Angabe, System-Java oder die Laufzeit, die Shamela mitbringt.
    Bevorzugt ab Java 21, denn nur damit läuft Lucene 10, das Shamelas neuere Indexteile lesen kann."""
    own = os.environ.get("ASHAMILA_JAVA")
    if own and os.access(own, os.X_OK):   # ausdrückliche Angabe gilt immer
        return own
    candidates = []
    if os.environ.get("JAVA_HOME"):
        candidates.append(os.path.join(os.environ["JAVA_HOME"], "bin", "java"))
    candidates += sorted(glob.glob(os.path.expanduser(
        "~/Library/Application Support/Shamela/app/mac/*/jre/*/Contents/Home/bin/java")), reverse=True)
    candidates += sorted(glob.glob(os.path.expanduser(
        "~/Library/Application Support/Shamela/app/mac/*/jre/*/bin/java")), reverse=True)
    candidates.append(shutil.which("java"))
    working = []
    for c in candidates:
        if c and os.path.isfile(c) and os.access(c, os.X_OK) and c not in working:
            major = java_major(c)
            if major >= 21:
                return c
            if major:
                working.append(c)
    if working:
        return working[0]
    raise SystemExit(
        "Java wurde nicht gefunden. Bitte die Shamela-App einmal starten "
        "oder Java installieren (z. B. 'brew install openjdk') und erneut versuchen.")


def classpath(java):
    """Lucene passend zur Java-Version: ab Java 21 Lucene 10 (liest auch Shamelas neue Indexteile
    im Format Lucene104 und alle älteren ab 9.0), sonst Lucene 9.12."""
    own = os.path.join(LIB_DIR, "shamela-export.jar")
    l10 = sorted(glob.glob(os.path.join(LIB_DIR, "lucene10", "*.jar")))
    if l10 and java_major(java) >= 21:
        jars = [own] + l10
    else:
        jars = sorted(glob.glob(os.path.join(LIB_DIR, "*.jar")))
    return os.pathsep.join(jars)


def book_db_path(shamela, book_id):
    return os.path.join(shamela, "book", "%03d" % (book_id % 1000), "%d.db" % book_id)


def split_page(rec):
    """Haupttext und Fußnoten trennen. Shamela speichert Seiten mit Fußnoten
    teils komplett im Feld 'foot', getrennt durch eine Unterstrich-Linie."""
    body, foot = rec.get("body"), rec.get("foot")
    if body is None and foot is not None:
        if FOOT_SEPARATOR in foot:
            body, foot = foot.split(FOOT_SEPARATOR, 1)
        else:
            body, foot = foot, None
    body = (body or "").replace("\r", "\n").strip()
    foot = (foot or "").replace("\r", "\n").strip() or None
    return body, foot


def pack(text):
    return zlib.compress(text.encode("utf-8"), 6) if text else None


def import_catalog(con, master):
    m = sqlite3.connect("file:%s?mode=ro" % master, uri=True)
    con.executemany("""INSERT INTO category (id, name, ord) VALUES (?,?,?)
                       ON CONFLICT(id) DO UPDATE SET name=excluded.name, ord=excluded.ord""",
                    m.execute("SELECT category_id, category_name, category_order FROM category"))
    con.executemany("""INSERT INTO author (id, name, death, death_text) VALUES (?,?,?,?)
                       ON CONFLICT(id) DO UPDATE SET name=excluded.name, death=excluded.death,
                         death_text=excluded.death_text""",
                    m.execute("SELECT author_id, author_name, death_number, death_text FROM author"))
    rows = m.execute("""SELECT book_id, book_name, book_category, main_author, authors,
                               book_date, meta_data FROM book WHERE hidden = 0""").fetchall()
    # Ein Buch, das du in eine andere Kategorie verschoben hast (moved), bleibt dort
    con.executemany("""INSERT INTO book (id, name, norm_name, category, author_id, authors, date, meta, orig_category)
                       VALUES (?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(id) DO UPDATE SET name=excluded.name, norm_name=excluded.norm_name,
                         category=CASE WHEN book.moved THEN book.category ELSE excluded.category END,
                         orig_category=excluded.category, author_id=excluded.author_id,
                         authors=excluded.authors, date=excluded.date, meta=excluded.meta""",
                    [(r[0], r[1], normalize(r[1]), r[2], r[3], r[4], r[5], r[6], r[2]) for r in rows])
    con.commit()
    m.close()


def save_book(con, shamela, book_id, pages, titles):
    """Ein Buch in einer Transaktion speichern (alles oder nichts)."""
    bdb = sqlite3.connect("file:%s?mode=ro" % book_db_path(shamela, book_id), uri=True)
    meta = {r[0]: r[1:] for r in bdb.execute("SELECT id, part, page, number FROM page")}
    toc = bdb.execute("SELECT id, page, parent FROM title").fetchall()
    bdb.close()

    cur = con.cursor()
    parts = set()
    for pid in sorted(set(meta) | set(pages)):
        part, num, hadith = meta.get(pid, (None, None, None))
        body, foot = split_page(pages.get(pid, {}))
        if part:
            parts.add(part)
        cur.execute("INSERT INTO page (book, pid, part, num, hadith, body, foot) VALUES (?,?,?,?,?,?,?)",
                    (book_id, pid, part, num, hadith, pack(body), pack(foot)))
        text = normalize(body + " " + (foot or ""))
        if text:
            cur.execute("INSERT INTO page_fts (rowid, text) VALUES (?, ?)", (cur.lastrowid, text))
    for tid, pid, parent in toc:
        title = (titles.get(tid) or "").replace("\r", " ").strip()
        cur.execute("INSERT OR REPLACE INTO toc (book, tid, pid, parent, title) VALUES (?,?,?,?,?)",
                    (book_id, tid, pid, parent, title))
    cur.execute("UPDATE book SET pages=?, parts=?, imported=? WHERE id=?",
                (len(meta) or len(pages), len(parts), int(time.time()), book_id))
    con.commit()


def pending(con, shamela, categories):
    """Bücher dieser Kategorien, die in Shamela heruntergeladen, aber noch nicht übernommen sind."""
    if not categories:
        return []
    q = "SELECT id FROM book WHERE imported IS NULL AND COALESCE(orig_category, category) IN (%s) ORDER BY id" % \
        ",".join("?" * len(categories))
    return [r[0] for r in con.execute(q, list(categories)) if os.path.exists(book_db_path(shamela, r[0]))]


def run(shamela, target, categories, log=print, progress=lambda done, total: None, stop=lambda: False):
    master = os.path.join(shamela, "master.db")
    if not os.path.exists(master):
        raise SystemExit("master.db nicht gefunden in: %s" % shamela)
    con = store.connect(target, create=True)
    import_catalog(con, master)

    todo = pending(con, shamela, categories)
    from . import extras
    try:
        extras.load_from_shamela(con, shamela, log=log)   # Korantext und Biografien, einmalig
    except Exception as e:  # Zusatzdaten sind nicht kritisch für die Übernahme
        log("Hinweis: Korantext/Biografien nicht übernommen (%s)" % e)
    if not todo:
        log("Nichts zu tun: alle heruntergeladenen Bücher dieser Kategorien sind schon übernommen.")
        return 0

    java = find_java()
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write("\n".join(map(str, todo)))
        ids_file = f.name
    cp = classpath(java)
    err = tempfile.TemporaryFile()   # Java-Meldungen aufheben, damit ein Abbruch erklärt werden kann
    proc = subprocess.Popen([java, "-cp", cp, "ShamelaExport", shamela, ids_file],
                            stdout=subprocess.PIPE, stderr=err)
    done, failed, started, stopped = 0, [], time.time(), False
    progress(0, len(todo))
    pages, titles = {}, {}
    try:
        for raw in proc.stdout:
            try:
                rec = json.loads(raw)
            except ValueError:
                continue
            t = rec["t"]
            if t == "p":
                pages[rec["i"]] = rec
            elif t == "t":
                titles[rec["i"]] = rec.get("body")
            elif t == "end":
                book_id = rec["b"]
                try:
                    save_book(con, shamela, book_id, pages, titles)
                    done += 1
                except Exception as e:  # ein defektes Buch stoppt die Übernahme nicht
                    con.rollback()
                    failed.append((book_id, str(e)))
                pages, titles = {}, {}
                progress(done, len(todo))
                if stop():
                    log("Angehalten nach %d von %d Büchern; ein neuer Start setzt fort." % (done, len(todo)))
                    stopped = True
                    proc.kill()
                    break
                if done % 10 == 0 or done == len(todo):
                    rate = done / max(time.time() - started, 1)
                    rest = (len(todo) - done) / rate if rate else 0
                    log("%d/%d Bücher übernommen · noch ca. %d min" % (done, len(todo), rest / 60))
    finally:
        proc.wait()
        os.unlink(ids_file)
    if not stopped and done + len(failed) < len(todo):
        err.seek(0)
        lines = [x.strip() for x in err.read().decode("utf-8", "replace").splitlines()
                 if x.strip() and not x.startswith(("Picked up", "WARNING", "INFO"))]
        main = [x for x in lines if "Exception" in x or x.startswith("Caused by")]
        why = " | ".join((main or lines)[:2])[:400] or "keine Meldung"
        log("Java beendet mit Code %s: %s" % (proc.returncode, why))
        if done == 0:
            raise SystemExit("Shamela-Texte konnten nicht gelesen werden (Java: %s). "
                             "Bitte Shamela schließen und erneut versuchen." % why)
    err.close()
    con.execute("INSERT INTO page_fts(page_fts) VALUES('optimize')")
    con.commit()
    from .roots import build_root_table
    build_root_table(con, log)
    if failed:
        with open(os.path.join(os.path.dirname(target), "import-fehler.csv"), "w", encoding="utf-8") as f:
            f.write("buch_id,fehler\n")
            for b, e in failed:
                f.write('%d,"%s"\n' % (b, e.replace('"', "'")))
        log("%d Bücher konnten nicht übernommen werden, siehe import-fehler.csv" % len(failed))
    log("Fertig: %d Bücher übernommen." % done)
    return done


def main(argv=None):
    ap = argparse.ArgumentParser(description="Bücher aus Shamela in Yamaktaba übernehmen")
    ap.add_argument("--shamela", default=os.path.expanduser("~/Library/Application Support/Shamela/database"),
                    help="Shamela-Ordner 'database'")
    ap.add_argument("--ziel", default=store.default_path(), help="Yamaktaba-Datenbank")
    ap.add_argument("--kategorien", required=True, help="Kategorie-Nummern, z. B. 10,6,7")
    ap.add_argument("--nur", help="nur diese Buch-Nummern (zum Testen), z. B. 84,135")
    a = ap.parse_args(argv)
    cats = [int(x) for x in a.kategorien.split(",") if x.strip()]
    if a.nur:
        con = store.connect(a.ziel, create=True)
        import_catalog(con, os.path.join(a.shamela, "master.db"))
        keep = {int(x) for x in a.nur.split(",")}
        con.execute("UPDATE book SET imported = -1 WHERE imported IS NULL AND id NOT IN (%s)" %
                    ",".join(map(str, keep)))
        con.commit()
        run(a.shamela, a.ziel, cats)
        con.execute("UPDATE book SET imported = NULL WHERE imported = -1")
        con.commit()
    else:
        run(a.shamela, a.ziel, cats)


if __name__ == "__main__":
    sys.exit(main())
