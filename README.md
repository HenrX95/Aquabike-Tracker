# IRONMAN 70.3 Tracker — Henrik

Automatischer Sync von Garmin Connect + Oura in eine JSON-Datei, ein statisches Dashboard,
und ein Generator, der den Trainingsplan als strukturierte Workouts auf die Forerunner 955 legt.
Zwift-Rides kommen über Garmin mit rein (Zwift pusht automatisch dorthin).

**Ziel:** IRONMAN 70.3 Venice-Jesolo, 24.04.2027 · 38 Wochen ab 03.08.2026
**Radziel:** 90 km bei IF 0,75–0,80 der Renntags-FTP · FTP-Hauptziel 280 W (Stretch 300 W)
**Stand:** targets.json v6 (27.09.2026) – Reset nach Bilanz W1–8, Phase „Wiedereinstieg“ W9–11

## Die eine Regel

Alle Zielwerte stehen in **`targets.json`** — und nur dort. `scripts/campaign.py` liest die Datei
und versorgt Sync, Dashboard und Workout-Generator. Das gilt seit v6 auch für Phasen,
Entlastungswochen und die Wochenschablone (welcher Wochentag welche Einheit).

## Standardwoche (v6)

| Tag | Einheit |
|---|---|
| Mo | Rad-Qualität 1 – Zwift, abends |
| Di | Schwimmen 1 (Technik/Ausdauer) + Kraft A (Beine/Knie) |
| Mi | Ruhetag + Mobility · Mittwochs-Vorkochen |
| Do | Rad-Qualität 2 – Zwift, abends |
| Fr | Schwimmen 2 – CSS |
| Sa | Lange Ausfahrt |
| So | Kraft B (Oberkörper/Rumpf) · ab Build II + 60 min Z2 · Sonntags-Vorkochen |

**Minimum-Woche (~5 h):** 2× Schwimmen, Rad-Qualität 1, lange Ausfahrt, Kraft A. Alles andere ist Bonus.
**Laufen:** kein festes Training. Läufe werden erfasst und gegen Leitplanken geprüft
(≤ 12 km, Ø-Puls ≤ 150 bei > 45 min, längster Lauf max. +10 %, Knie-Wert eintragen).

## Was automatisch läuft — und was nicht

**Ohne dich:** GitHub Actions holt jede Nacht um 23:15 (München) Garmin- und Oura-Daten,
rechnet Wochenlast und Ampeln, schreibt `data/dashboard.json` und baut `docs/index.html` neu.

**Nicht ohne dich:** Tests eintragen, Knie-Wert, Workouts nach FTP-Test neu hochladen,
Sonntags-Review im Claude-Projekt „Triathlon“ (Prompts in `PROMPTS.md`).

## Dateien

```
targets.json                ALLE Zielwerte + Phasen + Wochenschablone — die einzige Quelle
scripts/campaign.py         liest targets.json, leitet Phase/Soll/Wegmarken/Rennleistung ab
scripts/sync.py             Garmin + Oura → dashboard.json, Ampel-Logik
scripts/build_dashboard.py  dashboard.json → docs/index.html
scripts/template.html       Dashboard-Layout
scripts/garmin_workouts.py  Trainingsplan → strukturierte Garmin-Workouts + Kalender
data/manual.json            deine Eingaben (Tests, Knie, Gewicht, Aero-Minuten, Decoupling)
data/dashboard.json         wird generiert
docs/index.html             wird generiert — das schaust du an
```

## In `data/manual.json` eintragen

- `ftp_w` + `ftp_tested` — nach jedem Rampentest (W9, W18, W28, W35)
- `css_s` + `css_tested` — nach jedem CSS-Test (gleiche Wochen, freitags)
- `daily[]` — pro Tag nur, was du hast: `knee` (0–10), `weight_kg`, `bodyfat_pct`, `waist_cm`
- `race_power_hold_min`, `aero_minutes_week`, `decoupling_pct` — nach der langen Ausfahrt

## Workouts auf die Uhr

Actions-Tab → **Garmin-Workouts hochladen** → *Run workflow* → Wochen z. B. `9-16`.
Nutzt das Secret `GARMIN_TOKENS` (dasselbe wie der Sync). Immer ca. 8 Wochen im Voraus,
nach jedem FTP-/CSS-Test die kommenden Wochen erneut hochladen (gleichnamige Workouts werden ersetzt).

Lokal:
```bash
pip install -r requirements.txt
export GARMIN_TOKENS="…"     # oder GARMIN_EMAIL / GARMIN_PASSWORD
python3 scripts/garmin_workouts.py --dry-run --weeks 9-16   # anzeigen
python3 scripts/garmin_workouts.py --weeks 9-16 --push      # hochladen + Kalender + Uhr
python3 scripts/garmin_workouts.py --clean                  # alle "70.3 …" löschen
```

## Ampeln

| Signal | Regel | Konsequenz |
|---|---|---|
| sRPE-Last | > +15 % zur Vorwoche (inkl. Läufe) | Qualitätseinheit zurücknehmen |
| Ruhepuls (Oura) | 3 Tage +5 bpm über Median-Baseline | Nächste Einheit → Zone 2 |
| HRV | 3 Tage unter 85 % der Baseline | Qualität reduzieren, Schlaf schützen |
| Knie | > 3/10 oder morgens noch da | Gym-Last zurück bis 2 grüne Wochen |
| Laufen | > 12 km · Ø > 150 bpm über 45 min · +10 % längster Lauf · kein Knie-Wert | Nächster Lauf kürzer/lockerer |
| Schwimmen | < 2 Einheiten/Woche | Konstanz ist der Hebel |
| Schlaf | Ø < 7,5 h (nur Hauptschlaf) | Im Defizit doppelt relevant |

## Änderungen v6 (27.09.2026)

- RPE: Garmin-Rohwert 10 wurde als RPE 10 statt RPE 1 gelesen → behoben, betroffene Cache-Einträge gelöscht
- Schlaf: Oura-Nickerchen überschrieben die Nacht (0,1–0,5 h) → nur Hauptschlaf zählt
- Ruhepuls: Quelle jetzt Oura (niedrigster Nachtpuls), Baseline als Median
- Läufe/Gehen zählen jetzt in Wochenlast, Wochenstunden und Leitplanken
- Rennleistung relativ zur aktuellen FTP statt fix 235–250 W
- Gewicht/Körperfett/Taille aus `manual.json` werden mit Garmin-Werten zusammengeführt
- Workout-Workflow nutzt `GARMIN_TOKENS`, optionales Aufräumen und Push an die Uhr

## Bekannte Schwächen

- **`garminconnect` ist inoffiziell.** Garmin kann die API ändern; dann bricht der Sync.
- **Kein Leistungsmesser am Outdoor-Rad.** Qualität deshalb auf Zwift; draußen nur Puls.
- **Rennleistungs-Block ist eine Näherung** (nur NP je Einheit) → `race_power_hold_min` manuell.
- **Aero-Minuten und Decoupling** liefert keine API — beides manuell.
