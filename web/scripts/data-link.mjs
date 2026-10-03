// Makes the real exported artifacts reachable same-origin during development
// and `vite preview` by copying them to web/public/data. (A symlink was tried
// first, but Vite's static middleware does not follow symlinked directories
// for nested paths, so a plain copy is the reliable "a copy or a symlink"
// option from the task.) The identical code path (VITE_DATA_BASE_URL = "" ->
// same-origin) then serves both local development and production, where the
// base points at Vercel Blob. The copy is gitignored via web/.gitignore and
// never committed. Run again after re-exporting a race to refresh it.
import { cpSync, existsSync, lstatSync, mkdirSync, rmSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const webRoot = resolve(here, "..");
const copyPath = join(webRoot, "public", "data");
const target = resolve(webRoot, "..", "data", "export");

if (!existsSync(target)) {
  console.error(
    `No artifacts at ${target}. Export a race first:\n` +
      `  .venv/bin/python -m pipeline.export --year 2026 --round 15 --session R`,
  );
  process.exit(1);
}

mkdirSync(join(webRoot, "public"), { recursive: true });

// A stale symlink from an earlier version of this script is replaced (the
// symlink itself is removed, never its target).
if (lstatSafe(copyPath)?.isSymbolicLink()) rmSync(copyPath);

cpSync(target, copyPath, { recursive: true, force: true });
console.log(`public/data <- ${target} (copied; run again after re-exporting)`);

function lstatSafe(p) {
  try {
    return lstatSync(p);
  } catch {
    return null;
  }
}
