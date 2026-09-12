export const OVERVIEW_TITLE = 'Overview';

export const OVERVIEW_DESCRIPTION =
  'Your configurable view of the business, what needs attention now, and governed reports.';

export type OverviewLeaf = 'hub' | 'dashboard' | 'reports' | 'inbox';

export const OVERVIEW_LEAVES: { value: OverviewLeaf; label: string; href: string }[] = [
  { value: 'hub', label: 'Overview', href: '/brief' },
  { value: 'dashboard', label: 'Business dashboard', href: '/dashboards' },
  { value: 'reports', label: 'Reports', href: '/reports' },
  { value: 'inbox', label: 'Report inbox', href: '/inbox' },
];

export function overviewLeafFromPath(pathname: string): OverviewLeaf {
  if (pathname.startsWith('/dashboards')) return 'dashboard';
  if (pathname.startsWith('/reports')) return 'reports';
  if (pathname.startsWith('/inbox')) return 'inbox';
  return 'hub';
}

/** DIRECTION §6 Attention triage: attention column first on narrow viewports when ?zone=attention. */
export function overviewAttentionFirst(isMobile: boolean, zone: string | null | undefined): boolean {
  return Boolean(isMobile && zone === 'attention');
}
