# Coach-Routinen – IRONMAN 70.3 Venice-Jesolo (24.04.2027)

**Radziel: 90 km konstant 235–250 W · FTP-Ziel 300 W · 38 Wochen ab 03.08.2026**

Nicht eine Software, die von selbst läuft, sondern feste Rituale mit fertigen Prompts.
Du kopierst einen Block, ich mache den Rest. Aufwand für dich: 30 Sekunden täglich,
10 Minuten sonntags.

**Voraussetzung:** Diese Prompts in einem Chat im Projekt *IRONMAN 70.3* verwenden — dort liegen
Trainingsplan und Tracker, ich habe sie also automatisch im Zugriff. `dashboard.json` entweder
per Raw-URL (öffentliches Repo) oder als Anhang.

Raw-URL: https://raw.githubusercontent.com/HenrX95/Aquabike-Tracker/main/data/dashboard.json

---

## Täglich (morgens, ~60 Sekunden)

> Daily Check. Hier ist dashboard.json: [URL oder Datei anhängen]
>
> 1. Nenn mir die heutige Einheit laut Plan (Standard-Trainingswoche, Abschnitt 8) mit den
>    konkreten Intervallen für die aktuelle Phase.
> 2. Prüfe die Ampeln (sRPE, RHF, HRV, Knie, Schlaf). Wenn eine rot oder amber ist, sag mir,
>    was ich an der heutigen Einheit ändere.
> 3. Ein Satz zur Ernährung: welcher Tagestyp ist heute, wie viele kcal.
>
> Maximal 8 Zeilen. Keine Motivationssprüche.

---

## Wöchentlich (Sonntagabend, ~10 Minuten) — der eigentliche Hebel

Das Dashboard zeigt dir täglich die Zahlen. Dieser Review ist die wöchentliche Entscheidung:
was änderst du. Ohne dieses Ritual ist das ganze System ein Thermometer ohne Arzt.

> Wochenreview Woche [N]. dashboard.json anbei.
>
> Analysiere:
> - **Compliance**: Soll vs. Ist laut `plan.sport_targets` im Dashboard (Rad steigt ab Woche 19 auf 4). Wo ist die Lücke?
> - **Last**: sRPE-Trend über die letzten 4 Wochen. Steigerung im Rahmen von 10–15 %?
> - **Regeneration**: RHF- und HRV-Trend, Schlaf, Oura-Readiness. Zeichen von Überlastung?
> - **Knie**: Ampelstatus. Gym- und Geh-Progression freigeben oder halten?
> - **Gehen**: längste Einheit diese Phase — bin ich auf der Progression (siehe Abschnitt 7)?
> - **Rennleistung**: längster Block ≥235 W gegen die Wegmarke (W14 45' · W20 60' · W24 75' · W28 90' · W31 120' · W33 150'). Das ist die Leitkennzahl.
> - **Aero**: Minuten in Position diese Woche. Auf Kurs für 2,5 h am Renntag?
> - **Gewicht**: Wochentrend gegen ~0,3 kg/Woche bis Woche 28, danach Erhaltung. Zu schnell → Kalorien hoch.
> - **Prognose**: Was sagt der forecast-Block auf den Renntag? Auf Kurs oder unter Plan?
>
> Dann: konkrete Einheiten für die kommende Woche, Tag für Tag, mit Intervallen und
> Zielwerten. Wenn du etwas gegenüber dem Plan änderst, begründe es.
>
> Sei ehrlich, wenn eine Woche schlecht war. Ich brauche keinen Cheerleader.

---

## Nach jedem Test (Woche 1, 14, 20, 28, 33, 35)

> Testauswertung Woche [N]. Ergebnisse:
> - FTP: [X] W (vorher [Y] W)
> - CSS: [MM:SS]/100m (vorher [MM:SS])
> - Aero-30-min: [X] W / [X] km/h (falls getestet)
> - Längster Block ≥235 W: [X] min · Decoupling [X] %
> - Längster Gehtest: [X] km, Knie danach [X]/10
> - Gewicht: [X] kg · Taille: [X] cm
>
> Vergleiche gegen die Meilenstein-Tabelle (Abschnitt 12). Liege ich auf Kurs für
> FTP 300 W, 235–250 W über 90 km und CSS ~1:50? Wenn nicht: was ändern wir, und
> woran erkenne ich in 4 Wochen, ob es gewirkt hat?
>
> Wenn ich vorne liege: nach oben umplanen, wie im Plan vorgesehen.

---

## Aero-Position (ab Phase 3, wenn der Aufsatz montiert ist)

> Aero-Check. Ich fahre seit [N] Wochen mit Aufsatz. Aktuell halte ich die Position
> [X] Minuten am Stück bevor Rücken/Nacken/Hüftbeuger zu sehr ziehen. Wattverlust
> gegenüber aufrecht: [ca. X W].
>
> Ist das auf Kurs für 2,5 h Renndistanz? Halte ich die 235–250 W in Position oder verliere ich Watt?
> Was an Position, Rumpf-Gym oder Aufbau ändere ich?
> Und: meldet sich das Knie durch die Hüftbeuger-Belastung?

---

## Bei Störungen

**Krankheit / Pause**
> Ich war [N] Tage raus wegen [Grund]. Aktuelle Woche: [N]. Wie steige ich wieder ein,
> ohne den Plan zu verlieren? Was streiche ich, was hole ich nicht nach?

**Knie meldet sich**
> Knieschmerz [X]/10 seit [Datum], bei [Übung/Einheit/Gehtest]. Was regressiere ich konkret?
> Ab wann muss ich zum Arzt statt zu dir?

**Woche bricht zusammen**
> Diese Woche schaffe ich nur [N] Stunden. Priorisiere nach der Regel aus Abschnitt 8
> (2 Schwimmen, lange Ausfahrt, 1 Qualitäts-Rad, 1 Gehtest).

---

## Monatlich: Ernährung

> Monatsreview Ernährung. Gewichtsverlauf und Taille aus dashboard.json.
>
> Trend gegen die Prognose (~0,3 kg/Woche, 84 kg bis Woche 28, danach Erhaltung)? Taille ~1 cm/Monat?
> Falls zu schnell oder zu langsam: welche Mahlzeit ändere ich wie — keine Snacks einführen,
> sondern Portionen anpassen wie im Plan beschrieben.

---

## Renn-Verpflegung testen (ab Phase 3)

> Fueling-Check. Auf der letzten langen Ausfahrt habe ich [X] g Kohlenhydrate/Stunde
> genommen ([was genau]). Magen: [ok / Probleme]. Ziel sind 60–90 g/h für den Renntag.
>
> Passt die Menge und das Timing? Was teste ich auf der nächsten Ausfahrt?

---

## Warum keine echte Automatisierung meiner Antworten

Ein Skript könnte theoretisch die Anthropic-API nächtlich anrufen und dir eine Mail schicken.
Technisch machbar, aber: das kostet API-Guthaben, die Antwort hätte keinen Zugriff auf euren
Projektkontext, und du würdest sie morgens überfliegen statt zu lesen. Der Wert entsteht im
Dialog — wenn du zurückfragst, widersprichst, Kontext lieferst, den keine Zahl kennt.

Das Dashboard ersetzt die tägliche Information. Ich ersetze die wöchentliche Entscheidung.
