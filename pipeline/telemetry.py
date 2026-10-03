"""Per-driver telemetry channels for tel/<CODE>.json (P1.6).

One file per driver: throttle, brake, rpm, gear and drs, each exactly
``n_samples`` long, on the shared racing-window grid. The payload is the
lazy one — the frontend fetches ``tel/<CODE>.json`` only when a driver is
selected, so these files are written independently of ``replay.json``.

CONVENTIONS SHARED WITH replay.py (do not diverge):

- Source frame is FastF1 car data. Verified columns (Amendment 1, A1c):
  ``SessionTime``, ``RPM``, ``Speed``, ``nGear``, ``Throttle``, ``Brake``,
  ``DRS``. The gear channel is ``nGear``.
- Same window filter (only samples inside ``[t0_s, t_end_s]``) and the same
  retirement cutoff (for a retired driver, everything after the last
  ``Speed > 0`` sample is dropped) so ``tel/`` and ``replay.json`` agree:
  after a car's last real sample the channels are ``null``, never ``0``.
- All other gaps (dropouts, samples outside the window) become ``null``
  via ``Grid.resample`` — never silently ``0``.
- Memory: drivers are processed ONE AT A TIME and each driver's raw frame
  is released before the next one is loaded. Raw telemetry for all drivers
  is never held or accumulated at once.

DATA MODIFICATIONS, ALWAYS RECORDED IN race.json ``warnings``:

- **Throttle clipping.** The raw feed reaches values above the contract's
  0-100 range (104 on 2026 R15). Throttle is clipped to [0, 100] and the
  number of clipped samples is counted and reported in a ``warnings``
  entry, so the silent modification the contract forbids is impossible.
- **DRS binarization.** The contract pins ``drs`` to {0, 1}; the feed is
  already numeric, and any positive code (some feeds carry 2/3/8-style
  state codes) is mapped to 1. On the reference session the feed is 0 for
  every sample, so this is a no-op there; when the feed IS all-zero, a
  ``warnings`` entry says the channel must not be read as a reliable DRS
  state. DRS state is never invented.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from . import layout, schemas
from .grid import Grid
from .replay import _is_retired

THROTTLE_MAX = 100

CHANNELS = ("throttle", "brake", "rpm", "gear", "drs")


def _prepare_car_data(session, grid: Grid, number: str, info):
    """Window-filter and retirement-cutoff the raw car data of one driver.

    Mirrors replay.py exactly so both payloads agree on where a retired
    car's data ends. Returns ``None`` when the driver has no car data.
    """
    car = session.car_data.get(number)
    if car is None or len(car) == 0:
        return None
    window = (car["SessionTime"] >= pd.Timedelta(seconds=grid.t0_s)) & (
        car["SessionTime"] <= pd.Timedelta(seconds=grid.t_end_s)
    )
    car = car[window]
    if _is_retired(info) and len(car):
        speeds = car["Speed"].to_numpy()
        moving = speeds > 0
        if moving.any():
            cutoff = car["SessionTime"].iloc[int(np.flatnonzero(moving)[-1])]
            car = car[car["SessionTime"] <= cutoff]
    return car


def write_telemetry(session, grid: Grid, tel_dir) -> list[str]:
    """Write ``tel/<CODE>.json`` for every driver; returns warnings.

    The warnings MUST end up in race.json's ``warnings`` array: they
    declare every modification applied to the raw feed (throttle clipping,
    all-zero DRS).
    """
    results = session.results
    tel_dir = Path(tel_dir)
    tel_dir.mkdir(parents=True, exist_ok=True)

    total_clipped = 0
    drs_nonzero_seen = False

    for number in session.drivers:  # one driver at a time, released below
        info = results.loc[number]
        code = str(info["Abbreviation"])
        car = _prepare_car_data(session, grid, number, info)

        if car is None or len(car) == 0:
            channels = {name: [None] * grid.n_samples for name in CHANNELS}
        else:
            times = car["SessionTime"].dt.total_seconds().to_numpy()

            raw_throttle = car["Throttle"].to_numpy(dtype=float)
            total_clipped += int(
                ((raw_throttle < 0) | (raw_throttle > THROTTLE_MAX)).sum()
            )
            throttle = np.clip(raw_throttle, 0, THROTTLE_MAX)

            raw_drs = car["DRS"].to_numpy(dtype=float)
            if (raw_drs > 0).any():
                drs_nonzero_seen = True

            channels = {
                "throttle": grid.resample(times, throttle, f"{number} throttle"),
                "brake": grid.resample(
                    times, car["Brake"].to_numpy(dtype=float), f"{number} brake"
                ),
                "rpm": grid.resample(
                    times, car["RPM"].to_numpy(dtype=float), f"{number} rpm"
                ),
                "gear": grid.resample(
                    times, car["nGear"].to_numpy(dtype=float), f"{number} gear"
                ),
                # Contract: drs in {0, 1}. Positive feed codes binarize to 1;
                # the feed is numeric already, so this is lossless on {0,1}.
                "drs": grid.resample(times, (raw_drs > 0).astype(float), f"{number} drs"),
            }

        payload = {
            "schema": schemas.SCHEMA_TEL,
            "code": code,
            "step_s": grid.step_s,
            "n_samples": grid.n_samples,
            **channels,
        }
        layout.atomic_write_json(tel_dir / f"{code}.json", payload)

        # Release this driver's raw telemetry before the next iteration.
        del car, channels, payload

    warnings: list[str] = []
    if total_clipped:
        warnings.append(
            f"telemetry: throttle clipped to [0, {THROTTLE_MAX}] on "
            f"{total_clipped} sample(s) inside the trimmed racing window; "
            "the raw feed exceeds the contract range"
        )
    if not drs_nonzero_seen:
        warnings.append(
            "telemetry: drs channel is 0 for every sample of this session's "
            "feed; the channel is kept but must NOT be read as a reliable "
            "DRS state"
        )
    return warnings
