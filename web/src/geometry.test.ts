import { describe, expect, it } from "vitest";
import { carPositionsBounds, rotatePoint, trackBounds } from "./geometry";

// Reference values produced by `modules/utils.py: rotate()` on the real
// Azerbaijan artifact (rotation_deg 357.0), the exact function the exporter
// documents as the one the frontend must mirror.
const PY_POINT = { x: 892, y: -203, deg: 357 };
const PY_ROTATED = { x: 880.1533458837624, y: -249.4054685238841 };
const PY_CORNER = { x: 3689, y: 631 };
const PY_CORNER_ROTATED = { x: 3716.9683420989204, y: 437.06789384991765 };

describe("geometry — rotation matching modules/utils.py rotate()", () => {
  it("rotates a known track point exactly like the Python side", () => {
    const [x, y] = rotatePoint(PY_POINT.x, PY_POINT.y, PY_POINT.deg);
    expect(x).toBeCloseTo(PY_ROTATED.x, 9);
    expect(y).toBeCloseTo(PY_ROTATED.y, 9);
  });

  it("rotates a known corner position exactly like the Python side", () => {
    const [x, y] = rotatePoint(PY_CORNER.x, PY_CORNER.y, PY_POINT.deg);
    expect(x).toBeCloseTo(PY_CORNER_ROTATED.x, 9);
    expect(y).toBeCloseTo(PY_CORNER_ROTATED.y, 9);
  });

  it("is the identity at 0 degrees", () => {
    expect(rotatePoint(1234, -5678, 0)).toEqual([1234, -5678]);
  });

  it("maps (1, 0) to (cos, sin) — a counter-clockwise rotation", () => {
    const [x, y] = rotatePoint(1, 0, 90);
    expect(x).toBeCloseTo(0, 12);
    expect(y).toBeCloseTo(1, 12);
  });
});

describe("geometry — track bounds for canvas fitting", () => {
  it("computes the rotated bounding box of the polyline", () => {
    const b = trackBounds(
      [
        [0, 0],
        [2, 1],
      ],
      0,
    );
    expect(b).toEqual({ minX: 0, maxX: 2, minY: 0, maxY: 1 });
  });

  it("bounds cover the rotated corners too (for label fitting)", () => {
    const b = trackBounds([[0, 0]], 90);
    // The single point stays at (0, 0) under rotation.
    expect(b).toEqual({ minX: 0, maxX: 0, minY: 0, maxY: 0 });
  });
});

describe("geometry — degraded track: bounds fallback from car positions", () => {
  const cars = [
    { x: [10, 20, null, 40], y: [0, null, 30, 40] },
    { x: [null, null], y: [null, null] }, // a car with no data at all
  ];

  it("fits the view to the car positions when the track has no geometry", () => {
    // Only non-null sample PAIRS count: (10,0), (40,40) — (20,null) and
    // (null,30) are half-samples and must be skipped.
    const b = carPositionsBounds(cars, 0);
    expect(b).toEqual({ minX: 10, maxX: 40, minY: 0, maxY: 40 });
  });

  it("applies the (possibly 0/unavailable) rotation like the track bounds", () => {
    const b = carPositionsBounds([{ x: [1], y: [0] }], 90)!;
    // (1, 0) rotated 90° counter-clockwise lands on (0, 1), up to float error.
    expect(b.minX).toBeCloseTo(0, 12);
    expect(b.maxX).toBeCloseTo(0, 12);
    expect(b.minY).toBeCloseTo(1, 12);
    expect(b.maxY).toBeCloseTo(1, 12);
  });

  it("returns null when no car ever reported a position (empty-track path)", () => {
    expect(carPositionsBounds([], 0)).toBeNull();
    expect(carPositionsBounds([{ x: [null, null], y: [null, null] }], 0)).toBeNull();
  });
});
