# Idee – YamProduktion
Version: 0.1   ·   Status: 📝 Entwurf   ·   Datum: 04.11.2026

## Versionsverlauf
| Version | Datum | Änderung | Status |
|---------|-------|----------|--------|
| 0.1 | 04.11.2026 | Erster Entwurf aus Yamines Idee | Entwurf |

---

## 1. Projektname und Ein-Satz-Beschreibung

**YamProduktion** – eine App, die ein Produkt durch seinen ganzen Lebenszyklus führt: von der ersten Idee über Anforderungen, Berechnung und Konstruktion bis zu Fertigung, Montage und Inbetriebnahme. Alles aus einer Hand.

## 2. Problem

Wer ein technisches Produkt entwickelt, springt heute zwischen vielen Werkzeugen hin und her: Notizen für die Idee, Word für das Lastenheft, Excel oder Taschenrechner für die Auslegung, ein CAD-Programm für die Zeichnung, wieder Excel für Arbeitspläne und Stücklisten, separate Listen für Qualität und Projektplanung. Dabei geht der rote Faden verloren:

- Eine geänderte Anforderung (z. B. höheres Drehmoment) wirkt sich nicht automatisch auf Berechnung, Bauteile und Fertigung aus.
- Formeln und Wissen aus den Fachbüchern stecken im Regal statt im Arbeitsablauf.
- Nachweise (Festigkeit, Sicherheit, Normen) sind schwer nachvollziehbar.

## 3. Zielgruppe

- **Zuerst:** Yamine selbst – Ingenieur, der Produkte von der Idee bis zur Inbetriebnahme allein durchziehen möchte.
- 💡 Vorschlag: Später kleine Teams und Einzelkonstrukteure im Maschinen- und Anlagenbau (Sondermaschinen, Vorrichtungen, Antriebstechnik), für die große PLM-Systeme (Teamcenter, Windchill) zu teuer und zu schwer sind.

## 4. Kernidee

Ein **durchgehender roter Faden**: Jede Phase baut auf den Daten der vorherigen auf. Eine Anforderung wird zu einer Funktion, die Funktion zu einer Berechnung, die Berechnung zu einem Bauteil, das Bauteil zu einem Fertigungsschritt, alles zusammen zu einer Montage und schließlich zu einem geprüften, in Betrieb genommenen Produkt.

💡 Vorschlag: Das Herzstück ist ein **gemeinsames Produktmodell** (eine Datenbasis), nicht viele einzelne Werkzeuge. Ändert sich etwas, zeigt die App, welche nachfolgenden Schritte neu geprüft werden müssen („Änderung wirkt auf: Welle W1 → Lagerberechnung → Arbeitsplan AP-03“).

## 5. Die Phasen des Produktlebenszyklus

Geordnet nach dem Ablauf. Jede Phase hat ein klares Ergebnis und ein „Tor“ (Freigabe), bevor es weitergeht.

| Nr | Phase | Was passiert | Ergebnis |
|----|-------|--------------|----------|
| P1 | **Idee** | Idee festhalten, Problem, Nutzen, Zielmarkt, erste Skizzen | Ideensteckbrief |
| P2 | **Anforderungen** | Eigenschaften, Attribute, Funktionen definieren; Muss/Soll/Kann; Zielwerte mit Einheiten (z. B. Last 500 kg, Hub 300 mm) | Lastenheft, Funktionsstruktur |
| P3 | **Konzept** 💡 | Lösungsvarianten suchen (morphologischer Kasten), bewerten (Nutzwertanalyse), beste auswählen | Gewähltes Konzept, Prinzipskizze |
| P4 | **Berechnung & Auslegung** | Antriebe (Motor, Leistung, Drehmoment), Getriebe (Übersetzung, Zahnräder), Wellen, Lager, Schrauben, Federn, Festigkeit, Sicherheitsnachweise | Berechnungsprotokolle, Nachweise |
| P5 | **Konstruktion & Zeichnung** | 3D-Modell, Baugruppen, technische Zeichnungen, Stückliste | CAD-Modelle, Zeichnungen, Stückliste |
| P6 | **Fertigungsplanung** | Fertigungsverfahren wählen, Arbeitspläne, Rohteile, Zeiten, Kosten, Eigen- oder Fremdfertigung | Arbeitspläne, Kostenkalkulation |
| P7 | **Montage** | Montagereihenfolge, Montageplatte / Vorrichtung, Montageanleitung, Prüfschritte | Montageplan, Montageanleitung |
| P8 | **Inbetriebnahme** | Checklisten, Funktionstests, Messprotokolle, Abnahme, Übergabe an Kunden | Inbetriebnahmeprotokoll, Abnahme |
| P9 | **Betrieb & Rückmeldung** 💡 | Wartungsplan, Ersatzteile, Erfahrungen zurück in die Idee der nächsten Version | Wartungsplan, Verbesserungsliste |

### Querschnitt über alle Phasen

| Bereich | Was dazugehört |
|---------|----------------|
| **Projektmanagement** | Meilensteine, Aufgaben, Termine, Aufwand, Status je Phase |
| **Qualitätsmanagement** | Prüfpläne, Toleranzen, FMEA (Fehler-Möglichkeits- und Einflussanalyse), Abweichungen, Maßnahmen, Prüfprotokolle |
| **Sicherheit & Normen** 💡 | Risikobeurteilung nach Maschinenrichtlinie / Maschinenverordnung (EU) 2023/1230, CE-Unterlagen, technische Dokumentation |
| **Dokumente & Versionen** | Jede Zeichnung, Berechnung und Liste mit Version und Freigabestatus |
| **Wissensbasis** | Fachbücher, Formeln, Normen, Werkstoffdaten (siehe Abschnitt 7) |

## 6. Hauptfunktionen (nach Wichtigkeit)

1. **Produktprojekt anlegen und durch die Phasen führen** – mit Fortschrittsanzeige und Freigabe je Phase.
2. **Anforderungen strukturiert erfassen** – Eigenschaften, Attribute und Funktionen mit Zielwert, Einheit, Priorität.
3. **Berechnungsmodule für den Maschinenbau** – zuerst die häufigsten:
   - Antriebsauslegung (Leistung, Drehmoment, Drehzahl, Beschleunigung, Motorauswahl)
   - Getriebeberechnung (Übersetzung, Stirnrad-Grundgeometrie, Tragfähigkeit vereinfacht)
   - Welle (Biegung, Torsion, Vergleichsspannung, Sicherheit)
   - Lager (Lebensdauer L10)
   - Schraubenverbindung (Vorspannkraft, Sicherheit)
   - Jede Berechnung mit Formel, Eingaben, Ergebnis, Sicherheitsfaktor und Quellenangabe → druckbares Protokoll.
4. **Rückverfolgung** – Anforderung → Berechnung → Bauteil → Arbeitsschritt → Prüfung. Bei Änderungen zeigt die App, was betroffen ist.
5. **Stückliste und Bauteilverwaltung** – zentrale Liste aller Teile, Normteile, Zukaufteile.
6. **Fertigungs- und Montagepläne** – Arbeitsschritte, Maschinen, Zeiten, Montagereihenfolge, Montageplatte.
7. **Qualität und Inbetriebnahme** – Prüfpläne, Checklisten, Protokolle.
8. **Projektmanagement** – Aufgaben, Termine, Status.
9. **Wissensassistent** – Fragen an die eigenen Fachbücher („Welche Formel für Flächenpressung bei Passfedern?“) mit Seitenangabe.

## 7. Wissensbasis aus den eigenen Ingenieurbüchern

**Idee:** Yamine scannt seine Fachbücher (z. B. Roloff/Matek, Decker, Dubbel, Tabellenbuch Metall). Die App macht sie durchsuchbar und nutzt sie als Nachschlagewerk.

💡 Vorschlag, wie das sinnvoll funktioniert:
- **Durchsuchen statt Abschreiben:** Die Scans werden per Texterkennung (OCR) lesbar gemacht und lokal indexiert. Eine Frage liefert die passenden Seiten mit Buch und Seitenzahl.
- **Formeln gezielt übernehmen:** Die Berechnungsmodule werden von Hand (bzw. mit Claude) nach den Formeln aus Büchern und Normen programmiert. Jedes Modul nennt seine Quelle („nach Roloff/Matek, Kap. 11“). Die App rechnet mit geprüften Formeln, nicht mit „geratenen“ Antworten einer KI.
- **Belegt und unbelegt getrennt:** KI-Antworten werden immer als Vorschlag gekennzeichnet, geprüfte Formeln und Werte als belegt.

⚠️ Hinweis zum Urheberrecht: Gescannte Bücher sind geschützt. Für die **eigene, private Nutzung** auf dem eigenen Rechner ist das in der Regel unproblematisch (Privatkopie, § 53 UrhG – bei ganzen Büchern gelten allerdings Grenzen; im Zweifel nur Auszüge oder legal gekaufte E-Books nutzen). **Nicht erlaubt** wäre, die Scans oder ganze Textpassagen in einer App an andere weiterzugeben oder online zu veröffentlichen. Darum: Scans bleiben **lokal und privat**. Sollte die App später an andere gehen, liefert sie nur die selbst programmierten Berechnungen und Quellenhinweise, nie den Buchinhalt.

## 8. 💡 Verbesserungs- und Optimierungsvorschläge von Claude

1. **Nicht alles neu bauen – vor allem kein eigenes CAD.** Ein CAD-Programm selbst zu entwickeln wäre ein Projekt für Jahre. Besser: ein vorhandenes CAD anbinden (z. B. FreeCAD – kostenlos und per Python steuerbar – oder das CAD, das du schon nutzt, über Export von Stückliste, STEP und PDF). Die App liefert Maße aus der Berechnung an das CAD und holt Stückliste und Zeichnungen zurück.
2. **Mit Maschinenbau-Berechnungen starten.** Dort liegt der größte Mehrwert gegenüber Word/Excel, und dort hilft dein Fachwissen am meisten.
3. **Ein Beispielprodukt als roter Faden.** Wir entwickeln die App an einem echten Produkt (z. B. ein Hubtisch oder ein Förderband mit Motor und Getriebe). So ist jeder Schritt sofort testbar.
4. **Vorlagen je Produkttyp.** Später: Vorlagen wie „Fördertechnik“, „Vorrichtung“, „Getriebemotor-Anwendung“ mit passenden Anforderungen, Berechnungen und Prüfplänen.
5. **Berechnungsprotokolle als PDF** – sofort nutzbar für Kunden, Prüfer und CE-Dokumentation.
6. **Lokal und offline zuerst.** Deine Daten und Bücher bleiben auf deinem Rechner; keine Cloudkosten.
7. **Schrittweise wachsen.** Erst ein schmales, aber durchgehendes Band durch alle Phasen (Anforderung → Berechnung → Stückliste → Arbeitsplan → Prüfprotokoll), dann jede Phase vertiefen.

💡 Möglicher erster Umfang (Vorschau auf das Lastenheft, noch nicht verbindlich):
- Produktprojekt mit Phasen und Freigaben
- Anforderungen mit Zielwerten
- 3 Berechnungsmodule: Antrieb, Getriebeübersetzung, Welle – mit PDF-Protokoll
- Einfache Stückliste und Verknüpfung Anforderung ↔ Berechnung ↔ Bauteil

Die genaue Technik (z. B. lokale Web-App im Browser mit Python im Hintergrund und einer kleinen SQLite-Datenbank) wird erst im Plan festgelegt und begründet.

## 9. Was bewusst NICHT dazugehört (vorerst)

- Kein eigenes CAD-Programm und keine eigene FEM-Simulation (vorhandene Werkzeuge anbinden).
- Kein ERP/Warenwirtschaft (Einkauf, Lager, Buchhaltung).
- Keine Cloud, kein Mehrbenutzer-Server in der ersten Version.
- Keine Weitergabe der gescannten Buchinhalte.
- Keine vollständige Normenbibliothek (Normen sind kostenpflichtig; nur Verweise und eigene Auszüge).

## 10. Offene Fragen

1. **Zielplattform:** Soll die App auf deinem Mac im Browser laufen (lokal, offline), als Desktop-Programm oder auch auf dem Handy/Tablet?
2. **Produktbereich und Beispielprodukt:** Welche Produkte entwickelst du typischerweise (z. B. Sondermaschinen, Vorrichtungen, Antriebe, Fördertechnik)? Hast du ein konkretes Produkt, an dem wir die App entwickeln können?
3. **Werkzeuge und Nutzer:** Welches CAD-Programm nutzt du (SolidWorks, Inventor, FreeCAD, Fusion …), und arbeitest du allein oder später mit einem Team?
