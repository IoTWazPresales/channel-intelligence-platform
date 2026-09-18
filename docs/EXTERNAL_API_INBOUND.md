# Inbound connector source — specification

**Status:** spec only. No endpoints, models, or migrations in the session that wrote this.
**Date:** 2026-09-18
**Audience:** data in from other platforms (marketplaces, ecom, 3PLs). Vendor-agnostic source class.
Do not design against Amazon or any one vendor’s docs.

Claims below are **VERIFIED** against the tree unless marked **ASSERTED**.

---

## Existing ingestion contract (VERIFIED)

Every importer follows `upload → parse → map → validate → steward → apply → derive`.
That is locked (`docs/STEWARD_EXPERIENCE_CONTRACT.md`, import-parity rule). A connector
is a new **way to obtain the file-equivalent payload**. It is not a new way to write facts.

| Piece | Where it lives | Rule |
|---|---|---|
| `import_template` | `apps/api/app/models/ingestion.py` | Type of work (product master, DSI, CST, shipments, CPOR, …). `pipeline_handler`, `expected_columns`. |
| `source_definition` | same | One provider/feed instance bound to one template. `source_kind` is a string (examples on `cip`: `catalog`, `file`, `pos_extract`, `carrier_extract`, `settlement_extract`, …). `product_catalog_id` is set on **one** row today (`product_catalog_default`). `column_mapping_memory` is source-scoped JSON. |
| Import job | `import_job` | File name, headers, mapping decisions, staged metadata, status/stage. |
| Steward | shared `features/import-steward/` + candidate tables | Unmapped tokens stay reviewable. No auto-create of `dim_product` / `dim_customer` / `dim_distributor`. |
| `source_key` | fact tables | Natural business key. Latest-job-wins on shipment facts. Transaction-immutable on sell-out / customer sales (update resolution FKs only). |
| FLAG ≠ BLOCK | domain-wide | Bad, unmatched, or out-of-window rows **flag**. They do not abort eligible applies. Unresolved entities do not mint masters. |

On this `cip` host there is already a CST source named `cst_p4_amazon` with `source_kind='file'`.
That is a **file importer labelled Amazon**, not a connector. Do not grow it into a vendor SDK.

Auth on write paths is mixed: session/`require_roles` on some routers; CPOR historical is
authentication-only pending BACKLOG-136. Inbound connectors must not copy the forgeable header pattern.

---

## Source class (to build)

**Name:** `ConnectorSource`  
**Does not get:** its own fact tables, its own steward UI, or a bypass apply.

### Shape

A connector is a `source_definition` whose intake channel is `connector` instead of `file`.

```
source_definition
  import_template_id     → existing template (cst, shipments, listings, …)
  code                   → stable feed id (tenant-scoped)
  source_kind            → keep the domain kind (e.g. pos_extract); do not replace it with "amazon"
  intake_channel         → file | connector     # ASSERTED: new column — report, do not migrate here
  connector_class        → registered adapter id (generic: rest_page, sftp_drop, object_notify)
  connector_config_json  → endpoint, schedule, cursor, secret ref — never vendor field names in CIP schema
  column_mapping_memory  → same as file sources
  product_catalog_id     → only if the template is product master
```

`intake_channel` is the only new axis. If Warren refuses a migration, store it under
`expected_template.intake_channel` until a migration is approved. **ASSERTED** preference:
a real column, because every job must filter on it.

### Runtime

1. Scheduler or webhook wakes the connector class.
2. Adapter fetches a **canonical payload** (tabular rows + headers + cursor), not a vendor object graph.
3. CIP creates an `import_job` as if a file had landed (`file_name` = `connector:{code}:{cursor}`).
4. Parse / map / validate / steward / apply are the **existing** pipeline for that template.
5. Progress uses the existing background-task slot registry. No silent thread.
6. Cursor persistence is on the source (watermark). Replay of the same cursor is idempotent
   because apply is `source_key` upsert.

The adapter may not:

- INSERT into fact tables
- create dimension rows
- auto-resolve below `AI_AUTO_RESOLVE_THRESHOLD`
- skip FLAG ≠ BLOCK
- write `TMP-*` as if they were masters

### Canonical payload

Vendor-agnostic on purpose:

```
{
  "headers": ["..."],
  "rows": [ { "header": value, ... } ],
  "received_at": iso,
  "cursor": opaque,
  "payload_sha256": "..."
}
```

Column mapping is the same steward mapping panel as a workbook. If the connector’s headers
drift, the job stops in map/validate like a bad file — it does not silently remap.

### Auth (day one)

- Inbound credentials live in a secret store; CIP holds a reference, not the secret in git or `source_definition` plaintext.
- Each connector token can POST only to **its** `source_definition_id`.
- Tenant is the instance. Partner-push (a retailer pushing CST into this CIP) is a scoped
  inbound principal, same grant model as outbound, write-scoped to one template.

### Versioning

- Connector class interface `v1`. New vendors = new **config**, not new CIP types.
- Payload schema version on the job (`staged_metadata.connector_payload_version`).
- When a vendor changes their API, the adapter absorbs it. CIP rows stay the template.

### Size

A session to land the class + one fake adapter that posts the canonical payload into an
existing CST or listings template on a disposable DB. Several sessions to productionize
scheduler, secrets, cursor, and steward UX parity (the job must look like any other job
in Import Center). A programme if “Amazon” is the first live vendor — that work starts
**after** Warren has a sample payload, not from vendor docs.

### Decisions Warren must make

1. First connector template: CST, listings, or inbound shipments?
2. Migration for `intake_channel` now, or JSON until the settlement/paid migration batch?
3. Pull (CIP polls) vs push (vendor/webhook posts the canonical payload)? Push is smaller
   and does not require vendor SDKs.
4. Who owns unmatched marketplace SKUs — steward as today, or a dedicated catalogue-gap
   worklist (BACKLOG-129 already names CST unmappable products)?
5. May a partner org push into this instance, or only CIP-owned pulls?

---

## Explicit non-goals

- Amazon SP-API, Takealot, or any named marketplace client in this spec.
- Auto-create of masters from connector evidence.
- A second apply path that writes facts in the request thread.
- Treating connector success as “all rows resolved”.
