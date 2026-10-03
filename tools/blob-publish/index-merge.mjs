/**
 * The published index.json describes the PUBLISHED STORE, not the local disk.
 *
 * WHY THIS EXISTS
 *   The exporter rebuilds index.json from the race directories it finds under
 *   the export root (pipeline/export.py: rebuild_index). In CI that root is
 *   restored from the `f1-export-2026-*` cache, which is cold on the first run
 *   and can be evicted. A cold cache therefore produced an index listing ONE
 *   race, and the publisher uploaded it on top of the published one: the other
 *   fourteen races kept their blobs in the store but vanished from the index,
 *   so the deployed app silently fell back to a single race.
 *
 *   That is why this merge lives in the publisher and NOT in rebuild_index:
 *   index.json must keep agreeing with the directories actually on disk
 *   (pipeline/check.py asserts exactly that), so the exporter must never be
 *   taught about races that exist only in the store.
 *
 * CONTRACT
 *   - The merged document keeps the local document's top-level fields
 *     (schema, generated_at, step_s): the local exporter owns the schema.
 *   - A race's identity is (year, round), the same key rebuild_index sorts by,
 *     so a locally exported round REPLACES the published entry for that round
 *     instead of duplicating it.
 *   - Entries that exist only in the store are carried over VERBATIM, by
 *     reference: their blobs are already published, so their metadata and
 *     `bytes` still describe the store.
 *   - Races are sorted by (year, round), like the exporter's index.
 *   - Inputs are never mutated.
 *   - Anything malformed throws. This module exists to stop a silent shrink,
 *     so guessing at a broken index would defeat its only purpose.
 *
 * LIMIT
 *   Publishing is additive. There is no deletion path: pruning a race from the
 *   store requires pruning it from the published index by hand.
 */

/** Race identity in the index: (year, round), what rebuild_index sorts by. */
export function raceKey(race) {
  return `${race.year}-${race.round}`;
}

/**
 * True when an edge response's etag disagrees with the origin etag from
 * `head()`. Vercel Blob purges its edge asynchronously: a read taken moments
 * after a pathname is overwritten can still return the PREVIOUS document
 * (measured: the edge served a stale index.json with `x-vercel-cache: HIT`
 * and an etag from before the write; a `?bust=` query did NOT bypass it).
 * Merging from such a read would drop races that are in the store, which is
 * precisely the failure this module exists to prevent, so the caller treats a
 * stale read as fatal instead of merging from it.
 *
 * An absent etag on either side means "cannot tell", never "stale".
 */
export function isStaleRead(responseEtag, originEtag) {
  const normalize = (value) =>
    typeof value === "string" ? value.replace(/^W\//, "").replaceAll('"', "") : "";
  const edge = normalize(responseEtag);
  const origin = normalize(originEtag);
  return edge !== "" && origin !== "" && edge !== origin;
}

function assertRaces(value, what) {
  if (value == null || !Array.isArray(value.races)) {
    throw new Error(`${what} index has no races array`);
  }
  for (const race of value.races) {
    if (!Number.isFinite(Number(race?.year)) || !Number.isFinite(Number(race?.round))) {
      throw new Error(`${what} index has a race without a numeric year and round: ${JSON.stringify(race)}`);
    }
  }
}

/**
 * Union of the local and published race lists. Local wins on a shared (year,
 * round); published-only entries are kept as they are.
 *
 * @param {object} local     the index.json found on disk
 * @param {object|null} published the index.json currently in the store, or null
 * @returns {object} a new document with `local` top-level fields
 */
export function mergeIndexes(local, published) {
  assertRaces(local, "local");
  if (published != null) assertRaces(published, "published");

  const byKey = new Map();
  for (const race of published?.races ?? []) byKey.set(raceKey(race), race);
  // Local entries are applied second, so they replace the published ones.
  for (const race of local.races) byKey.set(raceKey(race), race);

  const races = [...byKey.values()].sort(
    (a, b) => Number(a.year) - Number(b.year) || Number(a.round) - Number(b.round),
  );
  return { ...local, races };
}
