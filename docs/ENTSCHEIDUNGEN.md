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
| E17 | 04.11.2026 | Baugruppen speichern nur Einbauten mit Lage-Formeln (JSON); Ausrichtung als „koaxial zu … mit Abstand, umdrehen, Lochkreis“ statt allgemeiner 3D-Zwangsbedingungen | Deckt Wellen-Lager-Naben-Verbände der KWA vollständig ab, ist eindeutig und rechnet sofort. Die QPainter-Ansicht (E13) reicht für die Gondel (≈ 30 Teile) – OpenGL erst, wenn sie zu langsam wird | ✅ |
| E18 | 04.11.2026 | Zeichnungen selbst erzeugen: verdeckte-Kanten-Projektion aus Open CASCADE (HLR), Blatt A3 als Liste aus Linien/Texten → PDF (ReportLab), DXF R12 (selbst geschrieben, Layer je Linienart) und Bildschirm | Keine weitere Abhängigkeit; alle drei Ausgaben zeigen garantiert dasselbe. Bemaßung automatisch (Gesamtmaße, Ø, Absätze, Lochkreise); Funktionsmaße bleiben Aufgabe des Konstrukteurs | ✅ |
| E20 | 04.11.2026 | Arbeitsplan als Vorschlag aus der 3D-Geometrie (Drehteil/Platte/Guss, Absätze, Bohrungen, Nuten) mit Zeiten aus den Schnittdaten-Formeln; jede Zahl von Hand überschreibbar | Spart das Abtippen und macht Kosten früh sichtbar; der Mensch bleibt verantwortlich (Handzeit ✎ hat Vorrang) | ✅ |
| E21 | 04.11.2026 | Stundensätze, Materialpreise und Zukaufpreise je Projekt speichern; Vorgaben sind ausdrücklich Schätzwerte | Echte Sätze und Angebote ersetzen sie ohne Programmänderung; Fremdteile ohne Angebot werden als „Schätzung“ (Eigenkosten + 25 %) gekennzeichnet | ✅ |
| E22 | 04.11.2026 | Montagevorrichtung als eigenes Bauteil (Vorlage „Montageplatte“, in Koordinaten des Grundteils), nicht als Einbau der Baugruppe | Eine Vorrichtung gehört nicht in Stückliste, Masse und Kosten des Produkts; als Bauteil bekommt sie trotzdem Zeichnung, Arbeitsplan und Rückverfolgung (Änderung → Montageplan „neu prüfen“) | ✅ |
| E23 | 04.11.2026 | Anzugsmomente aus der Schraubenberechnung des Projekts nur bei gleichem Gewinde **und** gleicher Festigkeitsklasse; sonst dieselbe Formel (VDI 2230 vereinfacht) für 8.8 als Richtwert mit Hinweis | Ein 10.9-Moment auf einer 8.8-Schraube würde sie überlasten – lieber ein sichtbarer Widerspruch als ein falscher Wert | ✅ |
| E24 | 04.11.2026 | Inbetriebnahme-Checkliste als Momentaufnahme: Sollwerte werden beim Anlegen aus Berechnungen und Montageplänen kopiert und verknüpft, nicht live nachgeführt | Ein Protokoll muss zeigen, wogegen geprüft wurde; ändert sich eine Berechnung, wird die Checkliste „neu prüfen“ und eine neue angelegt | ✅ |
| E25 | 04.11.2026 | Rückmeldungen aus Inbetriebnahme und Betrieb werden Ideen in Phase P1 (ohne Verknüpfung zurück) | Schließt den Kreis zur nächsten Version, ohne dass spätere Änderungen an der Checkliste die Idee wieder „neu prüfen“ setzen | ✅ |
| E26 | 04.11.2026 | FMEA, Risikobeurteilung, Normen-Checkliste und Abweichungsliste als ein gemeinsames Tabellen-Dokument: die Spalten werden einmal beschrieben, Oberfläche und PDF entstehen daraus | Vier Listen mit gleichem Aufbau (Zeilen, Bewertung, Ampel) – eine Seite und eine PDF-Funktion statt vier; neue Spalten an einer Stelle | ✅ |
| E27 | 04.11.2026 | Grenzmaße nach ISO 286 nur für die üblichen Felder (H, F, G, f, g, h, js, k, m, n, p) bis 500 mm hinterlegt, als „Norm, ungeprüft“; andere Passungen von Hand | Deckt Lager-, Naben- und Gleitsitze ab; eine vollständige Normtabelle aus dem Gedächtnis wäre zu fehleranfällig | ✅ |
| E28 | 04.11.2026 | Restrisiko in der Risikobeurteilung zählt erst, wenn die Maßnahme als „umgesetzt“ markiert ist; „erfüllt“ bei Normen setzt nur der Mensch | Eine Vorlage darf keine Sicherheit vortäuschen – geplante Maßnahmen sind noch keine Risikominderung | ✅ |
| E30 | 05.11.2026 | Aufgaben sind Querschnittsobjekte (AU-…): die Phase ist ein Feld der Aufgabe; Anlegen oder Ändern öffnet kein Phasentor, offene Aufgaben verhindern aber die Freigabe ihrer Phase | Eine Aufgabe ist Planung, kein Ergebnis – sie darf eine freigegebene Phase nicht zurücksetzen, aber eine unfertige nicht als fertig durchgehen lassen | ✅ |
| E31 | 05.11.2026 | Fortschritt je Phase = Anteil erledigter Aufgaben und geprüfter/freigegebener Objekte; freigegebene Phase = 100 % | Einfach nachvollziehbar und ohne Schätzung von Aufwänden; Gewichtung nach Aufwand wäre Scheingenauigkeit | ✅ |
| E32 | 05.11.2026 | Kostenposten Plan/Ist im Projekt (Metadaten) statt als eigene Objekte; Plan aus der Kalkulation je Baugruppe wird ersetzt, nicht addiert | Kostenposten brauchen keine Versionen und Rückverfolgung; erneutes Übernehmen nach Preisänderung darf nicht doppelt zählen | ✅ |
| E33 | 05.11.2026 | Bibliothek in eigenem Ordner mit eigener SQLite-Datei (FTS5), getrennt von allen Projekten; Kopie des Scans statt Verweis | Bücher gehören zu Yamine, nicht zu einem Projekt; urheberrechtlich geschützte Scans dürfen nie in Projektdatei, Doku-PDF oder Export gelangen (M52); Kopie bleibt gültig, auch wenn das Original verschoben wird | ✅ |
| E34 | 05.11.2026 | Texterkennung mit OCRmyPDF, sonst Tesseract je Seite; beides über Homebrew, nicht mitgeliefert | Kostenlos und offline; ohne Werkzeug wird das Buch trotzdem übernommen (lesbar, nicht durchsuchbar) statt abgewiesen | ✅ |
| E35 | 05.11.2026 | Fragen offline über Stichwörter und Fundstellen; KI-Antworten (Claude-API) vorerst nicht eingebaut | Kein Text verlässt den Mac (N2, N3), keine laufenden Kosten; eine Antwort mit Fundstelle ist nachprüfbar. Optional später: nur markierte Auszüge auf Knopfdruck an die API | ✅ |
| E29 | 04.11.2026 | Technische Dokumentation wird aus den vorhandenen Einzel-PDFs zusammengesetzt (pypdf, neue kleine Abhängigkeit) statt neu gesetzt | Jedes Kapitel sieht aus wie sein Einzeldruck; fehlerhafte Kapitel verhindern das Paket nicht und stehen im Inhaltsverzeichnis | ✅ |
| E19 | 04.11.2026 | Normteile mit vereinfachter Geometrie (kein Gewinde, Lager als Vollring × 0,62 für die Masse); Maße als „Norm, ungeprüft“ markiert | Reicht für Ansicht, Masse und Stückliste; die Werte stehen sichtbar als ungeprüft in Stückliste und Programm, bis sie mit Katalog/Tabellenbuch abgeglichen sind | ✅ |

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
| KI-Assistent (optional, S19) | In MS14: offline über Stichwörter und Fundstellen (E35); Claude-API mit Auszügen nur auf Anfrage bleibt möglich | Datenschutz und Urheberrecht zuerst | – |
| Tests | **pytest** + Screenshot-Tests der Oberfläche (hell/dunkel) | Rechenbeispiele aus der Literatur als feste Testfälle (N5) | – |
| Auslieferung | **PyInstaller → .app** + Startskript `start.command` für die Entwicklung | Doppelklick-Start auf dem Mac | – |

⚠️ Ressourcen-Hinweis: Der Geometriekern (OCP) ist einige 100 MB groß. Das ist einmalig, kostenlos und für das eigene CAD unverzichtbar. Alles andere ist klein. Es gibt keine laufenden Kosten.
