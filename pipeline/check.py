"""Self-check validator (P1.8): python -m pipeline.check --root data/export

Verifies every artifact on disk against the Phase 1 contract (as amended by
Amendment 1):
- JSON parses and the declared schema identifier matches;
- every array declared to be n_samples long is exactly that long;
- numeric ranges are plausible (speed 0-400, throttle 0-100, brake and drs
  in {0, 1}, rpm 0-18000, gear 0-8, position >= 1), x/y are integers;
- DELTA ENCODING: replay x/y are stored delta-encoded (Amendment 1, A1b),
  so range validation runs on the RECONSTRUCTED series (running sum over
  non-null entries; first non-null value absolute; nulls transparent to the
  chain) — never on the raw deltas, a legitimate delta of 200 would
  otherwise be wrongly rejected against an absolute bound;
- events are time-ordered and their ``kind`` is from the contract set;
- tel/<DRIVER>.json telemetry: schema, code/filename agreement, the
  n_samples invariant on every channel, and the per-channel value ranges —
  plus the SET of tel/ files matching the driver list in race.json exactly;
- index.json agrees with what is actually on disk (dirs, metadata, sizes).

Prints every failure found and exits non-zero if there was any.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import layout, schemas

SPEED_RANGE = (0, 400)
THROTTLE_RANGE = (0, 100)
# Plausible ranges for the telemetry channels (P1.6). F1 engines rev well
# below 18 000 and have 8 forward gears plus neutral (0).
RPM_RANGE = (0, 18_000)
GEAR_RANGE = (0, 8)
# Reconstructed x/y absolute bound, in tenths of a metre. Real circuit
# coordinates stay within a few tens of thousands; 1 000 000 (100 km) is far
# outside any circuit, so a corrupt delta chain lands here.
XY_ABS_LIMIT = 1_000_000
EVENT_KINDS = ("track_status", "race_control", "safety_car", "vsc")


class Failures(list):
    def add(self, message: str) -> None:
        self.append(message)


def _load_json(path: Path, failures: Failures, what: str):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        failures.add(f"{what}: file missing: {path}")
    except json.JSONDecodeError as exc:
        failures.add(f"{what}: invalid JSON in {path}: {exc}")
    return None


def _check_schema(payload, expected: str, failures: Failures, what: str) -> bool:
    if payload is None:
        return False
    if payload.get("schema") != expected:
        failures.add(
            f"{what}: declared schema {payload.get('schema')!r} != expected {expected!r}"
        )
        return False
    return True


def _check_channel(values, length: int, failures: Failures, what: str,
                   *, lo=None, hi=None, binary=False, integer=True) -> None:
    if len(values) != length:
        failures.add(f"{what}: length {len(values)} != n_samples {length}")
    for v in values:
        if v is None:
            continue
        if integer and not isinstance(v, int):
            failures.add(f"{what}: non-integer value {v!r}")
            return
        if binary and v not in (0, 1):
            failures.add(f"{what}: value {v!r} not in {{0, 1}}")
            return
        if lo is not None and not (lo <= v <= hi):
            failures.add(f"{what}: value {v} outside range [{lo}, {hi}]")
            return


def _reconstruct_deltas(values):
    """Inverse of the A1b delta encoding (see pipeline/replay.py).

    First non-null value is absolute; each later non-null value is the
    difference from the previous non-null value and is added to a running
    total; nulls are transparent to the chain.
    """
    out = []
    running = None
    for v in values:
        if v is None:
            out.append(None)
        elif running is None:
            running = v
            out.append(v)
        else:
            running += v
            out.append(running)
    return out


def _check_delta_channel(values, length: int, failures: Failures, what: str,
                         lo: int, hi: int) -> None:
    """Validate a delta-encoded channel: ints, exact length, and the RANGE
    CHECK ON THE RECONSTRUCTED SERIES, not on the deltas."""
    if len(values) != length:
        failures.add(f"{what}: length {len(values)} != n_samples {length}")
    for v in values:
        if v is None or isinstance(v, int):
            continue
        failures.add(f"{what}: non-integer delta {v!r}")
        return
    reconstructed = _reconstruct_deltas(values)
    for v in reconstructed:
        if v is None:
            continue
        if not (lo <= v <= hi):
            failures.add(
                f"{what}: reconstructed value {v} outside range [{lo}, {hi}] "
                "(delta chain corrupt)"
            )
            return


def check_race_dir(race_path: Path, failures: Failures) -> None:
    what = race_path.name  # e.g. 15-azerbaijan-grand-prix
    race = _load_json(race_path / layout.RACE_FILENAME, failures, what)
    if race is None or not _check_schema(race, schemas.SCHEMA_RACE, failures, what):
        return

    required_keys = (
        "year", "round", "session", "event", "location", "country", "date",
        "t0_s", "step_s", "n_samples", "total_laps", "drivers", "track",
        "timing", "events", "warnings",
    )
    for key in required_keys:
        if key not in race:
            failures.add(f"{what}: race.json missing key {key!r}")
    t0 = race.get("t0_s")
    if not isinstance(t0, (int, float)) or isinstance(t0, bool) or t0 < 0:
        failures.add(
            f"{what}: t0_s must be the session-relative second where the "
            f"trimmed grid starts (number >= 0), got {t0!r}"
        )

    n = race.get("n_samples")
    if not isinstance(n, int) or n <= 0:
        failures.add(f"{what}: invalid n_samples {n!r}")
        return

    # Events must be time-ordered and carry a contract kind.
    events = race.get("events") or []
    last_t = None
    for event in events:
        t = event.get("t_s")
        if not isinstance(t, (int, float)):
            failures.add(f"{what}: event without numeric t_s: {event!r}")
            continue
        if last_t is not None and t < last_t:
            failures.add(f"{what}: events not time-ordered at t_s={t}")
        last_t = t
        if event.get("kind") not in EVENT_KINDS:
            failures.add(
                f"{what}: event kind {event.get('kind')!r} not in {EVENT_KINDS} "
                f"at t_s={t}"
            )

    # Timing laps: position >= 1; lap times positive; pit flags boolean.
    for car in race.get("timing") or []:
        for lap in car.get("laps") or []:
            position = lap.get("position")
            if position is not None and (not isinstance(position, int) or position < 1):
                failures.add(f"{what}: timing position {position!r} < 1 for {car.get('code')}")
            lap_time = lap.get("lap_time_s")
            if lap_time is not None and (
                not isinstance(lap_time, (int, float)) or lap_time <= 0
            ):
                failures.add(
                    f"{what}: timing lap_time_s {lap_time!r} not null/positive "
                    f"for {car.get('code')} lap {lap.get('lap')}"
                )
            for flag in ("pit_in", "pit_out"):
                if flag in lap and not isinstance(lap[flag], bool):
                    failures.add(
                        f"{what}: timing {flag} {lap[flag]!r} not boolean for "
                        f"{car.get('code')} lap {lap.get('lap')}"
                    )

    # replay.json
    replay_path = race_path / layout.REPLAY_FILENAME
    replay = _load_json(replay_path, failures, what)
    if replay is not None and _check_schema(replay, schemas.SCHEMA_REPLAY, failures, what):
        if replay.get("n_samples") != n:
            failures.add(f"{what}: replay.json n_samples {replay.get('n_samples')!r} != {n}")
        cars = replay.get("cars")
        if not cars:
            failures.add(f"{what}: replay.json has no cars")
        for car in cars or []:
            code = car.get("code")
            for channel in ("x", "y"):
                _check_delta_channel(
                    car.get(channel) or [], n, failures,
                    f"{what}: replay {code} {channel}",
                    lo=-XY_ABS_LIMIT, hi=XY_ABS_LIMIT,
                )
            _check_channel(
                car.get("speed") or [], n, failures,
                f"{what}: replay {code} speed",
                lo=SPEED_RANGE[0], hi=SPEED_RANGE[1],
            )

    # tel/<DRIVER>.json (P1.6): the set of files must match the driver list
    # in race.json exactly, and every channel is validated per contract.
    tel_dir = race_path / layout.TEL_DIRNAME
    driver_codes = [d.get("code") for d in race.get("drivers") or []]
    if not tel_dir.is_dir():
        failures.add(
            f"{what}: no tel/ directory although per-driver telemetry (P1.6) "
            "is implemented"
        )
    else:
        tel_on_disk = {p.stem for p in tel_dir.glob("*.json")}
        expected = set(driver_codes)
        missing = sorted(expected - tel_on_disk)
        extra = sorted(tel_on_disk - expected)
        if missing:
            failures.add(f"{what}: tel/ is missing files for drivers: {missing}")
        if extra:
            failures.add(
                f"{what}: tel/ has files not in race.json drivers: {extra}"
            )
        for tel_path in sorted(tel_dir.glob("*.json")):
            code = tel_path.stem
            tel = _load_json(tel_path, failures, f"{what} tel/{code}")
            if tel is None or not _check_schema(
                tel, schemas.SCHEMA_TEL, failures, f"tel/{code}"
            ):
                continue
            if tel.get("n_samples") != n:
                failures.add(f"tel/{code}: n_samples {tel.get('n_samples')!r} != {n}")
            if tel.get("code") != code:
                failures.add(f"tel/{code}: declared code {tel.get('code')!r} != filename")
            for channel in ("throttle", "brake", "rpm", "gear", "drs"):
                if channel not in tel:
                    failures.add(f"tel/{code}: missing channel {channel!r}")
                    continue
                binary = channel in ("brake", "drs")
                if channel == "throttle":
                    lo, hi = THROTTLE_RANGE
                elif channel == "rpm":
                    lo, hi = RPM_RANGE
                elif channel == "gear":
                    lo, hi = GEAR_RANGE
                else:
                    lo, hi = (None, None)
                _check_channel(
                    tel[channel], n, failures, f"tel/{code} {channel}",
                    lo=lo, hi=hi, binary=binary,
                )


def check_root(root: Path) -> Failures:
    failures = Failures()
    root = Path(root)

    index = _load_json(root / layout.INDEX_FILENAME, failures, "index.json")
    if index is None or not _check_schema(index, schemas.SCHEMA_INDEX, failures, "index.json"):
        return failures

    on_disk = {str(p) for p in layout.iter_race_dirs(root)}
    seen = set()
    for entry in index.get("races") or []:
        year, round_number = entry.get("year"), entry.get("round")
        event = entry.get("event")
        if year is None or round_number is None or event is None:
            failures.add(f"index.json: incomplete race entry {entry!r}")
            continue
        path = layout.race_dir(root, year, round_number, event)
        seen.add(str(path))
        if str(path) not in on_disk:
            failures.add(f"index.json: race {entry.get('slug')} has no directory on disk")
            continue
        if entry.get("slug") != layout.race_slug(year, round_number, event):
            failures.add(f"index.json: slug {entry.get('slug')!r} does not match event")
        race = _load_json(path / layout.RACE_FILENAME, failures, f"index race {entry.get('slug')}")
        if race is not None:
            for key in ("event", "session", "date", "n_samples"):
                if entry.get(key) != race.get(key):
                    failures.add(
                        f"index.json: {key}={entry.get(key)!r} disagrees with race.json "
                        f"({race.get(key)!r}) for {entry.get('slug')}"
                    )
            if entry.get("drivers") != [d["code"] for d in race.get("drivers") or []]:
                failures.add(f"index.json: drivers disagree with race.json for {entry.get('slug')}")
        measured = layout.total_race_bytes(path)
        if entry.get("bytes") != measured:
            failures.add(
                f"index.json: bytes={entry.get('bytes')} disagrees with measured {measured} "
                f"for {entry.get('slug')}"
            )
        check_race_dir(path, failures)

    for path in sorted(on_disk - seen):
        failures.add(f"index.json: race directory on disk missing from index: {path}")

    return failures


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m pipeline.check",
        description="Validate exported artifacts against the Phase 1 contract.",
    )
    parser.add_argument("--root", default="data/export", help="export root (default: data/export)")
    args = parser.parse_args(argv)

    failures = check_root(Path(args.root))
    if failures:
        print(f"FAIL: {len(failures)} problem(s) found under {args.root}")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"OK: all artifacts under {args.root} satisfy the contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
