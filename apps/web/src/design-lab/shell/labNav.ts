/**
 * Design-lab information architecture (N-0013 r3, hybrid "H" — see
 * .eif/audit/NS_REDESIGN_R3_20260902/DIRECTION.md). Domains are derived from the capability audit;
 * placement rule: a workflow lives in the domain of its primary governed metric / entity.
 *
 * `populated: false` marks leaves whose route exists in production but whose data layer computes
 * nothing yet (data-gated visibility — shown in the directory as "not yet populated", hidden in rail).
 */
import type { SvgIconComponent } from '@mui/icons-material';
import AccountBalanceOutlinedIcon from '@mui/icons-material/AccountBalanceOutlined';
import AdminPanelSettingsOutlinedIcon from '@mui/icons-material/AdminPanelSettingsOutlined';
import CampaignOutlinedIcon from '@mui/icons-material/CampaignOutlined';
import DashboardOutlinedIcon from '@mui/icons-material/DashboardOutlined';
import EventNoteOutlinedIcon from '@mui/icons-material/EventNoteOutlined';
import Inventory2OutlinedIcon from '@mui/icons-material/Inventory2Outlined';
import LocalShippingOutlinedIcon from '@mui/icons-material/LocalShippingOutlined';
import StorageOutlinedIcon from '@mui/icons-material/StorageOutlined';

export type Role = 'admin' | 'steward' | 'planner' | 'viewer';

export type LabLeaf = {
  label: string;
  href: string;
  /** One sentence: what this workflow computes or lets you do. Shown in directory + palette. */
  what: string;
  roles?: Role[];
  populated?: boolean;
};

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
    ],
  },
  {
    id: 'funding',
    label: 'Funding & Settlement',
    short: 'Funding',
    href: '/design-lab/funding',
    icon: AccountBalanceOutlinedIcon,
    what: 'Price protection, rebate and support cases: book, evidence, approval and settlement.',
    leaves: [
      { label: 'Case book', href: '/design-lab/funding', what: 'All funding cases: claimed, settled, outstanding, blocked reasons, ageing.' },
      { label: 'Claims evidence', href: '/design-lab/funding?lens=claims', what: 'Imported claim evidence matched to cases.' },
      { label: 'Payments', href: '/design-lab/funding?lens=payments', what: 'Payment evidence and delivery rate.' },
      { label: 'Pricing support', href: '/design-lab/funding?lens=pricing', what: 'Sell-in pricing support terms feeding case economics.' },
    ],
  },
  {
    id: 'commercial',
    label: 'Commercial inputs',
    short: 'Commercial',
    href: '/design-lab/commercial',
    icon: CampaignOutlinedIcon,
    what: 'Plan inputs and market evidence: promotion plans, price observations. Shown only where data exists.',
    leaves: [
      { label: 'Promotion plans', href: '/design-lab/commercial?lens=promotions', what: 'Imported promotion plan lines per customer and period (inputs — no uplift calculation yet).' },
      { label: 'Price observations', href: '/design-lab/commercial?lens=prices', what: 'Captured listing prices over time per product and retailer.' },
      { label: 'Competition', href: '/design-lab/commercial?lens=competition', what: 'Not yet populated.', populated: false },
      { label: 'Roadmap', href: '/design-lab/commercial?lens=roadmap', what: 'Not yet populated.', populated: false },
      { label: 'Budgets', href: '/design-lab/commercial?lens=budgets', what: 'Not yet populated.', populated: false },
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
  return domain.leaves.filter((l) => l.populated !== false && (!l.roles || l.roles.includes(role)));
}
