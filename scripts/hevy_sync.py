#!/usr/bin/env python3
"""Pull every Hevy workout and write it to data/hevy/.

Reads the API key from the HEVY_API_KEY environment variable.
Outputs:
  data/hevy/workouts.json  - raw workouts exactly as the API returns them
  data/hevy/sets.csv       - one row per set, ready for charting
Uses only the Python standard library.
"""
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

BASE = "https://api.hevyapp.com/v1"
OUT = Path(__file__).resolve().parent.parent / "data" / "hevy"


def get(path, **params):
    url = f"{BASE}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"api-key": os.environ["HEVY_API_KEY"], "accept": "application/json"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as err:
            if err.code in (429, 500, 502, 503, 504) and attempt < 3:
                time.sleep(2 ** attempt * 2)
                continue
            # Never print the request (it carries the key); status and path are enough.
            sys.exit(f"Hevy API returned {err.code} for {path}")
        except urllib.error.URLError as err:
            if attempt < 3:
                time.sleep(2 ** attempt * 2)
                continue
            sys.exit(f"Could not reach Hevy: {err.reason}")


def get_all(path, key, page_size):
    items, page = [], 1
    while True:
        body = get(path, page=page, pageSize=page_size)
        items.extend(body.get(key, []))
        if page >= int(body.get("page_count", 1)):
            return items
        page += 1


def minutes(start, end):
    try:
        a = datetime.fromisoformat(start.replace("Z", "+00:00"))
        b = datetime.fromisoformat(end.replace("Z", "+00:00"))
        return round((b - a).total_seconds() / 60, 1)
    except (AttributeError, ValueError):
        return ""


def main():
    if not os.environ.get("HEVY_API_KEY"):
        sys.exit("HEVY_API_KEY is not set")

    workouts = get_all("/workouts", "workouts", 10)
    templates = get_all("/exercise_templates", "exercise_templates", 100)
    muscle = {t["id"]: t.get("primary_muscle_group", "") for t in templates}

    workouts.sort(key=lambda w: w.get("start_time", ""))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "workouts.json").write_text(json.dumps(workouts, indent=1, sort_keys=True) + "\n")

    fields = ["date", "workout_id", "workout", "start_time", "end_time", "duration_min", "exercise",
              "exercise_template_id", "muscle_group", "set_index", "set_type", "weight_kg", "reps",
              "rpe", "distance_m", "duration_s"]
    with open(OUT / "sets.csv", "w", newline="") as fh:
        out = csv.DictWriter(fh, fieldnames=fields)
        out.writeheader()
        for w in workouts:
            for ex in w.get("exercises", []):
                for s in ex.get("sets", []):
                    def cell(k):
                        v = s.get(k)
                        return "" if v is None else v
                    out.writerow({
                        "date": (w.get("start_time") or "")[:10],
                        "workout_id": w.get("id", ""),
                        "workout": w.get("title", ""),
                        "start_time": w.get("start_time", ""),
                        "end_time": w.get("end_time", ""),
                        "duration_min": minutes(w.get("start_time"), w.get("end_time")),
                        "exercise": ex.get("title", ""),
                        "exercise_template_id": ex.get("exercise_template_id", ""),
                        "muscle_group": muscle.get(ex.get("exercise_template_id"), ""),
                        "set_index": cell("index"),
                        "set_type": cell("type"),
                        "weight_kg": cell("weight_kg"),
                        "reps": cell("reps"),
                        "rpe": cell("rpe"),
                        "distance_m": cell("distance_meters"),
                        "duration_s": cell("duration_seconds"),
                    })
    print(f"Wrote {len(workouts)} workouts")


if __name__ == "__main__":
    main()
