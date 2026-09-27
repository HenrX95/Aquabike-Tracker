#!/usr/bin/env python3
"""
export_files.py – exportiert den Trainingsplan (dieselbe Logik wie garmin_workouts.py) als
  • Zwift-Workouts (.zwo)       → Documents/Zwift/Workouts/<ZwiftID>/
  • Garmin-Workout-Dateien (.fit) → per USB in GARMIN/NewFiles auf der Uhr

Radziele werden in % FTP geschrieben. Zwift nutzt seine FTP, die Uhr die FTP aus dem
Garmin-Profil → nach einem Rampentest muss nichts neu erzeugt werden, nur die FTP in
Zwift und Garmin Connect aktualisiert sein.

Nutzung:  python3 scripts/export_files.py --weeks 9-38 --out export/
Abhängigkeiten: garminconnect[workout], fit-tool
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import garmin_workouts as G  # noqa: E402
from garminconnect.workout import RepeatGroup  # noqa: E402

DAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


# ------------------------------------------------------------------ Zwischenformat

def to_nodes(steps):
    """garminconnect-Schritte → einfache Knoten (step/repeat)."""
    out = []
    for s in steps:
        if isinstance(s, RepeatGroup):
            out.append({"t": "repeat", "n": int(s.numberOfIterations), "children": to_nodes(s.workoutSteps)})
            continue
        cond = (s.endCondition or {}).get("conditionTypeKey")
        tgt = (s.targetType or {}).get("workoutTargetTypeKey")
        out.append({
            "t": "step",
            "kind": (s.stepType or {}).get("stepTypeKey", "interval"),
            "cond": {"time": "time", "distance": "distance"}.get(cond, "open"),
            "value": float(s.endConditionValue or 0),
            "target": {"power.zone": "power", "pace.zone": "pace"}.get(tgt, "none"),
            "lo": getattr(s, "targetValueOne", None),
            "hi": getattr(s, "targetValueTwo", None),
            "note": pctify(getattr(s, "description", None) or "", G.FTP),
        })
    return out


def short(s: str, n: int) -> str:
    s = s.replace("70.3 ", "")
    return s if len(s) <= n else s[:n]


def ascii_name(s: str) -> str:
    rep = {"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue", "ß": "ss", "+": "plus"}
    for a, b in rep.items():
        s = s.replace(a, b)
    return re.sub(r"[^A-Za-z0-9 ]+", " ", s).strip()


def pctify(text: str, ftp: int) -> str:
    """Wattangaben in Notizen → % FTP (Zwift und Uhr rechnen mit ihrer eigenen FTP)."""
    text = re.sub(r"(\d{2,3})-(\d{2,3}) W", lambda m: f"{round(int(m.group(1)) / ftp * 100)}-{round(int(m.group(2)) / ftp * 100)} % FTP", text)
    text = re.sub(r"(\d{2,3}) W\b", lambda m: f"{round(int(m.group(1)) / ftp * 100)} % FTP", text)
    return text


def fmt_pace(ms: float) -> str:
    sec = 100.0 / ms
    return f"{int(sec // 60)}:{int(round(sec % 60)):02d}"


# ------------------------------------------------------------------ Zwift (.zwo)

def cadence_from(note: str):
    m = re.search(r"TF (\d+)-(\d+)", note)
    if m:
        return int((int(m.group(1)) + int(m.group(2))) / 2)
    m = re.search(r"(\d{2,3})\+ rpm|Kadenz (\d{2,3})\+|Trittfrequenz (\d{2,3})\+", note)
    if m:
        return int(next(g for g in m.groups() if g))
    return None


def zwo_elems(nodes, ftp):
    out = []
    for n in nodes:
        if n["t"] == "repeat":
            ch = n["children"]
            if (len(ch) == 2 and all(c["t"] == "step" and c["cond"] == "time" and c["target"] == "power" for c in ch)):
                on, off = ch
                pw = lambda c: round((c["lo"] + c["hi"]) / 2 / ftp, 2)
                cad = cadence_from(on["note"])
                attrs = (f'Repeat="{n["n"]}" OnDuration="{int(on["value"])}" OffDuration="{int(off["value"])}" '
                         f'OnPower="{pw(on)}" OffPower="{pw(off)}"' + (f' Cadence="{cad}"' if cad else ""))
                ev = f'<textevent timeoffset="5" message="{html.escape(on["note"], quote=True)}"/>' if on["note"] else ""
                out.append(f"<IntervalsT {attrs}>{ev}</IntervalsT>")
            else:
                for _ in range(n["n"]):
                    out.extend(zwo_elems(ch, ftp))
            continue
        if n["cond"] != "time":
            out.append(f'<FreeRide Duration="600" FlatRoad="1"/>')
            continue
        d = int(n["value"])
        ev = f'<textevent timeoffset="5" message="{html.escape(n["note"], quote=True)}"/>' if n["note"] else ""
        if n["target"] != "power":
            out.append(f'<FreeRide Duration="{d}" FlatRoad="1">{ev}</FreeRide>')
            continue
        lo, hi = round(n["lo"] / ftp, 2), round(n["hi"] / ftp, 2)
        if n["kind"] == "warmup":
            out.append(f'<Warmup Duration="{d}" PowerLow="{lo:.2f}" PowerHigh="{hi:.2f}">{ev}</Warmup>')
        elif n["kind"] == "cooldown":
            out.append(f'<Cooldown Duration="{d}" PowerLow="{hi:.2f}" PowerHigh="{lo:.2f}">{ev}</Cooldown>')
        else:
            cad = cadence_from(n["note"])
            c = f' Cadence="{cad}"' if cad else ""
            out.append(f'<SteadyState Duration="{d}" Power="{(lo + hi) / 2:.3f}"{c}>{ev}</SteadyState>')
    return out


def write_zwo(session, week, path: Path, ftp: int):
    name = ascii_name(f"703 W{week:02d} {DAYS[session.day]} {session.name.split(f'W{week:02d} ', 1)[1]}")
    desc = html.escape(pctify(session.description, ftp) + " · Plan v4, Zielwerte in % FTP", quote=False)
    body = "\n    ".join(zwo_elems(to_nodes(session.steps), ftp))
    xml = f"""<workout_file>
  <author>Trainingsplan v4 Henrik</author>
  <name>{name}</name>
  <description>{desc}</description>
  <sportType>bike</sportType>
  <tags>
    <tag name="IRONMAN703"/>
  </tags>
  <workout>
    {body}
  </workout>
</workout_file>
"""
    fn = path / (name.replace(" ", "_") + ".zwo")
    fn.write_text(xml, encoding="utf-8")
    return fn


# ------------------------------------------------------------------ Garmin (.fit)

from fit_tool.fit_file_builder import FitFileBuilder  # noqa: E402
from fit_tool.profile.messages.file_id_message import FileIdMessage  # noqa: E402
from fit_tool.profile.messages.workout_message import WorkoutMessage  # noqa: E402
from fit_tool.profile.messages.workout_step_message import WorkoutStepMessage  # noqa: E402
from fit_tool.profile.profile_type import (  # noqa: E402
    DisplayMeasure, FileType, Intensity, Manufacturer, Sport, SubSport, WorkoutStepDuration, WorkoutStepTarget)

INTENSITY = {"warmup": Intensity.WARMUP, "cooldown": Intensity.COOLDOWN, "interval": Intensity.ACTIVE,
             "recovery": Intensity.RECOVERY, "rest": Intensity.REST}

EX_DE = {
    "LEG_PRESS": "Beinpresse", "SEATED_LEG_CURL": "Beinbeuger sitzend", "BARBELL_HIP_THRUST_ON_FLOOR": "Hip Thrust",
    "WEIGHTED_STEP_UP": "Step-up", "STANDING_CALF_RAISE": "Wadenheben", "LATERAL_WALKS_WITH_BAND_AT_ANKLES": "Seitgehen Band",
    "ROMANIAN_DEADLIFT": "Rum. Kreuzheben", "LAT_PULLDOWN": "Latzug", "SEATED_CABLE_ROW": "Rudern Kabel",
    "DUMBBELL_BENCH_PRESS": "KH-Bankdruecken", "DUMBBELL_SHOULDER_PRESS": "KH-Schulterdruecken", "FACE_PULL": "Face Pull",
    "SIDE_PLANK": "Seitstuetz 45s",
}


def fit_steps(nodes, ftp, sport):
    """Knoten → Liste von WorkoutStepMessage (Wiederholungen als Repeat-Schritt)."""
    msgs = []

    def emit(ns):
        for n in ns:
            if n["t"] == "repeat":
                start = len(msgs)
                emit(n["children"])
                m = WorkoutStepMessage()
                m.message_index = len(msgs)
                m.duration_type = WorkoutStepDuration.REPEAT_UNTIL_STEPS_CMPLT
                m.duration_step = start
                m.target_repeat_steps = n["n"]
                msgs.append(m)
                continue
            m = WorkoutStepMessage()
            m.message_index = len(msgs)
            note = n["note"]
            if n["cond"] == "time":
                m.duration_type = WorkoutStepDuration.TIME
                m.duration_time = n["value"]
            elif n["cond"] == "distance":
                m.duration_type = WorkoutStepDuration.DISTANCE
                m.duration_distance = n["value"]
            else:
                m.duration_type = WorkoutStepDuration.OPEN
            if n["target"] == "power" and n["lo"]:
                m.target_type = WorkoutStepTarget.POWER
                m.target_power_zone = 0
                m.custom_target_power_low = int(round(n["lo"] / ftp * 100))   # 0-1000 = % FTP
                m.custom_target_power_high = int(round(n["hi"] / ftp * 100))
            else:
                m.target_type = WorkoutStepTarget.OPEN
                if n["target"] == "pace" and n["lo"]:
                    note = f"Pace {fmt_pace(n['lo'])}-{fmt_pace(n['hi'])}/100m. {note}"
            kind = n["kind"]
            if sport == "swimming" and kind == "recovery":
                kind = "rest"
            m.intensity = INTENSITY.get(kind, Intensity.ACTIVE)
            label = {"warmup": "Einfahren", "cooldown": "Ausfahren", "recovery": "Erholung", "rest": "Pause"}.get(kind, "Intervall")
            if sport == "swimming":
                label = {"warmup": "Einschwimmen", "cooldown": "Ausschwimmen"}.get(kind, label)
            m.workout_step_name = label
            if note:
                m.notes = note[:100]
            msgs.append(m)

    emit(nodes)
    return msgs


def strength_steps(blocks, max_sets):
    msgs = []
    for _cat, ex, sets, reps, rest in blocks:
        n_sets = min(sets, max_sets) if max_sets else sets
        start = len(msgs)
        m = WorkoutStepMessage(); m.message_index = len(msgs)
        m.duration_type = WorkoutStepDuration.REPS
        m.duration_reps = reps
        m.target_type = WorkoutStepTarget.OPEN
        m.intensity = Intensity.ACTIVE
        m.workout_step_name = EX_DE.get(ex, ex)[:20]
        m.notes = f"{reps} Wdh., 2-3 in Reserve, nie durch Gelenkschmerz"
        msgs.append(m)
        r = WorkoutStepMessage(); r.message_index = len(msgs)
        r.duration_type = WorkoutStepDuration.TIME
        r.duration_time = float(rest)
        r.target_type = WorkoutStepTarget.OPEN
        r.intensity = Intensity.REST
        r.workout_step_name = "Pause"
        msgs.append(r)
        rp = WorkoutStepMessage(); rp.message_index = len(msgs)
        rp.duration_type = WorkoutStepDuration.REPEAT_UNTIL_STEPS_CMPLT
        rp.duration_step = start
        rp.target_repeat_steps = n_sets
        msgs.append(rp)
    return msgs


def write_fit(session, week, path: Path, ftp: int, serial: int):
    wname = short(f"W{week:02d} {DAYS[session.day]} " + session.name.split(f"W{week:02d} ", 1)[1], 30)
    if session.sport == "strength":
        is_a = "Unterkörper" in session.name
        max_sets = 2 if "2 Sätze" in session.description else None
        steps = strength_steps(G.GYM_A if is_a else G.GYM_B, max_sets)
        sport, sub = Sport.TRAINING, SubSport.STRENGTH_TRAINING
    else:
        sport = {"cycling": Sport.CYCLING, "swimming": Sport.SWIMMING}[session.sport]
        sub = SubSport.LAP_SWIMMING if session.sport == "swimming" else SubSport.GENERIC
        steps = fit_steps(to_nodes(session.steps), ftp, session.sport)

    fid = FileIdMessage()
    fid.type = FileType.WORKOUT
    fid.manufacturer = Manufacturer.DEVELOPMENT.value
    fid.product = 0
    fid.serial_number = serial
    fid.time_created = round(dt.datetime.now().timestamp() * 1000)

    wk = WorkoutMessage()
    wk.workout_name = wname
    wk.sport = sport
    wk.sub_sport = sub
    wk.num_valid_steps = len(steps)
    if session.sport == "swimming":
        wk.pool_length = float(G.POOL_LENGTH_M)
        wk.pool_length_unit = DisplayMeasure.METRIC

    b = FitFileBuilder(auto_define=True, min_string_size=50)
    b.add(fid); b.add(wk); b.add_all(steps)
    fn = path / (ascii_name(wname).replace(" ", "_") + ".fit")
    b.build().to_file(str(fn))
    return fn


# ------------------------------------------------------------------ main

def phase_folder(week: int) -> str:
    for lo, hi, name in G.PHASES:
        if lo <= week <= hi:
            return ascii_name(f"703 W{lo:02d} {hi:02d} {name}")
    return "703"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weeks", default="9-38")
    ap.add_argument("--out", default="export")
    a = ap.parse_args()
    G.load_targets(); G.load_ftp_css()
    ftp = G.FTP
    out = Path(a.out)
    zroot, froot = out / "Zwift_Workouts", out / "Garmin_FIT_Workouts"
    n_z = n_f = 0
    serial = 7030001
    for w in G.parse_weeks(a.weeks):
        zdir = zroot / phase_folder(w); zdir.mkdir(parents=True, exist_ok=True)
        fdir = froot / f"Woche_{w:02d}_ab_{G.week_monday(w).strftime('%d.%m.')}"; fdir.mkdir(parents=True, exist_ok=True)
        for s in sorted(G.build_week(w), key=lambda x: x.day):
            if s.sport == "cycling" and "Rampentest" not in s.name:
                write_zwo(s, w, zdir, ftp); n_z += 1
            write_fit(s, w, fdir, ftp, serial); serial += 1; n_f += 1
    print(f"{n_z} Zwift-Workouts in {zroot}/, {n_f} FIT-Workouts in {froot}/")


if __name__ == "__main__":
    main()
