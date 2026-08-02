# CURRENT state

**Last updated:** 2026-08-02 (corpus restore STOP before apply — collision worklist)

**Branch:** `main` (ahead of origin)

**Alembic:** `20260802_0009` · no migration this unit

## Done

- P2 corpus-safety `01e55d2` present; job 255 terminal `failed`.
- A0: both delete→steward_audit paths proven on `cip_alembic_smoke` (not cip).
- A1–A4 + Phase B preview: session_import_job_id=**752**, archive 28 files (+ stray sample), 35 ready / 15 attention / 3508 lines; PF 1H Gaming Desktop → Q1+Q2 ready; `existing_case_collisions=0` despite filename overlap with cases 7/9/90 (sheet/notes null — BACKLOG-104).

## STOP — Phase C not started

Apply would create **duplicate** draft cases for filenames of survivors 9/90 (and period-shifted 7) without modifying them. Awaiting Warren exclude/confirm list (BACKLOG-102) or detector fix (BACKLOG-104).

## Next

1. Warren: exclude proposal keys for overlaps with 7/9/90 (or accept duplicates) → resume apply.
2. Then D1–D4 validation + BACKLOG-103 (unified 1H fan-out) remains parked.

**Env:** local Windows. `cip`. Preview job 752 on cip (no lineup rows written by preview).
