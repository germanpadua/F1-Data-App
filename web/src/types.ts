/** Types for the Phase 1 static export contract (v1), as documented in
 * `odd/tasks/phase-1-export-pipeline.md` (including Amendment 1) and
 * `pipeline/README.md`. The frontend consumes exactly this shape. */

export interface IndexRaceEntry {
  year: number;
  round: number;
  slug: string;
  event: string;
  session: string;
  date: string;
  n_samples: number;
  drivers: string[];
  bytes: number;
}

export interface IndexFile {
  schema: string;
  generated_at: string;
  step_s: number;
  races: IndexRaceEntry[];
}

export interface DriverInfo {
  code: string;
  number: string;
  name: string;
  team: string;
  color: string;
}

export interface Corner {
  number: number;
  letter: string;
  x: number;
  y: number;
}

export interface TrackGeometry {
  points: [number, number][];
  rotation_deg: number;
  corners: Corner[];
}

export interface LapRecord {
  lap: number;
  position: number | null;
  lap_time_s: number | null;
  compound: string;
  tyre_life: number | null;
  pit_in: boolean;
  pit_out: boolean;
  gap_leader_s: number | null;
}

export interface TimingDriver {
  code: string;
  laps: LapRecord[];
}

export type EventKind = "track_status" | "race_control" | "safety_car" | "vsc";

export interface RaceEvent {
  t_s: number;
  kind: EventKind;
  status: string | null;
  message: string | null;
  driver: string | null;
}

export interface RaceManifest {
  schema: string;
  year: number;
  round: number;
  session: string;
  event: string;
  location: string;
  country: string;
  date: string;
  t0_s: number;
  step_s: number;
  n_samples: number;
  total_laps: number;
  drivers: DriverInfo[];
  track: TrackGeometry;
  timing: TimingDriver[];
  events: RaceEvent[];
  warnings: string[];
}

/** Raw wire format of replay.json: x/y delta-encoded (x[0]/y[0] absolute,
 * later values are differences from the previous non-null sample; null is
 * transparent to the chain). Speed is absolute. */
export interface ReplayCarRaw {
  code: string;
  x: (number | null)[];
  y: (number | null)[];
  speed: (number | null)[];
}

export interface ReplayDataRaw {
  schema: string;
  step_s: number;
  n_samples: number;
  cars: ReplayCarRaw[];
}

/** Decoded in-memory format: x/y absolute, null preserved as "no data". */
export interface CarSeries {
  code: string;
  x: (number | null)[];
  y: (number | null)[];
  speed: (number | null)[];
}

export interface ReplayData {
  schema: string;
  step_s: number;
  n_samples: number;
  cars: CarSeries[];
}
