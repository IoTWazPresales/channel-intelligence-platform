/** Attention signals mirror the 8 live signal families in apps/api/app/services/brief_signals.py. */
export type Signal = {
  id: string;
  severity: 'danger' | 'warning' | 'info';
  headline: string;
  count: number;
  detail: string;
  href: string;
  area: string;
};

export const signals: Signal[] = [
  { id: 'failed_imports', severity: 'danger', headline: 'DSI imports failed', count: 33, detail: 'Meridian W35 sell-out; Coastal W36 SOH — parse errors on 2 files', href: '/design-lab/data?tab=imports&status=failed', area: 'Data & Stewardship' },
  { id: 'cover_breach', severity: 'danger', headline: 'Distributor × product pairs under 2 weeks cover', count: 11, detail: 'NBP16-I9 at 3 of 4 distributors', href: '/design-lab/stock?lens=cover&status=breach', area: 'Stock & Sell-through' },
  { id: 'settlement_blocked', severity: 'warning', headline: 'Funding cases blocked', count: 7, detail: 'R612k outstanding · 4 need sell-through evidence', href: '/design-lab/funding?status=blocked', area: 'Promotions & Funding' },
  { id: 'inbound_open', severity: 'warning', headline: 'Inbound shipments unreceived past ETA', count: 1714, detail: 'Oldest 41 days · Highveld receipt file missing since W33', href: '/design-lab/supply?lens=receipts', area: 'Supply & Inbound' },
  { id: 'dsi_vintage_stale', severity: 'warning', headline: 'Distributor stock vintage older than 10 days', count: 2, detail: 'Highveld (14d), Kwazulu (12d)', href: '/design-lab/stock?lens=cover&vintage=stale', area: 'Stock & Sell-through' },
  { id: 'missing_assumptions', severity: 'info', headline: 'Lineup lines missing SKU assumptions', count: 18, detail: 'TechMart P10 lineup — cost basis absent', href: '/design-lab/planning?lens=readiness', area: 'Planning' },
  { id: 'soh_recon_not_run', severity: 'info', headline: 'SOH reconciliation not run this week', count: 1, detail: 'Last run W35 · 3 distributors reported', href: '/design-lab/stock?lens=cover&recon=1', area: 'Stock & Sell-through' },
  { id: 'steward_queue', severity: 'info', headline: 'Tokens awaiting steward resolution', count: 42, detail: '19 customers · 15 products · 8 distributors', href: '/design-lab/data?tab=steward', area: 'Data & Stewardship' },
];

export type ImportJob = {
  id: number;
  template: string;
  file: string;
  source: string;
  status: 'failed' | 'validated' | 'applied' | 'stewarding' | 'running';
  rows: number;
  unresolved: number;
  when: string;
};

export const importJobs: ImportJob[] = [
  { id: 1276, template: 'distributor_inventory', file: 'MER_sellout_W36.xlsx', source: 'Meridian Distribution', status: 'stewarding', rows: 4_812, unresolved: 23, when: '09:14 today' },
  { id: 1275, template: 'distributor_inventory', file: 'CTS_SOH_W36.csv', source: 'Coastal Tech Supply', status: 'failed', rows: 0, unresolved: 0, when: '08:52 today' },
  { id: 1274, template: 'inbound_shipments', file: 'ASN_2026-09-01.csv', source: 'Aurora logistics', status: 'applied', rows: 312, unresolved: 0, when: 'Yesterday 17:40' },
  { id: 1273, template: 'customer_sell_through', file: 'TechMart_W35.xlsx', source: 'TechMart', status: 'applied', rows: 9_106, unresolved: 0, when: 'Yesterday 16:05' },
  { id: 1272, template: 'cpor_claim_evidence', file: 'Metro_claims_P08.xlsx', source: 'Metro Electronics', status: 'validated', rows: 64, unresolved: 4, when: 'Yesterday 11:20' },
  { id: 1271, template: 'unified_lineup', file: 'OfficeWorld_P10_lineup.xlsx', source: 'OfficeWorld', status: 'stewarding', rows: 148, unresolved: 19, when: 'Mon 15:33' },
  { id: 1270, template: 'distributor_inventory', file: 'HVW_W35.xlsx', source: 'Highveld Wholesale', status: 'applied', rows: 3_940, unresolved: 0, when: 'Mon 09:10' },
  { id: 1269, template: 'product_master', file: 'PM_export_2026-08-30.xlsx', source: 'Product Master', status: 'applied', rows: 18_204, unresolved: 0, when: 'Sat 22:01' },
];

export type StewardToken = {
  id: number;
  entity: 'customer' | 'product' | 'distributor';
  token: string;
  jobs: number;
  rows: number;
  bestCandidate: string;
  candidateScore: number;
  corroborated: boolean;
};

export const stewardQueue: StewardToken[] = [
  { id: 1, entity: 'customer', token: 'METRO ELEC (PTA)', jobs: 3, rows: 412, bestCandidate: 'Metro Electronics — Pretoria', candidateScore: 0.93, corroborated: true },
  { id: 2, entity: 'customer', token: 'TECHMART ONLINE', jobs: 2, rows: 1_208, bestCandidate: 'TechMart (e-commerce)', candidateScore: 0.88, corroborated: true },
  { id: 3, entity: 'product', token: 'UX2780-Q BLK', jobs: 4, rows: 96, bestCandidate: '27" QHD IPS Monitor UX2780Q', candidateScore: 0.91, corroborated: true },
  { id: 4, entity: 'product', token: 'NB PRO 16 I9 1TB', jobs: 1, rows: 40, bestCandidate: 'Notebook Pro 16 i9 / 32GB / 1TB', candidateScore: 0.84, corroborated: false },
  { id: 5, entity: 'distributor', token: 'KZN CHANNEL', jobs: 2, rows: 3_120, bestCandidate: 'Kwazulu Channel Partners', candidateScore: 0.97, corroborated: true },
  { id: 6, entity: 'customer', token: 'GAMEZONE MENLYN', jobs: 1, rows: 88, bestCandidate: 'Game Zone — Menlyn', candidateScore: 0.71, corroborated: false },
  { id: 7, entity: 'product', token: 'DOCK TB4 V2', jobs: 2, rows: 61, bestCandidate: 'Thunderbolt 4 Dock DK-TB4', candidateScore: 0.66, corroborated: false },
];

export type Shipment = {
  id: string;
  distributor: string;
  po: string;
  units: number;
  eta: string;
  ageDays: number;
  state: 'in_transit' | 'arrived' | 'received' | 'unreceived';
};

export const shipmentLifecycle = [
  { state: 'Planned (PO)', count: 412, units: 68_400 },
  { state: 'Shipped', count: 388, units: 61_900 },
  { state: 'Arrived', count: 296, units: 47_200 },
  { state: 'Received (POD)', count: 2_120, units: 402_000 },
  { state: 'Unreceived past ETA', count: 1_714, units: 129_800 },
];

export const poCoverage = [
  { distributor: 'Meridian Distribution', covered: 0.82, backlogUnits: 4_100 },
  { distributor: 'Coastal Tech Supply', covered: 0.91, backlogUnits: 1_250 },
  { distributor: 'Highveld Wholesale', covered: 0.64, backlogUnits: 7_800 },
  { distributor: 'Kwazulu Channel Partners', covered: 0.77, backlogUnits: 2_900 },
];

export const lineupSummary = {
  cases: 14,
  lines: 1_260,
  planUnits: 96_400,
  shippedUnits: 71_200,
  readinessOk: 1_102,
  readinessMissing: 158,
  economicsOk: 980,
  economicsFlagged: 280,
};

export const planVsShipped = [
  { customer: 'TechMart', plan: 28_400, shipped: 22_100 },
  { customer: 'Metro Electronics', plan: 21_900, shipped: 18_600 },
  { customer: 'OfficeWorld', plan: 19_200, shipped: 15_100 },
  { customer: 'HiFi House', plan: 9_800, shipped: 6_900 },
  { customer: 'Game Zone', plan: 8_600, shipped: 5_100 },
  { customer: 'Byte & Co', plan: 5_200, shipped: 2_400 },
  { customer: 'Open channel', plan: 3_300, shipped: 1_000 },
];

// Commercial fixtures (promotion plans, listings, competition) live in ./commercial.ts. The earlier
// `priceObservations` / `promotionPlanLines` fixtures were removed: they modelled a deprecated
// `promotion_plan` scaffold and a `price_observations` table that do not match the real data layer.
