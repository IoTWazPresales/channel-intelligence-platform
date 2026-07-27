# CURRENT state

**Last updated:** 2026-07-27 (Unit C implement — VERIFY pending)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `feat/cpor-listing-status-audit` |
| **Alembic (DB)** | **`20260727_0074` on cip** (token surrogate) |
| **HEAD** | `32e4afb` (implement `4a63a30` + CURRENT pin) |
| **Pushed?** | yes |
| **Next** | **Unit C VERIFY blocked** — Claude CLI monthly spend limit (Opus + Fable). Raise limit / switch credits, then re-run `.tmp/unit_c_verify_opus_seed.md`. On PASS → Unit D CONSULT. |

---

## Standing quality bar

**Contract or STOP · no half-PASS · code is evidence.**  
Authoritative steward slot inventory: `docs/STEWARD_EXPERIENCE_CONTRACT.md` (**v1.3**).

**Consolidation arc:** A–B2 PASS; **Unit C implemented** (VERIFY next); D/E/F open (same session).

---

## CPOR historical import — status language

| Label | Fact |
|-------|------|
| **Proven** | H1; H2 apply; smoke `H2-SMOKE-556` |
| **Proven (this arc)** | Unit 1–3; Unit C: S9 plan + S12 pagination + S14 surrogate + S6/S4 payload |
| **Known contract gaps (v1.3)** | S6/S7 **drawer UI** → Unit D (payload done) |
| **Out of scope** | Unit 4 config-driven section; relocate into imports monolith |

Route (keep): `/commercial-planner/cpor-cases/historical-import`

---

## Unit C (this session)

| Label | Fact |
|-------|------|
| **Status** | Implemented; Opus VERIFY pending |
| **Migration** | `20260727_0074` — `import_cpor_historical_token_surrogate` (+ grants); applied on cip |
| **Backend** | Surrogate get-or-create; candidates enrichment + server pagination/`plan_class`; resolution-plan compute/apply async; tasks `imports.cpor_historical_resolution_plan_*`; slot `SLOT_CPOR_RESOLUTION_PLAN` ≠ SLOT_MAIN; case-apply untouched |
| **Web** | `CPOR_HISTORICAL_ENGINE_CONFIG` + `useStewardResolutionPlan`; `useCporCandidatesPage` + `StewardCandidatesPagination`; deleted `cporTokenRowId`; apply-all in plan toolbar (D-015) |
| **Decisions** | D-013, D-014, D-015; contract **v1.3** |
| **Tests** | API `test_cpor_historical_unit_c.py` 28p + slots; web section 7p |
| **Not proven** | Live operator soak; Opus VERIFY |

---

## Unit B2

| Label | Fact |
|-------|------|
| **Opus VERIFY** | **PASS** @ `f9c49f9` |

---

## Unit B / A

| Label | Fact |
|-------|------|
| **Unit B PASS** | @ `e625388` |
| **Unit A PASS** | @ `ce1ca27` / pin `ead4e9f` |

---

## Parked — DSI unified multifile

- Branch `feat/dsi-unified-multifile` @ `2c2391e`; stash `park-dsi-asus-dealer-name-automap`

---

## Do not

- Relocate CPOR into imports monolith
- Claim Unit 4 done
- Invent `bulkStrategy` / engine capabilities
- Put `Cpor*` modules under `features/import-steward/`
- Close S6/S7 drawer **UI** in Unit C (Unit D)
