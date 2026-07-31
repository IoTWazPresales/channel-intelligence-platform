# P1 Load defect log

**Phase:** P1 — Load the corpus  
**Locked:** 2026-07-30  
**Paired census:** [`docs/DATA_CENSUS.md`](DATA_CENSUS.md)  
**Discipline:** Defects go here. Fix inline **only** when `class=blocking`. Batch-fix at P1-X.

Shape mirrors [`docs/CI_API_DEFECT_LOG_2026-07-29.md`](CI_API_DEFECT_LOG_2026-07-29.md) (record first; fix later).

---

## Classes

| class | Meaning |
|-------|---------|
| `blocking` | Halted the load; fixed inline (or still open — blocks domain VERIFIED) |
| `continue` | Logged; load proceeded; batch at P1-X or defer to BACKLOG |

## Disposition values

| disposition | Meaning |
|-------------|---------|
| `open` | Not yet addressed |
| `fixed-inline` | Fixed during load because blocking |
| `batched` | Fixed at P1-X boundary |
| `deferred-BACKLOG-nnn` | Parked to a backlog id |

---

## Defects

| id | domain | period/grain | class | symptom | cip-evidence | disposition |
|----|--------|--------------|-------|---------|--------------|-------------|
| P1-D001 | DSI | job 604 steward products | blocking | Tokens ending `-CM`/`-E`/`-DEMO` stayed `no_match` though base sales models exist in PM (dealer/channel/demo tags). Embedded ASUS regex only covered some codes; prose names + `RC73XA…` missed. | Job 604: 55 suffix-tagged candidates; 50 exact PM hit after strip. Live `_resolve_product` after fix: backpack/RC73XA/mouse resolve; genuine gaps (`…2411288W`, `TM500MH-0R5220108W`) remain unresolved. | fixed-inline (`dsi_product_token_identity.channel_suffix_stripped_key`) |
| P1-D002 | shipment | open_order fact keys | blocking | Refresh of `ACZA …20260728` left soft-duplicate open-order facts: legacy `fact_upsert_key` used sheet segment `Unship` while new code lowercases to `unship`, so ON CONFLICT did not latest-job-win. | Pre-repair: 521 order/line/item collision groups; after delete-stale + normalize: open_order 1758→1237, collision groups 0, key_dupes 0. Job `#605` loaded. | fixed-inline (data repair; architecture already lowercases) |
| P1-D003 | CPOR | job 560 steward products | continue | Product trailers (`_Deal`/`-DG`/etc.) stayed `needs_review`; absolute accessory `no_match` blocked case apply. Ambiguous PM twins unchanged. | Evidence-gated one-level `-`/`_` strip in `product_identity_lookup_keys`; soak `#560`: +44 exact products resolved; 3 no_match → `ignore_no_catalogue` (10 lines skip_apply); active product no_match=0; cases **297** / lines **583**; queue product **115** (86 ambiguous + 29 needs_review) + 28 party. | fixed-inline (trailer strip + reuse DSI `ignore_no_catalogue`; steward leftovers = ambiguous/needs_review only) |
| P1-D004 | shipment | pod_date propagation | continue | Active `shipment_evidence_line` often has `pod_date`, but `shipment_evidence_current` / `fact_inbound_shipment` under-count landed vs evidence (Shipping KPIs read fact). | Active shipped evidence pod≈20 241 / null≈6 625; fact shipped pod=7 012 / null=6 117; current-view shipped pod=7 617 / null=6 529. | deferred-BACKLOG-088 |

---

## How to add a row

1. Assign next id `P1-D001`, `P1-D002`, …
2. Set `class` using the load-blocking table in `DATA_CENSUS.md`.
3. Link the census cell’s **Defect id** column to this id when bucket is `PARTIAL` or `DEFECT`.
4. Do **not** expand scope into BACKLOG-081 / new importers unless a NEW domain rule appears — then stop and CONSULT.
