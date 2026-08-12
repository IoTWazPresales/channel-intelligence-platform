'use client';

import { Alert, Box, Chip, Stack, Typography } from '@mui/material';
import { useMutation } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';

import {
  confidenceBand,
  confidenceBandColor,
  confidenceBandLabel,
} from '@/features/import-steward/confidenceBand';
import { formatPlanActionLabel, planTargetSummary } from '@/features/import-steward/stewardResolutionPlanDisplay';
import { StewardEvidenceSummary } from '@/features/import-steward/StewardEvidenceSummary';
import {
  StewardSuggestionCards,
  type StewardSuggestionCardItem,
} from '@/features/import-steward/StewardSuggestionCards';
import { StewardPendingButton } from '@/features/import-steward/StewardPendingButton';
import { apiPost, safeDisplayError } from '@/lib/api';
import {
  isShipmentCustomerEntity,
  isShipmentDistributorEntity,
  shipmentContextNeedsNameReview,
  shipmentContextParty,
  shipmentContextPossibleDuplicateOf,
  shipmentContextSpecialCategory,
  shipmentDuplicateReviewDecision,
  shipmentEntityChipLabel,
  shipmentHasUnresolvedDuplicateReview,
  shipmentSampleToken,
  shipmentSuggestedNameFromContext,
  type ShipmentMappingCandidateRow,
} from './shipmentMappingCandidateDisplay';
import { ShipmentCandidateDrawerActions } from './shipmentStewardRowActions';

function isExistingMasterMapAction(action: string | null): boolean {
  if (!action) return false;
  return action.startsWith('map_') || action === 'map_customer' || action === 'map_distributor';
}

export function ShipmentMappingStewardPanel({
  candidate,
  planRow,
  applyPlanPending,
  onApplyPlanRow,
  rowActionPending,
  onRowActionStart,
  onRowActionEnd,
  onInvalidate,
  onStewardFastComplete,
  lookupPeerCandidate,
  onOpenPeerByNormalizedKey,
}: {
  candidate: ShipmentMappingCandidateRow;
  planRow?: Record<string, unknown> | null;
  applyPlanPending?: boolean;
  onApplyPlanRow?: (candidateId: number) => void;
  rowActionPending?: boolean;
  onRowActionStart?: (candidateId: number) => void;
  onRowActionEnd?: () => void;
  /** Refresh candidate list after duplicate same-entity stamp (row stays actionable). */
  onInvalidate?: () => void;
  /** Evict after different-entity ack (status acknowledged_unique). */
  onStewardFastComplete?: (candidateIds: number[]) => void;
  lookupPeerCandidate?: (normalizedKey: string) => ShipmentMappingCandidateRow | null;
  onOpenPeerByNormalizedKey?: (normalizedKey: string) => void;
}) {
  const ready = planRow?.ready === true;
  const suggestedAction =
    typeof planRow?.suggested_action === 'string' ? planRow.suggested_action : null;
  const suggestedTargetId =
    planRow?.suggested_target_id != null && Number.isFinite(Number(planRow.suggested_target_id))
      ? Number(planRow.suggested_target_id)
      : null;
  const planConfidence =
    typeof planRow?.confidence === 'number'
      ? planRow.confidence
      : candidate.confidence_score != null
        ? candidate.confidence_score
        : null;
  const histRes =
    planRow && typeof planRow.historical_resolution === 'object' && planRow.historical_resolution !== null
      ? (planRow.historical_resolution as Record<string, unknown>)
      : null;
  const blockers = Array.isArray(planRow?.resolution_blockers)
    ? (planRow.resolution_blockers as string[])
    : [];

  const dupHints = shipmentContextPossibleDuplicateOf(candidate.context);
  const dupDecision = shipmentDuplicateReviewDecision(candidate.context);
  const dupUnresolved =
    isShipmentCustomerEntity(candidate.entity_type) && shipmentHasUnresolvedDuplicateReview(candidate.context);
  const ownKey = (candidate.normalized_key || '').trim();
  const dupPeerHintsExcludingSelf = useMemo(
    () => dupHints.filter((k) => k.trim() !== ownKey),
    [dupHints, ownKey]
  );
  const [dupPeerKey, setDupPeerKey] = useState(dupPeerHintsExcludingSelf[0] ?? '');
  const [dupMsg, setDupMsg] = useState<string | null>(null);

  useEffect(() => {
    setDupPeerKey(dupPeerHintsExcludingSelf[0] ?? '');
    setDupMsg(null);
  }, [candidate.id, dupPeerHintsExcludingSelf]);

  const duplicateLifecycle = {
    onMutate: async () => {
      onRowActionStart?.(candidate.id);
    },
    onSettled: () => {
      onRowActionEnd?.();
    },
  };

  const duplicateDifferentEntity = useMutation({
    mutationFn: (body: { peer_normalized_key: string; audit_note?: string }) =>
      apiPost<{ ok: boolean; candidate_id?: number }>(
        `/api/v1/shipment-evidence/import-candidates/${candidate.id}/duplicate-review/different-entity`,
        body
      ),
    ...duplicateLifecycle,
    onSuccess: (data) => {
      setDupMsg('Confirmed different entity — duplicate review recorded.');
      const id = data.candidate_id ?? candidate.id;
      onStewardFastComplete?.([id]);
      onInvalidate?.();
    },
  });

  const duplicateSameEntity = useMutation({
    mutationFn: (body: { peer_normalized_key: string; audit_note?: string }) =>
      apiPost<{ ok: boolean; message?: string }>(
        `/api/v1/shipment-evidence/import-candidates/${candidate.id}/duplicate-review/same-entity`,
        body
      ),
    ...duplicateLifecycle,
    onSuccess: (data) => {
      setDupMsg(
        typeof data.message === 'string' && data.message.trim()
          ? data.message
          : 'Marked same entity — map both tokens to the same master customer when ready.'
      );
      // Same-entity only stamps review — keep Map/plan actionable; refresh context only.
      onInvalidate?.();
    },
  });

  const dupBusy = duplicateDifferentEntity.isPending || duplicateSameEntity.isPending;

  const suggestionCards: StewardSuggestionCardItem[] = useMemo(() => {
    if (!isExistingMasterMapAction(suggestedAction) || suggestedTargetId == null) return [];
    const label = planTargetSummary(
      suggestedAction!,
      suggestedTargetId,
      candidate as unknown as Record<string, unknown>,
      planRow ?? undefined
    );
    return [
      {
        targetId: suggestedTargetId,
        label,
        score: planConfidence,
        reason: typeof planRow?.reason === 'string' ? planRow.reason : suggestedAction,
        onMap: () => {
          onApplyPlanRow?.(candidate.id);
        },
        mapPending: Boolean(applyPlanPending),
        mapDisabled: !ready || !onApplyPlanRow || Boolean(applyPlanPending),
      },
    ];
  }, [
    suggestedAction,
    suggestedTargetId,
    candidate,
    planRow,
    planConfidence,
    onApplyPlanRow,
    applyPlanPending,
    ready,
  ]);

  return (
    <Stack spacing={2} data-testid="shipment-mapping-steward-panel">
      <Alert severity="info">
        Provisional records are created as <strong>unverified</strong> and editable. Map tokens to existing master
        records when the plan agrees, or create provisional channel partners / distributors when no match exists.
      </Alert>

      {ready && suggestedAction && suggestedAction !== 'none' ? (
        <Alert severity="success" variant="outlined" data-testid="shipment-plan-ready-banner">
          <Typography variant="body2">
            <strong>Resolution plan ready:</strong>{' '}
            {planTargetSummary(
              suggestedAction,
              planRow?.suggested_target_id,
              candidate as unknown as Record<string, unknown>,
              planRow ?? undefined
            )}
          </Typography>
          {typeof planRow?.reason === 'string' && planRow.reason.trim() ? (
            <Typography variant="caption" component="div" sx={{ mt: 0.5 }}>
              {planRow.reason}
            </Typography>
          ) : null}
          {onApplyPlanRow ? (
            <Box sx={{ mt: 1 }}>
              <StewardPendingButton
                size="small"
                variant="contained"
                pending={applyPlanPending}
                pendingLabel="Applying plan…"
                onClick={() => onApplyPlanRow(candidate.id)}
                data-testid="shipment-steward-apply-plan-row"
              >
                Apply plan for this row
              </StewardPendingButton>
            </Box>
          ) : null}
        </Alert>
      ) : null}

      {!ready && histRes ? (
        <Alert severity="warning" variant="outlined" data-testid="shipment-historical-resolution">
          <Typography variant="body2">
            <strong>Previously resolved</strong> on import job {String(histRes.import_job_id ?? '—')} → customer{' '}
            {String(histRes.customer_id ?? '—')}
            {typeof histRes.confidence === 'number'
              ? ` (${Math.round(Number(histRes.confidence) * 100)}% confidence)`
              : ''}
            . Review before applying — current scorer disagrees or needs confirmation.
          </Typography>
        </Alert>
      ) : null}

      {!ready && blockers.length > 0 && !histRes ? (
        <Alert severity="warning" variant="outlined" data-testid="shipment-plan-blockers">
          <Typography variant="body2" component="div">
            <strong>Plan not ready:</strong>
            <ul style={{ margin: '4px 0 0', paddingLeft: 20 }}>
              {blockers.map((b) => (
                <li key={b}>{b.replace(/_/g, ' ')}</li>
              ))}
            </ul>
          </Typography>
        </Alert>
      ) : null}

      <Typography variant="body2">
        <strong>Selected:</strong> {shipmentEntityChipLabel(candidate.entity_type)} · normalized:{' '}
        {candidate.normalized_key} · status {candidate.status}
        {rowActionPending || dupBusy ? (
          <>
            {' '}
            <Chip size="small" color="info" label="Saving…" data-testid="shipment-steward-row-saving" />
          </>
        ) : null}
      </Typography>

      {isShipmentDistributorEntity(candidate.entity_type) ? (
        <Typography variant="caption" color="text.secondary">
          Party: {shipmentContextParty(candidate.context)}
        </Typography>
      ) : null}

      <StewardEvidenceSummary
        sampleRawValues={candidate.sample_raw_values}
        affectedRowCount={candidate.row_count}
        totalUnits={candidate.total_units}
        totalReportedValue={candidate.total_reported_value}
        testId="shipment-drawer-evidence"
        extras={
          <Typography variant="body2" color="text.secondary">
            Suggested name:{' '}
            {shipmentSuggestedNameFromContext(candidate.context, shipmentSampleToken(candidate))}
          </Typography>
        }
      />

      {isShipmentCustomerEntity(candidate.entity_type) && shipmentContextNeedsNameReview(candidate.context) ? (
        <Chip size="small" color="warning" variant="outlined" label="Verify name" />
      ) : null}
      {isShipmentCustomerEntity(candidate.entity_type) && shipmentContextSpecialCategory(candidate.context) ? (
        <Chip
          size="small"
          color="secondary"
          variant="outlined"
          label={`Special: ${shipmentContextSpecialCategory(candidate.context)}`}
        />
      ) : null}
      {isShipmentCustomerEntity(candidate.entity_type) && dupHints.length > 0 ? (
        <Alert
          severity={dupUnresolved ? 'warning' : 'info'}
          variant="outlined"
          data-testid="shipment-possible-duplicates"
        >
          <Typography variant="body2" component="div">
            <strong>Possible duplicates</strong> (same import job, name similarity after normalisation):
            <ul style={{ margin: '4px 0 0', paddingLeft: 20 }}>
              {dupHints.map((nk) => (
                <li key={nk}>
                  <code>{nk}</code>
                  {lookupPeerCandidate?.(nk) ? (
                    <>
                      {' '}
                      <Typography
                        component="button"
                        type="button"
                        variant="caption"
                        sx={{
                          border: 0,
                          bgcolor: 'transparent',
                          color: 'primary.main',
                          cursor: 'pointer',
                          textDecoration: 'underline',
                          p: 0,
                        }}
                        onClick={() => onOpenPeerByNormalizedKey?.(nk)}
                        data-testid="shipment-duplicate-peer-open"
                      >
                        Open peer
                      </Typography>
                    </>
                  ) : null}
                </li>
              ))}
            </ul>
            {dupDecision ? (
              <Typography variant="caption" display="block" sx={{ mt: 1 }}>
                Steward decision: <strong>{dupDecision.replace(/_/g, ' ')}</strong>
              </Typography>
            ) : null}
            {dupUnresolved ? (
              <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mt: 1.5 }}>
                <StewardPendingButton
                  size="small"
                  variant="contained"
                  pending={duplicateSameEntity.isPending}
                  pendingLabel="Saving…"
                  disabled={dupBusy || rowActionPending || !dupPeerKey.trim()}
                  onClick={() =>
                    void duplicateSameEntity.mutateAsync({ peer_normalized_key: dupPeerKey.trim() })
                  }
                  data-testid="shipment-duplicate-same-entity"
                >
                  Same entity
                </StewardPendingButton>
                <StewardPendingButton
                  size="small"
                  variant="outlined"
                  pending={duplicateDifferentEntity.isPending}
                  pendingLabel="Saving…"
                  disabled={dupBusy || rowActionPending || !dupPeerKey.trim()}
                  onClick={() =>
                    void duplicateDifferentEntity.mutateAsync({
                      peer_normalized_key: dupPeerKey.trim(),
                    })
                  }
                  data-testid="shipment-duplicate-different-entity"
                >
                  Different entity
                </StewardPendingButton>
              </Stack>
            ) : null}
            {dupMsg ? (
              <Typography variant="caption" display="block" sx={{ mt: 1 }} data-testid="shipment-duplicate-success">
                {dupMsg}
              </Typography>
            ) : null}
            {(duplicateSameEntity.isError || duplicateDifferentEntity.isError) && (
              <Typography variant="caption" color="error" display="block" sx={{ mt: 1 }}>
                {safeDisplayError(duplicateSameEntity.error || duplicateDifferentEntity.error)}
              </Typography>
            )}
          </Typography>
        </Alert>
      ) : null}

      {suggestedAction ? (
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
          <Typography variant="caption" color="text.secondary">
            Plan:
          </Typography>
          <Chip
            size="small"
            label={formatPlanActionLabel(suggestedAction)}
            color={ready ? 'success' : 'default'}
            variant="outlined"
          />
          {planConfidence != null && confidenceBand(planConfidence) ? (
            <Chip
              size="small"
              variant="outlined"
              color={confidenceBandColor(confidenceBand(planConfidence)!)}
              label={confidenceBandLabel(confidenceBand(planConfidence)!)}
            />
          ) : null}
        </Stack>
      ) : null}

      <StewardSuggestionCards
        suggestions={suggestionCards}
        testId="shipment-suggestion"
        emptyMessage="No ranked master suggestion for this row. Use Map / provisional actions below — never auto-created."
        mapLabel="Apply plan map"
        mapPendingLabel="Applying…"
        overrideSlot={
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap data-testid="shipment-drawer-override-actions">
            <ShipmentCandidateDrawerActions row={candidate} />
          </Stack>
        }
      />
    </Stack>
  );
}
