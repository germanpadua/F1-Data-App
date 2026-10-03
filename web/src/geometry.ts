/**
 * Track geometry: rotation and canvas fitting.
 *
 * `rotatePoint` mirrors `modules/utils.py: rotate()` EXACTLY. The Python side
 * multiplies the row vector [x, y] by the matrix
 *
 *   [[cos(a),  sin(a)],
 *    [-sin(a), cos(a)]]
 *
 * which yields [x·cos(a) − y·sin(a), x·sin(a) + y·cos(a)] — a counter-
 * clockwise rotation by `a` radians. `race.json` stores coordinates exactly as
 * FastF1 provides them (tenths of a metre, NOT pre-rotated) plus
 * `track.rotation_deg`; applying this same rotation here is what makes the map
 * orientation match the existing Streamlit charts.
 */
export function rotatePoint(x: number, y: number, rotationDeg: number): [number, number] {
  const a = (rotationDeg * Math.PI) / 180;
  const c = Math.cos(a);
  const s = Math.sin(a);
  return [x * c - y * s, x * s + y * c];
}

export interface Bounds {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
}

/** Rotated bounding box covering the centreline points and the corner labels. */
export function trackBounds(
  points: [number, number][],
  rotationDeg: number,
): Bounds {
  let minX = Infinity;
  let maxX = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;
  for (const [x0, y0] of points) {
    const [x, y] = rotatePoint(x0, y0, rotationDeg);
    minX = Math.min(minX, x);
    maxX = Math.max(maxX, x);
    minY = Math.min(minY, y);
    maxY = Math.max(maxY, y);
  }
  return { minX, maxX, minY, maxY };
}
