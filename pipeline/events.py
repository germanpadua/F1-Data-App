"""Timeline events for race.json (P1.5).

One time-ordered, de-duplicated list of
``{t_s, kind, status, message, driver}``.

TIME AXIS TRAP (verified on real 2026 data — do not "simplify" this):

- Track status ``Time`` is ALREADY a session-relative ``Timedelta``: use
  ``Time.total_seconds()`` directly.
- Race control ``Time`` is an ABSOLUTE ``datetime64``: it must be converted
  with ``Time - session.t0_date`` to land on the session-relative axis.
  Mixing these two silently misplaces every race control message.

Both are emitted as session-relative seconds — the same axis the shared
grid is defined on — so the frontend maps an event to a grid sample with
``round((t_s - race.t0_s) / step_s)`` using ``t0_s`` from race.json.

SAFETY CAR / VSC DERIVATION RULE
--------------------------------
A race control message is a safety-car period boundary only when its text
both mentions the safety car and names a transition:

- deploy: message contains "SAFETY CAR" and "DEPLOYED"
- end:    message contains "SAFETY CAR" and ("IN THIS LAP" or "ENDING")

``kind`` is ``vsc`` when the message contains "VIRTUAL", else
``safety_car``. Messages that merely mention the safety car without naming
a transition (e.g. "LAPPED CARS MAY NOW OVERTAKE THE SAFETY CAR") are
ordinary ``race_control`` events, NOT period boundaries.

Track status code "4" is the SC-deployed status ("7"/"8" would be the VSC
codes). To avoid emitting the same real-world event twice under two kinds,
a track-status SC/VSC event is SUPPRESSED when a race-control boundary
event already exists within 10 s of it; if no such message exists, the
track-status row is emitted as a derived ``safety_car``/``vsc`` event so a
period is never invisible.

Events outside the trimmed racing window (grid ``[t0_s, t_end_s]``) are
DROPPED deliberately, and the drop is recorded in a ``warnings`` entry:
pre-race messages (the ~57 min of formation running) and post-race admin
messages are not part of the race replay a user scrolls through.
"""
from __future__ import annotations

import pandas as pd

SC_STATUS_KINDS = {"4": "safety_car", "7": "vsc", "8": "vsc"}
SC_DEDUP_WINDOW_S = 10.0
KINDS = ("track_status", "race_control", "safety_car", "vsc")


def _driver_codes(session) -> dict[str, str]:
    """Racing number -> 3-letter code, for the ``driver`` event field."""
    codes = {}
    for number, row in session.results.iterrows():
        abbr = row.get("Abbreviation")
        if pd.notna(abbr):
            codes[str(number)] = str(abbr)
    return codes


def build_events(session, grid) -> tuple[list, list]:
    """Build ``(events, warnings)`` for the race.json ``events`` array."""
    codes = _driver_codes(session)
    events: list = []

    # --- race control messages (convert the ABSOLUTE datetime64 first!) ---
    for row in session.race_control_messages.itertuples():
        t_s = (row.Time - session.t0_date) / pd.Timedelta(seconds=1)
        text = str(row.Message or "")
        upper = text.upper()
        mentions_sc = "SAFETY CAR" in upper
        deploy = mentions_sc and "DEPLOYED" in upper
        end = mentions_sc and ("IN THIS LAP" in upper or "ENDING" in upper)
        if deploy or end:
            kind = "vsc" if "VIRTUAL" in upper else "safety_car"
        else:
            kind = "race_control"
        driver = codes.get(str(row.RacingNumber)) if pd.notna(row.RacingNumber) else None
        events.append(
            {
                "t_s": t_s,
                "kind": kind,
                "status": None,
                "message": text if text else None,
                "driver": driver,
            }
        )

    # --- track status changes (Time is already session-relative) ---
    previous_status = None
    for row in session.track_status.itertuples():
        status = str(row.Status)
        if status == previous_status:
            continue  # collapse consecutive rows carrying the same status
        previous_status = status
        t_s = row.Time.total_seconds()
        message = str(row.Message) if pd.notna(row.Message) else None
        if status in SC_STATUS_KINDS:
            # Dedup against race control (see module docstring).
            near_boundary = any(
                e["kind"] in ("safety_car", "vsc")
                and abs(e["t_s"] - t_s) <= SC_DEDUP_WINDOW_S
                for e in events
            )
            if near_boundary:
                continue
            kind = SC_STATUS_KINDS[status]
        else:
            kind = "track_status"
        events.append(
            {"t_s": t_s, "kind": kind, "status": status, "message": message,
             "driver": None}
        )

    # --- window, order, exact-duplicate pass ---
    kept = [e for e in events if grid.t0_s <= e["t_s"] <= grid.t_end_s]
    dropped = len(events) - len(kept)
    warnings = []
    if dropped:
        warnings.append(
            f"timeline events: {dropped} event(s) outside the trimmed racing "
            f"window [{grid.t0_s:.3f}, {grid.t_end_s:.3f}] s were dropped "
            "(pre-race and post-race session activity, not part of the race replay)"
        )

    kept.sort(key=lambda e: e["t_s"])  # stable: ties keep source order
    deduped = []
    seen = set()
    for e in kept:
        key = (round(e["t_s"], 6), e["kind"], e["status"], e["message"], e["driver"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(e)
    return deduped, warnings
