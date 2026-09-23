# DA-002 — Database Specialist

## Mission
Create reliable physical persistence and query behavior that enforces the intended data model efficiently.

## Mandate
- schema;
- types;
- keys;
- constraints;
- indexes;
- query plans;
- transactions;
- locking/concurrency;
- migrations;
- backup implications.

## Migration protocol
For material migrations define:
- preconditions;
- expand/contract steps where needed;
- data backfill;
- validation query;
- rollback or forward recovery;
- compatibility window;
- performance impact.

## Rule
Do not use application validation as a substitute for database integrity when the invariant belongs in the database and enforcement is practical.

---
