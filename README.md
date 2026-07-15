# Aquabike Tracker — Henrik

Automatischer Sync von Garmin Connect + Oura in eine JSON-Datei und ein statisches Dashboard.
Zwift-Rides kommen über Garmin mit rein (Zwift pusht automatisch dorthin).

## Was hier automatisch läuft — und was nicht

**Läuft ohne dich:** GitHub Actions holt jede Nacht um 23:15 (München) Garmin- und Oura-Daten,
rechnet Wochenlast und Ampeln, schreibt `data/dashboard.json` und baut `docs/index.html` neu.

**Läuft nicht ohne dich:** Claude. Ich habe kein Gedächtnis zwischen Chats und keinen Timer.
Ich kann `dashboard.json` in jedem Chat lesen, aber nur wenn du einen Chat öffnest.
Der tägliche Impuls bist du — der Rest ist automatisiert.

## Setup (einmalig, ~30 Minuten)

### 1. Privates Repo anlegen
Auf GitHub: neues **privates** Repo, z. B. `aquabike-tracker`. Diese Dateien reinschieben.

### 2. Secrets hinterlegen
Repo → Settings → Secrets and variables → Actions → *New repository secret*:

| Name | Wert |
|---|---|
| `GARMIN_EMAIL` | deine Garmin-Connect-Mailadresse |
| `GARMIN_PASSWORD` | dein Garmin-Passwort |
| `OURA_TOKEN` | Personal Access Token von cloud.ouraring.com/personal-access-tokens |

Diese Werte trägst du selbst ein. Sie liegen verschlüsselt bei GitHub und tauchen in keinem Log auf.

### 3. Workflow aktivieren
Actions-Tab → Workflow aktivieren → einmal *Run workflow* für einen Testlauf.

### 4. Dashboard erreichbar machen
Settings → Pages → Source: `main` / Ordner `/docs`.
Ergebnis: `https://<dein-user>.github.io/aquabike-tracker` — als Lesezeichen aufs Handy.

Bei einem privaten Repo braucht GitHub Pages einen bezahlten Plan. Kostenlose Alternative:
`docs/index.html` liegt lokal auf dem Rechner (per `git pull`), Doppelklick genügt — die Datei
ist standalone, keine Server nötig.

### 5. Raw-URL für mich notieren
```
https://raw.githubusercontent.com/<user>/aquabike-tracker/main/data/dashboard.json
```
Bei privatem Repo brauche ich einen Token in der URL — dann lieber die JSON in den Chat
ziehen oder das Repo öffentlich machen (es stehen keine Zugangsdaten drin, nur Trainingsdaten).

## Täglicher Ablauf

**Abends, 30 Sekunden:** `data/manual.json` ergänzen — was keine API liefert:

```json
{ "date": "2026-07-15", "rpe": 7, "knee": 2, "weight_kg": 91.8 }
```

- `rpe` — Anstrengung 1–10 nach jeder Einheit (Basis für die sRPE-Last)
- `knee` — schlimmster Knieschmerz des Tages, 0–10
- `weight_kg` — nur falls du keine Garmin-Waage hast

Nach FTP- und CSS-Tests oben im File `ftp_w` / `css_s` aktualisieren.

**Morgens:** Dashboard öffnen. Ampeln stehen ganz oben.

**Sonntags:** Chat mit mir öffnen, Prompt aus `PROMPTS.md`.

## Dateien

```
scripts/sync.py             Garmin + Oura → dashboard.json, Ampel-Logik
scripts/build_dashboard.py  dashboard.json → docs/index.html
scripts/template.html       Dashboard-Layout
data/manual.json            deine Eingaben (RPE, Knie, FTP, CSS, Taille)
data/dashboard.json         wird generiert — das lese ich
docs/index.html             wird generiert — das schaust du an
```

## Ampeln (aus Abschnitt 11 des Plans)

| Signal | Regel | Konsequenz |
|---|---|---|
| sRPE-Last | > +15 % zur Vorwoche | Qualitätseinheit zurücknehmen |
| Ruhepuls | 3 Tage +5 bpm über Baseline | Nächste Einheit → Zone 2 |
| Knie | > 3/10 oder morgens noch da | Gym-Last zurück bis 2 grüne Wochen |
| Schwimmen | < 3 Einheiten/Woche | Der Hebel, der über 1:40 entscheidet |
| Schlaf | Ø < 7,5 h | Im Defizit doppelt relevant |

## Bekannte Schwächen

- **`garminconnect` ist inoffiziell.** Garmin kann die API ändern; dann bricht der Sync.
  Fallback wäre Strava (offizielle API, aber ohne RHF und Schlaf).
- **Garmin MFA:** falls aktiviert, schlägt der Login fehl. Für dieses Konto ggf. deaktivieren
  oder Token-Caching ergänzen.
- **Schwimmtempo ≠ CSS.** Das Dashboard zeigt Ø-Tempo je Einheit. Echte CSS kommt nur
  aus dem 400/200-Test — deshalb manuell.
