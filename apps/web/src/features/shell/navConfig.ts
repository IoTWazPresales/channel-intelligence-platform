import type { NavItem, UserRole } from '@cip/types';

/** Leaf link within a navigation group. */
export type NavLeaf = {
  label: string;
  href: string;
  /** If set, only these roles see the leaf. Admin always sees everything. */
  roles?: UserRole[];
};

/** Top-level sidebar group (order is product navigation IA). */
export type NavGroup = {
  id: string;
  label: string;
  items: NavLeaf[];
};

export const NAV_STORAGE_COLLAPSED = 'cip.shell.nav.collapsed.v1';
export const NAV_STORAGE_GROUP_EXPANDED = 'cip.shell.nav.groupExpanded.v1';

const ALL: UserRole[] = ['admin', 'steward', 'planner', 'viewer'];
const STEWARD_PLUS: UserRole[] = ['admin', 'steward'];
const PLANNER_PLUS: UserRole[] = ['admin', 'planner'];
const ADMIN_ONLY: UserRole[] = ['admin'];

/** Web feature flag — default on when unset. */
export function isCommercialPlannerEnabled(): boolean {
  return process.env.NEXT_PUBLIC_CIP_COMMERCIAL_PLANNER_ENABLED !== 'false';
}

export function roleMayAccess(role: string | null | undefined, allowed?: UserRole[]): boolean {
  if (!allowed || allowed.length === 0) return true;
  const r = (role || 'viewer').toLowerCase() as UserRole;
  if (r === 'admin') return true;
  return allowed.includes(r);
}

export function filterNavGroupsForRole(groups: NavGroup[], role: string | null | undefined): NavGroup[] {
  return groups
    .map((g) => ({
      ...g,
      items: g.items.filter((item) => roleMayAccess(role, item.roles)),
    }))
    .filter((g) => g.items.length > 0);
}

export function shellNavGroups(role?: string | null): NavGroup[] {
  let groups = navGroups;
  if (!isCommercialPlannerEnabled()) {
    groups = navGroups
      .map((g) =>
        g.id === 'commercial-planning'
          ? { ...g, items: g.items.filter((i) => i.href !== '/commercial-planner') }
          : g,
      )
      .filter((g) => g.items.length > 0);
  }
  // Until /me resolves, keep full nav (avoid empty flash). Gate once role is known.
  if (role == null || String(role).trim() === '') return groups;
  return filterNavGroupsForRole(groups, role);
}

export const navGroups: NavGroup[] = [
  {
    id: 'overview',
    label: 'Overview',
    items: [{ label: 'Dashboard', href: '/dashboard', roles: ALL }],
  },
  {
    id: 'channel-intelligence',
    label: 'Channel Intelligence',
    items: [
      { label: 'Channel Operations', href: '/sell-out', roles: ALL },
      { label: 'Sell-Through', href: '/sell-out', roles: ALL },
      { label: 'CST channel intelligence', href: '/channel-intelligence', roles: ALL },
      { label: 'Listing Capture', href: '/listing-capture', roles: ALL },
      { label: 'Inbound shipments', href: '/shipping', roles: ALL },
      { label: 'Forecasting', href: '/forecasts', roles: ALL },
    ],
  },
  {
    id: 'commercial-planning',
    label: 'Commercial Planning',
    items: [
      { label: 'Commercial Planner', href: '/commercial-planner', roles: PLANNER_PLUS },
      { label: 'CPOR Cases', href: '/commercial-planner/cpor-cases', roles: PLANNER_PLUS },
      { label: 'Line-up Planning', href: '/lineup', roles: PLANNER_PLUS },
      { label: 'Plan vs Executed', href: '/plan-vs-executed', roles: PLANNER_PLUS },
    ],
  },
  {
    id: 'master-data',
    label: 'Master Data',
    items: [
      { label: 'Products', href: '/admin/products', roles: STEWARD_PLUS },
      { label: 'Product catalogue gaps', href: '/admin/product-master-gaps', roles: STEWARD_PLUS },
      { label: 'Customers', href: '/admin/customers', roles: STEWARD_PLUS },
      {
        label: 'Alias-scope conflicts',
        href: '/admin/customers/duplicates?tab=alias_scope',
        roles: STEWARD_PLUS,
      },
      {
        label: 'Name-similarity duplicates',
        href: '/admin/customers/duplicates?tab=name_similarity',
        roles: STEWARD_PLUS,
      },
      { label: 'Distributors', href: '/admin/distributors', roles: STEWARD_PLUS },
      {
        label: 'Distributor name-similarity duplicates',
        href: '/admin/distributors/duplicates',
        roles: STEWARD_PLUS,
      },
      { label: 'Channels & Regions', href: '/admin/channels-regions', roles: STEWARD_PLUS },
      { label: 'CST steward', href: '/admin/cst-steward', roles: STEWARD_PLUS },
    ],
  },
  {
    id: 'data-imports',
    label: 'Data Imports',
    items: [
      { label: 'Import Center', href: '/admin/imports', roles: STEWARD_PLUS },
      { label: 'Shipment Evidence', href: '/admin/shipment-evidence', roles: STEWARD_PLUS },
      { label: 'PO Management', href: '/admin/po-management', roles: STEWARD_PLUS },
      {
        label: 'Customer Reports',
        href: '/admin/imports?template=customer_sell_through',
        roles: STEWARD_PLUS,
      },
    ],
  },
  {
    id: 'admin',
    label: 'Admin',
    items: [
      { label: 'Users', href: '/admin/users', roles: ADMIN_ONLY },
      { label: 'Settings', href: '/settings', roles: ADMIN_ONLY },
    ],
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
