# CURRENT state

**Last updated:** 2026-08-07 (PROGRAM-A Unit 6a landed — awaiting Opus VERIFY)

**Branch:** `feat/unit6a-po-unlink`

**Alembic:** `20260802_0009` (unchanged — no migration)

## Done

- **Unit 6a** BACKLOG-109 / W6-2 / W6-3 / D-037: steward unlink of active `commercial_lineup_case_po`.
  - Service `lineup_case_po_unlink.py`; API `GET/POST …/lineup/case-po-links[/unlink]`.
  - Web `PoCaseLinkWorklistSection` → `ResolutionWorklist` Unlink (`requiresTarget: false`) on Po Management.
  - Unit tests 2/2; vitest 2/2; clone C1–C4 PASS on `cip_unit6a_smoke`.
  - VERIFY seed: `.tmp/unit6a_verify_opus_seed.md`

## Next

1. Opus **VERIFY** 6a → PASS before **6b IMPLEMENT**.
2. Unit **6b**: customer stamp via alias (C) + first live `opts.target` (BACKLOG-112 / BACKLOG-123).

**Skip re-audit:** D-032…D-036, Unit 2 protection, S10 waiver (PoAutoLink only).

**Env:** local Windows. `cip` for app; clone proofs via TEMPLATE + `DATABASE_URL_SYNC_MIGRATE`. Local `.env`: `CIP_LINEUP_PROTECTED_CASE_IDS=145` (not committed).
