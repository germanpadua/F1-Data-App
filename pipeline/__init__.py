"""Static export pipeline (Phase 1).

Turns a completed FastF1 session into compact, versioned, self-describing
JSON artifacts under ``data/export/`` (gitignored). The data contract lives
in ``odd/tasks/phase-1-export-pipeline.md``.

Entry points:
    python -m pipeline.export --year Y --round N [--session R] [--out DIR]
    python -m pipeline.check --root data/export
"""
