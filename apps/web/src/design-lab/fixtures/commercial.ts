/**
 * Commercial fixtures — Promotion Planner, listing intelligence, product competition.
 *
 * Shapes mirror the real data layer so nothing shown is a number CIP cannot hold or compute:
 *  - a promotion plan IS a CPOR case (`cpor_case` / `cpor_case_line`; customer × window × promotion type,
 *    lines product × distributor × POD-quarter layer) — the same row later claimed and settled;
 *  - waterfall: dealer_price = SRP / (1 + vat) × (1 − dealer_margin); support_unit = max(0, cost − dealer_price);
 *  - listings = `customer_listing` + `listing_observation` (+ activation vs covering line SRP);
 *  - competition = `dim_competitor_product` + `fact_competitor_mapping` (score, factors, approval) + `fact_competitor_price`.
 * Capability status per surface is declared in `commercialCapabilities` and rendered honestly.
 */
import type { LeafStatus } from '../shell/labNav';
import { customers, products } from './entities';

/** Same four-state vocabulary as navigation (`LeafStatus`), applied per capability inside a surface. */
export type Capability = { label: string; state: LeafStatus; note: string };

export const commercialCapabilities: Record<'planner' | 'listings' | 'competition', Capability[]> = {
  planner: [
    { label: 'Propose a plan from history, cover, forecast and MAC', state: 'partial', note: 'Draft exists (B4) but needs a seed case id; no proposal from customer + period alone.' },
    { label: 'Create and edit plans manually (lines, layers, parameters)', state: 'live', note: 'Case + line CRUD, per-cell edits, reset to suggested, lifecycle transitions with events.' },
    { label: 'Waterfall and validation (dealer price, support/unit, budget check, flags)', state: 'live', note: 'Server-side recompute; flags never block.' },
    { label: 'Evidence behind each line in one view', state: 'partial', note: 'Cost tiers, comparables, norms and MAC buckets exist as separate endpoints and popovers.' },
    { label: 'Export in the customer’s promotion-plan format', state: 'partial', note: 'Versioned XLSX exists; layout is one frozen 32-column tuple in code.' },
    { label: 'Map a new customer template once, export in it later', state: 'substrate', note: 'Import mapping profile is stored in the DB (sheet roles, column map, value maps); export side and “learn from example workbook” are not built.' },
    { label: 'Uplift, elasticity, effectiveness', state: 'planned', note: 'Trigger: 5–10 settled cases with claim evidence across ≥3 customers. Never shown as a figure until then.' },
  ],
  listings: [
    { label: 'Monitored listings and URLs per customer × product', state: 'live', note: 'Registry with status history; manual, CSV, feed proposals, auto-finder.' },
    { label: 'Price and availability history', state: 'live', note: 'Scheduled and manual polls; snapshots retained; re-parse without re-fetch.' },
    { label: 'Is the promotion live at the planned price?', state: 'live', note: 'Each observation is checked against the covering CPOR line SRP.' },
    { label: 'Price-change detection and alerts', state: 'partial', note: 'First→last drift per listing; no per-change events or attention signal yet.' },
    { label: 'Late activation / early deactivation', state: 'substrate', note: 'Derivable from the observation timeline and the line window; not computed.' },
    { label: 'Product content and specification evidence', state: 'substrate', note: 'Raw snapshots are stored; only price, availability and badge are extracted.' },
    { label: 'SEO / listing-quality monitoring', state: 'planned', note: 'Spec v0 non-goal; roadmap P5.' },
  ],
  competition: [
    { label: 'Our SKU ↔ competitor SKU mappings with approval', state: 'live', note: 'Approve / reject / delete workflow and page exist; rows come from seed only.' },
    { label: 'System-proposed candidates with factor breakdown', state: 'substrate', note: 'Deterministic scorer exists (category, form, specs, title, price proximity) — nothing calls it yet.' },
    { label: 'Competitor price observations', state: 'substrate', note: 'Table and list endpoint exist; no import template, no rows.' },
    { label: 'Monitored competitor listings', state: 'planned', note: 'Extend the listing registry to competitor products (BACKLOG §9.9).' },
    { label: 'Competitor impact on our sell-out or price', state: 'planned', note: 'Not derivable from stored data; not shown.' },
  ],
};

// ---------------------------------------------------------------------------------------------
// Promotion plans (CPOR cases in the planning half of the lifecycle)
// ---------------------------------------------------------------------------------------------

export type PlanStage = 'draft' | 'proposed' | 'approved' | 'active' | 'ended' | 'settled' | 'cancelled';
export const lifecycleStages: PlanStage[] = ['draft', 'proposed', 'approved', 'active', 'ended', 'settled'];
export const stageLabel: Record<PlanStage, string> = {
  draft: 'Draft',
  proposed: 'Proposed',
  approved: 'Approved',
  active: 'Live',
  ended: 'Ended',
  settled: 'Settled',
  cancelled: 'Cancelled',
};

export type PromotionType = 'Sell-Through PP' | 'Sell out PP' | 'Stock PP (In-Direct)';
export type PlanOrigin = 'proposed_by_cip' | 'manual' | 'historical_import';
export type ActivationStatus = 'not_activated' | 'price_consistent' | 'no_case_detected' | 'no_listing' | 'not_started';

export type PromotionPlan = {
  id: string;
  name: string;
  customerId: number;
  customer: string;
  promotionType: PromotionType;
  windowStart: string;
  windowEnd: string;
  period: string;
  stage: PlanStage;
  origin: PlanOrigin;
  lines: number;
  estimateUnits: number;
  supportTotal: number;
  roe: number;
  templateCode: string;
  activation: ActivationStatus;
  flags: string[];
  updated: string;
  owner: string;
};

const c = (id: number) => customers.find((x) => x.id === id)!;

export const promotionPlans: PromotionPlan[] = [
  { id: 'CPR-26-1204', name: 'TechMart Sept monitor sell-through', customerId: 101, customer: c(101).name, promotionType: 'Sell-Through PP', windowStart: '2026-09-07', windowEnd: '2026-09-20', period: 'FY26 P09 · W37–W38', stage: 'proposed', origin: 'proposed_by_cip', lines: 4, estimateUnits: 1_820, supportTotal: 486_400, roe: 18.2, templateCode: 'techmart_promo_grid_v2', activation: 'not_started', flags: ['cost_basis_drift on UX2780Q'], updated: 'Today 09:40', owner: 'L. Naidoo' },
  { id: 'CPR-26-1203', name: 'Metro Electronics FNB-Day notebooks', customerId: 102, customer: c(102).name, promotionType: 'Sell-Through PP', windowStart: '2026-08-24', windowEnd: '2026-09-06', period: 'FY26 P09 · W35–W36', stage: 'active', origin: 'manual', lines: 3, estimateUnits: 960, supportTotal: 402_000, roe: 18.2, templateCode: 'asus_consumer_cpor_tracking_v1', activation: 'not_activated', flags: ['listing 1 of 3 not at promo price'], updated: 'Yesterday 16:10', owner: 'S. Dlamini' },
  { id: 'CPR-26-1202', name: 'OfficeWorld P10 accessories bundle', customerId: 104, customer: c(104).name, promotionType: 'Sell-Through PP', windowStart: '2026-09-28', windowEnd: '2026-10-11', period: 'FY26 P10 · W40–W41', stage: 'draft', origin: 'proposed_by_cip', lines: 5, estimateUnits: 2_400, supportTotal: 228_000, roe: 18.2, templateCode: 'officeworld_promo_v1', activation: 'not_started', flags: ['2 lines missing SKU assumptions', 'template needs mapping'], updated: 'Mon 15:33', owner: 'L. Naidoo' },
  { id: 'CPR-26-1201', name: 'HiFi House curved monitor launch', customerId: 103, customer: c(103).name, promotionType: 'Stock PP (In-Direct)', windowStart: '2026-09-14', windowEnd: '2026-10-04', period: 'FY26 P09–P10', stage: 'approved', origin: 'manual', lines: 1, estimateUnits: 350, supportTotal: 210_000, roe: 18.2, templateCode: 'asus_consumer_cpor_tracking_v1', activation: 'not_started', flags: [], updated: 'Fri 11:02', owner: 'S. Dlamini' },
  { id: 'CPR-26-1198', name: 'Metro Electronics winter notebooks', customerId: 102, customer: c(102).name, promotionType: 'Sell-Through PP', windowStart: '2026-08-03', windowEnd: '2026-08-16', period: 'FY26 P08 · W32–W33', stage: 'ended', origin: 'proposed_by_cip', lines: 3, estimateUnits: 1_100, supportTotal: 356_000, roe: 18.0, templateCode: 'asus_consumer_cpor_tracking_v1', activation: 'price_consistent', flags: ['claim evidence pending'], updated: '2026-08-18', owner: 'S. Dlamini' },
  { id: 'CPR-26-1195', name: 'Game Zone dock + keyboard weekend', customerId: 105, customer: c(105).name, promotionType: 'Sell out PP', windowStart: '2026-07-24', windowEnd: '2026-07-27', period: 'FY26 P07', stage: 'settled', origin: 'historical_import', lines: 2, estimateUnits: 400, supportTotal: 62_000, roe: 18.0, templateCode: 'asus_consumer_cpor_tracking_v1', activation: 'price_consistent', flags: [], updated: '2026-08-21', owner: 'Historical import' },
  { id: 'CPR-26-1190', name: 'TechMart back-to-school notebooks', customerId: 101, customer: c(101).name, promotionType: 'Sell-Through PP', windowStart: '2026-07-06', windowEnd: '2026-07-19', period: 'FY26 P07', stage: 'settled', origin: 'historical_import', lines: 4, estimateUnits: 1_500, supportTotal: 510_000, roe: 18.0, templateCode: 'techmart_promo_grid_v2', activation: 'price_consistent', flags: [], updated: '2026-08-02', owner: 'Historical import' },
  { id: 'CPR-26-1187', name: 'Byte & Co printer clearance', customerId: 106, customer: c(106).name, promotionType: 'Sell out PP', windowStart: '2026-06-15', windowEnd: '2026-06-30', period: 'FY26 P06', stage: 'cancelled', origin: 'manual', lines: 1, estimateUnits: 120, supportTotal: 0, roe: 18.0, templateCode: 'asus_consumer_cpor_tracking_v1', activation: 'no_listing', flags: ['cancelled — zero payable'], updated: '2026-06-12', owner: 'L. Naidoo' },
];

export type CostSource = 'cst_reported' | 'sellout_evidence' | 'intake_weighted' | 'manual';
export const costSourceLabel: Record<CostSource, string> = {
  cst_reported: 'Customer-reported cost (CST)',
  sellout_evidence: 'DSI sell-out weighted avg',
  intake_weighted: 'Intake-weighted MAC',
  manual: 'Manual override',
};

export type PlanLine = {
  id: number;
  productId: number;
  sku: string;
  product: string;
  distributor: string;
  layer: string;
  srp: number;
  vatRate: number;
  dealerMarginPct: number;
  costBasis: number;
  costSource: CostSource;
  costAsOf: string;
  estimateQty: number;
  suggestedQty: number;
  historyUnits: number;
  forecast13w: number;
  coverWeeks: number;
  comparables: number;
  normSupportUnit: number;
  flags: string[];
  listing?: { marketplace: string; lastPrice: number; activation: ActivationStatus };
  competitors: { mapped: number; priced: number; lowestPrice?: number };
};

export function dealerPrice(l: Pick<PlanLine, 'srp' | 'vatRate' | 'dealerMarginPct'>): number {
  return (l.srp / (1 + l.vatRate)) * (1 - l.dealerMarginPct);
}
export function supportUnit(l: Pick<PlanLine, 'srp' | 'vatRate' | 'dealerMarginPct' | 'costBasis'>): number {
  return Math.max(0, l.costBasis - dealerPrice(l));
}
export function lineSupport(l: PlanLine): number {
  return supportUnit(l) * l.estimateQty;
}

const p = (id: number) => products.find((x) => x.id === id)!;

/** Lines for CPR-26-1204 (TechMart, proposed by CIP). */
export const planLines: PlanLine[] = [
  { id: 1, productId: 61, sku: p(61).sku, product: p(61).name, distributor: 'Meridian Distribution', layer: '26Q3', srp: 8_499, vatRate: 0.15, dealerMarginPct: 0.15, costBasis: 6_540, costSource: 'intake_weighted', costAsOf: '2026-08-30', estimateQty: 600, suggestedQty: 560, historyUnits: 520, forecast13w: 1_240, coverWeeks: 6.1, comparables: 4, normSupportUnit: 245, flags: ['cost_basis_drift +R120 since approval of CPR-26-1190'], listing: { marketplace: 'TechMart', lastPrice: 8_999, activation: 'not_started' }, competitors: { mapped: 2, priced: 0 } },
  { id: 2, productId: 62, sku: p(62).sku, product: p(62).name, distributor: 'Meridian Distribution', layer: '26Q3', srp: 12_999, vatRate: 0.15, dealerMarginPct: 0.15, costBasis: 9_980, costSource: 'cst_reported', costAsOf: '2026-08-28', estimateQty: 320, suggestedQty: 320, historyUnits: 290, forecast13w: 610, coverWeeks: 9.4, comparables: 2, normSupportUnit: 380, flags: [], listing: { marketplace: 'TechMart', lastPrice: 13_499, activation: 'not_started' }, competitors: { mapped: 1, priced: 0 } },
  { id: 3, productId: 63, sku: p(63).sku, product: p(63).name, distributor: 'Coastal Tech Supply', layer: '26Q3', srp: 3_299, vatRate: 0.15, dealerMarginPct: 0.15, costBasis: 2_560, costSource: 'sellout_evidence', costAsOf: '2026-08-31', estimateQty: 700, suggestedQty: 700, historyUnits: 640, forecast13w: 1_900, coverWeeks: 3.2, comparables: 5, normSupportUnit: 120, flags: ['cover 3.2 wks below 4.0 target — replenish before window'], listing: { marketplace: 'TechMart', lastPrice: 3_499, activation: 'not_started' }, competitors: { mapped: 0, priced: 0 } },
  { id: 4, productId: 82, sku: p(82).sku, product: p(82).name, distributor: 'Coastal Tech Supply', layer: '26Q3', srp: 1_799, vatRate: 0.15, dealerMarginPct: 0.18, costBasis: 1_330, costSource: 'manual', costAsOf: '2026-09-01', estimateQty: 200, suggestedQty: 180, historyUnits: 150, forecast13w: 420, coverWeeks: 7.8, comparables: 1, normSupportUnit: 60, flags: ['no_cost_evidence — manual cost entered'], competitors: { mapped: 1, priced: 0 } },
];

export type CostTier = { tier: string; value: number | null; asOf: string | null; chosen: boolean; note: string };
export const costEvidenceForLine = (line: PlanLine): CostTier[] => [
  { tier: 'Customer-reported cost (CST feed)', value: line.costSource === 'cst_reported' ? line.costBasis : line.productId === 61 ? 6_420 : null, asOf: line.productId === 61 ? '2026-08-28' : line.costSource === 'cst_reported' ? line.costAsOf : null, chosen: line.costSource === 'cst_reported', note: 'Latest report at or before case creation' },
  { tier: 'DSI sell-out weighted average (180 d)', value: line.costSource === 'sellout_evidence' ? line.costBasis : line.productId === 61 ? 6_510 : line.productId === 62 ? 10_020 : null, asOf: line.costSource === 'sellout_evidence' ? line.costAsOf : line.productId === 61 || line.productId === 62 ? '2026-08-31' : null, chosen: line.costSource === 'sellout_evidence', note: 'unit_sellout_price_ex_tax, weighted by units' },
  { tier: 'Intake-weighted MAC (bucket A on-hand · bucket B intake)', value: line.costSource === 'intake_weighted' ? line.costBasis : null, asOf: line.costSource === 'intake_weighted' ? line.costAsOf : null, chosen: line.costSource === 'intake_weighted', note: 'Display legs (planned supply, sell-out value) are not in the blend' },
  { tier: 'Manual', value: line.costSource === 'manual' ? line.costBasis : null, asOf: line.costSource === 'manual' ? line.costAsOf : null, chosen: line.costSource === 'manual', note: 'Provenance recorded; deviation from evidence flagged, never blocked' },
];

export const comparableCases = [
  { id: 'CPR-26-1190', customer: 'TechMart', window: 'Jul W28–W29', supportUnit: 262, estimate: 600, result: 548, delivery: 0.91 },
  { id: 'CPR-26-1161', customer: 'TechMart', window: 'Apr W15–W16', supportUnit: 230, estimate: 500, result: 610, delivery: 1.22 },
  { id: 'CPR-26-1144', customer: 'Metro Electronics', window: 'Mar W11–W12', supportUnit: 248, estimate: 450, result: 402, delivery: 0.89 },
  { id: 'CPR-25-0982', customer: 'TechMart', window: 'Nov W46–W47', supportUnit: 240, estimate: 800, result: 655, delivery: 0.82 },
];

export const budgetCheck = { reservationUsd: 41_200, drawnUsd: 27_900, thisPlanUsd: 26_700, source: 'lineup-derived profit reservation · FY26 P09', overBudget: true, hardEnforce: false };

// ---------------------------------------------------------------------------------------------
// External plan templates (canonical CPOR model ↔ customer workbook)
// ---------------------------------------------------------------------------------------------

export type TemplateStatus = 'mapped' | 'needs_mapping' | 'draft';
export type PlanTemplate = {
  code: string;
  name: string;
  owner: string;
  direction: 'import + export' | 'import only' | 'export only';
  sheets: string[];
  headerRow: number;
  canonicalFields: number;
  mappedFields: number;
  valueMaps: number;
  learnedFrom: string;
  lastUsed: string;
  status: TemplateStatus;
  usedByPlans: number;
};

export const planTemplates: PlanTemplate[] = [
  { code: 'asus_consumer_cpor_tracking_v1', name: 'Consumer CPOR tracking workbook', owner: 'Tenant default', direction: 'import + export', sheets: ['Disti Sell out', 'Reseller Sell out', 'USD Pivot'], headerRow: 1, canonicalFields: 39, mappedFields: 39, valueMaps: 2, learnedFrom: 'Consumer_CPOR_Tracking_Table_20260623.xlsx', lastUsed: 'Today', status: 'mapped', usedByPlans: 312 },
  { code: 'techmart_promo_grid_v2', name: 'TechMart promo grid', owner: 'TechMart', direction: 'import + export', sheets: ['Promo Grid'], headerRow: 3, canonicalFields: 39, mappedFields: 27, valueMaps: 1, learnedFrom: 'TechMart_Promo_Grid_Sep26.xlsx', lastUsed: 'Today', status: 'mapped', usedByPlans: 2 },
  { code: 'officeworld_promo_v1', name: 'OfficeWorld promotion request form', owner: 'OfficeWorld', direction: 'export only', sheets: ['Request'], headerRow: 2, canonicalFields: 39, mappedFields: 18, valueMaps: 0, learnedFrom: 'OW_Promo_Request_blank.xlsx', lastUsed: '—', status: 'needs_mapping', usedByPlans: 1 },
];

export type TemplateFieldMap = { canonical: string; header: string | null; example: string; required: boolean; transform?: string };

export const templateFieldMaps: Record<string, TemplateFieldMap[]> = {
  techmart_promo_grid_v2: [
    { canonical: 'case_code', header: 'Promo Ref', example: 'TM-SEP-0912', required: true },
    { canonical: 'customer', header: null, example: 'TechMart (implied by file)', required: true, transform: 'constant: TechMart' },
    { canonical: 'promotion_type', header: 'Mechanic', example: 'Sell-Through PP', required: true, transform: 'value map: Price drop → Sell-Through PP' },
    { canonical: 'window_start', header: 'Start', example: '07/09/2026', required: true, transform: 'date dd/mm/yyyy' },
    { canonical: 'window_end', header: 'End', example: '20/09/2026', required: true, transform: 'date dd/mm/yyyy' },
    { canonical: 'product_token', header: 'ASUS SKU', example: 'UX2780Q', required: true },
    { canonical: 'distributor', header: 'Supplier', example: 'Meridian', required: false },
    { canonical: 'srp', header: 'Promo RSP (incl VAT)', example: '8 499', required: true },
    { canonical: 'dealer_margin_pct', header: 'Margin %', example: '15%', required: false },
    { canonical: 'cost_basis', header: 'Cost ex VAT', example: '6 540', required: false },
    { canonical: 'support_unit', header: 'Support per unit', example: '260.12', required: true, transform: 'computed on export' },
    { canonical: 'estimate_qty', header: 'Forecast units', example: '600', required: true },
    { canonical: 'ttl_support', header: 'Total support', example: '156 072', required: false, transform: 'computed on export' },
    { canonical: 'result_qty', header: 'Actual units', example: '', required: false },
    { canonical: 'rebate_pct', header: null, example: '', required: false },
    { canonical: 'disti_margin_pct', header: null, example: '', required: false },
  ],
  officeworld_promo_v1: [
    { canonical: 'case_code', header: 'Reference', example: 'OW-P10-…', required: true },
    { canonical: 'promotion_type', header: null, example: '', required: true },
    { canonical: 'window_start', header: 'From', example: '2026-09-28', required: true },
    { canonical: 'window_end', header: 'To', example: '2026-10-11', required: true },
    { canonical: 'product_token', header: 'Product code', example: 'DK-TB4', required: true },
    { canonical: 'srp', header: 'Offer price', example: '2 499', required: true },
    { canonical: 'support_unit', header: 'Vendor contribution', example: '', required: true, transform: 'computed on export' },
    { canonical: 'estimate_qty', header: 'Qty', example: '400', required: true },
    { canonical: 'cost_basis', header: null, example: '', required: false },
    { canonical: 'distributor', header: null, example: '', required: false },
  ],
};

// ---------------------------------------------------------------------------------------------
// Listings (customer_listing + listing_observation)
// ---------------------------------------------------------------------------------------------

export type ListingStatus = 'active' | 'out_of_stock' | 'delisted' | 'dead_link';
export type Listing = {
  id: number;
  customerId: number;
  customer: string;
  productId: number | null;
  sku: string | null;
  product: string | null;
  marketplace: string;
  url: string;
  status: ListingStatus;
  source: 'manual' | 'csv' | 'feed_proposal' | 'auto_finder';
  observations: number;
  spanDays: number;
  firstPrice: number | null;
  lastPrice: number | null;
  availability: string;
  promoBadge: string | null;
  activation: ActivationStatus;
  caseCode?: string;
  casePrice?: number;
  lastFetched: string;
};

export const listings: Listing[] = [
  { id: 44, customerId: 102, customer: 'Metro Electronics', productId: 71, sku: 'NBP14-I7', product: p(71).name, marketplace: 'metro', url: 'metro.example/p/nbp14-i7', status: 'active', source: 'feed_proposal', observations: 41, spanDays: 38, firstPrice: 19_499, lastPrice: 18_999, availability: 'in_stock', promoBadge: null, activation: 'not_activated', caseCode: 'CPR-26-1203', casePrice: 16_999, lastFetched: 'Today 06:10' },
  { id: 45, customerId: 102, customer: 'Metro Electronics', productId: 72, sku: 'NBP16-I9', product: p(72).name, marketplace: 'metro', url: 'metro.example/p/nbp16-i9', status: 'active', source: 'feed_proposal', observations: 41, spanDays: 38, firstPrice: 34_999, lastPrice: 31_999, availability: 'in_stock', promoBadge: 'FNB Day', activation: 'price_consistent', caseCode: 'CPR-26-1203', casePrice: 31_999, lastFetched: 'Today 06:10' },
  { id: 46, customerId: 102, customer: 'Metro Electronics', productId: 73, sku: 'NBE15-I5', product: p(73).name, marketplace: 'metro', url: 'metro.example/p/nbe15-i5', status: 'active', source: 'feed_proposal', observations: 40, spanDays: 38, firstPrice: 11_499, lastPrice: 9_999, availability: 'low_stock', promoBadge: 'FNB Day', activation: 'price_consistent', caseCode: 'CPR-26-1203', casePrice: 9_999, lastFetched: 'Today 06:10' },
  { id: 51, customerId: 101, customer: 'TechMart', productId: 61, sku: 'UX2780Q', product: p(61).name, marketplace: 'techmart', url: 'techmart.example/monitors/ux2780q', status: 'active', source: 'auto_finder', observations: 36, spanDays: 35, firstPrice: 8_999, lastPrice: 8_999, availability: 'in_stock', promoBadge: null, activation: 'no_case_detected', lastFetched: 'Today 06:12' },
  { id: 52, customerId: 101, customer: 'TechMart', productId: 62, sku: 'UX3440W', product: p(62).name, marketplace: 'techmart', url: 'techmart.example/monitors/ux3440w', status: 'active', source: 'auto_finder', observations: 36, spanDays: 35, firstPrice: 13_999, lastPrice: 13_499, availability: 'in_stock', promoBadge: null, activation: 'no_case_detected', lastFetched: 'Today 06:12' },
  { id: 53, customerId: 101, customer: 'TechMart', productId: 63, sku: 'UX2410F', product: p(63).name, marketplace: 'techmart', url: 'techmart.example/monitors/ux2410f', status: 'out_of_stock', source: 'auto_finder', observations: 36, spanDays: 35, firstPrice: 3_499, lastPrice: 3_499, availability: 'out_of_stock', promoBadge: null, activation: 'no_case_detected', lastFetched: 'Today 06:12' },
  { id: 57, customerId: 104, customer: 'OfficeWorld', productId: 81, sku: 'DK-TB4', product: p(81).name, marketplace: 'officeworld', url: 'officeworld.example/dk-tb4', status: 'active', source: 'manual', observations: 9, spanDays: 8, firstPrice: 2_699, lastPrice: 2_699, availability: 'in_stock', promoBadge: null, activation: 'no_case_detected', lastFetched: 'Today 06:15' },
  { id: 58, customerId: 104, customer: 'OfficeWorld', productId: 82, sku: 'KB-MX', product: p(82).name, marketplace: 'officeworld', url: 'officeworld.example/kb-mx', status: 'active', source: 'manual', observations: 9, spanDays: 8, firstPrice: 1_899, lastPrice: 1_899, availability: 'in_stock', promoBadge: null, activation: 'no_case_detected', lastFetched: 'Today 06:15' },
  { id: 60, customerId: 105, customer: 'Game Zone', productId: null, sku: null, product: null, marketplace: 'gamezone', url: 'gamezone.example/keris-ii-origin', status: 'active', source: 'feed_proposal', observations: 12, spanDays: 11, firstPrice: 1_299, lastPrice: 1_299, availability: 'in_stock', promoBadge: null, activation: 'no_listing', lastFetched: 'Today 06:18' },
  { id: 61, customerId: 103, customer: 'HiFi House', productId: 62, sku: 'UX3440W', product: p(62).name, marketplace: 'hifihouse', url: 'hifihouse.example/ux3440w', status: 'dead_link', source: 'csv', observations: 22, spanDays: 30, firstPrice: 13_999, lastPrice: null, availability: 'unknown', promoBadge: null, activation: 'no_case_detected', lastFetched: '2026-08-29' },
];

export const activationLabel: Record<ActivationStatus, string> = {
  not_activated: 'Not at promo price',
  price_consistent: 'Promo live at price',
  no_case_detected: 'No promotion covering today',
  no_listing: 'No product link',
  not_started: 'Window not started',
};

/** Daily price history for listing 44 (Metro · NBP14-I7) across the CPR-26-1203 window. */
export const listingHistory = Array.from({ length: 38 }, (_, i) => {
  const d = new Date(2026, 6, 27 + i);
  const iso = d.toISOString().slice(0, 10);
  const inWindow = iso >= '2026-08-24' && iso <= '2026-09-06';
  const price = i < 12 ? 19_499 : 18_999;
  return { date: iso.slice(5), price, casePrice: inWindow ? 16_999 : null, inWindow };
});

export type ListingProposal = { id: number; customer: string; marketplace: string; externalId: string; suggestedUrl: string | null; productMatch: string | null; source: string; status: 'proposed' | 'confirmed' | 'rejected' };
export const listingProposals: ListingProposal[] = [
  { id: 901, customer: 'TechMart', marketplace: 'techmart', externalId: 'TM-883120', suggestedUrl: 'techmart.example/notebooks/nbp14-i7', productMatch: 'NBP14-I7', source: 'CST feed W36 (Web ID)', status: 'proposed' },
  { id: 902, customer: 'TechMart', marketplace: 'techmart', externalId: 'TM-883121', suggestedUrl: 'techmart.example/notebooks/nbp16-i9', productMatch: 'NBP16-I9', source: 'CST feed W36 (Web ID)', status: 'proposed' },
  { id: 903, customer: 'Game Zone', marketplace: 'gamezone', externalId: 'GZ-PLID-77120', suggestedUrl: null, productMatch: null, source: 'CST feed W35 (PLID)', status: 'proposed' },
  { id: 904, customer: 'Metro Electronics', marketplace: 'metro', externalId: 'MEL-449021', suggestedUrl: 'metro.example/p/wc-4k', productMatch: 'WC-4K (inactive product)', source: 'CST feed W36', status: 'proposed' },
];

// ---------------------------------------------------------------------------------------------
// Product competition (dim_competitor_product · fact_competitor_mapping · fact_competitor_price)
// ---------------------------------------------------------------------------------------------

export type MappingStatus = 'pending' | 'approved' | 'rejected';
export type MappingOrigin = 'loaded' | 'confirmed' | 'proposed';
export type CompetitorMapping = {
  id: number;
  productId: number;
  sku: string;
  product: string;
  competitorBrand: string;
  competitorSku: string;
  competitorName: string;
  score: number;
  factors: { category: number; form: number; specs: number; title: number; price: number };
  explanation: string;
  status: MappingStatus;
  origin: MappingOrigin;
  priceObservations: number;
  lastPrice: number | null;
  listingMonitored: boolean;
};

export const competitorMappings: CompetitorMapping[] = [
  { id: 1, productId: 61, sku: 'UX2780Q', product: p(61).name, competitorBrand: 'Dellex', competitorSku: 'S2722DGM', competitorName: 'Dellex 27" QHD 165Hz S2722DGM', score: 0.86, factors: { category: 1, form: 1, specs: 0.71, title: 0.62, price: 0.94 }, explanation: 'Weighted blend: category 1.00, form 1.00, specs 0.71, title tokens 0.62, price proximity 0.94 → score 0.860.', status: 'approved', origin: 'confirmed', priceObservations: 0, lastPrice: null, listingMonitored: false },
  { id: 2, productId: 61, sku: 'UX2780Q', product: p(61).name, competitorBrand: 'Lenova', competitorSku: 'Q27H-20', competitorName: 'Lenova Q27h-20 QHD', score: 0.79, factors: { category: 1, form: 1, specs: 0.58, title: 0.55, price: 0.9 }, explanation: 'Weighted blend: category 1.00, form 1.00, specs 0.58, title tokens 0.55, price proximity 0.90 → score 0.790.', status: 'approved', origin: 'loaded', priceObservations: 0, lastPrice: null, listingMonitored: false },
  { id: 3, productId: 62, sku: 'UX3440W', product: p(62).name, competitorBrand: 'Dellex', competitorSku: 'S3422DWG', competitorName: 'Dellex 34" Curved WQHD S3422DWG', score: 0.83, factors: { category: 1, form: 1, specs: 0.66, title: 0.6, price: 0.88 }, explanation: 'Weighted blend: category 1.00, form 1.00, specs 0.66, title tokens 0.60, price proximity 0.88 → score 0.830.', status: 'approved', origin: 'confirmed', priceObservations: 0, lastPrice: null, listingMonitored: false },
  { id: 4, productId: 71, sku: 'NBP14-I7', product: p(71).name, competitorBrand: 'Lenova', competitorSku: 'IDEAPRO-5-14', competitorName: 'Lenova IdeaPro 5 14" i7 16GB', score: 0.81, factors: { category: 1, form: 1, specs: 0.7, title: 0.48, price: 0.86 }, explanation: 'Weighted blend: category 1.00, form 1.00, specs 0.70, title tokens 0.48, price proximity 0.86 → score 0.810.', status: 'pending', origin: 'proposed', priceObservations: 0, lastPrice: null, listingMonitored: false },
  { id: 5, productId: 71, sku: 'NBP14-I7', product: p(71).name, competitorBrand: 'HPX', competitorSku: 'PAV-PLUS-14', competitorName: 'HPX Pavilion Plus 14 i7', score: 0.77, factors: { category: 1, form: 1, specs: 0.62, title: 0.44, price: 0.84 }, explanation: 'Weighted blend: category 1.00, form 1.00, specs 0.62, title tokens 0.44, price proximity 0.84 → score 0.770.', status: 'pending', origin: 'proposed', priceObservations: 0, lastPrice: null, listingMonitored: false },
  { id: 6, productId: 82, sku: 'KB-MX', product: p(82).name, competitorBrand: 'Logitek', competitorSku: 'MX-MECH', competitorName: 'Logitek MX Mechanical', score: 0.74, factors: { category: 1, form: 0.5, specs: 0.52, title: 0.71, price: 0.79 }, explanation: 'Weighted blend: category 1.00, form 0.50, specs 0.52, title tokens 0.71, price proximity 0.79 → score 0.740.', status: 'pending', origin: 'proposed', priceObservations: 0, lastPrice: null, listingMonitored: false },
  { id: 7, productId: 81, sku: 'DK-TB4', product: p(81).name, competitorBrand: 'Dellex', competitorSku: 'WD22TB4', competitorName: 'Dellex Thunderbolt Dock WD22TB4', score: 0.88, factors: { category: 1, form: 1, specs: 0.8, title: 0.66, price: 0.9 }, explanation: 'Weighted blend: category 1.00, form 1.00, specs 0.80, title tokens 0.66, price proximity 0.90 → score 0.880.', status: 'approved', origin: 'loaded', priceObservations: 0, lastPrice: null, listingMonitored: false },
  { id: 8, productId: 91, sku: 'PR-L2600', product: p(91).name, competitorBrand: 'Brothr', competitorSku: 'HL-L2400', competitorName: 'Brothr HL-L2400DW mono laser', score: 0.41, factors: { category: 1, form: 0.5, specs: 0.2, title: 0.3, price: 0.55 }, explanation: 'Weighted blend: category 1.00, form 0.50, specs 0.20, title tokens 0.30, price proximity 0.55 → score 0.410.', status: 'rejected', origin: 'proposed', priceObservations: 0, lastPrice: null, listingMonitored: false },
];

export const scorerWeights = { category: 0.25, form: 0.15, specs: 0.25, title: 0.25, price: 0.1 };
