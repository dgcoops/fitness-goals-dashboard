#!/usr/bin/env python3
"""Pull Garmin activities since 1 October 2026 and write them to data/garmin/.

Uses Garmin's Personal API. Reads the personal API key from GARMIN_API_KEY and
skips quietly when it is not set, so the workflow still passes before the key
is added.
Outputs:
  data/garmin/activities.json - activity summaries exactly as the API returns them
  data/garmin/runs.csv        - one row per run, ready for charting
Standard library only.
"""
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

BASE = "https://personal.connectapi.garmin.com"
TOKEN_PATH = "/personalapitoken-service/personal-api/personal-api-key/token"
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "garmin"
PAGE = 50


def call(path, headers, method="GET", params=None):
    url = BASE + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers=headers, method=method)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read()
        except urllib.error.HTTPError as err:
            if err.code in (429, 500, 502, 503, 504) and attempt < 3:
                time.sleep(2 ** attempt * 2)
                continue
            # Never print headers (they carry the key or token).
            sys.exit(f"Garmin API returned {err.code} for {path}")
        except urllib.error.URLError as err:
            if attempt < 3:
                time.sleep(2 ** attempt * 2)
                continue
            sys.exit(f"Could not reach Garmin: {err.reason}")


# Pull a little history before the goals began, so recent baselines (such as the
# last parkrun before the start) are kept. The dashboard decides what counts.
HISTORY_START = "2026-10-01"


def main():
    key = os.environ.get("GARMIN_API_KEY", "").strip()
    if not key:
        print("GARMIN_API_KEY is not set, skipping Garmin")
        return

    token = call(TOKEN_PATH, {"Accept": "*/*", "Authorization": f"ApiKey {key}"}, method="POST").decode().strip()
    auth = {"Accept": "application/json", "Authorization": f"Bearer {token}"}

    activities, start = [], 0
    while True:
        body = call("/activitylist-service/activities/search/activities", auth,
                    params={"start": start, "limit": PAGE, "startDate": HISTORY_START, "endDate": date.today().isoformat()})
        page = json.loads(body) if body else []
        if not isinstance(page, list):
            sys.exit("Garmin returned an unexpected activity list shape")
        activities.extend(page)
        if len(page) < PAGE:
            break
        start += PAGE

    activities.sort(key=lambda a: str(a.get("startTimeLocal", "")))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "activities.json").write_text(json.dumps(activities, indent=1, sort_keys=True) + "\n")

    fields = ["date", "activity_id", "name", "type", "start_time_local", "distance_km", "duration_s",
              "moving_s", "avg_hr", "max_hr", "elevation_gain_m", "avg_pace_s_per_km"]
    runs = 0
    with open(OUT / "runs.csv", "w", newline="") as fh:
        out = csv.DictWriter(fh, fieldnames=fields)
        out.writeheader()
        for a in activities:
            kind = (a.get("activityType") or {}).get("typeKey", "")
            metres, secs = a.get("distance"), a.get("duration")
            if "running" not in kind or not metres:
                continue
            moving = a.get("movingDuration") or secs
            out.writerow({
                "date": str(a.get("startTimeLocal", ""))[:10],
                "activity_id": a.get("activityId", ""),
                "name": a.get("activityName", ""),
                "type": kind,
                "start_time_local": a.get("startTimeLocal", ""),
                "distance_km": round(metres / 1000, 2),
                "duration_s": round(secs) if secs else "",
                "moving_s": round(moving) if moving else "",
                "avg_hr": a.get("averageHR") or "",
                "max_hr": a.get("maxHR") or "",
                "elevation_gain_m": round(a["elevationGain"]) if a.get("elevationGain") else "",
                "avg_pace_s_per_km": round(moving / (metres / 1000)) if moving else "",
            })
            runs += 1
    print(f"Wrote {len(activities)} activities, {runs} of them runs")


if __name__ == "__main__":
    main()
