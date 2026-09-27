#!/usr/bin/env python3
"""
campaign.py — die einzige Quelle fuer Kampagnen-Zielwerte.

Liest targets.json aus dem Repo-Root und stellt daraus abgeleitete Helfer bereit.
Wird importiert von sync.py, build_dashboard.py und garmin_workouts.py.

Wenn sich ein Ziel aendert, aendert es sich in targets.json — nirgends sonst.

v6 (27.09.2026):
- Rennleistung relativ zur aktuellen FTP (race_if) statt fixer Wattzahl
- Phase "Wiedereinstieg", Wochenschablone (week_template) aus targets.json
- Gewichtsziel linear ab dem letzten Messpunkt (body.checkpoint)
"""

from __future__ import annotations

import json
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
TARGETS_FILE = Path(os.getenv("TARGETS_FILE", ROOT / "targets.json"))
MANUAL_FILE = ROOT / "data" / "manual.json"

# --------------------------------------------------------------------- Laden

_FALLBACK: dict[str, Any] = {
    "campaign": {
        "race": "IRONMAN 70.3 Venice-Jesolo",
        "race_date": "2027-04-24",
        "week_1_monday": "2026-08-03",
        "total_weeks": 38,
        "recovery_weeks": [4, 8, 16, 20, 24, 28, 32],
        "phases": [
            {"name": "Grundlage", "weeks": [1, 8], "bike_hours": 4.5},
            {"name": "Wiedereinstieg", "weeks": [9, 11], "bike_hours": 4.0},
            {"name": "Build I", "weeks": [12, 18], "bike_hours": 5.0},
            {"name": "Build II", "weeks": [19, 28], "bike_hours": 6.0},
            {"name": "Rennspezifisch", "weeks": [29, 35], "bike_hours": 6.0},
            {"name": "Taper", "weeks": [36, 38], "bike_hours": 3.0},
        ],
    },
    "bike": {"race_if": [0.75, 0.80], "ftp_start_w": 250, "ftp_target_w": 280},
    "swim": {"sessions_per_week": 2, "css_target_sec_per_100m": 110},
    "body": {"weight_start_kg": 92, "weight_target_w28_kg": 83.5},
}


def _load() -> dict[str, Any]:
    try:
        return json.loads(TARGETS_FILE.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"[campaign] targets.json nicht lesbar ({exc}) – Fallback aktiv")
        return _FALLBACK


def _load_manual() -> dict[str, Any]:
    try:
        return json.loads(MANUAL_FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


T: dict[str, Any] = _load()

CAMPAIGN = T.get("campaign", _FALLBACK["campaign"])
BIKE = T.get("bike", _FALLBACK["bike"])
SWIM = T.get("swim", _FALLBACK["swim"])
RUN = T.get("run", {})
WALK = RUN  # Rueckwaertskompatibilitaet (v5 hiess der Block "walk")
BODY = T.get("body", _FALLBACK["body"])
RECOVERY_CFG = T.get("recovery", {})
AERO = T.get("aero", {})
WEEK_TEMPLATE = CAMPAIGN.get("week_template", {})

# --------------------------------------------------------------- Eckdaten

PLAN_START = date.fromisoformat(os.getenv("PLAN_START", CAMPAIGN["week_1_monday"]))
RACE_DATE = date.fromisoformat(os.getenv("RACE_DATE", CAMPAIGN["race_date"]))
TOTAL_WEEKS = int(CAMPAIGN.get("total_weeks", 38))
RECOVERY_WEEKS = set(CAMPAIGN.get("recovery_weeks", []))
RACE_NAME = CAMPAIGN.get("race", "IRONMAN 70.3")

RACE_IF = tuple(BIKE.get("race_if", [0.75, 0.80]))
MAX_RACE_IF = float(BIKE.get("max_race_if", 0.82))
FTP_START = int(BIKE.get("ftp_start_w", 250))
FTP_TARGET = int(BIKE.get("ftp_target_w", 280))
FTP_STRETCH = int(BIKE.get("ftp_stretch_w", FTP_TARGET))
CSS_START = int(SWIM.get("css_start_sec_per_100m", 120))
CSS_TARGET = int(SWIM.get("css_target_sec_per_100m", 110))
SWIMS_PER_WEEK = int(SWIM.get("sessions_per_week", 2))
WEIGHT_START = float(BODY.get("weight_start_kg", 92))
WEIGHT_TARGET = float(BODY.get("weight_target_w28_kg", 83.5))
DEFICIT_ENDS_WEEK = int(BODY.get("deficit_ends_week", 29))

SLEEP_TARGET_H = float(RECOVERY_CFG.get("sleep_hours_min", 7.5))
RHR_FLAG_DELTA = int(RECOVERY_CFG.get("rhr_amber_bpm_above_baseline", 5))
RHR_FLAG_DAYS = int(RECOVERY_CFG.get("rhr_amber_consecutive_days", 3))
HRV_FLAG_DAYS = int(RECOVERY_CFG.get("hrv_amber_consecutive_days", 3))
SRPE_FLAG_PCT = int(RECOVERY_CFG.get("srpe_max_weekly_increase_pct", 15))
HRV_AMBER_PCT = float(RECOVERY_CFG.get("hrv_amber_pct_of_baseline", 85)) / 100
KNEE_FLAG = int(RUN.get("knee_pain_amber_score", 3))
RUN_MAX_KM = float(RUN.get("max_session_km", 12))
RUN_HR_CAP = int(RUN.get("easy_hr_cap_bpm", 150))
RUN_MAX_INCREASE_PCT = float(RUN.get("max_longest_increase_pct", 10))

# --------------------------------------------------------------- FTP / Rennleistung


def current_ftp() -> int:
    """Aktuelle FTP aus manual.json, sonst Startwert aus targets.json."""
    ftp = _load_manual().get("ftp_w")
    return int(ftp) if isinstance(ftp, (int, float)) and ftp > 100 else FTP_START


def race_power(ftp: float | None = None) -> tuple[int, int]:
    """Rennleistungs-Band in Watt = race_if x FTP (Standard: aktuelle FTP)."""
    f = ftp or current_ftp()
    return int(round(f * RACE_IF[0])), int(round(f * RACE_IF[1]))


# Rueckwaertskompatibel: Band bei aktueller FTP
RACE_POWER = race_power()

# --------------------------------------------------------------- Helfer


def plan_week(d: date) -> int:
    """Kampagnenwoche 1..TOTAL_WEEKS fuer ein Datum (kann ausserhalb liegen)."""
    return (d - PLAN_START).days // 7 + 1


def week_monday(week: int) -> date:
    return PLAN_START + timedelta(weeks=week - 1)


def phase_name(week: int) -> str:
    for ph in CAMPAIGN["phases"]:
        lo, hi = ph["weeks"]
        if lo <= week <= hi:
            return ph["name"]
    return "vor Plan" if week < 1 else "nach Renntag"


def phase_for_week(week: int) -> str:
    for i, ph in enumerate(CAMPAIGN["phases"], start=1):
        lo, hi = ph["weeks"]
        if lo <= week <= hi:
            return f"{i} – {ph['name']}"
    return "vor Plan" if week < 1 else "nach Renntag"


def phase_key(week: int) -> str:
    """Kleingeschriebener Phasenname – Schluessel in targets.json-Untertabellen."""
    for ph in CAMPAIGN["phases"]:
        lo, hi = ph["weeks"]
        if lo <= week <= hi:
            return ph["name"].lower().replace(" ", "_")
    return "grundlage"


def bike_hours_target(week: int) -> float:
    for ph in CAMPAIGN["phases"]:
        lo, hi = ph["weeks"]
        if lo <= week <= hi:
            return float(ph.get("bike_hours", 5.0))
    return 5.0


def is_recovery_week(week: int) -> bool:
    return week in RECOVERY_WEEKS


def sport_targets(week: int) -> dict[str, int]:
    """
    Wochen-Soll je Disziplin. Rad: 3 Einheiten, ab Phase mit >= 6 h Radstunden 4
    (Zusatz-Z2 am Sonntag). Laufen/Gehen bewusst ohne Soll (kein festes Lauftraining).
    """
    bikes = 4 if bike_hours_target(week) >= 6 else 3
    if is_recovery_week(week):
        bikes -= 1
    return {"swim": SWIMS_PER_WEEK, "bike": bikes, "gym": 2}


def _waypoint(table: dict, week: int, default=None):
    """Naechstliegender Zielwert aus einer w<N>-Tabelle, der noch vor uns liegt."""
    pts = sorted((int(k[1:]), v) for k, v in table.items() if k.startswith("w") and k[1:].isdigit())
    for w, v in pts:
        if week <= w:
            return v
    return pts[-1][1] if pts else default


def ftp_waypoint(week: int) -> int:
    return int(_waypoint(BIKE.get("ftp_waypoints", {}), week, FTP_TARGET) or FTP_TARGET)


def race_power_hold_target(week: int) -> int:
    tbl = {k: v for k, v in BIKE.get("race_power_hold_minutes", {}).items() if not k.startswith("_")}
    return int(_waypoint(tbl, week, 0) or 0) if week >= 12 else 0


def weight_target(week: int) -> float:
    """Lineares Ziel vom letzten Messpunkt (body.checkpoint) bis W28, danach halten."""
    cp = BODY.get("checkpoint") or {}
    start_week = int(cp.get("week", 1))
    start_kg = float(cp.get("weight_kg", WEIGHT_START))
    if week >= 28:
        return WEIGHT_TARGET
    if week <= start_week:
        return start_kg
    frac = (week - start_week) / (28 - start_week)
    return round(start_kg - (start_kg - WEIGHT_TARGET) * frac, 1)


def summary() -> dict[str, Any]:
    """Kompakter Zielblock fuer dashboard.json."""
    lo, hi = race_power()
    return {
        "version": T.get("version"),
        "ftp_start_w": FTP_START,
        "ftp_race_w": FTP_TARGET,
        "ftp_stretch_w": FTP_STRETCH,
        "race_if": list(RACE_IF),
        "race_power_w": [lo, hi],
        "race_power_plan_w": int(round((lo + hi) / 2)),
        "css_start_s": CSS_START,
        "css_race_s": CSS_TARGET,
        "weight_start_kg": float((BODY.get("checkpoint") or {}).get("weight_kg", WEIGHT_START)),
        "weight_target_kg": WEIGHT_TARGET,
        "weight_race_day_kg": BODY.get("weight_race_day_kg", [83, 85]),
        "deficit_ends_week": DEFICIT_ENDS_WEEK,
        "waist_target_cm": 94,
        "swims_per_week": SWIMS_PER_WEEK,
        "run_max_km": RUN_MAX_KM,
        "run_hr_cap_bpm": RUN_HR_CAP,
        "decoupling_target_pct": BIKE.get("decoupling_target_pct", 5.0),
        "tiz_target_min": BIKE.get("weekly_minutes_in_zone_88_105_pct", {}),
        "aero_cda_target": AERO.get("cda_target"),
        "pacing_rule": BIKE.get("pacing_rule", ""),
    }


if __name__ == "__main__":
    w = plan_week(date.today())
    lo, hi = race_power()
    print(f"{RACE_NAME} am {RACE_DATE} · {TOTAL_WEEKS} Wochen ab {PLAN_START}")
    print(f"Heute: Woche {w} ({phase_for_week(w)}{', Entlastung' if is_recovery_week(w) else ''})")
    print(f"Soll diese Woche: {sport_targets(w)} · Radstunden {bike_hours_target(w)}")
    print(f"FTP aktuell {current_ftp()} W · Wegmarke {ftp_waypoint(w)} W · Rennleistung {lo}-{hi} W · "
          f"Block-Ziel {race_power_hold_target(w)} min · Gewicht-Soll {weight_target(w)} kg")
