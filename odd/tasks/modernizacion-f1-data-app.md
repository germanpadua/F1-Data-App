# Feature: Modernizacion F1-Data-App (Phase 0 — Hygiene, Data Currency, Reproducibility)

**Status**: in progress
**Authorized route**: C — phased (Phase 0 hygiene/data → Phase 1 JSON pipeline → Phase 2 frontend decision)
**Season scope (user decision)**: 2025 + 2026
**Created**: 2026-10-03

## Problem statement

The app is a Streamlit + FastF1 analysis tool last touched with season data up to 2024.
Before any UI work (Vercel/Next.js) can be meaningfully decided, three things must be true:

1. The repository must be clonable and maintainable (git is 733 MB due to committed caches).
2. A fresh environment must be able to install and run the app from `requirements.txt` alone.
3. The app must work against the current season (2026) and a live data source.

Phase 0 deliberately excludes the UI/presentation rewrite. That is Phase 1/2 territory.
Guard: Phase 0 must not grow into a full refactor. Scope is limited to the seven tasks below.

## Non-goals for Phase 0

- Rewriting the presentation layer (matplotlib/plotly → web charts).
- Introducing `pipeline/` JSON artifacts (that is Phase 1).
- Removing the module-level global coupling in `main_app.py` (deferred to Phase 1, when the data
  layer changes anyway).
- Adding tests/CI beyond what is needed to verify the tasks below.

## Findings that motivate the tasks (evidence)

| # | Finding | Evidence |
|---|---------|----------|
| F1 | `.git` is 733 MB; `cache/` (22 tracked files, ~140 MB of regenerable FastF1 pickles) and `circuito_prueba` (94 MB serialized `Lap` object, debug leftover) are tracked. History also holds cache blobs from 2020-2023 up to 92 MB. | `du -sh .git`; `git ls-files \| grep -c '^cache/'`; `git rev-list --objects --all \| ...` |
| F2 | `.gitignore` exists but is untracked and only ignores `.atl/`. | `git ls-files \| grep gitignore` (empty); `git status --short` shows `?? .gitignore` |
| F3 | `requirements.txt` omits `timple` (imported by `plotting.py`), `Pillow` (PIL) and `requests`. | `requirements.txt` content vs imports in `modules/plotting.py`, `modules/data_loading.py` |
| F4 | Seasons are hardcoded `[2020..2024]`; `driver_dash_styles` only covers 2023/2024. | `main_app.py`, `modules/plotting.py` |
| F5 | `grafico_evolucion_campeonato()` reads from `fastf1.ergast.Ergast()`; Ergast was deprecated and shut down at the end of 2024. Successor: jolpica-f1. | `modules/plotting.py`; FastF1 changelog + jolpica docs |
| F6 | `@st.cache_data` wraps a function returning a telemetry-loaded FastF1 `Session`; `cache_data` pickles the return value. | `modules/data_loading.py` |
| F7 | Session is loaded twice with different flags. | `modules/data_loading.py` (`telemetry=True, weather=False`) then `main_app.py` (`laps=True, telemetry=True, weather=True`) |
| F8 | Nominatim is called without a `User-Agent`, violating its usage policy. | `main_app.py` `obtener_coordenadas_osm()` |
| F9 | `print(absmax)` debug leftover; `for years in range(...)` shadows `year`; mangled `if funciona: break` flow. | `modules/plotting.py`, `main_app.py` |
| F10 | `mostrar_mapa_circuito()` writes generated PNGs back into `data/circuit_image/`, dirtying the worktree at runtime. | `modules/plotting.py` (`plt.savefig('data/circuit_image/'+name + '.png')`) |
| F11 | No README content, no `.streamlit/config.toml`, no branch protection, no CI. | repo root listing |

## Tasks

- [x] **T1 — Reproducible environment.** DONE (commit `b63dfcf`). `uv venv --python 3.12 .venv`
  resolved CPython 3.12.14. Pinned `requirements.txt` to 14 direct dependencies and added the three
  that were missing. Verified: fastf1 3.8.3, streamlit 1.65.0, plotly 7.1.0, pandas 2.3.3,
  matplotlib 3.11.2, numpy 2.5.3, scipy 1.18.1; all four modules import cleanly inside the venv.
- [x] **T2 — Real repository hygiene.** DONE (commit `32fe492`). `.gitignore` now covers `.atl/`,
  `__pycache__/`, `*.py[cod]`, `.venv/`, `venv/`, `cache/`, `circuito_prueba`. `cache/` (22 files)
  and `circuito_prueba` untracked via `git rm --cached`; files stay on disk. Verified: 0 remaining
  index entries matching `^cache/|^circuito_prueba`.
- [x] **T3 — Current-season support.** DONE (commit `eea7eda`). New `get_selectable_seasons()` in
  `modules/utils.py` returns 2018..current year (9 seasons, includes 2025 and 2026). `driver_dash_styles`
  documented as a cosmetic override whose unknown-season fallback is already handled. Deprecated
  `misc_mpl_mods` removed. Verified: seasons 2018-2026, dash fallback returns `'solid'` for 2026.
- [x] **T5 — Breaking-bug fixes.** DONE (commit `eea7eda`, same work unit: the changes interleave in
  the same files). `st.cache_data` → `st.cache_resource`; single load in the loader; Nominatim
  `User-Agent` + timeout; debug `print` removed; shadowed loop variable and the broken `funciona`
  control flow fixed; generated maps written to `cache/circuit_maps/` and looked up there so they are
  still reused. Verified: real 2026 Qualifying load returned 373 laps, imports clean with no
  `FutureWarning`.
- [x] **T4 — Live championship data source.** DONE (commit `fdb3f8a`). **Corrected finding:** the
  original task text was wrong about the cause. `fastf1/ergast/interface.py` in FastF1 3.8.3 already
  sets `BASE_URL = 'https://api.jolpi.ca/ergast/f1'`, so FastF1 already talks to jolpica and there
  was no URL to migrate. The real defects were the request fan-out and the missing rate-limit
  handling: `get_race_results` plus `get_sprint_results` per round is about 48 calls per season and
  tripped **HTTP 429 Too Many Requests** after ~24 requests, raising an uncaught exception. jolpica
  also returns empty `content` for rounds that have not run yet, and `content[0]` then raised
  `IndexError`.
  Rebuilt from **cumulative standings**, one call per round, behind `fetch_with_retry`. Verified on
  the live 2026 season: 15 completed rounds, 23 drivers, 11 constructors, three populated figures,
  per-round point totals matching the API exactly, no false warning from the new no-points guard.
  Two defects found while reviewing the delegated work and fixed by the parent before committing:
  a `RETRY_FAILED` on driver standings truncated the whole season (it now skips the round and the
  search is bounded by the schedule length), and `main_app.py` required all three figures to be
  non-None, so a missing teams table blanked the entire section.
  Also corrected a real pre-existing bug: the fuzzy constructor rename collapsed `Alpine F1 Team`,
  `Cadillac F1 Team` and `RB F1 Team` all into `Haas F1 Team`, merging three teams' points. 2026 now
  shows 11 distinct teams instead of 8.
  **New known risk, now guarded:** jolpica can transiently serve a completed round with the previous
  round's cumulative table, which shifts that round's points one round later. Observed once on round
  12 (Dutch GP) and gone on the next run. The app now warns when a completed round reports zero
  total points instead of rendering it silently.
- [x] **T6 — Operator documentation.** DONE (commit `24dea33`). Real `README.md` covering setup
  (`uv` + Python 3.12), running, the committed-versus-regenerable path table, the real data sources,
  the known limitations, and an explicit answer to the Vercel question. Plus `.streamlit/config.toml`.
  Verified: TOML parses, and `streamlit run main_app.py` boots and answers
  `GET /_stcore/health` with HTTP 200 `ok`.
- [ ] **T7 — Git history purge.** AUTHORIZED by the user on 2026-10-03 ("purge it if you can").
  Rewrite history with `git-filter-repo` to drop every `cache/` and `circuito_prueba` blob,
  reducing `.git` from 733 MB, then force push. A backup bundle is written outside the repository
  before the rewrite. Evidence: `du -sh .git` after purge; `git log --oneline` sanity check.
- [x] **T8 — Close the three native-review findings.** DONE (commit `d1ac7a0`). See the review record
  below. Verified: the 2026 per-round totals still match the API exactly, the all-rounds-fail path
  returns `(None, None, None)` without raising, and an injected empty round 8 no longer truncates
  the season.

## Deferred to Phase 1 / Phase 2: race replay (user request, 2026-10-03)

The user wants a race replay section modelled on the one already built in their own
`telemetry-sentinel` project. Recorded here because it constrains the Phase 1 export schema, and
retrofitting a data contract after the fact is the expensive mistake to avoid.

What `telemetry-sentinel` already proves (read-only inspection of
`/home/germanpadua/proyectos/telemetry-sentinel/web`):

- Stack: Vite + React + TypeScript, deployed through `web/vercel.json`
  (`buildCommand: npm run build`, `outputDirectory: dist`, `cleanUrls: true`). Static, no server.
- Render loop: `web/src/logic.ts` (224 lines) owns the data clock and the visibility rule;
  `web/src/Replay.tsx` (564 lines) draws cars on the canvas track from a decimated trace.
- Export contract: a Python script (`src/telemetry_sentinel/export_demo.py`, 461 lines) writes one
  JSON per session. Schema `telemetry-sentinel-demo-export/1` carries `cars[]` with parallel
  `t_s` / `speed_kmh` / `x_m` / `y_m` arrays, `track[]` (polyline), `circuit` (rotation + corner
  labels), `drivers` (abbreviation / team / color) and `decimation_step_s`.
- Measured weight: ~5.0-7.8 MB per race at a 2.0 s decimation step, 20 cars, ~9444 samples each.

Consequences for this project:

1. A replay is not possible in Streamlit at comparable quality. This settles Phase 2 in favour of
   the web frontend; Streamlit cannot animate a canvas at 60 fps.
2. Phase 1's exporter must emit positional telemetry and track geometry, not only aggregated charts.
3. Weight is the real design problem, not rendering: 48 races (2025+2026) at ~5 MB each is ~240 MB
   of JSON. The Phase 1 design must therefore answer: decimation step, delta/typed-array encoding
   (Int16 deltas over 4 parallel float arrays should cut this by 3-5x), per-race lazy loading, and
   whether large payloads belong in the repo at all or in object storage (Vercel Blob / R2).
4. The `web/` app from `telemetry-sentinel` is a reusable skeleton (clock, canvas, Vercel config,
   `results.json` pattern), but its domain model is alert episodes. Reusing it here means replacing
   the episode/alert semantics with race-analysis semantics. That is Phase 2 work.

### Replay scope — DECIDED by the user (2026-10-03)

The user selected **all four layers**, cumulative:

1. **Base replay** — 20 cars on the track map, play / pause / scrub / playback speed.
2. **Timing tower + tyre strategy** — position and gap per car, compound per stint, pit stops, all
   following the data clock.
3. **Synced driver telemetry** — the selected driver's speed / throttle / brake / RPM / gear / DRS
   tracking the cursor (FullThrottle-style).
4. **Timeline events** — flags, safety car, VSC, pit entries marked on the timeline.

This is the full-fat version, so the Phase 1 export contract must carry four separate payloads with
very different cost profiles:

| Payload | Shape | Cost | Loading strategy |
|---|---|---|---|
| Replay traces | 20 cars x (t, x, y, speed) | ~5 MB/race raw | decimated, delta-encoded, one file per race, lazy |
| Timing tower + strategy | per lap x per car (position, gap, compound, tyre life, pit) | tens of KB | inline in the race manifest |
| Driver telemetry channels | per car x (throttle, brake, rpm, gear, drs) | ~2x the replay payload | one file per race **per driver**, lazy, only on selection |
| Timeline events | ~1.5k rows | tens of KB | inline in the race manifest |

Design consequence: the per-race manifest stays small and cheap so the index page is fast, and the
heavy channels are fetched on demand. Splitting the telemetry channels per driver (rather than
per race) is what keeps layer 3 affordable; a single per-race file with all channels for all drivers
is the variant to avoid.

Under the full scope, the Streamlit path is definitively not viable for layers 1-3. Phase 2 is the
web frontend, reusing the `telemetry-sentinel` `web/` skeleton.

## Native review record

The phase-0 candidate went through the native review lifecycle on 2026-10-03.

| Field | Value |
|---|---|
| Lineage | `review-0456e121dbf4dd72` |
| Target identity | `sha256:7cfd3fbd8bee3ecb8c843cd9d3c20db883c9d4db054f2dc0e5b4e402670d6306` |
| Base tree / candidate tree | `81300c3b48992c7d34d69076ae2fe9f33add213c` / `89dbdb88aeedf17b4a5dc0a6b218b69e9c1a0a58` |
| Frozen revision (approved) | `sha256:548408359bfd443e17373240154d73d81c97801dabb61ee4f847ae76be3f2204` |
| Tier / lenses | medium / `review-reliability` |
| Changed lines / correction budget | 776 / 200 |
| Verdict | approved; no correction transition was offered |
| Acknowledgement | completed, authority burned (`gentle-ai.review-acknowledged/v1`) |
| Delivery | ordinary repository policy — the receipt never authorizes delivery |

The consent envelope was resolved upstream by the interactive Pi host, not by the agent, and no
consent was ever fabricated from model prose. START returned ambiguous output (`state: reviewing`
with `operation: answer-consent` but no `consentBinding` and no `consent/v3` envelope), so exactly
one target-scoped STATUS was issued to resolve the transition, per contract.

### Advisory findings and their follow-up

All three were non-blocking: none opened a correction, none reopened the review, and none is a
reason to re-run review on that candidate. T8 is a new candidate and was reviewed separately.

| Finding | Location | Severity | Follow-up |
|---|---|---|---|
| `R3-retry-swallows-errors` | `modules/utils.py:30-46` | SUGGESTION | T8: `fetch_with_retry` logs every failed attempt with attempt number, optional `label`, exception type and message |
| `R3-standings-break-truncates` | `modules/plotting.py:677-678` | WARNING | T8: empty standings for a round whose race has already run is a transient source gap, not end of season; with no schedule, two consecutive empty rounds are required to stop |
| `R3-standings-empty-pivot` | `modules/plotting.py:712-714` | WARNING | T8: the driver pivot and heatmap are skipped when there are no driver rows, and the teams figure is still returned alone |

## Dependency order

T1 → (T2, T3) → (T4, T5) → T6 → T7 (approval-gated).
T4 and T5 both touch `modules/plotting.py`, so they must be done sequentially, never in parallel.

## Work-unit commit log

Work-unit commits happen on the feature branch; record the commit identity here as evidence.

| Task | Commit | Message |
|------|--------|---------|
| bookkeeping | `2cfa56f` | `chore(odd): track phase-0 modernization feature document` |
| T2 | `32fe492` | `chore(repo): add real .gitignore and untrack FastF1 cache and debug dump` |
| T1 | `b63dfcf` | `chore(deps): pin direct dependencies and add missing timple, pillow, requests` |
| T3 + T5 | `eea7eda` | `fix(app): support 2025-2026 seasons and fix session cache, geocoding and map output` |
| T4 | `fdb3f8a` | `feat(championship): rebuild the standings charts from cumulative standings` |
| T6 | `24dea33` | `docs: add a real README and a Streamlit theme baseline` |
| bookkeeping | `f6653ae` | `chore(odd): close phase-0 tasks T3-T6 with commit evidence` |
| T8 | `d1ac7a0` | `fix(championship): close the three reliability findings from the native review` |

Local git identity was unset in this clone, so `user.name` / `user.email` were set **repo-locally**
(not globally) to match the existing history (`germanpadua <german8adaba@gmail.com>`).
