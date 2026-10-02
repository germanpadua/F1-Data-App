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

- [ ] **T1 — Reproducible environment.** Create a `uv`-managed venv on Python 3.12 (system Python is
  3.14, too new for the pinned FastF1/pandas stack). Pin `requirements.txt` and add the missing
  `timple`, `Pillow`, `requests`. Verify every module imports cleanly inside the venv.
  Evidence: `uv venv` output + import smoke command exit code.
- [ ] **T2 — Real repository hygiene.** Track a proper `.gitignore` (`.atl/`, `cache/`,
  `circuito_prueba`, `__pycache__/`, `*.pyc`, `.venv/`). Untrack `cache/` and `circuito_prueba`
  from the index. This is a normal commit, not a history rewrite.
  Evidence: `git ls-files` no longer lists cache/ or circuito_prueba.
- [ ] **T3 — Current-season support.** Replace the hardcoded season list with a dynamic range that
  includes 2025 and 2026, derived from FastF1's schedule instead of a literal. Make
  `driver_dash_styles` degrade cleanly for seasons it does not cover (remove the hand-maintained
  2024-only assumption).
  Evidence: a real 2026 session loads and produces a chart without a literal-year guard.
- [ ] **T4 — Live championship data source.** Replace the deprecated `fastf1.ergast.Ergast()` path in
  `grafico_evolucion_campeonato()` with a working source (jolpica-f1 Ergast-compatible endpoint or
  FastF1's native results backend), preserving the three existing figures (drivers, teams, heatmap).
  Evidence: the function returns three populated figures for a 2026 season.
- [ ] **T5 — Breaking-bug fixes.** `st.cache_data` → `st.cache_resource` for the `Session`-returning
  loader (T5a); single load path instead of double `session.load()` (T5b); add a `User-Agent` to the
  Nominatim call (T5c); remove the debug `print` and fix the shadowed/short-circuited loops (T5d);
  redirect generated circuit maps to a cache directory so runtime does not dirty the worktree (T5e).
  Evidence: app runs unchanged behaviorally; no traceback; worktree stays clean after a run.
- [ ] **T6 — Operator documentation.** Write a real `README.md` (setup with `uv`, run locally, data
  model, known limitations including the Vercel analysis) and add `.streamlit/config.toml` with a
  defined theme baseline.
  Evidence: a fresh reader can go from clone to running app using only the README.
- [ ] **T7 — [BLOCKED — REQUIRES EXPLICIT USER APPROVAL] Git history purge.** Rewrite history to
  remove `cache/` and `circuito_prueba` blobs (`git-filter-repo`), reducing `.git` from 733 MB.
  This is destructive and requires a coordinated force push. Do not start without an explicit,
  in-session go-ahead from the user.
  Evidence: `du -sh .git` after purge; `git log --oneline` sanity check.

## Dependency order

T1 → (T2, T3) → (T4, T5) → T6 → T7 (approval-gated).
T4 and T5 both touch `modules/plotting.py`, so they must be done sequentially, never in parallel.

## Work-unit commit log

Work-unit commits happen on the feature branch; record the commit identity here as evidence.

| Task | Commit | Message |
|------|--------|---------|
| — | — | (none yet) |
