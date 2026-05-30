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
      { label: 'Forecasting', href: '/forecasts' },
    ],
  },
  {
    id: 'commercial-planning',
    label: 'Commercial Planning',
    items: [
      { label: 'Commercial Planner', href: '/commercial-planner' },
      { label: 'Line-up Planning', href: '/lineup' },
    ],
  },
  {
    id: 'master-data',
    label: 'Master Data',
    items: [
      { label: 'Products', href: '/admin/products' },
      { label: 'Customers', href: '/admin/customers' },
      { label: 'Distributors', href: '/admin/distributors' },
      { label: 'Channels & Regions', href: '/admin/channels-regions' },
    ],
  },
  {
    id: 'data-imports',
    label: 'Data Imports',
    items: [
      { label: 'Import Center', href: '/admin/imports' },
      { label: 'Shipment Evidence', href: '/admin/shipment-evidence' },
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

export function navHrefMatches(pathname: string, search: string, href: string): boolean {
  const qIdx = href.indexOf('?');
  if (qIdx >= 0) {
    const path = href.slice(0, qIdx);
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
