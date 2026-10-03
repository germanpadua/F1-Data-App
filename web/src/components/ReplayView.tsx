import { formatRaceTime, replayDuration } from "../clock";
import { useDataClock } from "../useDataClock";
import type { CarSeries, RaceManifest } from "../types";
import { TrackCanvas } from "./TrackCanvas";
import { TimingTower } from "./TimingTower";

const SPEEDS = [1, 2, 4, 8, 16] as const;

/** The replay: one data clock drives the canvas map and the timing tower.
 * Race time (t - t0) is what the user scrubs; the clock itself stays on the
 * session-relative axis shared with the artifacts. */
export function ReplayView({
  race,
  cars,
  onBack,
}: {
  race: RaceManifest;
  cars: CarSeries[];
  onBack: () => void;
}) {
  const tEnd = race.t0_s + replayDuration(race.n_samples, race.step_s);
  const { t, playing, setPlaying, speed, setSpeed, jump } = useDataClock(tEnd);
  const raceT = t - race.t0_s;

  return (
    <div className="replay">
      <header className="replay-head">
        <button type="button" className="back" onClick={onBack}>
          ← Carreras
        </button>
        <h2>
          {race.event} {race.year} <span className="muted">· {race.location}</span>
        </h2>
      </header>

      <div className="clockbar">
        <button
          type="button"
          className="play"
          onClick={() => setPlaying(!playing)}
          aria-pressed={playing}
        >
          {playing ? "⏸ Pausa" : "▶ Reproducir"}
        </button>
        <div className="rates" role="group" aria-label="Velocidad de reproducción">
          {SPEEDS.map((s) => (
            <button
              type="button"
              key={s}
              aria-pressed={speed === s}
              onClick={() => setSpeed(s)}
            >
              {s}×
            </button>
          ))}
        </div>
        <label className="scrub">
          <span className="visually-hidden">Reloj de datos</span>
          <input
            type="range"
            min={0}
            max={replayDuration(race.n_samples, race.step_s)}
            step={race.step_s / 2}
            value={Math.min(Math.max(raceT, 0), replayDuration(race.n_samples, race.step_s))}
            onChange={(e) => jump(race.t0_s + Number(e.target.value))}
          />
        </label>
        <output className="clockread">{formatRaceTime(raceT)}</output>
      </div>

      <div className="replay-grid">
        <div className="map-panel">
          <TrackCanvas race={race} cars={cars} t={t} />
        </div>
        <TimingTower race={race} t={t} />
      </div>

      {race.warnings.length > 0 && (
        <details className="warnings">
          <summary>Avisos del dato ({race.warnings.length})</summary>
          <ul>
            {race.warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
