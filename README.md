# YamProduktion

Ein Mac-Programm, das ein Maschinenbau-Produkt von der Idee über Anforderungen, Berechnung, eigene CAD-Konstruktion, Fertigung und Montage bis zur Inbetriebnahme führt. Erstes Produkt: eine Mini-Windkraftanlage (5–10 kW).

**Aktueller Stand:** Phase 4 (Umsetzung) – Meilensteine MS1 „Minimaler Prototyp“, MS2 „Produktmodell & Rückverfolgung“ MS3 „TRIZ & Konzept“ und MS4 „Windkraft-Auslegung & Lastannahmen“ fertig. Plan: `docs/03_PLAN.md`.

## Starten (Mac)

1. Den Ordner `yamproduktion` auf den Mac kopieren (z. B. nach `Dokumente/ClaudeCodeFolder/`).
2. Im Ordner `code` auf **`start.command`** doppelklicken.
   - Beim ersten Mal legt das Skript eine eigene Python-Umgebung an und lädt die Pakete (1–2 Minuten, Internet nötig). Danach startet das Programm sofort.
   - Meldet macOS „nicht verifizierter Entwickler“: Rechtsklick auf `start.command` → **Öffnen** → Öffnen.
   - Passiert beim Doppelklick nichts: einmal im Terminal `chmod +x start.command tests.command` im Ordner `code` ausführen.
   - Benötigt Python ab 3.10 (z. B. von python.org oder `brew install python`). Fehlt es, sagt das Skript Bescheid.

## Benutzen

1. **Neues Projekt anlegen** (⌘N). Vorgeschlagen ist „Kleinwindanlage KWA-5“ mit typischen Anforderungen. Projekte liegen als `.yamp`-Datei in `Dokumente/YamProduktion/`.
2. **Anforderungen**: Text, Zielwert, Einheit, Art (Anforderung/Eigenschaft), Priorität und Status direkt in der Tabelle ändern. Alles wird sofort gespeichert, jede Änderung erhöht die Version. Rechts zeigt die **Rückverfolgung**, wovon eine Zeile abhängt, worauf sie wirkt und was sich wann geändert hat.
3. **Rotorauslegung**: „Werte aus Anforderungen übernehmen“, dann **Protokoll speichern (PDF)** (⌘S). Die Berechnung wird dabei mit den Anforderungen verknüpft.
4. **Änderung durchspielen**: Nennleistung von 5 auf 10 kW ändern → die Berechnung wird „⚠ neu prüfen“, die Übersicht zeigt einen Hinweis. Unter **Berechnungen** auf **Neu berechnen** klicken – der Verlauf zeigt „D 4,792 → 6,778 m“.
5. **Phasen freigeben** in der Übersicht: geht nur, wenn nichts mehr offen ist (Tooltip auf dem Knopf zeigt, was fehlt). Ändert sich später etwas, öffnet sich das Phasentor automatisch wieder.
6. **Sicherung**: Beim Öffnen wird automatisch eine Kopie angelegt (die letzten 10 bleiben) – Ablage › „Sicherungen im Finder zeigen“. Eine Sicherung öffnet man wie ein normales Projekt.
7. **Ideen & TRIZ**: Idee mit Problem, Nutzen, idealem Endergebnis und Ressourcen festhalten. Unter „Widerspruch lösen“ beschreiben, was besser werden soll und was sich dabei verschlechtert – die Widerspruchsmatrix zeigt die passenden Erfinderprinzipien. Lösungsidee ins Feld schreiben und beim Prinzip auf **Notieren**. Für „muss groß und klein zugleich sein“ die Art „Physikalischer Widerspruch“ wählen (Trennungsprinzipien).
8. **Funktionen**: Gesamtfunktion und Teilfunktionen als Baum (Doppelklick zum Umbenennen), Anforderungen den Funktionen zuordnen.
9. **Konzept**: je Teilfunktion Lösungswege sammeln (auch TRIZ-Ideen übernehmen), Varianten anlegen und im morphologischen Kasten zusammenstellen. Darunter Kriterien mit Gewicht und Punkte 0–10 vergeben; der Nutzwert wird sofort gerechnet, der beste markiert. Eine Variante **mit Begründung** auswählen.
10. **Produkt-Lastenheft (PDF)**: Knopf in der Übersicht – Ideen, Anforderungen nach Priorität, Eigenschaften, Funktionsstruktur, TRIZ und Konzept in einem Dokument.
11. **Berechnungen der Windkraftanlage** (unter „Berechnungen“): Rotorauslegung (jetzt mit Rotorschub), **Leistungskurve & Ertrag** (Jahresertrag aus Weibull-/Rayleigh-Verteilung), **Lastannahmen** nach IEC 61400-2 (vereinfachtes Lastmodell) und **Antriebsstrang** (Direktantrieb oder Getriebe, Generator-Anforderung). Auf jeder Seite holt „Werte aus dem Projekt übernehmen“ die passenden Anforderungen und Ergebnisse früherer Berechnungen (z. B. den Rotordurchmesser aus B-001). Ändert sich eine Anforderung, werden alle Berechnungen der Kette markiert; „Alle markierten neu berechnen“ rechnet sie in der richtigen Reihenfolge.
    - Wichtig: Der mittlere Wind am Standort ist eine Annahme (4,5 m/s in 10 m Höhe), bis du einen echten Wert einträgst. Massen und Abstände in den Lastannahmen sind Annahmen bis zur Konstruktion.
    - Gelb markiert = **unbelegt** (Lastfälle E und F, Klassenwerte): vor dem Bau mit dem Normtext IEC 61400-2 prüfen.
12. **Maschinenelemente** (Seitenleiste, Gruppe „Maschinenelemente“): Welle, Lager, Schrauben, Passfeder, Pressverband, Schweißnaht, Getriebe, Turm & Fundament, Bremse. Empfohlene Reihenfolge: zuerst Lastannahmen und Antriebsstrang speichern, dann **Turm** (holt Schub und Extremwind aus den Lasten), danach **Schrauben** und **Schweißnaht** (holen Schraubenkraft und Moment aus dem Turm). Welle, Lager und Passfeder holen ihre Lasten aus den Lastannahmen, das Getriebe aus dem Antriebsstrang.
    - Gelb markiert = unbelegt (z. B. Kerbfaktoren, Richtwerte für Sicherheiten, Haftbeiwerte). Die **Tragzahlen der Lager** sind Platzhalter: echte Werte aus dem Katalog des gewählten Lagers eintragen.
    - Turm und Fundament ersetzen nicht den Standsicherheitsnachweis eines Tragwerksplaners für die Baugenehmigung.
13. **Bauteile (3D)** (Seitenleiste › Konstruktion): Vorlage wählen (Welle, Flansch, Nabe, Zahnrad), **Werte aus dem Projekt übernehmen** holt die Maße aus den gespeicherten Berechnungen. Das Teil erscheint sofort in 3D mit Masse. Drehen mit der Maus, Mausrad zoomt, Doppelklick zeigt alles. **Schnitt** zeigt einen Halbschnitt. **Als Bauteil speichern** (⌘S) legt T-001 … an; **STEP/STL exportieren** für Fertiger bzw. 3D-Druck. Ändert sich später eine Berechnung, steht das Teil auf „neu prüfen“ – unten in der Liste **Neu erzeugen** klicken.
14. **Modellieren** (Seitenleiste › Konstruktion): freie Teile. **+ Skizze** öffnet den Skizzen-Editor: Werkzeug wählen (Linie, Rechteck, Kreis, Bogen) und in die Fläche klicken; Klicks nahe an einem Punkt rasten dort ein. Dann mit **Auswahl** Linien/Kreise anklicken (⇧ für mehrere) und rechts eine Bedingung oder ein Maß setzen (z. B. **Ø …** → `D`). Unten steht, ob die Skizze vollständig bestimmt ist. **Skizze fertig**, dann **+ Extrusion** oder **+ Rotation**, danach Bohrung, Muster, Fase, Verrundung. Die Maße stehen unten in der **Parameter-Tabelle** – Formeln wie `d + 80` und Werte aus Berechnungen wie `ber("welle", "d")` sind erlaubt. Ein ⚠ im Feature-Baum zeigt, welches Feature nicht passt und warum. **+ Import** liest eine STEP-Datei ein. **Als Bauteil speichern** (⌘S) – das Teil steht dann auch in der Bauteil-Liste und folgt Änderungen der Berechnungen.
15. **Baugruppen** (Seitenleiste › Konstruktion): **+ Bauteil** baut ein gespeichertes Teil ein, **+ Normteil** eine Schraube, Mutter, Scheibe, ein Lager oder eine Passfeder (aus der Liste oder eintippen, z. B. `ISO 4762 M16x50`, `22216 E`). Neue Teile stehen zuerst **koaxial** zum ersten Teil; links den **Abstand entlang der Achse** (Formel erlaubt), **umdrehen** und einen **Lochkreis** (Anzahl, Radius) setzen. Masse, Schwerpunkt und die **Stückliste** entstehen sofort; Export als CSV (Excel/Numbers) oder PDF. **Baugruppe speichern** legt G-001 … an; ändert sich ein eingebautes Teil, steht die Baugruppe auf „neu prüfen“.
16. **Zeichnungen**: Teil oder Baugruppe wählen – die Zeichnung (A3, Projektionsmethode 1, Schriftfeld, Allgemeintoleranz ISO 2768-mK) entsteht automatisch mit Ansichten, Schnitt A–A bei Bohrungen, Gesamtmaßen, Durchmessern, Absätzen und Lochkreisen; Baugruppen mit Positionsnummern und Stückliste. **Passmaße** eintragen wie `Ø80 k6; Ø140 H7`. **Als PDF** oder **Als DXF** (für CAD-/Laserprogramme) speichern. Funktionsmaße bitte prüfen und ergänzen.
17. **Arbeitspläne** (Seitenleiste › Fertigung): Bauteil wählen – Rohteil (z. B. Rundstahl Ø95 × 848) und Arbeitsgänge (Sägen, Drehen, Fräsen, Bohren …) werden aus der 3D-Geometrie vorgeschlagen, mit Drehzahl, Vorschub und Hauptzeit (Rechenweg unten). Alles ist änderbar: Rohteilmaße, Beschreibung, Maschine, Rüstzeit t_r, Stückzeit t_e (leer = berechnet), Losgröße, **Eigen- oder Fremdfertigung** mit Angebotspreis. **Arbeitsplan speichern** legt AP-001 … an, **PDF** druckt ihn mit Rechenweg und Kosten.
18. **Kosten & Anfragen**: Baugruppe wählen – Herstellkosten aus Arbeitsplänen und Zukaufpreisen (Preis für Lager/Schrauben direkt in die Tabelle schreiben). Darunter die **Kostensätze** des Projekts (€/h je Maschine, €/kg je Werkstoff) – die Vorgaben sind Schätzwerte, bitte durch eigene ersetzen. Unten die **Anfrageliste** aller fremd gefertigten Teile als PDF für die Angebotsanfrage.
19. **Montagepläne** (Seitenleiste › Montage): Baugruppe wählen – die Montageschritte werden vorgeschlagen (Grundteil, Lager warm aufziehen, Nabe aufschrumpfen mit Temperatur aus dem Pressverband, Schrauben über Kreuz mit Anzugsmoment, Endkontrolle), jeweils mit Werkzeugen, Prüfschritten zum Abhaken und Zeit. Alles änderbar, Schritte mit ↑ ↓ verschieben. **Montageplatte aus der Baugruppe erzeugen** legt die Vorrichtung als eigenes Bauteil an (unter „Bauteile (3D)“ änderbar). Der Schieber **Explosion** zieht die Baugruppe auseinander. **Anleitung als PDF** druckt alles mit Bildern je Schritt.
20. **Werkstoffe**: Nachschlagetabelle mit Streckgrenze, Zugfestigkeit, E-Modul und Dichte (Werte bitte mit dem Tabellenbuch abgleichen).
21. Tastenkürzel: ⌘B Seitenleiste ein/aus · ⌘⇧D Hell/Dunkel · ⌘O Projekt öffnen · ⌘W Projekt schließen.

Projekte aus MS1 und MS2 werden beim Öffnen automatisch auf das neue Format umgestellt (vorher wird gesichert).

Beispiele (Berechnungsprotokolle Rotor, Ertrag, Lastannahmen, Turm, Schweißnaht, Getriebe, Produkt-Lastenheft, Hauptwelle als STEP, Zeichnungen Hauptwelle (PDF/DXF) und Gondel mit Stückliste, Arbeitsplan Hauptwelle, Kalkulation Gondel, Anfrage Fremdfertigung) liegen in `daten/beispiele/`.

**TRIZ-Daten:** Die Widerspruchsmatrix stammt aus einer geprüften, frei verfügbaren Abschrift (Quelle steht im Programm unter jeder Empfehlung). Bitte einige Zellen mit dem eigenen TRIZ-Buch vergleichen.

## Tests

Doppelklick auf `code/tests.command` (nach dem ersten Start). Prüft die Rechnungen gegen Handrechnung, die Projektdatei, das PDF und die Oberfläche; Screenshots (hell/dunkel) landen in `code/tests/screenshots/`.

## Ordner

- `docs/` – Idee, Lastenheft, Plan, Entscheidungen (versioniert, ältere Fassungen in `docs/archiv/`)
- `code/src/yamproduktion/` – Programm (`berechnungen/`, `ui/`, `modell.py`, `pdf.py`, `einheiten.py`)
- `code/tests/` – automatische Tests
- `daten/` – Beispieldaten
