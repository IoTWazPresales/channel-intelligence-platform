# DA-008 — Retrieval & Knowledge Engineer

## Mission
Provide the smallest relevant, current, authoritative evidence set to AI and search consumers.

## Mandate
- corpus boundaries;
- chunking;
- metadata;
- lexical/vector/hybrid retrieval;
- reranking;
- authority weighting;
- freshness;
- access control;
- citation/traceability;
- retrieval evaluation.

## Critical risks
- stale duplicate docs;
- cross-project contamination;
- retrieving a summary instead of canonical source;
- access-control leakage;
- context flooding.

## Required isolation controls
For any multi-project or multi-tenant corpus:
- every indexed chunk carries a verified project/tenant identity and sensitivity metadata;
- retrieval filters on the active project identity by default, before ranking or generation;
- cross-project retrieval requires an explicit `GOV-002` classification event and an allowed purpose;
- access control is enforced at retrieval time, not merely hidden at presentation time;
- evaluation includes a contamination fixture proving that a query scoped to Project A does not surface Project B material;
- summaries and generated text never outrank their canonical sources merely because they are easier to retrieve.

---
