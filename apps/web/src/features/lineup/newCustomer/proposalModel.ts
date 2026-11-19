import type { ApproveBody, Proposal, ProposalLine, SeedSource } from './types';

export const SOURCE_OPTIONS: { value: SeedSource; label: string; explanation: string }[] = [
  {
    value: 'pm_bottom_cost',
    label: 'Master-catalogue items with a PM bottom cost',
    explanation:
      'Every active catalogue item that has a PM bottom cost recorded. Each line shows that cost as its evidence.',
  },
  {
    value: 'previous_lineups',
    label: 'SKUs from the previous line-ups',
    explanation:
      "The distinct SKUs from this customer's own 3 most recent line-up periods. If the customer has no line-ups of its own, the master line-up's 3 most recent periods (all customers) are used instead. Superseded and cancelled line-ups are ignored.",
  },
];

/** "2026-10-01" -> "2026 Q4". */
export function quarterLabel(iso: string): string {
  const [year, month] = iso.split('-').map(Number);
  return `${year} Q${Math.floor((month - 1) / 3) + 1}`;
}

function formatCost(value: number): string {
  return value.toLocaleString('en-US', { maximumFractionDigits: 4 });
}

export function evidenceText(line: ProposalLine): string {
  const e = line.evidence;
  if (e.kind === 'pm_bottom_cost') {
    return `PM bottom cost ${formatCost(e.pm_bottom_cost)}${e.currency ? ` ${e.currency}` : ''}`;
  }
  return `In line-ups: ${e.periods.map(quarterLabel).join(', ')}`;
}

/** One line stating which history was used and the periods, shown above the proposed lines. */
export function basisHeadline(p: Proposal): string {
  if (p.source === 'pm_bottom_cost') return 'Master-catalogue items with a PM bottom cost';
  const who = p.fallback === 'customer_own' ? "This customer's own line-ups" : 'Master line-up, all customers';
  const periods = p.periods_used.length ? p.periods_used.map(quarterLabel).join(', ') : 'no line-up periods found';
  return `${who}: ${periods}`;
}

export function allProductIds(p: Proposal): Set<number> {
  return new Set(p.lines.map((l) => l.product_id));
}

export function toggleProduct(selected: Set<number>, productId: number): Set<number> {
  const next = new Set(selected);
  if (next.has(productId)) next.delete(productId);
  else next.add(productId);
  return next;
}

export function approveBody(source: SeedSource, periodStart: string, selected: Set<number>): ApproveBody {
  return { source, period_start: periodStart, product_ids: [...selected].sort((a, b) => a - b) };
}

export function proposalPath(customerId: number, source: SeedSource, periodStart: string): string {
  const q = new URLSearchParams({ source, period_start: periodStart });
  return `/api/v1/lineup/new-customer/${customerId}/proposal?${q.toString()}`;
}

export const REPORTING_CUSTOMERS_PATH = '/api/v1/lineup/new-customer/reporting-customers';

export function approvePath(customerId: number): string {
  return `/api/v1/lineup/new-customer/${customerId}/approve`;
}
