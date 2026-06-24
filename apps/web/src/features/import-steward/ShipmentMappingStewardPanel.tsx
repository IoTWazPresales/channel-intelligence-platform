'use client';

import { Alert, Chip, Stack, Typography } from '@mui/material';

import {
  confidenceBand,
  confidenceBandColor,
  confidenceBandLabel,
} from '@/features/import-steward/confidenceBand';

import {
  shipmentContextNeedsNameReview,
  shipmentContextParty,
  shipmentContextPossibleDuplicateOf,
  shipmentContextSpecialCategory,
  shipmentEntityChipLabel,
  shipmentSuggestedNameFromContext,
  SHIPMENT_ENTITY_CUST,
  type ShipmentMappingCandidateRow,
} from './shipmentMappingCandidateDisplay';
import { ShipmentCandidateInlineActions } from './shipmentStewardRowActions';

export function ShipmentMappingStewardPanel({
  candidate,
  planRow,
}: {
  candidate: ShipmentMappingCandidateRow;
  planRow?: Record<string, unknown> | null;
}) {
  const ready = planRow?.ready === true;
  const suggestedAction = typeof planRow?.suggested_action === 'string' ? planRow.suggested_action : null;

  return (
    <Stack spacing={2} data-testid="shipment-mapping-steward-panel">
      <Alert severity="info" variant="outlined">
        Map or create provisional records to resolve tokens on evidence lines. Actions write through the same
        shipment-evidence steward API as the legacy panel.
      </Alert>

      <Stack spacing={0.5}>
        <Typography variant="subtitle2">
          {shipmentEntityChipLabel(candidate.entity_type)} · #{candidate.id}
        </Typography>
        <Typography variant="body2">
          <strong>{shipmentSampleToken(candidate)}</strong>
        </Typography>
        <Typography variant="caption" color="text.secondary">
          key: {candidate.normalized_key}
        </Typography>
        {candidate.entity_type === SHIPMENT_ENTITY_DIST ? (
          <Typography variant="caption" color="text.secondary">
            Party: {shipmentContextParty(candidate.context)}
          </Typography>
        ) : null}
      </Stack>

      {candidate.entity_type === SHIPMENT_ENTITY_CUST && shipmentContextNeedsNameReview(candidate.context) ? (
        <Chip size="small" color="warning" variant="outlined" label="Verify name" />
      ) : null}
      {candidate.entity_type === SHIPMENT_ENTITY_CUST && shipmentContextSpecialCategory(candidate.context) ? (
        <Chip size="small" color="secondary" variant="outlined" label={`Special: ${shipmentContextSpecialCategory(candidate.context)}`} />
      ) : null}
      {candidate.entity_type === SHIPMENT_ENTITY_CUST && shipmentContextPossibleDuplicateOf(candidate.context).length > 0 ? (
        <Typography variant="caption" color="text.secondary">
          Similar to: {shipmentContextPossibleDuplicateOf(candidate.context).join(', ')}
        </Typography>
      ) : null}

      {suggestedAction ? (
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
          <Typography variant="caption" color="text.secondary">
            Plan:
          </Typography>
          <Chip size="small" label={suggestedAction} color={ready ? 'success' : 'default'} variant="outlined" />
          {candidate.confidence_score != null ? (
            <Chip
              size="small"
              variant="outlined"
              color={confidenceBandColor(confidenceBand(candidate.confidence_score))}
              label={confidenceBandLabel(confidenceBand(candidate.confidence_score))}
            />
          ) : null}
        </Stack>
      ) : null}

      <Typography variant="body2" color="text.secondary">
        Suggested name: {shipmentSuggestedNameFromContext(candidate.context, shipmentSampleToken(candidate))}
      </Typography>

      <ShipmentCandidateInlineActions row={candidate} />
    </Stack>
  );
}
