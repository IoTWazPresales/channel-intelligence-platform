# P1 Data census

**Phase:** P1 — Load the corpus  
**Locked:** 2026-07-30 (P1-entry CONSULT READY + Warren approve)  
**Paired defect log:** [`docs/P1_LOAD_DEFECT_LOG.md`](P1_LOAD_DEFECT_LOG.md)

## A1 quarter window

| Field | Value |
|-------|--------|
| **Window (Warren 2026-07-30)** | All quarters with lineup coverage on cip |
| **Credible core** | **26Q1 → current** — treat as the primary A1 reporting band |
| **Reporting rule** | Census always reports **coverage per quarter** so earlier periods can be narrowed if thin |
| **Placeholder until lineup load** | Period columns below start as `NOT_LOADED`; P1-5 fills actual quarters found |

Quarter labels are derived from **period dates**, never from file-name labels.

---

## Verified definition (all four must hold)

A cell is **VERIFIED** only when:

1. Rows exist on cip **and** the count reconciles to the source expectation (± stated tolerance in the verification sequence).
2. Every unresolved row sits in a steward queue — **zero silently-dropped rows, zero auto-created dims**.
3. Domain invariant holds for that load (see per-domain sections).
4. Warren has run that domain’s **numbered verification sequence** and said VERIFIED.

Until (4), the maximum bucket is `UNVERIFIED` even if counts match.

---

## Missing-bucket taxonomy

| Bucket | Meaning |
|--------|---------|
| `ABSENT` | No source for this period — legitimately empty (not a defect) |
| `NOT_LOADED` | Source exists (or expected); work remaining |
| `PARTIAL` | Count &lt; expected → **defect** (link defect-log id) |
| `STEWARD_PENDING` | Parked in steward queue — system working |
| `UNVERIFIED` | Counts/invariants look OK; Warren has not signed the verification sequence |
| `DEFECT` | Invariant violated → defect-log id |
| `VERIFIED` | All four verified criteria met |

---

## Load-blocking vs log-and-continue

| Class | Action |
|-------|--------|
| **blocking** | Halt load; fix inline (identity mis-map, auto-create dim attempt, CPOR case-code loss, job crash) |
| **continue** | Log in `P1_LOAD_DEFECT_LOG.md`; do not fix mid-load |

---

## Domain status summary

| Domain | Unit | Status | Sign-off |
|--------|------|--------|----------|
| Scaffold | P1-0 | Done | n/a |
| Header vocabulary (082) | P1-1 | **Done** — `20260730_0075` on cip; D-022 `_policy` live | code unit verified (pytest 20/20) |
| DSI weekly | P1-2 | Leave alone (pre-loaded) — sellout 35 592 / SOH 47 411 | Leave-alone (Warren) |
| Shipment inbound | P1-3 | Job `#605`; P1-D002 fixed; **14 366** facts / file evidence **7 328** | **Warren OK 2026-07-31** |
| CPOR historical | P1-4 | Job `#560`; P1-D003 fixed; **297** cases / **583** lines | **Warren OK 2026-07-31** |
| Lineups | P1-5 | **Leave-alone confirmed** — 3 `po_issued` (NR 26Q1, NV/NB 26Q2); **285** lines; **52** PO links; A1 = `/plan-vs-executed` | **Warren leave-alone OK** (2026-07-31; census sealed 2026-08-01) |
| Boundary batch-fix | P1-X | **Closed 2026-08-01** — D001–D003 fixed-inline; D004 → BACKLOG-088 | P1 exit |

---

## CPOR historical

**Grain:** case-code × quarter  
**Invariant:** case codes preserved on plan-apply (blocking if lost)  
**Headline metrics:** cases discovered / resolved / blocked / plan-applied; case-codes preserved (Y/N count); customers+products resolved vs steward-pending  
**Job:** `#560` · staging lines **17 256** · `ignore_no_catalogue` lines **10** · active product `no_match` **0**

| Period | Discovered | Resolved | Blocked | Plan-applied | Codes preserved | Cust resolved | Prod resolved | Steward pending | Bucket | Defect id |
|--------|------------|----------|---------|--------------|-----------------|---------------|---------------|-----------------|--------|-----------|
| historical (job 560) | 1 200 staging case-codes · 17 256 lines | **297** `cpor_case` (295 hist) / **583** lines | 838 staging cases still blocked | yes (ready maps + trailer exact +44) | Y — applied codes subset of staging; no code loss on apply | 12 296 lines | 13 697 lines | product **115** (86 ambig + 29 needs_review) + cust **27** + dist **1** | `STEWARD_PENDING` / `UNVERIFIED` | P1-D003 (fixed-inline) |

**Blocker mix (staging cases, multi-count):** duplicate_line_grain 375 · unresolved_product 666 · unresolved_customer 287 · unresolved_distributor 6 · missing_window 7 · missing_customer_token 3 · missing_product_token 1. Clear (applyable) staging cases: **294**.

---

## DSI weekly

**Grain:** distributor × layout-group × period  
**Invariant:** one job per layout group; no cross-layout bleed; header precedence = confirmed memory &gt; template alias &gt; heuristic  
**Headline metrics:** files / layout-groups / rows; customer resolution rate; product resolution rate; header-map source split (memory / alias / heuristic)  
**Note (P1 lock):** do not re-touch DSI this phase — corpus already on cip.

| Period | Distributor | Layout group | Files | Rows in | Rows out | Cust res % | Prod res % | Map: memory | Map: alias | Map: heuristic | Bucket | Defect id |
|--------|-------------|--------------|-------|---------|----------|------------|------------|-------------|------------|----------------|--------|-----------|
| pre-P1 corpus | — | — | — | sellout 35 592 | SOH 47 411 | — | — | — | — | — | `UNVERIFIED` (leave alone) | — |

---

## Shipment inbound

**Grain:** customer-PO × product × period, by `line_state`  
**Invariant:** `line_state` gate (`shipped` ≠ `open_order`); shipping module remains lifecycle authority for `pod_date`  
**068 obligation (measurement only):** cell is not VERIFIED until **`pod_date` present vs NULL %** and shipped-not-landed gap are stated per period  
**Headline metrics:** rows; shipped / open_order / unshipped; `pod_date` present vs NULL %; resolution rate  
**Job:** `#605` · P1-D002 open-order key casing repaired

| Period | Rows | Shipped | Open order | Unshipped | pod_date present % | pod_date NULL % | Shipped-not-landed | Res % | Bucket | Defect id |
|--------|------|---------|------------|-----------|--------------------|-----------------|--------------------|-------|--------|-----------|
| job 605 corpus | **14 366** (all jobs) · this file evidence **7 328** | **13 129** | **1 237** | — | **48.8%** (7 012) | **51.2%** (7 354) | shipped∧NULL pod **6 117** | file Unship **799**/799 applied; Shipped file **6 538** → evidence **6 529** → ~**441** evidence still unmatched to facts (steward) | `UNVERIFIED` | P1-D002 (fixed-inline); **14k ≠ file** — cumulative fact table |

---

## Lineups

**Grain:** product × customer × quarter (A1 window)  
**Invariant:** quarter derived from period dates, never labels  
**Headline metrics:** quarters covered; lineup lines; PO auto-link coverage; gaps/quarter  
**Credible core:** 26Q1 → current (report all covered quarters; flag thin earlier periods)  
**Note:** already allocated on cip — **do not rebuild**; A1 = existing `/plan-vs-executed`.

| Quarter | Lineup lines | Products | Customers | PO auto-link % | In credible core? | Thin? | Bucket | Defect id |
|---------|--------------|----------|-----------|----------------|-------------------|-------|--------|-----------|
| 26Q1 NR (`#90` po_issued) | **104** lines · **23** PO links | — | — | 23 links / 1 case | yes | thin vs full history | `UNVERIFIED` (leave-alone) | — |
| 26Q2 NV (`#7` po_issued) | **22** lines · **1** PO link | — | — | 1 / 1 | yes | thin | `UNVERIFIED` (leave-alone) | — |
| 26Q2 NB (`#9` po_issued) | **159** lines · **28** PO links | — | — | 28 / 1 | yes | thin vs full history | `UNVERIFIED` (leave-alone) | — |
| **P1-5 total** | **285** lines · **52** PO links · **3** cases | — | — | — | 26Q1–26Q2 | yes | leave-alone sealed | — |

---

## Sign-off log

| Domain | Date | Warren VERIFIED? | Notes |
|--------|------|------------------|-------|
| DSI | 2026-07-31 | leave-alone | Pre-loaded; P1-2 do not re-touch |
| Shipment | 2026-07-31 | **yes** | `#605` file ~7.3k evidence; UI 14 366 = full corpus; Unship 799/799; ~441 shipped evidence unmatched (steward) |
| CPOR | 2026-07-31 | **yes** | ~297 cases OK |
| Lineups | 2026-07-31 / sealed 2026-08-01 | **leave-alone OK** | 3 po_issued + 52 PO links; census rows above; do not rebuild; A1 = existing `/plan-vs-executed` |
| P1-X census | 2026-08-01 | **P1 closed** | Defect batch: D001–D003 fixed-inline; D004 → BACKLOG-088. Exit artifacts: this file + `P1_LOAD_DEFECT_LOG.md` |
