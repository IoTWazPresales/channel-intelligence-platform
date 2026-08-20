# CURRENT state

**Last updated:** 2026-08-20 (CPOR settlement spec on main)

**Branch:** `main`

**Last content pin:** `3eeafdf` — do not treat a hash in this file as HEAD

**Alembic (code):** `20260818_0018` (`20260818_0018_report_delivery_email_channel.py`)

**Alembic on cip:** `20260818_0018` (head)

## On main

- Merged `fix/merged-customer-resolver-guard` at `57528c5`.
- **CPOR settlement design** (docs only): `docs/CPOR_SETTLEMENT_SPEC.md`. D-057–D-065. BACKLOG-135–140 for §9 gaps. No code / no migrations.

## Next

Settlement / MAC / line-windows are **not** started. Resume from the spec + D-057–D-065; pick a BACKLOG-135–140 TRIGGER rather than re-deriving. Clone DB `cip_merged_leftover_repair` can still be dropped when convenient.

**Env:** local Windows. Web `:3000` + API `:8001`.
