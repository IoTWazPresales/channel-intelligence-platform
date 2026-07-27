'use client';

import Alert from '@mui/material/Alert';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';

export type DsiProductResolutionEvidenceContext = {
  unresolved_distributor_ids?: number[];
  dominant_unresolved_distributor_id?: number;
  dominant_evidence_month?: string;
  shipment_evidence_month_counts?: Record<string, number>;
  dsi_evidence_month_counts?: Record<string, number>;
  shipment_distinct_product_ids?: number[];
  shipment_cross_distributor_corroboration?: {
    distinct_resolved_product_ids?: number[];
    match_count?: number;
    evidence_month?: string;
    summary?: string;
    auto_resolve_blocked?: boolean;
  };
  receipt_disambiguation?: {
    status?: string;
    tier?: string;
    receipt_line_count?: number;
    receipt_product_ids?: number[];
    canonical_distributor_key?: string;
    sales_model_key?: string;
    scope?: string;
  };
  temporal_supersession?: {
    status?: string;
    fifo_candidate?: boolean;
    summary?: string;
    canonical_distributor_key?: string;
  };
  fifo_candidate?: boolean;
  product_resolution_quality?: {
    total_rows?: number;
    resolved_receipt_temporal?: number;
    indeterminate_rows?: number;
    ignored_rows?: number;
    quality_denominator?: number;
  };
  product_running_change_received_both?: boolean;
  weekly_model_grain_without_sku?: boolean;
  weekly_resolution_warnings?: string[];
};

function formatMonthCounts(counts: Record<string, number> | undefined): string {
  if (!counts || typeof counts !== 'object') return '';
  const entries = Object.entries(counts)
    .filter(([k]) => k.trim().length > 0)
    .sort(([a], [b]) => a.localeCompare(b));
  if (!entries.length) return '';
  return entries.map(([m, n]) => `${m}: ${n}`).join(', ');
}

export function DsiProductResolutionEvidenceCard({
  context,
}: {
  context: DsiProductResolutionEvidenceContext | null | undefined;
}) {
  if (!context || typeof context !== 'object') return null;

  const distIds = Array.isArray(context.unresolved_distributor_ids)
    ? context.unresolved_distributor_ids
    : [];
  const shipMonths = formatMonthCounts(context.shipment_evidence_month_counts);
  const dsiMonths = formatMonthCounts(context.dsi_evidence_month_counts);
  const cross = context.shipment_cross_distributor_corroboration;
  const receipt = context.receipt_disambiguation;
  const temporal = context.temporal_supersession;
  const fifo = context.fifo_candidate === true || temporal?.fifo_candidate === true;
  const quality = context.product_resolution_quality;
  const weekly = Boolean(context.weekly_model_grain_without_sku);

  const hasBody =
    distIds.length > 0 ||
    Boolean(shipMonths || dsiMonths) ||
    Boolean(cross) ||
    Boolean(receipt) ||
    Boolean(temporal) ||
    fifo ||
    Boolean(quality) ||
    weekly;

  if (!hasBody) return null;

  return (
    <Alert severity="info" sx={{ mt: 1 }} data-testid="dsi-product-resolution-evidence">
      <Typography variant="subtitle2" component="div" gutterBottom>
        Resolution evidence
      </Typography>
      <Stack spacing={0.5} component="div">
        {distIds.length > 0 ? (
          <Typography variant="caption" component="div">
            Distributors in unresolved rows: {distIds.join(', ')}
            {context.dominant_evidence_month ? ` · dominant month ${context.dominant_evidence_month}` : ''}
          </Typography>
        ) : null}
        {shipMonths ? (
          <Typography variant="caption" component="div">
            Shipment evidence rows by month: {shipMonths}
          </Typography>
        ) : null}
        {dsiMonths ? (
          <Typography variant="caption" component="div">
            DSI staging rows by month: {dsiMonths}
          </Typography>
        ) : null}
        {Array.isArray(context.shipment_distinct_product_ids) && context.shipment_distinct_product_ids.length > 0 ? (
          <Typography variant="caption" component="div">
            Shipment product ids (same month): {context.shipment_distinct_product_ids.join(', ')}
          </Typography>
        ) : null}
        {cross ? (
          <Typography variant="caption" component="div" color="warning.main">
            {cross.summary ||
              `Cross-distributor shipment evidence only (${cross.match_count ?? 0} lines); auto-resolve blocked.`}
            {Array.isArray(cross.distinct_resolved_product_ids) && cross.distinct_resolved_product_ids.length > 0
              ? ` Product ids: ${cross.distinct_resolved_product_ids.join(', ')}.`
              : ''}
          </Typography>
        ) : null}
        {receipt ? (
          <Typography variant="caption" component="div">
            Receipt: {receipt.status ?? receipt.tier ?? '—'}
            {typeof receipt.receipt_line_count === 'number' ? ` · ${receipt.receipt_line_count} lines` : ''}
            {Array.isArray(receipt.receipt_product_ids) && receipt.receipt_product_ids.length > 0
              ? ` · product ids ${receipt.receipt_product_ids.join(', ')}`
              : ''}
            {receipt.canonical_distributor_key ? ` · dist ${receipt.canonical_distributor_key}` : ''}
          </Typography>
        ) : null}
        {temporal ? (
          <Typography variant="caption" component="div">
            Temporal: {temporal.status ?? '—'}
            {temporal.summary ? ` — ${temporal.summary}` : ''}
          </Typography>
        ) : null}
        {fifo ? (
          <Typography variant="caption" component="div" color="warning.main">
            FIFO candidate — multiple date-feasible SKUs; steward must choose per date cluster.
          </Typography>
        ) : null}
        {quality && typeof quality.total_rows === 'number' && quality.total_rows > 0 ? (
          <Typography variant="caption" component="div">
            Quality: {quality.resolved_receipt_temporal ?? 0} of {quality.total_rows} receipt/temporal resolved
            {typeof quality.indeterminate_rows === 'number'
              ? ` · ${quality.indeterminate_rows} indeterminate`
              : ''}
            {typeof quality.ignored_rows === 'number' && quality.ignored_rows > 0
              ? ` · ${quality.ignored_rows} ignored (excluded from denominator)`
              : ''}
          </Typography>
        ) : null}
        {weekly ? (
          <Typography variant="caption" component="div" color="warning.main">
            Weekly import: product identifier is mapped to model/sales-model grain without a dedicated SKU column.
          </Typography>
        ) : null}
      </Stack>
    </Alert>
  );
}
