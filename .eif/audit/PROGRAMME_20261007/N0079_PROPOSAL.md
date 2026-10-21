# N-0079 Budget ledger — proposal for D-0051 (draft for Warren)

Read-only; cip queried SELECT-only (`current_database()=cip`, 2026-10-07).

## AS-IS
- Old budget tables (`fact_budget_*`, `budget_health`, `dim_budget_owner`; models/facts.py:337-375): **0 rows each**, unlinked. `budgets.py:80-158` offers hard delete.
- `/budgets` (budgets/page.tsx:20) is a placeholder.
- Planner budget check (promo_plan_builder.py:812-846, lineup/budget_position.py:238-354): planned = lineup × SKU `reserve_total_pct` (31 SKU rows; 1 of 1,647 lineup items approved); drawn = Σ `ttl_support_usd` of **all** case lines by `pod_quarter` — **no status filter**, so drafts and cancelled cases (21 cancelled, $57k) count.
- Reapproval gate (budget_reapproval.py:19-21) counts proposed→settled as committed.
- Support bias (support_bias.py:128) uses the **campaign** reserve; the budget check uses the whole reserve. Two different "planned" numbers.
- Cases: 311 — 306 historical imports (211 settled $1.32M, 74 ended $242k, 21 cancelled), 5 native (3 draft, 2 cancelled). **No case has ever been approved or exported in-app** (0 `export_generated` events).
- Payment evidence: 3,375 rows, 2,718 paid/closed (ZAR), only 283 linked to a case.
- Warren's domain rules (COMMERCIAL_DOMAIN_RULES.md §1) already answer part of D-0051: 1.1 budget is **derived, not allocated**; 1.2 counts in the **landed** quarter; 1.6 unspent returns, cancel frees at once; 1.7 grain per sales model per customer, movable with audit trail; 1.10 50/50 is a **volume** split.

**Findings:** node title ("allocation") and D-0051 Q2 contradict rule 1.1. D-0051 Q3's "ASUS/customer cost share" reading has no support in docs or code.

## The five questions

**1 Grain.** *Recommend:* each ledger row is written at case-line grain (product × customer × landed quarter). Totals roll up two ways: product line × quarter (the PM view, spec §5 pivot) and customer × quarter. The limit check runs at product line × quarter. *Alt A:* check per customer × quarter. *Alt B:* keep one tenant-wide ceiling, as today. Reversible: yes, because both views are totals of the same rows.

**2 Who allocates.** *Recommend:* nobody types a pot (rule 1.1). Approving a lineup writes a **reserve** row from its derived reservation. Moving money is a **transfer** row: admin, or a planner on product lines where they have `can_edit` (`user_product_line_access`, 0 rows today). *Alt:* admin types an amount per product line per quarter. That is the old allocation shape, and it breaks rule 1.1. Reversible: medium.

**3 The 50/50.** *Recommend:* it is not a ledger rule. It is a normal-price vs discount volume split (rule 1.10; profit_reservation.py:18) and stays a planner default. The real question is another 50/50, `promo_reserve_split_pct` (campaign vs non-campaign reserve): recommend the ledger counts only the **campaign** part, matching support bias. *Alt:* count the whole reserve, as the budget check does today. Reversible: yes.

**4 Committed.** *Recommend:* the case's `approve` event, at `ttl_support_usd` using the FX rate booked at approval. Edits after approval and reapprovals write adjust rows; cancel writes a release row. Proposed cases show as "pending" without consuming headroom. *Alt:* approved and exported. But export only generates a file (cpor_exports.py:61), is not gated on approval, and proves nothing was sent. Reversible: medium.

**5 Consumed.** *Recommend:* the case's `settle` event, at `ttl_result_usd`. The same event writes a release row for commitment minus result (rule 1.6). Payment received is a separate **paid** row from linked payment evidence, used for reconciliation. *Alt:* consumed = paid; undercounts (283 of 3,375 payment rows link to a case; ZAR only). Reversible: medium.

## Data model sketch
One append-only table, `budget_ledger_entry`: `id, tenant_id, entry_type` (reserve | transfer | commit | commit_adjust | release | consume | paid), `product_line, customer_id, product_id?, landed_quarter, amount_usd, amount_local, fx_rate, case_id?, case_line_id?, payment_evidence_id?, source_event_id, actor, reverses_entry_id?, created_at`. Each row is written in the same transaction as its source event (lineup approve, transfer, case approve/patch/cancel/settle, payment apply). No updates or deletes; balances are sums; corrections are reversing rows. Forward-only from go-live. Optionally, add consume rows for the 211 settled historical cases, tagged `historical_import`.

## Screens
`/budgets`: product line × quarter grid (reserved, committed, pending, consumed, released, paid, remaining), drill to entries. Planner budget check, lineup budget position and reapproval gate read the ledger. Settlement desk shows commit/consume/paid. Retire hard-delete budget endpoints.

## Size
L, 3 units: (1) migration and writers on 6 events; (2) move the 3 readers; (3) page and transfer UI.

## Risks
- Landed quarter: `pod_quarter` missing on 10 of 658 lines; POD truthfulness open (BACKLOG-068/088).
- Products with no product line; FX booked vs floating (rule 1.5).
- Double counting while old and new readers overlap.
- Only 1 approved lineup item, so reserves start near zero. "No budget" should flag, not block.
