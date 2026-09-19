'use client';

import { fmtCurrency } from '../fixtures/entities';
import {
  lineAmount,
  settleCase,
  settleEvidence,
  settleLines,
  type SettleLine,
} from '../fixtures/settlementDesk';
import { SettlementDesk } from '@/features/settlement/SettlementDesk';
import {
  CORROBORATION_REASON,
  customerTitleBits,
  type Corroboration,
  type SettlementDeskView,
} from '@/features/settlement/settlementDeskModel';

function toView(): SettlementDeskView {
  const customer = customerTitleBits(settleCase.customer, settleCase.customerCode);
  const creditLines = settleLines.filter((l) => l.includeInCredit);
  const creditAmount = creditLines.reduce((s, l) => s + lineAmount(l.customerQty ?? 0, l.supportUnit), 0);
  const matched = settleLines.filter((l) => l.corroboration === 'match');
  const open = settleLines.filter((l) => l.corroboration !== 'match');
  return {
    caseId: settleCase.id,
    caseCode: settleCase.id,
    customerName: customer.name,
    customerCode: customer.code,
    programme: settleCase.programme,
    windowLabel: settleCase.window,
    distributorName: settleCase.distributor,
    currency: settleCase.currency,
    openedOn: settleCase.openedOn,
    endedOn: settleCase.endedOn,
    stage: settleCase.stage,
    status: 'settled',
    cipAmount: settleCase.cipAmount,
    customerAmount: settleCase.customerAmount,
    agreedAmount: settleCase.agreedAmount,
    hqCreditAmount: creditAmount,
    hqCreditLineCount: creditLines.length,
    matchedCount: matched.length,
    openCount: open.length,
    claimRowCount: settleLines.some((l) => l.customerQty != null) ? 1 : 0,
    paidInSchema: false,
    settledWithoutClaims: false,
    agreedActor: 'Ken',
    lines: settleLines.map((l: SettleLine) => ({
      id: l.id,
      sku: l.sku,
      salesModel: null,
      product: l.product,
      distributor: l.distributor,
      estimateQty: l.estimateQty,
      cipQty: l.cipQty,
      customerQty: l.customerQty,
      supportUnit: l.supportUnit,
      corroboration: l.corroboration as Corroboration,
      corroborationReason: CORROBORATION_REASON[l.corroboration as Corroboration],
      includeInCredit: l.includeInCredit,
    })),
    evidence: settleEvidence.map((e) => ({
      id: e.id,
      title: e.title,
      secondary: `${e.kind} · ${e.uploadedAt} · ${e.by}`,
    })),
    canSettle: false,
    fxSettleAllowed: true,
    fxDeclared: true,
    roeSnapshot: 18.78,
    allowedNext: [],
  };
}

/**
 * Composition A — Ken’s next-action desk.
 * Lab mounts the same SettlementDesk as production so the two cannot drift.
 * Evaluated a second LifecycleRail (rejected — one rail already owns the job).
 */
export function SettlementDeskA() {
  return (
    <SettlementDesk
      view={toView()}
      testId="settlement-desk-a"
      formatMoney={(amount) => (amount == null ? '—' : fmtCurrency(amount, { compact: true }))}
    />
  );
}
