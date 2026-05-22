# DSI region evidence & steward fallback — implementation plan (draft)

**Status:** Awaiting product approval — **do not implement** until signed off.  
**Branch context:** `main`, no migrations in this doc unless explicitly approved later.

---

## 1. Problem statement (your situation)

- Field mapping uses **`region_or_province_token` → province column**, but **province is empty** on this job (and often across historical data).
- **Channel / route-to-market column** has values; some are true RTM, some look like **country/region labels** mis-placed in the channel column.
- The platform today resolves region **only from province evidence** on each customer candidate. Empty province ⇒ `missing_source_evidence` for region, regardless of other signals.
- **Bulk region fallback** today sets a **job-level plan default** from the full `dim_region` catalog (including demo rows like NA-W, ECOM-era seeds) — not operating countries, not per-customer, and **not** evidence-based.
- Geo stewardship asks stewards to **type channel code + name** per token — poor fit when the business truth is already in the file.

**Goal:** Region for a **customer** should be suggested from **corroborated evidence** (including hints from channel text). Channel stays its own dimension. Optional **bulk region fallback** = steward picks **one country/region** from a **countries list**, **default off**.

---

## 2. Design principles (approved direction)

| Principle | Meaning |
|-----------|---------|
| **No channel → region mapping** | Do not auto-assign `dim_channel` rows to `dim_region` or treat channel_id as region_id. Channel column may **inform** region suggestions only. |
| **Evidence ≠ dimension write** | Hints appear in plan/drawer with `explanation_factors`; catalog/aliases/customer `region_id` change only on **steward apply**. |
| **Region is one domain (v1)** | Scope is `dim_region` / province token / customer `region_id` only. Channel stewardship remains separate on Region & channel tab. |
| **Province column is one source** | `region_or_province_token` evidence still used when populated; empty province triggers multi-source suggestions, not failure. |
| **Fallback default off** | Job-level region fallback is opt-in, explicit, and uses a **countries** picker — not silent demo catalog. |
| **No patch in React only** | Shared service used by DSI plan, drawer, bulk apply; other import modules unchanged unless they opt in later. |
| **Governance preserved** | No auto-create `dim_customer` / `dim_region` from import without steward action (existing project rules). |

---

## 3. Conceptual model

```
┌─────────────────────────────────────────────────────────────────┐
│  Per customer_dealer_token candidate (DSI)                        │
├─────────────────────────────────────────────────────────────────┤
│  Region evidence sources (ranked, explainable)                    │
│    1. Province column token(s) on staging lines (if any)        │
│    2. Channel column token(s) — HINT only (country/RTM parse)   │
│    3. Resolved distributor geography (HQ / location if present) │
│    4. Peer customers (same dealer_group / job) already region_id  │
│    5. dim_customer.region_id (strategic / master, same source)  │
│    6. Prior source_region_token_alias on this source_definition   │
│    7. (Later) shipment / other modules — read-only hints          │
├─────────────────────────────────────────────────────────────────┤
│  Output: suggested_region_id | null, confidence, factors[]      │
│          (+ optional “channel token looks geographic” flag)      │
├─────────────────────────────────────────────────────────────────┤
│  Job-level fallback (opt-in): single region_id for plan only    │
│    when src_r is null — same as today’s default_region_id       │
│    but UI = ISO countries list, default OFF                       │
└─────────────────────────────────────────────────────────────────┘
```

**Channel hint logic (v1, deterministic):**

- Parse channel raw tokens against a **reference country/region lexicon** (ISO 3166-1 alpha-2/alpha-3, common names, optional internal aliases).
- Match ⇒ evidence factor: `channel_token_geographic_hint` with proposed `dim_region` **if** a catalog row exists or steward creates it via “register from hint.”
- No match ⇒ token stays in **channel** unresolved list (RTM stewardship).
- **Do not** write `region_id` from channel without steward confirm.

---

## 4. What stays the same (non-regression)

- DSI validate / revalidate / apply pipelines, `source_key` facts, resolution tier order for product/distributor/customer entities.
- Shipment evidence steward, product master, historical lineup imports.
- Existing `region_source_token_alias` / `channel_source_token_alias` tables and geo steward create/alias endpoints.
- Plan apply, bulk provisional customer/distributor (except enriched explanations and optional region on apply).
- Celery revalidate dispatch (already async).

---

## 5. Phased delivery

### Phase A — Region evidence engine (backend, DSI-only consumers)

**New module (illustrative):** `apps/api/app/services/imports/dsi_customer_region_evidence.py`

**API:**

- `build_customer_region_evidence(session, import_job_id, candidate_id) -> RegionEvidenceResult`
- `build_job_region_evidence_batch(session, import_job_id, candidate_ids[]) -> dict[candidate_id, RegionEvidenceResult]`

**`RegionEvidenceResult` fields:**

- `suggested_region_id: int | null`
- `confidence: float` (0–1)
- `explanation_summary: str`
- `explanation_factors: list[{ source, detail, region_id?, region_code?, token? }]`
- `channel_geographic_hints: list[{ raw_token, guessed_region_code, matched_catalog: bool }]`
- `province_evidence: { raw_token?, resolved_id?, detail? }` (unchanged semantics)

**Integration points:**

- Call from `dsi_resolution_plan` row build (customer candidates) — attach to plan row JSON.
- Call from steward candidate read-model / drawer payload (optional GET or embedded in existing candidate list enrichment later).

**Tests:** Unit tests per evidence source; fixture job with empty province + channel `AU` + distributor in AU.

---

### Phase B — UX: evidence on Customers tab (no new tab)

- Plan row / drawer show **“Suggested region: Australia (AU)”** with expandable factors.
- Badge when province empty but hints exist: `Region: suggested` / `Region: unresolved`.
- Actions: **Accept suggestion** (sets row override `region_id` or maps via alias), **Pick region** (catalog/country picker), unchanged **Map customer** flows.

**No** automatic apply on revalidate.

---

### Phase C — Region & channel tab improvements (file token bootstrap)

- **Register region from file token** — prefill `region_code` / `name` from normalized token (steward confirm). Same for channel when token is RTM.
- **Register region from channel hint** — one click when hint confidence high: creates/links alias for **region** domain only (not channel→region FK).
- Remove duplicate manual empty code/name as default path.

---

### Phase D — Bulk region fallback (your spec)

**Behaviour:**

- **Default: off** (`default_region_id: null` in plan requests).
- When enabled: single **“Operating region (fallback)”** dropdown on Customers tab toolbar or bulk panel.
- Options: **ISO 3166 country list** (label = country name, value = resolve to `dim_region.id`).
  - If country not in `dim_region`: steward option **“Create region from country”** on select (one governed row, code = ISO2, name = official name) then apply fallback.
- Scope: affects **plan effective region** and provisional customer preview when `src_r` is null — same as current `default_region_id` semantics in `effective_customer_geo_for_plan`.
- **Remove** use of unscoped demo catalog for this picker (filter: countries reference ∪ existing `dim_region` matched by ISO code).

**Explicitly not in v1:**

- Auto-detect steward user locale as fallback.
- Auto-pick region from strategic customers without steward opt-in.

**Optional Phase D+ (later):** “Suggest fallback” chip — pre-select dropdown from plurality of distributor/customer evidence on job; steward still confirms.

---

### Phase E — Bulk actions

- **Apply suggested region to selected customers** (plan override or provisional patch) with preview counts.
- **Bulk register unresolved region tokens** from Region & channel tab (job-scoped).

---

## 6. UI sketch (after approval)

```
[ Plan toolbar: Refresh | chips | ⋮ plan options ]

Tabs: Distributors | Customers | Products | Region & channel

--- Customers tab ---
[ Bulk map ] [ Bulk provisional ] [ Region fallback ▼ OFF ]  ← countries dropdown, disabled until toggled ON
[ Apply suggested region (12) ]  … existing plan apply …

Filters …
Grid row: ACME | suggested region: AU (0.85) — channel hint "AU", distributor ANZ …

--- Region & channel tab ---
Unresolved channels (RTM) …
Unresolved regions (province tokens if any) …
Channel token "AU" — geographic hint → [ Register as region AU ] [ Ignore for region ]
```

---

## 7. Data / reference assets

| Asset | Purpose |
|-------|---------|
| **ISO 3166 country list** | Fallback dropdown + channel hint lexicon (static JSON in `packages/types` or `apps/api` reference data). |
| **`dim_region`** | Continues as SoT; create-on-select if country chosen but row missing. |
| **No new fact tables** | v1 uses existing context + dimensions. |

**Migration:** Only if we add `dim_region.iso_alpha2` or `region_country_reference` table — **stop and get explicit approval**. v1 can match by `dim_region.code` = ISO2 without schema change if codes are stored that way on create.

---

## 8. API contract changes (DSI)

| Endpoint | Change |
|----------|--------|
| `POST …/dsi-resolution-plan` | Response rows include `region_evidence` block; `defaults_used.region_id` only when client sends opt-in fallback. |
| `POST …/dsi-resolution-plan/effective` | Same enrichment. |
| `GET …/dsi-unresolved-geo-tokens` | Optional `geographic_channel_hints[]` per token (read-only). |
| **New** `GET …/reference/countries` or static web bundle | Countries for fallback dropdown (not full demo catalog). |
| Geo steward create | Accept optional `suggested_from_hint: true` audit in notes (no schema required). |

**Breaking:** None intended — new JSON fields additive.

---

## 9. Channel vs region — decision record

**Rejected:** `dim_channel.region_id` FK, auto map channel→region on validate.

**Accepted:** `channel_geographic_hint` evidence object; steward may **register a region alias** from that token, which then resolves province/region evidence on revalidate like any other alias.

---

## 10. Open questions for you

1. **Countries list:** ISO 3166 only, or ISO + your commercial regions (e.g. ANZ, DACH) as first-class options?
2. **Fallback scope:** Plan + provisional preview only (current `default_region_id`), or also write `region_id` on apply for all selected open customers?
3. **Hint aggressiveness:** Treat `AU Retail` as hint `AU`, or require exact country token match only in v1?
4. **Empty `dim_region`:** On first production use, bulk-import countries once, or create-on-select from dropdown only?
5. **Phase order:** OK to ship **D (fallback off + countries dropdown)** before **A (full evidence engine)**, or insist evidence first?

---

## 11. Success criteria

- Job with empty province but channel `AU` shows **explainable region suggestion** on customer rows without mapping channel to region.
- Bulk region fallback **off by default**; when on, picker shows **countries**, not NA-W demo rows.
- Revalidate + apply behaviour unchanged for modules outside DSI steward.
- Vitest + targeted pytest for evidence ranking and fallback opt-in.

---

## 12. Effort rough order (engineering)

| Phase | Relative size |
|-------|----------------|
| A Evidence engine | L |
| B Customers UX | M |
| C Region & channel tab bootstrap | M |
| D Countries fallback | S–M |
| E Bulk apply suggested | M |

**Recommended sequence if you want quick wins:** **D → A → B → C → E**  
(fixes misleading fallback UX fast; then substance on evidence)

---

*Document version: 2026-05-19 — draft for steward review.*
