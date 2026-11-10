# Is Dan ticking over?

A private dashboard tracking progress towards the 17 October 2027 goals.

## How it works

1. `.github/workflows/sync.yml` runs once a day.
2. `scripts/hevy_sync.py` pulls every Hevy workout into `data/hevy/`, `scripts/garmin_sync.py` pulls Garmin activities into `data/garmin/`, and `scripts/withings_sync.py` pulls weigh-ins into `data/withings/`.
3. `scripts/build.py` turns everything under `data/` into `site/data.json`.
4. The workflow commits the result, and AWS Amplify redeploys `site/`.

## Layout

- `data/manual/` - goals, weigh-ins and check-ins kept by hand until their sources are connected
- `data/hevy/`, `data/garmin/`, `data/withings/` - written by the sync, do not edit
- `data/withings/token.enc` - the current Withings refresh token, encrypted with `WITHINGS_TOKEN_KEY`. Delete it if you re-run the Withings setup.
- `site/` - the dashboard page (`index.html`) and its data (`data.json`)

## Setup

1. Keep this repository private.
2. Settings > Secrets and variables > Actions: add secrets named `HEVY_API_KEY` and `GARMIN_API_KEY` (a Garmin Connect personal API key).
3. Actions tab > "Sync training data" > "Run workflow" for the first pull.
4. AWS Amplify (London region): deploy this repository, then turn on password protection for the branch.

## Withings setup (once)

1. At developer.withings.com, create a Public API app with callback URL `http://localhost:8765/callback`.
2. On your own computer: `python3 scripts/withings_setup.py`, enter the app's client ID and secret, and approve access.
3. Add the four secrets it lists: `WITHINGS_CLIENT_ID`, `WITHINGS_CLIENT_SECRET`, `WITHINGS_REFRESH_TOKEN`, `WITHINGS_TOKEN_KEY`.
