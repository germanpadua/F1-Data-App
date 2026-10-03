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
 * AUTHENTICATION
 *   BLOB_READ_WRITE_TOKEN (the documented long-lived read-write token for
 *   code running outside Vercel, e.g. GitHub Actions). IF THE TOKEN IS
 *   UNSET THE SCRIPT PRINTS THAT PUBLISHING WAS SKIPPED AND EXITS 0 — a
 *   missing optional credential must never be a red build.
 *
 * USAGE
 *   node publish.mjs [--dry-run] [--root DIR] [--concurrency N]
 *     --dry-run      list what would be uploaded, totals, and out-of-scope
 *                    skips; needs no token; uploads nothing; exits 0.
 *     --root DIR     export root (default: <repo>/data/export)
 *     --concurrency  parallel uploads, small fixed bound (default: 4)
 *
 * EXIT CODES
 *   0 success, dry run, or token absent (skip)
 *   1 failure: missing export root/index.json, or any upload failure
 *     (every failed file is named; nothing is silently swallowed)
 */
import { createReadStream } from "node:fs";
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

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
      const result = await put(file.pathname, createReadStream(file.localPath), {
        access: ACCESS,
        addRandomSuffix: false,
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

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const { files, skippedRaces } = planUploads(args.root);
  const publishedRaceCount = new Set(
    files.filter((f) => f.pathname !== INDEX_FILENAME).map((f) => f.pathname.split("/").slice(0, 2).join("/"))
  ).size;

  if (args.dryRun) {
    printPlan(files, skippedRaces, args.root);
    console.log(`dry run: nothing was uploaded (${publishedRaceCount} in-scope race(s) planned)`);
    return 0;
  }

  const token = process.env.BLOB_READ_WRITE_TOKEN;
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
  await upload(files, token, args.concurrency);
  return 0;
}

main().catch((err) => {
  console.error(`ERROR: ${err?.stack ?? err}`);
  process.exit(1);
});
