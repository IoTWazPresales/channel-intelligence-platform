'use client';

import { Alert, Box, Chip, Stack, Typography } from '@mui/material';

import {
  confidenceBand,
  confidenceBandColor,
  confidenceBandLabel,
} from '@/features/import-steward/confidenceBand';
import { formatPlanActionLabel, planTargetSummary } from '@/features/import-steward/dsiResolutionPlanDisplay';

import { DsiPendingButton } from './DsiPendingButton';
import {
  isShipmentCustomerEntity,
  isShipmentDistributorEntity,
  shipmentContextNeedsNameReview,
  shipmentContextParty,
  shipmentContextPossibleDuplicateOf,
  shipmentContextSpecialCategory,
  shipmentEntityChipLabel,
  shipmentSampleToken,
  shipmentSuggestedNameFromContext,
  type ShipmentMappingCandidateRow,
} from './shipmentMappingCandidateDisplay';
import { ShipmentCandidateDrawerActions } from './shipmentStewardRowActions';

export function ShipmentMappingStewardPanel({
  candidate,
  planRow,
  applyPlanPending,
  onApplyPlanRow,
  rowActionPending,
}: {
  candidate: ShipmentMappingCandidateRow;
  planRow?: Record<string, unknown> | null;
  applyPlanPending?: boolean;
  onApplyPlanRow?: (candidateId: number) => void;
  rowActionPending?: boolean;
}) {
  const ready = planRow?.ready === true;
  const suggestedAction =
    typeof planRow?.suggested_action === 'string' ? planRow.suggested_action : null;
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
              <DsiPendingButton
                size="small"
                variant="contained"
                pending={applyPlanPending}
                pendingLabel="Applying plan…"
                onClick={() => onApplyPlanRow(candidate.id)}
                data-testid="shipment-steward-apply-plan-row"
              >
                Apply plan for this row
              </DsiPendingButton>
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
        {rowActionPending ? (
          <>
            {' '}
            <Chip size="small" color="info" label="Saving…" data-testid="shipment-steward-row-saving" />
          </>
        ) : null}
      </Typography>

      <Stack spacing={0.5}>
        <Typography variant="body2">
          <strong>{shipmentSampleToken(candidate)}</strong>
        </Typography>
        {isShipmentDistributorEntity(candidate.entity_type) ? (
          <Typography variant="caption" color="text.secondary">
            Party: {shipmentContextParty(candidate.context)}
          </Typography>
        ) : null}
      </Stack>

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
      {isShipmentCustomerEntity(candidate.entity_type) &&
      shipmentContextPossibleDuplicateOf(candidate.context).length > 0 ? (
        <Alert severity="info" variant="outlined" data-testid="shipment-possible-duplicates">
          <Typography variant="body2">
            <strong>Similar tokens on this job:</strong>{' '}
            {shipmentContextPossibleDuplicateOf(candidate.context).join(', ')}
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
          {planConfidence != null ? (
            <Chip
              size="small"
              variant="outlined"
              color={confidenceBandColor(confidenceBand(planConfidence))}
              label={confidenceBandLabel(confidenceBand(planConfidence))}
            />
          ) : null}
        </Stack>
      ) : null}

      <Typography variant="body2" color="text.secondary">
        Suggested name: {shipmentSuggestedNameFromContext(candidate.context, shipmentSampleToken(candidate))}
      </Typography>

      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
        <ShipmentCandidateDrawerActions row={candidate} />
      </Stack>
    </Stack>
  );
}
