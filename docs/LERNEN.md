# Lernen – YamProduktion

## MS1 (04.11.2026)
- **Gut:** Freigabe-Ablauf Idee → Lastenheft → Plan hat das sehr große Vorhaben sauber eingegrenzt (CAD auf Geometriekern statt Eigenbau).
- **Gut:** Screenshot-Tests haben zwei Darstellungsfehler sofort gezeigt (überlappende Prüfhinweise, leere Eingabefelder).
- **Erkenntnis Qt:** `QDoubleSpinBox` mit `setButtonSymbols(NoButtons)` plus Stylesheet-Padding zeigt in Fusion keinen Text. Lösung: Pfeil-Knöpfe per Stylesheet unsichtbar machen statt NoButtons.
- **Erkenntnis Qt:** Widgets aus Layouts immer mit `hide()` + `setParent(None)` entfernen, sonst bleiben sie bis zum nächsten Event-Durchlauf sichtbar und überlappen.
- **Erkenntnis Ablage:** Der geteilte Projektordner behält das Ausführungsrecht von `.command`-Dateien nicht – im README `chmod +x` als Abhilfe nennen.
- **Für den Skill:** Bei Desktop-Apps mit Qt: deutsche Zahlendarstellung über `QLocale.setDefault(German)` gleich zu Beginn setzen.

## MS2 (04.11.2026)
- **Gut:** Verknüpfung nur anlegen, wenn der Eingabewert (umgerechnet) wirklich dem Anforderungswert entspricht – so entsteht keine falsche Rückverfolgung bei Handeingaben.
- **Gut:** Vor jeder Umstellung des Dateiformats automatisch sichern; Umstellung mit einer echten Datei des alten Formats testen.
- **Erkenntnis Qt:** `setCellWidget` löscht alte Widgets erst später – vorher `hide()`, sonst bleiben sie im Screenshot an falscher Stelle stehen.
- **Erkenntnis UI:** Technische Feldnamen (z. B. `leistung_el_kw`) nie anzeigen – eigene Tabelle mit lesbaren Namen.

## MS3 (04.11.2026)
- **Gut:** TRIZ-Matrix nicht aus dem Gedächtnis erzeugt, sondern aus einer Abschrift übernommen, die jede Zelle gegen drei Quellen abgleicht – mit Quellenangabe im Programm und Stichproben-Test.
- **Erkenntnis Tests:** Ein modaler Dialog (`QMessageBox`) hält einen Offscreen-Test unbegrenzt an. Lösung: Dialoge im Test automatisch beantworten (Fixture) und pytest immer mit Zeitlimit starten.
- **Erkenntnis Qt:** `QComboBox` wächst mit dem längsten Eintrag und macht die ganze Seite zu breit. Lösung: `AdjustToMinimumContentsLengthWithIcon` mit fester Mindestlänge.
- **Erkenntnis Qt:** Tabellen in einer scrollenden Seite brauchen eine feste Höhe aus Kopf + Zeilenzahl, sonst werden sie zusammengedrückt und überlappen den Text darunter.

## MS4 (04.11.2026)
- **Gut:** Eine gemeinsame Rechenseite, die aus der Feldbeschreibung im Rechenmodul entsteht – neue Berechnungen brauchen keine eigene Oberfläche mehr (wichtig für die vielen Maschinenelemente in MS5).
- **Gut:** Normformeln nur mit Quelle übernehmen; was nur aus dem Gedächtnis stammt, im Ergebnis und im PDF als „unbelegt“ kennzeichnen.
- **Erkenntnis:** Übernommene Werte werden im Eingabefeld gerundet angezeigt. Damit die Kette exakt rechnet, wird der genaue Wert gemerkt und verwendet, solange das Feld nicht von Hand geändert wird.
- **Erkenntnis:** Bei verketteten Berechnungen muss „neu berechnen“ die Reihenfolge der Abhängigkeiten einhalten; sonst rechnet eine Folgeberechnung mit veralteten Werten. Eine Berechnung mit veralteter Quelle verweigert das Neu-Rechnen mit klarer Meldung.

## MS5 (04.11.2026)
- **Gut:** Der gemeinsame Rechenrahmen aus MS4 hat sich bezahlt gemacht: neun neue Berechnungen ohne eine einzige neue Oberfläche.
- **Gut:** Testbeispiele so wählen, dass sie eine physikalische Bilanz prüfen (Bremse: Arbeit der Bremse = Bewegungsenergie + Arbeit des Rotors), nicht nur die eigene Formel noch einmal abtippen.
- **Erkenntnis Fachlich:** Beim Getriebe die Richtung klar festlegen. In einer Windkraftanlage treibt der Rotor den Planetenträger, die Sonne läuft schnell. Das Moment an der Sonne ist also das Rotormoment geteilt durch die Übersetzung.
- **Erkenntnis:** Standard-Beispielwerte so wählen, dass alle Nachweise erfüllt sind, sonst wirken Screenshots und Beispiel-PDFs wie Fehler. Der Test prüft das.
- **Erkenntnis Qt:** Mit vielen Einträgen braucht die Seitenleiste Gruppenüberschriften (nicht wählbare Einträge) und kleinere Unterpunkte, sonst passt sie nicht auf den Bildschirm.
- **Erkenntnis Tests:** Die Oberflächen-Tests dauern zusammen über zwei Minuten. Getrennt nach Datei starten oder das Zeitlimit erhöhen.

## MS6 (04.11.2026)
- **Gut:** Bauteil-Vorlagen beschreiben ihre Parameter genauso wie Berechnungen (Felder, Quellen). Dadurch funktionieren Übernahme, Verknüpfung und „neu prüfen“ ohne neuen Code.
- **Gut:** Geometrie gegen geschlossene Formeln testen (Volumen abgesetzter Wellen, Flansch mit Löchern, Zahnprofilfläche, Zahndicke am Teilkreis = π·m/2, Halbschnitt = halbes Volumen) und STEP hin und zurück lesen.
- **Erkenntnis OCP:** Ab Version 7.8 heißen statische Methoden ohne „_s“ (`TopoDS.Edge` statt `TopoDS.Edge_s`) und Arrays liegen in `OCP.collections`. Beide Fassungen abfangen.
- **Erkenntnis CAD:** Fasen nachträglich an alle Kreiskanten zu setzen erzeugt ungültige Körper (auch an Innenkanten). Besser die Welle als Drehkörper aus einem Profil erzeugen, in das die Fasen gleich eingezeichnet sind.
- **Erkenntnis CAD:** Zahnräder aus einem Polygon haben hunderte Kanten und sehen facettiert aus. Evolventen als B-Spline und Kopf/Fuß als Kreisbogen ergeben saubere Flächen und gute STEP-Daten.
- **Für den Skill:** Große Bibliotheken zuerst einzeln prüfen (hier CadQuery: über 300 MB Zusatzpakete). Oft reicht der Kern mit einer dünnen eigenen Schicht.

## MS7 (04.11.2026)
- **Gut:** Ein Teil als Liste von Features plus Parameter-Tabelle. Bricht ein Feature, zeigt der Baum genau dieses mit Grund – alles davor bleibt sichtbar. Fehlersuche wird so einfach.
- **Gut:** Tests der Oberfläche über dieselben Wege wie mit der Maus (Klick an Skizzenkoordinaten, Bedingung auf die Auswahl), dazu Volumen gegen geschlossene Formeln (Lochkreis, Sackloch, Fase mit Eckkorrektur 4 × 1/3 mm³).
- **Erkenntnis:** Vor dem Einbinden einer Bibliothek prüfen, ob es für das **Zielsystem** fertige Pakete gibt (hier: SolveSpace nur bis Python 3.11 auf dem Mac) und welche Lizenz sie hat. Ein kleiner eigener Löser war schneller als jede Umgehung.
- **Erkenntnis Löser:** Gauß-Newton mit der kleinsten Änderung (`lstsq`) hält unterbestimmte Skizzen ruhig; Vorzeichen (Seite, Drehsinn) aus der aktuellen Lage übernehmen, sonst klappt die Skizze um. Rang der Jacobi-Matrix = Zahl der bestimmten Freiheitsgrade.
- **Erkenntnis CAD:** Verrundung R4 an allen Kanten einer 8-mm-Platte scheitert (oben und unten stoßen zusammen). Deshalb Kantenauswahl „senkrechte Kanten“ für Plattenecken.
- **Für den Skill:** Bei jeder neuen Abhängigkeit drei Fragen vor dem Einbau: Gibt es Pakete für das Zielsystem? Welche Lizenz? Wie groß?

## MS8 (04.11.2026)
- **Gut:** Erst die Projektion des Geometriekerns in einem kleinen Versuch klären (welche Richtung zeigt zum Betrachter, wie liegen die Achsen), dann die Zeichnung bauen. Das hat viel Raten gespart.
- **Gut:** Zeichnung als einfache Liste (Linie, Polygon, Text) – PDF, DXF und Bildschirm-Vorschau entstehen daraus und können nicht auseinanderlaufen.
- **Erkenntnis Zeichnung:** Wellen werden nicht längs geschnitten und brauchen nur eine Ansicht; Absatzmaße aus den **Planflächen** nehmen, nicht aus den Zylinderenden (sonst erscheinen Fasen als 1-mm-Absätze); je Durchmesser das längste Stück für den Maßtext wählen.
- **Erkenntnis Baugruppe:** Der Schwerpunkt liegt wegen der Passfedernuten 0,1 mm neben der Achse – Tests deshalb gegen das gewichtete Mittel der Einzelteile prüfen, nicht gegen „genau 0“.
- **Fehler gefunden durch Test:** Die Vorgabe „koaxial zum ersten Teil“ ging verloren, sobald ein Abstand mitgegeben wurde; Qt-Auswahllisten finden Tupel nicht wieder (`findData`) – Texte wie `teil:5` verwenden.
- **Für den Skill:** Bei Zeichnungen und Bildern das Ergebnis selbst als Bild ansehen, bevor der Test geschrieben wird.

## MS9 (04.11.2026)
- **Gut:** Fertigungszeiten als kleine Formeln mit Rechenweg in Worten – derselbe Text steht in der Oberfläche und im PDF, die Tests prüfen gegen die Handrechnung.
- **Erkenntnis Geometrie:** Open CASCADE teilt Bohrflächen manchmal in zwei Flächen (z. B. an einer Nut). Merkmale deshalb je Durchmesser zusammenfassen, sonst wird eine Bohrung doppelt geplant.
- **Erkenntnis:** Zahnräder sehen für die Merkmalserkennung wie „viele Bohrungen“ aus (Zahnlücken sind Zylinderstücke). Für Sonderteile die Vorlage als Hinweis nutzen statt der reinen Geometrie.
- **Erkenntnis Darstellung:** Geldbeträge immer mit zwei Nachkommastellen; Eingaben mit Leerzeichen als Tausendertrennung müssen wieder lesbar sein.
- **Für den Skill:** Jeder Schätz- oder Richtwert bekommt einen sichtbaren Hinweis direkt neben der Zahl (Oberfläche und PDF), nicht nur in der Dokumentation.

## MS10 (04.11.2026)
- **Gut:** Die Montageszene wird je Einbau nur einmal vernetzt; Lochkreis-Exemplare, Explosion und Montagezustand sind nur Punkt-Verschiebungen und Masken – dadurch flüssig und ohne neue Geometrie.
- **Erkenntnis Fachlich:** Die Schraubenberechnung der Vorlage rechnet in 10.9, die Normteile sind 8.8. Ein Moment darf nur bei gleicher Klasse übernommen werden – der Plan zeigt den Widerspruch jetzt an.
- **Erkenntnis:** Wird ein Wert (Anzugsmoment) in einer Tabelle geändert, muss er auch im Fließtext und in den Prüfschritten nachgezogen werden, sonst widerspricht sich die Anleitung.
- **Erkenntnis Darstellung:** Bilder für ein PDF immer mit hellem Hintergrund rendern, egal welches Thema die Oberfläche gerade hat.
- **Für den Skill:** Nachträgliche Optionen (hier: Vorrichtung) müssen alle Stellen anpassen, die von ihnen abhängen (Schritt einfügen, Text „Prismen“ → „Auflagen“), statt nur einen Schalter zu setzen.

