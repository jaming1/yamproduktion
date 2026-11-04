"""Seitenpanel „Rückverfolgung“: wovon ein Objekt abhängt, worauf es wirkt, und sein Verlauf (M3, M4)."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from ..berechnungen import FELD_NAMEN
from ..modell import NEU_PRUEFEN, TYP_NAME, Projekt


def status_text(status: str) -> str:
    """Status mit Symbol, damit er auch ohne Farbe erkennbar ist."""
    return {"Entwurf": "✎ Entwurf", "geprüft": "✓ geprüft", "freigegeben": "★ freigegeben",
            NEU_PRUEFEN: "⚠ neu prüfen"}.get(status, status)


class RueckverfolgungPanel(QFrame):
    """Einklappbares Detailpanel rechts neben einer Tabelle."""
    gehe_zu = Signal(str, int)   # typ, id

    def __init__(self):
        super().__init__()
        self.setObjectName("Detailpanel")
        self.setMinimumWidth(320)
        self.setMaximumWidth(380)
        aussen = QVBoxLayout(self)
        aussen.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        self.inhalt = QWidget()
        self.lay = QVBoxLayout(self.inhalt)
        self.lay.setContentsMargins(18, 16, 18, 16)
        self.lay.setSpacing(8)
        scroll.setWidget(self.inhalt)
        aussen.addWidget(scroll)
        self.leer()

    def _leeren(self):
        while self.lay.count():
            eintrag = self.lay.takeAt(0)
            w = eintrag.widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()

    def _label(self, text: str, name: str = "", wrap: bool = True) -> QLabel:
        lbl = QLabel(text)
        if name:
            lbl.setObjectName(name)
        lbl.setWordWrap(wrap)
        lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.lay.addWidget(lbl)
        return lbl

    def leer(self):
        self._leeren()
        self._label("Rückverfolgung", "Abschnitt")
        self._label("Eine Zeile auswählen, um zu sehen, wovon sie abhängt, worauf sie wirkt und was sich geändert hat.",
                    "Klein")
        self.lay.addStretch()

    def zeigen(self, projekt: Projekt, typ: str, id_: int, nr: str, titel: str, status: str, version: int = 1):
        self._leeren()
        self._label(f"{nr} · {TYP_NAME[typ]}", "Abschnitt")
        self._label(titel)
        self._label(f"{status_text(status)}  ·  Version {version}", "Fehler" if status == NEU_PRUEFEN else "Klein")

        self._label("Hängt ab von", "Unterabschnitt")
        quellen = projekt.haengt_ab_von(typ, id_)
        if not quellen:
            self._label("– nichts –", "Klein")
        for q in quellen:
            self._verweis(q)

        self._label("Wirkt auf", "Unterabschnitt")
        ziele = projekt.wirkt_auf(typ, id_, rekursiv=True)
        if not ziele:
            self._label("– nichts –", "Klein")
        for z in ziele:
            self._verweis(z)

        self._label("Verlauf", "Unterabschnitt")
        for v in projekt.verlauf(typ, id_)[:30]:
            datum = v.zeit.replace("T", " ")[:16]
            self._label(f"<span style='opacity:0.7'>{datum}</span><br>{v.text}")
        self.lay.addStretch()

    def _verweis(self, b):
        feld = f" → {FELD_NAMEN.get(b.feld, b.feld)}" if b.feld else ""
        titel = b.titel if len(b.titel) <= 24 else b.titel[:22] + " …"
        knopf = QPushButton(f"{b.nr}   {status_text(b.status)}\n{titel}{feld}")
        knopf.setObjectName("Verweis")
        knopf.setToolTip(f"{b.nr} {b.titel} – zum Objekt springen")
        knopf.clicked.connect(lambda _=False, t=b.typ, i=b.id: self.gehe_zu.emit(t, i))
        self.lay.addWidget(knopf)
