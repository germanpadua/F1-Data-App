"""Export CLI (P1.7): python -m pipeline.export --year Y --round N [--session R] [--out DIR]

Idempotent: re-running a race overwrites its artifacts atomically and rewrites
index.json with EVERY race present under the output root, not just this one.
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import fastf1

from . import layout, replay as replay_mod, schemas, track as track_mod
from .grid import DEFAULT_STEP_S, Grid, compute_n_samples

REPO_ROOT = Path(__file__).resolve().parent.parent


def _max_session_time_s(session) -> float:
    """Largest session-relative instant covered by the car/track-status data.

    Race control messages are not included: they can trail the last car data
    by many minutes (post-race admin flags), and they are emitted as t_s
    floats in race.json events, not as grid-indexed arrays. The grid must
    cover the cars; nothing else defines its extent.
    """
    max_td = session.track_status["Time"].max()
    max_s = max_td.total_seconds() if max_td is not None else 0.0
    for number in session.drivers:  # scalars only; keep memory flat
        pos = session.pos_data.get(number)
        if pos is not None and len(pos):
            pos_max = pos["SessionTime"].max()
            if pos_max is not None:
                max_s = max(max_s, pos_max.total_seconds())
        car = session.car_data.get(number)
        if car is not None and len(car):
            car_max = car["SessionTime"].max()
            if car_max is not None:
                max_s = max(max_s, car_max.total_seconds())
    return float(max_s)


def _build_race_manifest(session, grid: Grid, year: int, round_number: int,
                         session_code: str) -> dict:
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

    # P1.4 / P1.5 / P1.6 are other passes. The contract shape is honoured and
    # the gap is made visible through warnings instead of silent emptiness.
    warnings = [
        "timing tower and tyre strategy (P1.4) not implemented yet; timing is empty",
        "timeline events (P1.5) not implemented yet; events is empty",
        "per-driver telemetry (P1.6) not implemented yet; tel/ files are not written",
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
        "t0_s": 0.0,  # start of the session-relative axis; see pipeline/grid.py
        "step_s": grid.step_s,
        "n_samples": grid.n_samples,
        "total_laps": total_laps,
        "drivers": drivers,
        "track": track_mod.build_track(session),
        "timing": [],
        "events": [],
        "warnings": warnings,
    }


def export_race(year: int, round_number: int, session_code: str,
                out_root: Path) -> Path:
    """Export one race and rebuild the index. Returns the race directory."""
    session = fastf1.get_session(year, round_number, session_code)
    session.load()  # heavy; cached by FastF1 under <repo>/cache/

    grid = Grid(
        n_samples=compute_n_samples(_max_session_time_s(session)),
        step_s=DEFAULT_STEP_S,
    )

    race = _build_race_manifest(session, grid, year, round_number, session_code)
    replay = replay_mod.build_replay(session, grid)
    replay["schema"] = schemas.SCHEMA_REPLAY
    replay["step_s"] = grid.step_s
    replay["n_samples"] = grid.n_samples

    destination = layout.race_dir(out_root, year, round_number, race["event"])
    destination.mkdir(parents=True, exist_ok=True)
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
