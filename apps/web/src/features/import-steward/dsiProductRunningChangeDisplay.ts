'use client';

import type { DsiProductResolutionEvidenceContext } from './DsiProductResolutionEvidenceCard';

export type DsiProductResolutionQuality = {
  total_rows?: number;
  resolved_receipt_temporal?: number;
  resolved_other?: number;
  unresolved_rows?: number;
  ignored_rows?: number;
  indeterminate_rows?: number;
  quality_denominator?: number;
};

export type DsiProductRunningChangeContext = DsiProductResolutionEvidenceContext & {
  product_match_summary?: string;
  product_resolution_quality?: DsiProductResolutionQuality;
  product_running_change_received_both?: boolean;
  temporal_supersession?: {
    status?: string;
    fifo_candidate?: boolean;
    summary?: string;
  };
  fifo_candidate?: boolean;
  steward_ignore_reason_code?: string;
  token_level_resolve_product_blocked?: boolean;
};

export function formatDsiProductRunningChangeSummary(
  ctx: DsiProductRunningChangeContext | null | undefined
): string | null {
  if (!ctx || typeof ctx !== 'object') return null;
  const sum = ctx.product_match_summary;
  if (typeof sum === 'string' && sum.trim()) {
    if (sum.includes('resolved by shipment receipt/temporal')) return sum.trim();
  }
  const q = ctx.product_resolution_quality;
  if (!q || typeof q !== 'object') return null;
  const total = Number(q.total_rows ?? 0);
  if (total <= 0) return null;
  const resolved = Number(q.resolved_receipt_temporal ?? 0);
  const indeterminate = Number(q.indeterminate_rows ?? q.unresolved_rows ?? 0);
  const receivedBoth = ctx.product_running_change_received_both === true;
  const suffix = receivedBoth && indeterminate > 0 ? ' (received-both)' : '';
  return `${resolved} of ${total} resolved by shipment receipt/temporal; ${indeterminate} indeterminate${suffix}`;
}

export function isDsiTokenLevelResolveProductBlocked(
  ctx: Record<string, unknown> | null | undefined,
  planRow?: Record<string, unknown> | null
): boolean {
  if (planRow?.token_level_resolve_product_blocked === true) return true;
  if (!ctx) return false;
  const amb = ctx.product_ambiguous_eligible;
  const pids =
    amb && typeof amb === 'object' && !Array.isArray(amb) && Array.isArray((amb as { product_ids?: unknown }).product_ids)
      ? (amb as { product_ids: unknown[] }).product_ids
      : [];
  const multi = new Set(pids.map((x) => Number(x)).filter((x) => x > 0)).size >= 2;
  return (
    multi &&
    (Boolean(ctx.receipt_disambiguation) ||
      Boolean(ctx.temporal_supersession) ||
      ctx.fifo_candidate === true ||
      ctx.product_running_change_received_both === true)
  );
}

export function dsiIgnoreReasonCodeLabel(code: string | null | undefined): string | null {
  if (!code) return null;
  if (code === 'ignore_sku_indeterminate') return 'Ignore — SKU indeterminate (received-both)';
  if (code === 'ignore_no_catalogue') return 'Ignore — no catalogue match';
  return code.replace(/_/g, ' ');
}
