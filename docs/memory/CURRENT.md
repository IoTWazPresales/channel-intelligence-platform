# CURRENT state

**Last updated:** 2026-07-26 (Unit B2 Opus VERIFY PASS)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `feat/cpor-listing-status-audit` |
| **Alembic (DB)** | **`20260720_0073` on cip** |
| **HEAD** | `f9c49f9` |
| **Pushed?** | yes |
| **Next** | **Unit C CONSULT blocked** — Claude CLI monthly spend limit (Opus + Fable). Raise limit / switch credits, then re-seed Unit C from `.cursor/templates/consult_seed_template.md` (seed already at `.tmp/unit_c_consult_opus_seed.md`). |

---

## Standing quality bar

**Contract or STOP · no half-PASS · code is evidence.**  
Authoritative steward slot inventory: `docs/STEWARD_EXPERIENCE_CONTRACT.md` (**v1.2**).

**Consolidation arc:** Units A–B shipped; Unit B2 implemented (VERIFY pending). C/D/E/F open (same session).

---

## CPOR historical import — status language

| Label | Fact |
|-------|------|
| **Proven** | H1; H2 apply; smoke `H2-SMOKE-556` |
| **Proven (this arc)** | Unit 1 suggestions @ `50c1ee8`; Unit 2 intelligence @ `ade5624`; Unit 3 upload-first @ `5044fce` |
| **Known contract gaps (v1.2)** | S9 absent; S6 nulled evidence; S12 unverified at volume; S14 `cporTokenRowId` — close in Unit C |
| **Out of scope** | Unit 4 config-driven `ImportJobResolutionSection`; relocate into `admin/imports/page.tsx` |

Route (keep): `/commercial-planner/cpor-cases/historical-import`

---

## Unit B2 (this session)

| Label | Fact |
|-------|------|
| **Opus VERIFY** | **PASS** @ `f9c49f9` — response `.tmp/unit_b2_verify_opus_response.md` |
| **Wired + unit-tested** | Shipment bulk preview→apply; binds `useStewardBulkSteward` + `StewardBulkSection`; deleted local bulk modules; toolbar summary chips + effective refresh; D-011/D-012; contract v1.2 |
| **Baselines (D-007)** | Locked API 17 files: PRE **113p/6s** → AFTER **114p/6s** (+1 ignore enqueue in shipment async). New preview suite 19p. Web vitest AFTER **204p**. Full tsc path+code NEW=0 vs PRE. |
| **D-002** | No `bulkStrategy`; provisional names via `getBulkBodyExtras`; global-suspicious waived (D-012) |
| **Not proven** | Live operator soak |

---

## Unit B

| Label | Fact |
|-------|------|
| **Opus VERIFY** | **PASS** @ `e625388` — response `.tmp/unit_b_verify_opus_response.md` |
| **Wired + unit-tested** | Core `useStewardResolutionPlan` geo-free; DSI composes geo; shipment binds plan engine |
| **Not proven** | Live operator soak |

---

## Unit A

| Label | Fact |
|-------|------|
| **Opus VERIFY** | **PASS** @ `ce1ca27` / pin `ead4e9f` |

---

## Parked — DSI unified multifile

- Branch `feat/dsi-unified-multifile` @ `2c2391e`; stash `park-dsi-asus-dealer-name-automap`

---

## Do not

- Relocate CPOR into imports monolith
- Auto-create dims; change DSI resolution tiers
- Claim Unit 4 done
- Create new `Dsi*` / `Shipment*` / `Cpor*` files under `features/import-steward/`
- Add `bulkStrategy` / capability flags that fossilize S8 in the engine core
- Close S6/S7 in this unit (Unit D)
