import { describe, expect, it } from "vitest";
import { advanceClock, ClockState, FIXED_STEP, indexAtTime, MAX_FRAME_S, replayDuration, sampleTime } from "./clock";

describe("clock — shared time grid mapping", () => {
  it("maps a grid index to session time with t0_s + i * step_s", () => {
    expect(sampleTime(3413.247, 0.5, 0)).toBeCloseTo(3413.247);
    expect(sampleTime(3413.247, 0.5, 10)).toBeCloseTo(3418.247);
  });

  it("maps session time back to a grid index with round((t - t0) / step)", () => {
    expect(indexAtTime(3413.247, 0.5, 3413.247)).toBe(0);
    expect(indexAtTime(3413.247, 0.5, 3418.247)).toBe(10);
    // Between samples it rounds to the nearest one.
    expect(indexAtTime(0, 0.5, 1.24)).toBe(2);
    expect(indexAtTime(0, 0.5, 1.26)).toBe(3);
  });

  it("round-trips index -> time -> index", () => {
    for (const i of [0, 1, 17, 5000, 11857]) {
      expect(indexAtTime(3413.247, 0.5, sampleTime(3413.247, 0.5, i))).toBe(i);
    }
  });

  it("computes the replay duration from the grid length", () => {
    expect(replayDuration(11858, 0.5)).toBeCloseTo((11858 - 1) * 0.5);
  });
});

describe("advanceClock — deterministic fixed-step accumulator", () => {
  const start = (): ClockState => ({ t: 0, acc: 0 });

  it("advances by speed * wall time using fixed sub-steps", () => {
    // 1 s of wall time at 4x, fed in 60 Hz frames: exactly 4.0 s of race time.
    let s = start();
    for (let i = 0; i < 60; i++) s = advanceClock(s, 1 / 60, 4, 1000);
    expect(s.t).toBeCloseTo(4, 10);
  });

  it("is frame-rate independent: 120 small frames equal 60 big ones", () => {
    let a = start();
    let b = start();
    for (let i = 0; i < 120; i++) a = advanceClock(a, 1 / 120, 2, 1000);
    for (let i = 0; i < 60; i++) b = advanceClock(b, 1 / 60, 2, 1000);
    expect(a.t).toBeCloseTo(b.t, 10);
  });

  it("carries the sub-step remainder across calls (no lost time at high fps)", () => {
    // A frame shorter than FIXED_STEP must not be discarded: ten 1/600 s
    // frames add up to one full sub-step.
    let s = start();
    for (let i = 0; i < 10; i++) s = advanceClock(s, 1 / 600, 1, 1000);
    expect(s.t).toBeCloseTo(FIXED_STEP, 12);
    expect(s.acc).toBeCloseTo(0, 12);
  });

  it("never advances past the end of the replay", () => {
    let s = { t: 99.9, acc: 0 };
    s = advanceClock(s, 1, 1, 100);
    expect(s.t).toBe(100);
    expect(advanceClock({ t: 100, acc: 0 }, 1, 1, 100).t).toBe(100);
  });

  it("clamps a stalled frame so the replay cannot jump", () => {
    expect(advanceClock(start(), 60, 1, 1000).t).toBeLessThanOrEqual(MAX_FRAME_S);
  });

  it("does not advance on zero or negative wall time", () => {
    expect(advanceClock({ t: 5, acc: 0 }, 0, 4, 1000)).toEqual({ t: 5, acc: 0 });
    expect(advanceClock({ t: 5, acc: 0 }, -1, 4, 1000)).toEqual({ t: 5, acc: 0 });
  });
});
