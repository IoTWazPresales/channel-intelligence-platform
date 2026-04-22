# Platform Import System Truth

## Template/source model
- Import behavior is template-driven (`import_template`) and source-bound (`source_definition`).
- Template flags control visibility, admin-only constraints, file types, and destructive-confirm requirements.
- Source can carry parser hints, expected template overrides, and optional target product catalog linkage.

## Generic import lifecycle
- `POST /api/v1/imports/jobs` stores file and creates `import_job`.
- For non-Product-Master templates, sync processing can run in-process (`process_import_job_sync`).
- Pipeline stages include uploaded/raw/schema/mapped/validated/loaded/failed semantics.

## Product Master constrained lifecycle
- Dedicated endpoints under `/api/v1/imports/product-master/jobs/*`.
- Stages:
  - upload/infer headers
  - mapping decisions save
  - validate (staged metadata + row results)
  - commit (background, async status model)
- Mapping allows canonical targets plus explicit dispositions (`ignore`, `stage_raw`, `attribute_candidate`).

## Persistence behavior
- Validation pass writes staging snapshot (`staged_metadata`) and messages in `import_row_result`.
- Commit writes canonical product updates and optional catalog/EAV materialization.
- Commit-level state and diagnostics persist in `pm_commit_meta` and `error_summary`.

## Notable import truths/quirks
- Product Master bypasses legacy generic one-shot processing once constrained workflow metadata exists.
- Descriptor-row stripping, scalar normalization, and mapper-memory behavior are explicitly tested in API suite.
- Generic async import task exists in worker but is not the dominant API-triggered runtime path today.

## Operationally meaningful risk notes
- Import outcomes are observable via rows + progress metadata, but cross-job lineage reporting is still mostly per-job/manual.
- Product Master has stronger state machine controls than many other import templates, which are still lighter-weight.
