# Plan – YamProduktion
Version: 1.0   ·   Status: ✅ freigegeben   ·   Datum: 04.11.2026

## Versionsverlauf
| Version | Datum | Änderung | Status |
|---------|-------|----------|--------|
| 0.1 | 04.11.2026 | Erster Entwurf aus freigegebenem Lastenheft v1.0 | Entwurf |
| 1.0 | 04.11.2026 | Freigegeben | ✅ |

---

## 1. Gliederung

Der Plan ist in **6 Etappen mit 15 Meilensteinen** gegliedert. Die Reihenfolge folgt dem Produktlebenszyklus. Wo es nötig ist, wird sie so angepasst, dass jede Stufe auf der vorherigen aufbaut:

- **Fundament zuerst:** Ohne gemeinsames Produktmodell, Einheiten und Rückverfolgung funktioniert kein Modul richtig.
- **Berechnung vor CAD:** Die Maße fürs CAD kommen aus der Berechnung (M29).
- **CAD in drei Schritten:** erst Ansicht und parametrische Vorlagen-Teile, dann freies Modellieren, dann Baugruppen und Zeichnungen. Das CAD ist der größte und riskanteste Teil.
- **Die Mini-Windkraftanlage läuft von Anfang an mit.** Jeder Meilenstein wird an ihr getestet.

Jeder Meilenstein liefert ein **sichtbares, testbares Ergebnis** im Programm.

Technikwahl und Begründung: siehe [`ENTSCHEIDUNGEN.md`](ENTSCHEIDUNGEN.md).

---

## 2. Meilensteine

Status: ⏳ offen · 🔄 in Arbeit · ✅ fertig · ⛔ blockiert

### Etappe A – Fundament

| Nr | Meilenstein | Ergebnis (sichtbar & testbar) | Anforderungen | Status | Datum |
|----|-------------|-------------------------------|---------------|--------|-------|
| MS1 | **Minimaler Prototyp** | Mac-Programm startet per Doppelklick. Projekt „Kleinwindanlage KWA-5“ anlegen, Anforderungen mit Zielwert und Einheit eintragen, **erste Berechnung** (Windleistung → Rotordurchmesser) ausführen, **PDF-Protokoll** speichern. Hell-/Dunkelmodus, einklappbare Seitenleiste. | M1, M6, M10, M16, M17, M18 (Teil), N1, N7 | ✅ | 04.11.2026 |
| MS2 | **Produktmodell & Rückverfolgung** | Phasen P1–P9 mit Phasentor; Objekte mit Nummer, Version, Status, Verlauf; Verknüpfungen; **Änderung 5 → 10 kW markiert abhängige Objekte „neu prüfen“**; automatische Sicherung. | M2–M5, M7, M11, N8, N10 | ✅ | 04.11.2026 |

### Etappe B – Ideenfindung, Konzept, Auslegung

| Nr | Meilenstein | Ergebnis | Anforderungen | Status | Datum |
|----|-------------|----------|---------------|--------|-------|
| MS3 | **TRIZ & Konzept** | Ideen erfassen; TRIZ-Widerspruchsmatrix mit 40 Prinzipien; Funktionsstruktur; morphologischer Kasten; Nutzwertanalyse; Produkt-Lastenheft als PDF. Test: Konzeptwahl der Windkraftanlage (z. B. Getriebe vs. Direktantrieb). | M8, M9, M12–M15, S2, S3 | ✅ | 04.11.2026 |
| MS4 | **Windkraft-Auslegung & Lastannahmen** | Rotor (Betz, cp, Schnelllaufzahl), Leistungskurve, Jahresertrag (Weibull/Rayleigh), Lastfälle nach IEC 61400-2 (vereinfachtes Lastmodell), Antriebsstrang und Generatorauswahl, Werkstoffdatenbank. | M18–M20, M26, N5 | ✅ | 04.11.2026 |
| MS5 | **Maschinenelemente** | Getriebe (Übersetzung, Stirnrad/Planet, Tragfähigkeit), Welle (DIN 743/FKM), Lager (L10), Schrauben (VDI 2230), Passfeder, Pressverband, Schweißnaht, Turm & Fundament, Bremse. Jede Berechnung mit Literatur-Rechenbeispiel getestet. | M21–M25, S5, S7, N5 | ✅ (S7 Formeleditor verschoben; Literatur-Rechenbeispiele teils offen, siehe Bericht) | 04.11.2026 |

### Etappe C – Eigenes CAD

| Nr | Meilenstein | Ergebnis | Anforderungen | Status | Datum |
|----|-------------|----------|---------------|--------|-------|
| MS6 | **CAD-Grundlage & Vorlagen-Teile** | 3D-Ansicht (drehen, zoomen, schneiden); parametrische Vorlagen-Teile Welle, Flansch, Nabe, Zahnrad **entstehen direkt aus den Berechnungswerten**; Export STEP/STL. Test: Hauptwelle aus MS5 erscheint als 3D-Teil. | M29, M33, S6, S9 | ✅ (Schnitt als Halbschnitt; STEP-Import kommt in MS7) | 04.11.2026 |
| MS7 | **Skizzieren & Modellieren** | 2D-Skizzen mit Bemaßung und Bedingungen; Extrusion, Rotation, Bohrung, Fase, Verrundung, Muster; Parameter-Tabelle; STEP-Import. | M27, M28, M33 | ✅ (eigener Skizzen-Löser; Fase/Verrundung über Kantenauswahl statt Klick ins 3D) | 04.11.2026 |
| MS8 | **Baugruppen, Zeichnungen, Stückliste** | Baugruppen mit Verknüpfungen; Normteil-Bibliothek; technische Zeichnung mit Ansichten, Schnitten, Bemaßung, Toleranzen, Schriftfeld; Export PDF/DXF; automatische Stückliste; Masse & Schwerpunkt. Test: Gondel-Baugruppe der KWA. | M30–M32, S8, K4 | ✅ (Ausrichtung koaxial/Abstand/Lochkreis statt allgemeiner 3D-Bedingungen; Normteilmaße ungeprüft) | 04.11.2026 |

### Etappe D – Von der Fertigung bis zur Inbetriebnahme

| Nr | Meilenstein | Ergebnis | Anforderungen | Status | Datum |
|----|-------------|----------|---------------|--------|-------|
| MS9 | **Fertigungsplanung & Kosten** | Arbeitspläne je Bauteil, Rohteil, Schnittdaten/Zeiten, Eigen-/Fremdfertigung, Anfrageliste, Kostenkalkulation. | M34–M37, S10 | ✅ (Schnittwerte, Stundensätze und Preise als Richt-/Schätzwerte markiert; Verzahnen und Laminieren mit Handzeit) | 04.11.2026 |
| MS10 | **Montage & Montageplatte** | Montageplan mit Reihenfolge, Anzugsmomenten, Prüfschritten; Montageplatte als eigenes Objekt (im CAD konstruiert); Explosionsdarstellung; Montageanleitung als PDF. | M38–M40, S11 | ✅ (Anwärmtemperaturen, Fügespiel, Zeiten als Richt-/Schätzwerte markiert; Bilder aus dem eigenen 3D-Renderer) | 04.11.2026 |
| MS11 | **Inbetriebnahme & Betrieb** | Checklisten mit Soll/Ist, Vorlage Kleinwindanlage, Mess- und Abnahmeprotokoll (PDF), Wartungsplan, Rückmeldung in die nächste Version. | M41, M42, S12–S14 | ⏳ | |

### Etappe E – Querschnitt

| Nr | Meilenstein | Ergebnis | Anforderungen | Status | Datum |
|----|-------------|----------|---------------|--------|-------|
| MS12 | **Qualität, Sicherheit & Normen** | Prüfmerkmale aus Zeichnung → Prüfplan; Konstruktions- und Prozess-FMEA; Abweichungen & Maßnahmen; Risikobeurteilung (EN ISO 12100); Normen-Checkliste; **technische Dokumentation als PDF-Paket**. | M43–M47, S15, S16 | ⏳ | |
| MS13 | **Projektmanagement** | Aufgaben, Meilensteine, Fortschritt je Phase, Gantt-Ansicht, Kosten Plan/Ist. | M48, M49, S17, S18 | ⏳ | |
| MS14 | **Wissensbasis** | Buchscans importieren, Texterkennung, lokale Volltextsuche mit Buch/Seite; aus Buchstelle eine Berechnung anlegen; optional KI-Fragen (als „Vorschlag“ gekennzeichnet). | M50–M52, S19, S20, N2, N3 | ⏳ | |

### Etappe F – Abnahme

| Nr | Meilenstein | Ergebnis | Anforderungen | Status | Datum |
|----|-------------|----------|---------------|--------|-------|
| MS15 | **Abnahme mit der echten Windkraftanlage** | Alle 11 Abnahmekriterien aus dem Lastenheft (Abschnitt 6) sind erfüllt. Vorlage „Kleinwindanlage“ fertig, Projekt-Export, README. | S1, K1, Abnahme 1–11 | ⏳ | |

**Kann-Anforderungen** (K2 Kreativmethoden, K3 Blattelementmethode, K5 CAM-Export) kommen nach MS15 oder werden eingeschoben, wenn Zeit bleibt.

---

## 3. Was du parallel schon tun kannst

- **Bücher scannen** (als PDF, 300 dpi, ein PDF pro Buch, Dateiname = Buchtitel). Bis MS14 liegen sie dann bereit. Bei MS5 nutze ich gern Rechenbeispiele daraus für die Tests.
- **Eckdaten der Windkraftanlage** sammeln: Standort, mittlere Windgeschwindigkeit, Netz- oder Inselbetrieb, gewünschte Nabenhöhe.

---

## 4. Risiken

| Risiko | Wirkung | Gegenmaßnahme |
|--------|---------|---------------|
| CAD ist sehr umfangreich | Etappe C dauert deutlich länger als die anderen | Bewährter Geometriekern; erst Vorlagen-Teile (MS6), dann freies Modellieren |
| Rechenfehler bei realem Bau | Sicherheitsrisiko | Jede Formel mit Quelle und Literatur-Rechenbeispiel getestet (N5); Prüfung durch Sachverständige vor dem Bau |
| Normen sind kostenpflichtig | Formeln nicht vollständig verfügbar | Eigene Normauszüge bzw. Fachbücher als Quelle; vereinfachte Verfahren kennzeichnen |
| Große Bausteine (Geometriekern) | Programmgröße einige 100 MB | Einmalig, kostenlos, lokal; keine laufenden Kosten |
