import { formatLocalMoney, type SettleReadiness } from '@/features/cpor/fxDisplay';

import { customerTitleBits } from './settlementDeskModel';
import {
  CORROBORATION_REASON,
  isCorroboration,
  stageFromCaseStatus,
  type Corroboration,
  type SettlementDeskLine,
  type SettlementDeskView,
} from './settlementDeskModel';

export type SettlementDeskCase = {
  id: number;
  case_code: string;
  customer_code: string | null;
  customer_name: string | null;
  promotion_type: string;
  window_start: string | null;
  window_end: string | null;
  status: string;
  currency_code?: string;
  decided_by?: string | null;
  created_at?: string | null;
  allowed_next?: string[];
  settle_readiness?: SettleReadiness;
  customer_id?: number | null;
  superseded_by_case_id?: number | null;
  ttl_support_zar?: number | null;
  ttl_support_usd?: number | null;
  fx_mode?: string | null;
  fx_proposed_rate?: number | null;
  fx_proposed_source?: string | null;
  fx_declared_at?: string | null;
  fx_declared_by?: string | null;
  needs_reapproval?: boolean;
  intelligence_exclude?: boolean;
};

export type SettlementDeskApiLine = {
  line_id: number;
  product_id: number | null;
  product_sku?: string | null;
  product_sales_model_name?: string | null;
  product_name?: string | null;
  distributor_id?: number | null;
  distributor_name?: string | null;
  estimate_qty: number;
  result_qty: number | null;
  cip_qty?: number | null;
  customer_qty?: number | null;
  corroboration?: string;
  corroboration_reason?: string;
  include_in_credit?: boolean;
  support_unit: number | null;
};

export type SettlementDeskApi = {
  case_id: number;
  status: string;
  window_start: string | null;
  window_end: string | null;
  claim_row_count: number;
  out_of_window_claim_rows?: number;
  unresolved_products?: { token: string; units: number }[];
  cst_reconciliation?: { available: boolean; reason?: string; divergence_count?: number };
  lines: SettlementDeskApiLine[];
  can_settle: boolean;
  settle_readiness?: SettleReadiness;
  desk?: {
    cip_amount: number | null;
    customer_amount: number | null;
    agreed_amount: number | null;
    paid_amount: number | null;
    paid_in_schema: boolean;
    hq_credit_amount: number | null;
    hq_credit_line_count: number;
    matched_count: number;
    open_count: number;
    cip_qty_grain: string;
    agreed_actor?: string | null;
  };
};

export function mapSettlementDeskView(
  detail: SettlementDeskCase,
  settlement: SettlementDeskApi,
): SettlementDeskView {
  const customer = customerTitleBits(detail.customer_name, detail.customer_code);
  const lines: SettlementDeskLine[] = (settlement.lines ?? []).map((row) => {
    const corr: Corroboration = isCorroboration(row.corroboration) ? row.corroboration : 'pending';
    return {
      id: String(row.line_id),
      sku: row.product_sku?.trim() || (row.product_id != null ? String(row.product_id) : '—'),
      salesModel: row.product_sales_model_name?.trim() || null,
      product: row.product_name?.trim() || '—',
      distributor: row.distributor_name?.trim() || '—',
      estimateQty: row.estimate_qty ?? 0,
      cipQty: row.cip_qty ?? null,
      customerQty: row.customer_qty ?? null,
      supportUnit: row.support_unit,
      corroboration: corr,
      corroborationReason: row.corroboration_reason || CORROBORATION_REASON[corr],
      includeInCredit: Boolean(row.include_in_credit),
    };
  });

  const distiNames = Array.from(new Set(lines.map((l) => l.distributor).filter((d) => d && d !== '—')));
  const desk = settlement.desk;
  const claimRowCount = settlement.claim_row_count ?? 0;
  const hasCip = lines.some((l) => l.cipQty != null);
  const matchedCount = desk?.matched_count ?? lines.filter((l) => l.corroboration === 'match').length;
  const openCount = desk?.open_count ?? lines.length - matchedCount;

  const evidence =
    claimRowCount > 0
      ? [
          {
            id: 'cip',
            title: 'CIP auto-recon vs sell-out (product grain, −31d floor)',
            secondary: 'cip_recon · system',
          },
          {
            id: 'customer',
            title: `Customer report · ${claimRowCount} claim rows`,
            secondary: 'customer_report',
          },
        ]
      : hasCip
        ? [
            {
              id: 'cip',
              title: 'CIP auto-recon vs sell-out (product grain, −31d floor)',
              secondary: 'cip_recon · system',
            },
          ]
        : [];

  return {
    caseId: detail.id,
    caseCode: detail.case_code,
    customerName: customer.name,
    customerCode: customer.code,
    programme: detail.promotion_type,
    windowLabel:
      detail.window_start || detail.window_end
        ? `${detail.window_start ?? '…'} → ${detail.window_end ?? '…'}`
        : '—',
    distributorName: distiNames.length === 1 ? distiNames[0] : distiNames.join(', ') || '—',
    currency: detail.currency_code || 'ZAR',
    openedOn: detail.created_at?.slice(0, 10) ?? null,
    endedOn: detail.window_end,
    stage: stageFromCaseStatus(detail.status, hasCip),
    status: detail.status,
    cipAmount: desk?.cip_amount ?? null,
    customerAmount: desk?.customer_amount ?? null,
    agreedAmount: desk?.agreed_amount ?? null,
    hqCreditAmount: desk?.hq_credit_amount ?? null,
    hqCreditLineCount: desk?.hq_credit_line_count ?? 0,
    matchedCount,
    openCount,
    claimRowCount,
    paidInSchema: false,
    settledWithoutClaims: detail.status === 'settled' && claimRowCount === 0,
    agreedActor: desk?.agreed_actor ?? detail.decided_by ?? null,
    lines,
    evidence,
    canSettle: Boolean(settlement.can_settle),
    fxSettleAllowed:
      (settlement.settle_readiness?.fx_settle_allowed ?? detail.settle_readiness?.fx_settle_allowed) !==
      false,
    fxDeclared: Boolean(
      settlement.settle_readiness?.fx_declared ?? detail.settle_readiness?.fx_declared,
    ),
    roeSnapshot:
      settlement.settle_readiness?.roe_snapshot ?? detail.settle_readiness?.roe_snapshot ?? null,
    fxBasisLine:
      settlement.settle_readiness?.fx_basis_line ?? detail.settle_readiness?.fx_basis_line ?? null,
    allowedNext: detail.allowed_next ?? [],
    supersededByCaseId: detail.superseded_by_case_id ?? null,
    approvedAmount: detail.ttl_support_zar ?? null,
    approvedUsd: detail.ttl_support_usd ?? null,
    fxMode: detail.fx_mode ?? null,
    fxBookedBy: detail.fx_declared_by ?? null,
    fxBookedAt: detail.fx_declared_at ?? null,
    fxProposedRate: detail.fx_proposed_rate ?? null,
    fxProposedSource: detail.fx_proposed_source ?? null,
    needsReapproval: Boolean(detail.needs_reapproval),
    intelligenceExclude: Boolean(detail.intelligence_exclude),
    settleReadiness: settlement.settle_readiness ?? detail.settle_readiness ?? null,
    outOfWindowClaimRows: settlement.out_of_window_claim_rows ?? 0,
    unresolvedProducts: settlement.unresolved_products ?? [],
    cstReconciliation: settlement.cst_reconciliation ?? null,
  };
}

export { formatLocalMoney };
