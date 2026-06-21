---
name: cip-fix-protocol-audit
description: >-
  Produce an interconnection path map before any Channel Intelligence Platform
  importer bug fix, perf fix, or steward/validate/apply repair. Use when the user
  reports hangs, timeouts, slow apply, duplicate writes, wrong code path, or asks
  for fix protocol, path map, or canonical writer before implementing.
---

# CIP Fix-Protocol Audit

**Required before writing code** on any importer bug, perf fix, or "make X work" task.
Report the audit in chat first. **Do not implement** until the user approves the
single fix direction (unless they said "audit then implement").

## When to run

- Steward / validate / apply bug or slowness
- User says fix protocol, path map, find canonical path, no patches
- Symptom looks like poll timeout, retry loop, or UI stuck — still run this first

**Skip** for: docs-only, pure UI copy, unrelated modules, or user explicitly
scoped a one-line change with no import pipeline involvement.

## Stop conditions (do not implement if hit)

- Two paths exist for the same steward action with different commit models →
  **bulk/set-based is canonical** until proven otherwise
- Fix would change DSI resolution tier order or eligibility without explicit approval
- Fix would weaken steward governance (auto-create masters from evidence)
- Migration needed but not approved
- Audit cannot be completed → stop and report gaps

## Audit steps

### 1. Identify importer

Read the row in `docs/IMPORT_FLOW_CAPABILITY_CONTRACT.md` for the affected
`template_slug` (e.g. `distributor_inventory`, `inbound_shipments`).

### 2. Build path map

Grep and read until every write path is accounted for:

| UI / trigger | API route | Celery task | Sync writer | Commit model |
|--------------|-----------|-------------|-------------|--------------|

Search terms (parallel grep):

- `bulk_*`, `*_apply_sync`, `*_enqueue`, `execute_*`, `dispatch_*`
- Page components under `apps/web/src/features/import-steward/`
- Endpoints under `apps/api/app/api/v1/endpoints/imports.py` and domain routes

### 3. List UI write surfaces

Every button / action on the affected screen that mutates the same entities
(map, provisional, bulk map, apply, ignore, compute plan, validate, re-validate).

### 4. Commit granularity

Per-row loop vs per-batch vs set-based `INSERT … ON CONFLICT` chunked SQL.
Note transaction boundaries (open txn across cache load, per-chunk commit, etc.).

### 5. Canonical target

Answer:

- Does canonical bulk/sync writer already exist? (file paths)
- Why does the failing path diverge?
- Does shipment or DSI already solve this pattern? (reference file)

### 6. Fix direction (exactly one)

Choose **one**: wire → extend → replace. Not a P0/P1 patch stack.

**Forbidden as first fix** (wrong path symptoms):

- Poll budget / queue grace / client timeout only
- Retry on a per-row loop that should be batch
- UI dedupe hiding duplicate enqueue

Allowed only **after** canonical path is correct and a measured gap remains.

## First response template

```markdown
## Fix-protocol audit — [importer / symptom]

### Path map
| UI / trigger | API route | Celery task | Sync writer | Commit model |
|--------------|-----------|-------------|-------------|--------------|
| … | … | … | … | … |

### Parallel paths found
- …

### Canonical target
- **Files:** …
- **Why current path diverges:** …

### Fix direction (one)
**[wire | extend | replace]:** …

### Out of scope / stop
- …

### Awaiting approval to implement
```

Then **stop** unless user said implement in the same message.

## Parity bar

When adding or extending a writer, follow `.cursor/rules/import-parity.mdc`:

- Async dispatch + progress + task slot registry
- Set-based chunked upsert where applicable
- Shared steward workspace / AI resolver / column mapping patterns

## Related skills

| Invoke | When |
|--------|------|
| `Run cip-read-only-audit` | Need code-path forensics before fixing |
| `Run cip-session-handover` | Missing branch/incident context |
| `Run cip-context-update` | After approved fix ships |
| `Run cip-skills-index` | List all CIP skills |

See [reference.md](reference.md) for DSI/shipment canonical file anchors.
