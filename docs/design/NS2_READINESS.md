# NS-2 readiness report — Nav collapse + Brief landing

**Date:** 2026-08-31  
**Branch reviewed:** `main` @ `12404bc`  
**Scope:** Discovery and readiness only — no implementation, no contract rows authored in this session.  
**Sources:** `docs/design/IMPLEMENTATION_PLAN.md` (BACKLOG-149), `docs/design/CIP_NAV_MAP.md`,
`docs/design/CIP_DESIGN_LANGUAGE.md` (FROZEN v1.1), `docs/design/EIF_UNIT_DECLARATION.md`,
`docs/design/NAV_COVERAGE.md`, `docs/design/PACKET_DATA.md`, `docs/design/brief.html`,
`docs/design/brief-empty.html`, `apps/web/src/features/shell/navConfig.ts`, live API grep.

---

## 1. NS-2 unit definition (as written in the plan)

From `docs/design/IMPLEMENTATION_PLAN.md` § Unit NS-2 — Nav collapse to six containers + Brief:

| Field | Definition |
|-------|------------|
| **Goal** | Spine matches `CIP_NAV_MAP.md` (Brief · Lineup · Stock · Settlement · Response · Steward · Reports · Admin); Brief (grammar 3) replaces Dashboard/Control tower as landing; retired routes redirect, not 404. |
| **Grammar / container** | Grammar 3 · **Brief** + shell spine (all grammars inherit spine). |
| **Migration** | **No** |
| **New API** | `GET /brief/signals` — federated signal rows: failed imports, stale DSI, cover breaches, FX-blocked cases (NS-1a), recon-not-run, missing assumptions. Reuse import-job freshness for provenance. |
| **Web** | `navConfig.ts` six primary containers + utilities; `features/shell/` spine 190px; `brief/page.tsx` grammar 3 (Read + ranked signal rows; **no filter bar**; no KPI cards); redirects for retired paths. |
| **Contract rows** | C-NS2-01 … C-NS2-05 (grammar 3 blotter; spine labels; federated Read; full shell on empty frame; manager reaches any container unaided). |
| **Done state** | `NAV_COVERAGE.md` UNMAPPED still 0; `/brief` mapped to §1; `UNIT8_DEMO_P2_GATE.md` landing → Brief; shared shell extracted for NS-3–NS-7. |
| **Gates** | Create-path-before-consolidation (`/brief` live before removing dashboard KPI cards); P2-4 charter; RBAC nav gates unchanged; FX-blocked signal needs NS-1a (others may ship `data_unavailable`). |
| **Sequencing** | NS-2 **after** NS-1a so Brief can cite real FX-blocked counts. |

BACKLOG-149 TRIGGER (unchanged in backlog): BACKLOG-148 VERIFY PASS or FX-blocked signal waived in
CURRENT.

---

## 2. Routes affected (per `NAV_COVERAGE.md` + plan)

### New / landing

| Route | NS-2 disposition |
|-------|------------------|
| `/brief` | **NEW** — §1 Landing / attention blotter (not yet in `NAV_COVERAGE.md`; must be added at implementation) |
| `/` | Redirect → `/brief` (today: `apps/web/src/app/page.tsx` → `/dashboard`) |

### Retired → redirect to Brief (§1 absorbs)

| Route | Current `NAV_COVERAGE.md` line |
|-------|-------------------------------|
| `/dashboard` | §1 landing — absorbs Dashboard/Control tower |
| `/exceptions` | §1 landing — absorbs Exceptions inbox |
| `/getting-started` | §1 landing — absorbs Getting-started coach |

### Spine collapse — all mapped routes keep URLs; **nav IA** changes

Every route in `NAV_COVERAGE.md` remains mapped to containers §1–§6 or utilities; NS-2 re-groups
**sidebar** entries under six job containers instead of today's seven groups (`overview`,
`channel-intelligence`, `commercial-planning`, `master-data`, `data-imports`, `admin`).

**High-touch route families:**

| Container (target spine) | Routes absorbed (from NAV_COVERAGE) |
|--------------------------|-------------------------------------|
| **Brief** §1 | `/`, `/dashboard`, `/exceptions`, `/getting-started`, `/brief` |
| **Lineup** §2 | `/lineup`, `/buy-plans`, commercial-planner Lineup slice |
| **Stock** §3 | `/sell-out`, `/plan-vs-executed`, `/shipping`, `/admin/po-management`, `/forecasts`, `/channel-intelligence`, `/inventory` (retired) |
| **Settlement** §4 | `/commercial-planner/cpor-cases`, case detail, historical/payment-evidence import, `/budgets`, `/budget-requests` |
| **Response** §5 | `/promotions`, `/pricing`, `/competition`, `/roadmap` |
| **Steward** §6 | `/admin/imports`, shipment evidence, listing capture, master-data admin routes, CST steward, mappings (retired on trigger) |
| **Utilities** | `/reports`, `/dashboards`, `/inbox`, `/admin/users`, `/settings`, `/admin/sql-viewer`, `/admin/ops`, `/admin/steward-audit` |

### Docs / gates to update at implementation

- `docs/design/NAV_COVERAGE.md` — add `/brief`; confirm UNMAPPED = 0
- `docs/UNIT8_DEMO_P2_GATE.md` — A5/A6 landing from Control tower → Brief (and Stock lens target for A6)
- `apps/web/e2e/*` — login landing paths

---

## 3. Current nav today (`navConfig.ts`)

Seven sidebar **groups** (not six containers). Quoted structure from
`apps/web/src/features/shell/navConfig.ts`:

| Group id | Label | Leaves (label → href) |
|----------|-------|------------------------|
| `overview` | Overview | Dashboard → `/dashboard`; Report builder → `/reports`; Dashboards → `/dashboards`; Report inbox → `/inbox` |
| `channel-intelligence` | Channel Intelligence | Channel Operations → `/sell-out`; Sell-Through → `/sell-out`; CST channel intelligence → `/channel-intelligence`; Listing Capture → `/listing-capture`; Inbound shipments → `/shipping`; Forecasting → `/forecasts` |
| `commercial-planning` | Commercial Planning | Commercial Planner → `/commercial-planner`; CPOR Cases → `/commercial-planner/cpor-cases`; Line-up Planning → `/lineup`; Plan vs Executed → `/plan-vs-executed` |
| `master-data` | Master Data | Products, catalogue gaps, Customers (+ duplicate tabs), Distributors (+ duplicates), Channels & Regions, CST steward |
| `data-imports` | Data Imports | Import Center → `/admin/imports`; Shipment Evidence; PO Management; Customer Reports |
| `admin` | Admin | Users, SQL viewer, Ops/monitoring, Steward audit, Settings |

**Landing:** `apps/web/src/app/page.tsx` redirects to `/dashboard`, not Brief.

**Role gating:** `roleMayAccess` / `filterNavGroupsForRole` — admin sees all; per-leaf `roles`
arrays (e.g. Commercial Planner `PLANNER_PLUS`, master data `STEWARD_PLUS`).

**Gap vs target spine (`NAMING.md` / nav map):** No Brief · Lineup · Stock · Settlement ·
Response · Steward top-level labels; duplicate `/sell-out` entries; Dashboard still primary landing.

---

## 4. Brief — eight signals: data needs and availability

Canonical signal definitions: `docs/design/PACKET_DATA.md` § Brief — eight signal rows.  
Exemplar UI: `docs/design/brief.html` (populated), `docs/design/brief-empty.html` (empty state).

Planned aggregator: `GET /brief/signals` (**does not exist** in tree at `12404bc`).

| # | Signal (packet) | Figures needed | Available today? | Evidence / gap |
|---|-----------------|----------------|------------------|----------------|
| 1 | **Failed imports** | Count of failed, non-archived import jobs; optional DSI vintage on latest batch | **Yes** (partial) | `GET /api/v1/dashboard/summary` → `kpis.failed_import_jobs` (`dashboard.py`). Batch DSI date requires joining latest `ImportJob` for `distributor_sales_inventory` template — not in one field today. |
| 2 | **SOH recon not run** | Book-wide trust block — derived cover unverified | **Partial** | `GET /api/v1/channel-ops/summary` → `has_reconciliation_data` (rows in `fact_inventory_reconciliation`). DSI post-apply enqueues `dsi_soh_reconciliation` task; no single “book recon not run” boolean aligned to Brief copy. `ChannelOpsOverviewTab.tsx` shows client banner text only. |
| 3 | **DSI vintage stale** | Latest DSI `completed_at`; age in days; stale threshold | **Yes** | `GET /api/v1/dashboard/summary` → `freshness.by_template`, `is_stale`, `newest_age_hours` (168h threshold). Filter to DSI template slug in federator. |
| 4 | **Sell-out gap** | Since date; count of accounts missing customer sales file | **No** (not as specified) | `dsi_coverage.py` + imports weekly-coverage endpoint flag **missed weeks per distributor** — not “N accounts since date”. No customer-account grain sell-out gap aggregator. **Cannot compute** mockup row without new read model. |
| 5 | **Cover breach** | Pairs under 4w; book mean WOC | **Partial — grain mismatch** | `GET /api/v1/channel-ops/summary` → `replenishment_pairs_below_threshold`, `weeks_of_cover` at **distributor×product** grain (`REPLENISHMENT_WOC_THRESHOLD_WEEKS` = 4). Packet contract is **customer×SKU** (119 pairs). Counts will not match `PACKET_DATA.md` without customer-grain WOC aggregation. |
| 6 | **Inbound open** | Open not-received **lines**; pipeline fill % | **Partial** | `dashboard.py` → `inbound_shipments_tracked` counts shipments `status != received` (shipment rows, not line grain). `GET /shipping/lineup-quarter-summary` → `shipped_not_landed_units`, `pipeline_units` (Unit 7). **Pipeline fill %** (received÷ordered on open pipeline) not exposed as a single API field — must be derived or added. |
| 7 | **Settlement blocked** | FX undeclared cases; ZAR held | **Yes** (after NS-1a display) | `case_missing_roe` / `missing_roe` on `GET /cpor/cases` list (`cpor_cases.py`, `settle_readiness.py`). Aggregate count + sum of outstanding ZAR for `missing_roe` cases feasible. `currency_mismatch` exists on payment recon flags — separate from undeclared ROE. |
| 8 | **Missing assumptions** | SKU count on open cases | **Partial** | Per-case `open_assumption_count` via `settle_readiness.py` (line flags). `commercial_sku_assumption` table + planner readiness `missing_sku_assumption`. No book-level “103 SKUs on open cases” endpoint; cross-case SKU distinct count needs new aggregation. |

### Federated Read (packet)

`PACKET_DATA.md`: Read traces to **current signal rows only** — no day-over-day deltas until
snapshotting exists. Example: failed imports + SOH recon + cover breach + settlement outstanding.

**Read inputs today:** fragments exist across dashboard summary, channel-ops summary, CPOR list —
no federated composer. NS-2 must implement Read assembly in `GET /brief/signals` (or equivalent)
with explicit provenance per C-NS2-03.

### Spine badge counts (packet)

| Nav item | Packet count | Live source today |
|----------|-------------:|-------------------|
| Brief | 8 | N/A — equals on-surface signal row count |
| Stock | 119 | Would need customer×SKU &lt;4w count (see signal #5 gap) |
| Settlement | 310 | `GET /cpor/cases` open book count — available |
| Response | 6 | No ranked-actions read model — **not available** |
| Steward | 23 | Same as failed imports count today — available via dashboard KPI |

Badges may ship `data_unavailable` per plan gate until backends ready.

### Signals that cannot be computed as specified at `12404bc`

1. **Sell-out gap** (#4) — account-level “missing file since date” not in API.
2. **Cover breach** (#5) — at customer×SKU grain with packet figures.
3. **Response spine badge** — no action queue API.
4. **Pipeline fill %** (#6) — not a named field; derivation required.

---

## 5. Reference artifacts (`brief.html` / `brief-empty.html`)

| Artifact | Role |
|----------|------|
| `docs/design/brief.html` | Populated grammar-3 blotter: spine with badge counts, tenant stamp (ASUS SA · 26Q3), federated Read strip, eight ranked signal rows with severity tick, meta, single suggested action per row. |
| `docs/design/brief-empty.html` | Full shell empty state (C-NS2-04): spine + Read + empty blotter copy — no KPI cards. |

Design language: `CIP_DESIGN_LANGUAGE.md` §4 item 3 — signal blotter; §3 spine 190px, no filter
bar on Brief (period from tenant stamp).

---

## 6. EIF unit declaration block (§4 — ready to paste)

From `docs/design/EIF_UNIT_DECLARATION.md` §4 — NS-2 implementation prompt block:

```markdown
## EIF unit framing (do not skip)

- **Mode:** task-mode delivery unit (programme YAML/schema not in repo — do not mutate `.eif/program/`).
- **design_experience facet:** required — author DESIGN_EXPERIENCE_RECORD sections per `.eif/DESIGN_EXPERIENCE_RECORD.md`.
- **target_artifact_class:** high_fidelity (acceptance criteria + record front matter).
- **Design authority:** `docs/design/CIP_DESIGN_LANGUAGE.md` **FROZEN v1.1 — 2026-08-30** + `docs/design/CIP_NAV_MAP.md`.
- **Charter:** `docs/AUTONOMOUS_BUILD_CHARTER.md` v1.3 — contract rows cite grammar (§4) + container (nav map) per amendment 6.
- **Divergence:** preserve frozen Workbench — table AS-IS rejected vs frozen exemplar selected; use Preservation rationale (≥3 directions not required when language is frozen).
- **Sameness (CR-006):** visual-vocabulary challenge mandatory — cannot blanket-na; justify frozen patterns vs reject generic dashboard slop.
- **Execution slots:** only `applicable` or `not_applicable` with rationale — not dummy `na`.
- **Smoke:** browser automation on localhost:3000 — not API/curl proof (`.cursor/rules/smoke-via-browser.mdc`).
- **Do not:** declare EIF programme, start programme nodes, run migrations, or self-PASS VERIFY.

---

### NS-2 — Brief landing (replaces Control tower /dashboard)

| Field | Value |
|-------|--------|
| Container | Brief — `CIP_NAV_MAP.md` §1 Landing / attention blotter |
| Grammar | 3 — Signal blotter (`CIP_DESIGN_LANGUAGE.md` §4 item 3) |
| Exemplars | `docs/design/brief.html`, `brief-empty.html` |
| Packet data | `docs/design/PACKET_DATA.md` — eight signal rows |
| Retires | Dashboard KPI cards; Exceptions inbox as a place |
| VERIFY note | Until NS-2 PASS, gate A5/A6 may still target `/dashboard` (`docs/VERIFY_DEBT_RUNBOOK.md`) |

Contract rows must include: ranked signal rows (no KPI cards), Read traces to listed signals, no filter bar (period from tenant stamp), single next action per row, grammar 3 + container Brief on every row.
```

---

## 7. Readiness summary

| Area | Ready? | Notes |
|------|--------|-------|
| Design spec + exemplars | **Yes** | FROZEN v1.1; `brief.html` / `brief-empty.html`; PACKET_DATA |
| Route disposition doc | **Yes** | `NAV_COVERAGE.md` — add `/brief` at build |
| Nav target defined | **Yes** | `CIP_NAV_MAP.md` + `NAMING.md` labels |
| `GET /brief/signals` | **No** | Must be built; compose from partial sources |
| All eight signals computable | **No** | #4 sell-out gap; #5 customer×SKU cover; #6 pipeline fill %; Response badge |
| NS-1a FX-blocked signal | **Mostly** | `missing_roe` on case list; aggregate endpoint missing |
| Landing redirect | **No** | Still `/dashboard` |
| `navConfig` six containers | **No** | Seven legacy groups |
| Shared shell extraction | **No** | Prerequisite for NS-3–NS-7 |
| VERIFY debt / main gate | **Clear** | 2026-08-31 · `12404bc` |

**Recommendation:** NS-2 implementation can start with contract rows + `GET /brief/signals`
returning available signals and `data_unavailable` for gaps (#4, #5 grain, Response badge) per
plan gate — or block until sell-out-gap and customer×SKU cover read models are scoped. Warren
decision: ship thin Brief vs complete signal federation first.

---

## 8. Related deferred items (from VERIFY close — not NS-2 blockers)

- CPOR case **#313** on `cip` — exclude from settlement evidence.
- Evidence-chip **pass** state — needs case with claim evidence rows for browser proof.
- HL **disposition** — backend has no disposition channel; only `mapping_override`.
