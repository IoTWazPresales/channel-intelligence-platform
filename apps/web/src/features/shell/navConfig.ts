import type { NavItem, UserRole } from '@cip/types';

/**
 * Production information architecture — N-0013 r3/r3.1, accepted as D-0008 (2026-09-03).
 *
 * Primary navigation = capability domains derived from the data layer. A workflow lives in the
 * domain of its primary governed metric / entity. Leaves point at the REAL production route that
 * owns the capability today; a leaf's `status` is the honest four-state maturity vocabulary and is
 * never promoted because a capability appears in the North Star.
 *
 * Rail = `live` + `partial` (partial is marked). Capability directory = all four, labelled.
 */

/**
 * live      — end-to-end usable on real data.
 * partial   — real code path, but a required step is missing, manual or hard-coded (rail, marked).
 * substrate — tables / endpoints exist, no working user-facing view (directory only, "data only").
 * planned   — chartered, not built (directory only, labelled).
 */
export type LeafStatus = 'live' | 'partial' | 'substrate' | 'planned';

export const leafStatusLabel: Record<LeafStatus, string> = {
  live: 'Works today',
  partial: 'Partly built',
  substrate: 'Data only',
  planned: 'Planned',
};

/** Leaf link within a capability domain. */
export type NavLeaf = {
  label: string;
  href: string;
  /** One sentence: what this workflow computes or lets you do. Shown in directory + palette. */
  what?: string;
  /** If set, only these roles see the leaf. Admin always sees everything. */
  roles?: UserRole[];
  /** Defaults to 'live'. */
  status?: LeafStatus;
};

/** Top-level capability domain (order is product navigation IA). */
export type NavGroup = {
  id: string;
  label: string;
  /** Short label for narrow chrome (mobile bottom nav, crumbs). */
  short?: string;
  /** Domain home — where the rail heading and the domain crumb link to. */
  href?: string;
  /** Plain-language description of the domain, for the directory and palette. */
  what?: string;
  /** If set, only these roles see the domain at all. Leaves may narrow further. */
  roles?: UserRole[];
  items: NavLeaf[];
};

export const NAV_STORAGE_COLLAPSED = 'cip.shell.nav.collapsed.v1';
export const NAV_STORAGE_GROUP_EXPANDED = 'cip.shell.nav.groupExpanded.v2';

const ALL: UserRole[] = ['admin', 'steward', 'planner', 'viewer'];
const STEWARD_PLUS: UserRole[] = ['admin', 'steward'];
const PLANNER_PLUS: UserRole[] = ['admin', 'planner'];
const ADMIN_ONLY: UserRole[] = ['admin'];
const ADMIN_STEWARD: UserRole[] = ['admin', 'steward'];

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

export const leafStatus = (l: NavLeaf): LeafStatus => l.status ?? 'live';

/** Rail membership: live + partial. Substrate / planned are directory-only. */
export const inRail = (l: NavLeaf): boolean => {
  const s = leafStatus(l);
  return s === 'live' || s === 'partial';
};

export function filterNavGroupsForRole(groups: NavGroup[], role: string | null | undefined): NavGroup[] {
  return groups
    .filter((g) => roleMayAccess(role, g.roles))
    .map((g) => ({
      ...g,
      items: g.items.filter((item) => roleMayAccess(role, item.roles)),
    }))
    .filter((g) => g.items.length > 0);
}

/** Domains and leaves the current role may see — every status (directory / palette). */
export function shellNavGroups(role?: string | null): NavGroup[] {
  let groups = navGroups;
  if (!isCommercialPlannerEnabled()) {
    groups = navGroups
      .map((g) => ({ ...g, items: g.items.filter((i) => !i.href.startsWith('/commercial-planner') && i.href !== '/promotions') }))
      .filter((g) => g.items.length > 0);
  }
  // Until /me resolves, keep full nav (avoid empty flash). Gate once role is known.
  if (role == null || String(role).trim() === '') return groups;
  return filterNavGroupsForRole(groups, role);
}

/** Rail view of `shellNavGroups`: only live + partial leaves; domains with no rail leaf drop out. */
export function railNavGroups(role?: string | null): NavGroup[] {
  return shellNavGroups(role)
    .map((g) => ({ ...g, items: g.items.filter(inRail) }))
    .filter((g) => g.items.length > 0);
}

export const navGroups: NavGroup[] = [
  {
    id: 'overview',
    label: 'Overview',
    short: 'Overview',
    href: '/brief',
    what: 'What needs attention now, your configurable view of the business, and governed reports.',
    items: [
      {
        label: 'Attention',
        href: '/brief',
        roles: ALL,
        what: 'Live signals with counts and deep links: failed imports, cover breaches, blocked funding, stale stock.',
      },
      {
        label: 'Business dashboard',
        href: '/dashboards',
        roles: ALL,
        what: 'Configurable widgets over governed metrics; save and publish per role.',
      },
      {
        label: 'Reports',
        href: '/reports',
        roles: ALL,
        what: 'Governed report builder: metric, grain, dimensions; run, save, export, schedule.',
      },
      {
        label: 'Report inbox',
        href: '/inbox',
        roles: ALL,
        what: 'Delivered scheduled reports.',
      },
    ],
  },
  {
    id: 'stock',
    label: 'Stock & Sell-through',
    short: 'Stock',
    href: '/stock',
    what: 'Distributor and retailer stock, weeks of cover, sell-out velocity and execution against plan.',
    items: [
      { label: 'Cover', href: '/stock?lens=cover', roles: ALL, what: 'Derived SOH and weeks of cover per distributor × product; breaches and excess.' },
      { label: 'Movement', href: '/stock?lens=movement', roles: ALL, what: 'Weekly sell-out, shipments and stock trend by family and distributor.' },
      { label: 'Sell-through', href: '/channel-intelligence', roles: ALL, what: 'Retailer sell-through and customer inventory from retailer (CST) files.' },
      { label: 'Execution vs plan', href: '/stock?lens=execution', roles: ALL, what: 'Shipped against lineup plan per customer and period.' },
      { label: 'Forecasts', href: '/forecasts', roles: ALL, what: 'Demand forecast rows by method; velocity and analogue projections labelled by method.' },
    ],
  },
  {
    id: 'supply',
    label: 'Supply & Inbound',
    short: 'Supply',
    href: '/stock?lens=inbound',
    what: 'Inbound shipments through their lifecycle, receipt and proof-of-delivery evidence, PO coverage.',
    items: [
      { label: 'Shipments', href: '/stock?lens=inbound', roles: ALL, what: 'Shipment lifecycle: planned, shipped, arrived, received; ageing past ETA.' },
      {
        label: 'Receipts & POD',
        href: '/admin/shipment-evidence',
        roles: STEWARD_PLUS,
        status: 'partial',
        what: 'Inbound evidence import and steward resolution (POD rows to shipments). No per-shipment receipt view yet.',
      },
      { label: 'PO coverage', href: '/admin/po-management', roles: STEWARD_PLUS, what: 'Purchase orders, case links and auto-link proposals.' },
    ],
  },
  {
    id: 'planning',
    label: 'Planning',
    short: 'Planning',
    href: '/lineup',
    what: 'Lineup cases and plan lines per customer, readiness, line economics, PO reconciliation and rankings.',
    items: [
      { label: 'Lineup cases', href: '/lineup', roles: PLANNER_PLUS, what: 'Customer lineup per period: assortment, pending approval, net requirement.' },
      {
        label: 'Plans & line economics',
        href: '/commercial-planner',
        roles: PLANNER_PLUS,
        what: 'Commercial plans and lines: readiness, recalculated line economics with explanation and flags, PO reconciliation, rankings, planner defaults, data map.',
      },
      {
        label: 'Product roadmap',
        href: '/roadmap',
        roles: PLANNER_PLUS,
        status: 'substrate',
        what: 'Lifecycle phase and replacement candidates per product (fact_product_roadmap). Table and list exist; no writer or planning view.',
      },
    ],
  },
  {
    id: 'funding',
    label: 'Promotions & Funding',
    short: 'Promotions',
    href: '/commercial-planner/cpor-cases',
    what: 'One promotion case from plan to settlement: propose or author the plan, approve it, watch it run, claim and settle the support.',
    items: [
      {
        label: 'Promotion planner',
        href: '/promotions',
        roles: PLANNER_PLUS,
        status: 'partial',
        what: 'Propose or author a promotion plan (CPOR case) per customer and window: lines, waterfall economics, budget check. Needs a seed case id; no entity pickers yet.',
      },
      {
        label: 'Case book',
        href: '/commercial-planner/cpor-cases',
        roles: PLANNER_PLUS,
        what: 'Every promotion case across the lifecycle: draft → proposed → approved → active → ended → settled; claimed, settled, outstanding, blocked reasons.',
      },
      {
        label: 'Payments',
        href: '/commercial-planner/cpor-cases/payment-evidence-import',
        roles: PLANNER_PLUS,
        what: 'Payment / credit-note evidence import matched to cases; delivery rate (result ÷ estimate).',
      },
      {
        label: 'Plan templates',
        href: '/commercial-planner/cpor-cases/historical-import',
        roles: PLANNER_PLUS,
        status: 'partial',
        what: 'Customer promotion-plan workbooks mapped once to the canonical case model. Import-side profile works (historical plans); export-side profile not built.',
      },
      {
        label: 'Terms & assumptions',
        href: '/admin/customer-commercial-terms',
        roles: PLANNER_PLUS,
        what: 'Customer margin / rebate defaults and SKU assumptions feeding the waterfall.',
      },
      {
        label: 'Budget ledger',
        href: '/budgets',
        roles: PLANNER_PLUS,
        status: 'substrate',
        what: 'Allocation → commitment → actual (fact_budget_*). Tables and list exist with no rows; the planner uses the lineup-derived reservation instead.',
      },
    ],
  },
  {
    id: 'market',
    label: 'Market & Listings',
    short: 'Market',
    href: '/listing-capture',
    what: 'Evidence from the shelf: monitored retailer listings and prices, whether promotions are live at the planned price, and which competitor products sit against ours.',
    items: [
      { label: 'Monitored listings', href: '/listing-capture?tab=registry', roles: ALL, what: 'Registry of customer listing URLs per product with status; manual, CSV, feed proposals and auto-finder.' },
      { label: 'Price history', href: '/listing-capture?tab=observations', roles: ALL, what: 'Observed price and availability per listing over time, with the covering promotion price.' },
      { label: 'Promotion activation', href: '/listing-capture?tab=intelligence', roles: ALL, what: 'Each observation checked against the covering case-line SRP: live at price, not activated, or no promotion covering.' },
      { label: 'Feed proposals', href: '/listing-capture?tab=proposals', roles: ALL, what: 'Listing ids seen in retailer sell-through feeds, proposed for the registry; steward confirms.' },
      {
        label: 'Competitor mappings',
        href: '/competition?tab=mappings',
        roles: ALL,
        status: 'partial',
        what: 'Our SKU ↔ competitor SKU with score, explanation and approval. Workflow works; rows are seed-only and candidate scoring is not yet wired.',
      },
      {
        label: 'Competitor prices',
        href: '/competition?tab=prices',
        roles: ALL,
        status: 'substrate',
        what: 'Observed competitor prices (fact_competitor_price). Table and list exist; no import and no rows.',
      },
      { label: 'Competitor listings', href: '/competition', roles: ALL, status: 'planned', what: 'Monitor competitor product listings alongside ours (BACKLOG §9.9).' },
      { label: 'Listing quality / SEO', href: '/listing-capture', roles: ALL, status: 'planned', what: 'Content, specification and search-quality checks on listings (roadmap P5).' },
    ],
  },
  {
    id: 'data',
    label: 'Data & Stewardship',
    short: 'Data',
    href: '/admin/imports',
    what: 'Bring files in, resolve unknown names to master records, and keep master data trustworthy.',
    items: [
      { label: 'Import Center', href: '/admin/imports', roles: STEWARD_PLUS, what: 'Every import type on one guided pipeline; job history and progress.' },
      {
        label: 'Customer sell-through files',
        href: '/admin/imports?template=customer_sell_through',
        roles: STEWARD_PLUS,
        what: 'Retailer (CST) report import — same pipeline, template preselected.',
      },
      {
        label: 'Steward queue',
        href: '/admin/mappings',
        roles: STEWARD_PLUS,
        what: 'Cross-job manual mapping queue for tokens awaiting resolution (legacy queue; disposition deferred, D-0002).',
      },
      { label: 'Products', href: '/admin/products', roles: STEWARD_PLUS, what: 'Product master: records, SKU economics, provisional enrichment.' },
      { label: 'Product catalogue gaps', href: '/admin/product-master-gaps', roles: STEWARD_PLUS, what: 'Unmatched product tokens from imports awaiting catalogue decisions.' },
      { label: 'Customers', href: '/admin/customers', roles: STEWARD_PLUS, what: 'Customer / dealer master with groups, strategic flags and commercial terms.' },
      { label: 'Customer duplicates', href: '/admin/customers/duplicates?tab=name_similarity', roles: STEWARD_PLUS, what: 'Name-similarity duplicates and alias-scope conflicts to merge or dismiss.' },
      { label: 'Distributors', href: '/admin/distributors', roles: STEWARD_PLUS, what: 'Distributor master with commercial terms.' },
      { label: 'Distributor duplicates', href: '/admin/distributors/duplicates', roles: STEWARD_PLUS, what: 'Distributor name-similarity duplicates to merge or dismiss.' },
      { label: 'Channels & regions', href: '/admin/channels-regions', roles: STEWARD_PLUS, what: 'Channel and region dimensions.' },
      { label: 'CST steward', href: '/admin/cst-steward', roles: STEWARD_PLUS, what: 'Retailer sell-through token resolution.' },
      { label: 'Steward audit', href: '/admin/steward-audit', roles: ADMIN_STEWARD, what: 'Who mapped what, when, with which evidence.' },
    ],
  },
  {
    id: 'admin',
    label: 'Administration',
    short: 'Admin',
    href: '/admin/users',
    what: 'Users and roles, background operations, audited SQL access, settings.',
    items: [
      { label: 'Users & roles', href: '/admin/users', roles: ADMIN_ONLY, what: 'admin · steward · planner · viewer.' },
      { label: 'Operations', href: '/admin/ops', roles: ADMIN_STEWARD, what: 'Background jobs, retries, activity feed, monitoring.' },
      { label: 'SQL viewer', href: '/admin/sql-viewer', roles: ADMIN_ONLY, what: 'Read-only, audited SQL.' },
      { label: 'Settings', href: '/settings', roles: ADMIN_ONLY, what: 'Tenant, semantic catalog overlay, mailer.' },
      { label: 'Audit log', href: '/admin/steward-audit', roles: ADMIN_ONLY, status: 'planned', what: 'Platform-wide audit trail beyond steward actions.' },
    ],
  },
];

/** Flat list retained for legacy consumers/tests. */
export const navItems: NavItem[] = navGroups.flatMap((g) =>
  g.items.map((item) => ({ label: item.label, href: item.href, roles: item.roles, section: g.label }))
);

export function defaultGroupExpandedState(): Record<string, boolean> {
  const out: Record<string, boolean> = {};
  for (const g of navGroups) out[g.id] = false;
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
