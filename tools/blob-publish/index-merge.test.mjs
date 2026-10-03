import assert from "node:assert/strict";
import test from "node:test";

import { isStaleRead, mergeIndexes, raceKey } from "./index-merge.mjs";

/** A minimal race entry shaped like pipeline/export.py: rebuild_index. */
function race(year, round, event, extra = {}) {
  return {
    year,
    round,
    slug: `${year}-${round}-${event.toLowerCase().replace(/\s+/g, "-")}`,
    event,
    session: "R",
    date: `${year}-01-01`,
    n_samples: 100,
    drivers: ["VER"],
    bytes: 1,
    ...extra,
  };
}

function indexOf(...races) {
  return { schema: "f1da.export.index/1", generated_at: "2026-10-03T00:00:00Z", step_s: 0.5, races };
}

test("the cold cache that motivated this: one race on disk does not drop the published fourteen", () => {
  const published = indexOf(...Array.from({ length: 15 }, (_, i) => race(2026, i + 1, `Round ${i + 1}`)));
  const local = indexOf(race(2026, 15, "Round 15", { n_samples: 999 }));

  const merged = mergeIndexes(local, published);

  assert.equal(merged.races.length, 15, "a disk-only index would have published 1 race");
  assert.deepEqual(
    merged.races.map((r) => r.round),
    [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
  );
  // Local wins for the round that exists on both sides.
  assert.equal(merged.races.at(-1).n_samples, 999);
  // Store-only entries survive by reference, verbatim.
  assert.equal(merged.races[0], published.races[0]);
  assert.equal(Object.keys(merged.races[0]).length, Object.keys(published.races[0]).length);
});

test("no published index (first publish) returns the local races only", () => {
  const local = indexOf(race(2026, 1, "Australian"));
  for (const published of [null, undefined]) {
    const merged = mergeIndexes(local, published);
    assert.equal(merged.races.length, 1);
    assert.equal(merged.races[0], local.races[0]);
  }
});

test("the top-level document comes from the local index", () => {
  const local = indexOf(race(2026, 2, "Chinese"));
  const published = indexOf(race(2025, 9, "Old"));
  const merged = mergeIndexes(local, published);
  assert.equal(merged.schema, "f1da.export.index/1");
  assert.equal(merged.generated_at, "2026-10-03T00:00:00Z");
  assert.equal(merged.step_s, 0.5);
  assert.equal("races" in merged, true);
});

test("a round is identified by (year, round), so a renamed event replaces instead of duplicating", () => {
  const local = indexOf(race(2026, 15, "Azerbaijan Grand Prix"));
  const published = indexOf(race(2026, 15, "Baku Grand Prix"));
  const merged = mergeIndexes(local, published);
  assert.equal(merged.races.length, 1);
  assert.equal(merged.races[0].event, "Azerbaijan Grand Prix");
  assert.equal(merged.races[0], local.races[0]);
});

test("races across years sort by year then round", () => {
  const merged = mergeIndexes(
    indexOf(race(2027, 1, "A"), race(2026, 20, "B")),
    indexOf(race(2026, 3, "C"), race(2026, 2, "D")),
  );
  assert.deepEqual(
    merged.races.map((r) => `${r.year}-${r.round}`),
    ["2026-2", "2026-3", "2026-20", "2027-1"],
  );
});

test("a duplicate round inside the published index collapses to one entry", () => {
  const merged = mergeIndexes(indexOf(), indexOf(race(2026, 4, "Miami"), race(2026, 4, "Miami again")));
  assert.equal(merged.races.length, 1);
  assert.equal(merged.races[0].event, "Miami again", "the last published entry wins");
});

test("races round-trip through JSON without loss", () => {
  const local = indexOf(race(2026, 1, "São Paulo Grand Prix", { drivers: ["VER", "HAM"] }));
  const merged = mergeIndexes(local, indexOf(race(2026, 5, "Miami")));
  assert.deepEqual(JSON.parse(JSON.stringify(merged)).races, merged.races);
});

test("inputs are not mutated", () => {
  const local = indexOf(race(2026, 1, "Australian"));
  const published = indexOf(race(2025, 24, "Abu Dhabi"));
  const localBefore = structuredClone(local);
  const publishedBefore = structuredClone(published);

  mergeIndexes(local, published);

  assert.deepEqual(local, localBefore);
  assert.deepEqual(published, publishedBefore);
});

test("a malformed index throws instead of shrinking silently", () => {
  assert.throws(() => mergeIndexes(null, null), /local index has no races array/);
  assert.throws(() => mergeIndexes({ schema: "x" }, null), /local index has no races array/);
  assert.throws(() => mergeIndexes({ races: "nope" }, null), /local index has no races array/);
  assert.throws(() => mergeIndexes({ races: [] }, { races: null }), /published index has no races array/);
  assert.throws(
    () => mergeIndexes({ races: [{ event: "no identity" }] }, null),
    /without a numeric year and round/,
  );
  assert.throws(
    () => mergeIndexes({ races: [] }, { races: [{ year: 2026 }] }),
    /without a numeric year and round/,
  );
});

test("raceKey is the (year, round) pair the exporter's rebuild_index sorts by", () => {
  assert.equal(raceKey({ year: 2026, round: 15 }), "2026-15");
  assert.notEqual(raceKey({ year: 2026, round: 1 }), raceKey({ year: 2026, round: 10 }));
});

test("a stale edge read is detected by comparing the edge and origin etags", () => {
  // Fresh: the edge serves a weak etag of the same document.
  assert.equal(isStaleRead('W/"2b11be6d"', '"2b11be6d"'), false);
  assert.equal(isStaleRead('"2b11be6d"', '"2b11be6d"'), false);
  // Stale: the exact pair measured while the edge served a previous index.
  assert.equal(isStaleRead('"3d926b05"', '"2b11be6d"'), true);
  assert.equal(isStaleRead('W/"3d926b05"', '"2b11be6d"'), true);
  // Cannot tell: never reported as stale.
  assert.equal(isStaleRead(null, '"2b11be6d"'), false);
  assert.equal(isStaleRead('W/"2b11be6d"', undefined), false);
  assert.equal(isStaleRead(null, null), false);
});
