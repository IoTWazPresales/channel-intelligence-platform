# Cursor Prompt Templates

Reusable prompt patterns for working with the Channel Intelligence Platform codebase. Copy, fill in the bracketed sections, and paste into Cursor.

---

## 1. Discovery Prompt

Use when exploring a new area of the codebase before making changes.

```
## Hard Constraints
- Do NOT modify any code
- Do NOT run migrations or seed scripts
- Do NOT commit anything
- Read only — report findings

## Task
Read and understand [MODULE NAME] before any implementation work.

### Steps
1. Read all files in:
   - [list relevant paths, e.g., apps/api/app/api/v1/endpoints/MODULE.py]
   - [list relevant paths, e.g., apps/web/src/app/(app)/MODULE/]
   - [list relevant paths, e.g., apps/web/src/features/MODULE/]
   - [list relevant model files]
   - [list relevant service files]

2. Document:
   - What the module does (2-3 sentences)
   - Which API endpoints exist and what they accept/return
   - Which DB tables/models are involved
   - What the frontend renders and which API calls it makes
   - What is working, what is partial, what is missing
   - Any inconsistencies or potential issues

3. Write findings to [output path, e.g., docs/MODULE_DISCOVERY.md]

### Context
- Read CONTEXT.md for platform overview
- Read .cursor/rules/Supply-Chain-Intelligence-Project-Rules.mdc for patterns
- Current Alembic head: check with `alembic current`
```

---

## 2. Implementation Prompt

Use for phased feature development with checkpoints.

```
## Hard Constraints
- Never run `git add -A` or `git add .`
- Never run `alembic upgrade head` without confirmation
- Never modify working features without explicit instruction
- Always verify `current_database() = cip` before DB operations
- Report your plan BEFORE implementing

## Task
Implement [FEATURE DESCRIPTION].

### Phase 1: Analysis (report before proceeding)
- Read all relevant files listed below
- Identify which files need to change
- List new files that need to be created
- Identify any migration requirements
- Report: "Here is my implementation plan: [plan]. Shall I proceed?"

### Phase 2: Backend ([if applicable])
- Models: [describe model changes]
- Migration: Generate but do NOT run (`alembic revision --autogenerate -m "description"`)
- Service layer: [describe service changes]
- API endpoints: [describe endpoint changes]
- Report: "Backend changes complete. Ready for frontend."

### Phase 3: Frontend ([if applicable])
- Page/route: [describe page changes]
- Components: [describe component changes]
- API integration: [describe query/mutation hooks]
- Report: "Frontend changes complete. Ready for testing."

### Phase 4: Verification
- Run `pnpm lint`
- Run `pnpm test:web`
- Run API tests if backend changed
- Stage files with explicit paths: `git add [path1] [path2]`
- Commit with descriptive message

### Files to read first
- CONTEXT.md
- .cursor/rules/Supply-Chain-Intelligence-Project-Rules.mdc
- [list specific files relevant to this feature]

### Existing patterns to follow
- [reference a similar existing module, e.g., "Follow the pattern in commercial_planner.py for endpoint structure"]
- [reference UI pattern, e.g., "Use ModuleDataSection + EnterpriseDataGrid like exceptions/page.tsx"]
```

---

## 3. Migration Prompt

Use when database schema changes are needed.

```
## Hard Constraints
- Do NOT run `alembic upgrade head` — only generate
- Verify `alembic current` output before proceeding
- Never drop columns or tables without explicit approval
- Stage only the migration file with `git add apps/api/alembic/versions/NEW_FILE.py`

## Task
Create an Alembic migration for [DESCRIPTION].

### Steps

1. Check current state:
   ```bash
   cd apps/api
   source .venv/bin/activate
   alembic current
   ```
   Expected head: [EXPECTED_HEAD, e.g., 20260517_0038]

2. If head does not match, STOP and report the discrepancy.

3. Describe the schema changes needed:
   - [Table: column_name type constraints]
   - [Table: column_name type constraints]
   - [Index: index_name on table(columns)]

4. Create or update SQLAlchemy models in `apps/api/app/models/[module].py`:
   - [describe model changes]

5. Generate migration:
   ```bash
   alembic revision --autogenerate -m "[description]"
   ```

6. Review the generated migration file:
   - Verify upgrade() creates/alters the correct tables and columns
   - Verify downgrade() reverses all changes
   - Check for unintended operations (autogenerate can detect spurious diffs)

7. Report: "Migration generated at [path]. Here is what it does: [summary]. Shall I proceed with `alembic upgrade head`?"

### DO NOT
- Run the migration without reporting first
- Include seed data in migration files (use seed.py instead)
- Generate migrations against a database that is not at the expected head
```

---

## 4. Debug Prompt

Use when investigating issues or unexpected behavior.

```
## Hard Constraints
- Do NOT modify code to "fix" the issue until root cause is confirmed
- Gather evidence first, then propose a fix
- Check database state before assuming code bugs
- Check git state before assuming missing changes

## Task
Investigate [ISSUE DESCRIPTION].

### Step 1: Gather context
- Read the relevant code:
  - [list files]
- Check git status: `git status`, `git log --oneline -10`
- Check database state (if DB-related):
  ```sql
  SELECT current_database();
  -- [relevant queries]
  ```
- Check alembic state: `alembic current`

### Step 2: Reproduce
- [Describe how to trigger the issue]
- Capture: error messages, stack traces, network responses, console output

### Step 3: Analyze
- What is the expected behavior?
- What is the actual behavior?
- What changed recently? (`git log --oneline --since="2 days ago"`)
- Is this a data issue, code issue, or environment issue?

### Step 4: Report
Before making any fix, report:
1. Root cause: [explanation]
2. Affected files: [list]
3. Proposed fix: [description]
4. Risk assessment: [what else could break]
5. Test plan: [how to verify the fix]

### Step 5: Fix (only after approval or if fix is trivially safe)
- Implement the minimal fix
- Run tests: `pnpm test:web` and/or `pnpm test:api`
- Stage with explicit paths
- Commit with descriptive message referencing the issue
```

---

## 5. Anti-Patterns That Cause Regressions

### DO NOT do these — they have caused issues before:

| Anti-Pattern | Why It Breaks Things | What to Do Instead |
|-------------|---------------------|-------------------|
| `git add -A` or `git add .` | Stages `.env`, dumps, logs, unrelated changes | Use `git add path/to/specific/file` |
| Modifying validation rules to make imports pass | Silently corrupts data; downstream modules depend on validation | Fix the data or add a new valid code path |
| Using `numpy.bool_` in SQLAlchemy persistence | DB driver rejects non-native Python types | Cast with `bool(value)` before saving |
| Lazy-loading relationships in async endpoints | `MissingGreenlet` error crashes the request | Use `joinedload()` or `selectinload()` in the query |
| Auto-creating dimension records from import tokens | Breaks entity resolution governance | Flag for steward review instead |
| Running `seed.py` without `--commercial-system-reference-only` | Wipes all application data | Use the flag, or `alembic upgrade head` for reference dims |
| Mapping DAP/sell-in evidence to controlled cost fields | Confuses commercial sell-in pricing with internal cost basis | Keep DAP as evidence only; controlled cost comes from SKU assumptions |
| Weakening `source_key` uniqueness on fact tables | Allows duplicate fact rows on re-import | Preserve upsert-on-source_key semantics |
| Running `alembic upgrade head` without checking `alembic current` | Can apply migrations out of order or to wrong database | Always check current state first |
| Substring matching for entity resolution | Creates false-positive mappings that corrupt downstream analytics | Use exact token matching with steward confirmation |
| Silently swallowing import validation errors | Data appears clean but has hidden quality issues | Surface all validation errors to the user with actionable messages |
| Editing `.cursor/rules/` without approval | Changes project-wide agent behavior | Always ask before modifying rules files |
