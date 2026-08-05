#!/usr/bin/env python3
"""
Aquabike Sync — holt Garmin Connect + Oura Daten und schreibt data/dashboard.json

Laeuft taeglich via GitHub Actions (oder lokal per Cronjob).
Zwift-Rides kommen automatisch mit, weil Zwift nach Garmin Connect pusht.
Gewicht kommt ueber Withings → Garmin Connect mit.
RPE kommt aus der Selbstbeurteilung der Uhr, Fallback ist manual.json.

Benoetigte Secrets (Environment):
  GARMIN_EMAIL, GARMIN_PASSWORD, OURA_TOKEN

Optional:
  PLAN_START      Startdatum Woche 1, ISO (default 2026-07-13)
"""

import json
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests
from garminconnect import Garmin

# ---------------------------------------------------------------- Konfiguration

PLAN_START = date.fromisoformat(os.getenv("PLAN_START", "2026-08-03"))
RACE_DATE = date.fromisoformat(os.getenv("RACE_DATE", "2027-04-24"))  # 70.3 Venice-Jesolo
LOOKBACK_DAYS = 90          # so viel Historie halten wir im JSON
DATA = Path(__file__).resolve().parent.parent / "data"
OUT = DATA / "dashboard.json"
MANUAL = DATA / "manual.json"
RPE_CACHE = DATA / "rpe_cache.json"

# Selbstbeurteilung der Uhr. Garmin legt sie im summaryDTO ab und skaliert 0-100
# (30 = RPE 3). Verifiziert am 15.07.2026 gegen echte Aktivitaeten.
# Pfade werden der Reihe nach probiert, erster Treffer gewinnt.
EFFORT_PATHS = [
    ("summaryDTO", "directWorkoutRpe"),   # der echte Ort
    (None, "directWorkoutRpe"),           # Fallback: oberste Ebene
    (None, "workoutRpe"),
    (None, "perceivedEffort"),
]
FEEL_PATHS = [
    ("summaryDTO", "directWorkoutFeel"),
    (None, "directWorkoutFeel"),
    (None, "workoutFeel"),
]

# Nur fuer diese Aktivitaeten lohnt der zusaetzliche Detail-Call
RPE_SPORTS = {"swim", "bike", "gym"}

# Schwellen aus dem Trainingsplan (Abschnitt 11)
RHR_FLAG_DELTA = 5          # bpm ueber Baseline
RHR_FLAG_DAYS = 3           # an so vielen Tagen in Folge
SRPE_FLAG_PCT = 15          # max. Wochensteigerung in %
KNEE_FLAG = 3               # Knieschmerz > 3/10 = rot
SLEEP_TARGET_H = 7.5

# ---------------------------------------------------------------- Hilfsfunktionen


def log(msg):
    print(f"[sync] {msg}", file=sys.stderr)


def plan_week(d: date) -> int:
    """Trainingswoche 1..26 fuer ein Datum."""
    return (d - PLAN_START).days // 7 + 1


def phase_for_week(w: int) -> str:
    if w <= 6:
        return "1 – Grundlage"
    if w <= 14:
        return "2 – Build I"
    if w <= 20:
        return "3 – Build II"
    if w <= 26:
        return "4 – Konsolidierung"
    return "Rennblock 2027"


def is_recovery_week(w: int) -> bool:
    """Jede 4. Woche ist Erholungswoche."""
    return w % 4 == 0


def normalize_rpe(raw):
    """
    Garmin speichert die Selbstbeurteilung intern 0-100 (10 = RPE 1, 100 = RPE 10).
    Manche Endpunkte liefern aber schon 0-10. Beides sauber auf 1-10 bringen.
    """
    if raw is None:
        return None
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return None
    if v <= 0:
        return None
    if v > 10:                    # 0-100er Skala
        v = v / 10
    return round(min(10, max(1, v)), 1)


def pick(detail: dict, paths: list):
    """
    Ersten Treffer aus einer Liste von (container, key)-Pfaden holen.
    container=None bedeutet oberste Ebene.
    """
    for container, key in paths:
        obj = detail.get(container) if container else detail
        if isinstance(obj, dict) and obj.get(key) is not None:
            label = f"{container}.{key}" if container else key
            return label, obj[key]
    return None, None


def fetch_rpe(api, activities, cache: dict):
    """
    Holt die Selbstbeurteilung pro Aktivitaet aus dem Garmin-Detail-Objekt.
    Ergebnisse werden gecacht — alte Aktivitaeten aendern sich nicht mehr,
    also wird jede ID nur einmal abgefragt.
    """
    hits, misses, calls = 0, 0, 0
    field_used = None

    for a in activities:
        aid = str(a.get("activity_id") or "")
        if not aid or a["sport"] not in RPE_SPORTS:
            continue

        if aid in cache:                       # schon bekannt
            a["rpe_garmin"] = cache[aid].get("rpe")
            a["feel_garmin"] = cache[aid].get("feel")
            if a["rpe_garmin"]:
                hits += 1
            continue

        try:
            detail = api.get_activity(aid)
            calls += 1
            time.sleep(1.5)          # Garmin drosselt Actions-IPs (429)
        except Exception as e:
            log(f"Detail {aid} fehlgeschlagen: {e}")
            continue

        ekey, eraw = pick(detail, EFFORT_PATHS)
        fkey, fraw = pick(detail, FEEL_PATHS)
        rpe = normalize_rpe(eraw)
        feel = normalize_rpe(fraw)

        if rpe and not field_used:
            field_used = ekey
            log(f"Selbstbeurteilung gefunden unter '{ekey}' (Rohwert {eraw} → RPE {rpe})")

        cache[aid] = {"rpe": rpe, "feel": feel, "date": a["date"]}
        a["rpe_garmin"] = rpe
        a["feel_garmin"] = feel
        hits += 1 if rpe else 0
        misses += 0 if rpe else 1

    log(f"RPE: {hits} vorhanden, {misses} ohne Bewertung, {calls} neue Detail-Calls")
    if not field_used and misses and not any(v.get("rpe") for v in cache.values()):
        log("WARNUNG: keine Selbstbeurteilung gefunden. Entweder auf der Uhr nicht "
            "aktiviert, oder Garmin hat den Feldnamen geaendert — dann probe_rpe.py laufen lassen.")
    return cache


def sport_bucket(type_key: str) -> str:
    t = (type_key or "").lower()
    if "swim" in t:
        return "swim"
    if "cycl" in t or "bik" in t or "ride" in t:
        return "bike"
    if "strength" in t or "fitness_equipment" in t or "gym" in t:
        return "gym"
    if "walk" in t or "hik" in t:
        return "walk"
    if "run" in t:
        return "run"
    if "yoga" in t or "pilates" in t or "mobility" in t or "stretch" in t:
        return "mobility"
    if "cardio" in t or "elliptical" in t or "training" in t:
        return "cardio"
    return "other"


# Anzeige-Namen und Reihenfolge fuer das Dashboard
SPORT_LABELS = {
    "swim": "Schwimmen",
    "bike": "Rad",
    "gym": "Kraft",
    "walk": "Gehen / Wandern",
    "run": "Laufen",
    "mobility": "Mobility",
    "cardio": "Cardio",
    "other": "Sonstiges",
}
SPORT_ORDER = ["swim", "bike", "gym", "walk", "run", "mobility", "cardio", "other"]

# Disziplinen mit Wochen-Soll (Ampel). Gehen/Laufen bewusst OHNE Soll —
# wird erfasst, aber nicht als Versagen dargestellt wenn es fehlt.
SPORT_TARGETS = {"swim": 3, "bike": 3, "gym": 2}


# ---------------------------------------------------------------- Garmin


def garmin_login():
    """
    Login mit Token-Wiederverwendung. Garmin drosselt wiederholte Passwort-Logins
    von GitHub-Actions-IPs (429). Ein gecachtes Token umgeht das komplett.

    Ablauf:
    - GARMIN_TOKENS (Token-String) als Secret gesetzt → Token wird direkt genutzt,
      KEIN Passwort-Login, kein 429-Risiko. Token ist ~1 Jahr gueltig.
    - Kein Token oder abgelaufen → Passwort-Login als Rueckfall, danach wird das
      frische Token als String ins Log geschrieben (einmalig als Secret speichern).

    Die Bibliothek garminconnect speichert Tokens als String (client.dumps) und
    laedt sie ebenso (client.loads) — kein Verzeichnis, kein Base64 noetig.
    """
    import os as _os

    email = _os.environ.get("GARMIN_EMAIL")
    password = _os.environ.get("GARMIN_PASSWORD")
    token_str = _os.environ.get("GARMIN_TOKENS")

    # 1. Versuch: gecachtes Token direkt laden
    if token_str and len(token_str) > 512:
        try:
            api = Garmin()
            api.login(token_str)   # String > 512 Zeichen wird direkt als Token geladen
            log("Garmin: Login via Token — kein Passwort, kein Rate-Limit-Risiko")
            return api
        except Exception as e:
            log(f"Garmin: Token-Login fehlgeschlagen ({e}), Rueckfall auf Passwort")

    # 2. Rueckfall: Passwort-Login
    if not (email and password):
        raise RuntimeError("Kein gueltiges GARMIN_TOKENS und kein GARMIN_PASSWORD/-EMAIL")
    api = Garmin(email, password)
    api.login()
    log("Garmin: Login via Passwort")

    # Frisches Token als String ins Log — einmal als Secret GARMIN_TOKENS sichern
    try:
        token_dump = api.client.dumps()
        log("=================== GARMIN_TOKENS ===================")
        log("Diesen Wert als Repository-Secret GARMIN_TOKENS speichern.")
        log("Danach laeuft der Sync ~1 Jahr ohne Passwort-Login:")
        log(token_dump)
        log("================= Ende GARMIN_TOKENS =================")
    except Exception as e:
        log(f"Token-Export nicht moeglich: {e}")

    return api


def fetch_garmin(start: date, end: date):
    log("Garmin: Login")
    api = garmin_login()

    log(f"Garmin: Aktivitaeten {start} → {end}")
    raw = api.get_activities_by_date(start.isoformat(), end.isoformat())

    activities = []
    for a in raw:
        started = a.get("startTimeLocal", "")[:10]
        if not started:
            continue
        dur_min = round((a.get("duration") or 0) / 60, 1)
        activities.append(
            {
                "date": started,
                "activity_id": a.get("activityId"),
                "name": a.get("activityName"),
                "sport": sport_bucket(
                    (a.get("activityType") or {}).get("typeKey", "")
                ),
                "type_raw": (a.get("activityType") or {}).get("typeKey"),
                "duration_min": dur_min,
                "distance_km": round((a.get("distance") or 0) / 1000, 2),
                "avg_hr": a.get("averageHR"),
                "max_hr": a.get("maxHR"),
                "avg_power": a.get("avgPower"),
                "norm_power": a.get("normPower"),
                "elevation_m": round(a.get("elevationGain") or 0),
                # Schwimmtempo in s/100m
                "pace_per_100m": (
                    round((a.get("duration") or 0) / ((a.get("distance") or 1) / 100))
                    if sport_bucket((a.get("activityType") or {}).get("typeKey", ""))
                    == "swim"
                    and (a.get("distance") or 0) > 0
                    else None
                ),
            }
        )

    # Ruhepuls + Gewicht
    rhr, weights = [], []
    d = start
    while d <= end:
        iso = d.isoformat()
        try:
            stats = api.get_stats(iso)
            if stats.get("restingHeartRate"):
                rhr.append({"date": iso, "bpm": stats["restingHeartRate"]})
        except Exception as e:
            log(f"Garmin stats {iso}: {e}")
        d += timedelta(days=1)

    try:
        log("Garmin: Gewichtsdaten")
        body = api.get_body_composition(start.isoformat(), end.isoformat())
        for w in body.get("dateWeightList", []):
            weights.append(
                {
                    "date": datetime.fromtimestamp(
                        w["date"] / 1000, tz=timezone.utc
                    ).date().isoformat(),
                    "kg": round(w["weight"] / 1000, 2),
                }
            )
    except Exception as e:
        log(f"Garmin Gewicht nicht verfuegbar: {e}")

    return api, activities, rhr, weights


# ---------------------------------------------------------------- Oura


def fetch_oura(start: date, end: date):
    token = os.environ["OURA_TOKEN"]
    h = {"Authorization": f"Bearer {token}"}
    params = {"start_date": start.isoformat(), "end_date": end.isoformat()}

    def get(path):
        r = requests.get(
            f"https://api.ouraring.com/v2/usercollection/{path}",
            headers=h,
            params=params,
            timeout=30,
        )
        r.raise_for_status()
        return r.json().get("data", [])

    log("Oura: Schlaf + Readiness")
    sleep = [
        {
            "date": s["day"],
            "total_h": round((s.get("total_sleep_duration") or 0) / 3600, 2),
            "score": (s.get("score") if "score" in s else None),
            "hrv": s.get("average_hrv"),
            "rhr": s.get("lowest_heart_rate"),
        }
        for s in get("daily_sleep") + get("sleep")
        if s.get("day")
    ]
    # daily_sleep hat score, sleep hat Dauer — zusammenfuehren
    merged = {}
    for s in sleep:
        m = merged.setdefault(s["date"], {"date": s["date"]})
        for k, v in s.items():
            if v is not None:
                m[k] = v

    readiness = [
        {"date": r["day"], "score": r.get("score")}
        for r in get("daily_readiness")
        if r.get("day")
    ]

    return sorted(merged.values(), key=lambda x: x["date"]), readiness


# ---------------------------------------------------------------- Auswertung


def build_weekly(activities, manual):
    """Wochenaggregate inkl. sRPE-Last."""
    weeks = {}
    rpe_map = {m["date"]: m for m in manual.get("daily", [])}

    for a in activities:
        d = date.fromisoformat(a["date"])
        w = plan_week(d)
        if w < 1:
            continue
        wk = weeks.setdefault(
            w,
            {
                "week": w,
                "phase": phase_for_week(w),
                "recovery_week": is_recovery_week(w),
                "swims": 0,
                "bikes": 0,
                "gyms": 0,
                "bike_hours": 0.0,
                "swim_meters": 0,
                "srpe_load": 0,
                "rpe_covered": 0,
                "rpe_missing": 0,
            },
        )
        if a["sport"] == "swim":
            wk["swims"] += 1
            wk["swim_meters"] += int(a["distance_km"] * 1000)
        elif a["sport"] == "bike":
            wk["bikes"] += 1
            wk["bike_hours"] += a["duration_min"] / 60
        elif a["sport"] == "gym":
            wk["gyms"] += 1

        # sRPE = RPE x Dauer (Foster).
        # Quelle 1: Selbstbeurteilung der Uhr. Quelle 2: manual.json.
        rpe = a.get("rpe_garmin") or (rpe_map.get(a["date"]) or {}).get("rpe")
        if rpe:
            wk["srpe_load"] += int(rpe * a["duration_min"])
            wk["rpe_covered"] += 1
        else:
            wk["rpe_missing"] += 1

    for wk in weeks.values():
        wk["bike_hours"] = round(wk["bike_hours"], 1)

    return [weeks[k] for k in sorted(weeks)]


def build_flags(rhr, weekly, manual, sleep):
    """Ampeln aus Abschnitt 11 des Plans."""
    flags = []

    # (1) sRPE-Sprung
    non_rec = [w for w in weekly if not w["recovery_week"] and w["srpe_load"] > 0]
    if len(non_rec) >= 2:
        prev, cur = non_rec[-2], non_rec[-1]
        if prev["srpe_load"] > 0:
            pct = (cur["srpe_load"] - prev["srpe_load"]) / prev["srpe_load"] * 100
            if pct > SRPE_FLAG_PCT:
                flags.append(
                    {
                        "level": "red",
                        "metric": "sRPE-Last",
                        "text": f"Wochenlast +{pct:.0f}% (Grenze {SRPE_FLAG_PCT}%). Naechste Qualitaetseinheit zuruecknehmen.",
                    }
                )

    # (2) Ruhepuls
    if len(rhr) >= 14:
        baseline = sum(r["bpm"] for r in rhr[-28:-3]) / len(rhr[-28:-3])
        recent = rhr[-RHR_FLAG_DAYS:]
        if all(r["bpm"] >= baseline + RHR_FLAG_DELTA for r in recent):
            flags.append(
                {
                    "level": "red",
                    "metric": "Ruhepuls",
                    "text": f"RHF {RHR_FLAG_DAYS} Tage in Folge {RHR_FLAG_DELTA}+ bpm ueber Baseline ({baseline:.0f}). Naechste Einheit → Zone 2.",
                }
            )

    # (3) Knieschmerz
    knee = [m for m in manual.get("daily", []) if m.get("knee") is not None]
    if knee:
        worst = max(knee[-7:], key=lambda m: m["knee"])
        if worst["knee"] > KNEE_FLAG:
            flags.append(
                {
                    "level": "red",
                    "metric": "Knie",
                    "text": f"Knieschmerz {worst['knee']}/10 am {worst['date']}. Gym-Last einen Schritt zurueck, bis 2 gruene Wochen.",
                }
            )

    # (4) Schwimmfrequenz — der eigentliche Hebel
    if weekly:
        cur = weekly[-1]
        if cur["swims"] < 3 and not cur["recovery_week"]:
            flags.append(
                {
                    "level": "amber",
                    "metric": "Schwimmfrequenz",
                    "text": f"Nur {cur['swims']} Schwimmeinheiten diese Woche (Ziel 3). Groesster Hebel im Plan.",
                }
            )

    # (5) Fehlende Bewertungen — sonst rechnet die Lastampel mit Luecken
    if weekly:
        cur = weekly[-1]
        if cur["rpe_missing"] and cur["rpe_covered"] == 0:
            flags.append(
                {
                    "level": "amber",
                    "metric": "RPE",
                    "text": f"{cur['rpe_missing']} Einheiten ohne Bewertung. sRPE-Last ist unvollstaendig — auf der Uhr bewerten oder in manual.json nachtragen.",
                }
            )
        elif cur["rpe_missing"] > cur["rpe_covered"]:
            flags.append(
                {
                    "level": "amber",
                    "metric": "RPE",
                    "text": f"{cur['rpe_missing']} von {cur['rpe_missing'] + cur['rpe_covered']} Einheiten ohne Bewertung. Lastzahl untertreibt.",
                }
            )

    # (6) Schlaf
    if sleep:
        last7 = [s.get("total_h") for s in sleep[-7:] if s.get("total_h")]
        if last7 and sum(last7) / len(last7) < SLEEP_TARGET_H:
            flags.append(
                {
                    "level": "amber",
                    "metric": "Schlaf",
                    "text": f"Schnitt {sum(last7)/len(last7):.1f} h (Ziel {SLEEP_TARGET_H} h). Im Defizit zaehlt das doppelt.",
                }
            )

    # (7) HRV-Einbruch (Oura) — feiner als RHF, gerade im Defizit
    hrv_vals = [s.get("hrv") for s in sleep if s.get("hrv")]
    if len(hrv_vals) >= 10:
        baseline = sum(hrv_vals[-28:-3]) / len(hrv_vals[-28:-3]) if len(hrv_vals) >= 14 else sum(hrv_vals[:-3]) / max(1, len(hrv_vals[:-3]))
        recent = hrv_vals[-3:]
        if baseline > 0 and all(v < baseline * 0.85 for v in recent):
            flags.append(
                {
                    "level": "amber",
                    "metric": "HRV",
                    "text": f"HRV 3 Tage unter 85% der Baseline ({baseline:.0f} ms). Fruehes Ueberlastungssignal — Qualitaet reduzieren, Schlaf schuetzen.",
                }
            )

    if not flags:
        flags.append(
            {"level": "green", "metric": "Alles", "text": "Keine Warnungen. Plan laeuft."}
        )
    return flags


def build_css(activities):
    """Schwimm-Tempotrend: Median s/100m je Woche."""
    by_week = {}
    for a in activities:
        if a["sport"] != "swim" or not a.get("pace_per_100m"):
            continue
        w = plan_week(date.fromisoformat(a["date"]))
        by_week.setdefault(w, []).append(a["pace_per_100m"])
    out = []
    for w in sorted(by_week):
        p = sorted(by_week[w])
        out.append({"week": w, "median_pace_s": p[len(p) // 2]})
    return out


def build_by_sport(activities):
    """
    Progress je Sportart: Summen ueber den ganzen Plan + aktuelle Woche.
    Alle Garmin-Sportarten, nicht nur die drei Kerndisziplinen.
    """
    cur_w = plan_week(date.today())
    stats = {}
    for a in activities:
        w = plan_week(date.fromisoformat(a["date"]))
        if w < 1:
            continue
        s = a["sport"]
        st = stats.setdefault(
            s,
            {
                "sport": s,
                "label": SPORT_LABELS.get(s, s),
                "sessions_total": 0,
                "sessions_week": 0,
                "hours_total": 0.0,
                "km_total": 0.0,
                "target_per_week": SPORT_TARGETS.get(s),
                "longest_km": 0.0,
                "longest_min": 0,
            },
        )
        st["sessions_total"] += 1
        st["hours_total"] += a["duration_min"] / 60
        st["km_total"] += a["distance_km"] or 0
        st["longest_km"] = max(st["longest_km"], a["distance_km"] or 0)
        st["longest_min"] = max(st["longest_min"], a["duration_min"])
        if w == cur_w:
            st["sessions_week"] += 1

    for st in stats.values():
        st["hours_total"] = round(st["hours_total"], 1)
        st["km_total"] = round(st["km_total"], 1)
        st["longest_km"] = round(st["longest_km"], 1)

    # in Plan-Reihenfolge sortiert zurueckgeben
    return [stats[s] for s in SPORT_ORDER if s in stats]


def build_analysis(activities, weekly, manual):
    """
    Analyse der Einheiten gegen die 70.3-Ziele.
    - Zeit-in-Zone beim Rad (Sweet Spot / Schwelle als FTP-Treiber)
    - Schwimm-Volumen gegen Renndistanz
    - Geh/Lauf-Aufbau gegen 21,1 km
    - Trainingslast-Trend (sRPE)
    """
    ftp = manual.get("ftp_w") or 250

    # --- Rad: Zeit-in-Zone ueber Normalized Power ---
    zone_min = {"recovery": 0, "endurance": 0, "tempo": 0, "sweetspot": 0, "threshold": 0, "vo2": 0}
    bike_sessions = 0
    for a in activities:
        if a["sport"] != "bike":
            continue
        np = a.get("norm_power") or a.get("avg_power")
        if not np:
            continue
        bike_sessions += 1
        pct = np / ftp
        dur = a["duration_min"]
        if pct < 0.55:
            zone_min["recovery"] += dur
        elif pct < 0.75:
            zone_min["endurance"] += dur
        elif pct < 0.88:
            zone_min["tempo"] += dur
        elif pct < 0.95:
            zone_min["sweetspot"] += dur
        elif pct < 1.05:
            zone_min["threshold"] += dur
        else:
            zone_min["vo2"] += dur

    # --- Schwimmen: laengste kontinuierliche Distanz vs. 1,9 km ---
    swim_longest = max((a["distance_km"] for a in activities
                        if a["sport"] == "swim" and a.get("distance_km")), default=0)

    # --- Gehen/Laufen: laengste Einheit vs. 21,1 km Renndistanz ---
    walk_run = [a for a in activities if a["sport"] in ("walk", "run")]
    wr_longest = max((a["distance_km"] for a in walk_run if a.get("distance_km")), default=0)
    wr_total = round(sum(a["distance_km"] or 0 for a in walk_run), 1)

    # --- Trainingslast-Trend: letzte 4 Nicht-Erholungswochen ---
    load_trend = [
        {"week": w["week"], "load": w["srpe_load"]}
        for w in weekly if w["srpe_load"] > 0
    ][-6:]

    return {
        "ftp_used": ftp,
        "bike_zone_min": {k: round(v) for k, v in zone_min.items()},
        "bike_quality_min": round(zone_min["sweetspot"] + zone_min["threshold"] + zone_min["vo2"]),
        "bike_sessions_analyzed": bike_sessions,
        "swim_longest_km": round(swim_longest, 2),
        "swim_race_km": 1.9,
        "walkrun_longest_km": round(wr_longest, 1),
        "walkrun_total_km": wr_total,
        "walkrun_race_km": 21.1,
        "load_trend": load_trend,
    }


def build_forecast(weights, manual, days_to_race, targets):
    """
    Schlichte lineare Hochrechnung auf den Renntag. Kein Anspruch auf Praezision —
    zeigt nur, ob der aktuelle Trend Richtung Ziel laeuft oder nicht.
    Basiert auf dem Gewichtstrend (genug Datenpunkte) und den Testwerten aus manual.json.
    """
    out = {}

    # Gewicht: linearer Trend der letzten 30 Eintraege
    pts = [(i, w["kg"]) for i, w in enumerate(weights[-30:]) if w.get("kg")]
    if len(pts) >= 4:
        n = len(pts)
        sx = sum(p[0] for p in pts); sy = sum(p[1] for p in pts)
        sxx = sum(p[0]**2 for p in pts); sxy = sum(p[0]*p[1] for p in pts)
        denom = (n*sxx - sx*sx)
        if denom:
            slope = (n*sxy - sx*sy) / denom          # kg pro Eintrag
            # Annahme ~3 Wiegungen/Woche
            per_day = slope / (7/3)
            current = pts[-1][1]
            projected = current + per_day * days_to_race
            out["weight"] = {
                "current": round(current, 1),
                "projected": round(projected, 1),
                "target": targets["weight_dec_kg"],
                "on_track": projected <= targets["weight_dec_kg"] + 1,
            }

    # FTP: braucht mindestens zwei Testwerte, sonst nur Ist gegen Ziel
    ftp = manual.get("ftp_w")
    if ftp:
        out["ftp"] = {
            "current": ftp,
            "target": targets["ftp_race_w"],
            "gap": targets["ftp_race_w"] - ftp,
            "on_track": ftp >= 250 + (targets["ftp_race_w"] - 250) * (1 - days_to_race/264),
        }

    css = manual.get("css_s")
    if css:
        out["css"] = {
            "current": css,
            "target": targets["css_race_s"],
            "gap": css - targets["css_race_s"],
        }

    return out


# ---------------------------------------------------------------- Main


def main():
    end = date.today()
    start = end - timedelta(days=LOOKBACK_DAYS)

    manual = {}
    if MANUAL.exists():
        manual = json.loads(MANUAL.read_text())

    api, activities, rhr, weights = fetch_garmin(start, end)

    # Selbstbeurteilung der Uhr nachladen (gecacht)
    cache = json.loads(RPE_CACHE.read_text()) if RPE_CACHE.exists() else {}
    try:
        cache = fetch_rpe(api, activities, cache)
        # Cache auf den Lookback-Zeitraum eindampfen
        cutoff = start.isoformat()
        cache = {k: v for k, v in cache.items() if v.get("date", "9999") >= cutoff}
        RPE_CACHE.write_text(json.dumps(cache, indent=2, ensure_ascii=False))
    except Exception as e:
        log(f"RPE-Abruf fehlgeschlagen, nutze manual.json: {e}")

    try:
        sleep, readiness = fetch_oura(start, end)
    except Exception as e:
        log(f"Oura fehlgeschlagen: {e}")
        sleep, readiness = [], []

    # Gewicht: Garmin bevorzugt, sonst manuell
    if not weights:
        weights = [
            {"date": m["date"], "kg": m["weight_kg"]}
            for m in manual.get("daily", [])
            if m.get("weight_kg")
        ]

    weekly = build_weekly(activities, manual)
    cur_week = plan_week(end)
    days_to_race = (RACE_DATE - end).days

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "athlete": "Henrik Hundesrügge",
        "race": {
            "name": "IRONMAN 70.3 Venice-Jesolo",
            "date": RACE_DATE.isoformat(),
            "days_to_go": days_to_race,
            "weeks_to_go": days_to_race // 7,
            "swim_km": 1.9,
            "bike_km": 90,
            "run_km": 21.1,
        },
        "plan": {
            "current_week": cur_week,
            "phase": phase_for_week(cur_week),
            "recovery_week": is_recovery_week(cur_week),
            "weeks_total": 26,
        },
        "targets": {
            "ftp_dec_w": 285,
            "ftp_race_w": 300,
            "css_dec_s": 105,      # 1:45/100m
            "css_race_s": 100,     # 1:40/100m
            "weight_dec_kg": 85.5,
            "waist_target_cm": 94,
        },
        "current": {
            "weight_kg": weights[-1]["kg"] if weights else None,
            "rhr_bpm": rhr[-1]["bpm"] if rhr else None,
            "sleep_h_7d": (
                round(
                    sum(s["total_h"] for s in sleep[-7:] if s.get("total_h"))
                    / max(1, len([s for s in sleep[-7:] if s.get("total_h")])),
                    1,
                )
                if sleep
                else None
            ),
            "readiness": readiness[-1]["score"] if readiness else None,
            "ftp_w": manual.get("ftp_w"),
            "css_s": manual.get("css_s"),
            "waist_cm": manual.get("waist_cm"),
        },
        "flags": build_flags(rhr, weekly, manual, sleep),
        "weekly": weekly,
        "by_sport": build_by_sport(activities),
        "analysis": build_analysis(activities, weekly, manual),
        "forecast": build_forecast(weights, manual, days_to_race, {
            "ftp_race_w": 285, "css_race_s": 110, "weight_dec_kg": 83.5,
        }),
        "activities": sorted(activities, key=lambda a: a["date"], reverse=True)[:40],
        "rhr": rhr[-60:],
        "weights": weights[-60:],
        "sleep": sleep[-30:],
        "swim_pace": build_css(activities),
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    log(f"Geschrieben: {OUT} ({len(activities)} Aktivitaeten, Woche {cur_week})")


if __name__ == "__main__":
    main()
