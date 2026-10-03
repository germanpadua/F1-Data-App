# Feature: Phase 2 — Publish pipeline hardening

**Status**: in progress
**Predecessor**: `odd/tasks/phase-1-export-pipeline.md` (complete), `d8aea1e` (Phase 2 frontend slice)
**Created**: 2026-10-03
**Branch**: `feat/phase-0-modernization`

## Why this exists

Phase 2 deploys the static frontend to Vercel and serves the Phase 1 artifacts from Vercel Blob.
The deploy and the `VITE_DATA_BASE_URL` wiring are done and verified; the publishing path turned out
to have defects that only a real upload could reveal. This feature tracks those defects to closure
instead of leaving them as folklore.

## Verified state of the deployment (evidence)

- Deployed bundle inlines `VITE_DATA_BASE_URL = https://0a04umtkpigkvxmf.public.blob.vercel-storage.com`
  (read back from `https://f1-data-app.vercel.app/assets/index-CO6qk4oS.js`).
- `GET <blob-base>/index.json` -> `200`, 15 races, `access-control-allow-origin: *`,
  `content-type: application/json`. The app's plain `GET` triggers no preflight.
- Every race serves `race.json` and `replay.json` = `200`. The frontend fetches only those plus
  `index.json` (`web/src/data.ts`), so the app renders from Blob today.
- `pipeline.check --root data/export` **FAILS**: `tel/VER gear` (r9 British) and `tel/NOR gear`
  (r12 Dutch) carry values above 8 (up to 43). Pre-existing in the committed checker
  (`GEAR_RANGE = (0, 8)`, `pipeline/check.py:35`), not caused by the uncommitted local changes.
- `node tools/blob-publish/publish.mjs` -> **exit 1**, 359/361 files, 136.3 MB, 1m38s. Two
  telemetry files failed with `Response body object should not be disturbed or locked`.

## Contract decision at the gate (user)

The user chose to publish despite the failing self-check, on the record that the affected channel is
`tel/*.json`, which the frontend does not read yet, and that the fix will land by re-publishing and
overwriting. That choice is why `P2.2` (overwrite) must land before any re-publish: without it the
recovery path itself is impossible.

## Tasks

| # | Task | Status |
|---|------|--------|
| P2.1 | Publish the 2026 season to Blob and verify the frontend can read it | done |
| P2.2 | Add `allowOverwrite: true` to the publisher and document the idempotence contract | done |
| P2.3 | Re-publish to close the missing telemetry files and prove a second run is idempotent | done |
| P2.6 | Fix the upload failure `Response body object should not be disturbed or locked` (non-replayable body on SDK retry) | done |
| P2.4 | Reproduce and fix the `gear > 8` defect (r9 VER, r12 NOR): producer repair or documented contract widening | done by `c0a97b0` (parallel session): impossible gear is nulled with a warning |
| P2.5 | Verify and fix the CI index risk: `rebuild_index` + a cold `f1-export-2026-*` cache can shrink the published `index.json` to one race | pending — and the reason NOT to dispatch the workflow yet |

## Verified after the fixes (evidence)

Two consecutive full publishes finished clean: `exit 0`, **361/361 files, 136.3 MiB, 1m38s** each,
and the script printed `base URL: https://0a04umtkpigkvxmf.public.blob.vercel-storage.com` (an
independent confirmation of the configured `VITE_DATA_BASE_URL`). Before the two fixes the same
command exited 1 on every run (2, then 3 failures of 361) and never completed a store.

- Store inventory via the SDK `list()`: **361 blobs, 136.3 MiB**, `index.json` 1 + `race.json` 15 +
  `replay.json` 15 + `tel/*.json` 330, zero stray pathnames.
- Independent per-file HTTP check of all 361 planned pathnames (derived from `data/export`, not from
  the publisher): **361 x `200`, 0 failures**.
- **Store == disk, byte for byte.** A Vercel Blob etag is the md5 of the file content (confirmed on
  `index.json`), so all 360 race/telemetry files were hashed locally and compared against the etag
  the public CDN serves: **360/360 identical**, plus `index.json`. The published season therefore
  matches the post-`c0a97b0` exporter, gear nulls included.
- Second run over existing pathnames succeeds, which is the property P2.2 exists for.

## Concurrent work (not this feature)

`c0a97b0` ("stop trusting circuit info and the fastest lap, and null impossible gear") landed from a
parallel session while this one was publishing. It closes P2.4 at the source: the raw feed carries
impossible `nGear` values up to 63 in rounds 9 and 12, they are now exported as `null` with a
declared warning, `GEAR_RANGE` stays strict at `(0, 8)`, and `pipeline.check --root data/export` now
exits with `OK: all artifacts under data/export satisfy the contract`. That commit also made circuit
metadata optional (round 14) and walks timed laps to find a usable position trace (round 6), which
is why the season is complete at all.

**Not committed yet**: `tools/blob-publish/publish.mjs` (P2.2 + P2.6) and this document are the only
files this feature changed, and they are still in the working tree. No commit was made.

### P2.2 notes

Measured against the real store with a throwaway pathname:

```
put #1: OK
put #2: THREW -> Vercel Blob: This blob already exists, use `allowOverwrite: true` ...
put #3 (allowOverwrite:true): OK
```

So Vercel Blob rejects an existing pathname by default and `publish.mjs` never passed the option.
The workflow comment at `.github/workflows/export-latest-round.yml:163` ("a pathname already in Blob
is overwritten") is only true **after** this change.

### P2.6 notes (root cause, not a workaround)

The SDK wraps the request in `async-retry` with `VERCEL_BLOB_RETRIES` (default 10) and retries on
`unknown_error`, `service_unavailable` and `internal_server_error` (`@vercel/blob`
`dist/chunk-YYMLUMXS.js:751-820`). Each retry re-sends **the same `init.body`**, and `publish.mjs`
was passing `createReadStream(file.localPath)` — already consumed by the first attempt. Re-sending a
dead stream is exactly what raises *"Response body object should not be disturbed or locked"*.
That is why the failures hit different files on every run: the trigger is an upstream retry, not the
file. The fix uploads a `Buffer` (`node:fs/promises`), which survives retries; artifacts are at most
~3.2 MB, and the whole root is 136 MB, so buffering costs nothing.

A first attempt at the fix used `fs.readFile` without a callback and failed all 361 uploads with
`The "cb" argument must be of type function` — the publisher reported every failure and exited 1, so
the mistake was loud and never silent. The read is now `node:fs/promises`.

Raw values are not "a wrong gear number": r9 VER has 9, 13, 19, 23, 29, 34, 38, 43 and r12 NOR has
9..40. 43 is not a gear at all, so the question is whether the FastF1 feed carries garbage samples or
the export misaligns the channel. Because the CI self-check runs **before** the publish step with no
`continue-on-error`, the workflow cannot publish any round whose telemetry trips this rule.
