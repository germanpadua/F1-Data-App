import { useEffect, useRef, useState, useCallback } from "react";
import { advanceClock, type ClockState } from "./clock";

/**
 * The replay clock, driven by requestAnimationFrame with a fixed-step
 * accumulator (see clock.ts). `t` is session-relative seconds; race time is
 * `t - t0`. Playback stops automatically at the end of the replay.
 *
 * `tStart` is the beginning of the racing window (`race.t0_s`). It MUST be the
 * starting value, not zero: the artifacts live on the session-relative axis,
 * which begins at the start of the session, and the racing window starts about
 * an hour later. Starting at zero parks the clock before any lap has completed,
 * so the readout sits clamped at 0:00:00, the timing tower reports no data and
 * no car has a position yet.
 */
export function useDataClock(tEnd: number, tStart = 0) {
  const [t, setT] = useState(tStart);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(2);
  const stateRef = useRef<ClockState>({ t: tStart, acc: 0 });
  const speedRef = useRef(speed);
  speedRef.current = speed;

  useEffect(() => {
    if (!playing) return;
    let raf = 0;
    let prev = performance.now();
    const frame = (now: number) => {
      const dt = (now - prev) / 1000;
      prev = now;
      stateRef.current = advanceClock(stateRef.current, dt, speedRef.current, tEnd);
      setT(stateRef.current.t);
      if (stateRef.current.t >= tEnd) {
        setPlaying(false);
        return;
      }
      raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(raf);
  }, [playing, tEnd]);

  const jump = useCallback(
    (value: number) => {
      const clamped = Math.max(tStart, Math.min(tEnd, value));
      stateRef.current = { t: clamped, acc: 0 };
      setT(clamped);
    },
    [tEnd, tStart],
  );

  return { t, playing, setPlaying, speed, setSpeed, jump };
}
