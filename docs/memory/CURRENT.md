# CURRENT state

**Last updated:** 2026-09-03 (D-0008 production shell/nav copy slice — uncommitted; N-0013 remains complete)

**Branch:** `feat/ns-2-brief-nav-collapse`

**Last content pin:** confirm HEAD with `git rev-parse` after commit

**Alembic (code):** `20260902_0020` (N-0006 FX enforcement)

**Alembic on cip:** `20260902_0020`

## On feat/ns-2-brief-nav-collapse

- **Programme:** PRG-20260831T145514 rev **294**; `verify` **ok**. N-0013 **complete** (node rev 105). Frontier: **N-0006** only.
- **D-0008 accepted** (r3.1 capability-domain IA). **D-0002** remains **proposed**. **D-0009** remains **proposed**. Do not resolve either. Do not reopen N-0013.
- **Implementation ACs I1–I5** remain design-lab capability work, not this shell slice.
- **Production D-0008 shell/nav copy (uncommitted):** leftover product-surface IA/copy reconciled (getting-started/dashboard fallbacks, empty-state CTAs, admin/reports crumbs, Plan vs Executed live links → Execution vs plan `/stock?lens=execution`, Import Center naming, stock lens switcher labels). Middleware compatibility routes kept. Live pages no longer href retired URLs.
- **Tests:** `@cip/web` vitest **107 files / 583 passed**. Focused planner/PO/nav tests also passed after copy changes. `pnpm typecheck` still fails on **pre-existing** errors (CST aliases test types, shipment-evidence fixture types, settings/shipping-mailer `data-testid` slots) — not introduced by this slice.
- **Rendered (browser, localhost:3000):** `/brief`, `/getting-started`→`/brief`, `/dashboard`→`/brief`, `/promotions`, `/commercial-planner/cpor-cases`, `/admin/customer-commercial-terms`, `/competition`, `/listing-capture`, `/admin/imports`, `/admin/mappings`, `/sell-out`→`/stock?lens=movement`, `/shipping`→`/stock?lens=inbound`, `/admin/users`, `/reports`, `/commercial-planner` (guide), `/admin/po-management`, `/stock?lens=movement` after lens-label update. Attention body showed API error “Could not load attention signals” (API/auth), not a nav-copy miss. Inner ChannelOps “Sell-out” tab kept as metric language.
- **Do not stage:** `.cursor-recovery/`, `.eif/runtime/**`, `.cursor/hooks/eif_guard.py`, `.agents/`. Not committed (operator asked to wait until this slice was green + rendered).

## Programme frontier

- **N-0006** — FX ledger hygiene.
- **Production D-0008** — shell/nav copy slice ready to commit on request. Next product work: capability implementation slices (I1–I5) or N-0006. Do not opportunistically retouch design-lab fixtures.

**Design language:** `docs/design/CIP_DESIGN_LANGUAGE.md` v1.1 is **under review**; do not treat as quality ceiling.

**Deferred hygiene:** BACKLOG-156; BACKLOG-157; BACKLOG-158; BACKLOG-159; BACKLOG-160.

**Env:** local Windows. Web `:3000` + API `:8001`.
