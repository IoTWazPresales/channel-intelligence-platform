# Backfill source_key collision count

READ-ONLY measurement. `current_database()` = **cip**. No writes.

Measured: 2026-09-17T09:41:58 (local). Script: `apps/api/scripts/_backfill_collision_count_readonly.py`.

## Entities

| Entity | Table | Id | Code | Name |
|--------|--------|----|------|------|
| Pinnacle | `dim_distributor` | 29 | DIST-000012 | Pinnacle |
| Takealot | `dim_customer` | 20 | CUST-000012 | Takealot |

`source_key` includes resolved `product_id` (and DSI also `customer_id`). Unique constraint on both fact tables. Reimport **upserts** when the rebuilt key matches; if steward aliases now point at a different dim id, apply **inserts beside** the old fact.

## Pinnacle sell-out (`fact_sales_sellout`)

| Metric | Count |
|--------|------:|
| Fact rows | 5704 |
| Distinct `source_key` | 5704 |
| Duplicate `source_key` groups | **0** |
| **Would collide (upsert) on `source_key`** | **5589** |
| **Of those, resolution changed (would insert beside)** | **115** |
| Staging `resolved_*` differs from fact | 0 |
| Product alias hit (exact `alias_value` = staging token) | 1125 |
| Product alias points at a different product | 0 |
| Customer alias hit | 3965 |
| Customer alias points at a different customer | 115 |
| Transaction dates in DB | 2025-01-06 → 2026-06-12 |

115 is customer-token remaps only (`customer_source_token_alias` approved, latest id, same or null distributor). Product aliases that hit still match the fact’s `product_id`.

Invoice groups with more than one fact (337 groups / 5697 rows) are almost all multi-SKU or multi-customer invoices, not duplicate keys.

**Coverage gap:** four years of Pinnacle sell-out are not in `cip` yet. Existing Pinnacle facts span ~17 months in 2025–2026.

## Takealot sell-through (`fact_customer_sellthrough`)

| Metric | Count |
|--------|------:|
| Fact rows | 96 |
| Distinct `source_key` | 96 |
| Duplicate `source_key` groups | **0** |
| **Would collide (upsert) on `source_key`** | **96** |
| **Resolution changed (would insert beside)** | **0** |
| Staging product id differs from fact | 0 |
| Product alias hit on staging `raw_product_token` | **0** |
| Period starts in DB | 2025-09-22 → 2026-07-27 |

**Coverage gap:** three years of Takealot sell-through are not in `cip` yet (96 weekly-ish rows over ~10 months). Exact `product_alias.alias_value` = staging `raw_product_token` hit nothing, so remap risk for the incoming files is **unmeasured** until those tokens exist as aliases.

## How to read this

- Collide / upsert = existing row whose current aliases (or missing alias) would rebuild the **same** `source_key`.
- Insert beside = existing row whose current approved alias for the staged token points at a **different** dim id than the fact. Unique `source_key` still holds; a new key is inserted next to the old one.
- This is not a repair. Incoming four-year / three-year files were not present to match against.
