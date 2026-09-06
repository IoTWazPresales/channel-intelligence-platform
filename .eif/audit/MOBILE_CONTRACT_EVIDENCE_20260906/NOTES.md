# Mobile support contract — evidence recovery (do not decide)

**Date:** 2026-09-06  
**Purpose:** Recover what was actually specified. Not a decision. Reconcile before Design Language v2.  
**D-0002:** untouched.

This is not full responsive parity, not a generic “mobile is read-only”, and not “desktop only”.
The named contract is **desktop-primary with a listed set of away-from-desk workflows at 390px**, plus
**desktop-first authoring that degrades to read-only / cards** rather than an “open on desktop” wall.

## Operator buckets (mapped, not chosen)

| Bucket | Evidence fit |
|---|---|
| Full responsive parity | **Does not fit.** DIRECTION §6 and CONSULT Q6 list desktop-first workflows that are intentionally not card-transformed. |
| Read-only | **Partial only.** Authoring (grids, mapping, report builder, dashboard editor) degrades to read-only / cards. Funding **approve/return** is an explicit mobile *write*. |
| Attention plus approvals and actioning | **Close, incomplete.** CONSULT Q6: “attention / approval / lookup”. DIRECTION §6 adds stock cover lookup, import status, command palette, bottom nav. r3.1 adds promotion-planner review-and-approve cards. |
| Desktop-primary with selected workflows | **Fits the framing** (“which workflows earned 390px”) **if** the selected set is the DIRECTION table, not an unspecified subset. |

## Primary sources (in order)

1. **N-0013 acceptance criterion** (PROGRAM.yaml / `record_operator_rejection.py`):  
   `Rendered evidence: 1280px every prototyped surface; 390px shell + every mobile-required workflow; each claim cites screenshot + viewport`
2. **DIRECTION.md §6** — “Mobile — which workflows earned 390px”  
   `.eif/audit/NS_REDESIGN_R3_20260902/DIRECTION.md`
3. **CONSULT Q6** (claude-opus-4-8, separate process)  
   `.eif/audit/NS_REDESIGN_R3_20260902/CONSULT_RESPONSE.md`
4. **Capture script** that operationalised “390px: shell + mobile-required workflows”  
   `.eif/audit/NS_REDESIGN_R3_20260902/capture_renders.mjs`
5. **GOV-008 N-0013** treated that AC as the referent; sampled ≥3 mobile routes  
   `.eif/audit/NS6_GOV008_R3_20260903/independent-rendered-review.md` §7
6. **D-0008** (accepted): “Everything else in D-0007 unchanged” — D-0007’s prototype includes DIRECTION §6. Commercial r3.1 adds 390px planner/listings captures, not a replacement mobile doctrine.
7. **Production shell** copied the lab bottom-nav pattern: `AppShell.tsx` `MOBILE_PRIMARY = ['overview', 'stock', 'funding', 'data']` + `display: { xs: 'block', md: 'none' }`.

## DIRECTION §6 table (the enumerated 390px set)

| Workflow | Mobile treatment | Capture |
|---|---|---|
| Attention triage | Attention zone first via `?zone=attention` | `m-attention.png` |
| Funding approval / return | Record cards; full-screen case; sticky approve/return | `m-funding-cards.png`, `m-funding-case.png`, `m-funding-approved.png` |
| Stock cover lookup (breaches) | Headlines 2-up; chart stacked; breach rows as cards | `m-stock-breaches.png` |
| Import status check | Job list as record cards | `m-data-imports.png` |
| Find anything | Command palette full-width | `m-command-palette.png` |
| Navigation | Bottom nav (4 domains + More) + full drawer | `m-overview.png`, `m-drawer.png` |

**Desktop-first (not card-transformed):** report builder, dashboard editor, lineup planning grid, import column mapping.

**Grid rule:** decision/lookup → record cards; comparison/ranking → frozen first column (no generic “open on desktop”).

## CONSULT Q6 (broader than the DIRECTION table)

Genuinely mobile = attention / approval / lookup, not authoring. Explicitly includes steward/mapping approve-reject and settlement/CPOR status / blocked-item approval. DIRECTION §6 **did not** put steward-queue approve-reject in the earned-390px table (import status instead). That gap is unresolved.

## r3.1 commercial (additive, author-rendered)

`.eif/audit/NS_REDESIGN_R3_20260902/commercial/rendered-verification.md`:
- CM1–CM5: planner / plan workspace / line evidence / activation / listings at 390×844
- “review-and-approve is the mobile job; cell editing stays desktop”
- templates lens reachable but not card-transformed

Lab `m-*` still present under `.eif/audit/NS6_GOV008_R3_20260903/renders/` (`m-directory`, `m-funding`, `m-market`, `m-overview`, `m-pf-planner*`).

## What later production units did

N-0004 / N-0007 / N-0008 / N-0009 quality records include `desktop_1280` **and** `mobile_390` (Brief drawer; Stock regime strip wrap; Settlement/Lineup scope bar wrap).

Cover / Movement / Execution migrations (2026-09-06) verified **1280×800 only** on operator instruction. That is a **verification-scope cut**, not a recorded replacement of DIRECTION §6. It is the conflict to reconcile before Design Language v2 — not evidence that the contract was repealed.

## Conflict to reconcile (not resolved here)

- **Specified:** 1280 every prototyped surface; 390 shell + named mobile-required workflows (DIRECTION §6 + r3.1 commercial cards).
- **Shipped in production:** bottom nav + xs stacking exist; 390px **verification** was dropped for recent Stock lens migrations.
- **Open vs CONSULT:** steward-queue approve-reject at 390px was CONSULT-mobile and not in the DIRECTION capture table.

Do not author Design Language v2 until Warren picks among those.
