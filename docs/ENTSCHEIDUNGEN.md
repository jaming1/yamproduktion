# Entscheidungen – YamProduktion

| Nr | Datum | Entscheidung | Begründung | Status |
|----|-------|--------------|------------|--------|
| E1 | 04.11.2026 | Nur macOS, Desktop-Programm | Wunsch Yamine | ✅ |
| E2 | 04.11.2026 | Eigenes CAD auf bewährtem Geometriekern (Open CASCADE) | Wunsch Yamine; ein eigener Kern würde Jahre dauern | ✅ |
| E3 | 04.11.2026 | Erstes Produkt: Mini-Windkraftanlage 5–10 kW, wird real gebaut | Wunsch Yamine | ✅ |
| E4 | 04.11.2026 | Technik-Stapel (siehe unten) | siehe unten | ✅ |
| E5 | 04.11.2026 | TRIZ-Matrix aus geprüfter Abschrift (triz-solver v0.4.0, 2-von-3-Abgleich), Trennungsprinzipien aus MATRIZ (CC BY 4.0) | Keine erfundenen Werte (N6); Quelle im Programm sichtbar; Stichprobe mit eigenem TRIZ-Buch empfohlen | ✅ |
| E6 | 04.11.2026 | Nutzwert = Σ(Gewicht · Punkte) / Σ Gewicht auf Skala 0–10 | Vergleichbar unabhängig von der Zahl der Kriterien; Auswahl braucht immer eine Begründung | ✅ |
| E7 | 04.11.2026 | Lastannahmen nach dem vereinfachten Lastmodell der IEC 61400-2; Gleichungen aus NREL-Berichten, die die Norm zitieren; E, F und Klassenwerte als unbelegt markiert | Normtext liegt nicht vor; Sicherheit geht vor: nichts Unbelegtes ohne Kennzeichnung | ✅ |
| E8 | 04.11.2026 | Ertrag mit vereinfachter Leistungskurve (konstantes cp) bis eine gemessene Kurve vorliegt | Für Vorauslegung ausreichend, klar als Annahme gekennzeichnet | ✅ |
| E9 | 04.11.2026 | Maschinenelemente mit vereinfachten Normverfahren (DIN 743, ISO 281, VDI 2230, DIN 6892, DIN 7190, EN 1993-1-8, DIN 3990); Beiwerte ohne vorliegenden Normtext als unbelegt markiert | Vorauslegung jetzt möglich; vor dem Bau Abgleich mit Literatur-Rechenbeispielen und volle Nachweise | ✅ |
| E10 | 04.11.2026 | Getriebe-Eingaben beziehen sich auf die langsame (Rotor-)Welle; Ritzel bzw. Sonne laufen schnell | So passt die Übernahme aus dem Antriebsstrang ohne Umrechnung durch den Nutzer | ✅ |
| E11 | 04.11.2026 | Formeleditor (S7, Soll) auf einen späteren Meilenstein verschoben | Erst alle Muss-Berechnungen; der Editor nutzt dann denselben Rechenrahmen | ✅ |
| E12 | 04.11.2026 | Geometriekern direkt über OCP (Paket `cadquery-ocp`), ohne CadQuery-Paket | CadQuery zieht viele weitere große Pakete nach; für Vorlagen-Teile reicht eine eigene dünne Schicht (`cad/geometrie.py`). Ergänzt E4 | ✅ |
| E13 | 04.11.2026 | 3D-Ansicht ohne OpenGL: schattierte Dreiecke mit QPainter, nach Tiefe sortiert | Läuft auf jedem Mac und in automatischen Tests mit Screenshots; reicht für Einzelteile. Für große Baugruppen (MS8) wird eine OpenGL-Ansicht nachgerüstet | ✅ |
| E14 | 04.11.2026 | Bauteile speichern nur Vorlage und Parameter, die Geometrie wird bei Bedarf neu erzeugt | Projektdatei bleibt klein; jedes Teil ist jederzeit aus den Berechnungswerten reproduzierbar | ✅ |
| E15 | 04.11.2026 | Eigener Skizzen-Löser (Gauß-Newton mit numpy) statt SolveSpace | `python-solvespace` hat keine Mac-Pakete für Python 3.12/3.13 und steht unter GPL. Der eigene Löser (≈200 Zeilen) deckt alle Bedingungen ab, liefert verlässlich die offenen Freiheitsgrade und hält bei unterbestimmten Skizzen die Form | ✅ |
| E16 | 04.11.2026 | Freie Teile speichern Parameter-Tabelle und Feature-Baum als JSON (Vorlage „frei“), keine Geometrie | Wie E14: klein, reproduzierbar; Werte aus Berechnungen (`ber(...)`) werden verknüpft und lösen „neu prüfen“ aus | ✅ |

---

## E4 – Technik-Stapel

| Baustein | Wahl | Warum | Alternativen (verworfen) |
|----------|------|-------|--------------------------|
| Sprache | **Python 3.12** | Stärkstes Ökosystem für Ingenieurrechnungen (NumPy, SciPy), gute Anbindung an Open CASCADE, leicht lesbar und prüfbar | Swift (kein CAD-Kern-Ökosystem), C++ (viel aufwendiger), Web/Electron (schwer, Kern nur über WebAssembly) |
| Oberfläche | **PySide6 (Qt 6)** | Echte Mac-Desktop-App, bewährt für CAD-Programme (FreeCAD nutzt Qt), 3D-Ansicht direkt einbettbar | Tkinter (zu schwach für CAD), Electron (schwer) |
| Geometriekern | **Open CASCADE über OCP / CadQuery** | Kostenlos, industrieerprobt, STEP-Import/-Export, Bohrungen, Verrundungen, Schnitte; per `pip` für Apple Silicon installierbar; CadQuery bringt parametrisches Modellieren gleich mit | pythonOCC (braucht Conda; Anaconda macht auf dem Mac oft Probleme mit SQLite), eigener Kern |
| Skizzen-Bedingungen | **python-solvespace** (Constraint-Solver von SolveSpace) | Kleiner, bewährter Löser für Bemaßungen und Bedingungen in 2D-Skizzen | Eigenbau (fehleranfällig) |
| Einheiten | **Pint** | Jede Zahl mit Einheit, automatische Umrechnung, Fehler bei falschen Einheiten (M6) | Eigenbau |
| Daten | **SQLite** (eine Datei pro Projekt) + Dateien für CAD (STEP) | Lokal, robust, offen lesbar, keine Installation (N10) | Server-Datenbank (unnötig für einen Nutzer) |
| PDF-Protokolle | **ReportLab** | Schlank, keine Abhängigkeit von Browser-Engines | WeasyPrint (mehr Abhängigkeiten) |
| Texterkennung | **OCRmyPDF + Tesseract (Deutsch)** | Kostenlos, offline, macht Scans durchsuchbar | Cloud-OCR (Kosten, Datenschutz, Urheberrecht) |
| Suche | **SQLite FTS5** | Volltextsuche im selben Datenbank-System, schnell, offline | Elasticsearch (viel zu groß) |
| KI-Assistent (optional, S19) | Wird in MS14 entschieden (lokales Modell oder Claude-API mit Auszügen nur auf Anfrage) | Datenschutz und Urheberrecht zuerst prüfen | – |
| Tests | **pytest** + Screenshot-Tests der Oberfläche (hell/dunkel) | Rechenbeispiele aus der Literatur als feste Testfälle (N5) | – |
| Auslieferung | **PyInstaller → .app** + Startskript `start.command` für die Entwicklung | Doppelklick-Start auf dem Mac | – |

⚠️ Ressourcen-Hinweis: Der Geometriekern (OCP) ist einige 100 MB groß. Das ist einmalig, kostenlos und für das eigene CAD unverzichtbar. Alles andere ist klein. Es gibt keine laufenden Kosten.
