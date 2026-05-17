# Channel Intelligence Platform — Context

The Channel Intelligence Platform tracks the full stock journey from OEM through distributors and retailers to consumers. It ingests messy commercial files (CSV/XLSX), standardizes entities via steward workflows, and surfaces explainable recommendations for inventory, pricing, promotions, and commercial planning. The core loop is: upload → parse → map → validate → apply → derive.

## Current State

**Branch:** `cursor/customer-sales-pipeline-2787`
**Alembic head:** `20260517_0038` (customer_sales_retail_promotion_tables)

### Working Modules

- **Dashboard / Control Tower** — KPI cards, stock health snapshot, recommended actions
- **Data Imports (Admin)** — CSV/XLSX upload, field mapping, validation, apply pipeline
- **Field Mappings (Admin)** — Steward-driven entity resolution queue
- **Product Master** — Full CRUD, specs_json, lifecycle management, PM import/commit
- **Customer Master** — Import, search, steward approval
- **Distributor Master** — Import, search, token alias management
- **Commercial Planner** — Plan CRUD, line economics calculator, trust tiers, provenance, readiness, suggestions, SKU economics bulk import, defaults maintenance
- **Current Lineup (Workbench)** — CSV upload, entity resolution, sync-to-plan, workbench columns
- **Historical Lineup Import** — Bulk past-period lineup ingestion
- **Exceptions Inbox** — Actionable exception rows with explainable context
- **Inventory** — Basic SOH display (partial)
- **Shipping / Inbound** — Shipment evidence tracking (partial)
- **Sell-out** — Fact ingestion (partial)
- **Pricing** — Price facts (partial)
- **Settings** — App configuration

### In Progress

- **Customer Sales Pipeline** — Migration `0038` creates `customer_sales` and `retail_promotion` tables. Models exist in `app/models/customer_sales.py`. API endpoints and frontend are being built.
- **SOH Calculation** — Stock-on-hand derivation from inventory + inbound shipments (planned).

### Planned Next

1. Complete customer sales import pipeline (template → mapping → validate → apply)
2. SOH calculation engine (derive from inventory facts + inbound shipments)
3. Commercial planner line override UI completion (all override fields)
4. Plan export (CSV/XLSX download)
5. Dashboard stock health visualization (replace JSON dump with charts)
6. Plan status workflow with audit trail
7. Budget integration with commercial planner GP outputs

## How to Run Locally

### Prerequisites
- Node 20+, pnpm 9 (`corepack enable`)
- Python 3.12.x (3.13+ may break `asyncpg`)
- PostgreSQL (local or Docker), database `cip`

### Option A: Native (recommended for day-to-day)

```bash
# 1. Install JS dependencies
pnpm install

# 2. Set up Python venv
cd apps/api
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Run migrations
alembic upgrade head

# 4. Start API + Web (from repo root)
pnpm dev:api-web
```

### Option B: Full Docker

```bash
docker compose -f infra/docker/docker-compose.yml up --build
```

Web: http://localhost:3000 | API: http://localhost:8010/docs

### Option C: Hybrid (Postgres+Redis in Docker, app on host)

```bash
pnpm docker:deps          # Start Postgres + Redis
pnpm dev:api-web           # Start API + Web on host
```

### Key Commands

| Command | What it does |
|---------|-------------|
| `pnpm dev:api-web` | API on :8001 + Web on :3000 (no Redis needed) |
| `pnpm dev:all` | API + Web + Celery worker (needs Redis) |
| `pnpm test:web` | Vitest frontend tests |
| `pnpm test:api` | Pytest backend tests |
| `pnpm lint` | ESLint + type checks across all packages |
| `pnpm local:db:migrate` | `alembic upgrade head` via venv |
| `pnpm local:db:seed` | Run seed script (destructive demo seed) |

## Key Files to Read First

| File | Why |
|------|-----|
| `README.md` | Setup instructions, scripts table, product principles |
| `.cursor/rules/Supply-Chain-Intelligence-Project-Rules.mdc` | Complete project rules, architecture, patterns, gotchas |
| `docs/COMMERCIAL_PLANNER_AUDIT.md` | Audit of the commercial planner module |
| `apps/api/app/api/v1/endpoints/commercial_planner.py` | Core commercial planner API (3,200+ lines) |
| `apps/web/src/app/(app)/commercial-planner/page.tsx` | Commercial planner frontend (3,600+ lines) |
| `apps/api/app/models/` | All SQLAlchemy models |
| `apps/api/app/services/commercial_planner/` | Calculator, trust, suggestions, lineup sync |
| `apps/web/src/features/commercial-planner/` | Extracted planner sub-components (12 files) |
| `apps/api/alembic/versions/` | Migration history (38 migrations) |
| `docs/ARCHITECTURE.md` | System architecture overview |
| `docs/DATA_CONTRACTS.md` | API data contracts |
