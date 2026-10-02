# F1-Data-App

Streamlit app for exploring Formula 1 session data through
[FastF1](https://docs.fastf1.dev/): race position evolution, lap times by tyre
compound, qualifying deltas to pole, tyre degradation, team pace, track maps and
championship evolution.

## Status

Phase 0 (repository hygiene, current-season data, reproducibility) is complete.
The presentation layer is still Streamlit. A web frontend with a race replay and
a precomputed data pipeline are planned as Phase 1 and Phase 2; the tracked plan
lives in [`odd/tasks/modernizacion-f1-data-app.md`](odd/tasks/modernizacion-f1-data-app.md).

## Requirements

- **Python 3.12.** The pinned scientific stack is verified on 3.12 only. Do not
  use 3.13+ until the stack is re-verified.
- [`uv`](https://docs.astral.sh/uv/) for environment and dependency management.
- Network access on first run of each session.

## Setup

```bash
git clone https://github.com/germanpadua/F1-Data-App.git
cd F1-Data-App
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
```

## Run

```bash
.venv/bin/python -m streamlit run main_app.py
```

The first load of a given session downloads from the F1 live timing API and takes
minutes. Later loads are served from the local FastF1 cache in `cache/`.

## Data and artifacts

| Path | Contents | Committed |
|---|---|---|
| `data/circuitos_f1.csv` | Circuit coordinates used by the geocoding fallback | yes |
| `data/circuit_image/*.png` | Curated circuit maps | yes |
| `cache/` | FastF1 cache plus generated circuit maps | **no** — gitignored, hundreds of MB, fully regenerable |

Offered seasons are 2018 through the current year, derived at runtime from the
system date, so a new season needs no code change.

## Data sources

- **Session timing and telemetry** — the official F1 live timing API via FastF1.
- **Standings and schedules** — jolpica-f1 through `fastf1.ergast`. FastF1 3.8.x
  already defaults to `https://api.jolpi.ca/ergast/f1`; the original Ergast API
  shut down at the end of 2024.
- **Geocoding fallback** — OpenStreetMap Nominatim, called with the User-Agent
  its usage policy requires.

## Known limitations

- **This app cannot run on Vercel as it stands.** Vercel executes serverless
  functions with a read-only filesystem apart from an ephemeral `/tmp`, and
  FastF1 needs to download, parse and cache hundreds of megabytes per session.
  Hosting the analysis there requires splitting the project into a Python data
  pipeline that precomputes compact artifacts and a static frontend that only
  reads them. That is Phase 1 plus Phase 2, not a deployment change.
- **Single-user and stateful.** The Streamlit server holds heavy session objects
  in memory and a large cache on local disk, which is the opposite of the
  serverless model.
- **Championship data can lag at the source.** If jolpica serves a completed
  round with the previous round's cumulative table, that round's points surface
  one round later. The app warns when it detects a completed round with no
  points at all, instead of showing it silently.
- **HTTP 429 is a real risk.** jolpica rate-limits. Standing requests retry with
  backoff and skip a round rather than crash, but an aggressive refresh loop
  will still be throttled.
- Session loading fetches laps, telemetry and weather eagerly, so the first
  access to a session is slow and memory-hungry.

## Roadmap

- **Phase 1** — a Python pipeline that exports compact per-race artifacts
  (aggregated charts, plus positional telemetry, timing/strategy data, driver
  telemetry channels and timeline events for the replay), run automatically after
  each Grand Prix.
- **Phase 2** — a web frontend on Vercel with a race replay: 20 cars on the track
  map with a data clock, a timing tower with tyre strategy, synced driver
  telemetry, and flags/safety car events on the timeline.
