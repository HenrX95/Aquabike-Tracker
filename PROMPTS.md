# Coach-Routinen

Die Alternative zu Cowork: nicht eine Software, die von selbst läuft, sondern feste Rituale
mit fertigen Prompts. Du kopierst einen Block, ich mache den Rest. Aufwand für dich:
30 Sekunden täglich, 10 Minuten sonntags.

**Voraussetzung:** Diese Prompts in einem Chat im Projekt *Aquabike* verwenden — dort liegen
Trainingsplan und Tracker, ich habe sie also automatisch im Zugriff. `dashboard.json` entweder
per Raw-URL (öffentliches Repo) oder als Anhang.

---

## Täglich (morgens, ~60 Sekunden)

> Daily Check. Hier ist dashboard.json: [URL oder Datei anhängen]
>
> 1. Nenn mir die heutige Einheit laut Plan (Standard-Trainingswoche, Abschnitt 4) mit den
>    konkreten Intervallen für die aktuelle Phase.
> 2. Prüfe die Ampeln. Wenn eine rot ist, sag mir, was ich an der heutigen Einheit ändere.
> 3. Ein Satz zur Ernährung: welcher Tagestyp ist heute, wie viele kcal.
>
> Maximal 8 Zeilen. Keine Motivationssprüche.

---

## Wöchentlich (Sonntagabend, ~10 Minuten)

> Wochenreview Woche [N]. dashboard.json anbei.
>
> Analysiere:
> - **Compliance**: Soll vs. Ist bei Schwimmen (3), Rad (3), Gym (2). Wo ist die Lücke?
> - **Last**: sRPE-Trend über die letzten 4 Wochen. Steigerung im Rahmen von 10–15 %?
> - **Regeneration**: RHF-Trend, Schlaf, Oura-Readiness. Zeichen von Überlastung?
> - **Knie**: Ampelstatus. Gym-Progression freigeben oder halten?
> - **Gewicht**: Wochentrend gegen die ~0,4–0,5 kg/Woche. Zu schnell → Kalorien hoch.
>
> Dann: konkrete Einheiten für die kommende Woche, Tag für Tag, mit Intervallen und
> Zielwerten. Wenn du etwas gegenüber dem Plan änderst, begründe es.
>
> Sei ehrlich, wenn eine Woche schlecht war. Ich brauche keinen Cheerleader.

---

## Nach jedem Test (Woche 1, 6, 14, 20, 26)

> Testauswertung Woche [N]. Ergebnisse:
> - FTP: [X] W (vorher [Y] W)
> - CSS: [MM:SS]/100m (vorher [MM:SS])
> - Gewicht: [X] kg · Taille: [X] cm
>
> Vergleiche gegen die Meilenstein-Tabelle (Abschnitt 11). Liege ich auf Kurs für
> 285 W / CSS 1:45 im Dezember? Wenn nicht: was ändern wir, und woran erkenne ich in
> 4 Wochen, ob es gewirkt hat?
>
> Wenn ich vorne liege: nach oben umplanen, wie im Plan vorgesehen.

---

## Bei Störungen

**Krankheit / Pause**
> Ich war [N] Tage raus wegen [Grund]. Aktuelle Woche: [N]. Wie steige ich wieder ein,
> ohne den Plan zu verlieren? Was streiche ich, was hole ich nicht nach?

**Knie meldet sich**
> Knieschmerz [X]/10 seit [Datum], bei [Übung/Einheit]. Was regressiere ich konkret?
> Ab wann muss ich zum Arzt statt zu dir?

**Woche bricht zusammen**
> Diese Woche schaffe ich nur [N] Stunden. Priorisiere nach der Regel aus Abschnitt 4.

---

## Monatlich: Ernährung

> Monatsreview Ernährung. Gewichtsverlauf und Taille aus dashboard.json.
>
> Trend gegen die Prognose (~0,4–0,5 kg/Woche, ~85–86 kg im Dezember)? Taille ~1 cm/Monat?
> Falls zu schnell oder zu langsam: welche Mahlzeit ändere ich wie — keine Snacks einführen,
> sondern Portionen anpassen wie im Plan beschrieben.

---

## Warum keine echte Automatisierung meiner Antworten

Ein Skript könnte theoretisch die Anthropic-API nächtlich anrufen und dir eine Mail schicken.
Technisch machbar, aber: das kostet API-Guthaben, die Antwort hätte keinen Zugriff auf euren
Projektkontext, und du würdest sie morgens überfliegen statt zu lesen. Der Wert entsteht im
Dialog — wenn du zurückfragst, widersprichst, Kontext lieferst, den keine Zahl kennt.

Das Dashboard ersetzt die tägliche Information. Ich ersetze die wöchentliche Entscheidung.
