export type LineupApprovalFilter = 'all' | 'pending';

export type LineupScope = {
  approval: LineupApprovalFilter;
  periodLabel: string;
  assortmentLabel: string;
};

export const DEFAULT_LINEUP_SCOPE: LineupScope = {
  approval: 'all',
  periodLabel: 'Q1+Q2',
  assortmentLabel: '26Q3 assortment',
};

export function parseLineupApprovalFilter(raw: string | null | undefined): LineupApprovalFilter {
  return raw === 'pending' ? 'pending' : 'all';
}

export function lineupTaskSubtitle(scope: LineupScope): string {
  if (scope.approval === 'pending') return 'Pending approval';
  return scope.assortmentLabel;
}
