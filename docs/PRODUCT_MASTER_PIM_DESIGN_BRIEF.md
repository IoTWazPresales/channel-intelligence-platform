# Product Master / PIM Architecture — Design Brief & Catch-Up

> **Purpose of this document:** A self-contained brief you can paste into a fresh
> Claude (or any LLM) that has **no access to the codebase**, so it can reason
> about the product-master / attribute architecture with full context. Design
> discussion only — nothing here has been built. No code or schema has been
> changed as a result of this brief.

---

## 0. What the platform is (30-second version)

**Channel Intelligence Platform** — a supply-chain intelligence monorepo that tracks
stock flow **OEM → Distributor → Retailer → Consumer**. It ingests messy commercial
files (CSV/XLSX), standardises entities via steward (human-in-the-loop) workflows,
and surfaces explainable recommendations (inventory, buy plans, pricing, promo,
competition, roadmap, budgets).

- **API:** FastAPI, SQLAlchemy 2 (async), Alembic migrations, Celery/Redis.
- **Web:** Next.js 15 (App Router), React 19, MUI 6, AG Grid, TanStack Query.
- **DB:** PostgreSQL on **Supabase** (the dev DB is the Supabase `postgres`/`cip` DB).
- **Local dev:** Windows, **no Docker**; services run via Python venv + Node.
- **Governance rule that matters here:** *import evidence is evidence, not master
  data.* The system never auto-creates or auto-deletes master records
  (`dim_product`, `dim_customer`, `dim_distributor`) from import evidence without
  steward approval.

The relevant module is **Product Master import**: a wizard
(`upload → map → validate → review → commit`) that writes products into the catalog.

---

## 1. Catch-up: what happened in this session since the last code change

The last two code commits were:

- `c22210d` — fixed a PM commit crash (`Wrong number of elements for 36-tuple`:
  a tuple of `(bool, value)` pairs wasn't being flattened before going into a SQL
  `VALUES` clause) and hardened the dev process-kill scripts.
- `da96232` — fixed a second PM commit crash (`DatatypeMismatch: CASE types integer
  and text cannot be matched`: a `CASE` expression mixed a typeless-NULL `VALUES`
  column with a typed ORM column for `channel_id`/`launch_date`/`retired_date`; fixed
  by `cast(...)`). Also added a project rule: *custom SQL constructs must be validated
  with a real end-to-end DB run, not just mock tests.*

**Since then, no code has changed.** The session has been diagnosis + design talk:

1. **The PM commit finally succeeded** but took a very long time, and the user
   noticed alarming table sizes in Supabase:
   - `product_attribute_value` ≈ **2,019,207 rows (~286 MB)**
   - `import_job` ≈ **365 MB** (with only a handful of job rows)
   - source file was only **~20 MB**

2. **Audit findings (read-only, nothing changed):**

   - **The 500 errors in the logs were transient DNS failures**
     (`socket.gaierror: [Errno 11002] getaddrinfo failed`) resolving the Supabase
     host — *not* a code bug. They surface easily because the async DB engine uses
     **`NullPool`**, so **every API request opens a brand-new connection**
     (DNS + TLS + pooler auth). Any DNS blip lands on a request → 500.

   - **Every request takes ~5000 ms** for the same reason: ~5s is **connection
     setup overhead per request** (NullPool, no connection reuse), not query time.
     The frontend polls job state every 1–2s, so the UI constantly pays the ~5s tax.
     - *Why NullPool exists:* Supabase's **transaction pooler (`:6543`)** can't
       reuse asyncpg named prepared statements (`DuplicatePreparedStatementError`),
       so the original author disabled statement caches **and** used `NullPool` to
       make it *correct*. The performance cost was accepted and never revisited.
       The cleaner fix is to use the Supabase **session pooler (`:5432`)** which
       supports real pooling.

   - **The 2 million `product_attribute_value` rows are arithmetic, not a leak.**
     The file had **~17,136 products** and **~118 columns** dispositioned as
     `stage_raw`/`attribute_candidate`. The EAV model writes **one row per
     (product × attribute)** → 17K × 118 ≈ 2M. Each value is wrapped in a JSONB
     envelope `{"value": ...}`, which is where the 286 MB comes from.

   - **The commit was slow because the EAV write path uses the ORM unit-of-work**
     (`db.add()` per object; a `db.flush()` **inside the per-row loop** for each new
     catalog product → ~17K round trips; then one giant flush of ~2M ORM objects).
     The *read* side is already optimised (chunked `IN` batch loads) and `dim_product`
     already uses bulk `INSERT … ON CONFLICT` — but the EAV *writes* were never
     converted to bulk. Classic "tested on small data, never load-tested."

   - **`import_job` at 365 MB** = large JSONB columns (`inferred_schema` stores
     per-column samples, plus `mapping_decisions`, `field_mapping`, `file_headers`)
     **× Postgres MVCC bloat** from frequent `UPDATE`s during validate/commit/poll.
     Likely needs a one-time `VACUUM FULL` + trimming stored samples. (Confirm with
     `pg_stat_user_tables` before acting.)

   - **"Deleted jobs didn't delete customers" is correct behavior.** Deleting
     `import_job` rows does **not** cascade to `dim_customer` by design (governance
     rule). The "3 customers in Table Editor vs 0 in the Database→Tables view" is a
     **Supabase UI artifact**: Table Editor shows live rows; the Tables list shows a
     stale planner estimate (`pg_class.reltuples`). Data is intact.

3. **Then we discussed the bigger picture** (pricing, safety, and the product vision)
   — captured below in sections 4–6.

---

## 2. The relevant code as it stands today

**Async DB engine** (`apps/api/app/db/session.py`) — the pooling problem:

```python
engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
    poolclass=NullPool,                       # <-- new connection every request
    connect_args=_asyncpg_connect_args(...),  # statement caches disabled for :6543 pooler
)
```

**EAV commit path** (`apps/api/app/services/imports/pm_commit_catalog.py`) — the
volume + write-speed problem. Read-side is batched; write-side is ORM:

```python
# one ProductAttributeValue ORM object added per (product × attribute) value:
pav = ProductAttributeValue(
    catalog_product_id=catalog_product_id,
    attribute_definition_id=attribute_definition_id,
    value_json={"value": raw},   # JSONB envelope, untyped
)
db.add(pav)

# and, worse, a flush per NEW catalog product, inside the row loop:
db.add(cp)
db.flush()        # ~17K network round trips
```

**Key tables involved:**
- `dim_product` — canonical product master (the "truth").
- `catalog_product` — per-catalog source/evidence row; references
  `canonical_product_id → dim_product.id` and carries `source_sku`.
- `attribute_definition` — defines an attribute (namespace, display_name, data_type).
  **Attributes are data rows here, not SQL columns.** (This is the important part.)
- `product_attribute_value` (PAV) — EAV value rows, keyed off **`catalog_product_id`**
  (the evidence layer), `attribute_definition_id`, and a JSONB `value_json`.

---

## 3. The problems to solve (engineering)

| # | Problem | Nature |
|---|---------|--------|
| 1 | ~5s per request + DNS-blip 500s | `NullPool` → no connection reuse. Config/infra fix. |
| 2 | Commit takes minutes at scale | ORM unit-of-work writes 2M rows + per-row flush. Needs bulk `INSERT … ON CONFLICT`. Touches a live path → higher risk, do in small validated slices. |
| 3 | 286 MB of untyped JSONB-wrapped EAV values | Storage *shape* problem, not volume. Can't range-filter ("RAM ≥ 16GB") on stringly-typed JSON. |
| 4 | `import_job` 365 MB bloat | MVCC bloat + large JSONB. One-time VACUUM + trim samples. DB-affecting → needs explicit approval. |
| 5 | Attributes anchored to evidence layer, not canonical product | User wants attributes that reference the **product ID** as the key. |

---

## 4. The product vision (user's words, distilled)

The user **wants the 118+ columns** — and is right to. For a hardware catalog
(laptops, desktops, motherboards, GPUs…), specs like CPU, GPU, RAM size/speed/
generation, storage type/capacity, chassis material, panel type, etc. are exactly
the **intelligence signals** needed for filtering, speccing, "what fits where,"
promo pricing, and recommendations. Throwing them away is the real mistake.

The user's articulated end-state:
- Attributes should live in a **proper table that references the product** (product ID
  as key), not a loose blob.
- Businesses have **many columns per category**, and they vary by category.
- Ideally an **AI agent decides the product-master type** (laptops vs desktops vs
  motherboards…) and can **create/map columns** as needed — *or* the user selects a
  product type on import. (User is unsure of feasibility/cost/downstream impact and
  wants a sober assessment.)

---

## 5. Proposed architecture (PIM pattern) — for debate

This is a standard **PIM (Product Information Management)** problem. Recommended shape:

1. **Category → attribute schema (templates).**
   A product *type* ("Laptop", "Motherboard", "GPU") defines which attributes apply.
   **Attributes remain data rows** in `attribute_definition` (extended with a
   `category`/type linkage), **never real SQL columns.** So "create a new column" is
   an `INSERT`, never an `ALTER TABLE` — no migrations, no table locks, no bloat, and
   unlimited per-category attributes. This is the safe way to honor "AI creates
   columns."

2. **Typed values, not stringly-typed JSON.** Two viable options (or a hybrid):
   - **(a) Typed EAV:** value table gets `value_text`, `value_numeric`, `value_bool`,
     `value_unit` columns + indexes → enables real range/filter queries.
   - **(b) JSONB spec column on `dim_product` + GIN index:** Postgres `jsonb` + GIN
     handles "ram_gb ≥ 16 AND gpu_vendor = 'NVIDIA'" well and is far simpler than 2M
     EAV rows.
   - **Recommended hybrid:** typed storage for the **canonical specs you filter on
     most**, plus a `jsonb` blob for the **long tail** of rarely-queried attributes.

3. **Two clean layers (keep them separate):**
   - **Evidence:** raw source columns per catalog → stays on `catalog_product`
     (roughly as today).
   - **Truth:** resolved/normalized canonical specs → anchored on **`dim_product.id`**
     (this is the "reference the product ID" the user wants).

4. **Anchor attributes to the canonical product** for the specs that are "truth",
   while keeping per-source evidence where it belongs.

---

## 6. AI-assist model + cost (for debate)

Put AI in the **proposer** seat, never the **executor** seat — this also keeps it
inside the governance rule (no auto-creating master/schema without steward approval).

**AI does (cheap, high-value):**
- **Classify product type** per file ("this is Laptops") — one call per file.
- **Map messy headers → canonical attributes** ("`Mem (GB)`" → `ram_capacity_gb`,
  unit=GB) — **per unique header, cached by header signature**, *not per row*.
- **Normalize values** ("16GB"/"16 GB"/"16384MB" → `16`, unit GB) — deterministic
  rules first, AI fallback only for the weird ones.
- **Propose new attribute definitions** for unmapped columns → steward approves →
  *then* the `attribute_definition` row is created.

**AI must NOT:** invent schema silently in production, run per-row, or be the source
of truth.

**Cost lever (the whole game):** keep AI **per-header / per-file**, never per-row.
118 headers classified once ≈ pennies; 17K rows × 118 = millions of calls = never.
At per-header pricing, AI is a rounding cost.

**Pricing recommendation:** **decouple architecture from pricing.** Build it
- **flagged** (an `ai_assist_enabled` setting already exists),
- **metered** (log every AI call: job_id, tokens, purpose),
- **bounded** (per-header caching).
At single-digit-cents-per-import, the clean story is to **bake it into the platform
fee** and not nickel-and-dime. Metering lets you change your mind later without
re-architecting. Reserve any "premium AI tier" framing for genuinely expensive
*future* features (per-row enrichment, image analysis), not this.

**Pragmatic v1 (recommended):** user **selects the product category on import** →
loads a curated attribute template → AI **assists** mapping the file's headers onto
that template and **flags unknowns** for steward review. ~90% of the value,
deterministic, cheap, with a clean upgrade path to "AI auto-suggests the category."

---

## 7. Safety strategy (the user is — rightly — nervous about breakage)

The bugs that broke things (`36-tuple`, `DatatypeMismatch`) were **edits to a hot,
live code path validated only on small data.** The PIM work has a **different,
lower risk profile** because it can be almost entirely **additive**:

- **New tables / new nullable columns** — existing import/commit flow untouched.
- **Behind a feature flag** — new typed-attribute path runs in parallel with the
  current EAV path; flip on when proven, flip off instantly if not.
- **Feature branch, never `main`.**
- **Real-DB + realistic-volume validation before "done"** (extend the existing SQL
  Validation Rule with a scale check — don't ship things that pass at 10 rows and
  die at 2M).
- **DB snapshot / Supabase point-in-time restore point before any migration.**

Higher-risk items (touch live paths, do in tiny validated slices, not big-bang):
- **#1 connection pooling** and **#2 bulk-EAV rewrite.**

Lower-risk: the additive PIM model + category templates + AI-assist.

---

## 8. Open questions to chew on (good prompts for online Claude)

1. **Storage shape:** typed-EAV vs `jsonb`-on-`dim_product`+GIN vs hybrid — which
   best serves filtering/intelligence at, say, 100K products × 150 attributes, on
   Supabase Postgres? What are the query-pattern and index trade-offs?
2. **Category model:** how rigid should category→attribute templates be? Fully
   curated, fully AI-driven, or curated-with-AI-extension? How are cross-category
   attributes (e.g., "weight") handled without duplication?
3. **Canonical vs evidence:** which attributes are "truth" on `dim_product` vs
   "evidence" on `catalog_product`? What's the promotion/resolution rule from
   evidence → truth, and does it need steward sign-off?
4. **AI boundaries & cost:** confirm the per-header caching keeps cost negligible;
   design the steward-approval loop for AI-proposed attribute definitions; decide
   metering schema.
5. **Migration/rollout:** what's the smallest safe first slice that delivers value
   (probably: connection pooling fix + bulk-EAV write rewrite, *before* any model
   change) and what's the phase order after that?
6. **Backfill:** how to migrate the existing 2M JSONB-wrapped PAV rows into the new
   typed shape (or deprecate them) without downtime or data loss?

---

## 9. Hard constraints (must respect)

- **No migrations / model changes without explicit user approval** (stop condition).
- **No `alembic upgrade` against the real DB without instruction.**
- **Never auto-create/delete master records from import evidence.**
- **Custom SQL must be validated with a real DB run, not mock-only tests.**
- **Explicit-path git staging only; never push to `main` without instruction.**
- **Additive + feature-flagged + branch-first** for anything touching live paths.

---

*End of brief. Decisions made with online Claude should come back here for
implementation, where the agent can read the real files, run real DB validation, and
stay inside the guardrails above.*
