import type { SettleReadiness } from '@/features/cpor/fxDisplay';

import { customerPrimaryName, customerSecondaryCode } from './customerDisplay';

export const SETTLE_STAGES = [
  'opened',
  'running',
  'ended',
  'reconciled',
  'customer_confirmed',
  'hq_credit',
  'paid',
] as const;

export type SettleStage = (typeof SETTLE_STAGES)[number];

export const SETTLE_STAGE_LABEL: Record<SettleStage, string> = {
  opened: 'Opened',
  running: 'Running',
  ended: 'Ended',
  reconciled: 'CIP reconciled',
  customer_confirmed: 'Both agree',
  hq_credit: 'HQ credit',
  paid: 'Paid',
};

export type Corroboration = 'match' | 'mismatch' | 'customer_only' | 'cip_only' | 'pending';

export const CORROBORATION_CHIP: Record<Corroboration, string> = {
  match: 'Match',
  mismatch: 'Mismatch',
  customer_only: 'Customer only',
  cip_only: 'CIP only',
  pending: 'Awaiting customer',
};

export const CORROBORATION_REASON: Record<Corroboration, string> = {
  match: 'Agrees with CIP',
  mismatch: 'Mismatch',
  customer_only: 'Customer only',
  cip_only: 'CIP only',
  pending: 'Awaiting customer',
};

export function corroborationTone(
  c: Corroboration,
): 'danger' | 'warning' | 'success' | 'info' | 'neutral' {
  if (c === 'match') return 'success';
  if (c === 'mismatch' || c === 'cip_only') return 'danger';
  if (c === 'pending') return 'warning';
  return 'neutral';
}

export type SettlementDeskLine = {
  id: string;
  sku: string;
  salesModel: string | null;
  product: string;
  distributor: string;
  estimateQty: number;
  cipQty: number | null;
  customerQty: number | null;
  supportUnit: number | null;
  corroboration: Corroboration;
  corroborationReason: string;
  includeInCredit: boolean;
};

export type SettlementDeskEvidence = {
  id: string;
  title: string;
  secondary: string;
};

export type SettlementDeskView = {
  caseId: number | string;
  caseCode: string;
  customerName: string;
  customerCode: string | null;
  programme: string;
  windowLabel: string;
  distributorName: string;
  currency: string;
  openedOn?: string | null;
  endedOn?: string | null;
  stage: SettleStage;
  status: string;
  cipAmount: number | null;
  customerAmount: number | null;
  agreedAmount: number | null;
  hqCreditAmount: number | null;
  hqCreditLineCount: number;
  matchedCount: number;
  openCount: number;
  claimRowCount: number;
  paidInSchema: false;
  settledWithoutClaims: boolean;
  agreedActor: string | null;
  lines: SettlementDeskLine[];
  evidence: SettlementDeskEvidence[];
  canSettle: boolean;
  fxSettleAllowed: boolean;
  fxDeclared: boolean;
  roeSnapshot: number | null;
  fxBasisLine?: string | null;
  allowedNext: string[];
  /** BACKLOG-138 — set when this case has been soft-superseded (pointer, not status). */
  supersededByCaseId?: number | null;
  /** N-0044 (BACKLOG-202) — FX anchor facts that only the retired CporCaseWorkspace showed. */
  approvedAmount?: number | null;
  approvedUsd?: number | null;
  fxMode?: string | null;
  fxBookedBy?: string | null;
  fxBookedAt?: string | null;
  fxProposedRate?: number | null;
  fxProposedSource?: string | null;
  needsReapproval?: boolean;
  intelligenceExclude?: boolean;
  settleReadiness?: SettleReadiness | null;
  /** Settlement diagnostics from GET …/settlement. Flags only — none of them blocks settle. */
  outOfWindowClaimRows?: number;
  unresolvedProducts?: { token: string; units: number }[];
  cstReconciliation?: { available: boolean; reason?: string; divergence_count?: number } | null;
};

export function stageFromCaseStatus(status: string, hasCip: boolean): SettleStage {
  if (status === 'active') return 'running';
  if (status === 'ended') return hasCip ? 'reconciled' : 'ended';
  if (status === 'settled') return 'customer_confirmed';
  return 'opened';
}

export function fmtInt(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '—';
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 }).format(value);
}

export function lineAmount(qty: number | null | undefined, supportUnit: number | null | undefined): number | null {
  if (qty == null || supportUnit == null) return null;
  return qty * supportUnit;
}

export function isCorroboration(raw: string | null | undefined): raw is Corroboration {
  return (
    raw === 'match' ||
    raw === 'mismatch' ||
    raw === 'customer_only' ||
    raw === 'cip_only' ||
    raw === 'pending'
  );
}

export function customerTitleBits(name: string | null | undefined, code: string | null | undefined) {
  return {
    name: customerPrimaryName(name, code),
    code: customerSecondaryCode(code),
  };
}
