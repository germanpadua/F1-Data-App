"""Timing tower and tyre strategy for race.json (P1.4).

Per driver, per lap: position, lap time, compound, tyre life, pit in/out
booleans and the gap to the leader.

gap_leader_s derivation (verified against real 2026 R15 data)
------------------------------------------------------------
The gap to the leader at the end of lap N is the difference in session
time between the driver COMPLETING lap N and the leader completing lap N.
The completion instant of a lap is:

- ``LapStartTime + LapTime`` for a timed lap;
- ``PitInTime`` for a pit-in lap — those laps carry no ``LapTime`` (the
  car leaves the timing line for pit lane), and crossing the pit entry
  line is when its racing lap ends;
- unknown otherwise (a lap abandoned by retirement has neither) — the gap
  for that lap is ``null``.

The leader for lap N is the row with ``Position == 1`` on that lap. By
construction the leader's own gap is exactly ``0.0`` on every lap. A car a
lap down is compared against the leader's completion of the SAME lap
number, which yields a positive gap of roughly one lap duration — large,
but never negative or nonsensical. If no leader end time is known for a
lap, every gap on that lap is ``null``: a null is far better than a
plausible-looking wrong number.

Drivers are emitted in final classified order; retired drivers naturally
have no laps after their retirement because the laps frame has none.
"""
from __future__ import annotations

import pandas as pd

GAP_DECIMALS = 3


def _lap_end_s(row) -> float | None:
    """Completion instant of one lap, in session-relative seconds."""
    if pd.notna(row.LapTime) and pd.notna(row.LapStartTime):
        return row.LapStartTime.total_seconds() + row.LapTime.total_seconds()
    if pd.notna(row.PitInTime):
        return row.PitInTime.total_seconds()
    return None


def build_timing(session) -> tuple[list, list]:
    """Build ``(timing, warnings)`` for the race.json ``timing`` array."""
    laps = session.laps

    lap_ends: dict[tuple[str, int], float] = {}
    for number, grp in laps.groupby("DriverNumber", sort=False):
        for row in grp.sort_values("LapNumber").itertuples():
            end = _lap_end_s(row)
            if end is not None:
                lap_ends[(str(number), int(row.LapNumber))] = end

    # Leader per lap number: the row with Position == 1 on that lap.
    leader_end: dict[int, float] = {}
    front = laps[laps["Position"] == 1]
    for row in front.itertuples():
        end = lap_ends.get((str(row.DriverNumber), int(row.LapNumber)))
        if end is not None:
            leader_end[int(row.LapNumber)] = end

    timing = []
    for number in laps["DriverNumber"].unique():
        grp = laps[laps["DriverNumber"] == number].sort_values("LapNumber")
        info = session.results.loc[number]
        lap_entries = []
        for row in grp.itertuples():
            lap = int(row.LapNumber)
            end = lap_ends.get((str(number), lap))
            gap = None
            if end is not None and lap in leader_end:
                gap = round(end - leader_end[lap], GAP_DECIMALS)
            lap_entries.append(
                {
                    "lap": lap,
                    "position": int(row.Position) if pd.notna(row.Position) else None,
                    "lap_time_s": (
                        round(row.LapTime.total_seconds(), GAP_DECIMALS)
                        if pd.notna(row.LapTime)
                        else None
                    ),
                    "compound": str(row.Compound) if pd.notna(row.Compound) else None,
                    "tyre_life": int(row.TyreLife) if pd.notna(row.TyreLife) else None,
                    "pit_in": bool(pd.notna(row.PitInTime)),
                    "pit_out": bool(pd.notna(row.PitOutTime)),
                    "gap_leader_s": gap,
                }
            )
        timing.append({"code": str(info["Abbreviation"]), "laps": lap_entries})

    # Every lap number on which ANY driver has a row but the leader's own
    # completion instant is unknown (untimed leader laps — typically behind
    # the safety car) gets a null gap. State it in warnings: a null with a
    # warning is far better than a plausible-looking wrong number.
    warnings = []
    all_lap_numbers = sorted({int(l) for l in laps["LapNumber"].dropna()})
    unanchored = [l for l in all_lap_numbers if l not in leader_end]
    if unanchored:
        warnings.append(
            "timing: gap_leader_s is null on laps "
            f"{unanchored[0]}-{unanchored[-1]} (the leader's own lap time is "
            "unavailable there, e.g. untimed laps behind the safety car); gaps "
            "are not fabricated from partial data"
        )
    return timing, warnings
