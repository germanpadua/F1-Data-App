import { describe, expect, it } from "vitest";
import { carPoseAt } from "./replay";
import type { CarSeries } from "./types";

const T0 = 1000;
const STEP = 0.5;

const car: CarSeries = {
  code: "TST",
  //         i0     i1     i2     i3(gap)  i4     i5     i6   i7(last)  i8
  x: [null, 100, 110, 120, null, 200, 210, null, 300],
  y: [null, 50, 55, 60, null, 80, 85, null, 90],
  speed: [null, 200, 210, 220, null, 240, 250, null, 260],
};

describe("carPoseAt — null policy and interpolation", () => {
  it("hides the car before its first sample", () => {
    expect(carPoseAt(T0, STEP, car, T0 - 0.1)).toBeNull();
    expect(carPoseAt(T0, STEP, car, T0)).toBeNull(); // sample 0 is null
  });

  it("interpolates between two non-null samples", () => {
    const p = carPoseAt(T0, STEP, car, T0 + 1.25); // between i1 and i2, f = 0.5
    expect(p).toEqual({ x: 115, y: 57.5, speed: 215 });
  });

  it("is exact at a sample instant (f = 0)", () => {
    const p = carPoseAt(T0, STEP, car, T0 + 0.5);
    expect(p).toEqual({ x: 100, y: 50, speed: 200 });
  });

  it("hides the car inside a gap, even one sample long", () => {
    expect(carPoseAt(T0, STEP, car, T0 + 4 * STEP + 0.1)).toBeNull(); // i4 (gap)
    expect(carPoseAt(T0, STEP, car, T0 + 4 * STEP + 0.4)).toBeNull(); // still i4
  });

  it("shows the car exactly at its last real sample and hides it after", () => {
    // i3 (t = T0 + 1.5) is the last sample before the gap: visible exactly at
    // the sample instant, hidden half a step later, since i4 is null.
    expect(carPoseAt(T0, STEP, car, T0 + 3 * STEP)).toEqual({ x: 120, y: 60, speed: 220 });
    expect(carPoseAt(T0, STEP, car, T0 + 3 * STEP + 0.25)).toBeNull();
    // i6 (t = T0 + 3.0) is the array's last non-null sample: visible exactly
    // at the sample instant, hidden after, since i7 is null.
    const atLast = carPoseAt(T0, STEP, car, T0 + 6 * STEP);
    expect(atLast).toEqual({ x: 210, y: 85, speed: 250 });
    expect(carPoseAt(T0, STEP, car, T0 + 6 * STEP + 0.25)).toBeNull();
  });

  it("holds the final real position past the end of the replay", () => {
    const p = carPoseAt(T0, STEP, car, T0 + 100);
    expect(p).toEqual({ x: 300, y: 90, speed: 260 });
  });
});
