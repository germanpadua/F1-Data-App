"""Export CLI (P1.7): python -m pipeline.export --year Y --round N [--session R] [--out DIR]

Idempotent: re-running a race overwrites its artifacts atomically and rewrites
index.json with EVERY race present under the output root, not just this one.
"""
from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone
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


def completed_rounds(year: int) -> list[int]:
    """Rounds of ``year`` whose race has already happened.

    Derived from FastF1's schedule and today's UTC date: an event is completed
    when its ``EventDate`` is strictly before today, and testing events are
    excluded. Nothing is hardcoded, so this follows the calendar by itself.
    This is what ``--all-completed`` backfills; the export runs locally, so
    there is no CI job to keep in sync with.
    """
    today = pd.Timestamp(datetime.now(timezone.utc).date())
    schedule = fastf1.get_event_schedule(year, include_testing=False)
    completed = schedule[schedule["EventDate"] < today]
    return [int(r) for r in completed["RoundNumber"]]


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


def _empty_track() -> dict:
    """Degraded track payload: no geometry, no metadata, drawn unrotated."""
    return {"points": [], "rotation_deg": 0.0, "corners": []}


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

    # Degradation policy (Phase 1): an ENRICHMENT that fails degrades to an
    # empty section plus a warning in race.json; the CORE (the session, the
    # lap data, the racing window, the replay traces) is deliberately NOT
    # wrapped — a replay that silently exports as empty is worse than a
    # failed round, so those failures still abort the export loudly.
    try:
        track = track_mod.build_track(session)
        track_warnings = track.pop("warnings", [])
    except Exception as exc:  # noqa: BLE001 — the race must still export
        track = _empty_track()
        track_warnings = [
            "track: circuit map could not be built from this session "
            f"({exc}); the race is exported without track geometry"
        ]

    try:
        events, event_warnings = events_mod.build_events(session, grid)
    except Exception as exc:  # noqa: BLE001 — the race must still export
        events, event_warnings = [], [
            "events: timeline could not be built "
            f"({exc}); the race is exported without events"
        ]

    timing, timing_warnings = timing_mod.build_timing(session)

    # P1.6 telemetry warnings declare every modification applied to the raw
    # feed (throttle clipping, all-zero DRS) so none of it is silent.
    warnings = [
        *telemetry_warnings,
        *track_warnings,
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
        "track": track,
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
    # DRS) can be embedded in race.json before it is written. A telemetry
    # failure is an enrichment failure: it degrades to absent tel/ files
    # plus a warning, it does not abort the round.
    try:
        telemetry_warnings = telemetry_mod.write_telemetry(
            session, grid, destination / layout.TEL_DIRNAME
        )
    except Exception as exc:  # noqa: BLE001 — the race must still export
        telemetry_warnings = [
            "telemetry: per-driver telemetry could not be exported "
            f"({exc}); the tel/ files are absent for this race"
        ]

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


def _race_exported(out_root: Path, year: int, round_number: int) -> bool:
    """True when a race directory for this round already has its artifacts.

    Checked on disk (any ``<round>-*`` directory with a ``race.json``) so a
    backfill is resumable and idempotent regardless of slug differences.
    """
    year_dir = Path(out_root) / str(year)
    if not year_dir.is_dir():
        return False
    prefix = f"{round_number}-"
    return any(
        (p / layout.RACE_FILENAME).is_file()
        for p in year_dir.iterdir() if p.is_dir() and p.name.startswith(prefix)
    )


def export_all_completed(year: int, session_code: str, out_root: Path,
                         *, upto_round: int | None = None) -> int:
    """Backfill: export every completed round of ``year``, resumably.

    Rounds already exported (a race.json on disk) are SKIPPED, a round that
    fails is recorded and does NOT abort the rest, and index.json is rebuilt
    once at the end from whatever is on disk, so the self-check over the
    whole root stays valid even after a partial run.

    ``upto_round`` is an optional bounding cap (round <= N) used to limit
    how much is downloaded in one run; it does not affect the round
    selection itself, only where the backfill stops.
    """
    rounds = completed_rounds(year)
    if upto_round is not None:
        rounds = [r for r in rounds if r <= upto_round]
    if not rounds:
        print(f"no completed rounds to export in the {year} season")
        return 0
    print(f"backfilling {len(rounds)} completed round(s) of {year}: {rounds}")

    outcomes: list[tuple[int, str]] = []
    for round_number in rounds:
        if _race_exported(out_root, year, round_number):
            outcomes.append((round_number, "skipped (already exported)"))
            print(f"round {round_number}: skipped (already exported)")
            continue
        try:
            destination = export_race(year, round_number, session_code, out_root)
            outcomes.append((round_number, "exported"))
            print(f"round {round_number}: exported -> {destination}")
        except Exception as exc:  # noqa: BLE001 — one bad round must not stop the rest
            outcomes.append((round_number, f"FAILED: {exc}"))
            print(f"round {round_number}: FAILED: {exc}")

    index = rebuild_index(out_root)
    exported = sum(1 for _, status in outcomes if status == "exported")
    skipped = sum(1 for _, status in outcomes if status.startswith("skipped"))
    failed = sum(1 for _, status in outcomes if status.startswith("FAILED"))
    print(f"backfill summary for {year}: {exported} exported, "
          f"{skipped} skipped, {failed} failed")
    for round_number, status in outcomes:
        print(f"  round {round_number}: {status}")
    print(f"index.json rewritten with {len(index['races'])} race(s)")
    return 1 if failed else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m pipeline.export",
        description="Export a completed F1 session to static JSON artifacts.",
    )
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--round", type=int, default=None)
    parser.add_argument(
        "--all-completed", action="store_true",
        help="export every completed round of --year (resumable: already "
             "exported rounds are skipped; one failure does not abort the rest)",
    )
    parser.add_argument(
        "--upto-round", type=int, default=None,
        help="with --all-completed, cap the backfill at this round "
             "(bounding cap for tests and partial bootstraps)",
    )
    parser.add_argument("--session", default="R", help="session code (default: R)")
    parser.add_argument("--out", default=str(REPO_ROOT / "data" / "export"),
                        help="output root (default: data/export)")
    args = parser.parse_args(argv)

    if args.round is None and not args.all_completed:
        parser.error("either --round N or --all-completed is required")

    # FastF1 cache at the repo's cache/ so repeated runs never re-download.
    fastf1.Cache.enable_cache(str(REPO_ROOT / "cache"))
    logging.getLogger("fastf1").setLevel(logging.WARNING)

    out_root = Path(args.out)
    if args.all_completed:
        return export_all_completed(
            args.year, args.session, out_root, upto_round=args.upto_round
        )

    destination = export_race(args.year, args.round, args.session, out_root)
    index = rebuild_index(out_root)
    print(f"exported {destination}")
    print(f"index.json rewritten with {len(index['races'])} race(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
