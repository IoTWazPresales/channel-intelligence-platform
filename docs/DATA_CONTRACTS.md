# Data contracts (MVP)

## Recommendation patternDerived recommendation-style entities SHOULD include:

| Field | Type | Notes |
|-------|------|--------|
| `recommendation_type` | string | Domain-specific code |
| `status` | string | e.g. `active`, `superseded` |
| `confidence` | string? | Human-readable band |
| `explanation_summary` | string? | Short “why” |
| `explanation_factors` | JSON | Structured breakdown |
| `impact_estimate` | string? | Business framing |
| `action_owner` | string? | Queue or role |
| `reviewed_by` / `reviewed_at` | string / timestamptz? | HITL |

## Import job lifecycle

| Stage | Meaning |
|-------|---------|
| `uploaded` | Metadata created |
| `raw_stored` | Bytes persisted |
| `schema_inferred` | Columns + dtypes sampled |
| `fields_mapped` | Canonical mapping applied |
| `validated` | Row-level checks run |
| `loaded` | (Future) facts materialized |
| `failed` | Terminal error |

## API headers (stub auth)

- `X-User-Id`: opaque user id
- `X-User-Role`: one of `admin`, `data_steward`, `commercial_manager`, `planner`, `product_manager`, `finance_reviewer`, `executive_viewer`
