# Import Flow Capability Contract — Phase 1 Design (for review)

> **Status:** DESIGN ONLY. Nothing in this document changes behavior. No code path
> imports anything proposed here yet. This is the review artifact that must be
> approved before Phase 2/3 wire it in.
>
> **Branch:** `feature/pm-specs-json-retire-eav` (do not merge to main).
>
> **Author intent:** Make the *legitimate* per-importer differences (Product Master =
> straight upsert, no steward; DSI/shipment = steward) explicit and declarative, so
> the wizard and the job-tracking layer stop hard-coding `isPm ? … : isDsi ? …`
> branches and stop hand-rolling a separate task-slot registration per importer.

---

## 1. Why this exists (the drift, with evidence)

Every importer follows the same conceptual pipeline
(`upload → parse → map → validate → steward → apply/commit → derive`), but each one
grew its **own** wiring. Audit findings (read-only) from this branch:

### 1a. Frontend wizard branches on slug literals
`apps/web/src/app/(app)/admin/imports/page.tsx` (~3,900 lines) hard-codes:

```310:495:apps/web/src/app/(app)/admin/imports/page.tsx
const stepsDefault = ['Import type', 'Data provider', 'Template details', 'Import mode', 'Upload & preview'];
const stepsShipmentEvidence = ['Import type', 'Data provider', 'Template details', 'Upload & preview'];
const stepsPm = [ 'Import type', 'Data provider', 'Template details', 'Upload file', 'Column mapping', 'Validate results', 'Commit to catalog' ];
const stepsDsi = [ 'Import type', 'Data provider', 'Template details', 'Import mode', 'Upload file', 'Column mapping', 'Validate', 'Apply' ];
...
const isPm = selectedSlug === 'product_master';
const isDsi = selectedSlug === 'distributor_inventory';
const isShipmentEvidence = selectedSlug === 'inbound_shipments';
const steps = isPm ? stepsPm : isDsi ? stepsDsi : isShipmentEvidence ? stepsShipmentEvidence : stepsDefault;
```

There are **80+** `isPm` / `isDsi` / `isShipmentEvidence` conditionals through the file
(step gating, mapping UI mounting, validate/commit/apply dispatch, steward panels).
Adding or changing an importer means editing this monolith in dozens of places.

### 1b. Job-tracking registration is copy-pasted per importer
Each background task hand-writes its **own** `staged_metadata` slot with its own key,
`kind`, and `label`. Examples of the *same* pattern duplicated:

- `product_master_workflow.py::_persist_pm_commit_task_metadata` → slot `pm_commit_task`, kind `product_master_commit`
- `product_master_workflow.py::_persist_pm_validate_task_metadata` → slot `pm_validate_task`, kind `product_master_validate`
- `dsi_velocity_enqueue.py::_persist_velocity_task_metadata` → slot `dsi_velocity_compute_task`, kind `dsi_velocity_compute` (and a **second** near-identical copy in `dispatch_dsi_velocity_after_apply`)
- `dsi_soh_reconciliation_enqueue.py`, `dsi_forecasting_enqueue.py`, `dsi_resolution_plan_enqueue.py`, `lineup_parse_dispatch.py` — each its own slot writer.

The **discovery** side (`background_tasks.py::_build_background_task_records`) then
hand-codes a parallel reader block per slot, and `_clear_task_slot_metadata` hand-codes
a parallel clearer per slot. Three places, per importer, must stay in lock-step.

> **Phase 0 (already shipped on this branch) was a symptom of exactly this drift:**
> PM commit was invisible in the activity feed because nobody had written a
> `pm_commit_task` slot and `background_tasks.py` had no reader for it. The fix was
> correct but importer-specific — the *next* importer can reintroduce the same gap.

### 1c. Latent bug the contract would prevent
`import_job_background_metadata.py::clear_background_task_metadata` (used by
**cancel** and **retry** in `import_job_task_control.py`) only strips
`celery_task_id` and `dsi_bulk_task`:

```82:91:apps/api/app/services/imports/import_job_background_metadata.py
def clear_background_task_metadata(meta: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return staged_metadata without background-task keys (or None if empty)."""
    if not isinstance(meta, dict):
        return None
    m = dict(meta)
    m.pop("celery_task_id", None)
    m.pop("dsi_bulk_task", None)
    m.pop("pipeline_queued_at", None)
    m.pop("pipeline_started_at", None)
    return to_jsonable(m) if m else None
```

It does **not** clear `pm_commit_task`, `pm_validate_task`, `dsi_soh_reconcile_task`,
`dsi_velocity_compute_task`, `dsi_forecasting_task`, or `lineup_parse_task`. Cancelling
or retrying a job can therefore leave an **orphan slot** that the activity feed keeps
discovering. A single registry of slots (this contract) removes the possibility of
forgetting one. *(Not fixed in Phase 1 — recorded as the concrete Phase 2 payoff.)*

### 1d. `customer_sell_through` is invisible to the generic UI contract
`customer_sell_through` was seeded into the DB via migration `0045`, **not** present in
`template_definitions.py::IMPORT_TEMPLATE_ROWS`, and has no wizard branch. It runs
through its own parser/apply modules (`customer_sell_through*.py`). It is a real
importer with no row in the declarative source of truth — the contract must name it.

---

## 2. What already exists that we build on (not a greenfield)

The DB `import_template` row (seeded from `template_definitions.py`) already carries a
**partial** contract. Today's fields:

| Existing field | Meaning |
|---|---|
| `slug` | Importer identity (`product_master`, `distributor_inventory`, …) |
| `pipeline_handler` | Server dispatch key (`product_master_upsert`, `distributor_sales_inventory`, `shipment_evidence_import`, `stub_noop`, …) |
| `destructive_apply_requires_confirm` | Whether apply needs `confirm=true` |
| `requires_provider` | Whether a data-provider/source must be chosen |
| `enabled` / `hidden` / `admin_only` | Visibility/governance |
| `accepted_file_types` | Upload filter |
| `expected_columns` | Alias map for auto-mapping |

`GET /api/v1/imports/templates` also derives `pipeline_ready = pipeline_handler not in ('stub_noop',)`.

**The capability contract is the missing layer:** it describes *how the flow behaves*
(steps, mapping UI kind, steward, apply semantics, tracking) — not just *what the
template is*. It is **additive** to the existing template row.

---

## 3. The contract schema (proposed)

One declarative record per importer slug. Field set requested by the user, plus the
minimum extra fields the audit shows are needed to actually retire the branching.

| Field | Type | Semantics | Why it's needed |
|---|---|---|---|
| `slug` | `str` | Matches `import_template.slug` | Join key to existing template row |
| `steps` | `list[StepId]` | Ordered wizard steps (enum, see §4) | Replaces `stepsPm`/`stepsDsi`/… literals |
| `needs_mapping` | `bool` | Has an explicit column-mapping step | Gates the mapping step + endpoints |
| `mapping_ui` | `MappingUiKind \| null` | Which mapping component renders (`pm_columns`, `dsi_canonical`, `shipment_canonical`, `historical_lineup`, `none`) | Replaces `isPm`/`isDsi`/`isShipment` mapping mounts |
| `needs_steward` | `bool` | Entity resolution requires human steward review | Distinguishes DSI/shipment from PM/master upserts |
| `steward_surface` | `StewardSurface \| null` | Where stewarding happens (`inline_wizard`, `dsi_resolution_section`, `shipment_evidence_admin`, `null`) | Steward is not always in the wizard |
| `apply_mode` | `ApplyMode` | Terminal write semantics (see §3a) | Legitimises PM commit vs DSI apply vs master upsert |
| `apply_requires_confirm` | `bool` | Mirror of `destructive_apply_requires_confirm` | Keep contract self-contained for the UI |
| `tracking_kinds` | `list[TrackingKind]` | Background task kinds this importer can register (see §3b) | The single registry that Phase 2 consumes |
| `archives_on_complete` | `bool` | Whether a finished job auto-archives (hidden from default job list) | PM/DSI = **false** (stay visible); records the Phase 0 decision |
| `import_mode_choice` | `bool` | Wizard exposes a validate/apply (or historical/weekly) mode selector | DSI + generic masters show it; PM/shipment do not |
| `hidden_from_generic_ui` | `bool` | Importer is driven by a dedicated surface, not the generic wizard | `current_lineup` (Commercial Planner), `customer_sell_through` |

### 3a. `ApplyMode` enum

| Value | Meaning | Importers |
|---|---|---|
| `pm_commit` | Two-phase: validate → commit; upserts `dim_product` + `catalog_product`, writes specs to `dim_product.specs_json` | `product_master` |
| `master_upsert` | Single-pass validate/apply upsert into a `dim_*` table | `distributor_master`, `customer_master` |
| `fact_upsert_after_steward` | Validate → steward entity resolution → apply upserts `fact_*` tables; never auto-creates masters | `distributor_inventory`, `inbound_shipments`, `customer_sell_through` |
| `parse_to_history` | Parses workbook into normalized history/lineup tables (no `dim_*`/`fact_*` upsert) | `historical_lineup` |
| `external_surface` | Apply is owned by another module's flow, not generic imports | `current_lineup` (Commercial Planner) |
| `stub_noop` | Scaffold only; stores file + inferred schema, no loader | `customer_channel_mapping`, `pricing_support`, `lineup_plan`, `promotion_plan`, `customer_inventory_sales` |

### 3b. `TrackingKind` enum (the slot registry)

These are the **exact** `kind` strings the activity feed already understands. The
contract is the single place that maps a slot key → kind → label, replacing the
duplicated `_persist_*_task_metadata` writers and the parallel readers in
`background_tasks.py`.

| `tracking_kind` | `staged_metadata` slot key | Label template | Registered by (today) |
|---|---|---|---|
| `product_master_validate` | `pm_validate_task` | `Validating product master (job N)` | `pm_validate_sync` / workflow |
| `product_master_commit` | `pm_commit_task` | `Committing product master…` | `product_master_workflow` |
| `dsi_pipeline` | `celery_task_id` (main) | `Validating/Processing DSI import N` | DSI validate dispatch |
| `dsi_bulk_provisional` | `dsi_bulk_task` (kind=…) | `Creating provisional customers (DSI job N)` | `dsi_bulk_provisional_customers_sync` |
| `dsi_resolution_plan_apply` | `dsi_bulk_task` (kind=…) | `Applying resolution plan (DSI job N)` | `dsi_resolution_plan_enqueue` |
| `dsi_soh_reconciliation` | `dsi_soh_reconcile_task` | `Reconciling inventory…` | `dsi_soh_reconciliation_enqueue` |
| `dsi_velocity_compute` | `dsi_velocity_compute_task` | `Computing sell-out velocity…` | `dsi_velocity_enqueue` |
| `dsi_forecasting` | `dsi_forecasting_task` | `Generating forecasts…` | `dsi_forecasting_enqueue` |
| `shipment_import` | `celery_task_id` (main) | `Processing shipment import N` | shipment validate dispatch |
| `commercial_planner_lineup_parse` | `lineup_parse_task` | `Parsing current lineup…` | `lineup_parse_dispatch` |

> The contract does **not** invent new kinds. It catalogs the ones already in
> `background_tasks.py::_task_label` and `_build_background_task_records`, so Phase 2
> can generate the writer + reader + clearer from one table instead of three.

---

## 4. `StepId` enum (proposed)

Canonical step identifiers (the wizard renders a label per id; ordering comes from
`steps`). This replaces the four hard-coded label arrays.

| `StepId` | Default label | Used by |
|---|---|---|
| `import_type` | "Import type" | all |
| `data_provider` | "Data provider" | all with `requires_provider` |
| `template_details` | "Template details" | all |
| `import_mode` | "Import mode" | importers with `import_mode_choice` |
| `upload` | "Upload file" / "Upload & preview" | all |
| `column_mapping` | "Column mapping" | importers with `needs_mapping` |
| `validate` | "Validate" | PM, DSI, shipment |
| `commit` | "Commit to catalog" | `product_master` |
| `apply` | "Apply" | DSI |

The exact current step arrays map cleanly:

- **PM** → `[import_type, data_provider, template_details, upload, column_mapping, validate, commit]`
- **DSI** → `[import_type, data_provider, template_details, import_mode, upload, column_mapping, validate, apply]`
- **Shipment** → `[import_type, data_provider, template_details, upload, column_mapping, validate_resolve, apply]` *(DSI-aligned wizard; steward on validate step — 2026-06-24)*
- **Default (masters/historical)** → `[import_type, data_provider, template_details, import_mode, upload]`

---

## 5. Per-importer capability matrix (every importer)

> This is the heart of the contract. It is the single declarative source of truth that
> *legitimises* the differences while *exposing* the drift.

| slug | steps | needs_mapping | mapping_ui | needs_steward | steward_surface | apply_mode | confirm | archives_on_complete | mode_choice | hidden_from_generic_ui | tracking_kinds |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **product_master** | type,provider,details,upload,mapping,validate,commit | yes | `pm_columns` | no | — | `pm_commit` | yes | **no** | no | no | `product_master_validate`, `product_master_commit` |
| **distributor_inventory** (DSI) | type,provider,details,mode,upload,mapping,validate,apply | yes | `dsi_canonical` | **yes** | `dsi_resolution_section` | `fact_upsert_after_steward` | yes | **no** | yes (auto/historical/weekly) | no | `dsi_pipeline`, `dsi_bulk_provisional`, `dsi_resolution_plan_apply`, `dsi_soh_reconciliation`, `dsi_velocity_compute`, `dsi_forecasting` |
| **inbound_shipments** | type,provider,details,upload,mapping,validate,apply | yes | `shipment_canonical` | **yes** | `dsi_resolution_section` † | `fact_upsert_after_steward` | no | no | no | no | `shipment_import` |
| **distributor_master** | type,provider,details,mode,upload | no | `none` | no | — | `master_upsert` | no | no | yes (validate/apply) | no | *(none — inline sync)* |
| **customer_master** | type,provider,details,mode,upload | no | `none` | no | — | `master_upsert` | no | no | yes (validate/apply) | no | *(none — inline sync)* |
| **historical_lineup** (admin) | type,provider,details,mode,upload | yes (override) | `historical_lineup` | no | — | `parse_to_history` | no | no | yes | no | *(none — inline sync)* |
| **customer_sell_through** | *(own surface)* | yes | own surface (deferred) | **yes** | own surface (deferred) | `fact_upsert_after_steward` | no | no | own surface (deferred) | **yes** | *(own surface — parsers, see §1d / §10 D1)* |
| **cpor_historical_cases** | *(own surface — H2 wizard)* | yes | `cpor_canonical` | **yes** | `dsi_resolution_section` (shared workspace) | `fact_upsert_after_steward` | yes | no | no | **yes** | `cpor_historical_import` |
| **current_lineup** (hidden) | *(Commercial Planner upload)* | yes (parse) | external | no | — | `external_surface` | no | n/a | n/a | **yes** | `commercial_planner_lineup_parse` |

> † **`inbound_shipments` steward surface** (updated 2026-06-24): 7-step wizard aligned with DSI
> (upload → mapping → validate & resolve → apply). Steward uses `ImportStewardCandidateWorkspace`
> + `ShipmentImportJobResolutionSection` on the validate step (`dsi_resolution_section` parity).

Scaffold/`stub_noop` templates (`customer_channel_mapping`, `customer_inventory_sales`,
`pricing_support`, `lineup_plan`, `promotion_plan`) all collapse to:
`steps=[type,provider,details,mode,upload]`, `needs_mapping=no`, `mapping_ui=none`,
`needs_steward=no`, `apply_mode=stub_noop`, `tracking_kinds=[]`. The contract records
them so "scaffold" is a declared state, not an implicit fall-through.

---

## 6. Proposed types (for review — NOT yet created as files)

### 6a. Python (would live in a new `app/services/imports/import_flow_contract.py`)

```python
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum


class StepId(str, Enum):
    IMPORT_TYPE = "import_type"
    DATA_PROVIDER = "data_provider"
    TEMPLATE_DETAILS = "template_details"
    IMPORT_MODE = "import_mode"
    UPLOAD = "upload"
    COLUMN_MAPPING = "column_mapping"
    VALIDATE = "validate"
    COMMIT = "commit"
    APPLY = "apply"


class MappingUiKind(str, Enum):
    NONE = "none"
    PM_COLUMNS = "pm_columns"
    DSI_CANONICAL = "dsi_canonical"
    SHIPMENT_CANONICAL = "shipment_canonical"
    HISTORICAL_LINEUP = "historical_lineup"
    EXTERNAL = "external"


class StewardSurface(str, Enum):
    INLINE_WIZARD = "inline_wizard"
    DSI_RESOLUTION_SECTION = "dsi_resolution_section"
    SHIPMENT_EVIDENCE_ADMIN = "shipment_evidence_admin"


class ApplyMode(str, Enum):
    PM_COMMIT = "pm_commit"
    MASTER_UPSERT = "master_upsert"
    FACT_UPSERT_AFTER_STEWARD = "fact_upsert_after_steward"
    PARSE_TO_HISTORY = "parse_to_history"
    EXTERNAL_SURFACE = "external_surface"
    STUB_NOOP = "stub_noop"


class TrackingKind(str, Enum):
    PRODUCT_MASTER_VALIDATE = "product_master_validate"
    PRODUCT_MASTER_COMMIT = "product_master_commit"
    DSI_PIPELINE = "dsi_pipeline"
    DSI_BULK_PROVISIONAL = "dsi_bulk_provisional"
    DSI_RESOLUTION_PLAN_APPLY = "dsi_resolution_plan_apply"
    DSI_SOH_RECONCILIATION = "dsi_soh_reconciliation"
    DSI_VELOCITY_COMPUTE = "dsi_velocity_compute"
    DSI_FORECASTING = "dsi_forecasting"
    SHIPMENT_IMPORT = "shipment_import"
    COMMERCIAL_PLANNER_LINEUP_PARSE = "commercial_planner_lineup_parse"


@dataclass(frozen=True)
class TrackingSlot:
    """One background-task slot in import_job.staged_metadata.

    The single registry that Phase 2's shared register/discover/clear helper consumes,
    so a slot can never again be written without a matching reader/clearer."""
    kind: TrackingKind
    slot_key: str           # e.g. "pm_commit_task"
    label_template: str     # e.g. "Committing product master…"
    uses_main_celery_id: bool = False  # True for dsi_pipeline / shipment_import


@dataclass(frozen=True)
class ImportFlowCapability:
    slug: str
    steps: tuple[StepId, ...]
    needs_mapping: bool
    mapping_ui: MappingUiKind
    needs_steward: bool
    steward_surface: StewardSurface | None
    apply_mode: ApplyMode
    apply_requires_confirm: bool
    archives_on_complete: bool
    import_mode_choice: bool
    hidden_from_generic_ui: bool
    tracking_kinds: tuple[TrackingKind, ...] = ()


# Registry would be defined here, one entry per slug (see §5). Read-only.
# A GET /api/v1/imports/templates response could embed `capability` per template
# in a LATER phase (additive, no removal of existing fields).
```

### 6b. TypeScript (would live in `packages/types/` or `apps/web/src/features/import-steward/`)

```typescript
export type StepId =
  | 'import_type' | 'data_provider' | 'template_details' | 'import_mode'
  | 'upload' | 'column_mapping' | 'validate' | 'commit' | 'apply';

export type MappingUiKind =
  | 'none' | 'pm_columns' | 'dsi_canonical' | 'shipment_canonical'
  | 'historical_lineup' | 'external';

export type StewardSurface =
  | 'inline_wizard' | 'dsi_resolution_section' | 'shipment_evidence_admin';

export type ApplyMode =
  | 'pm_commit' | 'master_upsert' | 'fact_upsert_after_steward'
  | 'parse_to_history' | 'external_surface' | 'stub_noop';

export type TrackingKind =
  | 'product_master_validate' | 'product_master_commit'
  | 'dsi_pipeline' | 'dsi_bulk_provisional' | 'dsi_resolution_plan_apply'
  | 'dsi_soh_reconciliation' | 'dsi_velocity_compute' | 'dsi_forecasting'
  | 'shipment_import' | 'commercial_planner_lineup_parse';

export interface ImportFlowCapability {
  slug: string;
  steps: StepId[];
  needsMapping: boolean;
  mappingUi: MappingUiKind;
  needsSteward: boolean;
  stewardSurface: StewardSurface | null;
  applyMode: ApplyMode;
  applyRequiresConfirm: boolean;
  archivesOnComplete: boolean;
  importModeChoice: boolean;
  hiddenFromGenericUi: boolean;
  trackingKinds: TrackingKind[];
}

export const STEP_LABELS: Record<StepId, string> = {
  import_type: 'Import type',
  data_provider: 'Data provider',
  template_details: 'Template details',
  import_mode: 'Import mode',
  upload: 'Upload file',
  column_mapping: 'Column mapping',
  validate: 'Validate',
  commit: 'Commit to catalog',
  apply: 'Apply',
};
```

---

## 7. How it gets consumed (later phases — recorded, NOT built now)

- **Phase 2 (job-tracking unification):** `TrackingSlot` registry becomes the single
  source for a shared `register_background_task(job, kind, task_id)` helper plus a
  generic discover/clear loop in `background_tasks.py`. Kills the duplicated
  `_persist_*_task_metadata` writers and the §1c clear-metadata bug.
- **Phase 3 (wizard componentization):** the React wizard reads `ImportFlowCapability`
  from a **static client map first** (decision D2) to drive `steps`, mount the
  `mapping_ui` component, and gate validate/commit/apply — replacing the
  `isPm/isDsi/isShipment` chain. Flag-gated, one importer at a time, gated behind
  proving the core loop end-to-end. **Upgrade path:** if the app grows enough that the
  map drifts from the server (or new importers are added dynamically), promote the
  contract to a `capability` field on `GET /api/v1/imports/templates` — additive, no
  removal of the static map's shape.
- **Phase 4 (Supabase write optimizations):** unaffected by the contract, but the
  contract makes `apply_mode` an explicit hook for where bulk `INSERT…ON CONFLICT`
  applies.

**No phase here changes behavior until separately planned and approved.**

---

## 8. Explicit no-behavior-change statement (Phase 1)

- This is a **Markdown design doc only**. No `.py` / `.ts` source file is created or
  modified by Phase 1.
- No template row, model, migration, endpoint, or wizard code is touched.
- The proposed types in §6 are **illustrative**; they are not imported anywhere.
- Approval of this contract authorizes only the *next* planning step (Phase 2 file-level
  plan), not implementation.

---

## 9. Resolved decisions (user, 2026-05-31)

These answer the original open questions and are now binding for Phase 2/3 planning.

| # | Decision | Effect on the contract |
|---|---|---|
| **D1** | **`customer_sell_through` = its own surface** (like `current_lineup`), not the generic wizard. | `hidden_from_generic_ui = yes`. Its `mapping_ui` / `steward_surface` / `import_mode_choice` are **deferred to its own surface design**; `needs_steward = yes`, `apply_mode = fact_upsert_after_steward`, `apply_requires_confirm = no`. |
| **D2** | **Static client map first** for delivering the contract to the web app. | Phase 3 reads a static `ImportFlowCapability` map (§6b). Documented **upgrade path**: promote to a `capability` field on `GET /api/v1/imports/templates` *if* app complexity/size makes the static map drift — additive, no shape change. |
| **D3** | **TS types live in `packages/types/`** (shared), per recommendation. | §6b types target `packages/types/`; web + any future tooling import from there. |
| **D4** | **`inbound_shipments` wizard** promoted to explicit mapping / validate / apply steps (shipped 2026-06-24). | Shipment row: 7 steps; `steward_surface = dsi_resolution_section` (see §5 †). |
| **D5** | **§5 matrix committed as-is** — it is a **living document**, corrected during review, not code. | Matrix is canonical; edit in place as understanding sharpens. |

> §10 captures any matrix corrections made after this commit (add-only log).

---

## 10. Living-doc correction log (add-only)

Record matrix/contract corrections here as the doc is reviewed. Newest first. Do not
rewrite §5 history silently — note what changed and why.

- **2026-05-31** — Initial contract committed with decisions D1–D5 applied (§9). Matrix
  in §5 is the canonical starting point. No corrections yet.

- **2026-06-04** — Cross-importer alignment pass (branch `fix/shipment-steward-performance`).
  Canonical patterns are now recorded as an enforced rule in `.cursor/rules/import-parity.mdc`
  (steward = shared `ImportStewardCandidateWorkspace` + tabs + `confidenceBand`; apply = async
  dispatch broker→dev-thread→sync-fallback with progress + registered task slot; resolution =
  shared `try_ai_token_resolution`; mapping = `CanonicalColumnMappingPanel`; writes = set-based
  chunked `INSERT…ON CONFLICT`). Shipped on this branch:
  - **Shipment bulk steward → async** (commit `f4f327d`): `bulk-map-customer`,
    `bulk-apply-confirmed-plans`, `bulk-create-provisional-customers` now run as Celery tasks with
    progress; new `shipment_bulk_task` registered slot (orphan-slot fix); fire-and-poll + confidence
    banding in the panel. *(Structural panel→workspace swap still BACKLOG-001.)*
  - **DSI apply → async** (commit `c079cc6`, backend): `post_dsi_apply` dispatches `imports.dsi_apply`
    (pipeline-apply → complete-to-loaded) instead of running inline; SOH/velocity/forecasting stay
    their own tasks. Frontend `dsiApplyAsync` poll wired in the working tree (commit pending — see
    BACKLOG).
  - **customer_sell_through** (commit `09d21ef`, backend): added the missing `IMPORT_TEMPLATE_ROWS`
    entry (§1d closed — now in the declarative source, matching migration 0045); batched the per-row
    fact upsert; normalized its AI calls onto the shared wrapper. Minimal drivable web surface still
    deferred (BACKLOG).
  - **Out-of-scope alignment gaps** (AI resolver for `distributor_master` + `historical_lineup`;
    generic-pipeline async apply; PM two-pipeline consolidation; PM/historical mapping-UI fork;
    slot-registration / enqueue-helper dedup) captured in `docs/BACKLOG.md` with triggers.
