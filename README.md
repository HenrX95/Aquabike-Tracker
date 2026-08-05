# IRONMAN 70.3 Tracker — Henrik

Automatischer Sync von Garmin Connect + Oura in eine JSON-Datei, ein statisches Dashboard,
und ein Generator, der den Trainingsplan als strukturierte Workouts auf die Forerunner 955 legt.
Zwift-Rides kommen über Garmin mit rein (Zwift pusht automatisch dorthin).

**Ziel:** IRONMAN 70.3 Venice-Jesolo, 24.04.2027 · 38 Wochen ab 03.08.2026
**Radziel:** 90 km konstant bei 235–250 W (FTP-Ziel 300 W)

## Die eine Regel

Alle Zielwerte stehen in **`targets.json`** — und nur dort. `scripts/campaign.py` liest die Datei
und versorgt Sync, Dashboard und Workout-Generator. Wenn sich ein Ziel ändert, ändert es sich
an genau einer Stelle. Keine Zahl gehört hartkodiert in ein Skript.

## Was automatisch läuft — und was nicht

**Ohne dich:** GitHub Actions holt jede Nacht um 23:15 (München) Garmin- und Oura-Daten,
rechnet Wochenlast und Ampeln, schreibt `data/dashboard.json` und baut `docs/index.html` neu.

**Nicht ohne dich:** Claude. Kein Gedächtnis zwischen Chats, kein Timer. Ich kann
`dashboard.json` in jedem Chat lesen — aber nur, wenn du einen Chat öffnest.
Das Dashboard ersetzt die tägliche Information. Ich ersetze die wöchentliche Entscheidung.

## Dateien

```
targets.json                ALLE Zielwerte — die einzige Quelle
scripts/campaign.py         liest targets.json, leitet Phase/Soll/Wegmarken ab
scripts/sync.py             Garmin + Oura → dashboard.json, Ampel-Logik
scripts/build_dashboard.py  dashboard.json → docs/index.html
scripts/template.html       Dashboard-Layout
scripts/garmin_workouts.py  Trainingsplan → strukturierte Garmin-Workouts + Kalender
data/manual.json            deine Eingaben (Tests, Knie, Aero-Minuten, Decoupling)
data/dashboard.json         wird generiert — das lese ich
docs/index.html             wird generiert — das schaust du an
```

## Täglicher Ablauf

**Auf der Uhr:** Selbstbeurteilung nach jeder Einheit (liefert RPE für die Lastampel).

**In `data/manual.json`**, wenn es etwas zu tragen gibt:

- `ftp_w` / `css_s` — nach jedem Test
- `race_power_hold_min` — längster durchgehender Block ≥ 235 W nach der langen Ausfahrt
- `aero_minutes_week` — Minuten in Aeroposition (kommt aus keiner API)
- `decoupling_pct` — Pw:HR-Drift der letzten langen Ausfahrt
- `daily[].knee` — schlimmster Knieschmerz des Tages, 0–10

**Morgens:** Dashboard öffnen. Ampeln stehen ganz oben.
**Sonntags:** Chat öffnen, Prompt aus `PROMPTS.md`.

## Workouts auf die Uhr

```bash
pip install -r requirements.txt
export GARMIN_EMAIL="…" GARMIN_PASSWORD="…"

python3 scripts/garmin_workouts.py --dry-run --weeks 1-8   # anzeigen
python3 scripts/garmin_workouts.py --weeks 1-8             # hochladen + einplanen
python3 scripts/garmin_workouts.py --clean                 # alle "70.3 …" löschen
```

Alternativ über Actions-Tab → *Garmin-Workouts hochladen* → Run workflow.

Immer nur die aktuelle Phase hochladen. Nach jedem FTP-Test `manual.json` aktualisieren und
die kommenden Wochen neu erzeugen — sonst zeigt die Uhr Wattziele einer veralteten FTP.

## Setup (einmalig)

1. **Secrets** — Repo → Settings → Secrets and variables → Actions:
   `GARMIN_EMAIL`, `GARMIN_PASSWORD`, `GARMIN_TOKENS` (base64-Tarball des Token-Caches), `OURA_TOKEN`
2. **Workflow aktivieren** — Actions-Tab → einmal *Run workflow*
3. **Pages** — Settings → Pages → Source `main` / Ordner `/docs`
4. **Raw-URL** für Chats notieren:
   `https://raw.githubusercontent.com/HenrX95/Aquabike-Tracker/main/data/dashboard.json`

## Ampeln

| Signal | Regel | Konsequenz |
|---|---|---|
| sRPE-Last | > +15 % zur Vorwoche | Qualitätseinheit zurücknehmen |
| Ruhepuls | 3 Tage +5 bpm über Baseline | Nächste Einheit → Zone 2 |
| HRV | 3 Tage unter 85 % der Baseline | Qualität reduzieren, Schlaf schützen |
| Knie | > 3/10 oder morgens noch da | Gym- und Gehlast zurück bis 2 grüne Wochen |
| Schwimmen | < 2 Einheiten/Woche | Konstanz ist der Hebel, nicht Umfang |
| Schlaf | Ø < 7,5 h | Im Defizit doppelt relevant |

## Bekannte Schwächen

- **`garminconnect` ist inoffiziell.** Garmin kann die API ändern; dann bricht der Sync.
- **Rennleistungs-Block ist eine Näherung.** Ohne Power-Stream sieht der Sync nur die NP je
  Einheit, nicht Blöcke innerhalb einer Ausfahrt. Deshalb überschreibt `race_power_hold_min`
  aus `manual.json` den berechneten Wert.
- **Aero-Minuten und Decoupling** liefert keine API — beides manuell.
- **Der Repo-Name sagt noch „Aquabike".** Umbenennen geht in Settings; GitHub legt eine
  Weiterleitung an, dann müssen nur die Raw-URLs in `PROMPTS.md` nachgezogen werden.
