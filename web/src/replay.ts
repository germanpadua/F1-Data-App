/**
 * Car state on the shared grid: position and speed at session time `t`,
 * interpolated between the two bracketing samples so motion is smooth at the
 * 0.5 s grid resolution.
 *
 * Null policy (the whole point): a car is drawn only while its data exists.
 * The bracketing samples must BOTH be non-null for interpolation; if the next
 * sample is null — a dropout or a retirement cut — the car disappears as soon
 * as the clock passes its last real sample. A null is never drawn, and
 * nothing is ever placed at 0, 0.
 */
import type { CarSeries } from "./types";

export interface CarPose {
  x: number;
  y: number;
  /** km/h; null when the artifact has no speed for the bracketing samples. */
  speed: number | null;
}

export function carPoseAt(
  t0S: number,
  stepS: number,
  car: CarSeries,
  t: number,
): CarPose | null {
  const n = car.x.length;
  if (n === 0 || t < t0S) return null;
  const iFloat = (t - t0S) / stepS;
  const i = Math.min(Math.floor(iFloat), n - 1);
  const x0 = car.x[i];
  const y0 = car.y[i];
  if (x0 === null || y0 === null) return null;
  const j = i + 1;
  if (j >= n) {
    // Past the last sample (end of replay): hold the final real position.
    return { x: x0, y: y0, speed: car.speed[i] };
  }
  const f = iFloat - i;
  const x1 = car.x[j];
  const y1 = car.y[j];
  if (x1 === null || y1 === null) {
    // The next sample is missing (dropout or retirement): never interpolate
    // towards it. The car is visible exactly at the current sample's instant
    // and disappears as soon as the clock moves past it.
    return f === 0 ? { x: x0, y: y0, speed: car.speed[i] } : null;
  }
  const s0 = car.speed[i];
  const s1 = car.speed[j];
  return {
    x: x0 + f * (x1 - x0),
    y: y0 + f * (y1 - y0),
    speed: s0 !== null && s1 !== null ? s0 + f * (s1 - s0) : null,
  };
}
