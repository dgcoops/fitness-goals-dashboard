#!/usr/bin/env python3
"""Pull Withings weigh-ins and write them to data/withings/weight.csv.

Withings issues a new refresh token every time one is used, so the latest one is
kept in data/withings/token.enc, encrypted with WITHINGS_TOKEN_KEY. The first run
uses the WITHINGS_REFRESH_TOKEN secret. Skips quietly when secrets are missing.
Standard library plus the openssl command line tool.
"""
import csv
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "withings"
TOKEN_FILE = OUT / "token.enc"
HISTORY_START = datetime(2026, 10, 1, tzinfo=timezone.utc)
LONDON = ZoneInfo("Europe/London")
TYPES = {1: "weight_kg", 6: "fat_pct", 8: "fat_mass_kg", 5: "lean_mass_kg", 76: "muscle_kg", 77: "water_kg", 88: "bone_kg"}


def post(url, fields, token=None):
    req = urllib.request.Request(url, data=urllib.parse.urlencode(fields).encode())
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.load(resp)
    except urllib.error.URLError as err:
        sys.exit(f"Could not reach Withings: {getattr(err, 'reason', err)}")
    if body.get("status") != 0:
        # Withings reports errors inside a 200 response. Never print the request.
        sys.exit(f"Withings returned status {body.get('status')} for {fields.get('action')}")
    return body["body"]


def crypt(data, key, decrypt):
    args = ["openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-iter", "200000", "-salt", "-pass", "env:WITHINGS_TOKEN_KEY"]
    if decrypt:
        args.append("-d")
    run = subprocess.run(args, input=data, capture_output=True, env={**os.environ, "WITHINGS_TOKEN_KEY": key})
    if run.returncode:
        sys.exit("Could not " + ("decrypt" if decrypt else "encrypt") + " the stored Withings token")
    return run.stdout


def main():
    cid, secret, key = (os.environ.get(k, "").strip() for k in ("WITHINGS_CLIENT_ID", "WITHINGS_CLIENT_SECRET", "WITHINGS_TOKEN_KEY"))
    first = os.environ.get("WITHINGS_REFRESH_TOKEN", "").strip()
    if not (cid and secret and key and (first or TOKEN_FILE.exists())):
        print("Withings secrets are not set, skipping Withings")
        return

    refresh = crypt(TOKEN_FILE.read_bytes(), key, True).decode().strip() if TOKEN_FILE.exists() else first
    tokens = post("https://wbsapi.withings.net/v2/oauth2", {
        "action": "requesttoken", "grant_type": "refresh_token",
        "client_id": cid, "client_secret": secret, "refresh_token": refresh})

    # Save the new refresh token before using the access token, so it survives a later failure.
    OUT.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_bytes(crypt(tokens["refresh_token"].encode(), key, False))

    groups, offset = [], None
    while True:
        fields = {"action": "getmeas", "category": 1, "meastypes": ",".join(map(str, TYPES)),
                  "startdate": int(HISTORY_START.timestamp()), "enddate": int(datetime.now(timezone.utc).timestamp())}
        if offset:
            fields["offset"] = offset
        body = post("https://wbsapi.withings.net/measure", fields, tokens["access_token"])
        groups.extend(body.get("measuregrps", []))
        if not body.get("more"):
            break
        offset = body.get("offset")

    readings = []
    for g in groups:
        row = {"date": "", "time": ""}
        when = datetime.fromtimestamp(g["date"], LONDON)
        row["date"], row["time"] = when.date().isoformat(), when.strftime("%H:%M")
        for m in g.get("measures", []):
            if m.get("type") in TYPES:
                row[TYPES[m["type"]]] = round(m["value"] * 10 ** m["unit"], 2)
        if any(k in row for k in TYPES.values()):
            readings.append(row)
    readings.sort(key=lambda r: (r["date"], r["time"]))

    with open(OUT / "weight.csv", "w", newline="") as fh:
        out = csv.DictWriter(fh, fieldnames=["date", "time", *TYPES.values()], restval="")
        out.writeheader()
        out.writerows(readings)
    print(f"Wrote {len(readings)} Withings readings")


if __name__ == "__main__":
    main()
