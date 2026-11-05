"""Brainstorming-Board (K2): Ideen als Haftzettel sammeln, frei anordnen, gruppieren und mit Punkten bewerten.

Die Ansicht wird von der Kreativ-Seite eingebettet (Schnittstelle: ``setze``, ``laden``, ``ausgewaehlt`` und die
Signale ``meldung``, ``geaendert``, ``auswahl_geaendert``). Jede Änderung wird sofort im Projekt gespeichert.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetrics, QKeySequence, QPainter, QPalette, QPen, QShortcut
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFrame, QGraphicsItem, QGraphicsScene, QGraphicsSimpleTextItem, QGraphicsView,
    QHBoxLayout, QInputDialog, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget,
)

from .. import kreativ
from ..modell import Projekt, ProjektFehler
from .seiten import karte, scrollbar

BREITE, HOEHE = 180.0, 110.0
ABSTAND_X, ABSTAND_Y = 20.0, 20.0
OHNE_GRUPPE = "(ohne Gruppe)"
ZEIT_MINUTEN = 15

# Feste Palette je Gruppe: (Hintergrund hell, Hintergrund dunkel)
PALETTE = (
    ("#FFF1A8", "#5A5122"),   # gelb
    ("#CFE6FF", "#26445F"),   # blau
    ("#D3F2CF", "#2C4C31"),   # grün
    ("#FFD7E2", "#5A2F3C"),   # rosa
    ("#FFE0C0", "#5A3E24"),   # orange
    ("#E3D9FF", "#41365F"),   # lila
    ("#C9EFEA", "#21504B"),   # türkis
    ("#ECE3D4", "#4A4135"),   # sand
)
NEUTRAL = ("#FFFFFF", "#2B3036")


def _dunkel() -> bool:
    return QApplication.palette().color(QPalette.Window).lightness() < 128


def _schrift(px: int, fett: bool = False) -> QFont:
    f = QFont(QApplication.font())
    f.setPixelSize(px)
    f.setBold(fett)
    return f


class ZettelItem(QGraphicsItem):
    """Ein Haftzettel auf der Pinnwand. Lage ist die linke obere Ecke (wie im Modell gespeichert)."""

    def __init__(self, ansicht: "BoardAnsicht", eintrag: dict):
        super().__init__()
        self.ansicht = ansicht
        self.eintrag = dict(eintrag)
        self.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable
                      | QGraphicsItem.ItemSendsGeometryChanges)
        self.setCursor(Qt.OpenHandCursor)
        self.setPos(float(eintrag.get("x") or 0), float(eintrag.get("y") or 0))
        self.setToolTip(eintrag["text"])

    @property
    def id(self) -> int:
        return self.eintrag["id"]

    def neu_setzen(self, eintrag: dict) -> None:
        self.eintrag = dict(eintrag)
        self.setToolTip(eintrag["text"])
        self.update()

    def boundingRect(self) -> QRectF:
        return QRectF(-4, -4, BREITE + 8, HOEHE + 8)

    def itemChange(self, change, wert):
        if change == QGraphicsItem.ItemPositionChange:
            return QPointF(max(0.0, wert.x()), max(0.0, wert.y()))
        return super().itemChange(change, wert)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        hg, rand, text, text2, punkt = self.ansicht.farben(self.eintrag.get("gruppe", ""))
        painter.setRenderHint(QPainter.Antialiasing)
        rechteck = QRectF(0, 0, BREITE, HOEHE)
        # leichter Schatten
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 60 if _dunkel() else 28))
        painter.drawRoundedRect(rechteck.translated(2, 3), 6, 6)
        gewaehlt = self.isSelected()
        akzent = QApplication.palette().color(QPalette.Highlight)
        painter.setPen(QPen(akzent, 3) if gewaehlt else QPen(rand, 1))
        painter.setBrush(hg)
        painter.drawRoundedRect(rechteck, 6, 6)

        innen = rechteck.adjusted(10, 6, -10, -6)
        gruppe = (self.eintrag.get("gruppe") or "").strip()
        oben = innen.top()
        if gruppe:
            painter.setFont(_schrift(13, True))
            painter.setPen(text2)
            fm = QFontMetrics(painter.font())
            painter.drawText(QRectF(innen.left(), oben, innen.width(), fm.height()), Qt.AlignLeft | Qt.AlignVCenter,
                             fm.elidedText(gruppe.upper(), Qt.ElideRight, int(innen.width())))
            oben += fm.height() + 1
        punkte = int(self.eintrag.get("punkte") or 0)
        unten = innen.bottom()
        if punkte > 0:
            painter.setFont(_schrift(14, True))
            fm = QFontMetrics(painter.font())
            zeile = QRectF(innen.left(), unten - fm.height(), innen.width(), fm.height())
            r = 5.5
            mitte = QPointF(zeile.right() - fm.horizontalAdvance(str(punkte)) - 6 - r, zeile.center().y())
            painter.setPen(Qt.NoPen)
            painter.setBrush(punkt)
            painter.drawEllipse(mitte, r, r)
            painter.setPen(text)
            painter.drawText(zeile, Qt.AlignRight | Qt.AlignVCenter, str(punkte))
            unten -= fm.height()
        feld = QRectF(innen.left(), oben, innen.width(), max(10.0, unten - oben))
        painter.setPen(text)
        inhalt, schrift = _einpassen(self.eintrag["text"], feld)
        painter.setFont(schrift)
        painter.drawText(feld, Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, inhalt)

    def mousePressEvent(self, event) -> None:
        self.ansicht.nach_vorne(self)
        self.setCursor(Qt.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        self.setCursor(Qt.OpenHandCursor)
        self.ansicht.lagen_speichern()

    def mouseDoubleClickEvent(self, event) -> None:
        # Dialog erst nach dem Ereignis öffnen – das Board wird danach neu aufgebaut
        QTimer.singleShot(0, lambda i=self.id: self.ansicht.text_bearbeiten(i))
        event.accept()


def _einpassen(text: str, feld: QRectF) -> tuple[str, QFont]:
    """Schrift so groß wie möglich (16 → 13 px); passt es dann nicht, wird mit „…“ gekürzt."""
    flags = Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap
    for px in (16, 15, 14, 13):
        f = _schrift(px)
        if QFontMetrics(f).boundingRect(feld.toRect(), flags, text).height() <= feld.height():
            return text, f
    fm = QFontMetrics(f)
    woerter = text.split()
    while len(woerter) > 1:
        woerter.pop()
        kurz = " ".join(woerter) + " …"
        if fm.boundingRect(feld.toRect(), flags, kurz).height() <= feld.height():
            return kurz, f
    return fm.elidedText(text, Qt.ElideRight, int(feld.width())), f


class _Pinnwand(QGraphicsView):
    def __init__(self, szene: QGraphicsScene):
        super().__init__(szene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.setFrameShape(QFrame.NoFrame)
        self.setMinimumHeight(260)
        self.setFocusPolicy(Qt.StrongFocus)


class BoardAnsicht(QWidget):
    meldung = Signal(str, bool)
    geaendert = Signal()
    auswahl_geaendert = Signal()

    def __init__(self):
        super().__init__()
        self.projekt: Projekt | None = None
        self.sitzung: dict | None = None
        self.eintraege: list[dict] = []
        self.zettel: dict[int, ZettelItem] = {}
        self._gruppen: list[str] = []
        self._auswahl_id: int | None = None
        self._baut = False
        self._z = 1.0
        self._rest = ZEIT_MINUTEN * 60

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)

        # ---------------------------------------------------------- links: Eingabe + Pinnwand
        links = QVBoxLayout()
        links.setSpacing(10)
        reihe = QHBoxLayout()
        self.eingabe = QLineEdit()
        self.eingabe.setPlaceholderText("Neue Idee als Zettel …")
        self.eingabe.returnPressed.connect(self._eingabe_hinzufuegen)
        reihe.addWidget(self.eingabe, 3)
        self.gruppe_eingabe = QComboBox()
        self.gruppe_eingabe.setEditable(True)
        self.gruppe_eingabe.setInsertPolicy(QComboBox.NoInsert)
        self.gruppe_eingabe.lineEdit().setPlaceholderText("Gruppe")
        self.gruppe_eingabe.lineEdit().returnPressed.connect(self._eingabe_hinzufuegen)
        self.gruppe_eingabe.setToolTip("Neue Zettel kommen in diese Gruppe. Leer lassen = ohne Gruppe.")
        reihe.addWidget(self.gruppe_eingabe, 1)
        self.knopf_neu = QPushButton("+ Zettel")
        self.knopf_neu.setObjectName("Haupt")
        self.knopf_neu.clicked.connect(self._eingabe_hinzufuegen)
        reihe.addWidget(self.knopf_neu)
        links.addLayout(reihe)

        self.szene = QGraphicsScene(self)
        self.szene.selectionChanged.connect(self._auswahl_wechsel)
        self.ansicht = _Pinnwand(self.szene)
        links.addWidget(self.ansicht, 1)
        for taste in (QKeySequence.Delete, QKeySequence(Qt.Key_Backspace)):
            k = QShortcut(taste, self.ansicht)
            k.setContext(Qt.WidgetShortcut)
            k.activated.connect(self.loeschen)
        k = QShortcut(QKeySequence(Qt.Key_Plus), self.ansicht)
        k.setContext(Qt.WidgetShortcut)
        k.activated.connect(lambda: self.punkt(1))
        k = QShortcut(QKeySequence(Qt.Key_Minus), self.ansicht)
        k.setContext(Qt.WidgetShortcut)
        k.activated.connect(lambda: self.punkt(-1))
        k = QShortcut(QKeySequence(Qt.Key_Return), self.ansicht)
        k.setContext(Qt.WidgetShortcut)
        k.activated.connect(lambda: self._auswahl_id and self.text_bearbeiten(self._auswahl_id))

        unten = QHBoxLayout()
        self.hinweis = QLabel("Zettel mit der Maus verschieben · Doppelklick = Text ändern · Entf = löschen")
        self.hinweis.setObjectName("Klein")
        self.hinweis.setWordWrap(True)
        unten.addWidget(self.hinweis, 1)
        self.knopf_ordnen = QPushButton("Nach Gruppen ordnen")
        self.knopf_ordnen.setToolTip("Legt die Zettel spaltenweise je Gruppe nebeneinander.")
        self.knopf_ordnen.clicked.connect(self.nach_gruppen_ordnen)
        unten.addWidget(self.knopf_ordnen)
        links.addLayout(unten)
        lay.addLayout(links, 1)

        # ---------------------------------------------------------- rechts: Auswahl, Beste, Regeln, Zeit
        seite = QWidget()
        sl = QVBoxLayout(seite)
        sl.setContentsMargins(0, 0, 14, 0)
        sl.setSpacing(12)

        box, bl = karte()
        bl.setContentsMargins(14, 12, 14, 12)
        t = QLabel("Ausgewählter Zettel")
        t.setObjectName("Unterabschnitt")
        t.setStyleSheet("margin-top: 0px;")
        bl.addWidget(t)
        self.auswahl_text = QLabel()
        self.auswahl_text.setWordWrap(True)
        bl.addWidget(self.auswahl_text)
        punkte = QHBoxLayout()
        self.knopf_plus = QPushButton("+1 Punkt")
        self.knopf_plus.setToolTip("Einen Klebepunkt vergeben (Taste +)")
        self.knopf_plus.clicked.connect(lambda: self.punkt(1))
        self.knopf_minus = QPushButton("−1")
        self.knopf_minus.setToolTip("Einen Klebepunkt wegnehmen (Taste −)")
        self.knopf_minus.clicked.connect(lambda: self.punkt(-1))
        punkte.addWidget(self.knopf_plus, 2)
        punkte.addWidget(self.knopf_minus, 1)
        bl.addLayout(punkte)
        self.gruppe_wahl = QComboBox()
        self.gruppe_wahl.setEditable(True)
        self.gruppe_wahl.setInsertPolicy(QComboBox.NoInsert)
        self.gruppe_wahl.lineEdit().setPlaceholderText("Gruppe ändern")
        self.gruppe_wahl.setToolTip("Gruppe des Zettels – wählen oder neuen Namen eintippen und Enter drücken.")
        self.gruppe_wahl.activated.connect(lambda _i: self.gruppe_setzen(self.gruppe_wahl.currentText()))
        self.gruppe_wahl.lineEdit().returnPressed.connect(lambda: self.gruppe_setzen(self.gruppe_wahl.currentText()))
        bl.addWidget(self.gruppe_wahl)
        knoepfe = QHBoxLayout()
        self.knopf_text = QPushButton("Text ändern")
        self.knopf_text.clicked.connect(lambda: self._auswahl_id and self.text_bearbeiten(self._auswahl_id))
        self.knopf_loeschen = QPushButton("Löschen")
        self.knopf_loeschen.clicked.connect(self.loeschen)
        knoepfe.addWidget(self.knopf_text)
        knoepfe.addWidget(self.knopf_loeschen)
        bl.addLayout(knoepfe)
        sl.addWidget(box)

        box, bl = karte()
        bl.setContentsMargins(14, 12, 14, 12)
        t = QLabel("Beste Ideen")
        t.setObjectName("Unterabschnitt")
        t.setStyleSheet("margin-top: 0px;")
        bl.addWidget(t)
        self.beste_text = QLabel()
        self.beste_text.setWordWrap(True)
        self.beste_text.setTextFormat(Qt.PlainText)
        bl.addWidget(self.beste_text)
        sl.addWidget(box)

        t = QLabel("Regeln")
        t.setObjectName("Unterabschnitt")
        sl.addWidget(t)
        self.regeln = QLabel("\n".join(f"{i}. {r}" for i, r in enumerate(kreativ.REGELN_BRAINSTORMING, 1)))
        self.regeln.setObjectName("Klein")
        self.regeln.setWordWrap(True)
        sl.addWidget(self.regeln)
        box, bl = karte()
        bl.setContentsMargins(14, 12, 14, 12)
        t = QLabel("Zeit zum Sammeln")
        t.setObjectName("Unterabschnitt")
        t.setStyleSheet("margin-top: 0px;")
        bl.addWidget(t)
        zeit = QHBoxLayout()
        self.uhr = QLabel()
        self.uhr.setStyleSheet("font-size: 26px; font-weight: 700;")
        zeit.addWidget(self.uhr, 1)
        self.knopf_uhr = QPushButton("Start")
        self.knopf_uhr.clicked.connect(self.zeit_start_stopp)
        zeit.addWidget(self.knopf_uhr)
        self.knopf_uhr_zurueck = QPushButton("↺")
        self.knopf_uhr_zurueck.setToolTip(f"Zeit auf {ZEIT_MINUTEN}:00 zurücksetzen")
        self.knopf_uhr_zurueck.clicked.connect(self.zeit_zuruecksetzen)
        zeit.addWidget(self.knopf_uhr_zurueck)
        bl.addLayout(zeit)
        sl.addWidget(box)
        self.zeitgeber = QTimer(self)
        self.zeitgeber.setInterval(1000)
        self.zeitgeber.timeout.connect(self._tick)

        sl.addStretch(1)

        rechts = scrollbar(seite)
        rechts.setFixedWidth(276)
        rechts.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        lay.addWidget(rechts)

        self._uhr_zeigen()
        self.setze(None, None)

    # ================================================================ Schnittstelle
    def setze(self, projekt: Projekt | None, sitzung: dict | None) -> None:
        neu = (sitzung or {}).get("id") != (self.sitzung or {}).get("id")
        self.projekt = projekt if sitzung else None
        self.sitzung = sitzung if projekt else None
        if neu:
            self._auswahl_id = None
        self.setEnabled(self.sitzung is not None)
        self.laden()

    def ausgewaehlt(self) -> int | None:
        return self._auswahl_id

    def laden(self) -> None:
        alt_auswahl = self._auswahl_id
        self.eintraege = (self.projekt.kreativ_eintraege(self.sitzung["id"])
                          if self.projekt and self.sitzung else [])
        self._gruppen = [g for g, _ in kreativ.gruppen(self.eintraege) if g]
        self._baut = True
        self.szene.clear()
        self.zettel = {}
        for e in self.eintraege:
            item = ZettelItem(self, e)
            self.szene.addItem(item)
            self.zettel[e["id"]] = item
        if alt_auswahl in self.zettel:
            self.zettel[alt_auswahl].setSelected(True)
        else:
            self._auswahl_id = None
        if not self.eintraege:
            leer = QGraphicsSimpleTextItem("Noch keine Zettel – oben eine Idee eintippen und Enter drücken."
                                           if self.sitzung else "Keine Sitzung gewählt.")
            leer.setFont(_schrift(16))
            leer.setBrush(QApplication.palette().color(QPalette.PlaceholderText))
            leer.setPos(16, 16)
            self.szene.addItem(leer)
        self._baut = False
        self._szene_anpassen()
        self._gruppen_listen()
        self._seite_zeigen()
        if alt_auswahl != self._auswahl_id:
            self.auswahl_geaendert.emit()

    # ================================================================ Aktionen (auch für Tests)
    def zettel_hinzufuegen(self, text: str, gruppe: str = "") -> int | None:
        if not self._bereit():
            return None
        e = self._tu(self.projekt.kreativ_eintrag_neu, self.sitzung["id"], text, gruppe=gruppe.strip())
        if e is None:
            return None
        self._auswahl_id = e["id"]
        self.laden()
        self.zettel[e["id"]].ensureVisible()
        self.auswahl_geaendert.emit()
        self.geaendert.emit()
        return e["id"]

    def waehle(self, eintrag_id: int | None) -> None:
        self.szene.clearSelection()
        if eintrag_id in self.zettel:
            self.zettel[eintrag_id].setSelected(True)
            self.zettel[eintrag_id].ensureVisible()

    def punkt(self, delta: int) -> None:
        if self._auswahl_id is None:
            self.meldung.emit("Bitte zuerst einen Zettel anklicken.", True)
            return
        e = self._tu(self.projekt.kreativ_punkt, self._auswahl_id, delta)
        if e is not None:
            self._eintrag_aktualisieren(e)

    def gruppe_setzen(self, name: str) -> None:
        if self._auswahl_id is None:
            return
        name = name.strip()
        if name == OHNE_GRUPPE:
            name = ""
        if self.zettel[self._auswahl_id].eintrag.get("gruppe", "") == name:
            return
        if self._tu(self.projekt.kreativ_eintrag_aendern, self._auswahl_id, gruppe=name) is not None:
            self.laden()
            self.geaendert.emit()

    def text_setzen(self, text: str, eintrag_id: int | None = None) -> None:
        eid = eintrag_id if eintrag_id is not None else self._auswahl_id
        if eid is None or eid not in self.zettel:
            return
        e = self._tu(self.projekt.kreativ_eintrag_aendern, eid, text=text)
        if e is not None:
            self._eintrag_aktualisieren(e)

    def text_bearbeiten(self, eintrag_id: int) -> None:
        """Text eines Zettels im Dialog ändern (Doppelklick / Enter / Knopf)."""
        if eintrag_id not in self.zettel:
            return
        self.waehle(eintrag_id)
        alt = self.zettel[eintrag_id].eintrag["text"]
        text, ok = QInputDialog.getMultiLineText(self, "Zettel ändern", "Text des Zettels:", alt)
        if ok and text.strip() != alt:
            self.text_setzen(text, eintrag_id)

    def loeschen(self) -> None:
        if self._auswahl_id is None:
            return
        try:
            self.projekt.kreativ_eintrag_loeschen(self._auswahl_id)
        except ProjektFehler as exc:
            self.meldung.emit(str(exc), True)
            self.laden()
            return
        self._auswahl_id = None
        self.laden()
        self.auswahl_geaendert.emit()
        self.geaendert.emit()
        self.meldung.emit("Zettel gelöscht.", False)

    def nach_gruppen_ordnen(self) -> None:
        if not self._bereit() or not self.eintraege:
            return
        try:
            for spalte, (_, liste) in enumerate(kreativ.gruppen(self.eintraege)):
                for zeile, e in enumerate(liste):
                    self.projekt.kreativ_eintrag_aendern(e["id"], x=spalte * (BREITE + ABSTAND_X),
                                                         y=zeile * (HOEHE + ABSTAND_Y))
        except ProjektFehler as exc:
            self.meldung.emit(str(exc), True)
        self.laden()
        self.ansicht.ensureVisible(0, 0, 1, 1)
        self.geaendert.emit()
        self.meldung.emit("Zettel nach Gruppen geordnet.", False)

    def lagen_speichern(self) -> None:
        """Nach dem Verschieben: geänderte Lagen ins Projekt schreiben (ohne die Pinnwand neu aufzubauen)."""
        if not self._bereit():
            return
        geaendert = False
        for item in self.zettel.values():
            x, y = round(item.pos().x(), 1), round(item.pos().y(), 1)
            if (item.eintrag.get("x"), item.eintrag.get("y")) != (x, y):
                e = self._tu(self.projekt.kreativ_eintrag_aendern, item.id, x=x, y=y)
                if e is not None:
                    item.eintrag = e
                    geaendert = True
        if geaendert:
            self.eintraege = [z.eintrag for z in self.zettel.values()]
            self._szene_anpassen()
            self.geaendert.emit()

    # ================================================================ Zeitgeber
    def zeit_start_stopp(self) -> None:
        if self.zeitgeber.isActive():
            self.zeitgeber.stop()
        else:
            if self._rest <= 0:
                self._rest = ZEIT_MINUTEN * 60
            self.zeitgeber.start()
        self._uhr_zeigen()

    def zeit_zuruecksetzen(self) -> None:
        self.zeitgeber.stop()
        self._rest = ZEIT_MINUTEN * 60
        self._uhr_zeigen()

    def _tick(self) -> None:
        self._rest = max(0, self._rest - 1)
        if self._rest == 0:
            self.zeitgeber.stop()
            QApplication.beep()
            self.meldung.emit("Die Zeit ist um – jetzt die Zettel ordnen und mit Punkten bewerten.", False)
        self._uhr_zeigen()

    def _uhr_zeigen(self) -> None:
        self.uhr.setText(f"{self._rest // 60:02d}:{self._rest % 60:02d}")
        self.knopf_uhr.setText("Stopp" if self.zeitgeber.isActive() else "Start")

    # ================================================================ Farben
    def farben(self, gruppe: str) -> tuple[QColor, QColor, QColor, QColor, QColor]:
        """(Hintergrund, Rand, Text, Nebentext, Klebepunkt) für einen Zettel dieser Gruppe."""
        dunkel = _dunkel()
        gruppe = (gruppe or "").strip()
        if gruppe in self._gruppen:
            hg = QColor(PALETTE[self._gruppen.index(gruppe) % len(PALETTE)][dunkel])
        else:
            hg = QColor(NEUTRAL[dunkel])
        if dunkel:
            return hg, hg.lighter(135), QColor("#F2F3F5"), QColor("#D0D4DA"), QColor("#FF8A80")
        return hg, hg.darker(125), QColor("#1B1F24"), QColor("#4A525C"), QColor("#D32F2F")

    # ================================================================ intern
    def nach_vorne(self, item: ZettelItem) -> None:
        self._z += 1
        item.setZValue(self._z)

    def _bereit(self) -> bool:
        return self.projekt is not None and self.sitzung is not None

    def _tu(self, funktion, *args, **kwargs):
        try:
            return funktion(*args, **kwargs)
        except ProjektFehler as exc:
            self.meldung.emit(str(exc), True)
            return None

    def _eingabe_hinzufuegen(self) -> None:
        text = self.eingabe.text().strip()
        if not text:
            self.eingabe.setFocus()
            return
        if self.zettel_hinzufuegen(text, self.gruppe_eingabe.currentText()) is not None:
            self.eingabe.clear()
        self.eingabe.setFocus()

    def _eintrag_aktualisieren(self, e: dict) -> None:
        self.zettel[e["id"]].neu_setzen(e)
        self.eintraege = [e if x["id"] == e["id"] else x for x in self.eintraege]
        self._seite_zeigen()
        self.geaendert.emit()

    def _auswahl_wechsel(self) -> None:
        if self._baut:
            return
        gewaehlt = [i for i in self.szene.selectedItems() if isinstance(i, ZettelItem)]
        neu = gewaehlt[0].id if gewaehlt else None
        if neu != self._auswahl_id:
            self._auswahl_id = neu
            self._seite_zeigen()
            self.auswahl_geaendert.emit()

    def _szene_anpassen(self) -> None:
        rahmen = self.szene.itemsBoundingRect().united(QRectF(0, 0, 10, 10))
        self.szene.setSceneRect(QRectF(-12, -12, rahmen.right() + 24, rahmen.bottom() + HOEHE + 24))
        pal = QApplication.palette()
        self.szene.setBackgroundBrush(QBrush(pal.color(QPalette.AlternateBase)))

    def _gruppen_listen(self) -> None:
        for box, mit_ohne in ((self.gruppe_eingabe, False), (self.gruppe_wahl, True)):
            text = box.currentText()
            box.blockSignals(True)
            box.clear()
            if mit_ohne:
                box.addItem(OHNE_GRUPPE)
            box.addItems(self._gruppen)
            box.setEditText(text if not mit_ohne else "")
            box.blockSignals(False)

    def _seite_zeigen(self) -> None:
        item = self.zettel.get(self._auswahl_id)
        hat = item is not None
        for w in (self.knopf_plus, self.knopf_minus, self.gruppe_wahl, self.knopf_text, self.knopf_loeschen):
            w.setEnabled(hat)
        if hat:
            e = item.eintrag
            text = e["text"] if len(e["text"]) <= 60 else e["text"][:57].rstrip() + " …"
            self.auswahl_text.setText(f"„{text}“\n● {e.get('punkte') or 0} Punkte")
            self.auswahl_text.setObjectName("")
            self.gruppe_wahl.blockSignals(True)
            self.gruppe_wahl.setEditText(e.get("gruppe") or OHNE_GRUPPE)
            self.gruppe_wahl.blockSignals(False)
        else:
            self.auswahl_text.setText("Einen Zettel anklicken, um ihn zu bewerten, zu gruppieren oder zu ändern.")
            self.auswahl_text.setObjectName("Klein")
            self.gruppe_wahl.blockSignals(True)
            self.gruppe_wahl.setEditText("")
            self.gruppe_wahl.blockSignals(False)
        self.auswahl_text.style().unpolish(self.auswahl_text)
        self.auswahl_text.style().polish(self.auswahl_text)
        top = kreativ.beste(self.eintraege, 3)
        if top:
            self.beste_text.setText("\n".join(
                f"● {e['punkte']}   {e['text'] if len(e['text']) <= 50 else e['text'][:47].rstrip() + ' …'}"
                for e in top))
        else:
            self.beste_text.setText("Noch keine Punkte vergeben. Jede Person klebt z. B. 3 Punkte "
                                    "auf ihre Favoriten.")
        self.knopf_ordnen.setEnabled(bool(self.eintraege))

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == event.Type.PaletteChange:
            self._szene_anpassen()
            self.szene.update()
