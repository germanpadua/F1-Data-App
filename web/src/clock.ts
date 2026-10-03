/**
 * The data clock. One shared time grid drives every layer of the replay:
 * grid sample i corresponds to session time `t0_s + i * step_s` (see the
 * Phase 1 contract — no per-sample time array is ever stored).
 *
 * The clock is session-relative seconds (the same axis as race.json's
 * `events[].t_s`). The user-facing readout shows race time, `t - t0_s`.
 *
 * Playback advances deterministically: wall-clock deltas are accumulated and
 * consumed in FIXED_STEP sub-steps, so the clock advances by the same amount
 * per unit of real time regardless of frame rate, and a long stall (background
 * tab) cannot jump the replay forward.
 */

/** Sub-step of the accumulator, in wall seconds (60 Hz). */
export const FIXED_STEP = 1 / 60;
/** Longest wall delta consumed per frame; anything longer is clamped. */
export const MAX_FRAME_S = 0.25;

/** Mutable clock state: the value and the unconsumed wall-time remainder. */
export interface ClockState {
  t: number;
  acc: number;
}

/** Session time of grid sample `i`. */
export function sampleTime(t0S: number, stepS: number, index: number): number {
  return t0S + index * stepS;
}

/** Grid index of session time `t` (nearest sample). */
export function indexAtTime(t0S: number, stepS: number, t: number): number {
  return Math.round((t - t0S) / stepS);
}

/** Replay duration in seconds: from the first to the last grid sample. */
export function replayDuration(nSamples: number, stepS: number): number {
  return (nSamples - 1) * stepS;
}

/**
 * Advance the clock by `wallDt` seconds of real time multiplied by `speed`,
 * consuming time in fixed sub-steps and carrying any sub-step remainder in
 * `state.acc` across calls. Deterministic and frame-rate independent: the
 * result depends only on the accumulated wall time, never on how frames were
 * split (a 120 Hz display advances exactly like a 60 Hz one). A wall delta
 * longer than MAX_FRAME_S is clamped so a background-tab stall cannot jump
 * the replay forward.
 */
export function advanceClock(
  state: ClockState,
  wallDt: number,
  speed: number,
  tEnd: number,
): ClockState {
  if (!(wallDt > 0)) return state;
  let acc = state.acc + Math.min(wallDt, MAX_FRAME_S);
  let t = state.t;
  while (acc >= FIXED_STEP) {
    t = Math.min(t + FIXED_STEP * speed, tEnd);
    acc -= FIXED_STEP;
  }
  return { t, acc };
}

/** Race-time readout (t - t0) as h:mm:ss. */
export function formatRaceTime(raceT: number): string {
  const total = Math.max(0, Math.floor(raceT));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}
