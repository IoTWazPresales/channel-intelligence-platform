# BACKLOG-061-U2a — Customer code mint: ERP research + candidates

**Status:** research note (docs-only) · **Branch:** `feat/backlog-061-entity-promote-in-place` @ `66c657b`  
**Date:** 2026-07-10  
**DB sample:** `cip` SELECT-only · `tmp_pending=4892` (`unverified` 4887 / `active` 5) · existing non-TMP includes `CUST-1001`

---

## Locked (do not reopen)

- Codes come from **import OR system mint**; CIP is multi-tenant product vision
- BP1 CSV path retained; no mint in BP1 (already shipped)
- Partial success + per-row report; never auto-create `dim_customer`
- Theme B grid shell OUT; distributor batch OUT
- **Regression traps (verbatim):** Never invent a global hard-coded format; never auto-create dim_customer; FLAG≠BLOCK on collisions; partial success semantics from BP1
- **Behavior to retain (verbatim):** CSV/paste mapping path from BP1; single-row promote
- **Out of scope (verbatim):** Grid-shell extraction (Theme B); distributor batch (optional follow-on)

This unit is **docs only** — no migration, no settings seed, no app/UI code.

---

## 1. ERP survey

### (a) NetSuite — auto-generated numbering

Per entity type (Customer, etc.) at Setup → Company → Auto-Generated Numbers: enable, optional **prefix** / **suffix**, **minimum digits** (zero-pad), **initial / current number**, optional **Allow Override**. Example: prefix `CUST` + min digits 6 → `CUST000001`. Docs advise a separator at the end of prefixes (e.g. `CUST-`) so numeric-looking prefixes do not collide with pure numbers. Changing the initial number advances the *next* assignment; existing records are not renumbered unless an explicit Update path is used for previously unnumbered rows. **Gap policy:** sequential allocation under normal create; override and parallel create paths can produce operational gaps. **What breaks on convention change:** already-issued entity IDs stay; new prefix/padding only affects future creates — historical codes become a mixed namespace forever.

### (b) Dynamics 365 Finance — number sequences

Formats are **segment lists** (constant + alphanumeric + optional scope segments). **Scope** (Shared / Company / Legal entity / Operating unit, optionally + fiscal period) decides which org unit owns the sequence and whether the scope token appears in the number. **Continuous vs non-continuous:** continuous aims for no permanent gaps (status-list recycle / cleanup after cancel); non-continuous allows gaps and is preferred for performance via preallocation unless regulation requires continuity. Microsoft guidance: use non-continuous unless compliance forces continuous. **What breaks on convention change:** scope/segment edits do not rewrite history; a new sequence or format leaves old numbers valid but non-homogeneous — reporting filters that assume one pattern must be updated.

### (c) SAP — number ranges (NRIV / SNRO)

Objects (e.g. customer `DEBITOR`) own **intervals** with **internal** (system-assigned) vs **external** (user-supplied) assignment. **Buffering** (main-memory packages per app server) is the default performance path and **intentionally allows gaps** on rollback, server restart, or multi-instance buffers; “no buffering” is gap-averse but serializes on the range table. Account groups can map to different intervals (segmented ranges by customer group). **What breaks on convention change:** interval bounds and buffering are operational config; changing intervals mid-life risks overlap with already-assigned numbers — SAP practice is new intervals / groups, not rewrite.

**CIP takeaway:** mature ERPs treat permanent codes as **append-only identities** with configurable prefix/pad/scope, accept **gaps under concurrency** unless audit law forbids them, and never silently renumber history. CIP mint should mirror that: configurable pattern + collision-safe sequence + no rewrite of promoted rows.

---

## 2. Candidate conventions (exactly 3)

Sampled TMP rows used for examples (SELECT-only on `cip`, 2026-07-10):

| id | tmp_code | name |
|----|----------|------|
| 7 | `TMP-CUST-20260601115009-F196` | Apex High School |
| 8 | `TMP-CUST-20260601115122-0D89` | City Of Johannesburg |
| 10 | `TMP-CUST-20260601115541-500A` | Google South Africa |

Existing non-TMP collision context: `CUST-1001` already present → any `CUST-######` mint must bump past occupied values (silent bump per locked D4).

### Candidate A — Plain prefix + zero-padded sequence (NetSuite-like)

| Field | Value |
|-------|--------|
| **Pattern grammar** | `{PREFIX}{SEP}{SEQ:pad}` → literals `CUST` + `-` + zero-padded decimal sequence |
| **Default params (illustrative)** | `prefix=CUST`, `sep=-`, `pad_width=6`, `next_seq=1` (allocator bumps past occupied) |
| **Examples (mint order)** | Apex → `CUST-000001`; City Of Johannesburg → `CUST-000002`; Google SA → `CUST-000003` *(if `CUST-1001` exists, seq continues and skips 1001 when reached)* |
| **Collision story** | `SELECT … FOR UPDATE` on tenant settings row; render code; if `dim_customer.code` taken, `next_seq++` and retry (silent; not a FLAG event) |
| **Sort / read** | Lexicographic sort ≈ numeric if pad fixed; human-readable; matches steward mental model of ERP customer IDs |
| **ERP precedent** | NetSuite auto-numbers; Dynamics constant+alphanumeric shared sequence |
| **Rework cost if changed later** | Low for *future* mints (settings row update). Already-promoted rows keep old codes — mixed namespace. No mass rename. |

### Candidate B — Region-segmented (Dynamics scope-like)

| Field | Value |
|-------|--------|
| **Pattern grammar** | `{PREFIX}{SEP}{REGION}{SEP}{SEQ:pad}` → e.g. `C-ZA-00001` |
| **Default params (illustrative)** | `prefix=C`, `sep=-`, `segment_source=region_code` (fallback `XX` when `region_id` null), `pad_width=5`, per-segment or global `next_seq` |
| **Examples** | Sampled rows have **`region_id=NULL`** → Apex → `C-XX-00001`; City → `C-XX-00002`; Google → `C-XX-00003` until geo is enriched |
| **Collision story** | Same FOR UPDATE + bump; segment token is part of uniqueness key with seq |
| **Sort / read** | Sortable within region; readable if region codes are stable; noisy if most rows are `XX` |
| **ERP precedent** | Dynamics legal-entity / company segments; SAP account-group → interval mapping |
| **Rework cost** | Higher: changing segment source or region codes does not rewrite history; backlog mint before geo fill produces a large `XX` cohort that looks like Candidate A with extra noise |

### Candidate C — Year-segmented (period scope-like)

| Field | Value |
|-------|--------|
| **Pattern grammar** | `{PREFIX}{SEP}{YYYY}{SEP}{SEQ:pad}` → e.g. `CUS-2026-00001` |
| **Default params (illustrative)** | `prefix=CUS`, `sep=-`, `segment_source=mint_year_utc`, `pad_width=5`, `next_seq` reset or continued per year (settings must store year→seq map or composite next key) |
| **Examples** | Apex → `CUS-2026-00001`; City → `CUS-2026-00002`; Google → `CUS-2026-00003` |
| **Collision story** | FOR UPDATE; bump within year bucket; year rollover needs explicit next_seq policy |
| **Sort / read** | Chronological cohorts visible; longer codes; year boundary is a second sequence to operate |
| **ERP precedent** | Dynamics fiscal-period scope combinations; less common for *customer master* than for documents |
| **Rework cost** | Medium: year in the code is permanent; wrong timezone/policy at mint time is frozen; settings schema needs year-aware seq (more columns or JSON map) |

### Candidate summary

| ID | Pattern | Axis | Fit for ~4.9k TMP backlog | Notes |
|----|---------|------|---------------------------|-------|
| **A** | `CUST-000001` | Simple | Strong | Collides with existing `CUST-1001` via silent bump — fine |
| **B** | `C-ZA-00001` | Segmented (region) | Weak today | Sampled TMP rows lack `region_id` → mostly `XX` |
| **C** | `CUS-2026-00001` | Segmented (year) | OK | Extra seq bookkeeping; unusual for customer master |

---

## 3. RECOMMENDATION — Warren picks (not a decision)

**Recommendation: Candidate A (`CUST-{SEQ:06d}`).**

Rationale: matches NetSuite-style steward expectations; settings columns stay minimal (template + pad + next_seq); works with null geo on the current backlog; collision-safe bump already required by existing `CUST-1001`; lowest rework if a later tenant wants a different prefix via settings rather than code forks. Candidate B is the right *second* convention for a future multi-region tenant once `region_id` is reliably populated — not the first mint for this backlog. Candidate C adds year ceremony without ERP-customer precedent strong enough to justify it for master codes.

**This is a recommendation only.** U2b must not hardcode or seed a candidate until Warren picks.

---

## 4. Format-agnostic settings schema (paper only — no migration)

**Table (proposed name):** `customer_code_mint_setting`

| Column | Type | Notes |
|--------|------|--------|
| `tenant_id` | `text` PK / UNIQUE | Single seeded row e.g. `default` for this install; forward-compatible |
| `pattern_template` | `text` NOT NULL | Token string, e.g. `{PREFIX}{SEP}{SEQ}` or `{PREFIX}{SEP}{SEGMENT}{SEP}{SEQ}` |
| `prefix` | `text` NOT NULL | Literal prefix |
| `separator` | `text` NOT NULL DEFAULT `'-'` | |
| `pad_width` | `int` NOT NULL | Zero-pad width for SEQ |
| `segment_mode` | `text` NOT NULL | `none` \| `region` \| `mint_year` (expresses A/B/C without new tables) |
| `next_seq` | `bigint` NOT NULL | Next sequence to try (monotonic; bumps on collision) |
| `created_at` / `updated_at` | timestamptz | |

**Allocation strategy (locked D4):**

1. `SELECT … FROM customer_code_mint_setting WHERE tenant_id=:t FOR UPDATE`
2. Render candidate code from template + `next_seq`
3. If `dim_customer.code` exists (case-insensitive per BP1), `next_seq += 1` and retry
4. On success, persist `next_seq = used + 1` and return code
5. Mint bumps are **not** FLAG events; FLAG≠BLOCK remains for **imported/CSV** collisions only

One row expresses all three candidates via `segment_mode` + template — no per-candidate schema fork.

---

## 5. Mint-mode API sketch

**Recommend: extend `POST /api/v1/customers/promote/batch`** with `mode: "map" | "mint"` (default `"map"` = BP1 CSV behavior).

| | Extend batch | New endpoint |
|--|--------------|--------------|
| Pros | Reuses dry_run, partial success, per-row report, cap 500, dialog polling patterns | Cleaner OpenAPI separation |
| Cons | Body union / validation branches | Duplicates commit/report semantics; second UI path |

**Contract sketch (mint mode):** rows carry `tmp_code` only (`new_code` omitted/blank); service mints `new_code` via settings allocator, then calls existing single-row promote. `dry_run=true` → preview minted codes without write; `dry_run=false` → partial success per row. Cap **500** retained; ~4,892 backlog → client chunks (~10 batches).

**UX:** Select-N → dry-run preview of minted codes → confirm → chunked apply.

Tradeoff in one line: one endpoint keeps BP1 as the single bulk promote surface; mode flag is cheaper than a parallel writer.

---

## 6. No-code disposition — DEFERRED

**Definition:** an explicit park/exclude status for TMP rows that should **never** receive a permanent code (test junk, one-off noise), so they leave the mint queue without promote.

**Why defer is safe:** unminted rows remain `TMP-*` / typically `unverified` — already a harmless parked state. Add a disposition status later only if the mint queue proves noisy after real runs.

---

## Gate

1. Fable VERIFY of this note  
2. **Warren picks Candidate A / B / C** (or a variant) before U2b starts
