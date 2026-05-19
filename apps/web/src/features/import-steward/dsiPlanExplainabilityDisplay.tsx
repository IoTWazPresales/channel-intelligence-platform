'use client';

import { Chip, Stack, Typography } from '@mui/material';

export type DsiPlanWhy = {
  blockers?: string[];
  rule_path?: string;
  corroboration_hits?: Array<Record<string, unknown>>;
  narrative?: string;
};

export function formatPlanRulePathLabel(rulePath: string): string {
  return rulePath.replace(/\./g, ' → ').replace(/_/g, ' ');
}

export function planWhyCorroborationLabels(planWhy: DsiPlanWhy | null | undefined): string[] {
  if (!planWhy?.corroboration_hits?.length) return [];
  const labels: string[] = [];
  for (const hit of planWhy.corroboration_hits) {
    const marker = typeof hit.marker === 'string' ? hit.marker : '';
    if (marker === 'shipment_evidence_product') labels.push('Shipment evidence (product)');
    else if (marker === 'shipment_evidence_customer') labels.push('Shipment evidence (customer)');
    else if (marker === 'shipment_evidence_corroboration') {
      const n = hit.match_count;
      labels.push(typeof n === 'number' ? `Shipment corroboration (${n} lines)` : 'Shipment corroboration');
    } else if (marker) labels.push(marker.replace(/_/g, ' '));
  }
  return labels;
}

export function DsiPlanWhyPanel({ planWhy }: { planWhy: DsiPlanWhy | null | undefined }) {
  if (!planWhy) return null;
  const blockers = planWhy.blockers ?? [];
  const rulePath = (planWhy.rule_path || '').trim();
  const corrLabels = planWhyCorroborationLabels(planWhy);
  const narrative = (planWhy.narrative || '').trim();

  if (!blockers.length && !rulePath && !corrLabels.length && !narrative) return null;

  return (
    <Stack spacing={1} data-testid="dsi-plan-why-panel">
      <Typography variant="caption" color="text.secondary">
        Why this plan
      </Typography>
      {rulePath ? (
        <Typography variant="body2" data-testid="dsi-plan-why-rule-path">
          <strong>Rule:</strong> {formatPlanRulePathLabel(rulePath)}
        </Typography>
      ) : null}
      {narrative ? (
        <Typography variant="body2" color="text.secondary">
          {narrative}
        </Typography>
      ) : null}
      {blockers.length > 0 ? (
        <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
          {blockers.map((b) => (
            <Chip key={b} size="small" color="warning" variant="outlined" label={b} />
          ))}
        </Stack>
      ) : null}
      {corrLabels.length > 0 ? (
        <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
          {corrLabels.map((label) => (
            <Chip key={label} size="small" color="info" variant="outlined" label={label} />
          ))}
        </Stack>
      ) : null}
    </Stack>
  );
}

export function dsiCandidateCorroborationChipLabel(ctx: Record<string, unknown> | null | undefined): string | null {
  if (!ctx) return null;
  const markers = ctx.corroboration_markers;
  if (Array.isArray(markers) && markers.length > 0) {
    if (markers.includes('shipment_evidence_product')) return 'Shipment corroborated';
    if (markers.includes('shipment_evidence_customer')) return 'Shipment corroborated';
  }
  const sec = ctx.shipment_evidence_corroboration;
  if (sec && typeof sec === 'object' && !Array.isArray(sec)) {
    const n = (sec as Record<string, unknown>).best_match_count;
    if (typeof n === 'number' && n > 0) return `Shipment corroborated (${n})`;
    return 'Shipment corroborated';
  }
  return null;
}
