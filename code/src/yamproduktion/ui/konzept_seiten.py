"""MS3-Seiten: Ideen & TRIZ (M8, M9, S2, S3), Funktionsstruktur (M12), Konzept (M14, M15)."""
from __future__ import annotations

import json

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDoubleSpinBox, QFormLayout, QFrame, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QPlainTextEdit, QPushButton, QSplitter, QTableWidget, QTableWidgetItem, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

from .. import triz
from ..berechnungen.basis import formatiere
from ..modell import NEU_PRUEFEN, Projekt, ProjektFehler
from .rueckverfolgung import RueckverfolgungPanel, status_text
from .seiten import karte, leeren, scrollbar, titel


def _abschnitt(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("Abschnitt")
    return lbl


def _klein(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("Klein")
    lbl.setWordWrap(True)
    return lbl


def _combo(min_zeichen: int = 16) -> QComboBox:
    """Auswahlliste, die nicht mit dem längsten Eintrag mitwächst (sonst wird die Seite zu breit)."""
    c = QComboBox()
    c.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
    c.setMinimumContentsLength(min_zeichen)
    return c


def _mit_panel(links: QWidget, panel: RueckverfolgungPanel) -> QSplitter:
    teiler = QSplitter(Qt.Horizontal)
    teiler.addWidget(links)
    teiler.addWidget(panel)
    teiler.setStretchFactor(0, 1)
    teiler.setChildrenCollapsible(False)
    teiler.setSizes([1000, 340])
    return teiler


class _MehrzeiligesFeld(QPlainTextEdit):
    """Mehrzeiliges Textfeld, das beim Verlassen speichert."""
    fertig = Signal()

    def __init__(self, platzhalter: str = ""):
        super().__init__()
        self.setPlaceholderText(platzhalter)
        self.setTabChangesFocus(True)
        self.setFixedHeight(58)

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        self.fertig.emit()


# ================================================================ Ideen & TRIZ
class IdeenSeite(QWidget):
    meldung = Signal(str, bool)
    geaendert = Signal()
    gehe_zu_objekt = Signal(str, int)

    FELDER = (("titel", "Titel", "Kurzer Name der Idee", False),
              ("problem", "Problem", "Welches Problem soll gelöst werden?", True),
              ("nutzen", "Nutzen", "Wem hilft es, was wird besser?", True),
              ("ier", "Ideales Endergebnis", "TRIZ: Das System erfüllt die Funktion von selbst, ohne Kosten und "
                                             "Nachteile …", True),
              ("ressourcen", "Ressourcen", "Was ist schon vorhanden (Stoff, Energie, Raum, Zeit, Information)?", True))

    def __init__(self):
        super().__init__()
        self.projekt: Projekt | None = None
        self.idee_id: int | None = None
        self._w_id: int | None = None     # gespeicherter Widerspruch zur aktuellen Eingabe
        self._laedt = False

        inhalt = QWidget()
        lay = QVBoxLayout(inhalt)
        lay.setContentsMargins(32, 24, 24, 24)
        lay.addWidget(titel("Ideen & TRIZ",
                            "Idee festhalten, Widerspruch benennen, passende Erfinderprinzipien nachschlagen und "
                            "Lösungsideen notieren. Alles wird sofort gespeichert."))

        # --- Idee
        reihe = QHBoxLayout()
        reihe.addWidget(QLabel("Idee:"))
        self.ideen_wahl = _combo()
        self.ideen_wahl.currentIndexChanged.connect(self._idee_gewaehlt)
        reihe.addWidget(self.ideen_wahl, 1)
        self.neu = QPushButton("+  Neue Idee")
        self.neu.setObjectName("Haupt")
        self.neu.clicked.connect(self.neue_idee)
        reihe.addWidget(self.neu)
        self.idee_loeschen = QPushButton("Löschen")
        self.idee_loeschen.clicked.connect(self._idee_loeschen)
        reihe.addWidget(self.idee_loeschen)
        lay.addLayout(reihe)

        box, bl = karte()
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        self.felder: dict[str, QLineEdit | _MehrzeiligesFeld] = {}
        for feld, name, platz, mehr in self.FELDER:
            w = _MehrzeiligesFeld(platz) if mehr else QLineEdit()
            if mehr:
                w.fertig.connect(lambda f=feld: self._feld_speichern(f))
            else:
                w.setPlaceholderText(platz)
                w.editingFinished.connect(lambda f=feld: self._feld_speichern(f))
            self.felder[feld] = w
            form.addRow(name, w)
        bl.addLayout(form)
        self.idee_karte = box
        lay.addWidget(box)

        # --- Widerspruch
        lay.addWidget(_abschnitt("Widerspruch lösen"))
        box, bl = karte()
        art = QHBoxLayout()
        art.addWidget(QLabel("Art:"))
        self.art = _combo()
        self.art.addItems(["Technischer Widerspruch (Widerspruchsmatrix)", "Physikalischer Widerspruch (Separation)"])
        self.art.currentIndexChanged.connect(self._eingabe_geaendert)
        art.addWidget(self.art, 1)
        bl.addLayout(art)
        self.w_text = QLineEdit()
        self.w_text.setPlaceholderText("Beschreibung, z. B. „Größerer Rotor bringt Leistung, belastet aber den Turm stärker“")
        self.w_text.textEdited.connect(lambda _: setattr(self, "_w_id", None))
        bl.addWidget(self.w_text)

        self.matrix_box = QWidget()
        ml = QFormLayout(self.matrix_box)
        ml.setContentsMargins(0, 0, 0, 0)
        self.verbessern = _combo()
        self.verschlechtern = _combo()
        for c in (self.verbessern, self.verschlechtern):
            for par in triz.parameter():
                c.addItem(f"{par['nr']:>2} · {par['name']}", par["nr"])
            c.setMaxVisibleItems(20)
            c.currentIndexChanged.connect(self._eingabe_geaendert)
        ml.addRow("Das will ich verbessern:", self.verbessern)
        ml.addRow("Das verschlechtert sich dabei:", self.verschlechtern)
        bl.addWidget(self.matrix_box)

        idee_reihe = QHBoxLayout()
        self.l_text = QLineEdit()
        self.l_text.setPlaceholderText("Deine Lösungsidee zu einem Prinzip (dann bei dem Prinzip auf „Notieren“)")
        idee_reihe.addWidget(self.l_text, 1)
        self.w_speichern = QPushButton("Widerspruch speichern")
        self.w_speichern.clicked.connect(self.widerspruch_speichern)
        idee_reihe.addWidget(self.w_speichern)
        bl.addLayout(idee_reihe)

        self.empf_kopf = QLabel()
        self.empf_kopf.setObjectName("Unterabschnitt")
        self.empf_kopf.setWordWrap(True)
        bl.addWidget(self.empf_kopf)
        self.empf_lay = QVBoxLayout()
        self.empf_lay.setSpacing(6)
        bl.addLayout(self.empf_lay)
        quelle = _klein(f"Quelle: {triz.quelle()}  ·  {triz.hinweis()}")
        quelle.setTextInteractionFlags(Qt.TextSelectableByMouse)
        bl.addWidget(quelle)
        lay.addWidget(box)

        # --- Gespeichert
        lay.addWidget(_abschnitt("Widersprüche und Lösungsideen dieser Idee"))
        self.baum = QTreeWidget()
        self.baum.setHeaderLabels(["Nr", "Inhalt", "Status"])
        self.baum.setColumnWidth(0, 90)
        self.baum.setColumnWidth(1, 430)
        self.baum.setMinimumHeight(170)
        self.baum.currentItemChanged.connect(lambda *_: self._details_zeigen())
        lay.addWidget(self.baum)
        reihe = QHBoxLayout()
        self.eintrag_loeschen = QPushButton("Ausgewählten Eintrag löschen")
        self.eintrag_loeschen.clicked.connect(self._eintrag_loeschen)
        reihe.addWidget(self.eintrag_loeschen)
        reihe.addStretch()
        lay.addLayout(reihe)
        lay.addStretch()

        self.panel = RueckverfolgungPanel()
        self.panel.gehe_zu.connect(self.gehe_zu_objekt)
        aussen = QVBoxLayout(self)
        aussen.setContentsMargins(0, 0, 0, 0)
        aussen.addWidget(_mit_panel(scrollbar(inhalt), self.panel))
        self._eingabe_geaendert()

    # ---------- Laden ----------
    def setze_projekt(self, projekt: Projekt):
        self.projekt = projekt
        self.idee_id = None
        self.laden()

    def laden(self, auswahl: int | None = None):
        if not self.projekt:
            return
        self._laedt = True
        ideen = self.projekt.liste("idee")
        ziel = auswahl or self.idee_id or (ideen[0]["id"] if ideen else None)
        self.ideen_wahl.clear()
        for i in ideen:
            self.ideen_wahl.addItem(f"{i['nr']}  {i['titel'] or '(ohne Titel)'}", i["id"])
        if not ideen:
            self.ideen_wahl.addItem("– noch keine Idee: „+ Neue Idee“ –", None)
        index = max(0, self.ideen_wahl.findData(ziel))
        self.ideen_wahl.setCurrentIndex(index)
        self._laedt = False
        self._idee_gewaehlt()

    def _idee_gewaehlt(self, *_):
        if self._laedt or not self.projekt:
            return
        self.idee_id = self.ideen_wahl.currentData()
        self.idee_karte.setEnabled(self.idee_id is not None)
        self.idee_loeschen.setEnabled(self.idee_id is not None)
        i = self.projekt.objekt("idee", self.idee_id) if self.idee_id else {}
        for feld, w in self.felder.items():
            wert = i.get(feld, "")
            if isinstance(w, QLineEdit):
                w.setText(wert)
            else:
                w.setPlainText(wert)
        self._baum_laden()
        if self.idee_id:
            self._zeige("idee", self.idee_id)
        else:
            self.panel.leer()

    def _baum_laden(self):
        self.baum.clear()
        if not self.idee_id:
            return
        for w in self.projekt.liste("widerspruch", "idee_id=?", (self.idee_id,)):
            if w["art"] == "technisch" and w["verbessern"]:
                zusatz = f"  [{w['verbessern']} ↑ / {w['verschlechtern']} ↓]"
            else:
                zusatz = "  [physikalisch]"
            knoten = QTreeWidgetItem([w["nr"], w["beschreibung"] + zusatz, status_text(w["status"])])
            knoten.setData(0, Qt.UserRole, ("widerspruch", w["id"]))
            self.baum.addTopLevelItem(knoten)
            for l in self.projekt.liste("loesungsidee", "widerspruch_id=?", (w["id"],)):
                prinzip = f"Prinzip {l['prinzip']} {triz.prinzip(l['prinzip'])['name']}: " if l["prinzip"] else ""
                k = QTreeWidgetItem([l["nr"], prinzip + l["text"], status_text(l["status"])])
                k.setData(0, Qt.UserRole, ("loesungsidee", l["id"]))
                knoten.addChild(k)
            knoten.setExpanded(True)

    def _zeige(self, typ: str, id_: int):
        o = self.projekt.objekt(typ, id_)
        from ..modell import OBJEKTE
        self.panel.zeigen(self.projekt, typ, id_, o["nr"], o[OBJEKTE[typ][1]], o["status"], o["version"])

    def _details_zeigen(self):
        item = self.baum.currentItem()
        if item:
            self._zeige(*item.data(0, Qt.UserRole))

    def auswaehlen(self, typ: str, id_: int):
        if typ == "idee":
            self.laden(id_)
            return
        o = self.projekt.objekt(typ, id_)
        w = o if typ == "widerspruch" else self.projekt.objekt("widerspruch", o["widerspruch_id"]) \
            if o["widerspruch_id"] else None
        if w and w["idee_id"]:
            self.laden(w["idee_id"])
        for i in range(self.baum.topLevelItemCount()):
            oben = self.baum.topLevelItem(i)
            for item in [oben] + [oben.child(j) for j in range(oben.childCount())]:
                if item.data(0, Qt.UserRole) == (typ, id_):
                    self.baum.setCurrentItem(item)
                    return
        self._zeige(typ, id_)

    # ---------- Idee bearbeiten ----------
    def neue_idee(self):
        i = self.projekt.objekt_neu("idee", titel="Neue Idee")
        self.laden(i["id"])
        self.felder["titel"].setFocus()
        self.felder["titel"].selectAll()
        self.meldung.emit(f"{i['nr']} angelegt.", False)
        self.geaendert.emit()

    def _idee_loeschen(self):
        if not self.idee_id:
            return
        nr = self.projekt.objekt("idee", self.idee_id)["nr"]
        for w in self.projekt.liste("widerspruch", "idee_id=?", (self.idee_id,)):
            self.projekt.objekt_loeschen("widerspruch", w["id"])
        self.projekt.objekt_loeschen("idee", self.idee_id)
        self.idee_id = None
        self.laden()
        self.meldung.emit(f"{nr} mit ihren Widersprüchen gelöscht.", False)
        self.geaendert.emit()

    def _feld_speichern(self, feld: str):
        if self._laedt or not self.idee_id:
            return
        w = self.felder[feld]
        wert = (w.text() if isinstance(w, QLineEdit) else w.toPlainText()).strip()
        alt = self.projekt.objekt("idee", self.idee_id)
        if alt[feld] == wert:
            return
        self.projekt.objekt_aendern("idee", self.idee_id, **{feld: wert})
        if feld == "titel":
            self.ideen_wahl.setItemText(self.ideen_wahl.currentIndex(), f"{alt['nr']}  {wert or '(ohne Titel)'}")
        self._zeige("idee", self.idee_id)
        self.meldung.emit(f"{alt['nr']} gespeichert.", False)
        self.geaendert.emit()

    # ---------- TRIZ ----------
    def _physikalisch(self) -> bool:
        return self.art.currentIndex() == 1

    def setze_parameter(self, verbessern: int, verschlechtern: int):
        self.art.setCurrentIndex(0)
        self.verbessern.setCurrentIndex(verbessern - 1)
        self.verschlechtern.setCurrentIndex(verschlechtern - 1)

    def _eingabe_geaendert(self, *_):
        self._w_id = None
        self.matrix_box.setVisible(not self._physikalisch())
        leeren(self.empf_lay)
        if self._physikalisch():
            self.empf_kopf.setText("Trennungsprinzipien: Die widersprüchlichen Forderungen voneinander trennen")
            for t in triz.trennungsprinzipien():
                nummern = ", ".join(str(n) for n in t["prinzipien"])
                self._prinzip_zeile(f"<b>{t['name']}</b> – {t['frage']}<br>"
                                    f"<span style='opacity:0.75'>Passende Prinzipien: {nummern}</span>", None)
            return
        v, s = self.verbessern.currentData(), self.verschlechtern.currentData()
        if v == s:
            self.empf_kopf.setText("Gleicher Parameter auf beiden Seiten: Das ist ein physikalischer Widerspruch. "
                                   "Bitte oben „Physikalischer Widerspruch“ wählen.")
            return
        liste = triz.empfehlung(v, s)
        if not liste:
            self.empf_kopf.setText(f"Für {v} ↑ / {s} ↓ ist die Matrix leer. Tipp: Widerspruch anders formulieren "
                                   "oder als physikalischen Widerspruch betrachten.")
            return
        self.empf_kopf.setText(f"Empfohlene Prinzipien für „{triz.parameter_name(v)}“ ↑ gegen "
                               f"„{triz.parameter_name(s)}“ ↓ (in der Reihenfolge der Matrix)")
        for nr in liste:
            p = triz.prinzip(nr)
            self._prinzip_zeile(f"<b>{nr} · {p['name']}</b><br><span style='opacity:0.8'>{p['beschreibung']}</span>", nr)

    def _prinzip_zeile(self, html: str, nr: int | None):
        zeile = QFrame()
        zeile.setObjectName("Unterkarte")
        zl = QHBoxLayout(zeile)
        zl.setContentsMargins(10, 6, 6, 6)
        text = QLabel(html)
        text.setWordWrap(True)
        zl.addWidget(text, 1)
        knopf = QPushButton("Notieren")
        knopf.setToolTip("Die Lösungsidee aus dem Feld oben zu diesem Prinzip speichern")
        knopf.clicked.connect(lambda _=False, n=nr: self.loesungsidee_notieren(n))
        zl.addWidget(knopf, 0, Qt.AlignTop)
        self.empf_lay.addWidget(zeile)

    def widerspruch_speichern(self) -> int | None:
        if not self.idee_id:
            self.meldung.emit("Bitte zuerst eine Idee anlegen.", True)
            return None
        if self._w_id:
            return self._w_id
        text = self.w_text.text().strip()
        if not text:
            self.meldung.emit("Bitte den Widerspruch kurz beschreiben.", True)
            self.w_text.setFocus()
            return None
        if self._physikalisch():
            w = self.projekt.physikalischer_widerspruch_neu(text, self.idee_id)
        else:
            v, s = self.verbessern.currentData(), self.verschlechtern.currentData()
            if v == s:
                self.meldung.emit("Gleicher Parameter: bitte als physikalischen Widerspruch erfassen.", True)
                return None
            w = self.projekt.widerspruch_neu(text, v, s, self.idee_id)
        self._w_id = w["id"]
        self._baum_laden()
        self.meldung.emit(f"{w['nr']} gespeichert.", False)
        self.geaendert.emit()
        return w["id"]

    def loesungsidee_notieren(self, prinzip: int | None):
        text = self.l_text.text().strip()
        if not text:
            self.meldung.emit("Bitte zuerst die Lösungsidee ins Feld „Deine Lösungsidee“ schreiben.", True)
            self.l_text.setFocus()
            return
        w_id = self.widerspruch_speichern()
        if not w_id:
            return
        l = self.projekt.loesungsidee_neu(w_id, prinzip, text)
        self.l_text.clear()
        self._baum_laden()
        self.auswaehlen("loesungsidee", l["id"])
        self.meldung.emit(f"{l['nr']} notiert. Im Konzept kann sie als Lösungsweg übernommen werden.", False)
        self.geaendert.emit()

    def _eintrag_loeschen(self):
        item = self.baum.currentItem()
        if not item:
            return
        typ, id_ = item.data(0, Qt.UserRole)
        nr = self.projekt.objekt(typ, id_)["nr"]
        self.projekt.objekt_loeschen(typ, id_)
        if typ == "widerspruch" and self._w_id == id_:
            self._w_id = None
        self._baum_laden()
        self._zeige("idee", self.idee_id)
        self.meldung.emit(f"{nr} gelöscht.", False)
        self.geaendert.emit()


# ================================================================ Funktionsstruktur
class FunktionenSeite(QWidget):
    meldung = Signal(str, bool)
    geaendert = Signal()
    gehe_zu_objekt = Signal(str, int)

    def __init__(self):
        super().__init__()
        self.projekt: Projekt | None = None
        self._laedt = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 24, 32, 24)
        lay.addWidget(titel("Funktionsstruktur",
                            "Was soll das Produkt tun? Oben die Gesamtfunktion, darunter die Teilfunktionen "
                            "(Verb + Substantiv, z. B. „Drehzahl anpassen“). Die untersten Funktionen werden die "
                            "Zeilen des morphologischen Kastens. Doppelklick zum Umbenennen."))
        reihe = QHBoxLayout()
        self.neu_gesamt = QPushButton("+  Gesamtfunktion")
        self.neu_gesamt.setObjectName("Haupt")
        self.neu_gesamt.clicked.connect(lambda: self.funktion_anlegen(unter=False))
        self.neu_unter = QPushButton("+  Unterfunktion")
        self.neu_unter.clicked.connect(lambda: self.funktion_anlegen(unter=True))
        self.loeschen = QPushButton("Löschen")
        self.loeschen.clicked.connect(self.auswahl_loeschen)
        for k in (self.neu_gesamt, self.neu_unter, self.loeschen):
            reihe.addWidget(k)
        reihe.addStretch()
        lay.addLayout(reihe)

        links = QWidget()
        ll = QVBoxLayout(links)
        ll.setContentsMargins(0, 0, 0, 0)
        self.baum = QTreeWidget()
        self.baum.setHeaderLabels(["Funktion", "Nr", "erfüllt", "Status"])
        self.baum.setColumnWidth(0, 380)
        self.baum.setColumnWidth(1, 70)
        self.baum.setColumnWidth(2, 150)
        self.baum.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.baum.itemChanged.connect(self._umbenannt)
        self.baum.currentItemChanged.connect(lambda *_: self._details_zeigen())
        ll.addWidget(self.baum, 1)

        verkn = QHBoxLayout()
        verkn.addWidget(QLabel("Anforderung zuordnen:"))
        self.anf_wahl = _combo()
        verkn.addWidget(self.anf_wahl, 1)
        self.verknuepfen = QPushButton("Verknüpfen")
        self.verknuepfen.setToolTip("Die ausgewählte Funktion erfüllt diese Anforderung. Ändert sich die "
                                    "Anforderung, wird die Funktion „neu prüfen“.")
        self.verknuepfen.clicked.connect(self.anforderung_verknuepfen)
        verkn.addWidget(self.verknuepfen)
        ll.addLayout(verkn)

        self.panel = RueckverfolgungPanel()
        self.panel.gehe_zu.connect(self.gehe_zu_objekt)
        lay.addWidget(_mit_panel(links, self.panel), 1)

    def setze_projekt(self, projekt: Projekt):
        self.projekt = projekt
        self.laden()

    def laden(self, auswahl: int | None = None):
        if not self.projekt:
            return
        self._laedt = True
        if auswahl is None and self.baum.currentItem():
            auswahl = self.baum.currentItem().data(0, Qt.UserRole)
        self.baum.clear()
        knoten: dict[int, QTreeWidgetItem] = {}
        ziel = None
        for _, f in self.projekt.funktionsbaum():
            erfuellt = ", ".join(b.nr for b in self.projekt.haengt_ab_von("funktion", f["id"])
                                 if b.typ == "anforderung")
            item = QTreeWidgetItem([f["name"], f["nr"], erfuellt, status_text(f["status"])])
            item.setData(0, Qt.UserRole, f["id"])
            item.setFlags(item.flags() | Qt.ItemIsEditable)
            if f["status"] == NEU_PRUEFEN:
                item.setForeground(3, self.palette().brush(self.palette().ColorRole.Link))
            eltern = knoten.get(f["eltern_id"])
            (eltern.addChild(item) if eltern else self.baum.addTopLevelItem(item))
            knoten[f["id"]] = item
            if f["id"] == auswahl:
                ziel = item
        self.baum.expandAll()
        self.anf_wahl.clear()
        for a in self.projekt.anforderungen():
            self.anf_wahl.addItem(f"{a.nr}  {a.text}", a.id)
        self._laedt = False
        if ziel:
            self.baum.setCurrentItem(ziel)
        elif self.baum.topLevelItemCount():
            self.baum.setCurrentItem(self.baum.topLevelItem(0))
        else:
            self.panel.leer()
        self._knoepfe()

    def _knoepfe(self):
        hat = self.baum.currentItem() is not None
        self.neu_unter.setEnabled(hat)
        self.loeschen.setEnabled(hat)
        self.verknuepfen.setEnabled(hat and self.anf_wahl.count() > 0)

    def _aktuelle_id(self) -> int | None:
        item = self.baum.currentItem()
        return item.data(0, Qt.UserRole) if item else None

    def auswaehlen(self, id_: int):
        self.laden(id_)

    def _details_zeigen(self):
        self._knoepfe()
        fid = self._aktuelle_id()
        if self._laedt or not fid:
            return
        f = self.projekt.objekt("funktion", fid)
        self.panel.zeigen(self.projekt, "funktion", fid, f["nr"], f["name"], f["status"], f["version"])

    def funktion_anlegen(self, unter: bool, name: str = ""):
        eltern = self._aktuelle_id() if unter else None
        f = self.projekt.funktion_neu(name or ("Neue Teilfunktion" if unter else "Gesamtfunktion"), eltern)
        self.laden(f["id"])
        if not name and self.baum.currentItem():
            self.baum.editItem(self.baum.currentItem(), 0)
        self.meldung.emit(f"{f['nr']} angelegt.", False)
        self.geaendert.emit()
        return f

    def _umbenannt(self, item: QTreeWidgetItem, spalte: int):
        if self._laedt or spalte != 0:
            return
        name = item.text(0).strip()
        fid = item.data(0, Qt.UserRole)
        alt = self.projekt.objekt("funktion", fid)
        if not name:
            self._laedt = True
            item.setText(0, alt["name"])
            self._laedt = False
            return
        if name != alt["name"]:
            self.projekt.objekt_aendern("funktion", fid, name=name)
            self.meldung.emit(f"{alt['nr']} umbenannt.", False)
            self.laden(fid)
            self.geaendert.emit()

    def auswahl_loeschen(self):
        fid = self._aktuelle_id()
        if not fid:
            return
        f = self.projekt.objekt("funktion", fid)
        self.projekt.objekt_loeschen("funktion", fid)
        self.laden(f["eltern_id"])
        self.meldung.emit(f"{f['nr']} mit Unterfunktionen gelöscht.", False)
        self.geaendert.emit()

    def anforderung_verknuepfen(self):
        fid, aid = self._aktuelle_id(), self.anf_wahl.currentData()
        if not fid or not aid:
            return
        try:
            self.projekt.anforderung_zu_funktion(aid, fid)
        except ProjektFehler as exc:
            self.meldung.emit(str(exc), True)
            return
        self.laden(fid)
        self.meldung.emit(f"{self.projekt.anforderung(aid).nr} → {self.projekt.objekt('funktion', fid)['nr']} verknüpft.",
                          False)
        self.geaendert.emit()


# ================================================================ Konzept
class KonzeptSeite(QWidget):
    meldung = Signal(str, bool)
    geaendert = Signal()
    gehe_zu_objekt = Signal(str, int)

    def __init__(self):
        super().__init__()
        self.projekt: Projekt | None = None
        self._laedt = False
        inhalt = QWidget()
        lay = QVBoxLayout(inhalt)
        lay.setContentsMargins(32, 24, 24, 24)
        lay.addWidget(titel("Konzept",
                            "Morphologischer Kasten: je Teilfunktion mögliche Lösungswege sammeln und zu Varianten "
                            "kombinieren. Danach die Varianten mit der Nutzwertanalyse vergleichen und eine begründet "
                            "auswählen."))

        # --- Morphologischer Kasten
        lay.addWidget(_abschnitt("Morphologischer Kasten"))
        box, bl = karte()
        r1 = QHBoxLayout()
        self.f_wahl = _combo()
        self.loesung_text = QLineEdit()
        self.loesung_text.setPlaceholderText("Lösungsweg, z. B. „Stirnradgetriebe“")
        self.loesung_text.returnPressed.connect(self.loesung_hinzufuegen)
        knopf = QPushButton("+  Lösungsweg")
        knopf.clicked.connect(self.loesung_hinzufuegen)
        r1.addWidget(QLabel("Teilfunktion:"))
        r1.addWidget(self.f_wahl, 1)
        r1.addWidget(self.loesung_text, 1)
        r1.addWidget(knopf)
        bl.addLayout(r1)
        r2 = QHBoxLayout()
        self.li_wahl = _combo()
        self.li_knopf = QPushButton("TRIZ-Idee übernehmen")
        self.li_knopf.setToolTip("Eine Lösungsidee aus „Ideen & TRIZ“ als Lösungsweg der gewählten Teilfunktion übernehmen")
        self.li_knopf.clicked.connect(self.loesungsidee_uebernehmen)
        r2.addWidget(QLabel("Aus TRIZ:"))
        r2.addWidget(self.li_wahl, 1)
        r2.addWidget(self.li_knopf)
        bl.addLayout(r2)
        r2b = QHBoxLayout()
        self.v_name = QLineEdit()
        self.v_name.setPlaceholderText("Name der neuen Variante, z. B. „Direktantrieb + Pitch“")
        self.v_name.returnPressed.connect(self.variante_hinzufuegen)
        vk = QPushButton("+  Variante")
        vk.setObjectName("Haupt")
        vk.clicked.connect(self.variante_hinzufuegen)
        r2b.addWidget(QLabel("Variante:"))
        r2b.addWidget(self.v_name, 1)
        r2b.addWidget(vk)
        bl.addLayout(r2b)
        self.kasten = QTableWidget()
        self.kasten.verticalHeader().setVisible(False)
        self.kasten.verticalHeader().setDefaultSectionSize(48)
        self.kasten.setSelectionMode(QAbstractItemView.SingleSelection)
        self.kasten.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.kasten.horizontalHeader().sectionClicked.connect(self._spalte_geklickt)
        self.kasten.cellClicked.connect(lambda z, s: self._spalte_geklickt(s))
        bl.addWidget(self.kasten)
        self.kasten_hinweis = _klein("")
        bl.addWidget(self.kasten_hinweis)
        lay.addWidget(box)

        # --- Nutzwertanalyse
        lay.addWidget(_abschnitt("Nutzwertanalyse"))
        box, bl = karte()
        r3 = QHBoxLayout()
        self.k_name = QLineEdit()
        self.k_name.setPlaceholderText("Kriterium, z. B. „Kosten“, „Wartungsaufwand“, „Wirkungsgrad“")
        self.k_name.returnPressed.connect(self.kriterium_hinzufuegen)
        self.k_gewicht = QDoubleSpinBox()
        self.k_gewicht.setRange(0, 100)
        self.k_gewicht.setDecimals(1)
        self.k_gewicht.setValue(1)
        self.k_gewicht.setPrefix("Gewicht ")
        kk = QPushButton("+  Kriterium")
        kk.clicked.connect(self.kriterium_hinzufuegen)
        r3.addWidget(self.k_name, 1)
        r3.addWidget(self.k_gewicht)
        r3.addWidget(kk)
        bl.addLayout(r3)
        bl.addWidget(_klein("Punkte je Kriterium von 0 (schlecht) bis 10 (sehr gut). „–“ heißt noch nicht bewertet. "
                            "Nutzwert = Σ (Gewicht × Punkte) / Σ Gewicht."))
        self.nwa = QTableWidget()
        self.nwa.verticalHeader().setVisible(False)
        self.nwa.verticalHeader().setDefaultSectionSize(38)
        self.nwa.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.nwa.horizontalHeader().sectionClicked.connect(self._spalte_geklickt)
        bl.addWidget(self.nwa)
        lay.addWidget(box)

        # --- Auswahl
        lay.addWidget(_abschnitt("Auswahl"))
        box, bl = karte()
        self.konzept_text = QLabel()
        self.konzept_text.setWordWrap(True)
        bl.addWidget(self.konzept_text)
        r4 = QHBoxLayout()
        self.v_wahl = _combo()
        self.begruendung = QLineEdit()
        self.begruendung.setPlaceholderText("Begründung (Pflicht), z. B. „wartungsarm, wenige Verschleißteile“")
        self.begruendung.returnPressed.connect(self.auswaehlen)
        ak = QPushButton("Variante auswählen")
        ak.setObjectName("Haupt")
        ak.clicked.connect(self.auswaehlen)
        bl.addWidget(self.begruendung)
        r4.addWidget(self.v_wahl, 1)
        r4.addWidget(ak)
        bl.addLayout(r4)
        lay.addWidget(box)
        lay.addStretch()

        self.panel = RueckverfolgungPanel()
        self.panel.gehe_zu.connect(self.gehe_zu_objekt)
        aussen = QVBoxLayout(self)
        aussen.setContentsMargins(0, 0, 0, 0)
        rollen = scrollbar(inhalt)
        rollen.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        aussen.addWidget(_mit_panel(rollen, self.panel))

    def setze_projekt(self, projekt: Projekt):
        self.projekt = projekt
        self.laden()

    # ---------- Laden ----------
    def laden(self):
        if not self.projekt:
            return
        self._laedt = True
        p = self.projekt
        self.teil = p.teilfunktionen()
        self.varianten = p.liste("variante")
        f_alt = self.f_wahl.currentData()
        self.f_wahl.clear()
        for f in self.teil:
            self.f_wahl.addItem(f"{f['nr']}  {f['name']}", f["id"])
        if f_alt:
            self.f_wahl.setCurrentIndex(max(0, self.f_wahl.findData(f_alt)))
        self.li_wahl.clear()
        for l in p.liste("loesungsidee"):
            self.li_wahl.addItem(f"{l['nr']}  {l['text']}", l["id"])
        self.li_knopf.setEnabled(self.li_wahl.count() > 0 and bool(self.teil))
        v_alt = self.v_wahl.currentData()
        self.v_wahl.clear()
        for v in self.varianten:
            self.v_wahl.addItem(f"{v['nr']}  {v['name']}", v["id"])
        if v_alt:
            self.v_wahl.setCurrentIndex(max(0, self.v_wahl.findData(v_alt)))
        self._kasten_laden()
        self._nwa_laden()
        self._konzept_zeigen()
        self._laedt = False

    def _kopf(self, tabelle: QTableWidget, feste: list[str]):
        n = self.projekt.nutzwerte()
        beste = max(n.values()) if n and any(n.values()) else None
        koepfe = list(feste)
        for v in self.varianten:
            marke = " ★" if v["gewaehlt"] else ""
            warn = " ⚠" if v["status"] == NEU_PRUEFEN else ""
            koepfe.append(f"{v['nr']}{marke}{warn}\n{v['name']}")
        tabelle.setColumnCount(len(koepfe))
        tabelle.setHorizontalHeaderLabels(koepfe)
        kopf = tabelle.horizontalHeader()
        kopf.setMinimumHeight(46)
        for s in range(len(feste)):
            kopf.setSectionResizeMode(s, QHeaderView.Interactive)
        for s in range(len(feste), len(koepfe)):
            kopf.setSectionResizeMode(s, QHeaderView.Stretch)
        return beste, n

    def _hoehe(self, tabelle: QTableWidget):
        """Tabelle so hoch wie ihr Inhalt – die Seite scrollt als Ganzes."""
        kopf = max(tabelle.horizontalHeader().sizeHint().height(), 46)
        zeilen = tabelle.rowCount() * tabelle.verticalHeader().defaultSectionSize()
        tabelle.setFixedHeight(max(kopf + zeilen + 2 * tabelle.frameWidth() + 2, 90))

    def _kasten_laden(self):
        t = self.kasten
        t.clearContents()
        self._kopf(t, ["Teilfunktion"])
        t.setColumnWidth(0, 230)
        t.setRowCount(len(self.teil))
        for z, f in enumerate(self.teil):
            loes = self.projekt.loesungen(f["id"])
            item = QTableWidgetItem(f"{f['nr']}  {f['name']}\n{len(loes)} Lösungswege")
            item.setData(Qt.UserRole, ("funktion", f["id"]))
            item.setToolTip("\n".join(f"• {l['text']}" for l in loes) or "noch keine Lösungswege")
            t.setItem(z, 0, item)
            for s, v in enumerate(self.varianten, 1):
                combo = _combo()
                combo.addItem("–", None)
                for l in loes:
                    combo.addItem(l["text"], l["id"])
                combo.setCurrentIndex(max(0, combo.findData(self.projekt.variante_wahl(v["id"]).get(f["id"]))))
                combo.currentIndexChanged.connect(
                    lambda _i, c=combo, vid=v["id"], fid=f["id"]: self._wahl_geaendert(vid, fid, c.currentData()))
                alt = t.cellWidget(z, s)
                if alt:
                    alt.hide()
                t.setCellWidget(z, s, combo)
        self._hoehe(t)
        if not self.teil:
            self.kasten_hinweis.setText("Noch keine Teilfunktionen. Lege sie unter „Funktionen“ an.")
        elif not self.varianten:
            self.kasten_hinweis.setText("Noch keine Varianten. Name eingeben und „+ Variante“ drücken.")
        else:
            self.kasten_hinweis.setText("Je Variante und Teilfunktion einen Lösungsweg wählen. "
                                        "Auf eine Spalte klicken zeigt die Rückverfolgung der Variante.")

    def _nwa_laden(self):
        t = self.nwa
        t.clearContents()
        beste, n = self._kopf(t, ["Kriterium", "Gewicht"])
        t.setColumnWidth(0, 200)
        t.setColumnWidth(1, 80)
        kriterien = self.projekt.kriterien()
        b = self.projekt.bewertungen()
        t.setRowCount(len(kriterien) + 1)
        for z, k in enumerate(kriterien):
            name = QLineEdit(k["name"])
            name.setFrame(False)
            name.editingFinished.connect(lambda w=name, kid=k["id"]: self._kriterium_umbenannt(kid, w.text()))
            t.setCellWidget(z, 0, name)
            g = QDoubleSpinBox()
            g.setRange(0, 100)
            g.setDecimals(1)
            g.setValue(k["gewicht"])
            g.setFrame(False)
            g.valueChanged.connect(lambda wert, kid=k["id"]: self._gewicht_geaendert(kid, wert))
            t.setCellWidget(z, 1, g)
            for s, v in enumerate(self.varianten, 2):
                sp = QDoubleSpinBox()
                sp.setRange(-1, 10)
                sp.setDecimals(1)
                sp.setSingleStep(1)
                sp.setSpecialValueText("–")
                sp.setFrame(False)
                sp.setAlignment(Qt.AlignCenter)
                sp.setValue(b.get((v["id"], k["id"]), -1))
                sp.valueChanged.connect(lambda wert, vid=v["id"], kid=k["id"]: self._punkte_geaendert(vid, kid, wert))
                t.setCellWidget(z, s, sp)
        self._nutzwert_zeile()
        self._hoehe(t)

    def _nutzwert_zeile(self):
        t = self.nwa
        z = t.rowCount() - 1
        n = self.projekt.nutzwerte()
        beste = max(n.values()) if n and max(n.values(), default=0) > 0 else None
        kopf = QTableWidgetItem("Nutzwert (0–10)")
        f = kopf.font()
        f.setBold(True)
        kopf.setFont(f)
        t.setItem(z, 0, kopf)
        t.setItem(z, 1, QTableWidgetItem(""))
        for s, v in enumerate(self.varianten, 2):
            wert = n.get(v["id"], 0)
            text = formatiere(wert, 3) + ("  ▲ bester" if beste is not None and abs(wert - beste) < 1e-9 else "")
            item = QTableWidgetItem(text)
            item.setTextAlignment(Qt.AlignCenter)
            item.setFont(f)
            if beste is not None and abs(wert - beste) < 1e-9:
                item.setForeground(self.palette().brush(self.palette().ColorRole.Highlight))
            t.setItem(z, s, item)

    def _konzept_zeigen(self):
        k = self.projekt.gewaehltes_konzept()
        if not k:
            self.konzept_text.setText("Noch keine Variante ausgewählt. Wähle unten eine Variante und begründe die Wahl.")
            return
        warn = ("  <span style='color:#c0392b'>⚠ neu prüfen: Die Bewertung hat sich seit der Auswahl geändert.</span>"
                if k["status"] == NEU_PRUEFEN else "")
        self.konzept_text.setText(f"<b>Gewählt: {k['nr']} {k['name']}</b> · {status_text(k['status'])}{warn}<br>"
                                  f"Begründung: {k['begruendung']}")

    def _spalte_geklickt(self, spalte: int):
        tabelle = self.sender()
        erste = 2 if tabelle is self.nwa or tabelle is self.nwa.horizontalHeader() else 1
        if spalte >= erste and spalte - erste < len(self.varianten):
            self.zeige_variante(self.varianten[spalte - erste]["id"])

    def zeige_variante(self, vid: int):
        v = self.projekt.objekt("variante", vid)
        self.panel.zeigen(self.projekt, "variante", vid, v["nr"], v["name"], v["status"], v["version"])

    def auswaehlen_objekt(self, typ: str, id_: int):
        if typ == "variante":
            self.zeige_variante(id_)

    # ---------- Ändern ----------
    def _fertig(self, text: str, neu_laden: bool = True):
        if neu_laden:
            self.laden()
        self.meldung.emit(text, False)
        self.geaendert.emit()

    def loesung_hinzufuegen(self):
        fid = self.f_wahl.currentData()
        if not fid:
            self.meldung.emit("Bitte zuerst unter „Funktionen“ Teilfunktionen anlegen.", True)
            return
        try:
            self.projekt.loesung_neu(fid, self.loesung_text.text())
        except ProjektFehler as exc:
            self.meldung.emit(str(exc), True)
            return
        self.loesung_text.clear()
        self._fertig("Lösungsweg ergänzt.")

    def loesungsidee_uebernehmen(self):
        fid, lid = self.f_wahl.currentData(), self.li_wahl.currentData()
        if not fid or not lid:
            return
        self.projekt.loesungsidee_als_loesung(lid, fid)
        self._fertig("TRIZ-Lösungsidee als Lösungsweg übernommen.")

    def variante_hinzufuegen(self):
        name = self.v_name.text().strip() or f"Variante {len(self.varianten) + 1}"
        v = self.projekt.variante_neu(name)
        self.v_name.clear()
        self._fertig(f"{v['nr']} angelegt.")
        self.zeige_variante(v["id"])

    def _wahl_geaendert(self, vid: int, fid: int, lid: int | None):
        if self._laedt:
            return
        war_gewaehlt = self.projekt.objekt("variante", vid)["gewaehlt"]
        self.projekt.variante_wahl_setzen(vid, fid, lid)
        self._kopf(self.kasten, ["Teilfunktion"])
        self._kopf(self.nwa, ["Kriterium", "Gewicht"])
        self._konzept_zeigen()
        self.zeige_variante(vid)
        text = "Auswahl aufgehoben, weil die gewählte Variante geändert wurde." if war_gewaehlt else "Variante geändert."
        self.meldung.emit(text, bool(war_gewaehlt))
        self.geaendert.emit()

    def kriterium_hinzufuegen(self):
        try:
            self.projekt.kriterium_neu(self.k_name.text(), self.k_gewicht.value())
        except ProjektFehler as exc:
            self.meldung.emit(str(exc), True)
            return
        self.k_name.clear()
        self.k_gewicht.setValue(1)
        self._fertig("Kriterium ergänzt.")

    def _kriterium_umbenannt(self, kid: int, name: str):
        alt = next((k for k in self.projekt.kriterien() if k["id"] == kid), None)
        if self._laedt or not alt or alt["name"] == name.strip():
            return
        try:
            self.projekt.kriterium_aendern(kid, name=name)
        except ProjektFehler as exc:
            self.meldung.emit(str(exc), True)
            return
        self._nach_bewertung()

    def _gewicht_geaendert(self, kid: int, wert: float):
        if self._laedt:
            return
        self.projekt.kriterium_aendern(kid, gewicht=wert)
        self._nach_bewertung()

    def _punkte_geaendert(self, vid: int, kid: int, wert: float):
        if self._laedt or wert < 0:
            return
        self.projekt.bewerten(vid, kid, wert)
        self._nach_bewertung()

    def _nach_bewertung(self):
        self._nutzwert_zeile()
        self._kopf(self.kasten, ["Teilfunktion"])
        self._kopf(self.nwa, ["Kriterium", "Gewicht"])
        self._konzept_zeigen()
        self.geaendert.emit()

    def auswaehlen(self):
        vid = self.v_wahl.currentData()
        if not vid:
            self.meldung.emit("Es gibt noch keine Variante.", True)
            return
        try:
            v = self.projekt.variante_auswaehlen(vid, self.begruendung.text())
        except ProjektFehler as exc:
            self.meldung.emit(str(exc), True)
            self.begruendung.setFocus()
            return
        self.begruendung.clear()
        self._fertig(f"{v['nr']} {v['name']} als Konzept ausgewählt.")
        self.zeige_variante(vid)
