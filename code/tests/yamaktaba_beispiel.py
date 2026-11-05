"""Kleine Yamaktaba-Bibliothek für Tests: gleicher Aufbau wie ashamila/ (code/src, daten, bibliothek)."""
import shutil
import sys
from pathlib import Path

from buchbeispiel import beispielbuch

SCHNITTSTELLE = Path(__file__).with_name("daten") / "yamaktaba_schnittstelle" / "ashamila"


def yamaktaba_bauen(ordner: Path) -> Path:
    src = ordner / "code" / "src"
    shutil.copytree(SCHNITTSTELLE, src / "ashamila")
    (ordner / "daten").mkdir(parents=True)
    (ordner / "bibliothek").mkdir()
    sys.path.insert(0, str(src))
    import importlib
    for m in [m for m in sys.modules if m == "ashamila" or m.startswith("ashamila.")]:
        del sys.modules[m]
    import os
    os.environ["ASHAMILA_DATA"] = str(ordner / "daten")
    db = importlib.import_module("ashamila.db")
    ownbooks = importlib.import_module("ashamila.ownbooks")
    con = db.connect(str(ordner / "daten" / "bibliothek.db"), create=True)
    con.execute("INSERT INTO category (id, name, ord, own) VALUES (1010, 'Khizana', 1010, 1)")
    con.execute("INSERT INTO category (id, name, ord, own, parent) VALUES (1033, '99 Projekte & Medien', 1033, 1, 1010)")
    pdf = beispielbuch(ordner / "bibliothek" / "Uebungsbuch.pdf")
    ownbooks.import_file(con, pdf.read_bytes(), pdf.name, title="Übungsbuch Maschinenelemente", author="Muster",
                         category=1033, quelle="khizana", datei="Uebungsbuch.pdf")
    con.commit()
    con.close()
    sys.path.remove(str(src))
    return ordner
