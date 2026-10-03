"""Track geometry for race.json (P1.2).

Produces the centreline polyline (decimated to a few hundred points), the
circuit rotation angle and the corner labels.

Coordinates are stored exactly as FastF1 provides them (tenths of a metre,
integer values) and are NOT pre-rotated: ``rotation_deg`` travels alongside
and the frontend applies it exactly like ``modules/utils.py: rotate()``, so
the map orientation matches the existing Streamlit charts.
"""
from __future__ import annotations

import numpy as np

MAX_POINTS = 300
SMOOTH_WINDOW = 9


def build_track(session) -> dict:
    """Extract {points, rotation_deg, corners} from a loaded session.

    The centreline is the position trace of the race's fastest lap: a clean,
    pit-free racing lap covers the full circuit exactly once.
    """
    circuit = session.get_circuit_info()

    lap = session.laps.pick_fastest()
    if lap is None or len(lap) == 0:
        raise ValueError("no laps available to derive the centreline")

    pos = session.pos_data[lap["DriverNumber"]]
    start = lap["LapStartTime"]
    end = lap["LapStartTime"] + lap["LapTime"]
    mask = (pos["SessionTime"] >= start) & (pos["SessionTime"] <= end)
    xy = pos.loc[mask, ["X", "Y"]].to_numpy(dtype=float)
    if len(xy) < SMOOTH_WINDOW:
        raise ValueError("fastest-lap position trace too short for a centreline")

    # Light moving average removes GPS jitter before decimation.
    xy = np.column_stack(
        [
            np.convolve(xy[:, 0], np.ones(SMOOTH_WINDOW) / SMOOTH_WINDOW, mode="same"),
            np.convolve(xy[:, 1], np.ones(SMOOTH_WINDOW) / SMOOTH_WINDOW, mode="same"),
        ]
    )
    stride = max(1, int(np.ceil(len(xy) / MAX_POINTS)))
    xy = xy[::stride]
    points = [[int(round(x)), int(round(y))] for x, y in xy]

    corners = []
    for _, corner in circuit.corners.iterrows():
        corners.append(
            {
                "number": int(corner["Number"]),
                "letter": str(corner["Letter"]) if corner["Letter"] is not None else "",
                "x": int(round(float(corner["X"]))),
                "y": int(round(float(corner["Y"]))),
            }
        )

    return {
        "points": points,
        "rotation_deg": float(circuit.rotation),
        "corners": corners,
    }
