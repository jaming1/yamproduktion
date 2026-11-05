# Changelog – YamProduktion

## 04.11.2026
- Projektordner angelegt
- `docs/01_IDEE.md` v0.1 (Entwurf)
- `docs/01_IDEE.md` v0.2: Desktop-Programm, Mini-Windkraftanlage 5–10 kW als erstes Produkt, eigenes CAD (mit Ressourcen-Hinweis), TRIZ-Modul
- `docs/01_IDEE.md` v1.0 ✅ freigegeben (CAD auf Geometriekern, nur macOS, Windkraftanlage wird gebaut)
- `docs/02_LASTENHEFT.md` v0.1 (Entwurf)
- `docs/02_LASTENHEFT.md` v1.0 ✅ freigegeben
- `docs/03_PLAN.md` v0.1 (Entwurf) und `docs/ENTSCHEIDUNGEN.md` angelegt
- `docs/03_PLAN.md` v1.0 ✅ freigegeben, Technik-Stapel (E4) bestätigt

## 04.11.2026 – MS1 Minimaler Prototyp ✅
- Mac-Programm (Python + PySide6) mit Startskript `code/start.command`
- Projektdatei `.yamp` (SQLite), sofortiges Speichern, Versionen je Anforderung
- Anforderungen mit Zielwert, Einheit (Prüfung über Pint) und Priorität; Vorlage Kleinwindanlage
- Berechnung „Rotorauslegung aus Nennleistung“ mit Rechenweg, Prüfungen (Betz-Grenze, cp, Blattspitzengeschwindigkeit) und Quellen; Übernahme der Werte aus den Anforderungen
- PDF-Berechnungsprotokoll
- Hell-/Dunkel-/Automatikmodus, einklappbare Seitenleiste (Zustand wird gemerkt), Tastenkürzel
- 15 automatische Tests inkl. Oberflächen-Screenshots hell/dunkel

## 04.11.2026 – MS2 Produktmodell & Rückverfolgung ✅
- Phasen P1–P9 mit Phasentor: Freigabe nur ohne offene Punkte; Freigabe gibt alle Objekte der Phase frei; Änderungen öffnen das Tor wieder
- Jedes Objekt mit Nummer, Version, Status (Entwurf / geprüft / freigegeben / neu prüfen) und Verlauf
- Verknüpfungen Anforderung → Berechnung (entstehen automatisch beim Speichern, wenn die Werte aus Anforderungen stammen); Kreise werden verhindert
- Änderungswirkung: geänderter Zielwert oder Einheit markiert alle abhängigen Objekte (über alle Stufen) als „neu prüfen“
- „Neu berechnen“ übernimmt die aktuellen Anforderungswerte inkl. Einheitenumrechnung (z. B. 8000 W → 8 kW)
- Neue Seite „Berechnungen“ mit Status, Neu berechnen, Als geprüft markieren, PDF je Version
- Rückverfolgungs-Panel (einklappbar) mit Sprung zu verknüpften Objekten
- Eigenschaften (Art „Eigenschaft“) neben Anforderungen
- Automatische Sicherung beim Öffnen (letzte 10), Umstellung alter Projektdateien ohne Datenverlust
- 26 automatische Tests inkl. Abnahmekriterium 5 (5 → 10 kW) und Screenshots hell/dunkel

## 04.11.2026 – MS3 TRIZ & Konzept ✅
- Neue Seite „Ideen & TRIZ“: Ideen mit Problem, Nutzen, idealem Endergebnis (IER) und Ressourcen
- TRIZ: 39 Parameter, 40 Prinzipien (deutsch, mit Kurzbeschreibung), Widerspruchsmatrix (1248 Zellen, mit Quellenangabe), Trennungsprinzipien für physikalische Widersprüche; Lösungsideen werden je Prinzip notiert
- Neue Seite „Funktionen“: Funktionsbaum (Gesamt-/Teilfunktionen), Anforderungen zuordnen; Änderung einer Anforderung markiert die Funktion „neu prüfen“
- Neue Seite „Konzept“: morphologischer Kasten (Lösungswege je Teilfunktion, TRIZ-Ideen übernehmen, Varianten), Nutzwertanalyse (Gewichte, Punkte 0–10, bester markiert), Auswahl nur mit Begründung
- Änderungswirkung erweitert: geänderte Lösungswege oder Bewertungen setzen die gewählte Variante auf „neu prüfen“; Phasentore P1 und P3 mit eigenen Prüfungen
- Produkt-Lastenheft als PDF (Knopf in der Übersicht)
- Projektdateien werden automatisch auf Format 3 umgestellt
- 41 automatische Tests inkl. Konzeptwahl der Windkraftanlage und Screenshots hell/dunkel

## 04.11.2026 – MS4 Windkraft-Auslegung & Lastannahmen ✅
- Gemeinsame Rechenseite für alle Berechnungen: Eingaben, Ergebnis, Prüfungen, Diagramm, Tabellen, Rechenweg, Quellen, unbelegte Stellen (gelb)
- „Werte aus dem Projekt übernehmen“ holt Werte aus Anforderungen **und aus anderen Berechnungen**; Verknüpfung Berechnung → Berechnung mit Einheitenumrechnung
- Änderungskette: Anforderung → Rotor → Ertrag/Lasten/Antrieb werden markiert und in Abhängigkeitsreihenfolge neu gerechnet
- Rotorauslegung: Rotorschub und Schubbeiwert nach Impulstheorie
- Neu: Leistungskurve und Jahresertrag (Hellmann-Höhenprofil, Weibull/Rayleigh, Volllaststunden, Kapazitätsfaktor, Diagramm)
- Neu: Lastannahmen nach IEC 61400-2, vereinfachtes Lastmodell: Lastfälle A, B, D, E, F, H, Teilsicherheitsbeiwerte, Bemessungslasten; E und F als unbelegt gekennzeichnet
- Neu: Antriebsstrang und Generatorauswahl (Direktantrieb mit Polpaarzahl oder Getriebe mit Übersetzung/Stufen), Abgleich mit dem Wirkungsgrad der Rotorauslegung
- Neu: Werkstoffdatenbank (14 Werkstoffe: Baustahl, Vergütungsstahl, Edelstahl, Guss, Aluminium, GFK) mit Suche
- PDF-Protokolle mit Tabellen, Diagramm und Abschnitt „Unbelegt“
- 60 automatische Tests, darunter Prüfwerte aus der Literatur (Betz cT = 8/9, Rayleigh-Energiemusterfaktor 6/π, Weibull-Moment c³·Γ(1+3/k)) und Handrechnungen der Lastfälle

## 04.11.2026 – MS5 Maschinenelemente ✅
- Neun neue Berechnungen auf der gemeinsamen Rechenseite, in der Seitenleiste unter „Maschinenelemente“:
  - **Welle** (vereinfacht nach DIN 743): Biegung, Torsion, Dauerfestigkeit mit Kerbwirkung, Sicherheit gegen Fließen und Dauerbruch, Durchbiegung und Neigung am Lager
  - **Lager** (ISO 281): Lagerkräfte des fliegenden Rotors, äquivalente Last, L10h und modifizierte Lebensdauer
  - **Schrauben** (VDI 2230, vereinfacht): Montagevorspannkraft, Anziehmoment, Klemmkraft, Dauerhaltbarkeit
  - **Passfeder** (DIN 6885/6892) und **Pressverband** (DIN 7190): Flächenpressung, Fugendruck, Rutschsicherheit
  - **Schweißnaht** (EN 1993-1-8, richtungsbezogenes Verfahren): ringsum laufende Kehlnaht Rohr an Flansch
  - **Getriebe** (DIN 3990, vereinfacht): Stirnrad- oder Planetenstufe, Profilüberdeckung, Flanken- und Zahnfußsicherheit, Montage- und Nachbarbedingung
  - **Turm & Fundament**: Kippmoment, Spannung, Beulgrenze, Kopfauslenkung, Eigenfrequenz gegen 1P/3P, Kraft je Flanschschraube, Bodenpressung, Kippsicherheit
  - **Bremse**: Bremszeit, Umdrehungen bis Stillstand, Wärme, Zuspannkraft
- Werte fließen durch die Kette: Lasten → Turm → Flanschschrauben und Fußnaht; Lasten → Welle, Lager, Passfeder; Antriebsstrang → Getriebe; Rotor und Lasten → Bremse
- Werkstoffdatenbank: 42CrMo4 vergütet 40–100 mm ergänzt (15 Werkstoffe)
- Seitenleiste mit Gruppen „Windkraft“ und „Maschinenelemente“
- 87 automatische Tests (27 neu) (geschlossene Lösungen, Tabellenwerte, Handrechnungen, Energiebilanz) und Screenshots hell/dunkel

## 04.11.2026 – MS6 CAD-Grundlage & Vorlagen-Teile ✅
- Geometriekern Open CASCADE eingebunden (Paket `cadquery-ocp`, wird beim ersten Start automatisch installiert)
- Neue Seite **Bauteile (3D)** (Seitenleiste › Konstruktion) mit vier parametrischen Vorlagen:
  - **Rotorwelle**: Nabensitz mit Passfedernut (DIN 6885, Form A), zwei Lagersitze, Bund, Generatorzapfen, Fasen; Maße aus Welle und Passfeder
  - **Turmflansch** mit Rohrstutzen und Lochkreis; Maße aus Turm, Durchgangsloch aus der Schraubenberechnung (ISO 273 mittel)
  - **Rotornabe** mit Bohrung, Passfedernut und Blattanschluss-Scheibe; Maße aus dem Pressverband
  - **Stirnrad** mit echter Evolventenverzahnung (glatte Flanken als B-Spline); Maße aus dem Getriebe
- 3D-Ansicht: drehen (Maus links oder Pfeiltasten), verschieben (Maus rechts), zoomen (Mausrad, +/−), Doppelklick = alles zeigen, Ansichten Iso/Vorne/Oben/Seite, Halbschnitt mit verschiebbarer Schnittebene (Schnittfläche orange)
- Masse, Volumen und Abmessungen sofort; unmögliche Maße werden mit Begründung abgelehnt
- Export **STEP** (für Fertiger und andere CAD-Programme) und **STL** (3D-Druck)
- Bauteile im Projekt (T-001 …) mit Version, Status und Verknüpfung zu den Berechnungen: Ändert sich eine Berechnung, wird das Teil „neu prüfen“; „Neu erzeugen“ übernimmt die neuen Maße
- Projektdateien werden automatisch auf Format 4 umgestellt
- 104 automatische Tests (17 neu: Geometrie gegen geschlossene Formeln, STEP hin und zurück, Änderungskette Berechnung → Bauteil) und Screenshots hell/dunkel

## 04.11.2026 – MS7 Skizzieren & Modellieren ✅
- Neue Seite **Modellieren** (Seitenleiste › Konstruktion) für freie Teile mit **Feature-Baum**: Skizze, Extrusion (auch symmetrisch, umgekehrt, abziehen), Rotation, Bohrung (Durchgang oder Sackloch), Fase, Verrundung, Muster (Kreis oder Reihe), STEP-Import
- **Skizzen-Editor**: Linie, Rechteck, Kreis, Bogen, Hilfslinie; Fangen an vorhandenen Punkten; Bedingungen (waagerecht, senkrecht, parallel, rechtwinklig, gleich, tangential, deckungsgleich, fest) und Bemaßungen (Länge, Abstand, Ø, R, Winkel) – Maße erscheinen direkt in der Skizze; Anzeige „vollständig bestimmt“ bzw. offene Freiheitsgrade; widersprüchliche Bedingungen werden mit Meldung abgewiesen
- **Parameter-Tabelle** mit Formeln (z. B. `D = d + 80`); Werte direkt aus gespeicherten Berechnungen mit `ber("welle", "d")`
- Fehler im Feature-Baum halten nur dieses Feature an: Meldung mit Grund, alles davor bleibt sichtbar
- Freie Teile werden als Bauteil gespeichert (Liste „Frei modelliert“), mit Verknüpfung zu den benutzten Berechnungen: ändert sich die Berechnung, wird das Teil „neu prüfen“ und „Neu erzeugen“ baut es mit den neuen Werten
- 115 automatische Tests (11 neu: Formeln, Löser, Volumen gegen geschlossene Formeln, Änderungskette, Lagerdeckel komplett über die Oberfläche) und Screenshots hell/dunkel

## 04.11.2026 – MS8 Baugruppen, Zeichnungen, Stückliste ✅
- **Normteil-Bibliothek**: Zylinderschrauben ISO 4762, Sechskantschrauben ISO 4017, Muttern ISO 4032, Scheiben ISO 7089 (M6–M24), Rillenkugellager 62xx/63xx, Pendelrollenlager 22216–22220 E, Passfedern DIN 6885 A – mit Masse; Maße als „Norm, ungeprüft“ gekennzeichnet
- Neue Seite **Baugruppen**: Bauteile und Normteile einbauen, koaxial ausrichten (Abstand als Formel, umdrehen, Drehung), auf Lochkreise verteilen; Kreisbezüge werden erkannt; Masse und Schwerpunkt; **automatische Stückliste** mit Export CSV und PDF; STEP der ganzen Baugruppe
- Baugruppen G-001 … im Projekt (Dateiformat Version 5, ältere Projekte werden beim Öffnen umgestellt); eingebaute Teile sind verknüpft – Änderung am Teil → Baugruppe „neu prüfen“
- Neue Seite **Zeichnungen**: A3-Blatt nach ISO 128 (Projektionsmethode 1) mit Vorder-, Seiten- und Draufsicht (nur so viele wie nötig), Schnitt A–A mit Schraffur, Mittellinien, automatischer Bemaßung (Gesamtmaße, Ø, Absätze, Lochkreise), Passmaßen (z. B. Ø80 k6), Schriftfeld, Maßstab automatisch; Baugruppen mit Positionsnummern und Stückliste auf dem Blatt; Export **PDF** und **DXF**
- Test Gondel-Baugruppe der KWA: Hauptwelle, Rotornabe, 2 × 22216 E, 12 Blattschrauben M16 mit Muttern; 120 automatische Tests (5 neu) und Screenshots hell/dunkel

## 04.11.2026 – MS9 Fertigungsplanung & Kosten ✅
- **Schnittdaten und Hauptzeiten** (Drehen, Plandrehen, Fräsen, Bohren, Sägen, Brennschneiden) nach Tabellenbuch-Formeln mit Rechenweg; Richtwerte je Werkstoffgruppe, als ungeprüft gekennzeichnet
- **Rohteil** automatisch: Rundstahl (nächster Normdurchmesser + Aufmaß), Ronde aus Blech, Flachstahl/Blech, Gussrohteil; Rohteilmasse
- Neue Seite **Arbeitspläne**: Vorschlag aus der 3D-Geometrie (Absätze, Bohrungen, Lochkreise, Passfedernuten), Arbeitsgänge mit Maschine, Rüst- und Stückzeit, Losgröße, Eigen-/Fremdfertigung mit Angebotspreis, Stückkosten; Arbeitsplan als PDF; AP-001 … verknüpft mit dem Bauteil (Änderung → „neu prüfen“)
- Neue Seite **Kosten & Anfragen**: Herstellkosten je Baugruppe (Eigen, Fremd, Zukauf) für beliebige Stückzahl, Kostensätze des Projekts änderbar, Kalkulation als PDF, **Anfrageliste** für Fremdfertigung als PDF
- Dateiformat Version 6 (ältere Projekte werden beim Öffnen umgestellt)
- Test mit der Gondel: Hauptwelle in Eigenfertigung, Nabe als Gussteil fremd, Lager und Schrauben als Zukauf; 125 automatische Tests (5 neu) und Screenshots hell/dunkel

## 04.11.2026 – MS10 Montage & Montageplatte ✅ (Version 0.10.0)
- Neue Seite **Montagepläne**: Vorschlag aus der Baugruppe (Vorrichtung → Grundteil → Passfedern → Lager → Bauteile → Scheiben → Schrauben → Muttern → Endkontrolle) mit Tätigkeit, Teilen, Werkzeugen, Anzugsmomenten, Prüfschritten und Zeit; alles änderbar, Schritte verschieben/einfügen/löschen; Prüfung auf fehlende oder doppelte Einbauten
- **Anzugsmomente** aus der Schraubenberechnung (gleiches Gewinde und gleiche Klasse) oder nach VDI 2230 vereinfacht für 8.8 als Richtwert; Hinweis bei Klassen-Widerspruch
- **Fügetemperatur** der Nabe aus der Pressverband-Berechnung, Lager-Anwärmtemperatur als Herstellerrichtwert
- **Montageplatte** als neue CAD-Vorlage: Grundplatte, zwei Auflageböcke mit Halbschalen, Befestigungslöcher, Aufnahmepunkte; Maße automatisch aus der Baugruppe (längste freie Wellenstelle, größter Radius)
- **Explosionsdarstellung** mit Schieber; 3D-Ansicht zeigt den Zustand nach jedem Schritt, neue Teile farbig
- **Montageanleitung als PDF** mit Explosionsbild, Teileliste, Werkzeugliste, Vorrichtung mit Aufnahmepunkten, je Schritt einem Bild aus dem CAD, Anzugsmomenten, Prüfschritten zum Abhaken und Freigabefeld
- Montagepläne M-001 … verknüpft mit Baugruppe und Vorrichtung (Änderung → „neu prüfen“); Dateiformat Version 7
- 129 automatische Tests (4 neu) und Screenshots hell/dunkel

## 04.11.2026 – MS11 Inbetriebnahme & Betrieb ✅ (Version 0.11.0)
- Neue Seite **Inbetriebnahme**: Checkliste aus der Vorlage Kleinwindanlage mit 20 Prüfpunkten (mechanisch, elektrisch, Sicherheitsfunktionen, Messungen); Sollwerte aus Rotor-, Ertrags-, Brems-, Schrauben-Berechnung und Montageplänen mit Quelle; Ist-Werte mit sofortiger Bewertung (i. O. / n. i. O. / offen); eigene Prüfpunkte
- **Leistungskurve messen**: Messpunkte gegen die berechnete Kurve, Abweichung und Diagramm; **Messprotokoll** und **Abnahmeprotokoll** als PDF mit Unterschriftenfeld
- Neue Seite **Wartung**: Wartungsplan mit Intervallen, erstem Intervall, Verschleißteilen und Fälligkeit; Lagertausch aus L10h und Betriebsstunden; als PDF
- **Rückmeldung**: Mängel und Erfahrungen werden Ideen in Phase P1 für die nächste Version
- IB-001 … und WP-001 … verknüpft mit ihren Quellen (Änderung → „neu prüfen“); Dateiformat Version 8
- 133 automatische Tests (4 neu) und Screenshots hell/dunkel

## 04.11.2026 – MS12 Qualität, Sicherheit & Normen ✅ (Version 0.12.0)
- **Passmaße** auf der Zeichnung werden je Bauteil gemerkt; die Zeichnung liefert ihre Maßtexte für den Prüfplan
- Neue Seite **Prüfpläne**: Prüfmerkmale aus der Zeichnung, Grenzmaße nach ISO 286 (H, F, G, f, g, h, js, k, m, n, p; IT5–IT11) und ISO 2768-m, Prüfmittel nach der 1/10-Regel, Ist-Werte mit i. O./n. i. O., **Prüfprotokoll** als PDF mit Prüfmittelliste; Aktualisieren aus der Zeichnung behält Ist-Werte
- Neue Seite **FMEA**: Konstruktions- und Prozess-FMEA mit Vorlage Kleinwindanlage, B·A·E, RPZ, Ampel, Maßnahme und Neubewertung
- Neue Seite **Abweichungen**: Ursache, Maßnahme, Verantwortlich, Termin, Wirksamkeit; n. i. O. aus Prüfplänen und Inbetriebnahme übernehmen
- Neue Seite **Risikobeurteilung** nach EN ISO 12100 / (EU) 2023/1230: Grenzen der Maschine, 13 Gefährdungen, S·W, Schutzmaßnahme mit Stufe, Restrisiko erst nach Umsetzung
- Neue Seite **Normen**: 20 Normen und Regeln mit Status und Nachweis aus dem Projekt, Abgleich mit neuen Berechnungen
- Neue Seite **Technische Doku**: alle Unterlagen als **ein PDF** mit Deckblatt, Inhaltsverzeichnis (fehlende Kapitel rot) und Lesezeichen (pypdf)
- PP-, FM-, RB-, NL-, QA-Nummern, verknüpft mit Teilen und Berechnungen (Änderung → „neu prüfen“); Dateiformat Version 9
- 137 automatische Tests (4 neu) und Screenshots hell/dunkel

## 05.11.2026 – MS13 Projektmanagement ✅ (Version 0.13.0)
- Neue Seite **Aufgaben & Zeitplan**: Aufgaben und Meilensteine (AU-001 …) mit Verantwortlich, Start, Termin, Stand, Phase, Kosten Plan/Ist und verknüpftem Objekt; sofort gespeichert, überfällige Termine rot, Filter je Phase, Sprung zum Objekt
- **Fortschritt je Phase** in % (erledigte Aufgaben und geprüfte/freigegebene Objekte) auf der Seite und in der Übersicht; nächster Meilenstein
- **Zeitplan als Gantt** mit Heute-Linie und Meilenstein-Rauten; Vorlage „Kleinwindanlage“ mit 13 Aufgaben und 5 Meilensteinen (Dauern geschätzt); Zeitplan als PDF
- Neue Seite **Kosten Plan/Ist**: Posten je Kostenart, Plan aus der Kalkulation, Kosten der Aufgaben, Abweichung (rot ab +10 %), als PDF
- **Phasentore P5–P9** freigeschaltet: Freigabe mit Prüfungen (Bauteil, Arbeitsplan, Montageplan, abgenommene Inbetriebnahme, Wartungsplan) und ohne offene Aufgaben der Phase; Übersicht öffnet alle Phasen
- Dateiformat Version 10
- 141 automatische Tests (4 neu) und Screenshots hell/dunkel
