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
| P2.5 | Verify and fix the CI index risk: `rebuild_index` + a cold `f1-export-2026-*` cache can shrink the published `index.json` to one race | done: the publisher merges the published index (index-merge.mjs) and refuses a stale read |
| P2.7 | Artifacts are overwritten in place while Blob serves `cache-control: public, max-age=2592000`, so a returning visitor can read a 30-day-old copy of a re-exported race | pending (finding, not yet fixed) |
| P2.8 | The daily CI export cannot run on a GitHub-hosted runner: the F1 CDN answers `403 Forbidden` to every session stream | pending — an infrastructure decision, not a code fix |
| P2.9 | Decide whether `.github/workflows/diagnose-f1-egress.yml` (temporary) stays as a troubleshooting tool or is deleted | pending |

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

**Committed**: `9ff5ead` carries P2.2 and P2.6 (`tools/blob-publish/publish.mjs`). P2.5 is the second
commit and adds `tools/blob-publish/index-merge.mjs`, its `node --test` suite and the
`tools/blob-publish/package.json` test script.

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

### P2.5 notes (the CI could shrink the published index)

The mechanism: `rebuild_index` writes `index.json` from the race directories on disk, and in CI those
come from the `f1-export-2026-*` cache — cold on the first run, evictable later. A one-race index was
then uploaded over the published one, and the fourteen races still in the store vanished from the
app.

The fix is in the PUBLISHER, not the exporter, and that placement is the whole point: the exporter
must keep writing an index that agrees with the directories actually on disk (`pipeline/check.py`
asserts exactly that), so it must never be taught about races that exist only in the store. The
publisher is what knows the published store, so `index-merge.mjs` unions the two by `(year, round)` —
the same key `rebuild_index` sorts by — with the local entry winning for a round that exists in both.
The file is uploaded byte-for-byte as it sits on disk whenever the disk already covers the store; it
is re-serialized only when the merge actually adds races. A published index that cannot be read or
parsed is a hard failure, never a silent overwrite.

Verified with a fixture that reproduces the CI exactly — `/tmp/cold-cache` holding only round 15:

- dry run: `index.json: would publish 15 race(s) = 1 from disk + 14 only in the store (a disk-only
  index would have DROPPED 14)`
- real run: `exit 0`, 25 files, and the published index still lists **rounds 1..15**, byte-identical to
  `data/export/index.json` (same md5), so the merge is lossless
- the full-root run reports `the disk's 15 race(s) unchanged; the store has nothing extra` and does
  not re-serialize anything
- 11 unit tests (`npm test --prefix tools/blob-publish`) cover the cold-cache union, the renamed
  event, multi-year ordering, duplicate rounds, non-mutation, and every malformed-input path

**A residual risk found while testing, and guarded.** Blob purges its edge ASYNCHRONOUSLY: right after
an overwrite, a read can still return the previous document (measured headers: `x-vercel-cache: HIT`,
`age: 22`, and an etag from before the write while `head()` reported the new origin etag;
`?bust=` does NOT bypass it). Merging from such a read would drop store-only races — the very failure
P2.5 fixes, re-entering by another door. `readPublishedIndex` therefore compares the edge response's
etag against the origin etag from `head()` and fails loudly on a mismatch
(`isStaleRead`), because a stale read is not distinguishable from a real shrink otherwise. That guard
path is unit-tested, but its trigger was not reproduced deterministically: the evidence that the two
etags disagree while stale comes from the measured incident below.

**Incident, on the record.** To prove the "never overwrite blind" property, the published index was
deliberately corrupted twice (`{esto no es json` and `{}`). The publisher refused both times — `exit
1`, zero uploads, clear error — and that is the property that matters. It also proved the async purge
the hard way: for roughly twenty seconds after the restore the edge kept serving the corrupted copy
before it went fresh. The index was restored from `data/export/index.json` and re-verified by md5 and
by race count. Nothing else in the store was touched, and the deployed app's read path was confirmed
(`index.json`, `race.json`, `replay.json` all 200) after the restore.

### P2.8 notes (measured on a runner, not guessed)

The workflow's first-ever run failed in 15 s, before any export: `NotADirectoryError` from
`fastf1.Cache.enable_cache`, because `actions/cache` does not create its path on a miss and git cannot
track the empty `cache/` directory (fixed: an explicit `mkdir -p cache` step, plus the same fix in the
diagnostic workflow, which hit the identical trap).

The second run got past that and died on the data, three seconds in: FastF1 loaded the session object
and every channel failed (`Failed to load session info data!`, `Car telemetry data is unavailable!`,
`DataNotLoadedError`). The cause is environmental and now measured rather than assumed — a throwaway
diagnostic workflow printed the raw HTTP result, locally and on the runner:

| URL | local | GitHub-hosted runner |
|---|---|---|
| `.../2026-09-26_Azerbaijan_Grand_Prix/2026-09-26_Race/SessionInfo.jsonStream` | `200`, `server=AmazonS3` | **`403 Forbidden`**, `server=CloudFront` |
| `.../2026-09-26_Azerbaijan_Grand_Prix/2026-09-26_Race/TimingData.jsonStream` | `200`, `server=AmazonS3` | **`403 Forbidden`**, `server=CloudFront` |
| `.../2025-08-31_Dutch_Grand_Prix/2025-08-31_Race/SessionInfo.jsonStream` (2025) | `200` | **`403 Forbidden`**, `server=CloudFront` |
| `fastf1.get_event_schedule(2026)` | 23 rows | 23 rows (works) |

The block is not session-specific (2025 is blocked too), not a version problem (`requirements.txt`
pins `fastf1==3.8.3`, the same version locally) and not a cache problem. The schedule fetch works
because it reaches a different endpoint, which is why the `discover` step passes and everything after
it fails.

CONSEQUENCE: the export+publish workflow cannot succeed on a GitHub-hosted runner, by construction.
The options, none of them a code change in this repository alone: run the export where the egress is
allowed (self-hosted runner, a VPS, or a machine with a residential IP), route FastF1's requests
through a proxy whose IP is allowed (`requests` honours `HTTPS_PROXY`, so the export step could take
one from a secret), or drop the CI export and keep the repository's export as a local/manual step —
which the publisher's idempotence and index merge now make safe to re-run at any time.

Every artifact pathname is overwritten in place on a re-export while Blob serves
`cache-control: public, max-age=2592000`. A browser that cached `replay.json` keeps serving that
32-day-old copy to its user, so a re-export is invisible to returning visitors until the TTL expires.
The edge has the same exposure, mitigated only by the (asynchronous, hence not instant) purge. The
clean fix is content-addressed pathnames or a version carried by `index.json`; the cheap mitigation is
a much shorter `cacheControlMaxAge` for these pathnames.

Raw values are not "a wrong gear number": r9 VER has 9, 13, 19, 23, 29, 34, 38, 43 and r12 NOR has
9..40. 43 is not a gear at all, so the question is whether the FastF1 feed carries garbage samples or
the export misaligns the channel. Because the CI self-check runs **before** the publish step with no
`continue-on-error`, the workflow cannot publish any round whose telemetry trips this rule.
