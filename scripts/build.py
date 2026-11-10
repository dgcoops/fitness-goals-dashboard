#!/usr/bin/env python3
"""Turn the files under data/ into site/data.json, which the dashboard page reads.

Standard library only. Safe to run when a source has no data yet.
"""
import csv
import json
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
PLANNED_GYM_VISITS = 3

# How each goal lift is recognised in Hevy exercise names (lower case).
# A name must contain every word in "has" and none of the words in "not".
LIFTS = {
    "squat": {"label": "Squat", "has": ["squat", "barbell"],
              "not": ["front", "split", "overhead", "hack", "pause", "box", "zercher"]},
    "bench": {"label": "Bench", "has": ["bench press", "barbell"],
              "not": ["incline", "decline", "close", "wide", "smith"]},
    "deadlift": {"label": "Deadlift", "has": ["deadlift", "barbell"],
                 "not": ["romanian", "stiff", "sumo", "single", "deficit", "rack"]},
}


def rows(path):
    if not path.exists():
        return []
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def monday(d):
    return d - timedelta(days=d.weekday())


def mean(xs):
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 1) if xs else None


def lift_of(name):
    n = name.lower()
    for key, rule in LIFTS.items():
        if all(w in n for w in rule["has"]) and not any(w in n for w in rule["not"]):
            return key
    return None


def main():
    today = datetime.now(ZoneInfo("Europe/London")).date()
    this_mon = monday(today)
    last_mon, prev_mon = this_mon - timedelta(days=7), this_mon - timedelta(days=14)

    def in_week(d, start):
        return start <= d < start + timedelta(days=7)

    # ---- body ----
    weigh = []
    for r in rows(DATA / "withings" / "weight.csv") or rows(DATA / "manual" / "weight.csv"):
        kg = num(r.get("weight_kg"))
        if kg is not None:
            weigh.append({"date": date.fromisoformat(r["date"][:10]), "kg": kg, "fat": num(r.get("fat_pct"))})
    weigh.sort(key=lambda r: r["date"])
    series_weight = []
    for r in weigh:
        window = [w for w in weigh if r["date"] - timedelta(days=6) <= w["date"] <= r["date"]]
        series_weight.append({"date": r["date"].isoformat(), "kg": r["kg"], "fat": r["fat"],
                              "avg_kg": mean([w["kg"] for w in window]),
                              "avg_fat": mean([w["fat"] for w in window])})

    def body_tile(field):
        cur = mean([w[field] for w in weigh if in_week(w["date"], last_mon)])
        prev = mean([w[field] for w in weigh if in_week(w["date"], prev_mon)])
        delta = round(cur - prev, 1) if cur is not None and prev is not None else None
        return {"value": cur, "prev": prev, "delta": delta}

    # ---- gym ----
    sets = rows(DATA / "hevy" / "sets.csv")
    workout_days = {}
    for s in sets:
        if s.get("workout_id") and s.get("date"):
            workout_days[s["workout_id"]] = date.fromisoformat(s["date"])
    visits = defaultdict(int)
    for d in workout_days.values():
        visits[monday(d)] += 1

    best = {k: defaultdict(float) for k in LIFTS}      # lift -> day -> heaviest set of 5+
    e1rm = {k: defaultdict(float) for k in LIFTS}      # lift -> day -> estimated one-rep max
    for s in sets:
        key = lift_of(s.get("exercise", ""))
        kg, reps = num(s.get("weight_kg")), num(s.get("reps"))
        if not key or not kg or not reps or s.get("set_type") == "warmup":
            continue
        d = date.fromisoformat(s["date"])
        if reps >= 5:
            best[key][d] = max(best[key][d], kg)
        if reps <= 12:
            e1rm[key][d] = max(e1rm[key][d], round(kg * (1 + reps / 30), 1))

    def week_best(key, start):
        vals = [kg for d, kg in best[key].items() if in_week(d, start)]
        return max(vals) if vals else None

    lift_tiles = []
    for key, rule in LIFTS.items():
        cur, prev = week_best(key, last_mon), week_best(key, prev_mon)
        earlier = [kg for d, kg in best[key].items() if d < last_mon]
        lift_tiles.append({"id": key, "name": rule["label"], "value": cur, "prev": prev,
                           "delta": round(cur - prev, 2) if cur is not None and prev is not None else None,
                           "last_known": max(earlier) if cur is None and earlier else None})

    # ---- running (arrives with the Garmin sync) ----
    runs = rows(DATA / "garmin" / "runs.csv")
    run_km = defaultdict(float)
    for r in runs:
        km = num(r.get("distance_km"))
        if km:
            run_km[monday(date.fromisoformat(r["date"][:10]))] += km
    distance = None
    if runs:
        cur, prev = round(run_km.get(last_mon, 0), 1), round(run_km.get(prev_mon, 0), 1)
        distance = {"value": cur, "prev": prev, "pct": round((cur - prev) / prev * 100) if prev else None}

    # ---- goals ----
    goals = []
    for g in rows(DATA / "manual" / "goals.csv"):
        start, current, target = num(g["start"]), num(g["current"]), num(g["target"])
        basis = g["basis"]
        if g["id"] == "weight" and series_weight:
            current = series_weight[-1]["avg_kg"]
        elif g["id"] == "bodyfat" and series_weight and series_weight[-1]["avg_fat"] is not None:
            current = series_weight[-1]["avg_fat"]
        elif g["id"] in LIFTS and best[g["id"]]:
            current = max(best[g["id"]].values())
            basis = "Best logged set of 5 in Hevy"
        pct = None
        if start is not None and current is not None and start != target:
            pct = round(max(0, min(100, (start - current) / (start - target) * 100)))
        d0, d1 = date.fromisoformat(g["start_date"]), date.fromisoformat(g["deadline"])
        pace = round(max(0, min(1, (today - d0).days / (d1 - d0).days)) * 100)
        goals.append({"id": g["id"], "goal": g["goal"], "area": g["area"], "unit": g["unit"], "start": start,
                      "current": current, "target": target, "pct": pct, "pace": pace, "basis": basis,
                      "deadline": g["deadline"]})

    weeks = sorted(set(visits) | {last_mon})
    out = {
        "generated": datetime.now(ZoneInfo("Europe/London")).isoformat(timespec="minutes"),
        "final_day": max(g["deadline"] for g in goals) if goals else None,
        "week": {"start": last_mon.isoformat(), "end": (last_mon + timedelta(days=6)).isoformat()},
        "tiles": {
            "weight": body_tile("kg"),
            "bodyfat": body_tile("fat"),
            "distance": distance,
            "gym": {"value": visits.get(last_mon, 0), "prev": visits.get(prev_mon, 0),
                    "planned": PLANNED_GYM_VISITS, "total": len(workout_days), "connected": bool(sets)},
            "lifts": lift_tiles,
        },
        "goals": goals,
        "series": {
            "weight": series_weight,
            "lifts": {k: [{"date": d.isoformat(), "kg": best[k].get(d) or None, "e1rm": e1rm[k][d]}
                          for d in sorted(e1rm[k])] for k in LIFTS},
            "gym_weeks": [{"week": w.isoformat(), "visits": visits.get(w, 0)} for w in weeks],
        },
        "checkins": rows(DATA / "manual" / "checkins.csv"),
    }
    (ROOT / "site").mkdir(exist_ok=True)
    (ROOT / "site" / "data.json").write_text(json.dumps(out, indent=1) + "\n")
    print("Built site/data.json")


if __name__ == "__main__":
    main()
