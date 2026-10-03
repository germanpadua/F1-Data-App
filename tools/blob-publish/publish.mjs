#!/usr/bin/env node
/**
 * Publishes the exported F1 artifacts to Vercel Blob (Phase 1, publishing).
 *
 * WHAT IS UPLOADED
 *   - index.json (always), and for every race whose season is in the
 *     published scope: race.json, replay.json and every tel/<DRIVER>.json.
 *   - The on-disk relative path IS the Blob pathname, so
 *     data/export/2026/15-azerbaijan-grand-prix/replay.json keeps the
 *     pathname "2026/15-azerbaijan-grand-prix/replay.json".
 *   - Races outside the published scope are SKIPPED AND COUNTED, never
 *     uploaded.
 *
 * SCOPE
 *   PUBLISHED_SEASONS below is a deliberate MIRROR of
 *   pipeline/scope.py (Node cannot import Python; keep them in sync).
 *   It is a publishing scope only — the Python CLI can still export any
 *   season locally, and export is never restricted by it.
 *
 * IDEMPOTENCE
 *   Re-publishing OVERWRITES the same pathnames, so a run that failed
 *   partway is repaired by running the script again: nothing is duplicated
 *   and already-correct files are simply replaced. Vercel Blob refuses to
 *   overwrite an existing pathname unless the request says so explicitly
 *   ("This blob already exists, use `allowOverwrite: true`"), and that
 *   refusal is the difference between a recoverable and an unrecoverable
 *   partial store — so the option is requested, never assumed.
 *
 * MERGED INDEX
 *   The published index.json is the UNION of what is on disk and what is
 *   already in the store: see index-merge.mjs for why, and note that this is
 *   deliberately a publisher concern, never an exporter one. When the disk
 *   already covers everything published, the file is uploaded exactly as it
 *   sits on disk; it is re-serialized only when the merge really adds races.
 *   The published copy is read through an edge that purges asynchronously, so
 *   the read is checked against the origin etag from head() and a stale copy
 *   is a HARD failure rather than a smaller index (see isStaleRead).
 *
 * RETRY-SAFE BODIES
 *   Files are read into memory and uploaded as a Buffer, never as a stream.
 *   The SDK retries a failed request (up to VERCEL_BLOB_RETRIES, default 10)
 *   with the SAME body; a stream is already consumed by the first attempt,
 *   so the retry re-sends a dead stream and dies with "Response body object
 *   should not be disturbed or locked". Measured on a real season: 2 and 3
 *   uploads out of 361 failed that way, with different files each run.
 *   Artifacts are a few MB at most (largest: replay.json, ~3.2 MB), so
 *   buffering costs nothing and turns a retry into an actual retry.
 *
 * AUTHENTICATION
 *   BLOB_READ_WRITE_TOKEN (the documented long-lived read-write token for
 *   code running outside Vercel, e.g. GitHub Actions). IF THE TOKEN IS
 *   UNSET THE SCRIPT PRINTS THAT PUBLISHING WAS SKIPPED AND EXITS 0 — a
 *   missing optional credential must never be a red build.
 *
 * USAGE
 *   node publish.mjs [--dry-run] [--root DIR] [--concurrency N]
 *     --dry-run      list what would be uploaded, totals, and out-of-scope
 *                    skips; needs no token; uploads nothing; exits 0. With a
 *                    token it also reports what the merged index.json would
 *                    contain (MERGED INDEX above).
 *     --root DIR     export root (default: <repo>/data/export)
 *     --concurrency  parallel uploads, small fixed bound (default: 4)
 *
 * EXIT CODES
 *   0 success, dry run, or token absent (skip)
 *   1 failure: missing export root/index.json, any upload failure (every
 *     failed file is named; nothing is silently swallowed), or a published
 *     index.json that cannot be read or parsed — it is never overwritten
 *     blind, because publishing a smaller index hides races still in the store
 */
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { readFile } from "node:fs/promises";
import { isStaleRead, mergeIndexes } from "./index-merge.mjs";

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(SCRIPT_DIR, "..", "..");
const DEFAULT_ROOT = path.join(REPO_ROOT, "data", "export");
const INDEX_FILENAME = "index.json";
const RACE_FILENAME = "race.json";
const REPLAY_FILENAME = "replay.json";
const TEL_DIRNAME = "tel";

// MIRROR of pipeline/scope.py — keep in sync (see SCOPE above).
const PUBLISHED_SEASONS = [2026];

const ACCESS = "public";
const DEFAULT_CONCURRENCY = 4;

function parseArgs(argv) {
  const args = { dryRun: false, root: DEFAULT_ROOT, concurrency: DEFAULT_CONCURRENCY };
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === "--dry-run") {
      args.dryRun = true;
    } else if (arg === "--root") {
      args.root = path.resolve(argv[++i] ?? "");
    } else if (arg === "--concurrency") {
      const n = Number(argv[++i]);
      if (!Number.isInteger(n) || n < 1) {
        fail(`invalid --concurrency value: ${argv[i]}`);
      }
      args.concurrency = n;
    } else {
      fail(`unknown argument: ${arg}`);
    }
  }
  return args;
}

function fail(message) {
  console.error(`ERROR: ${message}`);
  process.exit(1);
}

function isPublished(year) {
  return PUBLISHED_SEASONS.includes(year);
}

function humanBytes(n) {
  if (n >= 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(1)} MB`;
  if (n >= 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${n} B`;
}

/**
 * Walk the export root and build the upload plan.
 * Returns { files: [{ localPath, pathname, bytes }], skippedRaces: [{year, dir}] }.
 */
function planUploads(root) {
  if (!existsSync(root) || !statSync(root).isDirectory()) {
    fail(`export root does not exist or is not a directory: ${root}`);
  }
  const indexLocal = path.join(root, INDEX_FILENAME);
  if (!existsSync(indexLocal)) {
    fail(`no ${INDEX_FILENAME} under ${root} — run the export first`);
  }

  const files = [{ localPath: indexLocal, pathname: INDEX_FILENAME, bytes: statSync(indexLocal).size }];
  const skippedRaces = [];

  for (const yearName of readdirSync(root).sort()) {
    const yearDir = path.join(root, yearName);
    if (!statSync(yearDir).isDirectory() || !/^\d{4}$/.test(yearName)) continue;
    const year = Number(yearName);

    for (const raceName of readdirSync(yearDir).sort()) {
      const raceDir = path.join(yearDir, raceName);
      if (!statSync(raceDir).isDirectory()) continue;
      if (!existsSync(path.join(raceDir, RACE_FILENAME))) continue; // not an exported race

      if (!isPublished(year)) {
        skippedRaces.push({ year, dir: path.join(yearName, raceName) });
        continue;
      }

      for (const name of [RACE_FILENAME, REPLAY_FILENAME]) {
        const localPath = path.join(raceDir, name);
        if (existsSync(localPath)) {
          files.push({ localPath, pathname: path.join(yearName, raceName, name), bytes: statSync(localPath).size });
        }
      }
      const telDir = path.join(raceDir, TEL_DIRNAME);
      if (existsSync(telDir)) {
        for (const telName of readdirSync(telDir).sort()) {
          if (!telName.endsWith(".json")) continue;
          const localPath = path.join(telDir, telName);
          files.push({
            localPath,
            pathname: path.join(yearName, raceName, TEL_DIRNAME, telName),
            bytes: statSync(localPath).size,
          });
        }
      }
    }
  }
  return { files, skippedRaces };
}

function printPlan(files, skippedRaces, root) {
  console.log(`export root: ${root}`);
  console.log(`published seasons: ${PUBLISHED_SEASONS.join(", ")}`);
  console.log(`would upload ${files.length} file(s), ${humanBytes(files.reduce((t, f) => t + f.bytes, 0))}:`);
  for (const f of files) {
    console.log(`  ${f.pathname}  (${humanBytes(f.bytes)})`);
  }
  console.log(`skipped ${skippedRaces.length} race(s) outside the published scope:`);
  for (const s of skippedRaces) {
    console.log(`  ${s.dir}  (season ${s.year})`);
  }
}

/** Run `worker(i)` for i in [0, items.length) with a bounded pool. */
async function pooled(items, concurrency, worker) {
  let next = 0;
  async function runner() {
    while (next < items.length) {
      const index = next++;
      await worker(items[index], index);
    }
  }
  await Promise.all(Array.from({ length: Math.min(concurrency, items.length) }, runner));
}

async function upload(files, token, concurrency) {
  const { put } = await import("@vercel/blob");
  const failures = [];
  let uploadedBytes = 0;
  let lastUrl = null;

  await pooled(files, concurrency, async (file) => {
    try {
      // A Buffer, never a stream: the SDK retries with the same body, and a
      // stream would already be consumed (see RETRY-SAFE BODIES above). A
      // merged index.json arrives with its own body (see MERGED INDEX above).
      const body = file.body ?? (await readFile(file.localPath));
      const result = await put(file.pathname, body, {
        access: ACCESS,
        // The on-disk relative path IS the pathname, so every re-publish
        // targets pathnames that already exist. Without this the second run
        // fails on every file (see IDEMPOTENCE in the header).
        addRandomSuffix: false,
        allowOverwrite: true,
        token,
      });
      uploadedBytes += file.bytes;
      lastUrl = result.url;
      console.log(`uploaded ${file.pathname} (${humanBytes(file.bytes)})`);
    } catch (err) {
      failures.push(`${file.pathname}: ${err?.message ?? err}`);
    }
  });

  if (failures.length > 0) {
    console.error(`FAILED: ${failures.length} upload(s) failed:`);
    for (const f of failures) console.error(`  ${f}`);
    process.exit(1);
  }

  console.log(`published ${files.length} file(s), ${humanBytes(uploadedBytes)} total`);
  if (lastUrl) {
    // The returned URL is <blob-base>/<pathname>; strip the pathname to give
    // the frontend configuration a concrete base URL.
    const base = new URL(lastUrl);
    base.pathname = "/";
    console.log(`base URL: ${base.toString().replace(/\/$/, "")}`);
  }
}

/**
 * The index.json currently published, or null when the store has none yet.
 * A published index that exists but cannot be read is a HARD failure: it is
 * never replaced blind, because a smaller index silently hides races that are
 * still in the store (see MERGED INDEX in the header).
 */
async function readPublishedIndex(token) {
  const { head, BlobNotFoundError } = await import("@vercel/blob");
  let info;
  try {
    info = await head(INDEX_FILENAME, { token });
  } catch (err) {
    if (err instanceof BlobNotFoundError) return null;
    throw new Error(`could not read the published ${INDEX_FILENAME}: ${err?.message ?? err}`);
  }
  // Read the blob URL, then prove the edge is not still serving a previous
  // copy: Blob purges asynchronously (see isStaleRead).
  const res = await fetch(info.url);
  if (!res.ok) {
    throw new Error(`could not read the published ${INDEX_FILENAME}: HTTP ${res.status}`);
  }
  if (isStaleRead(res.headers.get("etag"), info.etag)) {
    throw new Error(
      `the edge is still serving a previous copy of ${INDEX_FILENAME} ` +
      `(edge etag ${res.headers.get("etag")}, origin etag ${info.etag}). Refusing to merge from a ` +
      "stale read, because a stale index would drop races that are in the store. Retry in a few seconds."
    );
  }
  try {
    return await res.json();
  } catch (err) {
    throw new Error(`the published ${INDEX_FILENAME} is not valid JSON: ${err?.message ?? err}`);
  }
}

/**
 * Merge the published index with the one on disk so publishing stays additive,
 * report what the difference is, and — outside a dry run — attach the merged
 * body to the plan. Untouched when the disk already covers the store, so the
 * uploaded bytes stay exactly the exporter's.
 */
async function prepareIndex(files, token, { dryRun }) {
  const indexFile = files.find((f) => f.pathname === INDEX_FILENAME);
  if (!indexFile) return;

  const published = await readPublishedIndex(token);
  const local = JSON.parse(await readFile(indexFile.localPath, "utf8"));
  const merged = mergeIndexes(local, published);
  const fromDisk = local.races.length;
  // Reference identity, not a count: only entries the merge brought in from the
  // store require re-serializing the document.
  const onlyInStore = merged.races.filter((race) => !local.races.includes(race));
  const verb = dryRun ? "would publish" : "publishing";

  if (onlyInStore.length === 0) {
    console.log(`index.json: ${verb} the disk's ${fromDisk} race(s) unchanged; the store has nothing extra`);
    return;
  }
  console.log(
    `index.json: ${verb} ${merged.races.length} race(s) = ${fromDisk} from disk + ` +
    `${onlyInStore.length} only in the store (a disk-only index would have DROPPED ${onlyInStore.length})`
  );
  if (dryRun) return;

  indexFile.body = Buffer.from(JSON.stringify(merged, null, 2)); // as the exporter writes it
  indexFile.bytes = indexFile.body.length;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const { files, skippedRaces } = planUploads(args.root);
  const publishedRaceCount = new Set(
    files.filter((f) => f.pathname !== INDEX_FILENAME).map((f) => f.pathname.split("/").slice(0, 2).join("/"))
  ).size;
  const token = process.env.BLOB_READ_WRITE_TOKEN;

  if (args.dryRun) {
    printPlan(files, skippedRaces, args.root);
    if (token) {
      await prepareIndex(files, token, { dryRun: true });
    } else {
      console.log(
        `index.json: the published ${INDEX_FILENAME} could NOT be consulted (no token), so this ` +
        "plan is the disk alone; races that exist only in the store are not in it"
      );
    }
    console.log(`dry run: nothing was uploaded (${publishedRaceCount} in-scope race(s) planned)`);
    return 0;
  }

  if (!token) {
    console.log(
      "BLOB_READ_WRITE_TOKEN is not set: publishing SKIPPED (exit 0). " +
      "Set the Vercel Blob read-write token to enable publishing."
    );
    return 0;
  }

  console.log(`export root: ${args.root}`);
  console.log(`published seasons: ${PUBLISHED_SEASONS.join(", ")}`);
  console.log(
    `${publishedRaceCount} in-scope race(s) planned, ` +
    `${skippedRaces.length} race(s) skipped (outside the published scope)`
  );
  await prepareIndex(files, token, { dryRun: false });
  await upload(files, token, args.concurrency);
  return 0;
}

main().catch((err) => {
  console.error(`ERROR: ${err?.stack ?? err}`);
  process.exit(1);
});
