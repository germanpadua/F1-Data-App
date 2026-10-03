/**
 * Delta decoding for replay.json (Amendment 1 of the Phase 1 contract).
 *
 * `x` and `y` are stored delta-encoded: the first non-null value is ABSOLUTE
 * and every later non-null value is the integer difference from the previous
 * non-null sample. `null` (a missing sample) is TRANSPARENT to the chain: a
 * null contributes no difference, so the next non-null value is the difference
 * from the last non-null value before the gap. A running sum over the non-null
 * entries therefore reconstructs the absolute series losslessly across gaps of
 * any length — which is exactly what `pipeline/check.py` verifies on the
 * Python side. See `pipeline/README.md`, "Delta encoding in replay.json".
 */
export function decodeDelta(deltas: (number | null)[]): (number | null)[] {
  let running: number | null = null;
  return deltas.map((v) => {
    if (v === null) return null;
    running = running === null ? v : running + v;
    return running;
  });
}
