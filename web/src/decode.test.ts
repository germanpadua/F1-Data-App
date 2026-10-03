import { describe, expect, it } from "vitest";
import { decodeDelta } from "./decode";

describe("decodeDelta — replay.json x/y delta decoding", () => {
  it("recovers the series when there are no nulls (plain prefix sum)", () => {
    expect(decodeDelta([100, 5, -3, 10])).toEqual([100, 105, 102, 112]);
  });

  it("treats the first sample as absolute, never as a difference", () => {
    // 100 is an absolute coordinate: decoding must not shift it.
    expect(decodeDelta([100])[0]).toBe(100);
    expect(decodeDelta([-42])[0]).toBe(-42);
  });

  it("keeps null transparent to the delta chain (single null)", () => {
    // The value after the gap is the difference from the last non-null
    // value BEFORE the gap, not from the null.
    expect(decodeDelta([100, 5, null, 7])).toEqual([100, 105, null, 112]);
  });

  it("recovers correctly across a run of several nulls", () => {
    expect(decodeDelta([100, 5, null, null, null, 2])).toEqual([
      100, 105, null, null, null, 107,
    ]);
  });

  it("handles a leading null (car has no data yet at the grid start)", () => {
    expect(decodeDelta([null, 50, 3, null, -10])).toEqual([null, 50, 53, null, 43]);
  });

  it("handles an all-null series (driver never set a time)", () => {
    expect(decodeDelta([null, null, null])).toEqual([null, null, null]);
  });

  it("handles an empty series", () => {
    expect(decodeDelta([])).toEqual([]);
  });

  it("does not mutate the input array", () => {
    const input = [10, 1, null, 2];
    decodeDelta(input);
    expect(input).toEqual([10, 1, null, 2]);
  });
});
