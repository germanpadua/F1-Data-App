/**
 * The one module that owns all artifact fetching.
 *
 * The base URL comes from VITE_DATA_BASE_URL. Empty/absent means same-origin,
 * which is how development and `vite preview` work (web/public/data links to
 * the real data/export artifacts), and in production it points at the Vercel
 * Blob base URL. The identical code path serves both.
 *
 * replay.json x/y arrive delta-encoded (Amendment 1); this module decodes them
 * once on load so every consumer works with absolute coordinates. `null`
 * samples are preserved as null — they mean "no data", never zero.
 */
import { decodeDelta } from "./decode";
import type { IndexFile, RaceManifest, ReplayData, ReplayDataRaw } from "./types";

export function resolveBase(explicit?: string): string {
  const raw =
    explicit ??
    (import.meta as { env?: Record<string, string | undefined> }).env
      ?.VITE_DATA_BASE_URL ??
    "";
  return raw.replace(/\/+$/, "");
}

async function getJson<T>(base: string, path: string): Promise<T> {
  const res = await fetch(`${base}/${path}`);
  if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`);
  return (await res.json()) as T;
}

/**
 * Artifact directory of an index entry. index.json's `slug` is the full race
 * name `{year}-{round}-{event}` (pipeline/layout.py: race_slug), while the on-
 * disk layout is `{year}/{round}-{event}` (layout.py: race_dir). The directory
 * is therefore the slug minus its `{year}-` prefix — derived, never guessed.
 */
export function raceArtifactDir(entry: { year: number; slug: string }): string {
  const prefix = `${entry.year}-`;
  if (!entry.slug.startsWith(prefix)) {
    throw new Error(`slug ${entry.slug} does not start with its year ${entry.year}`);
  }
  return `${entry.year}/${entry.slug.slice(prefix.length)}`;
}

export function fetchIndex(base?: string): Promise<IndexFile> {
  return getJson<IndexFile>(resolveBase(base), "index.json");
}

export function fetchRace(dir: string, base?: string): Promise<RaceManifest> {
  return getJson<RaceManifest>(resolveBase(base), `${dir}/race.json`);
}

export async function fetchReplay(dir: string, base?: string): Promise<ReplayData> {
  const raw = await getJson<ReplayDataRaw>(resolveBase(base), `${dir}/replay.json`);
  return {
    schema: raw.schema,
    step_s: raw.step_s,
    n_samples: raw.n_samples,
    cars: raw.cars.map((c) => ({
      code: c.code,
      x: decodeDelta(c.x),
      y: decodeDelta(c.y),
      speed: c.speed,
    })),
  };
}
