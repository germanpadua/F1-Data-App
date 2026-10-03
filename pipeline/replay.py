"""Replay traces for replay.json (P1.3, amended by Amendment 1).

Per car: x, y and speed decimated onto the shared grid. This is the heavy
payload, so telemetry is processed ONE DRIVER AT A TIME and released
immediately; raw telemetry for all drivers is never held or accumulated.

Racing window (Amendment 1): the grid starts at the earliest LapStartTime
and ends at the latest lap end plus a margin, so position/car samples
before the race start and after the finish (pre-race running, cool-down)
are dropped by the grid resampler instead of stretching n_samples.

Null policy on real data (observed on 2026 R15):
- FastF1 keeps emitting position samples for a retired car — frozen at the
  car's final resting coordinates — all the way to the end of the session,
  and car telemetry keeps reporting Speed 0. Without a cutoff a retired car
  would sit on the map for the rest of the session instead of going null.
- Therefore, for a driver classified as retired, the trace is cut at the
  last instant the car was actually moving (last Speed > 0). Everything
  after that is null. Finished drivers keep their trace up to the grid end.
- All other gaps (data dropouts, samples before the car's first message)
  become null naturally via the grid.

DELTA ENCODING of x and y (Amendment 1, A1b):

``x[0]`` and ``y[0]`` (their first non-null entries) are ABSOLUTE; every
later non-null value is the integer difference from the previous non-null
value. ``speed`` stays absolute (small bounded range already).

NULL INTERACTION (the deliberate scheme):

A ``null`` sample is transparent to the delta chain. It is stored as
``null`` and contributes no difference; the next non-null sample after a
gap — any run of nulls — is the difference from the last non-null sample
BEFORE the gap. Reconstruction is therefore a plain running sum over the
non-null entries (first non-null value is absolute, each later one is
added to the running total), which is lossless across gaps of any length.
``pipeline/check.py`` reconstructs the series exactly this way before
range validation, so a delta is never compared against an absolute bound.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .grid import Grid


def _is_retired(result_row) -> bool:
    status = str(result_row.get("Status", ""))
    classified = str(result_row.get("ClassifiedPosition", ""))
    return status == "Retired" or classified == "R"


def _delta_encode(values: list) -> list:
    """Delta-encode a series per the scheme documented in the module docstring."""
    out: list = []
    previous: int | None = None
    for v in values:
        if v is None:
            out.append(None)  # transparent to the chain
            continue
        out.append(v if previous is None else v - previous)
        previous = v
    return out


def build_replay(session, grid: Grid, *, delta_encode: bool = True) -> dict:
    """Build the replay payload: absolute series, delta-encoded when asked.

    ``delta_encode=False`` exists so the size win of A1b can be measured
    against an absolute-x/y variant on the SAME trimmed grid.
    """
    cars = []
    results = session.results

    for number in session.drivers:  # one driver at a time, released below
        info = results.loc[number]
        pos = session.pos_data.get(number)
        car = session.car_data.get(number)
        if pos is None or car is None or len(pos) == 0:
            cars.append(
                {
                    "code": str(info["Abbreviation"]),
                    "x": [None] * grid.n_samples,
                    "y": [None] * grid.n_samples,
                    "speed": [None] * grid.n_samples,
                }
            )
            continue

        # Keep only samples inside the trimmed racing window.
        window = (pos["SessionTime"] >= pd.Timedelta(seconds=grid.t0_s)) & (
            pos["SessionTime"] <= pd.Timedelta(seconds=grid.t_end_s)
        )
        pos = pos[window]
        car_mask = (car["SessionTime"] >= pd.Timedelta(seconds=grid.t0_s)) & (
            car["SessionTime"] <= pd.Timedelta(seconds=grid.t_end_s)
        )
        car = car[car_mask]

        # Retirement cutoff (see module docstring).
        cutoff = None
        if _is_retired(info) and len(car):
            speeds = car["Speed"].to_numpy()
            moving = speeds > 0
            if moving.any():
                cutoff = car["SessionTime"].iloc[int(np.flatnonzero(moving)[-1])]

        if cutoff is not None:
            pos = pos[pos["SessionTime"] <= cutoff]
            car = car[car["SessionTime"] <= cutoff]

        x = y = speed = [None] * grid.n_samples
        times = None
        if len(pos):
            times = pos["SessionTime"].dt.total_seconds().to_numpy()
            x = grid.resample(times, pos["X"].to_numpy(), f"{number} x")
            y = grid.resample(times, pos["Y"].to_numpy(), f"{number} y")
            speed = grid.resample(
                car["SessionTime"].dt.total_seconds().to_numpy(),
                car["Speed"].to_numpy(),
                f"{number} speed",
            )

        if delta_encode:
            x = _delta_encode(x)
            y = _delta_encode(y)
        cars.append({"code": str(info["Abbreviation"]), "x": x, "y": y, "speed": speed})

        # Release this driver's raw telemetry before the next iteration.
        del pos, car, x, y, speed

    return {"cars": cars}
