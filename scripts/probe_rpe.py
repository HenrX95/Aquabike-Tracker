#!/usr/bin/env python3
"""
Diagnose: findet heraus, unter welchem Feldnamen Garmin die Selbstbeurteilung
(Perceived Effort / Feel) im Aktivitaets-Detail ablegt.

Einmal laufen lassen, nachdem du auf der Uhr mindestens eine Aktivitaet
mit Selbstbeurteilung gespeichert hast. Das Skript aendert nichts —
es liest nur und gibt aus, was es findet.

Aufruf ueber GitHub Actions: Tab Actions → "RPE Probe" → Run workflow
"""

import json
import os
import sys
from datetime import date, timedelta

from garminconnect import Garmin

# Feldnamen, die Garmin fuer die Selbstbeurteilung verwendet haben koennte.
# Der erste Treffer gewinnt. Reihenfolge = Wahrscheinlichkeit.
EFFORT_KEYS = [
    "directWorkoutRpe",       # Garmin intern, 0-100 skaliert (10 = RPE 1)
    "workoutRpe",
    "perceivedEffort",
    "rpe",
    "directPerceivedEffort",
]
FEEL_KEYS = [
    "directWorkoutFeel",      # 0-100, 5 Stufen
    "workoutFeel",
    "feel",
    "perceivedFeel",
]


def dig(obj, path=""):
    """Rekursiv alle Schluessel durchlaufen und Effort/Feel-Verdaechtige melden."""
    hits = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}" if path else k
            if any(w in k.lower() for w in ("rpe", "effort", "feel")):
                hits.append((p, v))
            hits += dig(v, p)
    elif isinstance(obj, list) and obj:
        hits += dig(obj[0], f"{path}[0]")
    return hits


def main():
    api = Garmin(os.environ["GARMIN_EMAIL"], os.environ["GARMIN_PASSWORD"])
    api.login()

    end = date.today()
    start = end - timedelta(days=21)
    acts = api.get_activities_by_date(start.isoformat(), end.isoformat())

    if not acts:
        print("Keine Aktivitaeten in den letzten 21 Tagen gefunden.")
        return

    print(f"{len(acts)} Aktivitaeten gefunden. Pruefe die letzten 5.\n")

    for a in acts[:5]:
        aid = a.get("activityId")
        name = a.get("activityName")
        day = (a.get("startTimeLocal") or "")[:10]
        print("=" * 70)
        print(f"{day}  {name}  (id {aid})")

        # 1. Steht schon etwas in der Listen-Antwort?
        list_hits = dig(a)
        if list_hits:
            print("  In der Aktivitaetsliste:")
            for p, v in list_hits:
                print(f"    {p} = {v!r}")

        # 2. Detail-Objekt holen
        try:
            detail = api.get_activity(str(aid))
        except Exception as e:
            print(f"  Detail-Abruf fehlgeschlagen: {e}")
            continue

        det_hits = dig(detail)
        if det_hits:
            print("  Im Detail-Objekt:")
            for p, v in det_hits:
                print(f"    {p} = {v!r}")
        else:
            print("  Im Detail-Objekt: nichts gefunden.")
            print("  → Selbstbeurteilung fuer diese Aktivitaet nicht gesetzt,")
            print("    oder Garmin nutzt einen unerwarteten Feldnamen.")

        # 3. Bekannte Kandidaten gezielt pruefen
        found = {k: detail.get(k) for k in EFFORT_KEYS + FEEL_KEYS if k in detail}
        if found:
            print(f"  Bekannte Kandidaten: {found}")

    print("\n" + "=" * 70)
    print("Schick mir die Ausgabe oben. Danach fixiere ich den Feldnamen in sync.py.")
    print("Falls ueberall 'nichts gefunden' steht: auf der Uhr unter")
    print("Aktivitaeten & Apps → <Sportart> → Selbstbeurteilung → Immer aktivieren,")
    print("eine Einheit aufzeichnen, bewerten, syncen, dann erneut laufen lassen.")


if __name__ == "__main__":
    main()
