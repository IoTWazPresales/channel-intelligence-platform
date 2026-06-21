# Resolution-improvement proposal (observe-and-propose only)

> **Status:** PROPOSAL. No matching-logic changes are implemented by this document. It records
> concrete opportunities to strengthen entity-resolution *suggestions* across importers, derived
> from the cross-importer alignment pass on `fix/shipment-steward-performance`. Each item lists a
> trigger; promote to `docs/BACKLOG.md` when picked up.

## Context (what exists today)

- Shared resolver: `ai_import_resolver.suggest_token_resolution` (Anthropic, `AI_AUTO_RESOLVE_THRESHOLD = 0.90`)
  behind `ai_resolver_wiring.try_ai_token_resolution` — deterministic-first, AI only on miss, auto
  only at ≥0.90, no-op when disabled. Now wired into DSI, shipment, product_master (workflow),
  customer_master (FK codes), and (this branch) customer_sell_through.
- Candidates are gathered per importer (`distributor_candidates`, `customer_candidates`,
  `product_candidates_from_{db,index}`) — currently simple substring filters over a capped scan.

## Opportunities

### 1. Cross-importer signal reuse (highest leverage)
The same raw token is resolved independently by each importer, discarding prior human decisions.
- **Approved alias tables are the cross-importer memory we already have.** `CustomerSourceTokenAlias`
  / `DistributorSourceTokenAlias` (written by steward map/provisional) should be consulted as a
  *first-class deterministic candidate source* for **every** importer's customer/distributor
  resolution, not just the one that created them. A token a steward mapped in DSI should
  deterministically resolve in shipment and sell-through.
- **Per-period stability:** DSI/shipment/sell-through repeatedly see the same distributor/customer
  tokens week over week. Cache `(normalized_token → entity_id)` resolutions (with the source job)
  so a confirmed resolution short-circuits both deterministic search and the AI call next period.
- *Trigger:* a "shared resolution memory" task; pairs with BACKLOG-024 (extend AI to the importers
  that lack it).

### 2. Confidence banding / thresholds
- Banding is now visual (shared `confidenceBand`: ≥0.90 high / ≥0.70 medium). The **auto-resolve
  threshold (0.90) is a single global constant**; consider making it *per token-type* — product SKU
  matches can safely auto-resolve higher/lower than free-text customer names, which carry more
  homonym risk. Surface the band in the steward queue filters (DSI already tabs; let "medium" be a
  one-click review bucket everywhere).
- *Trigger:* false-auto-resolve or excessive-manual-review feedback from Warren on a real file.

### 3. Divergent deterministic rules that could converge
- Each importer normalizes tokens slightly differently (`_norm_key`, product token keys, sell-through
  location codes). A **single canonical normalization** (case/space/punct/diacritics + known
  business-suffix stripping for partner names) used by all candidate gatherers would make the same
  token resolve identically everywhere and improve substring-match recall before AI is needed.
- Candidate gathering is substring-over-capped-scan; a **trigram / `pg_trgm` similarity** candidate
  query would feed the AI better candidates (and often resolve deterministically), especially for
  the 17k-row product catalog where the current cap can miss the true match.
- *Trigger:* a normalization-unification task; low risk, high recall payoff.

### 4. Where the wrapper could be smarter
- **Batch the AI calls.** Resolution is per-token in a loop; a validate run with many unresolved
  tokens makes many sequential Anthropic calls. Batch unique unresolved tokens per type into one
  request (with caching), cutting latency and cost on large files.
- **Feed richer context.** The wrapper passes `import_type` + minimal context; passing sibling
  evidence (e.g. co-occurring distributor for a customer token, period, channel) measurably
  disambiguates homonyms. Shipment already stashes `_ai_resolution`; make that context an input,
  not just an output.
- *Trigger:* AI latency/cost shows up on a large validate, or homonym mis-resolution is reported.

### 5. Where AI assist is absent but the failure mode exists
- `distributor_master` and `historical_lineup` hard-error on unknown tokens (BACKLOG-024).
- `current_lineup` (Commercial Planner parse) has no resolver wiring.
- These are the remaining "deterministic-or-bust" paths; wiring the shared wrapper closes the matrix.

## Non-goals
No change to the deterministic-first contract, the 0.90 auto bar as the *default*, the no-auto-create
governance, or the locked async DB config. All items above are suggestion-quality improvements that
keep humans in the loop for anything below the auto threshold.
