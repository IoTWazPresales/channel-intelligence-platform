# CURRENT state

**Last updated:** 2026-09-02 (N-0013 r3 design package — React prototype + rendered evidence — operator decisions required)

**Branch:** `feat/ns-2-brief-nav-collapse`

**Last content pin:** confirm HEAD with `git rev-parse` after commit

**Alembic (code):** `20260902_0020` (N-0006 FX enforcement)

**Alembic on cip:** `20260902_0020`

## On feat/ns-2-brief-nav-collapse

- **Programme:** PRG-20260831T145514 rev **254**; `verify` **ok** (no issues).
- **Operator rejection recorded (2026-09-02):** r2 package (Brief · Plan · Position · Settlement · Actions · Imports) rejected — D-0001/D-0003 superseded by **D-0004/D-0005**; **D-0002 deferred** (D-0006). Prior r1/r2 PASS records preserved in the log but no longer satisfy approval. Blocker `BL-OPERATOR-REJECTION-20260902`.
- **N-0013** **`blocked`** on operator acceptance of the **r3 package**: **D-0007 proposed** — capability-domain rail (Overview · Stock & Sell-through · Supply & Inbound · Planning · Funding & Settlement · Commercial inputs · Data & Stewardship · Administration[admin]); composed Overview (business dashboard + attention + pinned reports); entity context panel; command palette + capability directory; data-gated leaves. Quality dims recorded `authored_unverified` (author-rendered, no independent GOV-008 yet) — **not PASS**.
- **Prototype:** `apps/web/src/design-lab/**` + route group `apps/web/src/app/(design-lab)/` → `http://localhost:3000/design-lab`. Fixtures only, no API, production routes untouched. Typecheck/lint clean for design-lab.
- **Evidence:** `.eif/audit/NS_REDESIGN_R3_20260902/` — `OPERATOR_SUMMARY.md` (read first) · `DIRECTION.md` · `FAULT_FINDINGS.md` · `PRODUCT_CAPABILITY_AUDIT.md` · `COMPONENT_ECOSYSTEM_AUDIT.md` · `CONCEPTS.md` · `CONSULT_SEED.md` / `CONSULT_RESPONSE.md` (claude opus, separate process) · `rendered-verification.md` + `renders/proto/` (34 captures, 1280×800 + 390×844, `manifest.json`) · `EIF_REMEDIES_PROPOSAL.md` (EIF repo, **not applied**).
- **N-0010** / **N-0011** **`blocked`** — depend on N-0013.
- **N-0004**, **N-0007**, **N-0008**, **N-0009**, **N-0012** complete (preserved).
- **N-0006** programme ledger still **`proposed`** — hygiene decision, separate from architecture.
- **Not committed by this run (pre-existing, left as-is):** `.eif/runtime/**`, `.cursor/hooks/eif_guard.py`, `.cursor/rules/eif-*.mdc`, `apps/web/src/app/(app)/plan-vs-executed/page.tsx` (3-line pre-existing diff).

## Programme frontier

- **N-0013** — **operator decisions required** (see `OPERATOR_SUMMARY.md` §"Your decisions": accept D-0007; D-0002 shape; design-language disposition; viewer visibility of Data & Stewardship; authorise EIF remedies session).
- **N-0006** — FX ledger hygiene (not architecture-blocked).

**Blocked until D-0007 accepted:** N-0010, N-0011, Phase A / any production redesign implementation.

**Design language:** `docs/design/CIP_DESIGN_LANGUAGE.md` v1.1 is **under review** (FAULT_FINDINGS §1 recommends demote-to-reference + v2 from prototype primitives); do not treat as quality ceiling.

**Reconciliation evidence:** `docs/design/CIP_FULL_PLATFORM_RECONCILIATION.md` (50 capabilities; 0 RETIRE) — its "no reusable UI outside packages/ui" inference is **refuted** in `COMPONENT_ECOSYSTEM_AUDIT.md`.

**Deferred hygiene:** BACKLOG-156; BACKLOG-157; BACKLOG-158 (design-lab disposition after decision); BACKLOG-159 (EIF remedies).

**Env:** local Windows. Web `:3000` + API `:8001`.
