'use client';

import type { MouseEvent } from 'react';
import { Chip, CircularProgress, Stack, Typography } from '@mui/material';
import { DsiPendingButton } from '@/features/import-steward/DsiPendingButton';
import type { DsiCandidateRow, ImportStewardWorkspaceColumn } from '@/features/import-steward';
import {
  DSI_ENTITY_CUSTOMER,
  DSI_ENTITY_DISTRIBUTOR,
  DSI_ENTITY_PRODUCT,
  dsiEffectiveSuggestedAction,
} from '@/features/import-steward/dsiStewardCandidateFilterLogic';
import {
  dsiCandidateCorroborationChipLabel,
  formatPlanRulePathLabel,
  type DsiPlanWhy,
} from '@/features/import-steward/dsiPlanExplainabilityDisplay';
import {
  formatDsiRegionEvidenceDisplay,
  formatDsiRegionEvidenceTitle,
} from '@/features/import-steward/dsiRegionEvidenceDisplay';
import type { DsiRegionEvidenceDto } from '@/features/import-steward/dsiSteward.types';
import {
  inboundEvidenceContextNeedsNameReview,
  inboundEvidenceContextParty,
  inboundEvidenceContextPossibleDuplicateOf,
  inboundEvidenceContextSpecialCategory,
  inboundEvidenceHumanizeMatchReasonCaption,
  inboundEvidenceHumanizeSnakeTitle,
  inboundEvidenceSampleToken,
  inboundEvidenceSuggestedNameFromContext,
} from '@/features/import-steward/inboundEvidenceMappingCandidateDisplayUtils';

function dsiEntityChipLabel(entityType: string): string {
  if (entityType === DSI_ENTITY_CUSTOMER) return 'Channel partner';
  if (entityType === DSI_ENTITY_DISTRIBUTOR) return 'Distributor';
  if (entityType === DSI_ENTITY_PRODUCT) return 'Product';
  return entityType;
}

function dsiActionChipColor(action: string): 'success' | 'warning' | 'error' | 'default' {
  if (action === 'map_customer' || action === 'map_distributor' || action === 'resolve_product') return 'success';
  if (action === 'create_provisional_customer' || action === 'create_provisional_distributor') return 'warning';
  if (action === 'needs_review') return 'error';
  return 'default';
}

function strategicHint(ctx: Record<string, unknown> | null): boolean {
  return Boolean(ctx && ctx.strategic_channel_hint === true);
}

function DsiMatchCell({
  row,
  planRow,
}: {
  row: DsiCandidateRow;
  planRow?: Record<string, unknown>;
}) {
  const act = dsiEffectiveSuggestedAction(row, planRow);
  const mr = (row.match_reason || '').trim();
  const needsReview =
    act === 'needs_review' || ((!act || act === '') && (row.status || '').trim() === 'needs_review');
  const corrLabel = dsiCandidateCorroborationChipLabel(row.context);

  const corroborationChip =
    corrLabel != null ? (
      <Chip size="small" color="info" variant="outlined" label={corrLabel} data-testid="dsi-match-corroboration-chip" />
    ) : null;

  if (row.entity_type === DSI_ENTITY_PRODUCT) {
    const sum = row.context && typeof row.context.product_match_summary === 'string' ? row.context.product_match_summary.trim() : '';
    if (sum) {
      return (
        <Stack spacing={0.25} alignItems="flex-start">
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }} title={sum}>
            {sum}
          </Typography>
          {corroborationChip}
        </Stack>
      );
    }
    if (mr === 'no_alias_or_exact_dim_match' || !mr) {
      return (
        <Stack spacing={0.25} alignItems="flex-start">
          <Typography variant="body2" color="text.secondary">
            No match found
          </Typography>
          {corroborationChip}
        </Stack>
      );
    }
    return (
      <Stack spacing={0.25} alignItems="flex-start">
        <Typography variant="caption" color="text.secondary">
          {inboundEvidenceHumanizeSnakeTitle(mr)}
        </Typography>
        {corroborationChip}
      </Stack>
    );
  }

  if (row.entity_type === DSI_ENTITY_DISTRIBUTOR) {
    if (!mr) {
      return (
        <Stack spacing={0.25} alignItems="flex-start">
          <Typography variant="caption" color="text.secondary">
            —
          </Typography>
          {corroborationChip}
        </Stack>
      );
    }
    return (
      <Stack spacing={0.25} alignItems="flex-start">
        <Typography variant="caption" color="text.secondary">
          {inboundEvidenceHumanizeSnakeTitle(mr)}
        </Typography>
        {corroborationChip}
      </Stack>
    );
  }

  if (needsReview) {
    const cap = inboundEvidenceHumanizeMatchReasonCaption(row.match_reason);
    return (
      <Stack spacing={0.25} alignItems="flex-start">
        <Typography variant="body2">Needs review</Typography>
        {cap ? (
          <Typography variant="caption" color="text.secondary">
            {cap}
          </Typography>
        ) : null}
        {corroborationChip}
      </Stack>
    );
  }

  if (mr === 'no_alias_or_exact_dim_match') {
    return (
      <Stack spacing={0.25} alignItems="flex-start">
        <Typography variant="body2" color="text.secondary">
          No match found
        </Typography>
        {corroborationChip}
      </Stack>
    );
  }

  return (
    <Stack spacing={0.25} alignItems="flex-start">
      <Typography variant="caption" color="text.secondary">
        {inboundEvidenceHumanizeSnakeTitle(row.match_reason)}
      </Typography>
      {corroborationChip}
    </Stack>
  );
}

export type DsiResolutionWorkspaceColumnOptions = {
  planByCandidateId: Map<number, Record<string, unknown>>;
  formatPlanActionLabel: (action: string) => string;
  isTerminal: (row: DsiCandidateRow) => boolean;
  onFocusRow: (row: DsiCandidateRow) => void;
  onOpenPlanDrawer: (candidateId: number) => void;
  rowActionPendingId?: number | null;
};

export function buildDsiResolutionWorkspaceColumns(
  opts: DsiResolutionWorkspaceColumnOptions
): ImportStewardWorkspaceColumn<DsiCandidateRow>[] {
  const { planByCandidateId, formatPlanActionLabel, isTerminal, onFocusRow, onOpenPlanDrawer, rowActionPendingId } =
    opts;

  const cols: ImportStewardWorkspaceColumn<DsiCandidateRow>[] = [
    {
      id: 'type',
      header: 'Type',
      cell: (r) => <Chip size="small" label={dsiEntityChipLabel(r.entity_type)} variant="outlined" />,
    },
    {
      id: 'party',
      header: 'Party / scope',
      cell: (r) => (
        <Typography variant="body2">
          {r.entity_type === DSI_ENTITY_DISTRIBUTOR ? inboundEvidenceContextParty(r.context) : '—'}
        </Typography>
      ),
    },
    {
      id: 'token',
      header: 'Token (sample)',
      cellSx: { maxWidth: 260 },
      cell: (r) => {
        const tok = inboundEvidenceSampleToken(r.sample_raw_values, r.normalized_key);
        return (
          <>
            <Typography variant="body2" noWrap title={tok}>
              {tok}
            </Typography>
            <Typography variant="caption" color="text.secondary" display="block" noWrap title={r.normalized_key}>
              key: {r.normalized_key}
            </Typography>
          </>
        );
      },
    },
    {
      id: 'rows',
      header: 'Rows',
      align: 'right',
      cell: (r) => r.row_count,
    },
    {
      id: 'qty_value',
      header: 'Qty / value',
      align: 'right',
      cell: (r) => (
        <Typography variant="caption" display="block">
          {r.total_units ?? '—'} / {r.total_reported_value ?? '—'}
        </Typography>
      ),
    },
    {
      id: 'suggested',
      header: 'Suggested',
      cell: (r) => {
        const tok = inboundEvidenceSampleToken(r.sample_raw_values, r.normalized_key);
        const ctx = r.context;
        return (
          <Stack spacing={0.5} alignItems="flex-start">
            <Typography variant="body2">{inboundEvidenceSuggestedNameFromContext(ctx, tok)}</Typography>
            {r.entity_type === DSI_ENTITY_CUSTOMER && inboundEvidenceContextSpecialCategory(ctx) === 'noise_only' ? (
              <Chip size="small" color="secondary" variant="outlined" label="Special category" />
            ) : null}
            {r.entity_type === DSI_ENTITY_CUSTOMER && inboundEvidenceContextSpecialCategory(ctx) === 'internal_note' ? (
              <Chip size="small" color="info" variant="outlined" label="Internal note" />
            ) : null}
            {r.entity_type === DSI_ENTITY_CUSTOMER && inboundEvidenceContextPossibleDuplicateOf(ctx).length > 0 ? (
              <Typography variant="caption" color="text.secondary">
                Similar to: {inboundEvidenceContextPossibleDuplicateOf(ctx).join(', ')}
              </Typography>
            ) : null}
            {r.entity_type === DSI_ENTITY_CUSTOMER && inboundEvidenceContextNeedsNameReview(ctx) ? (
              <Chip size="small" color="warning" variant="outlined" label="Verify name" />
            ) : null}
            {strategicHint(ctx) ? (
              <Chip size="small" color="warning" variant="outlined" label="Strategic hint" />
            ) : null}
            {r.entity_type === DSI_ENTITY_PRODUCT &&
            ctx &&
            typeof ctx.product_match_summary === 'string' &&
            ctx.product_match_summary.trim() ? (
              <Typography variant="caption" color="text.secondary" noWrap sx={{ maxWidth: 200 }}>
                {ctx.product_match_summary.trim()}
              </Typography>
            ) : null}
          </Stack>
        );
      },
    },
    {
      id: 'plan',
      header: 'Plan',
      cell: (r) => {
        const pr = planByCandidateId.get(r.id);
        const act = dsiEffectiveSuggestedAction(r, pr);
        const conf =
          pr && typeof pr.confidence === 'number'
            ? pr.confidence
            : r.confidence_score != null
              ? r.confidence_score
              : null;
        const planWhy = pr?.plan_why as DsiPlanWhy | undefined;
        const ruleHint =
          planWhy?.rule_path && String(planWhy.rule_path).trim()
            ? formatPlanRulePathLabel(String(planWhy.rule_path))
            : null;
        return (
          <Stack
            spacing={0.5}
            alignItems="flex-start"
            onClick={(e) => {
              e.stopPropagation();
              onOpenPlanDrawer(r.id);
            }}
            sx={{ cursor: 'pointer' }}
            data-testid={`dsi-plan-cell-${r.id}`}
          >
            {act ? (
              <Chip size="small" label={formatPlanActionLabel(act)} color={dsiActionChipColor(act)} />
            ) : pr?.ready === true ? (
              <Chip size="small" label="Ready" color="success" variant="outlined" />
            ) : null}
            {conf != null ? (
              <Typography variant="caption" color="text.secondary">
                score {conf.toFixed(2)}
              </Typography>
            ) : null}
            {ruleHint ? (
              <Typography variant="caption" color="text.secondary" data-testid={`dsi-plan-rule-hint-${r.id}`}>
                {ruleHint}
              </Typography>
            ) : null}
            {(planWhy?.blockers?.length ?? 0) > 0 ? (
              <Typography variant="caption" color="warning.main">
                {planWhy!.blockers!.join(', ')}
              </Typography>
            ) : null}
            {(() => {
              if (r.entity_type !== DSI_ENTITY_CUSTOMER || !pr?.region_evidence) return null;
              const regionDisplay = formatDsiRegionEvidenceDisplay(
                pr.region_evidence as DsiRegionEvidenceDto
              );
              if (!regionDisplay) return null;
              return (
                <Stack spacing={0} data-testid={`dsi-region-evidence-${r.id}`}>
                  <Typography
                    variant="caption"
                    color={regionDisplay.kind === 'fallback' ? 'text.secondary' : 'info.main'}
                    title={formatDsiRegionEvidenceTitle(pr.region_evidence as DsiRegionEvidenceDto)}
                  >
                    {regionDisplay.line}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {regionDisplay.sourceLabel}
                  </Typography>
                </Stack>
              );
            })()}
          </Stack>
        );
      },
    },
    {
      id: 'match',
      header: 'Match',
      cellSx: { maxWidth: 220 },
      cell: (r) => <DsiMatchCell row={r} planRow={planByCandidateId.get(r.id)} />,
    },
    {
      id: 'actions',
      header: 'Actions',
      align: 'right',
      cell: (r) => (
        <DsiRowActions
          row={r}
          terminal={isTerminal(r)}
          pending={rowActionPendingId === r.id}
          onFocusRow={onFocusRow}
        />
      ),
    },
  ];

  return cols;
}

function DsiRowActions({
  row,
  terminal,
  pending,
  onFocusRow,
}: {
  row: DsiCandidateRow;
  terminal: boolean;
  pending?: boolean;
  onFocusRow: (row: DsiCandidateRow) => void;
}) {
  const isProduct = row.entity_type === DSI_ENTITY_PRODUCT;
  const isCustomer = row.entity_type === DSI_ENTITY_CUSTOMER;
  const stop = (fn: () => void) => (ev: MouseEvent) => {
    ev.stopPropagation();
    fn();
  };

  if (pending) {
    return (
      <Stack direction="row" spacing={0.5} alignItems="center" justifyContent="flex-end">
        <CircularProgress size={16} />
        <Typography variant="caption" color="text.secondary" data-testid={`dsi-row-action-pending-${row.id}`}>
          Saving…
        </Typography>
      </Stack>
    );
  }

  return (
    <Stack direction="row" spacing={0.5} justifyContent="flex-end" flexWrap="wrap" useFlexGap>
      <DsiPendingButton size="small" variant="outlined" disabled={terminal} onClick={stop(() => onFocusRow(row))}>
        {isProduct ? 'Resolve…' : 'Map…'}
      </DsiPendingButton>
      {!isProduct ? (
        <DsiPendingButton size="small" variant="outlined" disabled={terminal} onClick={stop(() => onFocusRow(row))}>
          Provisional…
        </DsiPendingButton>
      ) : null}
      {isCustomer ? (
        <DsiPendingButton
          size="small"
          variant="outlined"
          color="warning"
          disabled={terminal}
          onClick={stop(() => onFocusRow(row))}
          data-testid={`dsi-action-open-channel-inline-${row.id}`}
        >
          Open…
        </DsiPendingButton>
      ) : null}
      <DsiPendingButton
        size="small"
        variant="outlined"
        color="error"
        disabled={terminal}
        onClick={stop(() => onFocusRow(row))}
      >
        Reject…
      </DsiPendingButton>
    </Stack>
  );
}
