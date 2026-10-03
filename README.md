# F1-Data-App

Streamlit app for exploring Formula 1 session data through
[FastF1](https://docs.fastf1.dev/): race position evolution, lap times by tyre
compound, qualifying deltas to pole, tyre degradation, team pace, track maps and
championship evolution.

## Status

Phase 0 (repository hygiene, current-season data, reproducibility) and Phase 1
(the static export pipeline, see [pipeline/README.md](pipeline/README.md)) are
complete. The presentation layer is still Streamlit; the Phase 2 web frontend
with a race replay will read the precomputed artifacts. The tracked plan lives
in [`odd/tasks/modernizacion-f1-data-app.md`](odd/tasks/modernizacion-f1-data-app.md).

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

## Data pipeline

A Python pipeline turns each completed session into compact, versioned JSON
artifacts under `data/export/` (gitignored): track geometry, replay traces,
per-lap timing, timeline events and per-driver telemetry, all on one shared
0.5 s time grid trimmed to the racing window.

```bash
.venv/bin/python -m pipeline.export --year 2026 --round 15 --session R
.venv/bin/python -m pipeline.check --root data/export
```

The full data contract, artifact layout, measured sizes and the null/delta
rules a frontend author must implement are documented in
[`pipeline/README.md`](pipeline/README.md). Exporting and publishing are
**local steps, not CI jobs**: the F1 CDN answers `403 Forbidden` to every
session stream from a GitHub-hosted runner (measured; see
[`odd/tasks/phase-2-publish-hardening.md`](odd/tasks/phase-2-publish-hardening.md)),
so CI runs the test suites and nothing that needs F1 data. Publishing the
declared published season (2026, see [`pipeline/scope.py`](pipeline/scope.py))
to Vercel Blob is `node tools/blob-publish/publish.mjs` with
`BLOB_READ_WRITE_TOKEN` in the environment, and re-running it is safe: it
overwrites the same pathnames and merges the published index. A backfill
command exports every completed round of a season in one resumable run:
`python -m pipeline.export --year 2026 --all-completed`.

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

- **Phase 1** (complete) — a Python pipeline that exports compact per-race
  artifacts (track geometry, replay traces, timing/strategy data, per-driver
  telemetry channels and timeline events for the replay) on a shared time grid,
  with a self-check validator and a local publish step to Vercel Blob; see
  [`pipeline/README.md`](pipeline/README.md).
- **Phase 2** — a web frontend on Vercel with a race replay: 20 cars on the track
  map with a data clock, a timing tower with tyre strategy, synced driver
  telemetry, and flags/safety car events on the timeline.
