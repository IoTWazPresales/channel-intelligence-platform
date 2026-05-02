# Post–model-fix validation (schema + safe test audit)

**Date:** 2026-05-03  
**Branch:** `main`  
**Commit:** `5cbf9e1028f84533485b533701073289682df034` (`fix(api): restore clean model imports`)

This note records read-only inspection and non-destructive checks after the API model import fix. No database reset, reload, or Docker was used.

---

## 1. Baseline (recorded at validation time)

```text
git branch --show-current   → main
git rev-parse HEAD          → 5cbf9e1028f84533485b533701073289682df034
```

Recent history (abbreviated):

- `5cbf9e1` — fix(api): restore clean model imports  
- `1d68531` — chore(repo): remove tracked local artifacts  
- `6b272da` — chore(test): prevent import tests polluting dev database  

Working tree had unrelated local changes; **only this file** was committed from this validation pass.

---

## 2. Model / migration consistency

### 2.1 ORM ↔ intended schema (authoritative migration sources on disk)

The following **untracked** revision files in the workspace (not yet on `origin/main` at validation time) define the tables/columns that match the restored ORM:

| Model / field | Primary migration(s) (workspace copy) |
|---------------|----------------------------------------|
| `DimCustomer.customer_status`, `partner_tier`, `account_owner_internal`, `notes_summary`, `preferred_distributor_id` | `20260426_0012_customer_phase1_control_table.py` |
| `CustomerLocation`, `CustomerContact` | `20260426_0014_customer_stage_completion_scaffold.py`; timestamp defaults in `20260426_0015_customer_child_timestamp_defaults.py` |
| `DistributorLocation`, `DistributorContact` | `20260426_0017_distributor_child_scaffold.py` |
| `HistoricalLineupImportHeader`, `HistoricalLineupImportLine` | `20260427_0019_historical_lineup_import_foundation.py` |

Cross-check (read-only): column names, types, FK targets, and unique constraints in those migrations align with:

- `apps/api/app/models/dimensions.py` — `CustomerContact`, `CustomerLocation`, `DistributorContact`, `DistributorLocation`, extended `DimCustomer`
- `apps/api/app/models/historical_lineup.py` — header/line tables and FKs

**Minor ORM vs DDL nuance:** `HistoricalLineupImportHeader` / `Line` use `TimestampMixin` (`updated_at` non-null in the ORM). Alembic for `20260427_0019` declares `updated_at` nullable on those tables. This is a typical strictness mismatch only if you rely on NULL `updated_at`; inserts still work with server defaults.

### 2.2 Committed Git history vs Alembic graph (**blocker**)

`git ls-tree -r HEAD apps/api/alembic/versions/` **does not** include any of:

- `20260426_0012` … `20260426_0017`
- `20260427_0018`, `20260427_0019`

Yet **tracked** `20260427_0020_commercial_lineup_case.py` sets `down_revision = "20260427_0019"`.

So on a **clean clone of `main` only**, Alembic’s revision graph references revisions whose **files are missing from the repository**. That is inconsistent with a reproducible migration history, even though a developer machine that still has those `.py` files untracked on disk can run `alembic heads` successfully.

**Verdict:**

- **ORM vs the migration scripts that exist locally:** consistent for the tables listed above.  
- **ORM vs committed migration tree on `main`:** **not** self-contained; missing revision files must be committed (or the chain repaired) before fresh environments can migrate to create those tables.

`app/models/__init__.py` on `5cbf9e1` imports the restored symbols; no change required there for this audit.

---

## 3. Commands run (import + API health)

Environment: Windows PowerShell; repo `C:\Users\warren_eliason\channel-intelligence-platform`.  
Python: `apps\api\.venv\Scripts\python.exe`.

> Bash heredocs (`python - <<'PY'`) are not used below; equivalent `-c` one-liners were used.

```powershell
cd apps\api

.\.venv\Scripts\python.exe -c "from app.models import *; print('app.models wildcard import ok')"

.\.venv\Scripts\python.exe -c "from app.models.dimensions import CustomerContact, CustomerLocation, DistributorContact, DistributorLocation, DimCustomer; from app.models.historical_lineup import HistoricalLineupImportHeader, HistoricalLineupImportLine; print('specific model imports ok'); print(CustomerContact.__tablename__); print(CustomerLocation.__tablename__); print(DistributorContact.__tablename__); print(DistributorLocation.__tablename__); print(HistoricalLineupImportHeader.__tablename__); print(HistoricalLineupImportLine.__tablename__)"

.\.venv\Scripts\python.exe -m pytest tests/test_health.py -q

cd ..\..
```

**Results:**

| Step | Result |
|------|--------|
| Wildcard `from app.models import *` | OK |
| Specific imports + `__tablename__` prints | OK (`customer_contact`, `customer_location`, `distributor_contact`, `distributor_location`, `historical_lineup_import_header`, `historical_lineup_import_line`) |
| `pytest tests/test_health.py -q` | **2 passed** |

---

## 4. Web build

```powershell
pnpm --filter web build
```

**Result:** Succeeded (existing ESLint hook warnings in several pages; no build failure).

---

## 5. Guarded import test (`cip` DB protection)

```powershell
cd apps\api
.\.venv\Scripts\python.exe -m pytest tests/test_distributor_sales_inventory_import.py -q
cd ..\..
```

**`ALLOW_TESTS_ON_DEV_DB` was not set.**

**Result:** Every test in that module **errored at setup** with `pytest.fail` from `tests/conftest.py`: database name parsed from settings is `cip` for async and/or sync URL. Message begins with: `Refusing import pipeline DB tests: database name is 'cip' (default shared dev DB).`

**Interpretation:** Guard behaves as designed; **no test body ran**, so **no import-pipeline writes** occurred from this run.

---

## 6. Database mutation

| Activity | DB mutated? |
|----------|-------------|
| Python import checks | No |
| `test_health` (HTTP `/health` via `TestClient`) | No schema/data change expected from health endpoint alone |
| Guarded DSI pytest | **No** (failed before any test logic) |

No `alembic upgrade`, truncate, or reload was executed.

---

## 7. Blockers

1. **Missing migration files on `main`:** `20260427_0020` depends on `20260427_0019`, but `20260426_0012`–`20260427_0019` are not in the tracked tree. Fresh clones cannot rely on Git alone to create schema for the restored models until those revisions are committed or the graph is fixed.

---

## 8. Next recommended step

1. **Commit the missing Alembic revisions** (`20260426_0012` through `20260427_0019`, and any ordering fixes) so `down_revision` links resolve on clean checkout, **or** surgically repair `down_revision` if some steps were merged elsewhere (document the chosen history).  
2. After migrations are on `main`, run `alembic upgrade head` against a **disposable** DB (e.g. `cip_test`) and optionally run DSI / historical lineup tests there with the guard satisfied via non-`cip` DB name.  
3. Keep using **`ALLOW_TESTS_ON_DEV_DB` unset** when pointing at shared `cip` dev data.

---

## 9. Files committed from this validation

- `docs/engineering/post-model-fix-validation-2026-05-03.md` (this document)

Commit message: `docs(api): record post model fix validation`
