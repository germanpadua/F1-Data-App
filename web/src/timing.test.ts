import { describe, expect, it } from "vitest";
import { buildTimingTimeline, standingsAtTime } from "./timing";
import type { RaceManifest } from "./types";

const T0 = 1000;
const STEP = 0.5;

const race: RaceManifest = {
  schema: "f1da.export.race/1",
  year: 2026,
  round: 15,
  session: "R",
  event: "Test GP",
  location: "Test",
  country: "Testland",
  date: "2026-09-26",
  t0_s: T0,
  step_s: STEP,
  n_samples: 100,
  total_laps: 3,
  drivers: [
    { code: "AAA", number: "1", name: "A A", team: "T1", color: "#ff0000" },
    { code: "BBB", number: "2", name: "B B", team: "T2", color: "#00ff00" },
    { code: "CCC", number: "3", name: "C C", team: "T3", color: "#0000ff" },
  ],
  track: { points: [], rotation_deg: 0, corners: [] },
  timing: [
    {
      code: "AAA",
      laps: [
        { lap: 1, position: 1, lap_time_s: 90, compound: "MEDIUM", tyre_life: 1, pit_in: false, pit_out: false, gap_leader_s: 0 },
        { lap: 2, position: 1, lap_time_s: 90, compound: "MEDIUM", tyre_life: 2, pit_in: false, pit_out: false, gap_leader_s: 0 },
      ],
    },
    {
      code: "BBB",
      laps: [
        { lap: 1, position: 2, lap_time_s: 91, compound: "MEDIUM", tyre_life: 1, pit_in: false, pit_out: false, gap_leader_s: 1.2 },
        // Untimed lap (safety car): position known, lap time null. The timeline
        // must NOT fabricate an end time for it.
        { lap: 2, position: 2, lap_time_s: null, compound: "HARD", tyre_life: 1, pit_in: false, pit_out: false, gap_leader_s: 3.4 },
        { lap: 3, position: 2, lap_time_s: 92, compound: "HARD", tyre_life: 2, pit_in: false, pit_out: false, gap_leader_s: 5.0 },
      ],
    },
    {
      code: "CCC",
      laps: [
        // Position null on lap 1: no row can be produced for it.
        { lap: 1, position: null, lap_time_s: 95, compound: "SOFT", tyre_life: 1, pit_in: false, pit_out: false, gap_leader_s: null },
        { lap: 2, position: 3, lap_time_s: 95, compound: "SOFT", tyre_life: 2, pit_in: false, pit_out: false, gap_leader_s: null },
      ],
    },
  ],
  events: [],
  warnings: [],
};

describe("timing — timing tower from race.json per-lap data", () => {
  it("shows no standings before the first lap completes", () => {
    expect(standingsAtTime(race, T0 + 10)).toEqual([]);
  });

  it("advances a driver's row when the clock crosses the lap end", () => {
    // AAA lap 1 ends at T0 + 90; BBB lap 1 ends at T0 + 91.
    expect(standingsAtTime(race, T0 + 89.9)).toEqual([]);
    const at91 = standingsAtTime(race, T0 + 91);
    expect(at91.map((r) => r.code)).toEqual(["AAA", "BBB"]);
    expect(at91[0]).toMatchObject({ position: 1, gapLeaderS: 0 });
    expect(at91[1]).toMatchObject({ position: 2, gapLeaderS: 1.2 });
  });

  it("keeps the last known row during untimed laps instead of fabricating one", () => {
    // BBB lap 2 is untimed: between T0+91 (lap 1 end) and T0+183 (lap 3 end,
    // since lap 2 contributes no time) BBB must still show its lap-1 state.
    const rows = standingsAtTime(race, T0 + 150);
    const bbb = rows.find((r) => r.code === "BBB");
    expect(bbb).toMatchObject({ position: 2, gapLeaderS: 1.2, lap: 1 });
  });

  it("resumes advancing once a later timed lap completes", () => {
    const rows = standingsAtTime(race, T0 + 183);
    const bbb = rows.find((r) => r.code === "BBB");
    expect(bbb).toMatchObject({ position: 2, gapLeaderS: 5.0, lap: 3 });
  });

  it("skips laps with null position without dropping the driver", () => {
    // CCC has no position on lap 1; its first row must be lap 2.
    const rows = standingsAtTime(race, T0 + 190);
    const ccc = rows.find((r) => r.code === "CCC");
    expect(ccc).toMatchObject({ position: 3, lap: 2, gapLeaderS: null });
  });

  it("keeps the leader first and orders by position", () => {
    const rows = standingsAtTime(race, T0 + 500);
    expect(rows.map((r) => r.position)).toEqual([...rows.map((r) => r.position)].sort((a, b) => a - b));
    expect(rows[0].code).toBe("AAA");
  });

  it("builds one timeline per driver from the manifest", () => {
    const tl = buildTimingTimeline(race);
    expect(tl.get("AAA")).toHaveLength(2);
    expect(tl.get("BBB")).toHaveLength(2); // laps 1 and 3; lap 2 untimed contributes none
    expect(tl.get("CCC")).toHaveLength(1); // lap 2 only
  });
});
