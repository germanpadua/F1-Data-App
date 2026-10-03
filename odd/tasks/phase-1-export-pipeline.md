# Feature: Phase 1 — Static Export Pipeline

**Status**: in progress
**Predecessor**: `odd/tasks/modernizacion-f1-data-app.md` (Phase 0, complete)
**Created**: 2026-10-03

## Why this exists

Phase 2 is a static web frontend on Vercel with a full race replay. Vercel cannot run FastF1
(serverless functions, read-only filesystem except an ephemeral `/tmp`, no place for a
multi-hundred-MB cache), so every byte the frontend needs must be precomputed here and served as a
static asset.

Phase 1 is therefore the boundary between the two systems: a Python pipeline that turns a completed
FastF1 session into compact, versioned, self-describing artifacts.

The replay scope was decided by the user as all four layers: cars on the map with a data clock,
a timing tower with tyre strategy, synced per-driver telemetry, and timeline events.

## Hard constraint: the repository must not grow

Phase 0 purged 733 MB of committed caches from this repository. Artifacts therefore go to
`data/export/`, which is **gitignored**. Publishing them is a Phase 2 decision (object storage such
as Vercel Blob or R2, or a dedicated data branch). Committing race artifacts to `main` is explicitly
rejected.

## The data contract (v1)

This is the part that is expensive to get wrong, so it is pinned here before any code.

### One shared time grid

Every time-indexed array in every artifact shares one grid. This is what makes the frontend simple:
a sample is addressed by a single integer, and the replay clock, the timing tower and the telemetry
charts all advance together.

- `t0_s` — the session reference instant, in seconds. `0` is the start of the session (`R` = race
  start).
- `step_s` — the fixed step, default `0.5`.
- `sample_index = round((t_s - t0_s) / step_s)`
- `n_samples` — the grid length, identical for every array in every artifact of the same race.

Consequence, and a deliberate saving: **no per-sample time array is ever stored.** Time is implicit
from the index. A car trace is 3 arrays, not 4.

### Missing data

`null` for one grid sample. A driver who retired early has `null` from their last sample on; a
sample gap has `null` in the gap. `null` is never silently replaced by `0`, which on this data is a
valid and very different value (0 km/h is a stopped car, 0 % throttle is a lift).

### Quantization

- `x`, `y` — integers, exactly as FastF1 provides them (tenths of a metre). Never floats.
- `speed` — integer km/h.
- `throttle` — integer percent, 0-100.
- `brake`, `drs` — integers, 0 or 1.
- `rpm`, `gear` — integers.

### Layout

```
data/export/                                  (gitignored)
  index.json
  <year>/<round>-<slug>/
    race.json
    replay.json
    tel/<DRIVER>.json
```

The split exists to keep the index page cheap: `race.json` is tens of KB, `replay.json` is the heavy
one, and the per-driver telemetry files are fetched only when a driver is selected. Splitting channels
**per driver** rather than per race is what keeps the synced-telemetry layer affordable.

### `index.json`

```json
{
  "schema": "f1da.export.index/1",
  "generated_at": "2026-10-03T10:00:00Z",
  "step_s": 0.5,
  "races": [
    {
      "year": 2026, "round": 15, "slug": "2026-15-azerbaijan-grand-prix",
      "event": "Azerbaijan Grand Prix", "session": "R", "date": "2026-09-26",
      "n_samples": 10800, "drivers": ["VER", "PER"], "bytes": 1234567
    }
  ]
}
```

### `race.json` — the manifest

```json
{
  "schema": "f1da.export.race/1",
  "year": 2026, "round": 15, "session": "R",
  "event": "Azerbaijan Grand Prix",
  "location": "Baku", "country": "Azerbaijan", "date": "2026-09-26",
  "t0_s": 0.0, "step_s": 0.5, "n_samples": 10800,
  "total_laps": 51,
  "drivers": [
    {"code": "VER", "number": "1", "name": "Max Verstappen",
     "team": "Red Bull Racing", "color": "#3671C6"}
  ],
  "track": {
    "points": [[1234, 5678], [1235, 5680]],
    "rotation_deg": 12.3,
    "corners": [{"number": 1, "letter": "", "x": 1234, "y": 5678}]
  },
  "timing": [
    {"code": "VER", "laps": [
      {"lap": 1, "position": 1, "lap_time_s": 93.104,
       "compound": "MEDIUM", "tyre_life": 3,
       "pit_in": false, "pit_out": false, "gap_leader_s": 0.0}
    ]}
  ],
  "events": [
    {"t_s": 123.4, "kind": "track_status", "status": "2", "message": null, "driver": null},
    {"t_s": 180.0, "kind": "race_control", "status": null,
     "message": "SAFETY CAR DEPLOYED", "driver": null}
  ],
  "warnings": []
}
```

- `track.points` is the **centreline** polyline, decimated to a few hundred points. It is the road the
  cars are drawn on.
- `track.rotation_deg` comes from FastF1's circuit info; the frontend applies it exactly as
  `modules/utils.py: rotate()` does, so the map orientation matches the existing Streamlit charts.
- `timing[].laps[].gap_leader_s` is the gap to the leader at the end of that lap, `null` if unknown
  (for example the leader itself, or a car a lap down).
- `events` merges track status changes and race control messages into one time-ordered list. `kind` is
  one of `track_status`, `race_control`, `safety_car`, `vsc`. The safety car and VSC are derived from
  race control messages and track status, and the derivation rule must be documented in code.
- `warnings` lists anything the exporter had to skip or approximate, so a gap in the data is visible
  in the artifact instead of being a silent hole.

### `replay.json` — the heavy payload

```json
{
  "schema": "f1da.export.replay/1",
  "step_s": 0.5, "n_samples": 10800,
  "cars": [{"code": "VER", "x": [1234], "y": [5678], "speed": [312]}]
}
```

`x`, `y` and `speed` are each exactly `n_samples` long.

### `tel/<DRIVER>.json` — the lazy payload

```json
{
  "schema": "f1da.export.tel/1",
  "code": "VER", "step_s": 0.5, "n_samples": 10800,
  "throttle": [100], "brake": [0], "rpm": [11800], "gear": [8], "drs": [1]
}
```

Each channel array is exactly `n_samples` long.

## Tasks

- [ ] **P1.1 — Skeleton and grid maths.** Create the `pipeline/` package with the shared time-grid
  helpers (session instant to grid index, array length invariant, `null` for missing), the
  `data/export/` layout writer, and artifact schema constants. Everything else depends on this.
- [ ] **P1.2 — Track geometry.** Extract the centreline polyline, the rotation angle and the corner
  labels from the session and write them into `race.json`.
- [ ] **P1.3 — Replay traces.** Decimate each car's position and speed onto the shared grid and write
  `replay.json`. This is the payload with the largest size budget, so it is measured, not assumed.
- [ ] **P1.4 — Timing tower and tyre strategy.** Per lap per driver: position, lap time, compound,
  tyre life, pit in/out, gap to leader.
- [ ] **P1.5 — Timeline events.** Track status changes, race control messages, and the derived safety
  car and VSC periods, time-ordered and de-duplicated.
- [ ] **P1.6 — Per-driver telemetry.** Throttle, brake, RPM, gear and DRS onto the same grid, one file
  per driver.
- [ ] **P1.7 — CLI and index.** `python -m pipeline.export --year Y --round N [--session R] [--out DIR]`,
  idempotent, and rewriting `index.json` with every race it has produced.
- [ ] **P1.8 — Self-check validator.** `python -m pipeline.check --root data/export` verifying schemas,
  the `n_samples` length invariant on every array, plausible value ranges, and time ordering of events.
  This is the verification surface for the whole pipeline: a pipeline that produces plausible-looking
  but wrong-length arrays is worse than one that fails.
- [ ] **P1.9 — CI workflow.** A GitHub Actions workflow that runs the export and the self-check for the
  most recent completed round, and uploads the artifacts. It must not commit artifacts to the repo.
- [ ] **P1.10 — Documentation.** `pipeline/README.md` describing the contract, the commands, and the
  measured sizes, plus a README section in the repository root.

## Verification

A real completed round must be exported and self-checked end to end. `2026` round `15`
(Azerbaijan Grand Prix, 2026-09-26) is known to have data and is the reference case. Reported sizes
per artifact are required evidence, not estimates.

## Non-goals

- No frontend work. Phase 2.
- No artifact publishing or object storage. Phase 2.
- No alert or episode domain: that belongs to the sibling `telemetry-sentinel` project, and reusing
  its web shell does not mean importing its domain model.
- No commits of generated artifacts.
