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
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests
from garminconnect import Garmin

# ---------------------------------------------------------------- Konfiguration

PLAN_START = date.fromisoformat(os.getenv("PLAN_START", "2026-07-13"))
LOOKBACK_DAYS = 90          # so viel Historie halten wir im JSON
DATA = Path(__file__).resolve().parent.parent / "data"
OUT = DATA / "dashboard.json"
MANUAL = DATA / "manual.json"
RPE_CACHE = DATA / "rpe_cache.json"

# Selbstbeurteilung der Uhr: Garmin skaliert intern 0-100.
# Reihenfolge = Wahrscheinlichkeit. probe_rpe.py findet den echten Namen.
EFFORT_KEYS = ["directWorkoutRpe", "workoutRpe", "perceivedEffort", "rpe",
               "directPerceivedEffort"]
FEEL_KEYS = ["directWorkoutFeel", "workoutFeel", "feel", "perceivedFeel"]

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


def pick(d: dict, keys: list):
    """Ersten vorhandenen Schluessel aus einer Kandidatenliste zurueckgeben."""
    for k in keys:
        if d.get(k) is not None:
            return k, d[k]
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
        except Exception as e:
            log(f"Detail {aid} fehlgeschlagen: {e}")
            continue

        ekey, eraw = pick(detail, EFFORT_KEYS)
        fkey, fraw = pick(detail, FEEL_KEYS)
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
        log("WARNUNG: keine Selbstbeurteilung gefunden. Auf der Uhr aktiviert? "
            "Sonst probe_rpe.py laufen lassen.")
    return cache


def sport_bucket(type_key: str) -> str:
    t = (type_key or "").lower()
    if "swim" in t:
        return "swim"
    if "cycl" in t or "bik" in t or "ride" in t or "virtual_ride" in t:
        return "bike"
    if "strength" in t or "training" in t or "fitness" in t:
        return "gym"
    return "other"


# ---------------------------------------------------------------- Garmin


def fetch_garmin(start: date, end: date):
    email = os.environ["GARMIN_EMAIL"]
    password = os.environ["GARMIN_PASSWORD"]

    log("Garmin: Login")
    api = Garmin(email, password)
    api.login()

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

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "athlete": "Henrik Hundesrügge",
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
