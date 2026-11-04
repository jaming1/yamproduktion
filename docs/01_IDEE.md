# Idee – YamProduktion
Version: 1.0   ·   Status: ✅ freigegeben   ·   Datum: 04.11.2026

## Versionsverlauf
| Version | Datum | Änderung | Status |
|---------|-------|----------|--------|
| 0.1 | 04.11.2026 | Erster Entwurf aus Yamines Idee | Entwurf |
| 0.2 | 04.11.2026 | Desktop-Programm, Fokus Maschinenbau mit Mini-Windkraftanlage (5–10 kW) als erstem Produkt, eigenes CAD, TRIZ-Modul ergänzt | Entwurf |
| 1.0 | 04.11.2026 | Freigegeben; offene Fragen beantwortet (CAD auf Geometriekern, nur macOS, Windkraftanlage wird real gebaut) | ✅ |

---

## 1. Projektname und Ein-Satz-Beschreibung

**YamProduktion** – ein Desktop-Programm für den Maschinenbau, das ein Produkt durch seinen ganzen Lebenszyklus führt: Ideenfindung (inkl. TRIZ), Anforderungen, Konzept, Berechnung, eigene CAD-Konstruktion, Fertigung, Montage und Inbetriebnahme. Alles aus einer Hand, alle Module in einer App.

## 2. Problem

Wer ein technisches Produkt entwickelt, springt heute zwischen vielen Werkzeugen hin und her: Notizen für die Idee, Word für das Lastenheft, Excel oder Taschenrechner für die Auslegung, ein CAD-Programm für die Zeichnung, wieder Excel für Arbeitspläne und Stücklisten, separate Listen für Qualität und Projektplanung. Dabei geht der rote Faden verloren:

- Eine geänderte Anforderung (z. B. höhere Nennleistung) wirkt sich nicht automatisch auf Berechnung, Geometrie und Fertigung aus.
- Formeln und Wissen aus den Fachbüchern stecken im Regal statt im Arbeitsablauf.
- Nachweise (Festigkeit, Sicherheit, Normen) sind schwer nachvollziehbar.

## 3. Zielgruppe und Bereich

- **Bereich:** Maschinenbau.
- **Nutzer:** zuerst Yamine selbst als Ingenieur, der Produkte von der Idee bis zur Inbetriebnahme durchzieht.
- **Erstes Produkt (roter Faden):** eine **Mini-Windkraftanlage mit 5 bis 10 kW**. Die App wird an diesem echten Produkt entwickelt und getestet, bleibt aber allgemein für Maschinenbau-Produkte nutzbar.
- 💡 Vorschlag: Später auch kleine Teams und Einzelkonstrukteure, für die große PLM-Systeme zu teuer und zu schwer sind.

## 4. Kernidee

Ein **durchgehender roter Faden**: Jede Phase baut auf den Daten der vorherigen auf. Eine Anforderung wird zu einer Funktion, die Funktion zu einer Berechnung, die Berechnung zu einem Bauteil im eigenen CAD, das Bauteil zu einem Fertigungsschritt, alles zusammen zu einer Montage und schließlich zu einem geprüften, in Betrieb genommenen Produkt.

💡 Vorschlag: Das Herzstück ist ein **gemeinsames Produktmodell** (eine Datenbasis), auf das alle Module zugreifen. Ändert sich etwas, zeigt die App, welche Schritte neu geprüft werden müssen („Nennleistung 5 → 10 kW wirkt auf: Rotordurchmesser → Blattlast → Hauptwelle → Lager → Turmfuß → Arbeitsplan AP-03“).

## 5. Die Phasen des Produktlebenszyklus

Jede Phase hat ein klares Ergebnis und ein „Tor“ (Freigabe), bevor es weitergeht. Rechts jeweils das Beispiel Mini-Windkraftanlage.

| Nr | Phase | Was passiert | Beispiel Windkraftanlage |
|----|-------|--------------|--------------------------|
| P1 | **Ideenfindung** | Idee festhalten, Problem, Nutzen, Markt; Kreativmethoden und **TRIZ** | Horizontal- oder Vertikalachse? Netz- oder Inselbetrieb? |
| P2 | **Anforderungen** | Eigenschaften, Attribute, Funktionen mit Zielwerten und Einheiten; Muss/Soll/Kann | Nennleistung 5–10 kW, Nennwind 11 m/s, Abschaltwind 25 m/s, Lebensdauer 20 Jahre |
| P3 | **Konzept** | Funktionsstruktur, Lösungsvarianten (morphologischer Kasten), Bewertung (Nutzwertanalyse) | Direktantrieb vs. Getriebe, Pitch- vs. Stall-Regelung, Turmbauart |
| P4 | **Berechnung & Auslegung** | Ingenieurwissen ausrechnen: Antriebe, Getriebe, Wellen, Lager, Schrauben, Festigkeit, Sicherheitsnachweise | Rotorauslegung (Betz, Schnelllaufzahl), Getriebeübersetzung, Generator, Hauptwelle, Lager, Turm, Fundament |
| P5 | **Konstruktion (eigenes CAD)** | 2D-Skizzen, 3D-Bauteile, Baugruppen, technische Zeichnungen, Stückliste | Nabe, Gondel, Hauptwelle, Turmflansch, Zeichnungen |
| P6 | **Fertigungstechnik & -planung** | Verfahren wählen, Arbeitspläne, Rohteile, Zeiten, Kosten, Eigen-/Fremdfertigung | Drehen der Welle, Schweißen des Maschinenträgers, Blätter aus GFK |
| P7 | **Montage** | Montagereihenfolge, Montageplatte / Vorrichtung, Montageanleitung, Prüfschritte | Gondelmontage auf Montageplatte, Anzugsmomente, Rotormontage |
| P8 | **Inbetriebnahme** | Checklisten, Funktionstests, Messprotokolle, Abnahme | Drehrichtung, Bremse, Abschaltung bei Sturm, Leistungskurve |
| P9 | **Betrieb & Rückmeldung** 💡 | Wartungsplan, Ersatzteile, Erfahrungen zurück in die nächste Version | Wartungsintervalle, Verschleißteile |

### Querschnitt über alle Phasen

| Modul | Was dazugehört |
|-------|----------------|
| **TRIZ** | Widerspruchsmatrix, 40 innovative Prinzipien, Ideales Endergebnis, Ressourcenanalyse; nutzbar in Ideenfindung und bei technischen Widersprüchen in jeder Phase (z. B. „Rotor soll groß sein für Leistung, aber klein für geringe Lasten“) |
| **Projektmanagement** | Meilensteine, Aufgaben, Termine, Aufwand, Status je Phase |
| **Qualitätsmanagement** | Prüfpläne, Toleranzen, FMEA, Abweichungen, Maßnahmen, Prüfprotokolle |
| **Sicherheit & Normen** 💡 | Risikobeurteilung nach Maschinenverordnung (EU) 2023/1230, Kleinwindanlagen nach IEC 61400-2, CE-Unterlagen, technische Dokumentation |
| **Dokumente & Versionen** | Jede Zeichnung, Berechnung und Liste mit Version und Freigabestatus |
| **Wissensbasis** | Fachbücher, Formeln, Werkstoffdaten, Normverweise (siehe Abschnitt 7) |

## 6. Hauptfunktionen (nach Wichtigkeit)

1. **Produktprojekt anlegen und durch die Phasen führen** – mit Fortschrittsanzeige und Freigabe je Phase.
2. **Anforderungen strukturiert erfassen** – Eigenschaften, Attribute und Funktionen mit Zielwert, Einheit, Priorität.
3. **Berechnungsmodule (Ingenieurwissen ausrechnen)** – zuerst das, was die Windkraftanlage braucht:
   - Rotor- und Leistungsauslegung (Windleistung, Betz-Grenze, Schnelllaufzahl, Rotordurchmesser)
   - Antriebsstrang: Drehmoment, Drehzahl, Generatorauswahl
   - Getriebeberechnung (Übersetzung, Stirnrad-/Planetenstufe, Tragfähigkeit)
   - Welle (Biegung, Torsion, Vergleichsspannung, Dauerfestigkeit, Sicherheit)
   - Lager (Lebensdauer L10), Schraubenverbindungen (Flansch, Vorspannkraft)
   - Turm und Fundament (Kippmoment, Standsicherheit)
   - Jede Berechnung mit Formel, Eingaben, Ergebnis, Sicherheitsfaktor und Quellenangabe → druckbares PDF-Protokoll.
4. **Eigenes CAD** – Skizzen, parametrische 3D-Teile, Baugruppen, Zeichnungen. Maße kommen direkt aus der Berechnung.
5. **TRIZ-Werkzeuge** – Widerspruch eingeben, passende Prinzipien vorschlagen, Ideen dokumentieren.
6. **Rückverfolgung** – Anforderung → Berechnung → Bauteil → Arbeitsschritt → Prüfung.
7. **Stückliste und Bauteilverwaltung** – Eigen-, Norm- und Zukaufteile.
8. **Fertigungs- und Montagepläne** – Arbeitsschritte, Maschinen, Zeiten, Kosten, Montagereihenfolge, Montageplatte.
9. **Qualität und Inbetriebnahme** – Prüfpläne, FMEA, Checklisten, Protokolle.
10. **Projektmanagement** – Aufgaben, Termine, Status.
11. **Wissensassistent** – Fragen an die eigenen Fachbücher mit Buch- und Seitenangabe.

## 7. Wissensbasis aus den eigenen Ingenieurbüchern

Yamine scannt seine Fachbücher. Die App macht sie durchsuchbar und nutzt sie als Nachschlagewerk.

💡 Vorschlag, wie das sinnvoll funktioniert:
- **Durchsuchen statt Abschreiben:** Scans werden per Texterkennung (OCR) lesbar gemacht und lokal indexiert. Eine Frage liefert die passenden Seiten mit Buch und Seitenzahl.
- **Formeln geprüft programmieren:** Die Berechnungsmodule werden nach den Formeln aus Büchern und Normen programmiert und nennen ihre Quelle. Die App rechnet mit geprüften Formeln, nicht mit „geratenen“ KI-Antworten.
- **Belegt und unbelegt getrennt:** KI-Antworten sind immer als Vorschlag gekennzeichnet.

⚠️ Urheberrecht: Für die **eigene, private Nutzung** auf dem eigenen Rechner sind Scans in der Regel unproblematisch (Privatkopie, § 53 UrhG; bei ganzen Büchern gibt es Grenzen). **Nicht erlaubt** wäre, Scans oder Textpassagen mit der App an andere weiterzugeben. Darum bleiben die Scans **lokal und privat**; eine weitergegebene App enthält nur die selbst programmierten Berechnungen und Quellenhinweise.

## 8. Eigenes CAD – wie das machbar wird

Yamines Entscheidung: **CAD und alle Module werden selbst gebaut**, damit alles aus einer Hand ist.

⚠️ Ressourcen-Hinweis
- **Geplant:** eigenes CAD mit Skizzen, 3D-Teilen, Baugruppen und Zeichnungen in der App.
- **Aufwand:** Ein CAD von Grund auf (eigene Geometrie-Mathematik für Körper, Bohrungen, Verrundungen, Schnitte) ist ein Vorhaben über viele Jahre. Das ist der mit Abstand größte Brocken des Projekts.
- **Alternativen:**
  1. Eigenes CAD in der App, aber auf einem bewährten, kostenlosen **Geometriekern** (z. B. Open CASCADE, auf dem auch FreeCAD läuft). Oberfläche, Bedienung, Parametrik und die Verbindung zu den Berechnungen bauen wir selbst; die schwere Geometrie-Mathematik übernimmt der Kern.
  2. Zuerst parametrische Bauteile aus Vorlagen (Welle, Flansch, Nabe, Zahnrad), die aus den Berechnungswerten automatisch entstehen, danach freies Modellieren.
  3. Kompletter Eigenbau inklusive Geometriekern.
- **Empfehlung:** 1 und 2 kombiniert. Das CAD ist dann trotzdem **deins und in die App eingebaut**, aber wir erfinden das Rad nicht neu. Die Entscheidung kommt verbindlich im Plan (`ENTSCHEIDUNGEN.md`).

## 9. 💡 Weitere Vorschläge von Claude

1. **Schmales, durchgehendes Band zuerst:** erst einmal alle Phasen in einfacher Form am Beispiel Windkraftanlage (Anforderung → Rotor-/Wellenberechnung → parametrisches Bauteil → Arbeitsplan → Prüfprotokoll), dann jede Phase vertiefen.
2. **Vorlagen je Produkttyp:** „Kleinwindanlage“ als erste Vorlage mit passenden Anforderungen, Berechnungen, Prüfplänen und Normen; später weitere (Fördertechnik, Vorrichtung, Getriebemotor).
3. **PDF-Protokolle** für Berechnungen, Prüfungen und Inbetriebnahme – direkt nutzbar für CE-Dokumentation.
4. **Lokal und offline:** Daten und Bücher bleiben auf deinem Mac, keine Cloudkosten.
5. **Modular aufgebaut:** Jedes Modul (TRIZ, Berechnung, CAD, QM, PM …) ist ein eigener Baustein, der auf das gemeinsame Produktmodell zugreift. So kann die App Schritt für Schritt wachsen.

💡 Möglicher erster Umfang (Vorschau aufs Lastenheft, noch nicht verbindlich):
- Desktop-App mit Produktprojekt, Phasen und Freigaben
- Anforderungen mit Zielwerten
- Berechnungen: Rotorauslegung, Antriebsstrang/Getriebeübersetzung, Hauptwelle – mit PDF-Protokoll
- Erstes parametrisches 3D-Bauteil (Hauptwelle) aus den Berechnungswerten
- Einfache Stückliste und Verknüpfung Anforderung ↔ Berechnung ↔ Bauteil

## 10. Was bewusst NICHT dazugehört (vorerst)

- Keine eigene FEM-Simulation und Strömungssimulation in der ersten Ausbaustufe (später als Modul denkbar).
- Kein eigener Geometriekern (Empfehlung siehe Abschnitt 8).
- Kein ERP/Warenwirtschaft (Einkauf, Lager, Buchhaltung).
- Keine Cloud, kein Mehrbenutzer-Server in der ersten Version.
- Keine Weitergabe der gescannten Buchinhalte.
- Keine elektrische Netzanbindung/Zertifizierung der Windkraftanlage in der App (nur Checklisten und Verweise).

## 11. Geklärte Fragen (04.11.2026)

1. **CAD:** Eigenes CAD auf einem bewährten Geometriekern (Open CASCADE) – ✅ bestätigt.
2. **Rechner:** Nur macOS.
3. **Windkraftanlage:** Wird real gebaut → Berechnungen und Nachweise richten sich an IEC 61400-2 (Kleinwindenergieanlagen) und der Maschinenverordnung aus.
