# Coach-Routinen – IRONMAN 70.3 Venice-Jesolo (24.04.2027)

**FTP-Ziel 280 W (Stretch 300) · Rennleistung IF 0,75–0,80 · CSS 1:50 · 38 Wochen ab 03.08.2026**

Diese Prompts im Claude-Projekt **„Triathlon“** verwenden. Dort liegen Trainingsplan v4 (docx)
und Ernährungsplan (xlsx). `dashboard.json` per Raw-URL oder als Anhang:

https://raw.githubusercontent.com/HenrX95/Aquabike-Tracker/main/data/dashboard.json

Hinweis: Die Tracking-Website selbst lädt ihre Daten per JavaScript – immer die Raw-URL oben verwenden.

---

## Wöchentlich (Sonntagabend, ~10 Minuten) — der eigentliche Hebel

> Wochenreview Woche [N]. dashboard.json: [URL]
>
> Analysiere:
> - **Umfang**: `weekly[].total_hours` gegen Minimum-Woche (5 h) und Soll der Phase.
> - **Compliance**: Soll vs. Ist laut `plan.sport_targets`. Wo ist die Lücke?
> - **Last**: sRPE-Trend der letzten 4 Wochen (inkl. Läufe). Steigerung ≤ 10–15 %?
> - **Regeneration**: Ruhepuls, HRV, Schlaf, Readiness. Überlastungszeichen?
> - **Knie & Laufen**: Ampeln, Lauf-km der Woche, Leitplanken eingehalten?
> - **Rennleistung**: längster Block ≥ 0,75 × FTP gegen die Wegmarke.
> - **Gewicht**: Trend gegen ~0,2 kg/Woche bis W28 (Ziel 83,5 kg). Zu schnell → kcal hoch.
>
> Dann: konkrete Einheiten für die kommende Woche, Tag für Tag, mit Zielwerten.
> Standardwoche laut Trainingsplan v4, Abschnitt 4. Sei ehrlich, wenn eine Woche schlecht war.

---

## Nach jedem Test (W9, W18, W28, W35)

> Testauswertung Woche [N]:
> - FTP: [X] W (vorher [Y] W) · CSS: [MM:SS]/100 m (400 m: [Zeit], 200 m: [Zeit])
> - Gewicht: [X] kg · Körperfett: [X] % · Taille: [X] cm
>
> Vergleiche gegen die Meilensteine (Trainingsplan v4, Abschnitt 10). Auf Kurs für
> FTP 280 W und CSS 1:50? Was ändern wir? Welche Wochen soll ich neu auf die Uhr laden?

---

## Bei Störungen

**Woche bricht zusammen**
> Diese Woche schaffe ich nur [N] Stunden / [Termine]. Priorisiere nach der Minimum-Woche
> (2× Schwimmen, Rad-Qualität 1, lange Ausfahrt, Kraft A).

**Dienstreise**
> Ich bin von [Datum] bis [Datum] in [Ort], Hotel mit [Gym/Pool/nichts]. Baue mir eine Reisewoche.

**Knie meldet sich**
> Knieschmerz [X]/10 seit [Datum], bei [Übung/Einheit/Lauf]. Was regressiere ich konkret?
> Ab wann muss ich zum Arzt statt zu dir?

**Krankheit / Pause**
> Ich war [N] Tage raus wegen [Grund]. Aktuelle Woche: [N]. Wie steige ich wieder ein?

---

## Monatlich: Ernährung

> Monatsreview Ernährung. Gewicht, Körperfett und Taille aus dashboard.json.
> Trend gegen ~0,2 kg/Woche? Welche Mahlzeit ändere ich wie (Portionen, keine Snacks)?

---

## Renn-Verpflegung testen (ab Build II)

> Fueling-Check. Auf der letzten langen Ausfahrt [X] g KH/Stunde ([was genau]). Magen: [ok/Probleme].
> Ziel 60–90 g/h am Renntag. Was teste ich als Nächstes?
