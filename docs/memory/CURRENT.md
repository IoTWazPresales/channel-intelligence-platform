# CURRENT state

**Last updated:** 2026-08-31 (VERIFY debt cleared; NS-2 readiness)

**Branch:** `main`

**Last content pin:** `12404bc` — confirm HEAD with `git rev-parse`

**Alembic (code):** `20260818_0019` (`20260818_0019_shipping_mailer_recipient.py`)

**Alembic on cip:** `20260818_0019`

## On main

- **VERIFY debt cleared (2026-08-31 · `12404bc`).** All seven charter v1.3 amendment 7 units
  (6f, 7, 8, 11, 12, 15B, B4) closed with Opus CONSULT fourth-pass PASS; register empty in
  `docs/BACKLOG.md`. Promotion to `main` no longer gated by VERIFY debt.
- **Design language FROZEN v1.1** + nav map + charter v1.3 governing (`83b4290` promotion).
- **NS-1a display groundwork** in tree (`settle_readiness.py`, `missing_roe` on CPOR list/detail)
  — BACKLOG-148 not formally VERIFY-closed as a north-star unit.
- **NS-2 readiness** documented in `docs/design/NS2_READINESS.md` — discovery only; no
  implementation this session.

## VERIFY arc findings (retained)

- 19 web tests broken by RBAC `5b2a6a4` — fixed via `importOriginal` partial mock
  (`WEB_TEST_FAILURE_DIAGNOSIS.md`).
- HL mapping parity gap closed (Unit 11 fix pass).
- Shipment steward S2/S3/S4 closed (tab reset, debounced search, confidence band).
- S11 apply stall = worker/API DB binding mismatch, not product defect.

## Deferred (not VERIFY debt)

- CPOR case #313 on `cip` (SESSION F fixture contamination).
- Evidence-chip pass state unproven — no dev case with claim evidence rows.
- HL disposition backend gap — no disposition channel; `mapping_override` only.

## Next

- **NS-2** (BACKLOG-149): nav collapse + Brief landing per `docs/design/NS2_READINESS.md` when
  Warren schedules unit start (BACKLOG-148 FX display or waiver still on TRIGGER).
- Shared shell extraction feeds NS-3–NS-7.

**Env:** local Windows. Web `:3000` + API `:8001`.
