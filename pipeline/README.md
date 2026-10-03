# Data pipeline (Phase 1)

Turns a completed FastF1 session into compact, versioned, self-describing JSON
artifacts under `data/export/` (gitignored). This is the boundary between the
Python side (which can run FastF1) and the future static frontend (which
cannot). The authoritative contract is
[`odd/tasks/phase-1-export-pipeline.md`](../odd/tasks/phase-1-export-pipeline.md),
including its Amendments; this file documents the contract **as implemented**.

## Commands

```bash
# Export one session (default output root: data/export/)
.venv/bin/python -m pipeline.export --year 2026 --round 15 --session R

# Backfill: export every COMPLETED round of a season in one go (resumable:
# already-exported rounds are skipped, one failure does not abort the rest,
# per-round summary at the end). "Completed" is derived from FastF1's
# schedule and today's date, the same notion the CI uses.
.venv/bin/python -m pipeline.export --year 2026 --all-completed

# Optional bounding cap (round <= N), for partial bootstraps and tests
.venv/bin/python -m pipeline.export --year 2026 --all-completed --upto-round 15

# Validate every artifact on disk against the contract (the verification surface)
.venv/bin/python -m pipeline.check --root data/export
```

Requirements: Python 3.12, FastF1 3.8.3 (see `requirements.txt`). The FastF1
cache lives in `cache/` at the repo root. CI runs this automatically once a day
for the most recently completed round (`.github/workflows/export-latest-round.yml`);
artifacts are uploaded as workflow artifacts and are **never committed**.

## Artifact layout

```
data/export/                                  (gitignored)
  index.json
  <year>/<round>-<slug>/
    race.json
    replay.json
    tel/<CODE>.json        one per driver, fetched lazily
```

Measured sizes for the reference case, 2026 round 15 (Azerbaijan Grand Prix,
race, 22 drivers, `n_samples` 11 858):

| Artifact | Measured size |
|---|---|
| `race.json` | 164 747 B (~161 KB) |
| `replay.json` | 4 086 965 B (~3.9 MB) |
| `tel/*.json` (22 files) | 5 570 542 B (~5.3 MB); largest 338 401 B, median 238 623 B |
| **Per-race total** | **9 822 254 B (~9.4 MB)** |
| 24-race season extrapolation | ~235.7 MB |

The split keeps the index page cheap: `race.json` is tens-to-hundreds of KB,
`replay.json` is the heavy one, and a driver's telemetry is only fetched when
selected.

## Publishing (Vercel Blob)

Exporting and publishing are two different things. The CLI can export any
season locally; publishing to Vercel Blob is bounded to a **declared
published-season scope** so the published payload stays well inside the free
tier (1 GB): one race measures 9 822 254 B, so the completed 15-round 2026
season is ~147 MB, ~15% of the free tier.

- **The scope lives in one place**: [`pipeline/scope.py`](scope.py),
  `PUBLISHED_SEASONS = (2026,)`. Widening it is a one-line change there plus
  the mirror constant in `tools/blob-publish/publish.mjs` (Node cannot import
  Python). Nothing else needs to change.
- The scope is **enforced at publish time only, never at export time**:
  `export.py` and `check.py` are deliberately scope-blind, and the publisher
  skips and counts out-of-scope races.
- The publisher (`tools/blob-publish/publish.mjs`) uploads `index.json` and,
  for every in-scope race, `race.json`, `replay.json` and every
  `tel/<DRIVER>.json`, preserving the on-disk relative paths as Blob
  pathnames (e.g. `2026/15-azerbaijan-grand-prix/replay.json`), public
  access, bounded concurrency (4), non-zero exit naming the file on failure.

```bash
# Preview exactly what would be uploaded, totals and out-of-scope skips
# (no token needed, nothing is uploaded)
node tools/blob-publish/publish.mjs --dry-run

# Publish for real (needs BLOB_READ_WRITE_TOKEN in the environment)
node tools/blob-publish/publish.mjs
```

**The token**: `BLOB_READ_WRITE_TOKEN` is Vercel's documented long-lived
read-write token for code running outside Vercel, which is exactly this case
(GitHub Actions). Create it in the Vercel dashboard under **Storage → your
Blob store → Blob read-write token**, then add it as a **GitHub repository
secret named `BLOB_READ_WRITE_TOKEN`** (Settings → Secrets and variables →
Actions). Without the secret, the publisher prints that publishing was
skipped and exits 0, so CI stays green for anyone without the token.

The daily CI job (`.github/workflows/export-latest-round.yml`) installs the
publisher with `npm install --prefix tools/blob-publish` and runs it after
the export and self-check. There is deliberately **no root `package.json`**:
the Phase 2 frontend gets its own directory and its own Vercel project.

## The shared time grid

Every time-indexed array in every artifact of one race shares ONE grid:

- `t0_s` — the session-relative second at which the grid starts. It is the
  earliest `LapStartTime` across drivers (about lights out), **not** 0.0: the
  grid is trimmed to the racing window (latest lap end + 5 s margin), which
  excludes ~57 minutes of pre-race running.
- `step_s` — fixed step, 0.5 s.
- `n_samples` — grid length, identical for every array in every artifact
  (11 858 on the reference race).

**No per-sample time array is ever stored.** A frontend maps a grid index back
to a session instant with `t_s = t0_s + index * step_s`, and an event/timing
instant to an index with `index = round((t_s - t0_s) / step_s)`, both using
`t0_s` from `race.json`.

## Null rules (implement these exactly)

- A missing sample is JSON `null`. `null` means "no data", never zero:
  0 km/h is a stopped car, 0 % throttle is a lift, so a silent zero would lie.
- A driver who retired has `null` in every channel from their last real
  sample on. The exporter cuts a retired car at the last instant it was
  moving (`Speed > 0`); on the reference race STR therefore has 10 110 nulls
  of 11 858 samples while RUS (finished) has only 203 gap nulls.
- Shorter gaps (data dropouts, samples outside the window) are also `null`,
  naturally.
- Buckets with several source samples keep the **last** one; source NaNs
  become `null`.

## Delta encoding in `replay.json` (Amendment 1)

`x` and `y` (tenths of a metre, integers) are **delta-encoded**:

- `x[0]`/`y[0]` (first non-null entries) are ABSOLUTE;
- every later non-null value is the integer difference from the previous
  non-null value;
- `null` is transparent to the chain: after any run of nulls, the next
  non-null value is the difference from the last non-null value BEFORE the
  gap.

Reconstruction is a running sum over non-null entries, lossless across gaps
of any length:

```js
let running = null;
const xy = deltas.map(v => {
  if (v === null) return null;
  running = running === null ? v : running + v;
  return running;
});
```

`speed` stays absolute (small bounded range already).

## Telemetry channels (`tel/<CODE>.json`)

Each file: `schema`, `code`, `step_s`, `n_samples`, and five arrays, each
exactly `n_samples` long: `throttle`, `brake`, `rpm`, `gear`, `drs`.

- `throttle` — integer 0-100. The raw feed can exceed 100 (it reaches 104 on
  the reference race); the exporter clips and **records the number of clipped
  samples in `race.json` `warnings`** (410 samples there).
- `brake` — 0 or 1. `drs` — 0 or 1.
- `rpm` — integer (plausible range checked 0-18 000). `gear` — integer 0-8
  (0 = neutral).
- `drs` — **0 for every sample of the reference race's feed.** The channel is
  kept, but `race.json` carries a warning saying it must NOT be read as a
  reliable DRS state. Do not infer DRS from it.
- Retired drivers follow the same cutoff as `replay.json`, so the map trace
  and the telemetry charts go null together.

## Events, timing and warnings

- `race.json` `events` merges track status changes and race control messages
  into one time-ordered, de-duplicated list (`t_s` is session-relative
  seconds; map to the grid with the formula above). Safety car / VSC periods
  are derived from race control messages mentioning both the safety car and a
  transition ("DEPLOYED" / "IN THIS LAP" / "ENDING"); track-status rows near
  such a message are suppressed to avoid duplicates. The derivation rule is
  documented in `pipeline/events.py`.
- `race.json` `timing` carries per lap, per driver: position, lap time,
  compound, tyre life, pit in/out, and `gap_leader_s` (null when unknown —
  never fabricated).
- `race.json` `warnings` lists every skip or approximation (clipped throttle,
  all-zero DRS, events dropped outside the racing window, unavailable leader
  gaps). **A gap in the data is visible in the artifact instead of being a
  silent hole.** Frontends should surface these warnings.

## Known caveats

- **All-zero DRS** in the reference feed (see above); a real DRS state must
  come from a richer source or a later feed.
- **Clipped throttle**: 410 raw samples above 100 in the reference race;
  exact counts are in `warnings`.
- **Dropped out-of-window events**: 57 pre-race/post-race events on the
  reference race, counted in `warnings`.
- **Null gaps**: retirement cutoffs and data dropouts, by design (see null
  rules).
- `pipeline/check.py` is the verification surface: schemas, the `n_samples`
  invariant on every array, per-channel ranges, delta-chain reconstruction,
  event ordering, and agreement between `index.json`, the disk contents and
  the `tel/` file set versus the driver list.
