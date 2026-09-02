export type SettlementStateFilter = '' | 'open' | 'active' | 'ended' | 'approved' | 'settled' | 'blocked';

export type SettlementSavedView = 'desk' | 'all' | 'blocked';

export type SettlementScope = {
  state: SettlementStateFilter;
  savedView: SettlementSavedView;
  periodLabel: string;
};

export const DEFAULT_SETTLEMENT_SCOPE: SettlementScope = {
  state: 'open',
  savedView: 'desk',
  periodLabel: '26Q3',
};

export function parseSettlementStateFilter(raw: string | null | undefined): SettlementStateFilter {
  const allowed: SettlementStateFilter[] = ['', 'open', 'active', 'ended', 'approved', 'settled', 'blocked'];
  return allowed.includes(raw as SettlementStateFilter) ? (raw as SettlementStateFilter) : 'open';
}

export function parseSettlementSavedView(raw: string | null | undefined): SettlementSavedView {
  return raw === 'all' || raw === 'blocked' ? raw : 'desk';
}

/** Map scope state to API list `status` query param(s). */
export function settlementStateToStatusParam(state: SettlementStateFilter): string {
  switch (state) {
    case 'active':
      return 'active';
    case 'ended':
      return 'ended';
    case 'approved':
      return 'approved';
    case 'settled':
      return 'settled';
    case 'open':
      return 'active,ended,approved,proposed';
    case 'blocked':
      return '';
    default:
      return '';
  }
}

export function settlementScopeLabel(scope: SettlementScope, openCount?: number): string {
  if (scope.state === 'blocked') return 'FX blocked';
  if (scope.state === 'settled') return 'Settled';
  if (scope.state === 'open' && openCount != null) return `Open · ${openCount}`;
  if (scope.state === 'open') return 'Open';
  return scope.state || 'All';
}
