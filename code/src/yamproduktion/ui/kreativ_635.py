"""Methode 6-3-5 als Formular (K2): je Blatt eine Tabelle Runden × 3 Ideen, mit Rundentimer."""
from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QHBoxLayout, QHeaderView, QLabel, QPlainTextEdit, QProgressBar, QPushButton,
    QStackedWidget, QStyledItemDelegate, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .. import kreativ
from ..modell import Projekt, ProjektFehler

HILFE = ("Jede Person beginnt mit einem eigenen Blatt, schreibt in 5 Minuten 3 Ideen in die oberste freie Zeile "
         "und gibt das Blatt weiter. Die Ideen der Vorgänger dürfen aufgegriffen und weiterentwickelt werden.")
_ID = Qt.UserRole


class _FeldEditor(QStyledItemDelegate):
    """Mehrzeiliges Eingabefeld in der Zelle: Enter speichert, Umschalt+Enter macht eine neue Zeile."""

    def createEditor(self, parent, option, index):
        e = QPlainTextEdit(parent)
        e.setTabChangesFocus(True)
        e.setFrameShape(QPlainTextEdit.NoFrame)
        e.installEventFilter(self)
        return e

    def setEditorData(self, editor, index):
        editor.setPlainText(index.data(Qt.EditRole) or "")
        editor.moveCursor(editor.textCursor().MoveOperation.End)

    def setModelData(self, editor, model, index):
        model.setData(index, editor.toPlainText().strip(), Qt.EditRole)

    def eventFilter(self, editor, event):
        if (event.type() == QEvent.KeyPress and event.key() in (Qt.Key_Return, Qt.Key_Enter)
                and not event.modifiers() & Qt.ShiftModifier):
            self.commitData.emit(editor)
            self.closeEditor.emit(editor, QStyledItemDelegate.NoHint)
            return True
        return super().eventFilter(editor, event)


class Formular635Ansicht(QWidget):
    meldung = Signal(str, bool)
    geaendert = Signal()
    auswahl_geaendert = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.projekt: Projekt | None = None
        self.sitzung: dict | None = None
        self.n = 6
        self.blatt = 1
        self._laedt = False
        self._letzte_auswahl: int | None = None
        self._rest = kreativ.MINUTEN_635 * 60

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        # --- Kopfzeile 1: Blattwahl + Timer
        kopf = QHBoxLayout()
        kopf.addWidget(QLabel("Blatt:"))
        self._blatt_box = QHBoxLayout()
        self._blatt_box.setSpacing(4)
        kopf.addLayout(self._blatt_box)
        self.blatt_gruppe = QButtonGroup(self)
        self.blatt_gruppe.setExclusive(True)
        self.blatt_gruppe.idClicked.connect(self.zeige_blatt)
        self.blatt_knoepfe: list[QPushButton] = []
        kopf.addStretch(1)
        self.uhr = QLabel(self._uhrtext())
        self.uhr.setObjectName("Gross")
        self.uhr.setMinimumWidth(96)
        self.uhr.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.uhr.setToolTip("Zeit für die aktuelle Runde")
        kopf.addWidget(self.uhr)
        self.start_knopf = QPushButton("Start")
        self.start_knopf.setToolTip("Rundentimer starten oder anhalten")
        self.start_knopf.clicked.connect(self.timer_umschalten)
        kopf.addWidget(self.start_knopf)
        self.zurueck_knopf = QPushButton("Zurück")
        self.zurueck_knopf.setToolTip(f"Timer wieder auf {kreativ.MINUTEN_635}:00 stellen")
        self.zurueck_knopf.clicked.connect(self.timer_zuruecksetzen)
        kopf.addWidget(self.zurueck_knopf)
        lay.addLayout(kopf)

        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._tick)

        # --- Kopfzeile 2: wer schreibt, Fortschritt, Sprung
        zeile = QHBoxLayout()
        self.schreiber_text = QLabel("")
        self.schreiber_text.setObjectName("MarkeBlau")
        zeile.addWidget(self.schreiber_text)
        zeile.addStretch(1)
        self.fortschritt_text = QLabel("")
        zeile.addWidget(self.fortschritt_text)
        self.fortschritt = QProgressBar()
        self.fortschritt.setTextVisible(False)
        self.fortschritt.setFixedWidth(160)
        zeile.addWidget(self.fortschritt)
        self.liste_knopf = QPushButton("Alle Ideen als Liste")
        self.liste_knopf.setCheckable(True)
        self.liste_knopf.setObjectName("Skizze")
        self.liste_knopf.toggled.connect(self.liste_zeigen)
        zeile.addWidget(self.liste_knopf)
        self.frei_knopf = QPushButton("Nächste freie Stelle")
        self.frei_knopf.setObjectName("Haupt")
        self.frei_knopf.clicked.connect(self.naechste_freie)
        zeile.addWidget(self.frei_knopf)
        lay.addLayout(zeile)

        hilfe = QLabel(HILFE + "  Enter speichert, Umschalt+Enter beginnt eine neue Zeile, Entf leert das Feld.")
        hilfe.setObjectName("Klein")
        hilfe.setWordWrap(True)
        lay.addWidget(hilfe)

        # --- Formular eines Blatts
        self.stapel = QStackedWidget()
        self.tabelle = QTableWidget(0, kreativ.IDEEN_JE_RUNDE)
        self.tabelle.setHorizontalHeaderLabels([f"Idee {s}" for s in range(1, kreativ.IDEEN_JE_RUNDE + 1)])
        self.tabelle.setItemDelegate(_FeldEditor(self.tabelle))
        self.tabelle.setWordWrap(True)
        self.tabelle.setStyleSheet("QTableWidget::item { padding: 4px 8px; }")
        self.tabelle.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tabelle.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.tabelle.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed
                                     | QAbstractItemView.AnyKeyPressed | QAbstractItemView.SelectedClicked)
        self.tabelle.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        vh = self.tabelle.verticalHeader()
        vh.setSectionResizeMode(QHeaderView.Fixed)
        vh.setDefaultSectionSize(86)
        vh.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.tabelle.itemChanged.connect(self._zelle_geaendert)
        self.tabelle.currentCellChanged.connect(lambda *_: self._auswahl_pruefen())
        QShortcut(QKeySequence.Delete, self.tabelle, self._feld_leeren, context=Qt.WidgetShortcut)
        QShortcut(QKeySequence(Qt.Key_Backspace), self.tabelle, self._feld_leeren, context=Qt.WidgetShortcut)
        self.stapel.addWidget(self.tabelle)

        self.liste = QTableWidget(0, 3)
        self.liste.setHorizontalHeaderLabels(["Blatt", "Runde · Person", "Idee"])
        self.liste.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.liste.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.liste.setSelectionMode(QAbstractItemView.SingleSelection)
        self.liste.setWordWrap(True)
        self.liste.setStyleSheet("QTableWidget::item { padding: 4px 8px; }")
        self.liste.verticalHeader().hide()
        lh = self.liste.horizontalHeader()
        lh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        lh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        lh.setSectionResizeMode(2, QHeaderView.Stretch)
        self.liste.currentCellChanged.connect(lambda *_: self._auswahl_pruefen())
        self.liste.cellDoubleClicked.connect(self._aus_liste_springen)
        self.stapel.addWidget(self.liste)
        lay.addWidget(self.stapel, 1)

        self._aktiv_setzen(False)

    # ------------------------------------------------------------ Schnittstelle
    def setze(self, projekt: Projekt | None, sitzung: dict | None) -> None:
        neu = (sitzung or {}).get("id") != (self.sitzung or {}).get("id")
        self.projekt = projekt
        self.sitzung = sitzung if projekt and sitzung and sitzung.get("methode") == "635" else None
        if neu:
            self.blatt = 1
            self.timer_zuruecksetzen()
        self.n = int(self.sitzung.get("teilnehmer") or 6) if self.sitzung else 6
        try:
            kreativ.pruefe_teilnehmer(self.n)
        except kreativ.KreativFehler:
            self.n = 6
        self._blattknoepfe_bauen()
        self.laden()

    def laden(self) -> None:
        if not self.sitzung or not self.projekt:
            self._laedt = True
            self.tabelle.setRowCount(0)
            self.liste.setRowCount(0)
            self._laedt = False
            self.schreiber_text.setText("Keine 6-3-5-Sitzung gewählt")
            self.fortschritt_text.setText("")
            self.fortschritt.setValue(0)
            self._aktiv_setzen(False)
            self._auswahl_pruefen()
            return
        self._aktiv_setzen(True)
        self.blatt = min(max(1, self.blatt), self.n)
        try:
            felder = self.projekt.blatt_635(self.sitzung["id"], self.blatt)
        except ProjektFehler as exc:
            self.meldung.emit(str(exc), True)
            return
        zeile, spalte = self.tabelle.currentRow(), self.tabelle.currentColumn()
        self._laedt = True
        self.tabelle.setRowCount(self.n)
        for r in range(1, self.n + 1):
            kopf = QTableWidgetItem(f"Runde {r} · Person {kreativ.schreiber(self.blatt, r, self.n)}")
            kopf.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.tabelle.setVerticalHeaderItem(r - 1, kopf)
            for s in range(1, kreativ.IDEEN_JE_RUNDE + 1):
                e = felder.get((r, s))
                item = QTableWidgetItem(e["text"] if e else "")
                item.setData(_ID, e["id"] if e else None)
                item.setTextAlignment(Qt.AlignLeft | Qt.AlignTop)
                item.setToolTip(e["text"] if e else "Leer – hineinschreiben oder doppelklicken")
                self.tabelle.setItem(r - 1, s - 1, item)
        self._laedt = False
        for i, k in enumerate(self.blatt_knoepfe, start=1):
            k.setChecked(i == self.blatt)
        if 0 <= zeile < self.n and 0 <= spalte < kreativ.IDEEN_JE_RUNDE:
            self.tabelle.setCurrentCell(zeile, spalte)
        self._stand_zeigen()
        if self.liste_knopf.isChecked():
            self._liste_fuellen()
        self._auswahl_pruefen()

    def ausgewaehlt(self) -> int | None:
        if self.stapel.currentWidget() is self.liste:
            item = self.liste.item(self.liste.currentRow(), 0) if self.liste.currentRow() >= 0 else None
        else:
            item = self.tabelle.currentItem()
        return item.data(_ID) if item is not None else None

    # ------------------------------------------------------------ öffentliche Bedienung (auch für Tests)
    def zeige_blatt(self, nr: int) -> None:
        if not 1 <= nr <= self.n:
            return
        self.blatt = nr
        self.laden()

    def feld_setzen(self, runde: int, spalte: int, text: str) -> None:
        """Feld im aktuellen Blatt füllen (leer = leeren) und sofort speichern."""
        item = self.tabelle.item(runde - 1, spalte - 1)
        if item is None:
            return
        self.tabelle.setCurrentCell(runde - 1, spalte - 1)
        if item.text() == text.strip():
            return
        item.setText(text.strip())        # löst _zelle_geaendert aus

    def waehle_feld(self, runde: int, spalte: int) -> None:
        if self.liste_knopf.isChecked():
            self.liste_knopf.setChecked(False)
        self.tabelle.setCurrentCell(runde - 1, spalte - 1)
        self.tabelle.setFocus()

    def naechste_freie(self) -> tuple[int, int, int] | None:
        """Springt zum ersten leeren Feld der aktuellen Runde; gibt (Blatt, Runde, Spalte) zurück."""
        if not self.sitzung or not self.projekt:
            return None
        eintraege = self.projekt.kreativ_eintraege(self.sitzung["id"])
        stand = kreativ.stand_635(eintraege, self.n)
        if stand["fertig"]:
            self.meldung.emit("Alle Felder sind ausgefüllt – die Runde 6-3-5 ist fertig.", False)
            return None
        gefuellt = {(e["blatt"], e["runde"], e["spalte"]) for e in eintraege if e.get("blatt") and e["text"].strip()}
        r = stand["runde"]
        # zuerst ab dem aktuellen Blatt suchen, dann reihum
        for b in [*range(self.blatt, self.n + 1), *range(1, self.blatt)]:
            for s in range(1, kreativ.IDEEN_JE_RUNDE + 1):
                if (b, r, s) not in gefuellt:
                    if b != self.blatt:
                        self.zeige_blatt(b)
                    self.waehle_feld(r, s)
                    return b, r, s
        return None

    def liste_zeigen(self, an: bool) -> None:
        if self.liste_knopf.isChecked() != an:
            self.liste_knopf.setChecked(an)      # ruft uns erneut auf
            return
        if an:
            self._liste_fuellen()
        self.stapel.setCurrentWidget(self.liste if an else self.tabelle)
        self._auswahl_pruefen()

    # ------------------------------------------------------------ Timer
    def timer_umschalten(self) -> None:
        if self.timer.isActive():
            self.timer.stop()
            self.start_knopf.setText("Weiter")
        else:
            if self._rest <= 0:
                self._rest = kreativ.MINUTEN_635 * 60
                self.uhr.setText(self._uhrtext())
            self.timer.start()
            self.start_knopf.setText("Pause")

    def timer_zuruecksetzen(self) -> None:
        self.timer.stop()
        self._rest = kreativ.MINUTEN_635 * 60
        self.uhr.setText(self._uhrtext())
        self.start_knopf.setText("Start")

    def _tick(self) -> None:
        self._rest = max(0, self._rest - 1)
        self.uhr.setText(self._uhrtext())
        if self._rest == 0:
            self.timer.stop()
            self.start_knopf.setText("Start")
            self.meldung.emit("Zeit um – Blatt weitergeben.", False)

    def _uhrtext(self) -> str:
        return f"{self._rest // 60}:{self._rest % 60:02d}"

    # ------------------------------------------------------------ intern
    def _aktiv_setzen(self, an: bool) -> None:
        for w in (self.tabelle, self.liste, self.frei_knopf, self.liste_knopf, self.start_knopf, self.zurueck_knopf):
            w.setEnabled(an)

    def _blattknoepfe_bauen(self) -> None:
        if len(self.blatt_knoepfe) == self.n:
            return
        for k in self.blatt_knoepfe:
            self.blatt_gruppe.removeButton(k)
            k.setParent(None)
            k.deleteLater()
        self.blatt_knoepfe = []
        for i in range(1, self.n + 1):
            k = QPushButton(str(i))
            k.setObjectName("Skizze")
            k.setCheckable(True)
            k.setMinimumWidth(40)
            k.setToolTip(f"Blatt {i} zeigen (beginnt bei Person {i})")
            self.blatt_gruppe.addButton(k, i)
            self._blatt_box.addWidget(k)
            self.blatt_knoepfe.append(k)

    def _stand_zeigen(self) -> None:
        stand = kreativ.stand_635(self.projekt.kreativ_eintraege(self.sitzung["id"]), self.n)
        r = stand["runde"]
        if stand["fertig"]:
            self.schreiber_text.setText(f"Blatt {self.blatt}: alle Runden fertig")
        else:
            self.schreiber_text.setText(f"Runde {r}: Person {kreativ.schreiber(self.blatt, r, self.n)} "
                                        f"schreibt auf dieses Blatt")
        self.fortschritt_text.setText(f"{stand['gefuellt']} von {stand['gesamt']} Feldern")
        self.fortschritt.setMaximum(stand["gesamt"])
        self.fortschritt.setValue(stand["gefuellt"])
        for i in range(self.n):
            kopf = self.tabelle.verticalHeaderItem(i)
            if kopf is not None:
                jetzt = i + 1 == r and not stand["fertig"]
                kopf.setText(("▸ " if jetzt else "   ") + f"Runde {i + 1} · Person "
                             f"{kreativ.schreiber(self.blatt, i + 1, self.n)}")
                kopf.setToolTip("Diese Runde ist gerade dran" if jetzt else "")

    def _zelle_geaendert(self, item: QTableWidgetItem) -> None:
        if self._laedt or not self.sitzung or not self.projekt:
            return
        runde, spalte = item.row() + 1, item.column() + 1
        try:
            e = self.projekt.feld_635_setzen(self.sitzung["id"], self.blatt, runde, spalte, item.text())
        except ProjektFehler as exc:
            self.meldung.emit(str(exc), True)
            self.laden()
            return
        self._laedt = True
        item.setData(_ID, e["id"] if e else None)
        if e and item.text() != e["text"]:
            item.setText(e["text"])
        item.setToolTip(e["text"] if e else "Leer – hineinschreiben oder doppelklicken")
        self._laedt = False
        self._stand_zeigen()
        self.geaendert.emit()
        self._auswahl_pruefen()

    def _feld_leeren(self) -> None:
        item = self.tabelle.currentItem()
        if item is not None and item.text():
            item.setText("")

    def _liste_fuellen(self) -> None:
        self.liste.setRowCount(0)
        if not self.sitzung or not self.projekt:
            return
        eintraege = sorted((e for e in self.projekt.kreativ_eintraege(self.sitzung["id"]) if e.get("blatt")),
                           key=lambda e: (e["blatt"], e["runde"], e["spalte"]))
        self.liste.setRowCount(len(eintraege))
        for z, e in enumerate(eintraege):
            werte = (f"Blatt {e['blatt']}",
                     f"Runde {e['runde']} · Person {kreativ.schreiber(e['blatt'], e['runde'], self.n)}", e["text"])
            for s, w in enumerate(werte):
                item = QTableWidgetItem(w)
                item.setData(_ID, e["id"])
                item.setData(Qt.UserRole + 1, (e["blatt"], e["runde"], e["spalte"]))
                item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                self.liste.setItem(z, s, item)
        self.liste.resizeRowsToContents()

    def _aus_liste_springen(self, zeile: int, _spalte: int) -> None:
        item = self.liste.item(zeile, 0)
        if item is None:
            return
        b, r, s = item.data(Qt.UserRole + 1)
        self.liste_knopf.setChecked(False)
        self.zeige_blatt(b)
        self.waehle_feld(r, s)

    def _auswahl_pruefen(self) -> None:
        jetzt = self.ausgewaehlt()
        if jetzt != self._letzte_auswahl:
            self._letzte_auswahl = jetzt
            self.auswahl_geaendert.emit()
