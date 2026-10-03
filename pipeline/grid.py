"""Shared time-grid maths (P1.1, amended by Amendment 1).

TIME ORIGIN — the trap this module exists to pin down:

FastF1 exposes ``session.t0_date``, a wall-clock timestamp that is a
whole-session maximum and can sit tens of minutes before the actual race
start. Using it as the origin would silently shift an entire replay.

Instead, every array in every artifact is addressed on FastF1's
*session-relative* time axis: the ``Time`` / ``SessionTime`` Timedelta
columns that FastF1 already provides on telemetry, track status and race
control data. On that axis:

    t0_s         the session-relative second at which the grid starts.
                 Amendment 1: the grid is trimmed to the racing window, so
                 t0_s is the earliest LapStartTime across drivers (about
                 lights out) and is NO LONGER 0.0 by definition. It is
                 written into race.json so the frontend can map a grid
                 index back to a session time.
    step_s       fixed step (default 0.5 s)
    sample_index = round((t_s - t0_s) / step_s)

No per-sample time array is ever stored: time is implicit from the index.
A missing sample is ``None`` (JSON ``null``), never ``0`` — 0 km/h is a
stopped car and 0 % throttle is a lift, so a silent zero would be a lie.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

DEFAULT_STEP_S = 0.5


def compute_n_samples(max_t_s: float, t0_s: float = 0.0,
                      step_s: float = DEFAULT_STEP_S) -> int:
    """Grid length covering every instant from ``t0_s`` up to ``max_t_s``.

    The last valid sample index is ``round((max_t_s - t0_s) / step_s)``, so
    the array needs that many buckets plus one (bucket 0 exists).
    """
    return int((max_t_s - t0_s) / step_s) + 1


@dataclass(frozen=True)
class Grid:
    """The one shared time grid for a race (racing window only, Amendment 1)."""

    n_samples: int
    step_s: float = DEFAULT_STEP_S
    t0_s: float = 0.0

    @property
    def t_end_s(self) -> float:
        """Session-relative second of the last grid sample."""
        return self.t0_s + (self.n_samples - 1) * self.step_s

    def index_of(self, t_s: float) -> int:
        """Session-relative seconds to grid index (may fall outside range)."""
        return int(round((t_s - self.t0_s) / self.step_s))

    def index_of_timedelta(self, td: pd.Timedelta) -> int:
        return self.index_of(td.total_seconds())

    def require_length(self, name: str, seq) -> None:
        """Enforce the n_samples invariant on an exported array."""
        n = len(seq)
        if n != self.n_samples:
            raise ValueError(
                f"length invariant violated: {name} has {n} samples, "
                f"expected n_samples={self.n_samples}"
            )

    def resample(self, session_times, values, name: str) -> list:
        """Decimate samples onto the grid, preserving the null policy.

        ``session_times``: session-relative seconds (float array) or
        ``pd.Timedelta`` values; ``values``: parallel numeric values.

        Returns a list of exactly ``n_samples`` entries. Buckets with no
        source sample stay ``None`` (JSON null) — gaps in the source data
        become nulls instead of collapsing the time axis. When several
        source samples fall into one bucket the last one wins. Source NaNs
        (FastF1 marks unavailable samples as NaN) also become ``None``.

        Amendment 1: the grid covers the racing window only, so source
        samples outside ``[t0_s, t_end_s]`` are EXPECTED (pre-race running
        before the earliest LapStartTime, cool-down and parc fermé after the
        last lap end plus margin) and are dropped here rather than treated
        as an error.
        """
        times = np.asarray(
            [
                t.total_seconds() if isinstance(t, pd.Timedelta) else t
                for t in session_times
            ],
            dtype=float,
        )
        vals = np.asarray(values, dtype=float)
        if len(times) != len(vals):
            raise ValueError(f"{name}: time/value length mismatch")

        out: list = [None] * self.n_samples
        # Iterate backwards so the first writer per bucket is the last sample.
        idx = np.round((times - self.t0_s) / self.step_s).astype(np.int64)
        for i, v in zip(idx[::-1], vals[::-1]):
            if i < 0 or i >= self.n_samples:
                continue  # outside the trimmed racing window; dropped
            if math.isnan(v):
                continue
            if out[i] is None:
                out[i] = int(round(v))
        self.require_length(name, out)
        return out
