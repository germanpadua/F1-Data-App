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

- `t0_s` — the session reference instant, in seconds. Originally documented as `0` meaning the start of
  the session; **amended by Amendment 1** to be the session-relative second at which the trimmed racing
  grid starts. It is written to the artifact and the frontend needs it to map a grid index back to a
  session time.
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

- `x`, `y` — integers, exactly as FastF1 provides them (tenths of a metre). Never floats. **Amended by
  Amendment 1: delta-encoded in `replay.json`** (`x[0]` absolute, then differences).
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

## Amendments

### Amendment 1 — trim the grid to the racing window, and delta-encode x/y

Raised by the P1.1/P1.2/P1.3 implementation, which measured the first real export.

**Problem.** `n_samples` came out at **19 434** on 2026 round 15, because the session-relative `Time`
axis starts at the beginning of the session and includes roughly 57 minutes of pre-race running. The
race itself is about 105 minutes. `replay.json` measured **7.18 MB** for that race, which extrapolates
to about **172 MB for a 24-race season** — too heavy to be the input of a static site.

**A1a — the grid covers the racing window only.**

- Grid origin: the earliest `LapStartTime` across drivers, which is the leader's lap 1 and therefore
  approximately lights out.
- Grid end: the latest lap end across drivers plus a 5 s margin.
- `t0_s` is now meaningful and MUST be written: the session-relative seconds at which the grid starts.
  It was previously documented as `0.0`; it is now the offset the frontend needs in order to map a
grid index back to a session time for events and timing data.
- `n_samples` shrinks accordingly. Expect roughly 12 000-13 000 for a normal race.

**A1b — `x` and `y` are delta-encoded.** `x[0]` and `y[0]` are absolute; every later value is the
integer difference from the previous sample. A smooth position series becomes small integers, which
compresses far better on the wire. The frontend recovers the series with a prefix sum, which is a few
lines. `speed` stays absolute because it is already a small bounded range.

Both changes must be reflected in `pipeline/check.py`: the length invariant is unchanged, but the
range check must run on the reconstructed series, not the deltas, or a delta of 200 would be wrongly
rejected.

**A1c — channels recorded from the implementation.** These are verified against real 2026 data and
supersede guesswork:

| Data | Column notes |
|---|---|
| Laps | `LapTime`, `LapNumber`, `Compound`, `TyreLife`, `PitInTime`, `PitOutTime`, `Position`, `LapStartTime`, `TrackStatus` |
| Track status | `Time` is a Timedelta (session-relative), plus `Status` and `Message` |
| Race control | `Time` is an **absolute datetime64**, NOT a Timedelta. It must be converted with `Time - session.t0_date`. `t0_date` is safe as an axis *converter* here and remains forbidden as the grid origin |
| Position data | `SessionTime`, `X`, `Y`, `Status` |
| Car data | `SessionTime`, `RPM`, `Speed`, `nGear`, `Throttle`, `Brake`, `DRS` |

Two further findings from the same run:

- **Raw `Throttle` reaches 104** in the feed, above the contract's 0-100. P1.6 must clip to 0-100 and
  record the clipping in `warnings`.
- **`DRS` is 0 for every sample** of this session's feed. The channel will be legitimately all-zero; it
  must not be dropped or treated as missing, and the frontend must not infer DRS state from it as if it
  were reliable.

## Tasks

- [x] **P1.1 — Skeleton and grid maths.** Create the `pipeline/` package with the shared time-grid
  helpers (session instant to grid index, array length invariant, `null` for missing), the
  `data/export/` layout writer, and artifact schema constants. Everything else depends on this.
- [x] **P1.2 — Track geometry.** Extract the centreline polyline, the rotation angle and the corner
  labels from the session and write them into `race.json`.
- [x] **P1.3 — Replay traces.** Decimate each car's position and speed onto the shared grid and write
  `replay.json`. This is the payload with the largest size budget, so it is measured, not assumed.
- [x] **P1.4 — Timing tower and tyre strategy.** Per lap per driver: position, lap time, compound,
  tyre life, pit in/out, gap to leader.
- [x] **P1.5 — Timeline events.** Track status changes, race control messages, and the derived safety
  car and VSC periods, time-ordered and de-duplicated.
- [x] **P1.6 — Per-driver telemetry.** Throttle, brake, RPM, gear and DRS onto the same grid, one file
  per driver.
- [x] **P1.7 — CLI and index.** `python -m pipeline.export --year Y --round N [--session R] [--out DIR]`,
  idempotent, and rewriting `index.json` with every race it has produced.
- [x] **P1.8 — Self-check validator.** `python -m pipeline.check --root data/export` verifying schemas,
  the `n_samples` length invariant on every array, plausible value ranges, and time ordering of events.
  This is the verification surface for the whole pipeline: a pipeline that produces plausible-looking
  but wrong-length arrays is worse than one that fails.
- [x] **P1.9 — CI workflow.** A GitHub Actions workflow that runs the export and the self-check for the
  most recent completed round, and uploads the artifacts. It must not commit artifacts to the repo.
- [x] **P1.10 — Documentation.** `pipeline/README.md` describing the contract, the commands, and the
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

## Status: COMPLETE (2026-10-03)

All ten tasks are implemented and the pipeline exports and self-checks a real race end to end.

### Measured artifacts — 2026 round 15, Azerbaijan Grand Prix

| Artifact | Bytes | Fetched when |
|---|---|---|
| `race.json` | 164 747 | always, it is the index/manifest for the race |
| `replay.json` | 4 086 965 | when the replay is opened |
| `tel/*.json` (22 files) | 5 570 542 total, largest 338 401, median 238 623 | one file, only when a driver is selected |
| **per race** | **9 822 254** | |

`n_samples` is 11 858 with `t0_s` 3413.247. `index.json` is 708 B. A 24-race season is
**~235.7 MB** of artifacts.

**Read that number correctly:** it is a *deploy-size* figure, not a per-visit cost. The index page reads
only `index.json`, the replay fetches one `replay.json`, and a `tel/` file is fetched only when a driver
is selected. Per-visit transfer is therefore about 4.25 MB of JSON before compression.

### Two reductions that were measured, not assumed

| Change | `n_samples` | `replay.json` |
|---|---|---|
| session-wide grid (original contract) | 19 434 | 7 184 195 |
| + trim to the racing window | 11 858 | 4 853 862 |
| + delta-encoded x/y | 11 858 | 4 086 965 |

Verified by round trip: prefix-summing one real car's deltas reproduces the absolute series exactly,
including across a 200-null gap on a retired car.

### Honest caveats recorded in `race.json`'s `warnings`

- raw `throttle` reaches 104 in the feed, so it is clipped on 410 samples and the clip count is recorded
- `drs` is 0 for every sample of this feed: the channel is kept but explicitly marked as not a reliable
  DRS state
- 57 events outside the trimmed window were dropped, and the count is stated rather than hidden
- 125 `gap_leader_s` values are null because the leader's own lap was untimed during the safety car;
  they are not fabricated

### Review status

The work in this phase is **NOT REVIEWED**. The first `review.start` for it returned a real
`gentle-ai.review-integration.consent/v3` envelope at **risk level high** (shell scripting in
`.github/workflows/export-latest-round.yml`) with `lineage_created: false`, and the consent choice is
the human's to make, not the agent's. It was relayed verbatim with its `consentBinding` and never
answered from agent prose. The binding expires after ten minutes, so a later attempt needs a fresh
`review.start`.
