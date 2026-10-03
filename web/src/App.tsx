import { useCallback, useEffect, useState } from "react";
import { fetchIndex, fetchRace, fetchReplay, raceArtifactDir } from "./data";
import { RacePicker } from "./components/RacePicker";
import { ReplayView } from "./components/ReplayView";
import type { IndexFile, RaceManifest, ReplayData } from "./types";

export function App() {
  const [index, setIndex] = useState<IndexFile | null>(null);
  const [slug, setSlug] = useState<string | null>(null);
  const [race, setRace] = useState<RaceManifest | null>(null);
  const [replay, setReplay] = useState<ReplayData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchIndex()
      .then(setIndex)
      .catch((err) => setError(`No se pudo cargar index.json: ${err.message}`));
  }, []);

  const openRace = useCallback(
    (next: string) => {
      const entry = index?.races.find((r) => r.slug === next);
      if (!entry) return;
      const dir = raceArtifactDir(entry);
      setSlug(next);
      setRace(null);
      setReplay(null);
      setError(null);
      Promise.all([fetchRace(dir), fetchReplay(dir)])
        .then(([r, rep]) => {
          setRace(r);
          setReplay(rep);
        })
        .catch((err) => setError(`No se pudo cargar la carrera: ${err.message}`));
    },
    [index],
  );

  const back = useCallback(() => {
    setSlug(null);
    setRace(null);
    setReplay(null);
    setError(null);
  }, []);

  if (error)
    return (
      <div className="center">
        <p className="error">{error}</p>
        <button type="button" onClick={back}>
          Volver
        </button>
      </div>
    );
  if (!index) return <div className="center muted">Cargando carreras…</div>;
  if (!slug)
    return (
      <main className="app">
        <h1 className="brand">F1 Data App</h1>
        <RacePicker index={index} onSelect={openRace} />
      </main>
    );
  if (!race || !replay)
    return (
      <div className="center muted">
        Cargando {slug}… ({replay ? "" : "replay.json "}{race ? "" : "race.json"})
      </div>
    );
  return (
    <main className="app">
      <ReplayView race={race} cars={replay.cars} onBack={back} />
    </main>
  );
}
