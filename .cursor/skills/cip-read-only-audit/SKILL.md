---
name: cip-read-only-audit
description: >-
  Read-only code archaeology for Channel Intelligence Platform. Use when the user
  asks report only, no fixes, verify hypothesis, find what emits this query,
  read-only audit, file:line for every claim, or trace ORM per-row lookups.
  Hard constraints: no edits, no migrations, no DB writes, no service restarts.
disable-model-invocation: true
---

# CIP Read-Only Audit

Forensic code investigation. **Report only — propose no fix** unless the user
explicitly asks for recommendations in a separate message.

## Hard constraints (non-negotiable)

- **No** file edits, migrations, commits, or staging
- **No** `alembic upgrade` or seed scripts
- **No** import validate/apply against `cip` or remote Supabase (unless user
  explicitly approved read-only SQL via MCP — prefer code-only)
- **No** service restarts, worker kills, or backend termination
- **No** browser automation unless user explicitly requested
- If ambiguous → report ambiguity; do not assume

## When to run

- "Find what emits this SQL"
- "Verify or refute hypothesis: …"
- "Read-only audit" / "report only" / "no changes yet"
- Per-row PK lookup hunts, N+1 relationship traversal
- Pre-fix forensics (pair with `Run cip-fix-protocol-audit` before implementing)

## Inputs to collect from user

| Input | Required? |
|-------|-----------|
| Hypothesis to verify/refute | Yes (or infer from error message / SQL in prompt) |
| Scope (importer, phase, job ID) | If provided |
| Exact SQL or stack trace | If provided |

## Investigation procedure

1. **Restate hypothesis** in one sentence (verify / refute / inconclusive).
2. **Find code paths yourself** — grep, semantic search, read call chains.
3. **For every claim**, cite `path:line` (real files only).
4. **Classify each DB access:**
   - Single bulk SELECT (materialised once)
   - Batched / chunked query
   - Per-row or lazy iteration (`session.get`, relationship access)
   - Unknown → say unknown
5. **Trace ORM paths:** relationships reachable from the named phase/function;
   note `joinedload` / `selectinload` vs implicit lazy load.
6. **Engine config** (if relevant): which session factory, sync vs async, connect_args —
   cite config resolution code, not `.env` secrets.
7. **Verdict:** CONFIRMED / REFUTED / INCONCLUSIVE with evidence summary.

## Output template

```markdown
## Read-only audit — [short title]

**Hypothesis:** …
**Verdict:** [CONFIRMED | REFUTED | INCONCLUSIVE]

### Findings

#### 1. [Finding title]
- **Location:** `path:line`
- **Behaviour:** …
- **Fetch style:** bulk | batched | per-row | lazy relationship

#### 2. …

### Code paths examined
| Function / route | Role | DB access pattern |
|------------------|------|-------------------|
| … | … | … |

### What this does NOT explain
- …

### Not proposed (read-only scope)
No fixes in this report.
```

Optional **"If asked for fix direction later"** section only when user said
"no changes yet" but may want hints — keep separate and label clearly.

## Evidence quality bar

- No file:line → do not state as fact
- Do not infer query shape from model name alone — read the query/fetch code
- Distinguish validate upfront vs row loop vs apply vs steward endpoints
- Quote SQLAlchemy pattern (`scalars().all()` vs `yield_per` vs `session.get`)

## After audit

- Bug fix needed → `Run cip-fix-protocol-audit` then wait for approval
- Live DB evidence needed → ask user; default remain code-only
- Update memory → `Run cip-context-update` only after separate implementation work

## Related skills

| Invoke | When |
|--------|------|
| `Run cip-fix-protocol-audit` | Ready to plan a fix |
| `Run cip-skills-index` | List all CIP skills |
