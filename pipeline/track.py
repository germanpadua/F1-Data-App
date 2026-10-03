"""Track geometry for race.json (P1.2).

Produces the centreline polyline (decimated to a few hundred points), the
circuit rotation angle and the corner labels.

Coordinates are stored exactly as FastF1 provides them (tenths of a metre,
integer values) and are NOT pre-rotated: ``rotation_deg`` travels alongside
and the frontend applies it exactly like ``modules/utils.py: rotate()``, so
the map orientation matches the existing Streamlit charts.

Two real degradations are handled here (both observed on the 2026 season):

- The fastest lap may have NO position data (2026 R6 Monaco: lap 76 has an
  empty per-lap frame while the session-level data is fine), so the
  reference lap is picked by walking timed laps until one yields a usable
  position trace instead of blindly trusting ``pick_fastest()``.
- Circuit info may be unavailable (2026 R14 Spanish GP: FastF1 logs
  "Failed to load circuit info" and ``get_circuit_info()`` raises), so the
  metadata is OPTIONAL: no corners, rotation 0, and a warning in race.json.
  A missing thing is reported as missing, never faked.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

MAX_POINTS = 300
SMOOTH_WINDOW = 9
# A candidate lap's in-window position samples must span at least this
# fraction of the lap's own duration to count as a complete circuit trace.
# 2026 R6 Monaco has a huge position-data dropout mid-race: laps 44-45 leave
# only 4-15 s of samples (6-20% of the lap) — enough rows to pass a row-count
# check, but drawing them would map a fragment of the circuit, not the track.
# Complete laps span ~100% of their window, so this bar separates them.
MIN_TRACE_SPAN_FRACTION = 0.8


def _usable_position_frame(pos) -> bool:
    """True when a position frame can seed a centreline: non-empty, carrying
    the ``X``/``Y`` columns, with at least one finite coordinate pair."""
    if pos is None or len(pos) == 0:
        return False
    if not {"X", "Y"}.issubset(set(pos.columns)):
        return False
    return bool(pos[["X", "Y"]].notna().all(axis=1).any())


def _lap_key(lap) -> tuple[str, object] | None:
    """(DriverNumber, LapNumber) of one lap, whatever shape FastF1 hands back
    (``pick_fastest()`` may return a one-row Laps or a bare row Series)."""
    if lap is None:
        return None
    if isinstance(lap, pd.DataFrame):
        if len(lap) == 0:
            return None
        lap = lap.iloc[0]
    if not isinstance(lap, pd.Series):
        return None
    try:
        return (str(lap["DriverNumber"]), lap["LapNumber"])
    except (KeyError, IndexError):
        return None


def _pick_reference_xy(session) -> tuple[pd.Series, np.ndarray]:
    """Return ``(lap_row, xy)`` for the first lap with a usable position trace.

    The fastest lap is tried first for backward compatibility; if its position
    data is unusable (empty, missing X/Y or all-NaN) the remaining timed laps
    are walked in lap-time order until one works. Raw whole-session position
    data is deliberately NOT a fallback: it would include the pit lane and
    outlaps and make the map ugly — only a clean single racing lap is a
    centreline.

    Why this exists: 2026 R6 Monaco. ``pick_fastest()`` returns lap 76, whose
    per-lap position data is EMPTY (0 rows; ``get_telemetry()`` even raises
    ``KeyError: "None of ['Date'] are in the columns"``) while the session-level
    position data for the same driver is fine (8087 rows). The centreline is
    therefore built from the next lap that actually has position data.
    """
    laps = session.laps
    if laps is None or len(laps) == 0:
        raise ValueError("no laps available to derive the centreline")

    fastest = laps.pick_fastest()
    fastest_key = _lap_key(fastest)

    timed = laps.dropna(subset=["LapTime"]).sort_values("LapTime", kind="stable")
    if len(timed) == 0:
        raise ValueError("no timed laps available to derive the centreline")

    # Candidates in trial order: the fastest lap first (it is also the head of
    # the lap-time ordering; the sort makes the intent explicit and is stable),
    # then every other timed lap from fastest upwards.
    candidates = sorted(
        ((row) for _, row in timed.iterrows()),
        key=lambda row: 0
        if (str(row["DriverNumber"]), row["LapNumber"]) == fastest_key
        else 1,
    )

    for row in candidates:
        number = str(row["DriverNumber"])
        pos = session.pos_data.get(number)
        if not _usable_position_frame(pos):
            continue
        start = row["LapStartTime"]
        end = row["LapStartTime"] + row["LapTime"]
        mask = (pos["SessionTime"] >= start) & (pos["SessionTime"] <= end)
        window = pos.loc[mask, ["SessionTime", "X", "Y"]].dropna(subset=["X", "Y"])
        if len(window) < SMOOTH_WINDOW:
            continue  # trace too short to smooth; walk to the next lap
        # A centreline needs ONE FULL circuit lap. A position-data dropout can
        # leave a fragment (Monaco 2026 lap 44: 20 rows over 4.5 s of a 76 s
        # lap) that passes the row-count bar; requiring the samples to span
        # the lap's duration rejects it.
        lap_time_s = row["LapTime"].total_seconds()
        span_s = (
            window["SessionTime"].max() - window["SessionTime"].min()
        ).total_seconds()
        if lap_time_s <= 0 or span_s < MIN_TRACE_SPAN_FRACTION * lap_time_s:
            continue
        logger.info(
            "centreline reference lap: driver %s lap %s (%d position samples)",
            number, row["LapNumber"], len(window),
        )
        return row, window[["X", "Y"]].to_numpy(dtype=float)

    raise ValueError("no lap with usable position data to derive the centreline")


def build_track(session) -> dict:
    """Extract {points, rotation_deg, corners, warnings} from a loaded session.

    The centreline is the position trace of one clean, pit-free racing lap
    covering the full circuit exactly once (see ``_pick_reference_xy``).

    The circuit metadata (corners, rotation) is OPTIONAL and never fatal:
    when FastF1 cannot provide it the track degrades to an unrotated map with
    no corner labels, and the loss is declared in the returned ``warnings``
    (which the exporter embeds in race.json). This never raises for metadata.
    """
    _, xy = _pick_reference_xy(session)

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

    warnings: list[str] = []
    corners: list[dict] = []
    rotation_deg = 0.0

    circuit = None
    reason = None
    try:
        circuit = session.get_circuit_info()
    except Exception as exc:  # noqa: BLE001 — metadata is optional, never fatal
        reason = str(exc) or type(exc).__name__
    if circuit is None:
        if reason is None:
            reason = "FastF1 returned no circuit info for this session"
        warnings.append(
            "track: circuit metadata unavailable "
            f"({reason}); corner labels and rotation are missing and the "
            "map is drawn unrotated"
        )
        return {
            "points": points,
            "rotation_deg": rotation_deg,
            "corners": corners,
            "warnings": warnings,
        }

    try:
        for _, corner in circuit.corners.iterrows():
            corners.append(
                {
                    "number": int(corner["Number"]),
                    "letter": str(corner["Letter"]) if corner["Letter"] is not None else "",
                    "x": int(round(float(corner["X"]))),
                    "y": int(round(float(corner["Y"]))),
                }
            )
        rotation_deg = float(circuit.rotation)
    except Exception as exc:  # noqa: BLE001 — metadata is optional, never fatal
        corners = []
        rotation_deg = 0.0
        warnings.append(
            "track: circuit metadata could not be read "
            f"({exc}); corner labels and rotation are missing and the "
            "map is drawn unrotated"
        )

    return {
        "points": points,
        "rotation_deg": rotation_deg,
        "corners": corners,
        "warnings": warnings,
    }
