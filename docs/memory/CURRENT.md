# CURRENT state

**Last updated:** 2026-08-08 (PROGRAM-A Unit 6f — D-040 distributor attribution propose→confirm)

**Branch:** `feat/unit6f-distributor-attribution-confirm` (from Unit 6c @ `03a5c19`)

**Alembic:** `20260807_0010` (distributor_attribution_status on commercial_lineup_line)

## Done

- **Unit 6f / D-040:** first-class `distributor_attribution_status`
  (`token_proposed` | `steward_set` | `shipment_confirmed` | `conflict`).
- Stamp sets `token_proposed`; confirmer (product+period+exact qty) confirms / conflicts
  without auto-clearing FK; Accept ship-corroborated; soft-clear dist-only; override.
- Worklist ship-offer CTA + `DistributorAttributionReviewSection` on PO management.
- cip remediation: backfill proposed; confirmer; `sadc homeless`→OC+Stylus 45
  (`steward_set`); **DCC left**; protected cases 7/90/122/145 stable.
- Docs: D-038 amended; D-040 locked; BACKLOG-127 (DAP), BACKLOG-128 (Stylus PO-link).
- CONSULT CLI Opus/Fable WAIVED (spend limit) — Human-approved plan = lock.

## Next

1. **Browser smoke** residual if not done in-session: attribution review + Accept ship CTA.
2. **BACKLOG-124** — empty_token (mandate resumes after 6f).
3. BACKLOG-125 / 126 residual stems without ship sole.
4. Roadmap A1∥A2∥A3 only after Warren confirms 124 handling.

**Env:** local Windows. `cip` @ `20260807_0010`. Smoke clone `cip_unit6c_smoke` also at head.
