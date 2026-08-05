#!/usr/bin/env python3
"""
garmin_workouts.py
==================
Erzeugt die komplette 70.3-Kampagne (Venice-Jesolo, 24.04.2027) als strukturierte
Garmin-Workouts, lädt sie in Garmin Connect hoch und legt sie im Trainingskalender
auf das jeweilige Datum. Damit erscheinen alle Einheiten auf der Forerunner 955
unter Training > Workouts bzw. als "Heutiges Workout" und lassen sich direkt starten.

Abhängigkeiten:
    pip install "garminconnect[workout]" curl_cffi

Nutzung:
    python3 garmin_workouts.py --dry-run                # nur JSON erzeugen, nichts hochladen
    python3 garmin_workouts.py --weeks 1-4              # Wochen 1-4 hochladen + einplanen
    python3 garmin_workouts.py --weeks 1-37             # gesamte Kampagne
    python3 garmin_workouts.py --clean                  # alle Workouts mit PREFIX löschen
    python3 garmin_workouts.py --weeks 5-8 --no-schedule
    python3 garmin_workouts.py --weeks 1-2 --push       # zusätzlich direkt an die Uhr schicken

Zugangsdaten über Umgebungsvariablen:
    GARMIN_EMAIL, GARMIN_PASSWORD  (Login nur beim ersten Mal; danach Token-Cache)
    GARMINTOKENS                   (optional, Pfad zum Token-Verzeichnis)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable

# ----------------------------------------------------------------------------
# 1. KONFIGURATION  – hier anpassen, sonst nichts
# ----------------------------------------------------------------------------

RACE_DATE = date(2027, 4, 24)      # IRONMAN 70.3 Venice-Jesolo (Samstag)
TOTAL_WEEKS = 38                   # Kampagnenlänge -> Woche 1 = Mo 03.08.2026
PREFIX = "70.3"                    # Namenspräfix aller erzeugten Workouts

FTP = 250                          # aktuelle FTP in Watt (wird aus manual.json überschrieben)
FTP_TARGET = 300                   # Zielwert Renntag – nötig für 245 W bei IF 0.82
RACE_POWER = (235, 250)            # ZIELGRÖSSE der Kampagne: Wattband über 90 km
MAX_RACE_IF = 0.88                 # Warnschwelle: Rennleistung / aktuelle FTP
CSS = 120                          # aktuelle CSS in Sekunden pro 100 m (2:00)
POOL_LENGTH_M = 25                 # Beckenlänge
HR_MAX = 185                       # zur Ableitung der Geh-Herzfrequenzbänder
WEIGHT_KG = 92                     # nur für Info im Beschreibungstext

MANUAL_JSON = Path("data/manual.json")   # Ist-Werte aus dem Tracker (FTP, CSS); optional
TARGETS_JSON = Path("targets.json")      # Zielwerte – zentrale Quelle für Plan und Dashboard

# Trainingswochentage (0 = Montag)
DAY_REST, DAY_BIKE_Q, DAY_SWIM_1, DAY_BIKE_2, DAY_SWIM_2, DAY_LONG_BIKE, DAY_WALK = range(7)

STATE_FILE = Path("garmin_workout_state.json")
OUT_DIR = Path("workouts_json")

# ----------------------------------------------------------------------------
# 2. Garmin-Bausteine
# ----------------------------------------------------------------------------

from garminconnect import Garmin  # noqa: E402
from garminconnect.workout import (  # noqa: E402
    CyclingWorkout,
    ExecutableStep,
    RepeatGroup,
    StrengthWorkout,
    SwimmingWorkout,
    WalkingWorkout,
    WorkoutSegment,
    create_repeat_group,
    create_strength_set,
)

STEP = {
    "warmup":   {"stepTypeId": 1, "stepTypeKey": "warmup", "displayOrder": 1},
    "cooldown": {"stepTypeId": 2, "stepTypeKey": "cooldown", "displayOrder": 2},
    "interval": {"stepTypeId": 3, "stepTypeKey": "interval", "displayOrder": 3},
    "recovery": {"stepTypeId": 4, "stepTypeKey": "recovery", "displayOrder": 4},
    "rest":     {"stepTypeId": 5, "stepTypeKey": "rest", "displayOrder": 5},
}

COND = {
    "lap.button": {"conditionTypeId": 1, "conditionTypeKey": "lap.button", "displayOrder": 1, "displayable": True},
    "time":       {"conditionTypeId": 2, "conditionTypeKey": "time", "displayOrder": 2, "displayable": True},
    "distance":   {"conditionTypeId": 3, "conditionTypeKey": "distance", "displayOrder": 3, "displayable": True},
}

TGT = {
    "none":     {"workoutTargetTypeId": 1, "workoutTargetTypeKey": "no.target", "displayOrder": 1},
    "power":    {"workoutTargetTypeId": 2, "workoutTargetTypeKey": "power.zone", "displayOrder": 2},
    "cadence":  {"workoutTargetTypeId": 3, "workoutTargetTypeKey": "cadence", "displayOrder": 3},
    "hr":       {"workoutTargetTypeId": 4, "workoutTargetTypeKey": "heart.rate.zone", "displayOrder": 4},
    "pace":     {"workoutTargetTypeId": 6, "workoutTargetTypeKey": "pace.zone", "displayOrder": 6},
}

SPORT = {
    "cycling":  {"sportTypeId": 2, "sportTypeKey": "cycling", "displayOrder": 2},
    "swimming": {"sportTypeId": 4, "sportTypeKey": "swimming", "displayOrder": 3},
    "strength": {"sportTypeId": 5, "sportTypeKey": "strength_training", "displayOrder": 5},
    "walking":  {"sportTypeId": 17, "sportTypeKey": "walking", "displayOrder": 17},
}

POOL_UNIT = {"unitId": 1, "unitKey": "meter", "factor": 100.0}


class Order:
    """Fortlaufende, eindeutige stepOrder-Zähler."""

    def __init__(self) -> None:
        self.n = 0

    def next(self) -> int:
        self.n += 1
        return self.n

    def skip(self, k: int) -> None:
        self.n += k


def step(
    order: Order,
    kind: str,
    *,
    seconds: float | None = None,
    meters: float | None = None,
    target: str = "none",
    v1: float | None = None,
    v2: float | None = None,
    note: str | None = None,
) -> ExecutableStep:
    """Ein ausführbarer Schritt mit Zeit- oder Distanzende und optionalem Ziel."""
    if seconds is not None:
        cond, value = COND["time"], float(seconds)
    elif meters is not None:
        cond, value = COND["distance"], float(meters)
    else:
        cond, value = COND["lap.button"], 0.0

    extra: dict[str, Any] = {}
    if v1 is not None:
        extra["targetValueOne"] = float(v1)
    if v2 is not None:
        extra["targetValueTwo"] = float(v2)
    if note:
        extra["description"] = note

    return ExecutableStep(
        stepOrder=order.next(),
        stepType=STEP[kind],
        endCondition=cond,
        endConditionValue=value,
        targetType=TGT[target],
        **extra,
    )


def watts(pct: float) -> int:
    return int(round(FTP * pct))


def pace_ms(sec_per_100m: float) -> float:
    """Garmin erwartet Pace-Ziele in m/s."""
    return 100.0 / sec_per_100m


def hr_band(lo: float, hi: float) -> tuple[int, int]:
    return int(round(HR_MAX * lo)), int(round(HR_MAX * hi))


def duration_of(steps: list[ExecutableStep | RepeatGroup]) -> int:
    """Grobe Gesamtdauer in Sekunden (Distanzschritte werden geschätzt)."""
    total = 0.0
    for s in steps:
        if isinstance(s, RepeatGroup):
            total += s.numberOfIterations * duration_of(s.workoutSteps)
        else:
            cond = (s.endCondition or {}).get("conditionTypeKey")
            val = s.endConditionValue or 0.0
            if cond == "time":
                total += val
            elif cond == "distance":
                total += val / 100.0 * CSS      # Schwimmen: Distanz über CSS schätzen
            else:
                total += 60.0
    return int(total)


def renumber(steps: list[Any], start: int = 1) -> int:
    """Vergibt stepOrder neu: Gruppe zuerst, dann ihre Kinder (Garmin-Konvention)."""
    n = start
    for s in steps:
        s.stepOrder = n
        n += 1
        if isinstance(s, RepeatGroup):
            n = renumber(s.workoutSteps, n)
    return n


@dataclass
class Session:
    """Eine geplante Einheit."""
    name: str
    sport: str
    steps: list[Any]
    description: str = ""
    day: int = 0
    extra: dict[str, Any] = field(default_factory=dict)


# ----------------------------------------------------------------------------
# 3. Einheiten-Bausteine
# ----------------------------------------------------------------------------

def bike_sweetspot(reps: int, minutes: int, lo: float = 0.88, hi: float = 0.93) -> tuple[list, str]:
    o = Order()
    steps = [step(o, "warmup", seconds=12 * 60, target="power",
                  v1=watts(0.55), v2=watts(0.70), note="Locker einrollen, TF 90-95")]
    block = [
        step(o, "interval", seconds=minutes * 60, target="power",
             v1=watts(lo), v2=watts(hi), note=f"Sweet Spot {watts(lo)}-{watts(hi)} W, TF 85-95"),
        step(o, "recovery", seconds=5 * 60, target="power", v1=watts(0.45), v2=watts(0.60)),
    ]
    steps.append(create_repeat_group(reps, block, o.next()))
    o.skip(0)
    steps.append(step(o, "cooldown", seconds=8 * 60, target="power", v1=watts(0.40), v2=watts(0.55)))
    return steps, f"Sweet Spot {reps}x{minutes} min @ {watts(lo)}-{watts(hi)} W"


def bike_threshold(reps: int, minutes: int, lo: float = 0.95, hi: float = 1.00) -> tuple[list, str]:
    o = Order()
    steps = [step(o, "warmup", seconds=15 * 60, target="power",
                  v1=watts(0.55), v2=watts(0.70), note="Einrollen + 3x30 s Anrisse")]
    block = [
        step(o, "interval", seconds=minutes * 60, target="power",
             v1=watts(lo), v2=watts(hi), note=f"Schwelle {watts(lo)}-{watts(hi)} W, gleichmäßig"),
        step(o, "recovery", seconds=6 * 60, target="power", v1=watts(0.45), v2=watts(0.60)),
    ]
    steps.append(create_repeat_group(reps, block, o.next()))
    steps.append(step(o, "cooldown", seconds=10 * 60, target="power", v1=watts(0.40), v2=watts(0.55)))
    return steps, f"Schwelle {reps}x{minutes} min @ {watts(lo)}-{watts(hi)} W"


def bike_over_under(sets: int = 3, blocks: int = 3) -> tuple[list, str]:
    o = Order()
    steps = [step(o, "warmup", seconds=15 * 60, target="power", v1=watts(0.55), v2=watts(0.70))]
    inner = [
        step(o, "interval", seconds=120, target="power", v1=watts(0.93), v2=watts(0.97), note="UNDER"),
        step(o, "interval", seconds=60, target="power", v1=watts(1.03), v2=watts(1.08), note="OVER"),
    ]
    inner_group = create_repeat_group(blocks, inner, o.next())
    outer = [inner_group, step(o, "recovery", seconds=6 * 60, target="power", v1=watts(0.45), v2=watts(0.60))]
    steps.append(create_repeat_group(sets, outer, o.next()))
    steps.append(step(o, "cooldown", seconds=10 * 60, target="power", v1=watts(0.40), v2=watts(0.55)))
    return steps, f"Over-Unders {sets}x{blocks}x(2 min {watts(0.95)} W / 1 min {watts(1.05)} W)"


def bike_vo2(reps: int, minutes: int, lo: float, hi: float) -> tuple[list, str]:
    o = Order()
    steps = [step(o, "warmup", seconds=18 * 60, target="power",
                  v1=watts(0.55), v2=watts(0.75), note="Gründlich einrollen, 3x1 min @ 100% zum Öffnen")]
    block = [
        step(o, "interval", seconds=minutes * 60, target="power",
             v1=watts(lo), v2=watts(hi), note=f"VO2max {watts(lo)}-{watts(hi)} W, TF 95-105"),
        step(o, "recovery", seconds=int(minutes * 60 * 1.2), target="power", v1=watts(0.40), v2=watts(0.55)),
    ]
    steps.append(create_repeat_group(reps, block, o.next()))
    steps.append(step(o, "cooldown", seconds=12 * 60, target="power", v1=watts(0.40), v2=watts(0.50)))
    return steps, f"VO2max {reps}x{minutes} min @ {watts(lo)}-{watts(hi)} W"


def bike_endurance(minutes: int, ss_blocks: int = 0, ss_minutes: int = 15) -> tuple[list, str]:
    o = Order()
    steps = [step(o, "warmup", seconds=10 * 60, target="power", v1=watts(0.50), v2=watts(0.65))]
    if ss_blocks:
        block = [
            step(o, "interval", seconds=ss_minutes * 60, target="power",
                 v1=watts(0.88), v2=watts(0.93), note="Sweet Spot, in Aeroposition"),
            step(o, "recovery", seconds=8 * 60, target="power", v1=watts(0.55), v2=watts(0.68)),
        ]
        steps.append(create_repeat_group(ss_blocks, block, o.next()))
        rest = minutes - 18 - ss_blocks * (ss_minutes + 8)
    else:
        rest = minutes - 18
    steps.append(step(o, "interval", seconds=max(rest, 10) * 60, target="power",
                      v1=watts(0.56), v2=watts(0.72), note="Zone 2, gleichmäßig, TF 85-90"))
    steps.append(step(o, "cooldown", seconds=8 * 60, target="power", v1=watts(0.40), v2=watts(0.55)))
    suffix = f" inkl. {ss_blocks}x{ss_minutes} min Sweet Spot" if ss_blocks else ""
    return steps, f"Grundlage {minutes} min Z2{suffix}"


def bike_race_power(blocks: int, minutes: int) -> tuple[list, str]:
    """Muskuläre Ausdauer bei absoluter Rennleistung – das Kernziel der Kampagne."""
    lo, hi = RACE_POWER
    o = Order()
    steps = [step(o, "warmup", seconds=15 * 60, target="power", v1=watts(0.55), v2=watts(0.70))]
    block = [
        step(o, "interval", seconds=minutes * 60, target="power", v1=lo, v2=hi,
             note=f"RENNLEISTUNG {lo}-{hi} W – durchgehend Aeroposition, TF 85-90, Verpflegung testen"),
        step(o, "recovery", seconds=6 * 60, target="power", v1=watts(0.48), v2=watts(0.60)),
    ]
    steps.append(create_repeat_group(blocks, block, o.next()))
    steps.append(step(o, "cooldown", seconds=10 * 60, target="power", v1=watts(0.40), v2=watts(0.55)))
    return steps, (f"Rennleistung {blocks}x{minutes} min @ {lo}-{hi} W "
                   f"(= {lo / FTP:.0%}-{hi / FTP:.0%} der aktuellen FTP), Aeroposition")


def bike_muscular_endurance(reps: int, minutes: int) -> tuple[list, str]:
    """Grosser Gang, niedrige Trittfrequenz – Kraftausdauer für konstante Wattleistung."""
    lo, hi = RACE_POWER
    o = Order()
    steps = [step(o, "warmup", seconds=15 * 60, target="power", v1=watts(0.55), v2=watts(0.70))]
    block = [
        step(o, "interval", seconds=minutes * 60, target="power", v1=lo, v2=hi + 10,
             note=f"{lo}-{hi + 10} W bei TF 60-70 – grosser Gang, sitzend, ruhiger Oberkoerper"),
        step(o, "recovery", seconds=5 * 60, target="power", v1=watts(0.45), v2=watts(0.58)),
    ]
    steps.append(create_repeat_group(reps, block, o.next()))
    steps.append(step(o, "cooldown", seconds=10 * 60, target="power", v1=watts(0.40), v2=watts(0.55)))
    return steps, f"Kraftausdauer {reps}x{minutes} min @ {lo}-{hi + 10} W, TF 60-70"


def bike_long_race(minutes: int, rp_minutes: int) -> tuple[list, str]:
    lo, hi = RACE_POWER
    o = Order()
    steps = [
        step(o, "warmup", seconds=15 * 60, target="power", v1=watts(0.50), v2=watts(0.66)),
        step(o, "interval", seconds=max(minutes - rp_minutes - 30, 20) * 60, target="power",
             v1=watts(0.58), v2=watts(0.72), note="Zone 2, Aeroposition üben, Verpflegung 60-80 g KH/h"),
        step(o, "interval", seconds=rp_minutes * 60, target="power", v1=lo, v2=hi,
             note=f"RENNLEISTUNG {lo}-{hi} W – Simulation inkl. Trinken/Essen, Aeroposition halten"),
        step(o, "cooldown", seconds=15 * 60, target="power", v1=watts(0.40), v2=watts(0.55)),
    ]
    return steps, f"Lange Ausfahrt {minutes} min inkl. {rp_minutes} min Rennleistung @ {lo}-{hi} W"


def bike_race_sim() -> tuple[list, str]:
    """Generalprobe: 90 km durchgehend auf Rennleistung."""
    lo, hi = RACE_POWER
    o = Order()
    steps = [
        step(o, "warmup", seconds=12 * 60, target="power", v1=watts(0.50), v2=watts(0.66)),
        step(o, "interval", seconds=150 * 60, target="power", v1=lo, v2=hi,
             note=f"GENERALPROBE 90 km @ {lo}-{hi} W – Renn-Setup, Renn-Verpflegung, "
                  f"Aeroposition. Danach direkt 30 min gehen."),
        step(o, "cooldown", seconds=10 * 60, target="power", v1=watts(0.40), v2=watts(0.55)),
    ]
    return steps, f"Generalprobe 90 km @ {lo}-{hi} W + Brick-Gehen"


def bike_opener() -> tuple[list, str]:
    o = Order()
    steps = [
        step(o, "warmup", seconds=12 * 60, target="power", v1=watts(0.50), v2=watts(0.65)),
    ]
    block = [
        step(o, "interval", seconds=180, target="power", v1=watts(0.88), v2=watts(0.95), note="Öffner, locker kräftig"),
        step(o, "recovery", seconds=180, target="power", v1=watts(0.45), v2=watts(0.58)),
    ]
    steps.append(create_repeat_group(3, block, o.next()))
    steps.append(step(o, "cooldown", seconds=8 * 60, target="power", v1=watts(0.40), v2=watts(0.52)))
    return steps, "Öffner 3x3 min @ 88-95% FTP – Beine wecken, nicht ermüden"


# ---------------------------------- Schwimmen -------------------------------

def swim_technique() -> tuple[list, str]:
    o = Order()
    steps = [
        step(o, "warmup", meters=400, note="Locker einschwimmen, ruhig ausatmen"),
    ]
    drill = [
        step(o, "interval", meters=50, note="Drill: Catch-up / Fingertip-Drag / Faust / 6-Kick-Switch / Einarm"),
        step(o, "recovery", seconds=20),
    ]
    steps.append(create_repeat_group(8, drill, o.next()))
    focus = [
        step(o, "interval", meters=100, target="pace",
             v1=pace_ms(CSS + 8), v2=pace_ms(CSS + 2), note="EIN Fokus-Cue aus den Drills umsetzen"),
        step(o, "recovery", seconds=20),
    ]
    steps.append(create_repeat_group(6, focus, o.next()))
    steps.append(step(o, "cooldown", meters=200, note="Locker ausschwimmen"))
    return steps, "Technik: 400 ES · 8x50 Drills · 6x100 Fokus · 200 AS (~1.800 m)"


def swim_css(reps: int, dist: int, rest: int, offset: int = 0) -> tuple[list, str]:
    target = CSS + offset
    o = Order()
    steps = [
        step(o, "warmup", meters=300, note="Einschwimmen locker"),
    ]
    build = [step(o, "interval", meters=50, note="Steigerung"), step(o, "recovery", seconds=20)]
    steps.append(create_repeat_group(4, build, o.next()))
    main = [
        step(o, "interval", meters=dist, target="pace",
             v1=pace_ms(target + 3), v2=pace_ms(target - 3),
             note=f"CSS-Tempo {fmt_pace(target)}/100 m – metronomisch, erste Wdh. nicht sprinten"),
        step(o, "recovery", seconds=rest),
    ]
    steps.append(create_repeat_group(reps, main, o.next()))
    steps.append(step(o, "cooldown", meters=200))
    return steps, f"CSS-Set {reps}x{dist} m @ {fmt_pace(target)}/100 m, {rest} s Pause"


def swim_endurance(dist: int, race_pace_blocks: int = 0) -> tuple[list, str]:
    o = Order()
    steps = [step(o, "warmup", meters=200, note="Locker anschwimmen")]
    if race_pace_blocks:
        block = [
            step(o, "interval", seconds=240, target="pace",
                 v1=pace_ms(CSS + 8), v2=pace_ms(CSS + 2), note="Renntempo-Block"),
            step(o, "recovery", seconds=45),
        ]
        steps.append(create_repeat_group(race_pace_blocks, block, o.next()))
    steps.append(step(o, "interval", meters=dist, target="pace",
                      v1=pace_ms(CSS + 15), v2=pace_ms(CSS + 5),
                      note="Durchgehend, entspannt, Züge pro Bahn stabil halten"))
    steps.append(step(o, "cooldown", meters=200))
    return steps, f"Ausdauer: {dist} m am Stück, ruhiges Tempo"


def swim_race_sim() -> tuple[list, str]:
    o = Order()
    steps = [
        step(o, "warmup", meters=400, note="Einschwimmen + 4x50 Steigerung"),
        step(o, "interval", meters=1900, target="pace",
             v1=pace_ms(CSS + 8), v2=pace_ms(CSS), note="RENNSIMULATION 1.900 m – Pacing wie am Renntag"),
        step(o, "cooldown", meters=200),
    ]
    return steps, "Rennsimulation 1.900 m am Stück"


# ------------------------------------ Gehen ---------------------------------

def walk_endurance(minutes: int, note: str = "") -> tuple[list, str]:
    lo, hi = hr_band(0.62, 0.75)
    o = Order()
    steps = [
        step(o, "warmup", seconds=10 * 60, target="hr", v1=hr_band(0.50, 0.62)[0], v2=hr_band(0.50, 0.62)[1],
             note="Locker anlaufen, Knie beobachten"),
        step(o, "interval", seconds=minutes * 60, target="hr", v1=lo, v2=hi,
             note=note or "Zügiges Gehen, HF 62-75% max. Bei Knieschmerz > 3/10 abbrechen."),
        step(o, "cooldown", seconds=8 * 60, target="hr", v1=hr_band(0.45, 0.58)[0], v2=hr_band(0.45, 0.58)[1]),
    ]
    return steps, f"Gehen {minutes + 18} min gesamt, HF {lo}-{hi}"


def walk_brick(minutes: int) -> tuple[list, str]:
    lo, hi = hr_band(0.65, 0.78)
    o = Order()
    steps = [
        step(o, "interval", seconds=minutes * 60, target="hr", v1=lo, v2=hi,
             note="BRICK direkt nach dem Rad – zügig gehen, Kadenz hoch, Knie kontrollieren"),
        step(o, "cooldown", seconds=5 * 60, target="hr", v1=hr_band(0.45, 0.58)[0], v2=hr_band(0.45, 0.58)[1]),
    ]
    return steps, f"Brick-Gehen {minutes} min direkt nach der langen Ausfahrt"


# ------------------------------------- Gym ----------------------------------

GYM_A = [
    # (Kategorie, Übungs-Key, Sätze, Wdh., Pause)
    ("SQUAT", "LEG_PRESS", 3, 15, 90),
    ("LEG_CURL", "SEATED_LEG_CURL", 3, 12, 75),
    ("HIP_RAISE", "BARBELL_HIP_THRUST_ON_FLOOR", 3, 12, 75),
    ("LUNGE", "WEIGHTED_STEP_UP", 3, 10, 75),
    ("CALF_RAISE", "STANDING_CALF_RAISE", 3, 15, 60),
    ("HIP_STABILITY", "LATERAL_WALKS_WITH_BAND_AT_ANKLES", 2, 15, 45),
]

GYM_B = [
    ("PULL_UP", "LAT_PULLDOWN", 3, 12, 75),
    ("ROW", "SEATED_CABLE_ROW", 3, 12, 75),
    ("BENCH_PRESS", "DUMBBELL_BENCH_PRESS", 3, 10, 75),
    ("SHOULDER_PRESS", "DUMBBELL_SHOULDER_PRESS", 3, 8, 75),
    ("ROW", "FACE_PULL", 3, 15, 45),
    ("DEADLIFT", "ROMANIAN_DEADLIFT", 3, 10, 90),
    ("PLANK", "SIDE_PLANK", 2, 1, 45),
]


def gym(blocks: list[tuple[str, str, int, int, int]], label: str) -> tuple[list, str]:
    steps: list[Any] = []
    order = 1
    for category, exercise, sets, reps, rest in blocks:
        steps.append(create_strength_set(category, order, sets, reps, float(rest), exercise_name=exercise))
        order += 3
    return steps, f"Kraft {label} – Gewichte 2-3 Wdh. in Reserve, nie durch Gelenkschmerz trainieren"


# ----------------------------------------------------------------------------
# 4. Kampagnenlogik: welche Einheit in welcher Woche
# ----------------------------------------------------------------------------

PHASES = [
    (1, 8, "Grundlage"),
    (9, 18, "Build I"),
    (19, 28, "Build II"),
    (29, 35, "Rennspezifisch"),
    (36, 38, "Taper"),
]

RECOVERY_WEEKS = {4, 8, 12, 16, 20, 24, 28, 32}


def phase_of(week: int) -> str:
    for lo, hi, name in PHASES:
        if lo <= week <= hi:
            return name
    return "Taper"


RACE_SIM_WEEK = 33          # Generalprobe: 90 km durchgehend auf Rennleistung
MULTI_SIM_WEEK = 35         # Rennsimulation aller drei Disziplinen (laut Plandokument)


def rp_minutes(week: int) -> int:
    """Minuten auf Rennleistung innerhalb der langen Ausfahrt – die Kernprogression.

    Die Zahl, die am Ende ueber 235-250 W ueber 90 km entscheidet:
    von 25 min in Woche 9 auf 100 min in Woche 34.
    """
    if week < 9:
        return 0
    return int(min(25 + (week - 9) * 3, 100))


def is_recovery(week: int) -> bool:
    """Entlastungswochen laut Plandokument."""
    return week in RECOVERY_WEEKS


def fmt_pace(seconds: float) -> str:
    m, s = divmod(int(round(seconds)), 60)
    return f"{m}:{s:02d}"


def build_race_week(week: int) -> list[Session]:
    """Rennwoche: nur Öffner, lockeres Wasserfühlen, Renntag am Samstag."""
    def s(day: int, sport: str, label: str, built: tuple[list, str]) -> Session:
        steps, desc = built
        return Session(name=f"{PREFIX} W{week:02d} {label}", sport=sport,
                       steps=steps, description=desc, day=day)

    return [
        s(DAY_BIKE_Q, "cycling", "Rad Öffner", bike_opener()),
        s(DAY_SWIM_1, "swimming", "Schwimmen locker", swim_endurance(800)),
        s(DAY_BIKE_2, "cycling", "Rad Anrisse", bike_opener()),
        s(DAY_SWIM_2, "swimming", "Wasserfühlen kurz", swim_endurance(600)),
        s(DAY_WALK, "walking", "Ausgehen locker", walk_endurance(20)),
    ]


def r5(x: float) -> int:
    """Auf 5 Minuten runden – sonst entstehen Vorgaben wie \"2x21 min\"."""
    return max(5, int(round(x / 5.0)) * 5)


def build_week(week: int) -> list[Session]:
    """Liefert alle Einheiten einer Kampagnenwoche."""
    if week == TOTAL_WEEKS:
        return build_race_week(week)
    p = phase_of(week)
    rec = is_recovery(week)
    r = 0.6 if rec else 1.0          # Umfangsfaktor in Entlastungswochen
    sessions: list[Session] = []

    def add(day: int, sport: str, label: str, built: tuple[list, str], extra: dict | None = None) -> None:
        steps, desc = built
        sessions.append(Session(
            name=f"{PREFIX} W{week:02d} {label}",
            sport=sport, steps=steps, description=desc, day=day, extra=extra or {},
        ))

    # ---------------- Rad: Qualität 1 (Dienstag) ----------------
    if p == "Grundlage":
        reps = 2 if week < 5 else 3
        add(DAY_BIKE_Q, "cycling", "Rad Sweet Spot", bike_sweetspot(reps, int(15 * r) + (5 if week >= 4 and not rec else 0)))
    elif p == "Build I":
        if week % 2:
            add(DAY_BIKE_Q, "cycling", "Rad Schwelle", bike_threshold(3 if week < 14 else 2, 12 if week < 14 else 20))
        else:
            add(DAY_BIKE_Q, "cycling", "Rad Over-Unders", bike_over_under(3, 3))
    elif p == "Build II":
        if week % 2:
            add(DAY_BIKE_Q, "cycling", "Rad VO2max 5x3", bike_vo2(5, 3, 1.14, 1.20))
        else:
            add(DAY_BIKE_Q, "cycling", "Rad VO2max 4x4", bike_vo2(4, 4, 1.08, 1.14))
    elif p == "Rennspezifisch":
        add(DAY_BIKE_Q, "cycling", "Rad Schwelle 2x20", bike_threshold(2, 20, 0.95, 1.00))
    else:  # Taper
        add(DAY_BIKE_Q, "cycling", "Rad Öffner", bike_opener())

    # ---------------- Rad: Qualität 2 (Donnerstag) ----------------
    if p == "Grundlage":
        add(DAY_BIKE_2, "cycling", "Rad Sweet Spot 2", bike_sweetspot(2, r5(15 * r), 0.88, 0.92))
    elif p == "Build I":
        if week % 2:
            add(DAY_BIKE_2, "cycling", "Rad Kraftausdauer", bike_muscular_endurance(3, r5(10 * r)))
        else:
            add(DAY_BIKE_2, "cycling", "Rad Rennleistung", bike_race_power(2, r5(20 * r)))
    elif p == "Build II":
        add(DAY_BIKE_2, "cycling", "Rad Rennleistung", bike_race_power(2, r5(25 * r)))
    elif p == "Rennspezifisch":
        add(DAY_BIKE_2, "cycling", "Rad Rennleistung", bike_race_power(2, r5(35 * r)))
    else:
        add(DAY_BIKE_2, "cycling", "Rad locker", bike_endurance(45))

    # ---------------- Rad: lange Ausfahrt (Samstag) ----------------
    long_minutes = {
        "Grundlage": 120 + (week // 3) * 10,
        "Build I": 150 + (week - 9) * 5,
        "Build II": 195,                      # Phase 3/4: Radumfang auf ~6 h/Woche – Bedingung für 300 W
        "Rennspezifisch": 210,
        "Taper": 90,
    }[p]
    long_minutes = int(long_minutes * r)
    if week == RACE_SIM_WEEK:
        add(DAY_LONG_BIKE, "cycling", "Generalprobe 90 km", bike_race_sim())
    elif p == "Rennspezifisch":
        add(DAY_LONG_BIKE, "cycling", "Lange Ausfahrt Rennleistung",
            bike_long_race(long_minutes, r5(rp_minutes(week) * r)))
    elif p == "Build II":
        add(DAY_LONG_BIKE, "cycling", "Lange Ausfahrt Rennleistung",
            bike_long_race(long_minutes, r5(rp_minutes(week) * r)))
    elif p == "Build I":
        add(DAY_LONG_BIKE, "cycling", "Lange Ausfahrt Rennleistung",
            bike_long_race(long_minutes, r5(rp_minutes(week) * r)))
    else:
        add(DAY_LONG_BIKE, "cycling", "Lange Ausfahrt",
            bike_endurance(long_minutes, ss_blocks=1 if week >= 6 else 0, ss_minutes=20))

    # ---------------- Schwimmen (Mittwoch / Freitag) ----------------
    if p in ("Grundlage", "Build II"):
        add(DAY_SWIM_1, "swimming", "Schwimmen Technik", swim_technique(), {"pool": True})
    elif p == "Rennspezifisch" and week >= 31:
        add(DAY_SWIM_1, "swimming", "Schwimmen Rennsimulation", swim_race_sim(), {"pool": True})
    else:
        add(DAY_SWIM_1, "swimming", "Schwimmen Ausdauer",
            swim_endurance(1200 if p == "Build I" else 1900, race_pace_blocks=0 if p == "Build I" else 3),
            {"pool": True})

    if p == "Grundlage":
        css_set = swim_css(10, 100, 20, offset=4)
    elif p == "Build I":
        css_set = swim_css(12, 100, 15, offset=0)
    elif p == "Build II":
        css_set = swim_css(6, 200, 25, offset=0)
    elif p == "Rennspezifisch":
        css_set = swim_css(4, 400, 45, offset=2)
    else:
        css_set = swim_css(6, 100, 25, offset=2)
    add(DAY_SWIM_2, "swimming", "Schwimmen CSS", css_set, {"pool": True})

    # ---------------- Gehen (Sonntag, ggf. Brick am Samstag) ----------------
    walk_minutes = {
        "Grundlage": 50 + week * 4,
        "Build I": 80 + (week - 9) * 4,
        "Build II": 120 + (week - 19) * 4,
        "Rennspezifisch": 170,
        "Taper": 60,
    }[p]
    walk_minutes = int(min(walk_minutes, 180) * r)
    add(DAY_WALK, "walking", "Gehen lang", walk_endurance(walk_minutes))
    if week >= 29 and not rec:
        add(DAY_LONG_BIKE, "walking", "Brick Gehen", walk_brick(25))

    # ---------------- Zusatzvolumen Phase 3/4 (Montag) ----------------
    if p in ("Build II", "Rennspezifisch") and not rec:
        add(DAY_REST, "cycling", "Rad Zusatz Z2", bike_endurance(60))

    # ---------------- Kraft ----------------
    add(DAY_BIKE_Q, "strength", "Kraft A Unterkörper", gym(GYM_A, "A – Unterkörper & Kniestabilität"))
    add(DAY_WALK, "strength", "Kraft B Ganzkörper", gym(GYM_B, "B – Ganzkörper, Rumpf & Schwimmstütze"))

    return sessions


def week_monday(week: int) -> date:
    race_monday = RACE_DATE - timedelta(days=RACE_DATE.weekday())
    first_monday = race_monday - timedelta(weeks=TOTAL_WEEKS - 1)
    return first_monday + timedelta(weeks=week - 1)


# ----------------------------------------------------------------------------
# 5. Aufbau der Garmin-Objekte
# ----------------------------------------------------------------------------

def to_workout(s: Session):
    renumber(s.steps)
    seg = WorkoutSegment(segmentOrder=1, sportType=SPORT[s.sport], workoutSteps=s.steps)
    common = dict(
        workoutName=s.name[:80],
        estimatedDurationInSecs=duration_of(s.steps),
        workoutSegments=[seg],
        description=s.description[:1000],
    )
    if s.sport == "cycling":
        return CyclingWorkout(**common), "upload_cycling_workout"
    if s.sport == "swimming":
        return SwimmingWorkout(
            poolLength=float(POOL_LENGTH_M),
            poolLengthUnit=POOL_UNIT,
            **common,
        ), "upload_swimming_workout"
    if s.sport == "walking":
        return WalkingWorkout(**common), "upload_walking_workout"
    if s.sport == "strength":
        return StrengthWorkout(**common), "upload_strength_workout"
    raise ValueError(s.sport)


# ----------------------------------------------------------------------------
# 6. Garmin-Login (Token-Cache wie im Aquabike-Tracker)
# ----------------------------------------------------------------------------

def garmin_login() -> Garmin:
    tokenstore = os.getenv("GARMINTOKENS", "~/.garminconnect")
    email = os.getenv("GARMIN_EMAIL")
    password = os.getenv("GARMIN_PASSWORD")
    client = Garmin(email, password, prompt_mfa=lambda: input("MFA-Code: "))
    try:
        client.login(tokenstore)
        print(f"[auth] Session aus Token-Cache ({tokenstore}) wiederhergestellt")
    except Exception as exc:  # noqa: BLE001
        print(f"[auth] Token-Login fehlgeschlagen ({exc}); Passwort-Login …")
        if not email or not password:
            sys.exit("GARMIN_EMAIL / GARMIN_PASSWORD nicht gesetzt.")
        client.login()
        client.garth.dump(os.path.expanduser(tokenstore))
        print(f"[auth] Neue Tokens gespeichert unter {tokenstore}")
    return client


def load_targets() -> None:
    """Zielwerte aus targets.json übernehmen (gemeinsame Quelle mit dem Dashboard)."""
    global RACE_POWER, FTP_TARGET, MAX_RACE_IF, RACE_DATE, TOTAL_WEEKS, POOL_LENGTH_M
    if not TARGETS_JSON.exists():
        return
    try:
        cfg = json.loads(TARGETS_JSON.read_text())
    except Exception as exc:  # noqa: BLE001
        print(f"[cfg] targets.json nicht lesbar ({exc}) – Standardwerte aktiv")
        return
    bike = cfg.get("bike", {})
    if isinstance(bike.get("race_power_w"), list) and len(bike["race_power_w"]) == 2:
        RACE_POWER = (int(bike["race_power_w"][0]), int(bike["race_power_w"][1]))
    FTP_TARGET = int(bike.get("ftp_target_w", FTP_TARGET))
    MAX_RACE_IF = float(bike.get("max_race_if", MAX_RACE_IF))
    camp = cfg.get("campaign", {})
    if camp.get("race_date"):
        RACE_DATE = date.fromisoformat(camp["race_date"])
    TOTAL_WEEKS = int(camp.get("total_weeks", TOTAL_WEEKS))
    print(f"[cfg] Zielwerte aus {TARGETS_JSON} geladen (v{cfg.get('version', '?')})")


def load_ftp_css() -> None:
    """FTP/CSS aus manual.json des Trackers übernehmen, falls vorhanden."""
    global FTP, CSS
    data = None
    if MANUAL_JSON.exists():
        try:
            data = json.loads(MANUAL_JSON.read_text())
        except Exception:  # noqa: BLE001
            data = None
    if isinstance(data, dict):
        ftp = data.get("ftp") or (data.get("tests") or {}).get("ftp")
        css = data.get("css_sec_per_100m") or (data.get("tests") or {}).get("css")
        if isinstance(ftp, (int, float)) and ftp > 100:
            FTP = int(ftp)
        if isinstance(css, (int, float)) and 60 < css < 240:
            CSS = int(css)
    lo, hi = RACE_POWER
    print(f"[cfg] FTP={FTP} W (Ziel {FTP_TARGET} W) · Rennleistung {lo}-{hi} W · CSS={fmt_pace(CSS)}/100 m")
    print(f"[cfg] Rennleistung entspricht IF {lo / FTP:.2f}-{hi / FTP:.2f} der aktuellen FTP")
    if hi / FTP > MAX_RACE_IF:
        need = int(round(hi / 0.82))
        print(f"[WARNUNG] {hi} W liegen bei {hi / FTP:.0%} der aktuellen FTP – ueber 90 km nicht haltbar.")
        print(f"          Fuer IF 0.82 braucht es eine FTP von ~{need} W. "
              f"Bis dahin sind die Rennleistungs-Blocks Zielarbeit, keine Wiederholungsvorgabe:")
        print(f"          erst die Dauer aufbauen, dann das Wattband nach oben ziehen.")


# ----------------------------------------------------------------------------
# 7. Hauptprogramm
# ----------------------------------------------------------------------------

def parse_weeks(spec: str) -> list[int]:
    out: list[int] = []
    for part in spec.split(","):
        if "-" in part:
            a, b = part.split("-")
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return [w for w in out if 1 <= w <= TOTAL_WEEKS]


def main() -> None:
    ap = argparse.ArgumentParser(description="70.3-Trainingsplan als Garmin-Workouts")
    ap.add_argument("--weeks", default="1-4", help="z. B. 1-4, 5, 9-12 (Standard: 1-4)")
    ap.add_argument("--dry-run", action="store_true", help="nur JSON schreiben, nichts hochladen")
    ap.add_argument("--no-schedule", action="store_true", help="hochladen, aber nicht in den Kalender legen")
    ap.add_argument("--push", action="store_true", help="Workouts zusätzlich direkt an die Uhr senden")
    ap.add_argument("--clean", action="store_true", help=f"alle Workouts mit Präfix '{PREFIX}' löschen und beenden")
    args = ap.parse_args()

    load_targets()
    load_ftp_css()
    weeks = parse_weeks(args.weeks)

    if args.dry_run:
        OUT_DIR.mkdir(exist_ok=True)
        total = 0
        for w in weeks:
            monday = week_monday(w)
            print(f"\n=== Woche {w:02d} ({phase_of(w)}{', Entlastung' if is_recovery(w) else ''}) "
                  f"ab {monday.isoformat()} ===")
            for s in build_week(w):
                workout, _ = to_workout(s)
                day = monday + timedelta(days=s.day)
                print(f"  {day.strftime('%a %d.%m.')}  {s.sport:9s} {s.name:34s} "
                      f"{duration_of(s.steps)//60:3d} min  – {s.description}")
                (OUT_DIR / f"{s.name.replace(' ', '_').replace('/', '-')}.json").write_text(
                    json.dumps(workout.to_dict(), indent=2, ensure_ascii=False))
                total += 1
        print(f"\n{total} Workouts als JSON in {OUT_DIR}/ geschrieben (nichts hochgeladen).")
        return

    client = garmin_login()

    if args.clean:
        existing = client.get_workouts(0, 500)
        removed = 0
        for w in existing:
            if str(w.get("workoutName", "")).startswith(PREFIX):
                client.delete_workout(w["workoutId"])
                removed += 1
        print(f"{removed} Workouts mit Präfix '{PREFIX}' gelöscht.")
        return

    state: dict[str, Any] = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
    existing = {str(w.get("workoutName")): w["workoutId"] for w in client.get_workouts(0, 500)}
    device_id = None
    if args.push:
        devices = client.get_devices()
        if devices:
            device_id = devices[0]["deviceId"]
            print(f"[push] Zielgerät: {devices[0].get('productDisplayName', device_id)}")

    for w in weeks:
        monday = week_monday(w)
        print(f"\n=== Woche {w:02d} ({phase_of(w)}) ab {monday.isoformat()} ===")
        for s in build_week(w):
            workout, method = to_workout(s)
            if s.name in existing:
                client.delete_workout(existing[s.name])
            result = getattr(client, method)(workout)
            wid = result.get("workoutId")
            day = monday + timedelta(days=s.day)
            line = f"  {day.strftime('%a %d.%m.')}  {s.name:34s} -> id {wid}"
            if not args.no_schedule:
                client.schedule_workout(wid, day.isoformat())
                line += "  [Kalender]"
            if device_id:
                client.push_workout_to_device(wid, device_id)
                line += "  [Uhr]"
            print(line)
            state[s.name] = {"id": wid, "date": day.isoformat(), "sport": s.sport}

    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False))
    print(f"\nFertig. Zustand in {STATE_FILE} gespeichert.")


if __name__ == "__main__":
    main()
