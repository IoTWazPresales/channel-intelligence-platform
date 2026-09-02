/**
 * Dashboard fixture mirroring the real model in apps/api/app/api/v1/endpoints/dashboards.py:
 * one governed metric per widget, visual ∈ kpi|table|bar|line|area, 12-col layout, publish per role.
 * Metric keys follow apps/api/app/semantics/catalog/default.yaml families.
 */
export type WidgetVisual = 'kpi' | 'table' | 'bar' | 'line' | 'area';

export type Widget = {
  id: string;
  metricKey: string;
  title: string;
  visual: WidgetVisual;
  w: 3 | 4 | 5 | 6 | 7 | 8 | 12;
  h: 1 | 2;
  grain?: string;
};

export type GovernedMetric = {
  key: string;
  label: string;
  family: string;
  status: 'implemented' | 'spec_only' | 'do_not_build';
  grains: string[];
  defaultVisual: WidgetVisual;
};

export const governedMetrics: GovernedMetric[] = [
  { key: 'channel_ops.network_soh', label: 'Network stock on hand', family: 'Channel ops', status: 'implemented', grains: ['distributor', 'product', 'family'], defaultVisual: 'kpi' },
  { key: 'channel_ops.weeks_of_cover', label: 'Weeks of cover', family: 'Channel ops', status: 'implemented', grains: ['distributor', 'product'], defaultVisual: 'kpi' },
  { key: 'channel_ops.cover_breaches', label: 'Pairs under cover threshold', family: 'Channel ops', status: 'implemented', grains: ['distributor'], defaultVisual: 'bar' },
  { key: 'channel_ops.sell_out_units', label: 'Distributor sell-out units', family: 'Channel ops', status: 'implemented', grains: ['week', 'family', 'distributor'], defaultVisual: 'line' },
  { key: 'channel_intel.sell_through_units', label: 'Retailer sell-through units', family: 'Channel intelligence', status: 'implemented', grains: ['week', 'customer'], defaultVisual: 'area' },
  { key: 'pve.plan_units', label: 'Plan units', family: 'Plan vs executed', status: 'implemented', grains: ['customer', 'period'], defaultVisual: 'bar' },
  { key: 'pve.shipped_vs_plan', label: 'Shipped vs plan', family: 'Plan vs executed', status: 'implemented', grains: ['customer', 'period'], defaultVisual: 'bar' },
  { key: 'shipping.unreceived_past_eta', label: 'Shipments unreceived past ETA', family: 'Shipping', status: 'implemented', grains: ['distributor', 'age_bucket'], defaultVisual: 'kpi' },
  { key: 'shipping.lifecycle_counts', label: 'Shipment lifecycle', family: 'Shipping', status: 'implemented', grains: ['state'], defaultVisual: 'bar' },
  { key: 'cpor.book_total', label: 'Funding book total', family: 'Funding (CPOR)', status: 'implemented', grains: ['customer', 'programme'], defaultVisual: 'kpi' },
  { key: 'cpor.outstanding', label: 'Funding outstanding', family: 'Funding (CPOR)', status: 'implemented', grains: ['customer', 'age_bucket'], defaultVisual: 'kpi' },
  { key: 'cpor.delivery_rate', label: 'Settlement delivery rate', family: 'Funding (CPOR)', status: 'implemented', grains: ['programme'], defaultVisual: 'kpi' },
  { key: 'cpor.support_per_unit', label: 'Support per unit sold', family: 'Funding (CPOR)', status: 'implemented', grains: ['programme', 'product'], defaultVisual: 'table' },
  { key: 'forecast.velocity_projection', label: 'Velocity projection (method-labelled)', family: 'Forecasts', status: 'spec_only', grains: ['product', 'week'], defaultVisual: 'line' },
  { key: 'cpor.claim_rate', label: 'Claim rate', family: 'Funding (CPOR)', status: 'do_not_build', grains: [], defaultVisual: 'kpi' },
];

export const defaultWidgets: Record<'planner' | 'admin' | 'steward' | 'viewer', Widget[]> = {
  planner: [
    { id: 'w1', metricKey: 'channel_ops.network_soh', title: 'Network stock on hand', visual: 'kpi', w: 3, h: 1 },
    { id: 'w2', metricKey: 'channel_ops.weeks_of_cover', title: 'Network weeks of cover', visual: 'kpi', w: 3, h: 1 },
    { id: 'w3', metricKey: 'channel_ops.sell_out_units', title: 'Sell-out this week', visual: 'kpi', w: 3, h: 1, grain: 'week' },
    { id: 'w4', metricKey: 'cpor.outstanding', title: 'Funding outstanding', visual: 'kpi', w: 3, h: 1 },
    { id: 'w5', metricKey: 'channel_ops.sell_out_units', title: 'Sell-out vs shipments, W24–W36', visual: 'line', w: 8, h: 2, grain: 'week' },
    { id: 'w6', metricKey: 'channel_ops.cover_breaches', title: 'Cover distribution (distributor × product)', visual: 'bar', w: 4, h: 2 },
    { id: 'w7', metricKey: 'pve.shipped_vs_plan', title: 'Shipped vs plan by customer, P09', visual: 'bar', w: 7, h: 2, grain: 'customer' },
    { id: 'w8', metricKey: 'cpor.outstanding', title: 'Funding outstanding by age', visual: 'bar', w: 5, h: 2, grain: 'age_bucket' },
    { id: 'w9', metricKey: 'channel_ops.sell_out_units', title: 'Sell-out by family', visual: 'table', w: 12, h: 1, grain: 'family' },
  ],
  admin: [],
  steward: [],
  viewer: [],
};
defaultWidgets.admin = defaultWidgets.planner;
defaultWidgets.viewer = defaultWidgets.planner.filter((w) => w.id !== 'w8');
defaultWidgets.steward = [
  { id: 's1', metricKey: 'channel_ops.network_soh', title: 'Network stock on hand', visual: 'kpi', w: 3, h: 1 },
  { id: 's2', metricKey: 'shipping.unreceived_past_eta', title: 'Unreceived past ETA', visual: 'kpi', w: 3, h: 1 },
  { id: 's3', metricKey: 'channel_ops.sell_out_units', title: 'Sell-out this week', visual: 'kpi', w: 3, h: 1, grain: 'week' },
  { id: 's4', metricKey: 'cpor.outstanding', title: 'Funding outstanding', visual: 'kpi', w: 3, h: 1 },
  { id: 's5', metricKey: 'channel_ops.sell_out_units', title: 'Sell-out vs shipments, W24–W36', visual: 'line', w: 8, h: 2, grain: 'week' },
  { id: 's6', metricKey: 'shipping.lifecycle_counts', title: 'Shipment lifecycle', visual: 'bar', w: 4, h: 2 },
];

export const savedReports = [
  { name: 'Weekly cover by distributor', metric: 'Weeks of cover · distributor × week', schedule: 'Mon 07:00', lastRun: 'Mon 07:00' },
  { name: 'P09 shipped vs plan — strategic customers', metric: 'Shipped vs plan · customer', schedule: 'On demand', lastRun: 'Yesterday' },
  { name: 'Funding outstanding > 30d', metric: 'Funding outstanding · age bucket', schedule: 'Fri 16:00', lastRun: 'Fri 16:00' },
];
