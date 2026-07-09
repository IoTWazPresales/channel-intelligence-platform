# BACKLOG-061 — Promote-in-place design (Phase A)

**Status:** Design only · 2026-07-09  
**Branch base:** `5f55567` / feature tip after Phase A commit  
**Authoritative backlog:** `docs/BACKLOG.md` BACKLOG-061 (do not rewrite)  
**Phase B:** implement only after Fable PASS on this design + Warren gate on any schema delta

---

## 1. Problem (evidence-backed)

There is **no promote-in-place** path today. Operators can:

| Path | Same id? | Assigns real code? | Status flip? |
|------|----------|--------------------|--------------|
| Merge (`customer_full_merge` / alias-scope / `distributor_full_merge`) | No — loser soft-redirects | Survivor keeps code | Loser → `merged` |
| PATCH customer | Yes | **No** (`CustomerPatch` has no code) | Yes (allow-list) |
| Bulk upsert-by-code | New row if code unknown | Yes on new row | New → `active` |

Cost without promote: provisional rows keep `TMP-*` codes; later imports that key by real business code **mint duplicates** while the TMP row remains. Soft-redirect merge is the only governed cleanup, and it changes identity (loser id).

---

## 2. Discovery summary (Phase A)

### 2.1 Status taxonomy

| Surface | Values |
|---------|--------|
| DB `dim_customer.customer_status` (cip) | `unverified` 4893 · `merged` 75 · `active` 11 · **`verified` 7** |
| DB `dim_distributor.distributor_status` (cip) | **`active` 25 only** |
| API `ALLOWED_CUSTOMER_STATUS` | `{active, inactive, onboarding, blocked, unverified, needs_review}` — **no `verified`, no `merged`** (`customers.py:45`) |
| Customer master ingest allow-list | `{active, inactive, onboarding, blocked}` only (`pipeline.py:35`) |
| Distributor API | **No** status allow-list; create/patch do not expose `distributor_status` |

**`verified` gates nothing at runtime.** It is not in the API allow-list; no production `customer_status == "verified"` check. Duplicate-group “verified for survivor hint” means “not in `{unverified, needs_review}`” — literal `verified` is never required.

### 2.2 Provisional mint / reuse

| Entity | Mint status | Reuse gate |
|--------|-------------|------------|
| Customer (DSI/shipment steward, bulk provisional) | `unverified` + `TMP-CUST-%` | `TMP-CUST-%` **and** `customer_status == "unverified"` (`provisional_entity_identity.py:196-199`) |
| Customer (admin POST blank code) | Request status (schema default **`active`**) | Same reuse rule — **admin-minted TMP+active is not reusable** |
| Distributor (DSI/shipment steward) | Model default **`active`** + `TMP-DIST-%` | `TMP-DIST-%` only — **no status gate** |

PATCH provisional-reuse warning (retain): leaving `unverified` on `TMP-CUST-%` returns warning string (`customers.py:47-50`, `134-146`).

### 2.3 SELECT-only cip (2026-07-09)

```
current_database= cip
alembic= 20260709_0068
unverified_TMP_CUST= 4887
TMP_CUST_any= 4961   (unverified 4887 / merged 69 / active 5)
TMP_DIST_any= 23     (all distributor_status=active)
unverified_TMP_DIST= 0
customer_status_verified= 7
distributor_status_verified= 0
customer_merged_into_set= 75
distributor_merged_into_set= 0
```

**Backlog vs cip contradiction (report, do not improvise):** BACKLOG-061 cites “~23 TMP-DIST unverified”. On cip, all 23 `TMP-DIST-%` are **`active`**. Promote design must treat distributor provisional as **code-prefix based**, not `unverified`-based, unless Phase B deliberately aligns mint status (separate decision).

### 2.4 Merge — must not break

- Soft redirect: `merged_into_customer_id` / `merged_into_distributor_id` + loser status `merged`
- FK repoint engines before redirect (`customer_full_repoint` / `distributor_full_repoint`)
- Import resolution does **not** walk `merged_into_*` (aliases + dim ids); integrity audit does
- Promote keeps **same id** → no FK repoint, no alias repoint required

---

## 3. Design decisions

### 3.1 What should `verified` mean?

| Gate | Recommendation | Phase B default if deferred |
|------|----------------|----------------------------|
| **A. Stop provisional reuse** | **YES — primary gate.** Promote sets status that fails the reuse predicate. For customers today that means leaving `unverified` (already true for any non-`unverified`). Formalize target status as **`active`** (canonical master), not orphaned `verified`. | Keep reuse = `unverified` + `TMP-CUST-%` only |
| **B. Merge-survivor preference** | Prefer non-TMP + non-`unverified`/`needs_review` (already approximated). Do **not** require literal `verified`. | No change |
| **C. Reporting eligibility** | **Defer.** Tagged-customer sell-through reporting is the TRIGGER for 061; define reporting filter in that project, not here. | Gates nothing |
| **D. Import filters** | **Defer.** Do not filter DSI/shipment resolution by status until gates are product-defined. | Resolution ignores status (current) |

**Orphaned `verified` (7 rows):** **Retire as a write target.** Phase B options (Warren picks one):

1. **Preferred:** One-time SELECT→PATCH/script (Warren-approved write) remap `verified` → `active`; keep `verified` out of allow-list forever.  
2. Add `verified` to allow-list and treat as synonym of `active` for all gates — more confusion, not recommended.  
3. Leave orphan rows read-only until remap — allow-list still excludes `verified`.

**Recommendation:** Option 1 after Phase B promote ships (or as a tiny Warren-approved data fix). Design does **not** revive `verified` as the promote target.

### 3.2 Promote-in-place contract

**Definition:** Steward-confirmed mutation of **one** existing `dim_customer` or `dim_distributor` row:

1. **Same primary key** (no merge, no new dim row).
2. **Code reassignment:** `TMP-*` (or steward-supplied old code) → unique real business `code`.
3. **Status:** customer `unverified` (or TMP+active edge cases) → **`active`**; distributor TMP+`active` stays **`active`** (or set explicitly `active`).
4. **Uniqueness:** reject if target `code` already owned by **any** other row (case-insensitive).  
   **Amendment (B1 evidence):** `dim_customer.code` is UNIQUE and merge losers **retain** their codes (`customer_full_merge` does not rename). Therefore “collision with merged-away row allowed” from an earlier draft is **not implementable** without a separate loser-code-retire step. B1 blocks all collisions; document loser-code retire as a future ops/merge enhancement if needed.
5. **Confirm required:** `confirm=true`; preview returns collisions + reuse impact.
6. **Audit:** `ImportRowResult`-style or dedicated audit note on row / activity — at minimum structured API response + optional `merge_note`-like field only if Warren approves column (distributor already has `merge_note`; customer does not).
7. **Aliases:** **no auto-repoint** — same id; existing `CustomerSourceTokenAlias` / distributor aliases remain valid.
8. **Facts / evidence:** untouched (same `customer_id` / `distributor_id`).
9. **Distinct from merge:** never sets `merged_into_*`; never repoints FKs.

**Eligibility (v1 recommendation):**

| | Customer | Distributor |
|--|----------|--------------|
| Code | `TMP-CUST-%` | `TMP-DIST-%` |
| Status | Prefer `unverified`; allow `active` TMP with explicit confirm (admin-mint edge) | `active` TMP (all 23 today) |
| Exclude | `merged_into_customer_id IS NOT NULL` | `merged_into_distributor_id IS NOT NULL` |

**Bulk upsert interaction:** After promote, old TMP code is gone from the row. A later bulk upsert that still sends the TMP code would create a **new** row — same as today when status leaves `unverified`. Preview must warn: “future imports using old TMP code may mint a duplicate; prefer alias or update source files.”

### 3.3 Distributor parity

- Add promote API + admin action symmetric to customer.
- **Do not** invent `unverified` mint for distributors in Phase B unless Warren wants mint-path alignment as a separate sub-task.
- Optionally add `ALLOWED_DISTRIBUTOR_STATUS` + PATCH status later — **out of promote MVP** if promote only needs code reassignment on TMP+active.

### 3.4 API allow-list alignment

| Change | Phase |
|--------|-------|
| Promote endpoint sets `customer_status='active'` (already allowed) | B |
| Do **not** add `verified` to allow-list | — |
| Do **not** add `merged` to allow-list (merge engine only) | — |
| Remap 7 `verified` → `active` | Warren-approved data fix (not Phase A) |
| Distributor status API | Defer unless needed for eligibility UI |

### 3.5 Schema delta assessment

| Need | Verdict |
|------|---------|
| New status enum / check constraint | **Not required** for MVP if target is `active` |
| New columns | **Not required** for MVP; audit via API response + existing timestamps. Optional later: `promoted_at`, `promoted_from_code` — **flag for Warren**, no migration in Phase A |
| New tables | **Not required** |
| Migration 0069 | Unrelated; still unapplied |

**Phase A authors no migration.**

---

## 4. Phase B regression traps (carry verbatim + discovery)

From BACKLOG-061:

- Do not break `merged_into_*` soft redirect  
- Do not auto-create on promote  
- Code uniqueness  
- Bulk upsert-by-code must not silently duplicate when steward intended promote  
- Lineup/shipment resolution keeps using aliases + dim codes regardless of status until gates are defined  

From discovery:

- Customer reuse is status-sensitive; distributor reuse is not — do not “fix” distributor by requiring `unverified` without changing mint paths  
- Admin-created TMP customers default `active` — eligibility must include or explicitly exclude them  
- No code reassignment exists today — promote is the first writer of `code` on an existing row; test uniqueness + concurrent promote  
- Retain PATCH provisional-reuse warning; promote should surface the same warning text (or stronger) in preview  

---

## 5. Explicit non-goals (Phase A/B)

- Auto-promote without steward confirm  
- Fuzzy name matching to choose target code  
- Changing DSI resolution tier order  
- Walking `merged_into_*` in import resolution  
- Building promote inside IC/lineup alias pass  
- Applying alembic / depending on 0069  

---

## 6. Decisions for Warren (before or during Phase B)

1. Confirm promote target status = **`active`** (not revive `verified`).  
2. Approve remapping 7 orphan `verified` → `active` (timing).  
3. Distributor: promote TMP+`active` as-is vs also align mint to `unverified` (separate unit?).  
4. Optional audit columns vs API-only audit for v1.  
5. Whether admin TMP+`active` customers are eligible for promote in v1.

---

## 7. Suggested Phase B split (not started)

1. **B1** — Customer promote preview/confirm API + tests (no UI).  
2. **B2** — Admin UI action on customers.  
3. **B3** — Distributor parity.  
4. **B4** — Orphan `verified` remap (Warren write approval).
