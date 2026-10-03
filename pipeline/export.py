"""Export CLI (P1.7): python -m pipeline.export --year Y --round N [--session R] [--out DIR]

Idempotent: re-running a race overwrites its artifacts atomically and rewrites
index.json with EVERY race present under the output root, not just this one.
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import pandas as pd
import fastf1

from . import events as events_mod
from . import layout, replay as replay_mod, schemas, telemetry as telemetry_mod
from . import timing as timing_mod
from . import track as track_mod
from .grid import DEFAULT_STEP_S, Grid, compute_n_samples

REPO_ROOT = Path(__file__).resolve().parent.parent

# Amendment 1 (A1a): the grid ends at the latest lap end plus this margin.
RACING_WINDOW_MARGIN_S = 5.0


def _racing_window_s(session) -> tuple[float, float]:
    """(t0_s, t_end_s) of the trimmed racing window, in session-relative seconds.

    Amendment 1 (A1a): the origin is the earliest ``LapStartTime`` across
    drivers — the leader's lap 1, about lights out — and the end is the
    latest lap end across drivers plus a 5 s margin. Roughly 57 minutes of
    pre-race session running are thereby excluded from every artifact.
    """
    laps = session.laps
    start = laps["LapStartTime"].min()
    end = (laps["LapStartTime"] + laps["LapTime"]).max()
    if pd.isna(start) or pd.isna(end):
        raise ValueError("no lap times available to derive the racing window")
    t0_s = start.total_seconds()
    t_end_s = end.total_seconds() + RACING_WINDOW_MARGIN_S
    if t_end_s <= t0_s:
        raise ValueError(f"degenerate racing window: [{t0_s}, {t_end_s}] s")
    return t0_s, t_end_s


def _build_race_manifest(session, grid: Grid, year: int, round_number: int,
                         session_code: str, telemetry_warnings: list[str]) -> dict:
    event = session.event
    results = session.results.sort_values("Position", na_position="last")

    drivers = []
    for number, row in results.iterrows():
        drivers.append(
            {
                "code": str(row["Abbreviation"]),
                "number": str(number),
                "name": str(row["FullName"]),
                "team": str(row["TeamName"]),
                "color": "#" + str(row["TeamColor"]).lstrip("#"),
            }
        )

    total_laps = int(session.laps["LapNumber"].max())

    events, event_warnings = events_mod.build_events(session, grid)
    timing, timing_warnings = timing_mod.build_timing(session)

    # P1.6 telemetry warnings declare every modification applied to the raw
    # feed (throttle clipping, all-zero DRS) so none of it is silent.
    warnings = [
        *telemetry_warnings,
        *event_warnings,
        *timing_warnings,
    ]

    return {
        "schema": schemas.SCHEMA_RACE,
        "year": year,
        "round": round_number,
        "session": session_code,
        "event": str(event["EventName"]),
        "location": str(event["Location"]),
        "country": str(event["Country"]),
        "date": event["EventDate"].date().isoformat(),
        # Amendment 1: session-relative second at which the trimmed grid
        # starts (about lights out). The frontend needs this to map a grid
        # index back to a session time; it is NOT 0.0 by definition any more.
        "t0_s": grid.t0_s,
        "step_s": grid.step_s,
        "n_samples": grid.n_samples,
        "total_laps": total_laps,
        "drivers": drivers,
        "track": track_mod.build_track(session),
        "timing": timing,
        "events": events,
        "warnings": warnings,
    }


def export_race(year: int, round_number: int, session_code: str,
                out_root: Path) -> Path:
    """Export one race and rebuild the index. Returns the race directory."""
    session = fastf1.get_session(year, round_number, session_code)
    session.load()  # heavy; cached by FastF1 under <repo>/cache/

    t0_s, t_end_s = _racing_window_s(session)
    grid = Grid(
        n_samples=compute_n_samples(t_end_s, t0_s),
        step_s=DEFAULT_STEP_S,
        t0_s=t0_s,
    )

    destination = layout.race_dir(
        out_root, year, round_number, str(session.event["EventName"])
    )
    destination.mkdir(parents=True, exist_ok=True)

    # P1.6: telemetry first, so its warnings (throttle clipping, all-zero
    # DRS) can be embedded in race.json before it is written.
    telemetry_warnings = telemetry_mod.write_telemetry(
        session, grid, destination / layout.TEL_DIRNAME
    )

    race = _build_race_manifest(
        session, grid, year, round_number, session_code, telemetry_warnings
    )
    replay = replay_mod.build_replay(session, grid)
    replay["schema"] = schemas.SCHEMA_REPLAY
    replay["step_s"] = grid.step_s
    replay["n_samples"] = grid.n_samples

    layout.atomic_write_json(destination / layout.RACE_FILENAME, race)
    layout.atomic_write_json(destination / layout.REPLAY_FILENAME, replay)
    return destination


def rebuild_index(out_root: Path) -> dict:
    """Rewrite index.json from every race directory found under out_root."""
    races = []
    for path in layout.iter_race_dirs(out_root):
        race_path = path / layout.RACE_FILENAME
        with open(race_path, encoding="utf-8") as f:
            race = json.load(f)
        year = int(path.parent.name)
        round_number = int(path.name.split("-", 1)[0])
        races.append(
            {
                "year": year,
                "round": round_number,
                "slug": layout.race_slug(year, round_number, race["event"]),
                "event": race["event"],
                "session": race["session"],
                "date": race["date"],
                "n_samples": race["n_samples"],
                "drivers": [d["code"] for d in race["drivers"]],
                "bytes": layout.total_race_bytes(path),
            }
        )
    races.sort(key=lambda r: (r["year"], r["round"]))
    index = {
        "schema": schemas.SCHEMA_INDEX,
        "generated_at": layout.utc_now_iso(),
        "step_s": DEFAULT_STEP_S,
        "races": races,
    }
    layout.atomic_write_json(Path(out_root) / layout.INDEX_FILENAME, index, indent=2)
    return index


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m pipeline.export",
        description="Export a completed F1 session to static JSON artifacts.",
    )
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--round", type=int, required=True)
    parser.add_argument("--session", default="R", help="session code (default: R)")
    parser.add_argument("--out", default=str(REPO_ROOT / "data" / "export"),
                        help="output root (default: data/export)")
    args = parser.parse_args(argv)

    # FastF1 cache at the repo's cache/ so repeated runs never re-download.
    fastf1.Cache.enable_cache(str(REPO_ROOT / "cache"))
    logging.getLogger("fastf1").setLevel(logging.WARNING)

    out_root = Path(args.out)
    destination = export_race(args.year, args.round, args.session, out_root)
    index = rebuild_index(out_root)
    print(f"exported {destination}")
    print(f"index.json rewritten with {len(index['races'])} race(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
