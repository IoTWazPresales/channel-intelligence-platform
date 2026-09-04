# CURRENT state

**Last updated:** 2026-09-04 (GOV-008 CONSULT model caveat VERIFIED; N-0013 remains complete; not reopened)

**Branch:** `feat/ns-2-brief-nav-collapse`

**Last content pin:** confirm HEAD with `git rev-parse` after commit

**Alembic (code):** `20260902_0020` (N-0006 FX enforcement)

**Alembic on cip:** `20260902_0020`

## On feat/ns-2-brief-nav-collapse

- **Programme:** PRG-20260831T145514 rev **294**; `verify` **ok**. N-0013 **complete** (node rev 105). Frontier: **N-0006** only.
- **D-0008 accepted** (r3.1 capability-domain IA). **D-0002** remains **proposed**. **D-0009** remains **proposed**. Do not resolve either. Do not reopen N-0013.
- **CONSULT provenance (GOV-008 addendum, 2026-09-04):** `consult_model_logged` is **VERIFIED** from Claude Code CLI session jsonl (`claude-opus-4-8`, `entrypoint=sdk-cli`, `promptSource=sdk`, Claude Code 2.1.202, `stop_reason=end_turn`): `ce2fbf92-…` (IA, 2026-09-02T16:49:43Z) and `46068c16-…` (commercial, 21:34:04Z) under `~/.claude/projects/C--Users-warren-eliason-channel-intelligence-platform/`. Verdicts unchanged. N-0013 not reopened. Seq 287 in `PROGRAM_LOG.ndjson` remains `UNVERIFIED` (append-only; no engine event for post-hoc caveat resolution — BACKLOG-169). Session logs live outside the repo and are not durable long-term.
- **Implementation ACs I1–I5** remain design-lab capability work, not this shell slice.
- **Production D-0008 shell/nav copy (uncommitted):** leftover product-surface IA/copy reconciled (getting-started/dashboard fallbacks, empty-state CTAs, admin/reports crumbs, Plan vs Executed live links → Execution vs plan `/stock?lens=execution`, Import Center naming, stock lens switcher labels). Middleware compatibility routes kept. Live pages no longer href retired URLs.
- **Tests:** `@cip/web` vitest **107 files / 583 passed**. Focused planner/PO/nav tests also passed after copy changes. `pnpm typecheck` still fails on **pre-existing** errors (CST aliases test types, shipment-evidence fixture types, settings/shipping-mailer `data-testid` slots) — not introduced by this slice.
- **Rendered (browser, localhost:3000):** `/brief`, `/getting-started`→`/brief`, `/dashboard`→`/brief`, `/promotions`, `/commercial-planner/cpor-cases`, `/admin/customer-commercial-terms`, `/competition`, `/listing-capture`, `/admin/imports`, `/admin/mappings`, `/sell-out`→`/stock?lens=movement`, `/shipping`→`/stock?lens=inbound`, `/admin/users`, `/reports`, `/commercial-planner` (guide), `/admin/po-management`, `/stock?lens=movement` after lens-label update. Attention body showed API error “Could not load attention signals” (API/auth), not a nav-copy miss. Inner ChannelOps “Sell-out” tab kept as metric language.
- **Do not stage:** `.cursor-recovery/`, `.eif/runtime/**`, `.cursor/hooks/eif_guard.py`, `.agents/`. Not committed (operator asked to wait until this slice was green + rendered).

## Programme frontier

- **N-0006** — FX ledger hygiene.
- **Production D-0008** — shell/nav copy slice ready to commit on request. Next product work: capability implementation slices (I1–I5) or N-0006. Do not opportunistically retouch design-lab fixtures.

**Design language:** `docs/design/CIP_DESIGN_LANGUAGE.md` v1.1 is **under review**; do not treat as quality ceiling.

**Deferred hygiene:** BACKLOG-156 … BACKLOG-165; BACKLOG-166 (CONSULT invocation record); BACKLOG-167 (seed/response transcription vs capture); BACKLOG-168 (AI resolver missing `ANTHROPIC_API_KEY` must fail loudly); BACKLOG-169 (engine cannot record post-hoc caveat resolution).

**Env:** local Windows. Web `:3000` + API `:8001`.
