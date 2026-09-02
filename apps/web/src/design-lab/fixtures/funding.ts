import { customers, products } from './entities';

export type CaseStatus = 'open' | 'evidence_pending' | 'blocked' | 'approved' | 'settled';

export type FundingCase = {
  id: string;
  customerId: number;
  customer: string;
  programme: string;
  period: string;
  sku: string;
  product: string;
  units: number;
  claimed: number;
  settled: number;
  outstanding: number;
  status: CaseStatus;
  blockedReason?: string;
  ageDays: number;
  supportPerUnit: number;
  evidence: { claim: boolean; payment: boolean; sellThrough: boolean };
};

const programmes = ['Price protection Q3', 'Sell-out rebate W30–W36', 'Display allowance P09', 'Launch support NBP16'];
const blockers = [
  'Sell-through evidence missing for W34',
  'Claimed units exceed shipped units by 120',
  'Payment evidence references different period',
  'Customer token unresolved: "METRO ELEC (PTA)"',
];

function seeded(seed: number) {
  let s = seed;
  return () => {
    s = (s * 9301 + 49297) % 233280;
    return s / 233280;
  };
}
const r = seeded(9090);

export const fundingCases: FundingCase[] = Array.from({ length: 26 }, (_, i) => {
  const c = customers[i % (customers.length - 1)];
  const p = products[(i * 3) % products.length];
  const units = 40 + Math.round(r() * 900);
  const perUnit = 45 + Math.round(r() * 140);
  const claimed = units * perUnit;
  const statuses: CaseStatus[] = ['open', 'evidence_pending', 'blocked', 'approved', 'settled', 'blocked', 'open', 'settled'];
  const status = statuses[i % statuses.length];
  const settled = status === 'settled' ? claimed : status === 'approved' ? Math.round(claimed * 0.5) : 0;
  return {
    id: `CPR-26-${(1180 + i).toString()}`,
    customerId: c.id,
    customer: c.name,
    programme: programmes[i % programmes.length],
    period: i % 2 ? 'FY26 P08' : 'FY26 P09',
    sku: p.sku,
    product: p.name,
    units,
    claimed,
    settled,
    outstanding: claimed - settled,
    status,
    blockedReason: status === 'blocked' ? blockers[i % blockers.length] : undefined,
    ageDays: 3 + Math.round(r() * 80),
    supportPerUnit: perUnit,
    evidence: {
      claim: status !== 'evidence_pending',
      payment: status === 'settled' || status === 'approved',
      sellThrough: !(status === 'blocked' && i % 4 === 0),
    },
  };
});

export const fundingBook = (() => {
  const book = fundingCases.reduce((a, c) => a + c.claimed, 0);
  const settled = fundingCases.reduce((a, c) => a + c.settled, 0);
  const outstanding = book - settled;
  const blocked = fundingCases.filter((c) => c.status === 'blocked');
  const blockedValue = blocked.reduce((a, c) => a + c.outstanding, 0);
  const settledCount = fundingCases.filter((c) => c.status === 'settled').length;
  return {
    cases: fundingCases.length,
    book,
    settled,
    outstanding,
    blocked: blocked.length,
    blockedValue,
    deliveryRate: settledCount / fundingCases.length,
    awaitingApproval: fundingCases.filter((c) => c.status === 'open').length,
  };
})();

export const ageingBuckets = [
  { bucket: '0–14d', value: fundingCases.filter((c) => c.ageDays <= 14 && c.status !== 'settled').reduce((a, c) => a + c.outstanding, 0) },
  { bucket: '15–30d', value: fundingCases.filter((c) => c.ageDays > 14 && c.ageDays <= 30 && c.status !== 'settled').reduce((a, c) => a + c.outstanding, 0) },
  { bucket: '31–60d', value: fundingCases.filter((c) => c.ageDays > 30 && c.ageDays <= 60 && c.status !== 'settled').reduce((a, c) => a + c.outstanding, 0) },
  { bucket: '60d+', value: fundingCases.filter((c) => c.ageDays > 60 && c.status !== 'settled').reduce((a, c) => a + c.outstanding, 0) },
];

export const statusLabel: Record<CaseStatus, string> = {
  open: 'Awaiting approval',
  evidence_pending: 'Evidence pending',
  blocked: 'Blocked',
  approved: 'Approved',
  settled: 'Settled',
};
