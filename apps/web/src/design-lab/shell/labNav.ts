/**
 * Design-lab information architecture (N-0013 r3 + commercial amendment — see
 * .eif/audit/NS_REDESIGN_R3_20260902/DIRECTION.md and commercial/COMMERCIAL_DIRECTION.md).
 * Domains are derived from the capability audit; placement rule: a workflow lives in the domain of its
 * primary governed metric / entity.
 *
 * Leaf `status` is the honest four-state vocabulary (CONSULT Q4). Rail shows `live` + `partial`
 * (partial is marked); the capability directory shows all four, each labelled. Nothing unbuilt is
 * presented as working. The r3 binary "computes nothing → hidden" rule is withdrawn: stored
 * observations, mappings and planning workflows are first-class capabilities before derived analytics.
 */
import type { SvgIconComponent } from '@mui/icons-material';
import AccountBalanceOutlinedIcon from '@mui/icons-material/AccountBalanceOutlined';
import AdminPanelSettingsOutlinedIcon from '@mui/icons-material/AdminPanelSettingsOutlined';
import DashboardOutlinedIcon from '@mui/icons-material/DashboardOutlined';
import EventNoteOutlinedIcon from '@mui/icons-material/EventNoteOutlined';
import Inventory2OutlinedIcon from '@mui/icons-material/Inventory2Outlined';
import LocalShippingOutlinedIcon from '@mui/icons-material/LocalShippingOutlined';
import StorefrontOutlinedIcon from '@mui/icons-material/StorefrontOutlined';
import StorageOutlinedIcon from '@mui/icons-material/StorageOutlined';

export type Role = 'admin' | 'steward' | 'planner' | 'viewer';

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

export type LabLeaf = {
  label: string;
  href: string;
  /** One sentence: what this workflow computes or lets you do. Shown in directory + palette. */
  what: string;
  roles?: Role[];
  /** Defaults to 'live'. */
  status?: LeafStatus;
};

export const inRail = (l: LabLeaf) => (l.status ?? 'live') === 'live' || l.status === 'partial';

export type LabDomain = {
  id: string;
  label: string;
  short: string;
  href: string;
  icon: SvgIconComponent;
  /** Plain-language description of the domain, for the directory and domain overview. */
  what: string;
  leaves: LabLeaf[];
  roles?: Role[];
};

export const labDomains: LabDomain[] = [
  {
    id: 'overview',
    label: 'Overview',
    short: 'Overview',
    href: '/design-lab',
    icon: DashboardOutlinedIcon,
    what: 'Your configurable view of the business, what needs attention now, and governed reports.',
    leaves: [
      { label: 'Business dashboard', href: '/design-lab', what: 'Configurable widgets over ~30 governed metrics; publish per role.' },
      { label: 'Attention', href: '/design-lab?zone=attention', what: 'Live signals with counts and deep links: failed imports, cover breaches, blocked funding, stale stock.' },
      { label: 'Reports', href: '/design-lab/reports', what: 'Governed report builder: metric, grain, dimensions; run, save, export, schedule; pin to dashboard.' },
    ],
  },
  {
    id: 'stock',
    label: 'Stock & Sell-through',
    short: 'Stock',
    href: '/design-lab/stock',
    icon: Inventory2OutlinedIcon,
    what: 'Distributor and retailer stock, weeks of cover, sell-out velocity and execution against plan.',
    leaves: [
      { label: 'Cover', href: '/design-lab/stock?lens=cover', what: 'Derived SOH and weeks of cover per distributor × product; breaches and excess.' },
      { label: 'Movement', href: '/design-lab/stock?lens=movement', what: 'Weekly sell-out, shipments and stock trend by family and distributor.' },
      { label: 'Sell-through', href: '/design-lab/stock?lens=sellthrough', what: 'Retailer sell-through and customer inventory from retailer files.' },
      { label: 'Execution vs plan', href: '/design-lab/stock?lens=execution', what: 'Shipped against lineup plan per customer and period.' },
      { label: 'Forecasts', href: '/design-lab/stock?lens=forecast', what: 'Velocity and analogue projections, labelled by method.' },
    ],
  },
  {
    id: 'supply',
    label: 'Supply & Inbound',
    short: 'Supply',
    href: '/design-lab/supply',
    icon: LocalShippingOutlinedIcon,
    what: 'Inbound shipments through their lifecycle, receipts and proof of delivery, PO coverage.',
    leaves: [
      { label: 'Shipments', href: '/design-lab/supply?lens=shipments', what: 'Shipment lifecycle: planned, shipped, arrived, received; ageing past ETA.' },
      { label: 'Receipts & POD', href: '/design-lab/supply?lens=receipts', what: 'Receipt evidence and proof-of-delivery status per shipment.' },
      { label: 'PO coverage', href: '/design-lab/supply?lens=po', what: 'Purchase-order coverage and backlog per distributor.' },
    ],
  },
  {
    id: 'planning',
    label: 'Planning',
    short: 'Planning',
    href: '/design-lab/planning',
    icon: EventNoteOutlinedIcon,
    what: 'Lineup cases and plan lines per customer, readiness, line economics and PO reconciliation.',
    leaves: [
      { label: 'Lineup cases', href: '/design-lab/planning?lens=cases', what: 'Customer lineup cases per period with plan lines and status.' },
      { label: 'Readiness', href: '/design-lab/planning?lens=readiness', what: 'Missing SKU assumptions, terms and cost basis before commit.' },
      { label: 'Line economics', href: '/design-lab/planning?lens=economics', what: 'Recalculated line economics with explanation and flags per line.' },
      { label: 'PO reconciliation', href: '/design-lab/planning?lens=po', what: 'Plan lines matched to purchase orders; auto-link results.' },
      { label: 'Rankings', href: '/design-lab/planning?lens=rankings', what: 'Product rankings within a customer lineup.' },
      { label: 'Product roadmap', href: '/design-lab/planning?lens=roadmap', what: 'Lifecycle phase and replacement candidates per product (fact_product_roadmap). Table exists; no writer or view yet.', status: 'substrate' },
    ],
  },
  {
    id: 'funding',
    label: 'Promotions & Funding',
    short: 'Promotions',
    href: '/design-lab/funding',
    icon: AccountBalanceOutlinedIcon,
    what: 'One promotion case from plan to settlement: propose or author the plan, approve it, watch it run, claim and settle the support.',
    leaves: [
      { label: 'Promotion planner', href: '/design-lab/funding?lens=planner', what: 'Propose or author a promotion plan per customer and window: lines, waterfall economics, evidence, budget check, export in the customer’s format.', status: 'partial' },
      { label: 'Case book', href: '/design-lab/funding', what: 'Every promotion case across the lifecycle: draft → proposed → approved → live → ended → settled; claimed, settled, outstanding, blocked reasons, ageing.' },
      { label: 'Claims evidence', href: '/design-lab/funding?lens=claims', what: 'Imported claim evidence matched to case lines; out-of-window rows flagged.' },
      { label: 'Payments', href: '/design-lab/funding?lens=payments', what: 'Payment evidence and delivery rate (result ÷ estimate).' },
      { label: 'Plan templates', href: '/design-lab/funding?lens=templates', what: 'Customer promotion-plan workbook layouts mapped once to the canonical case model; used to read historical plans and to export new ones.', status: 'partial' },
      { label: 'Terms & assumptions', href: '/design-lab/funding?lens=pricing', what: 'Customer margin / rebate defaults and SKU assumptions feeding the waterfall.' },
      { label: 'Budget ledger', href: '/design-lab/funding?lens=budgets', what: 'Allocation → commitment → actual (fact_budget_*). Tables exist with no rows; the planner uses the lineup-derived reservation instead.', status: 'substrate' },
    ],
  },
  {
    id: 'market',
    label: 'Market & Listings',
    short: 'Market',
    href: '/design-lab/market',
    icon: StorefrontOutlinedIcon,
    what: 'Evidence from the shelf: monitored retailer listings and prices, whether promotions are live at the planned price, and which competitor products sit against ours. Reused by planning, promotions, dashboards and attention.',
    leaves: [
      { label: 'Monitored listings', href: '/design-lab/market', what: 'Registry of customer listing URLs per product with status history; manual, CSV, feed proposals and auto-finder.' },
      { label: 'Price history', href: '/design-lab/market?lens=history', what: 'Observed price and availability per listing over time, with the covering promotion price overlaid.' },
      { label: 'Promotion activation', href: '/design-lab/market?lens=activation', what: 'Each observation checked against the covering case line SRP: live at price, not activated, or no promotion covering.' },
      { label: 'Feed proposals', href: '/design-lab/market?lens=proposals', what: 'Listing ids seen in retailer sell-through feeds, proposed for the registry; steward confirms.' },
      { label: 'Competitor mappings', href: '/design-lab/market?lens=competition', what: 'Our SKU ↔ competitor SKU with score, factor breakdown and approval. Workflow works; rows are seed-only and candidate scoring is not yet wired.', status: 'partial' },
      { label: 'Competitor prices', href: '/design-lab/market?lens=competitor-prices', what: 'Observed competitor prices (fact_competitor_price). Table and list exist; no import and no rows.', status: 'substrate' },
      { label: 'Competitor listings', href: '/design-lab/market?lens=competitor-listings', what: 'Monitor competitor product listings alongside ours (BACKLOG §9.9).', status: 'planned' },
      { label: 'Listing quality / SEO', href: '/design-lab/market?lens=quality', what: 'Content, specification and search-quality checks on listings (roadmap P5).', status: 'planned' },
    ],
  },
  {
    id: 'data',
    label: 'Data & Stewardship',
    short: 'Data',
    href: '/design-lab/data',
    icon: StorageOutlinedIcon,
    what: 'Bring files in, resolve unknown names to master records, and keep master data trustworthy.',
    leaves: [
      { label: 'Import Center', href: '/design-lab/data?tab=imports', what: '19 import types on one guided pipeline; job history and progress.', roles: ['admin', 'steward', 'planner'] },
      { label: 'Steward queue', href: '/design-lab/data?tab=steward', what: 'Cross-job tokens awaiting resolution to products, customers, distributors.', roles: ['admin', 'steward'] },
      { label: 'Products', href: '/design-lab/data?tab=masters&m=products', what: 'Product master: 18k records, duplicates, provisional enrichment.' },
      { label: 'Customers', href: '/design-lab/data?tab=masters&m=customers', what: 'Customer / dealer master with groups, strategic flags and terms.' },
      { label: 'Distributors', href: '/design-lab/data?tab=masters&m=distributors', what: 'Distributor master with commercial terms.' },
      { label: 'Steward audit', href: '/design-lab/data?tab=audit', what: 'Who mapped what, when, with which evidence.', roles: ['admin', 'steward'] },
    ],
  },
  {
    id: 'admin',
    label: 'Administration',
    short: 'Admin',
    href: '/design-lab/admin',
    icon: AdminPanelSettingsOutlinedIcon,
    what: 'Users and roles, background operations, audited SQL access, settings.',
    roles: ['admin'],
    leaves: [
      { label: 'Users & roles', href: '/design-lab/admin?tab=users', what: 'admin · steward · planner · viewer.' },
      { label: 'Operations', href: '/design-lab/admin?tab=ops', what: 'Background jobs, retries, activity feed.' },
      { label: 'SQL viewer', href: '/design-lab/admin?tab=sql', what: 'Read-only, audited SQL.' },
      { label: 'Audit log', href: '/design-lab/admin?tab=audit', what: 'Platform audit trail.' },
      { label: 'Settings', href: '/design-lab/admin?tab=settings', what: 'Tenant, period, environment.' },
    ],
  },
];

export function domainForPath(pathname: string): LabDomain | undefined {
  if (pathname === '/design-lab' || pathname === '/design-lab/reports') return labDomains[0];
  return labDomains.find((d) => d.href !== '/design-lab' && pathname.startsWith(d.href));
}

export function visibleDomains(role: Role): LabDomain[] {
  return labDomains.filter((d) => !d.roles || d.roles.includes(role));
}

export function visibleLeaves(domain: LabDomain, role: Role): LabLeaf[] {
  return domain.leaves.filter((l) => inRail(l) && (!l.roles || l.roles.includes(role)));
}
