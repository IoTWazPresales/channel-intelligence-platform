# CURRENT state

**Last updated:** 2026-07-27 (Unit D implement — VERIFY pending)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `feat/cpor-listing-status-audit` |
| **Alembic (DB)** | **`20260727_0074` on cip** |
| **HEAD** | *(set after Unit D commit)* |
| **Pushed?** | pending |
| **Next** | Opus VERIFY Unit D → Unit E CONSULT (CST steward) |

---

## Standing quality bar

**Contract or STOP · no half-PASS · code is evidence.**  
Authoritative steward slot inventory: `docs/STEWARD_EXPERIENCE_CONTRACT.md` (**v1.4**).

**Consolidation arc:** A–C PASS; **Unit D implemented** (VERIFY next); E/F open.

---

## Unit D (this session)

| Label | Fact |
|-------|------|
| **Status** | Implemented; Opus VERIFY pending |
| **Shared** | `StewardEvidenceSummary` + `StewardSuggestionCards` (D-017); CPOR + shipment bind both |
| **Apply-all** | DSI moved to plan toolbar `onApplyAllReady`; workspace apply-all removed; apply-selected retained (D-016) |
| **Decisions** | D-016, D-017; contract **v1.4** |
| **Not proven** | Opus VERIFY; live soak |

---

## Unit C

| Label | Fact |
|-------|------|
| **Opus VERIFY** | **PASS** @ `4a63a30` |

---

## Unit B2 / B / A

| Label | Fact |
|-------|------|
| **B2 PASS** | @ `f9c49f9` |
| **B PASS** | @ `e625388` |
| **A PASS** | @ `ce1ca27` / pin `ead4e9f` |

---

## Do not

- Relocate CPOR into imports monolith
- Claim Unit 4 / Unit E done
- Invent `bulkStrategy` / engine capabilities
- Put importer-prefixed modules under `features/import-steward/` (D-006)
