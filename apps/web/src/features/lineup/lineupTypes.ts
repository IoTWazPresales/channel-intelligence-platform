export type LineupPlanRow = {
  id: number;
  customer_code: string | null;
  customer_name?: string | null;
  channel_code: string | null;
  period_start: string;
  period_label: string | null;
  product_id?: number | null;
  sku: string | null;
  product_name?: string | null;
  planned_volume_units: number;
  approval_status: string;
  notes?: string | null;
};

export type NetRequirementResponse = {
  data_unavailable?: boolean;
  row_count: number;
  horizon_weeks?: number;
  target_cover_weeks?: number;
  rows: Array<{
    distributor_id: number;
    product_id: number;
    net_requirement: number;
  }>;
};

export type HalfYearPeriodsResponse = {
  year: number;
  half: number;
  rule?: string;
  periods: Array<{ period_start: string; period_label: string }>;
};

export type ApplyNetRequirementResponse = {
  inserted: number;
  updated: number;
  draft_rows_built?: number;
  commercial_case_id?: number | null;
};

export const PENDING_APPROVAL_STATUSES = new Set(['draft', 'pending_approval', 'submitted']);

export function isPendingApproval(status: string): boolean {
  return PENDING_APPROVAL_STATUSES.has(status);
}

export function approvalBadgeLabel(status: string): string {
  if (status === 'approved') return 'Approved';
  if (status === 'rejected') return 'Rejected';
  if (isPendingApproval(status)) return 'Pending';
  return status;
}

export function formatUnits(n: number): string {
  return new Intl.NumberFormat('en-US').format(Math.round(n));
}
