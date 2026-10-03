/**
 * Timing tower state, derived from race.json's per-lap `timing`.
 *
 * The artifact records, for each driver and each completed lap, the position
 * and gap to the leader AT THE END OF THAT LAP — but not the lap's end instant.
 * The end instant is derivable without inventing anything: every driver starts
 * lap 1 at the grid origin `t0_s` (the contract defines the grid start as the
 * earliest LapStartTime, i.e. approximately lights out), so lap k ends at
 *
 *   t0_s + sum(lap_time_s of laps 1..k)
 *
 * Two artifact nulls shape this module:
 * - `lap_time_s: null` (untimed laps, e.g. behind the safety car): the lap has
 *   NO derivable end instant, so it contributes no time and produces no row.
 *   The driver's last known row simply persists until the next timed lap
 *   completes — gaps freeze behind a safety car, which is what actually
 *   happens on track. Nothing is interpolated or fabricated.
 * - `position: null` on a timed lap: the lap advances the clock (the lap
 *   happened) but produces no row.
 * `gap_leader_s: null` (leader on untimed laps, cars a lap down) is preserved
 * as null and rendered as a dash — never replaced by a number.
 */
import type { RaceManifest, TimingDriver } from "./types";

export interface TimingRow {
  code: string;
  /** Lap this row comes from. */
  lap: number;
  position: number;
  /** Gap to the leader in seconds at that lap's end; null when unknown. */
  gapLeaderS: number | null;
  /** Compound on that lap, for the strategy view. */
  compound: string;
  pitIn: boolean;
  pitOut: boolean;
  /** Session time at which this row takes effect. */
  atS: number;
}

/** Per driver, the time-ordered rows that ever take effect. */
export function buildTimingTimeline(
  race: RaceManifest,
): Map<string, TimingRow[]> {
  const timeline = new Map<string, TimingRow[]>();
  for (const entry of race.timing) {
    timeline.set(entry.code, driverRows(entry, race.t0_s));
  }
  // Drivers without any timing entry still appear in the tower (as no data).
  for (const d of race.drivers) {
    if (!timeline.has(d.code)) timeline.set(d.code, []);
  }
  return timeline;
}

function driverRows(entry: TimingDriver, t0S: number): TimingRow[] {
  const rows: TimingRow[] = [];
  let elapsed = 0;
  for (const lap of entry.laps) {
    if (lap.lap_time_s === null) continue; // untimed lap: no end instant, no row
    elapsed += lap.lap_time_s;
    if (lap.position === null) continue; // timed but position unknown
    rows.push({
      code: entry.code,
      lap: lap.lap,
      position: lap.position,
      gapLeaderS: lap.gap_leader_s,
      compound: lap.compound,
      pitIn: lap.pit_in,
      pitOut: lap.pit_out,
      atS: t0S + elapsed,
    });
  }
  return rows;
}

/**
 * Running order at session time `t`: each driver's last row whose end instant
 * is at or before `t`, sorted by position. Drivers with no row yet (before
 * their first timed lap, or retired with no data) are listed at the bottom.
 */
export function standingsAtTime(race: RaceManifest, t: number): TimingRow[] {
  const timeline = buildTimingTimeline(race);
  const active: TimingRow[] = [];
  const waiting: string[] = [];
  for (const [code, rows] of timeline) {
    // Rows are time-ordered by construction; take the last one at or before t.
    let row: TimingRow | null = null;
    for (const r of rows) {
      if (r.atS <= t) row = r;
      else break;
    }
    if (row) active.push(row);
    else waiting.push(code);
  }
  active.sort((a, b) => a.position - b.position || a.code.localeCompare(b.code));
  waiting.sort();
  return active;
}

/** Codes with no row yet at time t (rendered as "sin datos"). */
export function driversWithoutData(race: RaceManifest, t: number): string[] {
  const active = new Set(standingsAtTime(race, t).map((r) => r.code));
  return race.drivers.map((d) => d.code).filter((c) => !active.has(c)).sort();
}
