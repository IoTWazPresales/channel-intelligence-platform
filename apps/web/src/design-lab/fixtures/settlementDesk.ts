/**
 * Design-lab fixture for BACKLOG-191 settlement desk compositions.
 * Fictional case. Not read from or written to the API.
 *
 * Lifecycle verified against schema 2026-09-18: cpor_case.status has
 * draft/proposed/approved/rejected/active/ended/settled/cancelled.
 * There is no paid/closed status today — `paid` here is a proposed stage.
 */
import { customers, distributors, products } from './entities';

export const settleStages = [
  'opened',
  'running',
  'ended',
  'reconciled',
  'customer_confirmed',
  'hq_credit',
  'paid',
] as const;

export type SettleStage = (typeof settleStages)[number];

export const settleStageLabel: Record<SettleStage, string> = {
  opened: 'Opened',
  running: 'Running',
  ended: 'Ended',
  reconciled: 'CIP reconciled',
  customer_confirmed: 'Both agree',
  hq_credit: 'HQ credit',
  paid: 'Paid',
};

export type Corroboration = 'match' | 'mismatch' | 'customer_only' | 'cip_only' | 'pending';

export type SettleLine = {
  id: string;
  sku: string;
  product: string;
  distributor: string;
  estimateQty: number;
  cipQty: number;
  customerQty: number | null;
  supportUnit: number;
  corroboration: Corroboration;
  includeInCredit: boolean;
};

export type SettleEvidence = {
  id: string;
  kind: 'cip_recon' | 'customer_report' | 'credit_pack' | 'payment';
  title: string;
  uploadedAt: string;
  by: string;
};

export const settleCase = {
  id: 'CPR-26-1184',
  customer: customers[0].name,
  customerCode: customers[0].code,
  programme: 'Sell-out PP Q2',
  window: '2026-04-01 → 2026-06-30',
  distributor: distributors[0].name,
  distributorCode: distributors[0].code,
  currency: 'ZAR',
  stage: 'customer_confirmed' as SettleStage,
  openedOn: '2026-03-28',
  endedOn: '2026-06-30',
  cipAmount: 412_400,
  customerAmount: 398_150,
  agreedAmount: 398_150,
  paidAmount: 0,
  note: 'Paid is a proposed stage. cpor_case has ended and settled today — no paid/closed column.',
};

export const settleLines: SettleLine[] = [
  {
    id: 'L-1',
    sku: products[3].sku,
    product: products[3].name,
    distributor: distributors[0].name,
    estimateQty: 120,
    cipQty: 118,
    customerQty: 118,
    supportUnit: 850,
    corroboration: 'match',
    includeInCredit: true,
  },
  {
    id: 'L-2',
    sku: products[4].sku,
    product: products[4].name,
    distributor: distributors[0].name,
    estimateQty: 80,
    cipQty: 74,
    customerQty: 68,
    supportUnit: 1_200,
    corroboration: 'mismatch',
    includeInCredit: false,
  },
  {
    id: 'L-3',
    sku: products[5].sku,
    product: products[5].name,
    distributor: distributors[0].name,
    estimateQty: 200,
    cipQty: 196,
    customerQty: 196,
    supportUnit: 420,
    corroboration: 'match',
    includeInCredit: true,
  },
  {
    id: 'L-4',
    sku: products[6].sku,
    product: products[6].name,
    distributor: distributors[2].name,
    estimateQty: 40,
    cipQty: 40,
    customerQty: null,
    supportUnit: 310,
    corroboration: 'pending',
    includeInCredit: false,
  },
  {
    id: 'L-5',
    sku: products[7].sku,
    product: products[7].name,
    distributor: distributors[0].name,
    estimateQty: 0,
    cipQty: 12,
    customerQty: 0,
    corroboration: 'cip_only',
    supportUnit: 180,
    includeInCredit: false,
  },
];

export const settleEvidence: SettleEvidence[] = [
  {
    id: 'E-1',
    kind: 'cip_recon',
    title: 'CIP auto-recon vs sell-out (week-aligned)',
    uploadedAt: '2026-07-02',
    by: 'system',
  },
  {
    id: 'E-2',
    kind: 'customer_report',
    title: 'TechMart confirmation workbook Q2',
    uploadedAt: '2026-07-11',
    by: 'Ken',
  },
];

export const corroborationLabel: Record<Corroboration, string> = {
  match: 'Match',
  mismatch: 'Mismatch',
  customer_only: 'Customer only',
  cip_only: 'CIP only',
  pending: 'Awaiting customer',
};

export function lineAmount(qty: number, supportUnit: number): number {
  return qty * supportUnit;
}
