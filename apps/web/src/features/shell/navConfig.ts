import type { NavItem } from '@cip/types';

/** Leaf link within a navigation group. */
export type NavLeaf = {
  label: string;
  href: string;
};

/** Top-level sidebar group (order is product navigation IA). */
export type NavGroup = {
  id: string;
  label: string;
  items: NavLeaf[];
};

export const NAV_STORAGE_COLLAPSED = 'cip.shell.nav.collapsed.v1';
export const NAV_STORAGE_GROUP_EXPANDED = 'cip.shell.nav.groupExpanded.v1';

/** Web feature flag — default on when unset. */
export function isCommercialPlannerEnabled(): boolean {
  return process.env.NEXT_PUBLIC_CIP_COMMERCIAL_PLANNER_ENABLED !== 'false';
}

export function shellNavGroups(): NavGroup[] {
  if (isCommercialPlannerEnabled()) return navGroups;
  return navGroups
    .map((g) =>
      g.id === 'commercial-planning'
        ? { ...g, items: g.items.filter((i) => i.href !== '/commercial-planner') }
        : g,
    )
    .filter((g) => g.items.length > 0);
}

export const navGroups: NavGroup[] = [
  {
    id: 'overview',
    label: 'Overview',
    items: [{ label: 'Dashboard', href: '/dashboard' }],
  },
  {
    id: 'channel-intelligence',
    label: 'Channel Intelligence',
    items: [
      { label: 'Channel Operations', href: '/sell-out' },
      { label: 'Sell-Through', href: '/sell-out' },
      { label: 'Inbound shipments', href: '/shipping' },
      { label: 'Forecasting', href: '/forecasts' },
    ],
  },
  {
    id: 'commercial-planning',
    label: 'Commercial Planning',
    items: [
      { label: 'Commercial Planner', href: '/commercial-planner' },
      { label: 'CPOR Cases', href: '/commercial-planner/cpor-cases' },
      { label: 'Line-up Planning', href: '/lineup' },
      { label: 'Plan vs Executed', href: '/plan-vs-executed' },
    ],
  },
  {
    id: 'master-data',
    label: 'Master Data',
    items: [
      { label: 'Products', href: '/admin/products' },
      { label: 'Product catalogue gaps', href: '/admin/product-master-gaps' },
      { label: 'Customers', href: '/admin/customers' },
      {
        label: 'Alias-scope conflicts',
        href: '/admin/customers/duplicates?tab=alias_scope',
      },
      {
        label: 'Name-similarity duplicates',
        href: '/admin/customers/duplicates?tab=name_similarity',
      },
      { label: 'Distributors', href: '/admin/distributors' },
      {
        label: 'Distributor name-similarity duplicates',
        href: '/admin/distributors/duplicates',
      },
      { label: 'Channels & Regions', href: '/admin/channels-regions' },
      { label: 'CST steward', href: '/admin/cst-steward' },
    ],
  },
  {
    id: 'data-imports',
    label: 'Data Imports',
    items: [
      { label: 'Import Center', href: '/admin/imports' },
      { label: 'Shipment Evidence', href: '/admin/shipment-evidence' },
      { label: 'PO Management', href: '/admin/po-management' },
      { label: 'Customer Reports', href: '/admin/imports?template=customer_sell_through' },
    ],
  },
  {
    id: 'admin',
    label: 'Admin',
    items: [{ label: 'Settings', href: '/settings' }],
  },
];

/** Flat list retained for legacy consumers/tests. */
export const navItems: NavItem[] = navGroups.flatMap((g) =>
  g.items.map((item) => ({ ...item, section: g.label }))
);

export function defaultGroupExpandedState(): Record<string, boolean> {
  const out: Record<string, boolean> = {};
  for (const g of navGroups) out[g.id] = true;
  return out;
}

function duplicatesTabFromSearch(search: string): string {
  const raw = search.startsWith('?') ? search.slice(1) : search;
  const tab = new URLSearchParams(raw).get('tab');
  if (tab === 'alias_scope' || tab === 'name_similarity') return tab;
  return 'name_similarity';
}

export function navHrefMatches(pathname: string, search: string, href: string): boolean {
  const qIdx = href.indexOf('?');
  const path = qIdx >= 0 ? href.slice(0, qIdx) : href;
  const hrefQuery = qIdx >= 0 ? href.slice(qIdx + 1) : '';

  if (path === '/admin/customers/duplicates') {
    if (pathname !== path) return false;
    const expectedTab = hrefQuery
      ? new URLSearchParams(hrefQuery).get('tab') || 'name_similarity'
      : 'name_similarity';
    return duplicatesTabFromSearch(search) === expectedTab;
  }

  if (qIdx >= 0) {
    const query = href.slice(qIdx);
    return pathname === path && search === query;
  }
  if (pathname === href) return true;
  if (href !== '/' && pathname.startsWith(`${href}/`)) return true;
  return false;
}

export function activeGroupId(pathname: string, search: string): string | null {
  for (const g of navGroups) {
    if (g.items.some((item) => navHrefMatches(pathname, search, item.href))) return g.id;
  }
  return null;
}
