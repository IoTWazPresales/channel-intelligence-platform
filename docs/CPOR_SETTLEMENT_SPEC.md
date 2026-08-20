# CPOR settlement — design decisions (2026-08-20)

**Status:** locked design for a future session. Not implemented as a unit.
**Origin:** Warren, 2026-08-20. Companion: `docs/STEWARD_ENGINE_DECISIONS.md` D-057–D-065.
**Does not replace** `docs/SPEC_CPOR_V1_AND_LISTING_CAPTURE_V0.md` (v1 substrate + waterfall).
Where this file and that spec disagree, **this file wins** for settlement / mid-case / MAC / audit.

Tree notes (contradictions, not smoothed) are in **§9** and the closing **Tree vs this spec** section.

---

## 1. Process today

Manual 11-hop chain after a case ends:

| Hop | Who | What |
|-----|-----|------|
| 1 | — | Case ends |
| 2 | Ken → KAM | Ken asks for results |
| 3 | KAM → customer | KAM asks the customer for the results report |
| 4 | customer → KAM | Customer returns the report |
| 5 | KAM → Ken | KAM forwards the report |
| 6 | Ken | Ken checks the report against the CPOR table |
| 7 | Ken → KAM | Ken sends the amount |
| 8 | KAM → customer | KAM sends the amount to the customer |
| 9 | customer → KAM | Customer confirms or disputes |
| 10 | KAM → Ken | KAM relays the confirmation or dispute |
| 11 | Ken | Ken closes |

**Hops the system removes** (once settlement is on the case):

- **2** — case-end is visible; Ken does not chase the KAM for a file.
- **5** — the report is uploaded and attached to the case (hop 4 lands on the case, not in Ken’s inbox).
- **6** — expected is computed from lines (units in each line’s window × that line’s rate). Ken does not re-key the table.
- **10** — confirm / dispute is a case event. KAM does not relay a second copy.

**Hops that stay human** until a customer portal exists (still out of scope):

- **3, 4** — KAM still asks the customer and the customer still returns a file.
- **7, 8, 9** — Ken still sends the amount via the KAM; the customer still confirms or disputes.
- **11** — Ken still takes the settle/close action. The system records it; it does not auto-close.

Hop **1** can be detected (window end) but does not auto-settle.

---

## 2. Roles

| Role | Person | Authority |
|------|--------|-----------|
| **KAM** | Warren | Proposes cases. Owns terms. Amends mid-case (MAC, added SKU, price). Customer-facing: asks for the report, sends the amount, takes confirm/dispute. |
| **PM** | — | Reviews and amends **proposals before approval only**. No authority after approval. |
| **Ken** | — | Compiles results into the CPOR table from the customer’s report, settles, sends for closure. **Does not touch MAC or terms.** |
| **MDM + Wayne** | — | Approve. **Wayne approves re-approvals.** |

IAM in the tree today is `admin` / `steward` / `planner` / `viewer` (`app/core/security.py`). These four CPOR roles are **not** in that enum. See §9.

---

## 3. Case model

- A case is a **set of lines**. Support and budget are **per SKU line, never case-level**.
- Each line carries a **week-aligned effective window** and a **fixed rate** (`support_unit` in the current waterfall — D-027: not a separate owed amount).
- **Terms never mutate after approval.** A change **supersedes**: the old line closes at the end of the prior week; a new line runs from the new week to the case end date. Same pattern for adding a SKU mid-case.
- Any mid-case amendment (MAC change, added SKU, price change) **re-flags for approval** and **the customer is notified**. The case **keeps running** throughout (no pause).
- **Cap is in units**, derived from a rand→USD ceiling. **FX is recorded at approval** (`roe_snapshot` already exists on `cpor_case`).
- **Over-cap flags and continues.** It does not stop the case.

Distinct from BACKLOG-095: money-ceiling `needs_reapproval` still **blocks approve/export** on the money axis. D-060 is the **unit** cap during an active case — flag, do not halt.

---

## 4. Mid-case behaviour

- Nothing is **chased or settled** mid-case. Flags accrue and resolve at the end.
- **Exception:** amendments (§3) happen when detected — re-flag for approval, notify the customer, supersede lines week-aligned, case stays running.

---

## 5. Customer MAC

- Derived **per customer × SKU**: anchored on the **first DSI sell-out** of that SKU to that customer, **weighted average forward**.
- **Editable**, with effect **from the edit forward** — never retrospective, never rewrites settled cases.
- The customer’s **weekly SOH report** carries their actual cost and is the **check, not the input**. Evetech is the one account with no SOH file.
- **Rebates are irrelevant to this:** the customer’s SOH cost is what they paid.
- **Weekly grain.** A week straddling a boundary is **flagged, never silently pro-rated**.
- **POD is ASUS→distributor and is NOT the customer’s cost.** Distributor sell-out is the customer’s purchase event.

This is **not** D-044 / D-049 planner MAC (intake-weighted / disti deals-only). Those remain the promo-planner cost legs. This series is customer×SKU, sell-out-anchored, steward-editable forward.

---

## 6. Settlement

- **Expected** = sum over lines of (units in **that line’s window** × **that line’s rate**).
  Compatible with D-027: rate is approved `support_unit`; `ttl_result = support_unit × result_qty`. Do not invent a second owed field.
- The customer’s report is **uploaded and attached to the case** — HQ audit artifact, not just a parse source. (`cpor_claim_evidence_line.raw_source_row` preserves parse rows; attachment of the original file is the missing piece.)
- **There is no negotiated middle.** Where figures disagree, the wrong input is found and corrected on the case, then recomputed until both sides align.
- Amendments are recorded as **case events**; the event trail is the justification.

---

## 7. Audit

- **Field-level events:** entity, field, old value, new value, actor, timestamp.
  Append-only; a correction is a new event.
- **Frozen snapshots** at approval and at settlement.
- **No write path is exempt.** Imports and agent decisions stamp an actor; a **null actor is a defect**.

Today `cpor_case_event` is `event_type` + `payload_json` + nullable `actor`. `_actor()` in `cpor_cases.py` / `cpor_exports.py` reads `X-User-Id` and may be null. That is the defect this section forbids going forward.

---

## 8. UI direction (not built)

Four surfaces:

| Surface | Job |
|---------|-----|
| **Overview** | Health + what needs you |
| **Cases** | Action-sorted worklist |
| **Precedent** | Query the settled corpus by customer / SKU / type / quarter |
| **Analysis** | Norms, BU, trends |

**Precedent must show delivery rate against support %** — that is the argument to a PM.

**Deleted as not unit-comparable** (do not ship as portfolio averages across mixed price points):

- “support per unit sold”
- “cost per incremental unit”

BACKLOG-089 closed an incremental-unit-cost **engine** (per-case, FLAG on weak baseline). This deletion is the **portfolio-average** of those ratios across mixed SRPs — not a silent unbuild of the per-case FLAG path. Do not put either ratio on Precedent/Analysis as a rolled average.

---

## 9. Known gaps blocking this

1. **`fact_inventory_customer` is empty; customer SOH is arriving and not landing there.**
   Tree: CST apply writes `reported_soh` / `unit_cost` / `unit_mac` to **`fact_customer_sellthrough`**, not `fact_inventory_customer`. `/inventory` still claims `fact_inventory_customer`. The SOH check in §5 can use CST facts **if** that is accepted; it cannot use `fact_inventory_customer` until that table is a writer target. **Do not treat CST landing as this gap closed.**
2. **CPOR routers have no authentication or role enforcement** for KAM / PM / Ken / Wayne.
   Tree nuance: some GETs (`list_cases`, `get_case`, a few intelligence/create paths) take `Depends(get_current_user)`. Most writes (patch, transition, recompute, claim import, settlement, export) do **not**. `require_roles` is unused on every `/cpor` router. Stub mode forges `admin` from headers. Role enum has no KAM/PM/Ken/Wayne.
3. **`cpor_case_line` has no effective window columns.**
   Windows exist on **`cpor_case`** (`window_start` / `window_end`). Settlement `_claim_in_window` uses the **case** window. Unique grain is `(case_id, product_id, distributor_id, pod_quarter)` — two open lines for the same SKU in one case (supersede mid-case) **cannot be stored** without a window (or equivalent) in the unique key.
4. **`cpor_case.superseded_by_case_id` is read and never written.**
   Readers in tree (more than three): `cpor_cases.py` (serialize), `incremental_unit_cost.py`, `payment_recon.py`, `portfolio_intelligence.py`, `support_bias.py`, `norms_and_comparable.py`, `listing_capture/cpor_activation.py`. Lineup’s `commercial_lineup_case.superseded_by_case_id` **is** written (`lineup_case_supersession.py`) — that is a different table. No CPOR writer.
5. **Named accounts still carry `TMP-CUST` codes.** Promote-in-place (BACKLOG-061, pruned as shipped) maps a code the operator supplies. **No mint scheme is in production.** CIP will mint its own codes, updatable later (D-065). ERP codes are an optional later mapping.
6. **`status` and `workflow_status` have drifted on ~4 rows.** Both columns exist on `cpor_case` (defaults `draft`). Lifecycle transitions in `lifecycle.py` talk to **`status`**. This session did **not** re-count the ~4 drifted rows on cip.

Backlog: **135–140** (this file’s §9). Do not mint codes or run a migration from this spec.

---

## Tree vs this spec (flag, do not smooth)

| This spec | Tree now |
|-----------|----------|
| Line-level week windows | Case-level dates only; claim rollup uses case window |
| Field-level audit; null actor is a defect | `cpor_case_event` + nullable `X-User-Id` |
| Frozen snapshots at approval and settlement | `source_snapshot_json` on lines; no case-level freeze pair |
| KAM / PM / Ken / Wayne | `admin` / `steward` / `planner` / `viewer`; CPOR writes mostly unauthenticated |
| Customer MAC series, forward edits | Cost suggestion + intake-weighted MAC on **lines**; no customer×SKU MAC master |
| Report attached as HQ artifact | Claim evidence parse + `raw_source_row`; original file not a first-class attachment |
| Over-cap (units) flags and continues | `cap_qty` nullable; money ceiling (095) can **block** export |
| Terms never mutate; supersede in-case | No line window; unique grain blocks two living lines per SKU |
| CIP-minted customer codes | `TMP-CUST-*` on named accounts; promote map exists, mint does not |
