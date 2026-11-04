"""Hell- und Dunkelmodus (N7). 'auto' folgt der macOS-Einstellung."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

FARBEN = {
    "hell": {
        "hintergrund": "#F6F7F9", "flaeche": "#FFFFFF", "seite": "#ECEFF3", "text": "#1B1F24",
        "text2": "#5A6470", "linie": "#D5DAE0", "akzent": "#1F6FB2", "akzent_text": "#FFFFFF",
        "ok": "#1E7B34", "ok_bg": "#E3F4E1", "fehler": "#B3261E", "fehler_bg": "#FBE3E1",
        "warn": "#8A5300", "warn_bg": "#FFF1D6", "blau_bg": "#E1EDF8",
    },
    "dunkel": {
        "hintergrund": "#16191D", "flaeche": "#1F2328", "seite": "#1A1D21", "text": "#E8EAED",
        "text2": "#A0A8B2", "linie": "#353B42", "akzent": "#5AA9E6", "akzent_text": "#0B1520",
        "ok": "#6FD08A", "ok_bg": "#1C3324", "fehler": "#FF8A80", "fehler_bg": "#3A1F1D",
        "warn": "#FFC66B", "warn_bg": "#3A2C12", "blau_bg": "#18304A",
    },
}


def aktuelles_schema(modus: str) -> str:
    if modus in ("hell", "dunkel"):
        return modus
    app = QApplication.instance()
    try:
        if app and app.styleHints().colorScheme() == Qt.ColorScheme.Dark:
            return "dunkel"
    except AttributeError:
        pass
    return "hell"


def anwenden(app: QApplication, modus: str) -> dict:
    schema = aktuelles_schema(modus)
    f = FARBEN[schema]
    app.setStyle("Fusion")
    font = QFont(app.font())
    font.setPointSizeF(13.0)  # entspricht auf dem Mac etwa 16 px
    app.setFont(font)

    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(f["hintergrund"]))
    pal.setColor(QPalette.WindowText, QColor(f["text"]))
    pal.setColor(QPalette.Base, QColor(f["flaeche"]))
    pal.setColor(QPalette.AlternateBase, QColor(f["seite"]))
    pal.setColor(QPalette.Text, QColor(f["text"]))
    pal.setColor(QPalette.Button, QColor(f["flaeche"]))
    pal.setColor(QPalette.ButtonText, QColor(f["text"]))
    pal.setColor(QPalette.Highlight, QColor(f["akzent"]))
    pal.setColor(QPalette.HighlightedText, QColor(f["akzent_text"]))
    pal.setColor(QPalette.ToolTipBase, QColor(f["flaeche"]))
    pal.setColor(QPalette.ToolTipText, QColor(f["text"]))
    pal.setColor(QPalette.PlaceholderText, QColor(f["text2"]))
    app.setPalette(pal)

    app.setStyleSheet(f"""
        QWidget {{ font-size: 16px; }}
        #Seitenleiste {{ background: {f['seite']}; border-right: 1px solid {f['linie']}; }}
        #Seitenleiste QListWidget {{ background: transparent; border: none; font-size: 16px; }}
        #Seitenleiste QListWidget::item {{ padding: 5px 14px; border-radius: 8px; margin: 1px 8px; }}
        #Seitenleiste QListWidget::item:selected {{ background: {f['akzent']}; color: {f['akzent_text']}; }}
        #ProjektName {{ font-size: 15px; color: {f['text2']}; padding: 14px 18px 6px 18px; }}
        QLabel#Titel {{ font-size: 26px; font-weight: 600; }}
        QLabel#Untertitel {{ color: {f['text2']}; }}
        QLabel#Abschnitt {{ font-size: 18px; font-weight: 600; margin-top: 8px; }}
        QPushButton {{ padding: 8px 16px; border: 1px solid {f['linie']}; border-radius: 8px;
                       background: {f['flaeche']}; min-height: 24px; }}
        QPushButton:hover {{ border-color: {f['akzent']}; }}
        QPushButton#Haupt {{ background: {f['akzent']}; color: {f['akzent_text']}; border: none; font-weight: 600;
                             padding: 10px 22px; }}
        QPushButton#Haupt:disabled {{ background: {f['linie']}; color: {f['text2']}; }}
        QPushButton#Werkzeug {{ border: none; background: transparent; padding: 6px 10px; font-size: 18px; }}
        QPushButton#Werkzeug:hover {{ background: {f['seite']}; }}
        QPushButton#Skizze {{ padding: 5px 10px; font-size: 14px; min-height: 20px; }}
        QPushButton#Skizze:checked {{ background: {f['akzent']}; color: {f['akzent_text']}; border-color: {f['akzent']}; }}
        QFrame#Karte {{ background: {f['flaeche']}; border: 1px solid {f['linie']}; border-radius: 12px; }}
        QFrame#Kopfzeile {{ background: {f['flaeche']}; border-bottom: 1px solid {f['linie']}; }}
        QTableWidget {{ background: {f['flaeche']}; border: 1px solid {f['linie']}; border-radius: 8px;
                        gridline-color: {f['linie']}; }}
        QHeaderView::section {{ background: {f['seite']}; padding: 8px; border: none;
                                border-bottom: 1px solid {f['linie']}; font-weight: 600; }}
        QLineEdit, QDoubleSpinBox, QComboBox {{ padding: 6px 8px; border: 1px solid {f['linie']};
                                               border-radius: 6px; background: {f['flaeche']}; min-height: 24px; }}
        QComboBox::drop-down {{ border: none; width: 22px; }}
        QDoubleSpinBox {{ padding-left: 10px; }}
        QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{ width: 22px; border: none; background: transparent; }}
        QLineEdit:focus, QDoubleSpinBox:focus, QComboBox:focus {{ border-color: {f['akzent']}; }}
        QLabel#Ok {{ background: {f['ok_bg']}; color: {f['ok']}; border-radius: 6px; padding: 6px 10px; }}
        QLabel#Fehler {{ background: {f['fehler_bg']}; color: {f['fehler']}; border-radius: 6px; padding: 6px 10px; }}
        QLabel#Gross {{ font-size: 30px; font-weight: 700; color: {f['akzent']}; }}
        QLabel#Klein {{ color: {f['text2']}; font-size: 14px; }}
        QLabel#Unterabschnitt {{ font-weight: 600; margin-top: 10px; color: {f['text2']}; }}
        QFrame#Unterkarte {{ background: {f['hintergrund']}; border: 1px solid {f['linie']}; border-radius: 8px; }}
        QFrame#Detailpanel {{ background: {f['flaeche']}; border: 1px solid {f['linie']}; border-radius: 8px; }}
        QPushButton#Verweis {{ text-align: left; padding: 6px 10px; }}
        QFrame#Warnung {{ background: {f['warn_bg']}; border: 1px solid {f['warn']}; border-radius: 10px; }}
        QFrame#Warnung QLabel {{ color: {f['warn']}; }}
        QLabel#MarkeGrau {{ color: {f['text2']}; font-size: 14px; }}
        QLabel#MarkeBlau {{ color: {f['akzent']}; background: {f['blau_bg']}; border-radius: 6px; padding: 2px 8px; font-size: 14px; }}
        QLabel#MarkeGruen {{ color: {f['ok']}; background: {f['ok_bg']}; border-radius: 6px; padding: 2px 8px; font-size: 14px; }}
        QComboBox#StatusWarnung {{ background: {f['warn_bg']}; color: {f['warn']}; border-color: {f['warn']}; font-weight: 600; }}
        QStatusBar {{ background: {f['seite']}; border-top: 1px solid {f['linie']}; }}
        QScrollArea {{ border: none; background: transparent; }}
    """)
    return f
