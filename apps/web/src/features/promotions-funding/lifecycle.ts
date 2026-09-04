export const LIFECYCLE_STAGES = ['draft', 'proposed', 'approved', 'active', 'ended', 'settled'] as const;
export type PlanStage = (typeof LIFECYCLE_STAGES)[number] | 'cancelled' | 'rejected';

export const STAGE_LABEL: Record<PlanStage, string> = {
  draft: 'Draft',
  proposed: 'Proposed',
  approved: 'Approved',
  active: 'Live',
  ended: 'Ended',
  settled: 'Settled',
  cancelled: 'Cancelled',
  rejected: 'Rejected',
};

export const ORIGIN_LABEL: Record<string, string> = {
  proposed_by_cip: 'Proposed by CIP',
  manual: 'Manual',
  historical_import: 'Historical import',
  native: 'Manual',
};

export function stageTone(s: string): 'danger' | 'warning' | 'success' | 'info' | 'neutral' {
  if (s === 'active') return 'success';
  if (s === 'approved') return 'info';
  if (s === 'proposed' || s === 'rejected') return 'warning';
  if (s === 'cancelled') return 'danger';
  return 'neutral';
}

/** Planning-half statuses used by the planner headline and tab badge. */
export const PLANNING_STAGES = ['draft', 'proposed', 'approved', 'rejected'] as const;

export function countPlanning(counts: Record<string, number> | undefined): number {
  if (!counts) return 0;
  return PLANNING_STAGES.reduce((n, s) => n + (counts[s] ?? 0), 0);
}

/**
 * Support shown on the list and the workspace must be the same grain: sum of line `ttl_support`.
 * Never mix payment-recon owed into this figure (I1).
 */
export function supportFromLines(lines: { ttl_support?: number | null }[] | undefined): number {
  if (!lines?.length) return 0;
  return lines.reduce((n, l) => n + (Number(l.ttl_support) || 0), 0);
}

export function estimateQtyFromLines(lines: { estimate_qty?: number | null }[] | undefined): number {
  if (!lines?.length) return 0;
  return lines.reduce((n, l) => n + (Number(l.estimate_qty) || 0), 0);
}

export const ACTION_LABELS: Record<string, string> = {
  propose: 'Submit for approval',
  approve: 'Approve',
  reject: 'Reject',
  resend: 'Resend',
  activate: 'Mark live',
  end: 'End window',
  settle: 'Settle',
  cancel: 'Cancel',
};
