"""Replay traces for replay.json (P1.3).

Per car: x, y and speed decimated onto the shared grid. This is the heavy
payload, so telemetry is processed ONE DRIVER AT A TIME and released
immediately; raw telemetry for all drivers is never held or accumulated.

Null policy on real data (observed on 2026 R15):
- FastF1 keeps emitting position samples for a retired car — frozen at the
  car's final resting coordinates — all the way to the end of the session,
  and car telemetry keeps reporting Speed 0. Without a cutoff a retired car
  would sit on the map for the rest of the session instead of going null.
- Therefore, for a driver classified as retired, the trace is cut at the
  last instant the car was actually moving (last Speed > 0). Everything
  after that is null. Finished drivers keep their full trace (cool-down and
  parc fermé are real positions).
- All other gaps (data dropouts, samples before the car's first message)
  become null naturally via the grid.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .grid import Grid


def _is_retired(result_row) -> bool:
    status = str(result_row.get("Status", ""))
    classified = str(result_row.get("ClassifiedPosition", ""))
    return status == "Retired" or classified == "R"


def build_replay(session, grid: Grid) -> dict:
    """Build {schema-independent payload} of cars on the shared grid."""
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

        # Retirement cutoff (see module docstring).
        cutoff = None
        if _is_retired(info):
            speeds = car["Speed"].to_numpy()
            moving = speeds > 0
            if moving.any():
                cutoff = car["SessionTime"].iloc[int(np.flatnonzero(moving)[-1])]

        if cutoff is not None:
            pos = pos[pos["SessionTime"] <= cutoff]
            car = car[car["SessionTime"] <= cutoff]

        times = pos["SessionTime"].dt.total_seconds().to_numpy()
        x = grid.resample(times, pos["X"].to_numpy(), f"{number} x")
        y = grid.resample(times, pos["Y"].to_numpy(), f"{number} y")
        speed = grid.resample(
            car["SessionTime"].dt.total_seconds().to_numpy(),
            car["Speed"].to_numpy(),
            f"{number} speed",
        )
        cars.append({"code": str(info["Abbreviation"]), "x": x, "y": y, "speed": speed})

        # Release this driver's raw telemetry before the next iteration.
        del pos, car, times, x, y, speed

    return {"cars": cars}
