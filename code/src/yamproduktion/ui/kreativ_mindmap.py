"""Mindmap (K2): Gliederung links, grafische Mindmap rechts. Alles wird sofort gespeichert."""
from __future__ import annotations

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QFontMetricsF, QKeySequence, QPainter, QPainterPath, QPalette,
                           QPen, QShortcut)
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QGraphicsItem, QGraphicsPathItem, QGraphicsScene,
                               QGraphicsView, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QSplitter,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from .. import kreativ
from ..modell import Projekt, ProjektFehler
from .thema import FARBEN

ID_ROLLE = Qt.UserRole
THEMA = -1                      # Kennung des Themas im Baum (das Thema hat keine Beitrags-ID)
TEXT_BREITE = 160.0             # maximale Textbreite eines Knotens in der Grafik

# Je Hauptast eine Farbe: (hell, dunkel). Hell: weiße Schrift auf kräftiger Fläche, dunkel: dunkle Schrift auf
# heller Fläche – beides mit Kontrast über 4,5 : 1.
AST_FARBEN = (
    ("#C2410C", "#FDBA74"),     # orange
    ("#15803D", "#86EFAC"),     # grün
    ("#7E22CE", "#D8B4FE"),     # violett
    ("#BE185D", "#F9A8D4"),     # rosa
    ("#0E7490", "#67E8F9"),     # türkis
    ("#A16207", "#FDE047"),     # gelb
    ("#4338CA", "#A5B4FC"),     # indigo
    ("#B91C1C", "#FCA5A5"),     # rot
)


def _ist_dunkel() -> bool:
    return QApplication.palette().color(QPalette.Window).lightness() < 128


def _farben() -> dict:
    return FARBEN["dunkel" if _ist_dunkel() else "hell"]


def _mische(a: QColor, b: QColor, anteil_a: float) -> QColor:
    return QColor(round(a.red() * anteil_a + b.red() * (1 - anteil_a)),
                  round(a.green() * anteil_a + b.green() * (1 - anteil_a)),
                  round(a.blue() * anteil_a + b.blue() * (1 - anteil_a)))


def _ast_farbe(index: int) -> QColor:
    hell, dunkel = AST_FARBEN[index % len(AST_FARBEN)]
    return QColor(dunkel if _ist_dunkel() else hell)


# ---------------------------------------------------------------- Grafik
class _Knoten(QGraphicsItem):
    """Ein Knoten der Mindmap: abgerundete Fläche mit umbrochenem Text. art: 'thema' | 'ast' | 'zweig'."""

    def __init__(self, eintrag_id: int, text: str, art: str, farbindex: int):
        super().__init__()
        self.eintrag_id = eintrag_id
        self.text = text
        self.art = art
        self.farbindex = farbindex
        self.schrift = QFont(QApplication.font())
        self.schrift.setPixelSize(20 if art == "thema" else 16)
        self.schrift.setBold(art != "zweig")
        rand_x, rand_y = (20, 14) if art == "thema" else (12, 8)
        breite = TEXT_BREITE + (40 if art == "thema" else 0)
        fm = QFontMetricsF(self.schrift)
        r = fm.boundingRect(QRectF(0, 0, breite, 10000), Qt.TextWordWrap | Qt.AlignCenter, text or " ")
        w, h = r.width() + 2 * rand_x, r.height() + 2 * rand_y
        self._rect = QRectF(-w / 2, -h / 2, w, h)
        self._text_rect = self._rect.adjusted(rand_x, rand_y, -rand_x, -rand_y)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(text)
        self.setZValue(1)

    def boundingRect(self) -> QRectF:
        return self._rect.adjusted(-4, -4, 4, 4)

    def farben(self) -> tuple[QColor, QColor, QColor]:
        """(Fläche, Rand, Text) – passend zu Hell/Dunkel."""
        f = _farben()
        if self.art == "thema":
            return QColor(f["akzent"]), QColor(f["akzent"]), QColor(f["akzent_text"])
        stark = _ast_farbe(self.farbindex)
        if self.art == "ast":
            return stark, stark, QColor("#0B1520" if _ist_dunkel() else "#FFFFFF")
        grund = QColor(f["flaeche"])
        return _mische(stark, grund, 0.22 if _ist_dunkel() else 0.14), stark, QColor(f["text"])

    def paint(self, painter: QPainter, option, widget=None) -> None:
        flaeche, rand, schrift = self.farben()
        painter.setRenderHint(QPainter.Antialiasing)
        radius = 18 if self.art == "thema" else 10
        if self.isSelected():
            painter.setPen(QPen(QColor(_farben()["text"]), 3))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(self._rect.adjusted(-4, -4, 4, 4), radius + 3, radius + 3)
        painter.setPen(QPen(rand, 2))
        painter.setBrush(QBrush(flaeche))
        painter.drawRoundedRect(self._rect, radius, radius)
        painter.setPen(schrift)
        painter.setFont(self.schrift)
        painter.drawText(self._text_rect, Qt.TextWordWrap | Qt.AlignCenter, self.text)


class _Ansicht(QGraphicsView):
    doppelklick = Signal(int)          # Knoten-ID (THEMA für das Thema)

    def __init__(self, szene: QGraphicsScene):
        super().__init__(szene)
        self.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QGraphicsView.NoFrame)
        self.setToolTip("")

    def einpassen(self) -> None:
        szene = self.scene()
        if szene is None or not szene.items():
            return
        r = szene.itemsBoundingRect().adjusted(-40, -40, 40, 40)
        self.setSceneRect(r.adjusted(-2000, -2000, 2000, 2000))
        self.fitInView(r, Qt.KeepAspectRatio)
        if self.transform().m11() > 1.0:          # kleine Mindmaps nicht aufblasen
            self.resetTransform()
            self.centerOn(r.center())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.einpassen()

    def wheelEvent(self, event) -> None:
        faktor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        neu = self.transform().m11() * faktor
        if 0.15 <= neu <= 3.0:
            self.scale(faktor, faktor)

    def mouseDoubleClickEvent(self, event) -> None:
        item = self.itemAt(event.position().toPoint())
        if isinstance(item, _Knoten):
            self.doppelklick.emit(item.eintrag_id)
            return
        super().mouseDoubleClickEvent(event)


# ---------------------------------------------------------------- Gliederung
class _Baum(QTreeWidget):
    umhaengen = Signal(int, object)    # Knoten-ID, neue Eltern-ID (None = Hauptast)

    def __init__(self):
        super().__init__()
        self.setHeaderHidden(True)
        self.setColumnCount(1)
        self.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setIndentation(18)
        self.setWordWrap(True)

    def dropEvent(self, event) -> None:
        # Nicht Qt verschieben lassen – nur den neuen Elternknoten ermitteln, speichern und neu laden.
        quelle = self.currentItem()
        ziel = self.itemAt(event.position().toPoint())
        event.setDropAction(Qt.IgnoreAction)
        event.accept()
        if quelle is None or ziel is None or ziel is quelle:
            return
        qid = quelle.data(0, ID_ROLLE)
        if qid == THEMA:
            return
        lage = self.dropIndicatorPosition()
        if lage == QAbstractItemView.OnItem:
            eltern = ziel
        else:
            eltern = ziel.parent()
        eid = None if eltern is None else eltern.data(0, ID_ROLLE)
        self.umhaengen.emit(qid, None if eid in (None, THEMA) else eid)


# ---------------------------------------------------------------- Ansicht
class MindmapAnsicht(QWidget):
    meldung = Signal(str, bool)
    geaendert = Signal()
    auswahl_geaendert = Signal()

    def __init__(self):
        super().__init__()
        self.projekt: Projekt | None = None
        self.sitzung: dict | None = None
        self.knoten: list[dict] = []
        self.knoten_items: dict[int, _Knoten] = {}
        self.thema_item: _Knoten | None = None
        self._baum_items: dict[int, QTreeWidgetItem] = {}
        self._auswahl: int = THEMA
        self._laedt = False

        haupt = QHBoxLayout(self)
        haupt.setContentsMargins(0, 0, 0, 0)
        self.teiler = QSplitter(Qt.Horizontal)
        haupt.addWidget(self.teiler)

        # --- links: Eingabe + Gliederung
        links = QWidget()
        ll = QVBoxLayout(links)
        ll.setContentsMargins(0, 0, 8, 0)
        ll.setSpacing(8)
        self.eingabe = QLineEdit()
        self.eingabe.setPlaceholderText("Neuer Ast …")
        self.eingabe.returnPressed.connect(self._enter)
        ll.addWidget(self.eingabe)
        knoepfe = QHBoxLayout()
        self.knopf_ast = QPushButton("+ Ast")
        self.knopf_ast.setObjectName("Haupt")
        self.knopf_ast.setToolTip("Neuer Hauptast direkt am Thema")
        self.knopf_ast.clicked.connect(lambda: self._aus_eingabe(ast=True))
        self.knopf_zweig = QPushButton("+ Zweig")
        self.knopf_zweig.setToolTip("Neuer Zweig unter dem ausgewählten Knoten (Enter)")
        self.knopf_zweig.clicked.connect(lambda: self._aus_eingabe(ast=False))
        knoepfe.addWidget(self.knopf_ast, 1)
        knoepfe.addWidget(self.knopf_zweig, 1)
        ll.addLayout(knoepfe)

        self.baum = _Baum()
        self.baum.currentItemChanged.connect(self._baum_auswahl)
        self.baum.itemChanged.connect(self._baum_text_geaendert)
        self.baum.umhaengen.connect(self._umhaengen)
        ll.addWidget(self.baum, 1)
        for taste in (QKeySequence.Delete, QKeySequence(Qt.Key_Backspace)):
            kurz = QShortcut(taste, self.baum)
            kurz.setContext(Qt.WidgetShortcut)
            kurz.activated.connect(self.loeschen)

        hinweis = QLabel("Doppelklick = umbenennen · Entf = löschen · ziehen = umhängen")
        hinweis.setObjectName("Klein")
        hinweis.setWordWrap(True)
        ll.addWidget(hinweis)
        unten = QHBoxLayout()
        self.knopf_loeschen = QPushButton("Löschen")
        self.knopf_loeschen.clicked.connect(self.loeschen)
        self.knopf_kopieren = QPushButton("Als Text kopieren")
        self.knopf_kopieren.setToolTip("Die Gliederung als eingerückten Text in die Zwischenablage legen")
        self.knopf_kopieren.clicked.connect(self.kopieren)
        unten.addWidget(self.knopf_loeschen)
        unten.addWidget(self.knopf_kopieren, 1)
        ll.addLayout(unten)
        links.setMinimumWidth(240)
        self.teiler.addWidget(links)

        # --- rechts: Grafik
        self.szene = QGraphicsScene(self)
        self.szene.selectionChanged.connect(self._szene_auswahl)
        self.ansicht = _Ansicht(self.szene)
        self.ansicht.doppelklick.connect(self._grafik_doppelklick)
        self.teiler.addWidget(self.ansicht)
        self.teiler.setStretchFactor(0, 0)
        self.teiler.setStretchFactor(1, 1)
        self.teiler.setSizes([300, 800])
        self._knoepfe_pruefen()

    # ------------------------------------------------------------ Schnittstelle
    def setze(self, projekt: Projekt | None, sitzung: dict | None) -> None:
        wechsel = sitzung is None or self.sitzung is None or sitzung.get("id") != self.sitzung.get("id")
        self.projekt, self.sitzung = projekt, sitzung
        if wechsel:
            self._auswahl = THEMA
        self.laden()

    def ausgewaehlt(self) -> int | None:
        return None if self._auswahl == THEMA else self._auswahl

    def laden(self) -> None:
        if self.projekt is None or self.sitzung is None:
            self.knoten = []
        else:
            try:
                self.knoten = self.projekt.kreativ_eintraege(self.sitzung["id"])
            except ProjektFehler as exc:
                self.knoten = []
                self.meldung.emit(str(exc), True)
        if self._auswahl != THEMA and self._auswahl not in {k["id"] for k in self.knoten}:
            self._auswahl = THEMA
        self._baum_fuellen()
        self._zeichnen()
        self._auswahl_zeigen()
        self._knoepfe_pruefen()

    # ------------------------------------------------------------ öffentliche Methoden (auch für Tests)
    def thema(self) -> str:
        if not self.sitzung:
            return ""
        return (self.sitzung.get("frage") or "").strip() or (self.sitzung.get("titel") or "").strip() or "Thema"

    def waehle(self, eintrag_id: int | None) -> None:
        """Knoten auswählen (None = Thema)."""
        neu = THEMA if eintrag_id is None else eintrag_id
        if neu != THEMA and neu not in self._baum_items:
            return
        alt = self._auswahl
        self._auswahl = neu
        self._auswahl_zeigen()
        self._knoepfe_pruefen()
        if alt != neu:
            self.auswahl_geaendert.emit()

    def ast_hinzufuegen(self, text: str) -> dict | None:
        """Neuer Hauptast direkt am Thema."""
        return self._neu(text, None)

    def zweig_hinzufuegen(self, text: str) -> dict | None:
        """Neuer Zweig unter dem ausgewählten Knoten (am Thema = Hauptast). Die Auswahl bleibt beim Elternknoten."""
        return self._neu(text, self.ausgewaehlt())

    def umbenennen(self, text: str) -> bool:
        if not self._darf_aendern():
            return False
        if self._auswahl == THEMA:
            self.meldung.emit("Das Thema ist die Frage der Sitzung – bitte oben bei der Sitzung ändern.", True)
            return False
        try:
            self.projekt.kreativ_eintrag_aendern(self._auswahl, text=text)
        except ProjektFehler as exc:
            self.meldung.emit(str(exc), True)
            self.laden()
            return False
        self.laden()
        self.geaendert.emit()
        return True

    def loeschen(self) -> bool:
        if not self._darf_aendern():
            return False
        if self._auswahl == THEMA:
            self.meldung.emit("Das Thema in der Mitte kann nicht gelöscht werden.", True)
            return False
        eid = self._auswahl
        eintrag = next((k for k in self.knoten if k["id"] == eid), None)
        unter = self._nachkommen(eid)
        if unter:
            antwort = QMessageBox.question(
                self, "Knoten löschen",
                f"„{eintrag['text'] if eintrag else ''}“ hat {unter} Zweig{'e' if unter != 1 else ''} darunter. "
                "Alles zusammen löschen?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if antwort != QMessageBox.Yes:
                return False
        eltern = eintrag.get("eltern_id") if eintrag else None
        try:
            self.projekt.kreativ_eintrag_loeschen(eid)
        except ProjektFehler as exc:
            self.meldung.emit(str(exc), True)
            self.laden()
            return False
        self._auswahl = eltern if eltern is not None else THEMA
        self.laden()
        self.auswahl_geaendert.emit()
        self.geaendert.emit()
        self.meldung.emit("Gelöscht.", False)
        return True

    def haengen(self, eintrag_id: int, eltern_id: int | None) -> bool:
        """Knoten unter einen anderen Knoten hängen (None = Hauptast am Thema)."""
        if not self._darf_aendern():
            return False
        try:
            self.projekt.kreativ_eintrag_aendern(eintrag_id, eltern_id=eltern_id)
        except ProjektFehler as exc:
            self.meldung.emit(str(exc), True)
            self.laden()
            return False
        self._auswahl = eintrag_id
        self.laden()
        self.geaendert.emit()
        return True

    def als_text(self) -> str:
        return kreativ.gliederung(self.thema(), self.knoten)

    def kopieren(self) -> None:
        QApplication.clipboard().setText(self.als_text())
        self.meldung.emit("Gliederung kopiert.", False)

    # ------------------------------------------------------------ intern: Ändern
    def _darf_aendern(self) -> bool:
        if self.projekt is None or self.sitzung is None:
            self.meldung.emit("Bitte zuerst eine Mindmap-Sitzung wählen.", True)
            return False
        return True

    def _neu(self, text: str, eltern_id: int | None) -> dict | None:
        if not self._darf_aendern():
            return None
        try:
            e = self.projekt.kreativ_eintrag_neu(self.sitzung["id"], text, eltern_id=eltern_id)
        except ProjektFehler as exc:
            self.meldung.emit(str(exc), True)
            return None
        self.laden()
        self.geaendert.emit()
        return e

    def _aus_eingabe(self, ast: bool) -> None:
        text = self.eingabe.text()
        e = self.ast_hinzufuegen(text) if ast else self.zweig_hinzufuegen(text)
        if e is not None:
            self.eingabe.clear()
        self.eingabe.setFocus()

    def _enter(self) -> None:
        self._aus_eingabe(ast=self._auswahl == THEMA)

    def _nachkommen(self, eid: int) -> int:
        kinder = [k["id"] for k in self.knoten if k.get("eltern_id") == eid]
        return len(kinder) + sum(self._nachkommen(k) for k in kinder)

    def _baum_text_geaendert(self, item: QTreeWidgetItem, _spalte: int) -> None:
        if self._laedt:
            return
        eid = item.data(0, ID_ROLLE)
        if eid == THEMA or self.projekt is None:
            return
        alt = next((k["text"] for k in self.knoten if k["id"] == eid), None)
        if item.text(0).strip() == (alt or "").strip():
            return
        try:
            self.projekt.kreativ_eintrag_aendern(eid, text=item.text(0))
        except ProjektFehler as exc:
            self.meldung.emit(str(exc), True)
        else:
            self.geaendert.emit()
        # Neu laden erst nach dem Ende der Bearbeitung im Baum
        QTimer.singleShot(0, self.laden)

    def _umhaengen(self, eid: int, eltern_id) -> None:
        alt = next((k.get("eltern_id") for k in self.knoten if k["id"] == eid), None)
        if alt == eltern_id:
            return
        QTimer.singleShot(0, lambda: self.haengen(eid, eltern_id))

    def _grafik_doppelklick(self, eid: int) -> None:
        self.waehle(None if eid == THEMA else eid)
        if eid != THEMA and eid in self._baum_items:
            self.baum.editItem(self._baum_items[eid], 0)
        else:
            self.eingabe.setFocus()

    # ------------------------------------------------------------ intern: Anzeigen
    def _knoepfe_pruefen(self) -> None:
        aktiv = self.sitzung is not None and self.projekt is not None
        for w in (self.eingabe, self.knopf_ast, self.knopf_zweig, self.knopf_kopieren, self.baum):
            w.setEnabled(aktiv)
        self.knopf_loeschen.setEnabled(aktiv and self._auswahl != THEMA)
        if self._auswahl == THEMA:
            self.eingabe.setPlaceholderText("Neuer Ast …")
            self.knopf_zweig.setToolTip("Neuer Ast am Thema (Enter)")
        else:
            name = next((k["text"] for k in self.knoten if k["id"] == self._auswahl), "")
            kurz = name if len(name) <= 24 else name[:22] + " …"
            self.eingabe.setPlaceholderText(f"Neuer Zweig unter „{kurz}“ …")
            self.knopf_zweig.setToolTip(f"Neuer Zweig unter „{name}“ (Enter)")

    def _baum_fuellen(self) -> None:
        self._laedt = True
        self.baum.blockSignals(True)
        self.baum.clear()
        self._baum_items = {}
        if self.sitzung is not None:
            wurzel = QTreeWidgetItem([self.thema()])
            wurzel.setData(0, ID_ROLLE, THEMA)
            wurzel.setToolTip(0, self.thema())
            wurzel.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDropEnabled)
            f = wurzel.font(0)
            f.setBold(True)
            wurzel.setFont(0, f)
            self.baum.addTopLevelItem(wurzel)
            stapel = [wurzel]
            for tiefe, k in kreativ.baum(self.knoten):
                del stapel[tiefe:]
                item = QTreeWidgetItem([k["text"]])
                item.setData(0, ID_ROLLE, k["id"])
                item.setToolTip(0, k["text"])
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable
                              | Qt.ItemIsDragEnabled | Qt.ItemIsDropEnabled)
                stapel[-1].addChild(item)
                stapel.append(item)
                self._baum_items[k["id"]] = item
            self.baum.expandAll()
        self.baum.blockSignals(False)
        self._laedt = False

    def _zeichnen(self) -> None:
        self._laedt = True
        self.szene.blockSignals(True)
        self.szene.clear()
        self.knoten_items = {}
        self.thema_item = None
        f = _farben()
        self.ansicht.setBackgroundBrush(QBrush(QColor(f["flaeche"])))
        if self.sitzung is None:
            leer = self.szene.addText("Keine Mindmap gewählt.")
            leer.setDefaultTextColor(QColor(f["text2"]))
            self.szene.blockSignals(False)
            self._laedt = False
            return
        lagen = kreativ.anordnung(self.knoten)
        # Farbe je Hauptast; Zweige erben sie
        farbe: dict[int, int] = {}
        tiefe_von: dict[int, int] = {}
        hauptast = -1
        for tiefe, k in kreativ.baum(self.knoten):
            tiefe_von[k["id"]] = tiefe
            if tiefe == 1:
                hauptast += 1
                farbe[k["id"]] = hauptast
            else:
                farbe[k["id"]] = farbe.get(k.get("eltern_id"), 0)

        self.thema_item = _Knoten(THEMA, self.thema(), "thema", 0)
        self.thema_item.setPos(0, 0)
        self.thema_item.setZValue(2)
        self.szene.addItem(self.thema_item)
        for k in self.knoten:
            if k["id"] not in lagen:
                continue
            art = "ast" if tiefe_von.get(k["id"]) == 1 else "zweig"
            item = _Knoten(k["id"], k["text"], art, farbe.get(k["id"], 0))
            item.setPos(*lagen[k["id"]])
            self.szene.addItem(item)
            self.knoten_items[k["id"]] = item

        # Verbindungen: geschwungen von der Mitte des Elternknotens zur Mitte des Knotens
        for k in self.knoten:
            if k["id"] not in self.knoten_items:
                continue
            eltern = self.knoten_items.get(k.get("eltern_id"), self.thema_item)
            a, b = eltern.pos(), self.knoten_items[k["id"]].pos()
            pfad = QPainterPath(a)
            dx, dy = b.x() - a.x(), b.y() - a.y()
            if abs(dx) >= abs(dy):
                pfad.cubicTo(QPointF(a.x() + dx * 0.5, a.y()), QPointF(a.x() + dx * 0.5, b.y()), b)
            else:
                pfad.cubicTo(QPointF(a.x(), a.y() + dy * 0.5), QPointF(b.x(), a.y() + dy * 0.5), b)
            linie = QGraphicsPathItem(pfad)
            breite = 5 if tiefe_von.get(k["id"]) == 1 else 3
            stift = QPen(_ast_farbe(farbe.get(k["id"], 0)), breite)
            stift.setCapStyle(Qt.RoundCap)
            linie.setPen(stift)
            linie.setZValue(0)
            self.szene.addItem(linie)
        self.szene.blockSignals(False)
        self._laedt = False
        self.ansicht.einpassen()

    def _auswahl_zeigen(self) -> None:
        self._laedt = True
        self.baum.blockSignals(True)
        if self._auswahl == THEMA:
            item = self.baum.topLevelItem(0)
        else:
            item = self._baum_items.get(self._auswahl)
        if item is not None:
            self.baum.setCurrentItem(item)
            self.baum.scrollToItem(item)
        self.baum.blockSignals(False)
        self.szene.blockSignals(True)
        self.szene.clearSelection()
        g = self.thema_item if self._auswahl == THEMA else self.knoten_items.get(self._auswahl)
        if g is not None:
            g.setSelected(True)
        self.szene.blockSignals(False)
        self._laedt = False

    def _baum_auswahl(self, aktuell: QTreeWidgetItem | None, _vorher=None) -> None:
        if self._laedt or aktuell is None:
            return
        eid = aktuell.data(0, ID_ROLLE)
        self.waehle(None if eid == THEMA else eid)

    def _szene_auswahl(self) -> None:
        if self._laedt:
            return
        gewaehlt = [i for i in self.szene.selectedItems() if isinstance(i, _Knoten)]
        if not gewaehlt:
            # Klick ins Leere: Auswahl sichtbar lassen
            QTimer.singleShot(0, self._auswahl_zeigen)
            return
        eid = gewaehlt[0].eintrag_id
        self.waehle(None if eid == THEMA else eid)

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() in (QEvent.PaletteChange, QEvent.ApplicationPaletteChange) and not self._laedt:
            self._zeichnen()
            self._auswahl_zeigen()
