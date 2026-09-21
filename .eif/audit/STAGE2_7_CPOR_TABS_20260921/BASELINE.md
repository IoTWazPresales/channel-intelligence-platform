# N-0032 implementation baseline — observed at `e264410`

**Run:** `STAGE2_7_CPOR_TABS_20260921` · **Actor:** `stage2b-001` · **Date:** 2026-09-21 · **Provenance:** implementation-observation

## Observed behaviour before change

| Surface | Observed |
|---|---|
| `/commercial-planner/cpor-cases/[id]` | Renders `SettlementDeskLive` inside `FundingChrome` (`492795c`): case header + stage rail + headline strip + overlap panel + lines grid + Next-action panel + supersede/settle dialogs. **No tabs.** |
| `features/cpor/CporCaseWorkspace.tsx` | **Unmounted** (only `page.fxReadiness.test.tsx` references it). Holds seven tabs: Lines, USD pivot (renders `<pre>{JSON.stringify(pivot.cells)}</pre>`), Events (plain `Typography` list), Exports (Generate + version list + Download), Settlement (superseded by the desk), Promo load (`CporPromoLoadPanel`), Payments/recon (`CporPaymentEvidencePanel`). Also holds `CporFxAnchorPanel`, `CporSettleReadinessRow`, `CporComparableCasesPanel` and the lifecycle transition buttons — none of which the desk has. |
| Endpoints used by the five tabs | `GET /api/v1/cpor/cases/{id}/pivot`, `GET …/events`, `GET …/exports`, `POST …/export`, `GET …/exports/{v}/file`, plus the two panels' own `…/promo-load-recon` and `…/payment-evidence` / `…/payment-recon`. All exist; none change. |
| BACKLOG-093 | Promo-load recon recorded by the roadmap as shipped A2 (2026-08-08) "case tab + `…/promo-load-recon`" — the tab is unreachable in production today. |

## Latent capabilities to preserve

- Desk single primary CTA in the header; Next-action panel copy and `DualMoney` figures
- `SettlementConfirmDialog` and `CporCaseSupersedeDialog` wiring in `SettlementDeskLive`
- `CporCaseWorkspace` continues to render for `page.fxReadiness.test.tsx` (case 312 shape) — FX anchor, settle-readiness row, comparable cases, transition buttons stay reachable there until a later node ports them
- `CporPromoLoadPanel` and `CporPaymentEvidencePanel` behaviour and test ids (`cpor-promo-load*`, `cpor-payment-*`, `cpor-recon-*`)
- Export download URL shape `/api/v1/cpor/cases/{id}/exports/{version}/file`
- `missing_roe` copy: "FX undeclared — USD pivot totals are withheld until a case rate of exchange is recorded."

Scope decision recorded up front: `CporCaseWorkspace` is **not** deleted in this node (AC 7) — the desk lacks four of its capabilities. BACKLOG-202 will say exactly which.
