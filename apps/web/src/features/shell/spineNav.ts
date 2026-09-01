import type { UserRole } from '@cip/types';

/** Six job-container spine item (north-star IA). */
export type SpineContainer = {
  id: string;
  label: string;
  href: string;
  roles?: UserRole[];
  /** Route prefixes that activate this container in the spine. */
  routePrefixes: string[];
};

export type UtilityNavItem = {
  label: string;
  href: string;
  roles?: UserRole[];
};

const ALL: UserRole[] = ['admin', 'steward', 'planner', 'viewer'];
const STEWARD_PLUS: UserRole[] = ['admin', 'steward'];
const PLANNER_PLUS: UserRole[] = ['admin', 'planner'];
const ADMIN_ONLY: UserRole[] = ['admin'];

export const SPINE_DRAWER_WIDTH = 190;

export const spineContainers: SpineContainer[] = [
  {
    id: 'brief',
    label: 'Brief',
    href: '/brief',
    roles: ALL,
    routePrefixes: ['/brief', '/dashboard', '/exceptions', '/getting-started'],
  },
  {
    id: 'lineup',
    label: 'Lineup',
    href: '/lineup',
    roles: PLANNER_PLUS,
    routePrefixes: ['/lineup', '/buy-plans'],
  },
  {
    id: 'stock',
    label: 'Stock',
    href: '/stock',
    roles: ALL,
    routePrefixes: [
      '/stock',
      '/sell-out',
      '/plan-vs-executed',
      '/shipping',
      '/channel-intelligence',
      '/forecasts',
      '/inventory',
    ],
  },
  {
    id: 'settlement',
    label: 'Settlement',
    href: '/commercial-planner/cpor-cases',
    roles: PLANNER_PLUS,
    routePrefixes: ['/commercial-planner/cpor-cases', '/budgets', '/budget-requests'],
  },
  {
    id: 'response',
    label: 'Response',
    href: '/commercial-planner',
    roles: PLANNER_PLUS,
    routePrefixes: ['/commercial-planner', '/promotions', '/pricing', '/competition', '/roadmap'],
  },
  {
    id: 'steward',
    label: 'Steward',
    href: '/admin/imports',
    roles: STEWARD_PLUS,
    routePrefixes: [
      '/admin/imports',
      '/admin/shipment-evidence',
      '/admin/po-management',
      '/admin/products',
      '/admin/product-master-gaps',
      '/admin/customers',
      '/admin/distributors',
      '/admin/channels-regions',
      '/admin/cst-steward',
      '/listing-capture',
      '/admin/steward-audit',
      '/admin/ops',
    ],
  },
];

export const utilityNavItems: UtilityNavItem[] = [
  { label: 'Reports', href: '/reports', roles: ALL },
  { label: 'Admin', href: '/admin/users', roles: ADMIN_ONLY },
];

export function activeSpineContainerId(pathname: string): string | null {
  let best: { id: string; len: number } | null = null;
  for (const c of spineContainers) {
    for (const prefix of c.routePrefixes) {
      if (pathname === prefix || (prefix !== '/' && pathname.startsWith(`${prefix}/`))) {
        const len = prefix.length;
        if (!best || len > best.len) best = { id: c.id, len };
      }
    }
  }
  return best?.id ?? null;
}

export function filterSpineForRole<T extends { roles?: UserRole[] }>(
  items: T[],
  role: string | null | undefined,
): T[] {
  return items.filter((item) => roleMayAccess(role, item.roles));
}

export function roleMayAccess(role: string | null | undefined, allowed?: UserRole[]): boolean {
  if (!allowed || allowed.length === 0) return true;
  const r = (role || 'viewer').toLowerCase() as UserRole;
  if (r === 'admin') return true;
  return allowed.includes(r);
}

export function shellSpineContainers(role?: string | null): SpineContainer[] {
  let containers = spineContainers;
  if (process.env.NEXT_PUBLIC_CIP_COMMERCIAL_PLANNER_ENABLED === 'false') {
    containers = containers.filter((c) => !['lineup', 'settlement', 'response'].includes(c.id));
  }
  if (role == null || String(role).trim() === '') return containers;
  return filterSpineForRole(containers, role);
}

export function shellUtilityNav(role?: string | null): UtilityNavItem[] {
  if (role == null || String(role).trim() === '') return utilityNavItems;
  return filterSpineForRole(utilityNavItems, role);
}
