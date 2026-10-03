import { useEffect, useRef, useState, useCallback } from "react";
import { advanceClock, type ClockState } from "./clock";

/**
 * The replay clock, driven by requestAnimationFrame with a fixed-step
 * accumulator (see clock.ts). `t` is session-relative seconds; race time is
 * `t - t0`. Playback stops automatically at the end of the replay.
 */
export function useDataClock(tEnd: number) {
  const [t, setT] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(2);
  const stateRef = useRef<ClockState>({ t: 0, acc: 0 });
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
      const clamped = Math.max(0, Math.min(tEnd, value));
      stateRef.current = { t: clamped, acc: 0 };
      setT(clamped);
    },
    [tEnd],
  );

  return { t, playing, setPlaying, speed, setSpeed, jump };
}
