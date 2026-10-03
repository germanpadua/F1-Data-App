import { driversWithoutData, standingsAtTime } from "../timing";
import { formatRaceTime } from "../clock";
import type { RaceManifest } from "../types";

/** The timing tower: each driver's position and gap to the leader at the
 * current clock time, taken from race.json's per-lap timing, advancing as the
 * clock crosses each lap end (see timing.ts for the null rules). Leader first. */
export function TimingTower({ race, t }: { race: RaceManifest; t: number }) {
  const rows = standingsAtTime(race, t);
  const waiting = driversWithoutData(race, t);
  const byCode = new Map(race.drivers.map((d) => [d.code, d]));

  return (
    <section className="tower" aria-label="Torre de tiempos">
      <h3>Torre de tiempos</h3>
      {rows.length === 0 && waiting.length === 0 && (
        <p className="muted small">Sin datos todavía.</p>
      )}
      <ol className="tower-rows">
        {rows.map((row) => {
          const d = byCode.get(row.code);
          return (
            <li key={row.code} className="tower-row">
              <span className="pos">{row.position}</span>
              <span className="swatch" style={{ background: d?.color ?? "#888" }} />
              <strong>{row.code}</strong>
              <span className="compound">{row.compound}</span>
              {row.pitIn && <span className="pit" title="Entrada a boxes">P-in</span>}
              {row.pitOut && <span className="pit" title="Salida de boxes">P-out</span>}
              <span className="gap">
                {row.gapLeaderS === null
                  ? "—"
                  : row.gapLeaderS === 0
                    ? "LÍDER"
                    : `+${row.gapLeaderS.toFixed(3)}`}
              </span>
            </li>
          );
        })}
        {waiting.map((code) => (
          <li key={code} className="tower-row nodata">
            <span className="pos">·</span>
            <span className="swatch" style={{ background: byCode.get(code)?.color ?? "#888" }} />
            <strong>{code}</strong>
            <span className="gap muted">sin datos</span>
          </li>
        ))}
      </ol>
      <p className="muted small">
        Estado a {formatRaceTime(t - race.t0_s)} de carrera, según el final de la última
        vuelta cronometrada de cada piloto.
      </p>
    </section>
  );
}
