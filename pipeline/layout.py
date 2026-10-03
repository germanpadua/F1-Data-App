"""data/export/ layout writer (P1.1): slugs, directories, atomic JSON writes.

Layout (from the Phase 1 contract):

    data/export/                     (gitignored)
      index.json
      <year>/<round>-<slug>/
        race.json
        replay.json
        tel/<DRIVER>.json

Every write is atomic (temp file + os.replace) so a crashed run can never
leave a half-written artifact behind.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

INDEX_FILENAME = "index.json"
RACE_FILENAME = "race.json"
REPLAY_FILENAME = "replay.json"
TEL_DIRNAME = "tel"


def slugify(text: str) -> str:
    """Lowercase, ASCII-alphanumeric runs joined by single hyphens."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    if not slug:
        raise ValueError(f"cannot slugify {text!r}")
    return slug


def race_slug(year: int, round_number: int, event_name: str) -> str:
    """e.g. 2026-15-azerbaijan-grand-prix"""
    return f"{year}-{round_number}-{slugify(event_name)}"


def race_dir(root: Path, year: int, round_number: int, event_name: str) -> Path:
    """<year>/<round>-<slug>/ directory for one race."""
    return Path(root) / str(year) / f"{round_number}-{slugify(event_name)}"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def atomic_write_json(path: Path, payload, *, indent: int | None = None) -> None:
    """Write JSON atomically: serialize first, then replace in one step."""
    path = Path(path)
    text = json.dumps(payload, indent=indent, allow_nan=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        # Best effort cleanup of the temp file on failure; the previous
        # artifact (if any) was never touched.
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def iter_race_dirs(root: Path):
    """Yield every race directory under root that contains a race.json."""
    root = Path(root)
    if not root.is_dir():
        return
    for year_dir in sorted(p for p in root.iterdir() if p.is_dir() and p.name.isdigit()):
        for race_dir_path in sorted(
            p for p in year_dir.iterdir() if (p / RACE_FILENAME).is_file()
        ):
            yield race_dir_path


def total_race_bytes(race_dir_path: Path) -> int:
    """Measured bytes of every artifact file of one race."""
    total = 0
    for name in (RACE_FILENAME, REPLAY_FILENAME):
        p = race_dir_path / name
        if p.is_file():
            total += p.stat().st_size
    tel = race_dir_path / TEL_DIRNAME
    if tel.is_dir():
        total += sum(p.stat().st_size for p in tel.glob("*.json"))
    return total
