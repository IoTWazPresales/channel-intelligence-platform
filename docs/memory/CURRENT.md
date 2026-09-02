# CURRENT state

**Last updated:** 2026-09-02 (N-0013 r3.1 commercial amendment — Promotions & Funding · Market & Listings · four-state leaf status — D-0008 proposed, operator decisions required)

**Branch:** `feat/ns-2-brief-nav-collapse`

**Last content pin:** confirm HEAD with `git rev-parse` after commit

**Alembic (code):** `20260902_0020` (N-0006 FX enforcement)

**Alembic on cip:** `20260902_0020`

## On feat/ns-2-brief-nav-collapse

- **Programme:** PRG-20260831T145514 rev **273**; `verify` **ok** (no issues).
- **Operator rejection recorded (2026-09-02):** r2 package (Brief · Plan · Position · Settlement · Actions · Imports) rejected — D-0001/D-0003 superseded by **D-0004/D-0005**; **D-0002 deferred** (D-0006). Prior r1/r2 PASS records preserved in the log but no longer satisfy approval. Blocker `BL-OPERATOR-REJECTION-20260902`.
- **N-0013** **`blocked`** on operator acceptance of the **r3.1 package**: **D-0008 proposed** (supersedes D-0007, never accepted) — capability-domain rail (Overview · Stock & Sell-through · Supply & Inbound · Planning · **Promotions & Funding** · **Market & Listings** · Data & Stewardship · Administration[admin]); composed Overview (business dashboard + attention + pinned reports); entity context panel; command palette + capability directory; **four-state leaf status `live / partial / substrate / planned`** (binary data-gating withdrawn); export = canonical `cpor_case` ↔ per-customer template profile. Quality dims `authored_unverified` (author-rendered, no independent GOV-008 yet) — **not PASS**.
- **r3.1 commercial correction (operator truths):** promotion plan **is** the CPOR case (`cpor_case`/`cpor_case_line`), one lifecycle from planner to settlement → one domain; "Commercial inputs" removed (its `promotion_plan` / `price_observations` fixtures were not tables); listing intelligence + product competition = reusable evidence domain **Market & Listings**; nothing unbuilt rendered as working (Budget ledger / Competitor prices = data only; Competitor listings / Listing quality = planned). CONSULT (claude opus CLI) agreed on all six questions.
- **Prototype:** `apps/web/src/design-lab/**` + route group `apps/web/src/app/(design-lab)/` → `http://localhost:3000/design-lab`. New: `FundingSurface` lenses planner/templates/budgets, `PromotionPlannerSurface`, `PlanTemplatesSurface` (mounts production `CanonicalColumnMappingPanel`), `MarketSurface` (`/design-lab/market`), primitives `LifecycleRail` · `CapabilityLedger` · `CapabilityStatus`; `/design-lab/commercial` deleted. Fixtures only, no API, production routes untouched. Typecheck clean for design-lab.
- **Evidence:** `.eif/audit/NS_REDESIGN_R3_20260902/` — `OPERATOR_SUMMARY.md` (read first; r3.1 section at the end) · `DIRECTION.md` (amendment banner) · **`commercial/COMMERCIAL_DIRECTION.md`** (D-0007→D-0008 delta, IA, template architecture, N-0010 disposition, cross-domain links, open decisions) · `commercial/CAPABILITY_ACCOUNTING.md` · `commercial/CONSULT_SEED.md` / `CONSULT_RESPONSE.md` · `commercial/rendered-verification.md` + `commercial/renders/` (27 captures) · r3 artifacts unchanged (`FAULT_FINDINGS.md`, audits, `CONCEPTS.md`, `renders/proto/` 34 captures) · `EIF_REMEDIES_PROPOSAL.md` (EIF repo, **not applied**).
- **N-0010** **`blocked`** — **D-0009 proposed**: it is the "Actions container", not the planner; ACs cite rejected design input (doc/code contradiction recorded); proposal = retire framing, charter Promotions & Funding surface + Market & Listings surface + promotion-plan template profile after D-0008. **N-0011** `blocked` — depends on N-0013.
- **N-0004**, **N-0007**, **N-0008**, **N-0009**, **N-0012** complete (preserved).
- **N-0006** programme ledger still **`proposed`** — hygiene decision, separate from architecture.
- **Not committed by this run (pre-existing, left as-is):** `.eif/runtime/**`, `.cursor/hooks/eif_guard.py`, `.cursor/rules/eif-*.mdc`, `apps/web/src/app/(app)/plan-vs-executed/page.tsx` (3-line pre-existing diff).

## Programme frontier

- **N-0013** — **operator decisions required** (see `OPERATOR_SUMMARY.md` §"Your decisions" 1–5 and r3.1 §6–9: accept **D-0008**; D-0002 shape; design-language disposition; viewer visibility of Data & Stewardship; authorise EIF remedies session; **N-0010 disposition D-0009**; template-profile increment; Plan templates home).
- **N-0006** — FX ledger hygiene (not architecture-blocked).

**Blocked until D-0008 accepted:** N-0010, N-0011, Phase A / any production redesign implementation.

**Design language:** `docs/design/CIP_DESIGN_LANGUAGE.md` v1.1 is **under review** (FAULT_FINDINGS §1 recommends demote-to-reference + v2 from prototype primitives); do not treat as quality ceiling.

**Reconciliation evidence:** `docs/design/CIP_FULL_PLATFORM_RECONCILIATION.md` (50 capabilities; 0 RETIRE) — its "no reusable UI outside packages/ui" inference is **refuted** in `COMPONENT_ECOSYSTEM_AUDIT.md`.

**Deferred hygiene:** BACKLOG-156; BACKLOG-157; BACKLOG-158 (design-lab disposition after decision); BACKLOG-159 (EIF remedies); BACKLOG-160 (commercial doc/code contradictions: `market.py` readiness claim, `/promotions` scaffold notice, N-0010 ACs).

**Env:** local Windows. Web `:3000` + API `:8001`.
