"""Published-season scope: WHICH exported seasons are published to Blob.

This module is a DECLARED, DOCUMENTED DECISION, not something to be
discovered implicitly. Before it existed, the CI derived the current year
at runtime, so the fact that only the 2026 season is published was
invisible. Now it is written down here, in one place.

WHAT THIS SCOPE IS AND IS NOT
-----------------------------

- This is a **publishing** scope and nothing else. It decides which
  seasons are uploaded to public object storage (Vercel Blob) by
  ``tools/blob-publish/publish.mjs`` and by the CI job that calls it.
- It is NOT an export limitation. The CLI can still export any season
  locally for any year FastF1 has data for, with
  ``python -m pipeline.export --year Y --round N`` or the backfill
  ``--all-completed``. Nothing in the export path reads this module.
- The scope is enforced at PUBLISH time only, never at export time:
  ``pipeline/export.py`` and ``pipeline/check.py`` are deliberately
  scope-blind.

WHY IT EXISTS
-------------

The publisher is bounded to one season so the total published payload
stays well inside Vercel Blob's free tier (1 GB). Measured: one race is
9 822 254 B, so a completed 15-round season is roughly 147 MB — about 15%
of the free tier. Publishing every season ever exported would eventually
exceed it for no present benefit.

HOW TO WIDEN IT
---------------

A one-line change: add the year to the tuple below (and update
``tools/blob-publish/publish.mjs``, which mirrors this constant because
the publisher is Node and cannot import Python). Nothing else needs to
change: export, backfill, self-check and CI are all scope-blind, and the
publisher uploads every in-scope race it finds on disk.
"""
from __future__ import annotations

# Seasons whose artifacts are published to Vercel Blob. See the module
# docstring: publishing scope only, one line to widen.
PUBLISHED_SEASONS: tuple[int, ...] = (2026,)


def is_published(year: int) -> bool:
    """True when artifacts of this season are published to Blob."""
    return year in PUBLISHED_SEASONS
