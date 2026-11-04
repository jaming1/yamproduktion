# Lastenheft – YamProduktion
Version: 0.1   ·   Status: 📝 Entwurf   ·   Datum: 04.11.2026

## Versionsverlauf
| Version | Datum | Änderung | Status |
|---------|-------|----------|--------|
| 0.1 | 04.11.2026 | Erster Entwurf aus freigegebener Idee v1.0 | Entwurf |

---

## 1. Ziel und Abgrenzung

### Ziel
YamProduktion ist ein Desktop-Programm für macOS, mit dem ein Maschinenbau-Produkt vollständig von der Ideenfindung bis zur Inbetriebnahme entwickelt wird. Alle Module (TRIZ, Anforderungen, Konzept, Berechnung, CAD, Fertigung, Montage, Inbetriebnahme, Qualitäts- und Projektmanagement, Wissensbasis) arbeiten auf **einem gemeinsamen Produktmodell**.

Das erste Produkt, das mit der App entwickelt und **real gebaut** wird, ist eine **Mini-Windkraftanlage mit 5 bis 10 kW**. Die App muss so gut sein, dass diese Anlage damit bis zur Inbetriebnahme gebracht werden kann.

### Abgrenzung (nicht Teil dieses Lastenhefts)
- Eigener Geometriekern (es wird ein bewährter Kern verwendet, siehe Idee Abschnitt 8)
- FEM- und Strömungssimulation (spätere Ausbaustufe)
- ERP, Einkauf, Lager, Buchhaltung
- Cloud-Betrieb, Mehrbenutzer-Server, Windows/Linux
- Weitergabe gescannter Buchinhalte
- Elektrische Netzanschluss-Zertifizierung (nur Checklisten und Verweise)

---

## 2. Gemeinsames Produktmodell (Datenfluss)

Alle Module lesen und schreiben in dasselbe Modell. Die wichtigsten Objekte und ihre Verknüpfung:

```
Projekt
 └─ Produkt (z. B. Kleinwindanlage KWA-5)
     ├─ Idee / TRIZ-Widersprüche / Lösungsideen
     ├─ Anforderung  ──erfüllt durch──▶ Funktion ──umgesetzt in──▶ Konzept-Variante
     │      │                                                        │
     │      └──────────nachgewiesen durch──▶ Berechnung ◀────────────┘
     │                                        │  (Eingaben, Formel, Quelle, Ergebnis, Sicherheit)
     │                                        ▼ liefert Parameter
     ├─ Bauteil / Baugruppe (CAD-Modell, Zeichnung, Werkstoff)
     │      ├─ Stücklistenposition (Eigen-, Norm-, Zukaufteil)
     │      ├─ Arbeitsplan ──▶ Arbeitsgang (Verfahren, Maschine, Zeit, Kosten)
     │      └─ Prüfmerkmal ──▶ Prüfplan / Prüfprotokoll
     ├─ Montageplan ──▶ Montageschritt (Reihenfolge, Montageplatte, Anzugsmoment)
     ├─ Inbetriebnahme-Checkliste ──▶ Protokoll / Abnahme
     ├─ Risiko (Risikobeurteilung, FMEA) ──▶ Maßnahme
     └─ Aufgabe / Meilenstein (Projektmanagement)
```

Jedes Objekt hat: eindeutige Nummer, Version, Status (Entwurf / geprüft / freigegeben), Änderungsverlauf und Verknüpfungen zu anderen Objekten.

---

## 3. Anforderungen

Priorität: **M** = Muss · **S** = Soll · **K** = Kann

### 3.1 Grundsystem & Produktmodell
| Nr | Anforderung |
|----|-------------|
| M1 | Projekte und Produkte anlegen, öffnen, speichern, kopieren; alles lokal auf dem Mac. |
| M2 | Das Produkt durchläuft die Phasen P1–P9; jede Phase hat Status und eine Freigabe („Phasentor“). |
| M3 | Alle Objekte (Anforderung, Berechnung, Bauteil, Arbeitsgang, Prüfung …) haben Nummer, Version, Status und Änderungsverlauf. |
| M4 | **Rückverfolgung:** Objekte sind verknüpfbar; zu jedem Objekt sieht man, wovon es abhängt und was davon abhängt. |
| M5 | **Änderungswirkung:** Ändert sich ein Wert, markiert die App alle abhängigen Objekte als „neu prüfen“. |
| M6 | Einheitensystem: jede Zahl mit Einheit (SI), automatische Umrechnung, Fehler bei unverträglichen Einheiten. |
| M7 | Automatische Sicherung und Wiederherstellung; kein Datenverlust bei Absturz. |
| S1 | Vorlagen je Produkttyp; erste Vorlage „Kleinwindanlage 5–10 kW“. |
| K1 | Export des ganzen Projekts als Archiv (zum Sichern oder Weitergeben ohne Buchinhalte). |

### 3.2 Ideenfindung & TRIZ (P1)
| Nr | Anforderung |
|----|-------------|
| M8 | Ideen erfassen mit Beschreibung, Skizze/Bild, Nutzen, Problem. |
| M9 | TRIZ-Widerspruchsmatrix: 39 technische Parameter auswählen → passende der 40 innovativen Prinzipien anzeigen. |
| S2 | Weitere TRIZ-Werkzeuge: Ideales Endergebnis, Ressourcenanalyse, physikalische Widersprüche (Separationsprinzipien). |
| S3 | Lösungsideen aus TRIZ direkt als Konzept-Variante übernehmen. |
| K2 | Weitere Kreativmethoden (Brainstorming-Board, 6-3-5, Mindmap). |

### 3.3 Anforderungen & Funktionen (P2)
| Nr | Anforderung |
|----|-------------|
| M10 | Anforderungen mit Nummer, Text, Zielwert, Einheit, Toleranz, Priorität (Muss/Soll/Kann), Quelle. |
| M11 | Eigenschaften und Attribute des Produkts definieren (z. B. Nennleistung, Masse, Lebensdauer). |
| M12 | Funktionsstruktur: Gesamtfunktion in Teilfunktionen gliedern (z. B. „Wind wandeln“ → „Energie aufnehmen“, „Drehzahl wandeln“, „Strom erzeugen“). |
| M13 | Lastenheft des Produkts als PDF ausgeben. |

### 3.4 Konzept (P3)
| Nr | Anforderung |
|----|-------------|
| M14 | Morphologischer Kasten: Teilfunktionen × Lösungsprinzipien, Varianten zusammenstellen. |
| M15 | Nutzwertanalyse mit gewichteten Kriterien; Ergebnis und Begründung der Wahl speichern. |
| S4 | Prinzipskizze je Variante (einfaches 2D-Zeichnen). |

### 3.5 Berechnung & Auslegung (P4)
| Nr | Anforderung |
|----|-------------|
| M16 | Jede Berechnung zeigt Eingaben, Formel, Zwischenergebnisse, Ergebnis, Sicherheitsfaktor, Grenzwert, Bewertung (erfüllt / nicht erfüllt) und **Quelle** (Buch, Norm, Kapitel). |
| M17 | Berechnungsprotokoll als PDF. |
| M18 | **Windkraft:** Windleistung, Betz-Grenze, Leistungsbeiwert, Schnelllaufzahl, Rotordurchmesser, Nenndrehzahl, Rotorschub, Leistungskurve, Jahresenergieertrag aus Windverteilung (Weibull/Rayleigh). |
| M19 | **Lastannahmen** für Kleinwindanlagen nach IEC 61400-2 (vereinfachtes Lastmodell, Lastfälle, Teilsicherheitsbeiwerte). |
| M20 | **Antriebsstrang:** Drehmoment, Leistung, Drehzahl, Wirkungsgrade, Generatorauswahl. |
| M21 | **Getriebe:** Übersetzung, Stirnrad- und Planetenstufe (Geometrie), Zahnfuß- und Flankentragfähigkeit (vereinfacht nach DIN 3990 / ISO 6336). |
| M22 | **Welle:** Biegung, Torsion, Vergleichsspannung, Dauerfestigkeit mit Kerbwirkung (nach FKM-Richtlinie bzw. DIN 743), Durchbiegung, Sicherheit. |
| M23 | **Lager:** Lebensdauer L10/L10h, modifizierte Lebensdauer. |
| M24 | **Verbindungen:** Schrauben (VDI 2230, vereinfacht), Passfedern, Pressverbände, Schweißnähte. |
| M25 | **Turm & Fundament:** Kippmoment, Biegespannung Turm, Standsicherheit Fundament, Flanschverschraubung. |
| M26 | Werkstoffdatenbank (Festigkeitswerte, E-Modul, Dichte) für gängige Stähle, Aluminium, GFK. |
| S5 | **Bremse und Sicherheitssystem:** Bremsmoment, Abschaltung bei Überdrehzahl/Sturm. |
| S6 | Ergebnisse (z. B. Wellendurchmesser) als Parameter direkt ins CAD übergeben. |
| S7 | Eigene Berechnungen mit Formeleditor anlegen (Formel, Variablen, Einheiten). |
| K3 | Rotorblatt-Auslegung nach Blattelementmethode (BEM). |

### 3.6 Konstruktion – eigenes CAD (P5)
| Nr | Anforderung |
|----|-------------|
| M27 | 2D-Skizzen mit Linien, Bögen, Kreisen, Bemaßung und geometrischen Bedingungen. |
| M28 | Parametrische 3D-Bauteile: Extrusion, Rotation, Bohrung, Fase, Verrundung, Muster. |
| M29 | Parameter verknüpfbar mit Berechnungsergebnissen (Wellendurchmesser kommt aus M22). |
| M30 | Baugruppen mit Verknüpfungen (Achse, Fläche, Abstand). |
| M31 | Technische Zeichnungen: Ansichten, Schnitte, Bemaßung, Toleranzen, Oberflächenangaben, Schriftfeld; Export PDF und DXF. |
| M32 | Stückliste automatisch aus der Baugruppe. |
| M33 | Austausch mit anderen Programmen: Import/Export STEP, Export STL. |
| S8 | Bibliothek für Normteile (Schrauben, Muttern, Scheiben, Lager, Passfedern). |
| S9 | Parametrische Vorlagen-Bauteile (Welle, Flansch, Nabe, Zahnrad) aus Berechnungswerten. |
| K4 | Kollisionsprüfung in Baugruppen, Masse und Schwerpunkt. |

### 3.7 Fertigungstechnik & Fertigungsplanung (P6)
| Nr | Anforderung |
|----|-------------|
| M34 | Arbeitsplan je Bauteil: Arbeitsgänge mit Verfahren (Drehen, Fräsen, Bohren, Schweißen, Laminieren …), Maschine, Werkzeug, Rüst- und Stückzeit. |
| M35 | Rohteil festlegen (Halbzeug, Abmessungen, Werkstoff). |
| M36 | Kostenkalkulation je Bauteil und gesamt (Material, Fertigung, Zukauf). |
| M37 | Kennzeichnung Eigen- oder Fremdfertigung; Anfrageliste für Fremdfertigung. |
| S10 | Schnittdaten- und Zeitberechnung (Schnittgeschwindigkeit, Vorschub, Hauptzeit). |
| K5 | CAM-Export (z. B. G-Code für einfache Dreh-/Fräsbearbeitung). |

### 3.8 Montage (P7)
| Nr | Anforderung |
|----|-------------|
| M38 | Montageplan: Reihenfolge der Schritte, benötigte Teile, Werkzeuge, Anzugsmomente, Prüfschritte. |
| M39 | Montageplatte / Montagevorrichtung als eigenes Objekt mit Konstruktion und Aufnahmepunkten. |
| M40 | Montageanleitung als PDF mit Bildern aus dem CAD. |
| S11 | Explosionsdarstellung aus der Baugruppe. |

### 3.9 Inbetriebnahme (P8)
| Nr | Anforderung |
|----|-------------|
| M41 | Inbetriebnahme-Checklisten (mechanisch, elektrisch, Sicherheitsfunktionen) mit Soll/Ist-Werten. |
| M42 | Messprotokolle und Abnahmeprotokoll als PDF. |
| S12 | Vorlage „Kleinwindanlage“: Drehrichtung, Bremse, Überdrehzahlschutz, Sturmabschaltung, Leistungskurve messen. |

### 3.10 Betrieb & Rückmeldung (P9)
| Nr | Anforderung |
|----|-------------|
| S13 | Wartungsplan mit Intervallen und Verschleißteilen. |
| S14 | Erfahrungen und Mängel als Verbesserung zurück in die Ideenphase der nächsten Version. |

### 3.11 Qualitätsmanagement (Querschnitt)
| Nr | Anforderung |
|----|-------------|
| M43 | Prüfmerkmale aus Zeichnung (Maße, Toleranzen) in Prüfpläne übernehmen. |
| M44 | FMEA (Konstruktions- und Prozess-FMEA) mit Bewertung und Maßnahmen. |
| M45 | Abweichungen/Fehler erfassen, Ursache, Maßnahme, Wirksamkeit. |
| S15 | Prüfmittel und Prüfprotokolle je Bauteil. |

### 3.12 Sicherheit & Normen (Querschnitt)
| Nr | Anforderung |
|----|-------------|
| M46 | Risikobeurteilung (Gefährdungen, Risiko, Maßnahme, Restrisiko) nach Maschinenverordnung (EU) 2023/1230 bzw. EN ISO 12100. |
| M47 | Checkliste der relevanten Normen je Produkt (für die Windkraftanlage u. a. IEC 61400-2) mit Status. |
| S16 | Technische Dokumentation zusammenstellen (Berechnungen, Zeichnungen, Risikobeurteilung, Anleitungen) als ein PDF-Paket. |

### 3.13 Projektmanagement (Querschnitt)
| Nr | Anforderung |
|----|-------------|
| M48 | Aufgaben mit Verantwortlich, Termin, Status, Verknüpfung zu Phase und Objekt. |
| M49 | Meilensteine und Übersicht je Phase (Fortschritt in %). |
| S17 | Zeitplan als Gantt-Darstellung. |
| S18 | Kostenübersicht Plan/Ist. |

### 3.14 Wissensbasis (Querschnitt)
| Nr | Anforderung |
|----|-------------|
| M50 | Gescannte Bücher (PDF/Bilder) importieren, per Texterkennung lesbar machen und lokal durchsuchen. |
| M51 | Suchergebnis zeigt Buch, Kapitel, Seite und öffnet die Seite. |
| M52 | Scans bleiben ausschließlich lokal; sie werden nie exportiert oder geteilt. |
| S19 | Fragen in normaler Sprache an die Bücher stellen; Antwort mit Seitenangaben, gekennzeichnet als „Vorschlag, nicht geprüft“. |
| S20 | Aus einer Buchstelle eine Berechnung anlegen (Formel übernehmen, Quelle automatisch eingetragen). |

---

## 4. Nicht-funktionale Anforderungen

| Nr | Bereich | Anforderung |
|----|---------|-------------|
| N1 | Plattform | Nur macOS (Apple Silicon, aktuelle macOS-Version); ein Programm, keine Installation mehrerer Teile. |
| N2 | Offline | Alles funktioniert ohne Internet. Ausnahme: optionaler KI-Wissensassistent (S19). |
| N3 | Datenschutz | Alle Daten lokal; keine Weitergabe an Dritte ohne ausdrückliche Aktion. |
| N4 | Geschwindigkeit | Berechnungen in unter 1 Sekunde; CAD-Ansicht flüssig bei Baugruppen mit mindestens 500 Teilen. |
| N5 | Richtigkeit | Jede Berechnung ist mit mindestens einem Rechenbeispiel aus der Literatur getestet; Abweichung höchstens 1 %. |
| N6 | Nachvollziehbarkeit | Jedes Ergebnis zeigt Formel und Quelle; KI-Vorschläge sind immer getrennt von geprüften Werten. |
| N7 | Bedienbarkeit | Klare deutsche Sprache, große Bedienelemente, Hell-/Dunkelmodus, Tastenkürzel; Seitenleisten einklappbar, maximale Arbeitsfläche für CAD und Berechnung. |
| N8 | Robustheit | Automatische Sicherung; verständliche Fehlermeldungen mit Lösungsvorschlag; kein Absturz bei falschen Eingaben. |
| N9 | Erweiterbarkeit | Modularer Aufbau: neue Berechnungen, Vorlagen und Module ohne Umbau des Kerns. |
| N10 | Datenformat | Offene, lesbare Formate (z. B. SQLite, STEP, PDF), damit die Daten auch ohne die App erhalten bleiben. |

---

## 5. Rahmenbedingungen

- **Nutzer:** zunächst nur Yamine (ein Nutzer, ein Mac).
- **Budget:** möglichst keine laufenden Kosten; bevorzugt kostenlose, quelloffene Bausteine (z. B. Geometriekern Open CASCADE).
- **Technik:** wird im Plan festgelegt und in `ENTSCHEIDUNGEN.md` begründet.
- **Zeit:** Entwicklung in Meilensteinen; jeder Meilenstein liefert ein nutzbares Ergebnis.
- **Sicherheit beim echten Bau:** Die Windkraftanlage wird real gebaut. Die App ist ein Werkzeug für Auslegung und Dokumentation; Ergebnisse müssen fachlich geprüft werden. Für Genehmigung (Baurecht), Netzanschluss und ggf. CE-Kennzeichnung ist eine Prüfung durch Sachverständige vorzusehen.
- **Urheberrecht:** Buchscans nur zur privaten Nutzung, ausschließlich lokal.

---

## 6. Abnahmekriterien – wann ist die App „fertig“?

Die App gilt als fertig (Version 1), wenn die **Mini-Windkraftanlage vollständig in der App entwickelt** wurde:

1. Idee, TRIZ-Analyse und Anforderungen der Anlage sind in der App erfasst; das Produkt-Lastenheft ist als PDF erzeugt.
2. Ein Konzept wurde mit morphologischem Kasten und Nutzwertanalyse ausgewählt.
3. Alle Muss-Berechnungen (M18–M25) sind für die Anlage durchgeführt; jedes Protokoll ist als PDF vorhanden und zeigt erfüllte Sicherheiten.
4. Alle Eigenteile sind im eigenen CAD konstruiert, die Gesamtbaugruppe ist erstellt, Zeichnungen und Stückliste sind exportiert.
5. Eine Wertänderung (z. B. Nennleistung 5 → 10 kW) markiert alle betroffenen Berechnungen, Bauteile und Pläne als „neu prüfen“.
6. Für jedes Eigenteil gibt es einen Arbeitsplan mit Kosten; die Gesamtkosten sind berechnet.
7. Montageplan mit Montageplatte und Montageanleitung (PDF) liegt vor.
8. Inbetriebnahme-Checkliste ist ausgefüllt, Abnahmeprotokoll erzeugt.
9. FMEA, Risikobeurteilung und Normen-Checkliste sind ausgefüllt; die technische Dokumentation ist als PDF-Paket erzeugt.
10. Die Buchsuche findet zu einer Fachfrage die richtige Seite in den eigenen Scans.
11. Die App läuft offline auf Yamines Mac ohne Absturz durch den ganzen Ablauf.

---

## 7. Offene Punkte für den Plan

- Wahl der Technik (Programmiersprache, Oberfläche, Anbindung des Geometriekerns) → im Plan mit Begründung.
- Reihenfolge der Module: Vorschlag ist ein schmales, durchgehendes Band durch alle Phasen zuerst, danach Vertiefung.
