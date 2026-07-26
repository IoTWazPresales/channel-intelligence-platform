'use client';

import type { ReactNode } from 'react';
import { Chip, Stack, Typography } from '@mui/material';

import type { ImportStewardWorkspaceColumn } from '@/features/import-steward/importStewardCandidateWorkspace.types';
import { dsiEffectiveSuggestedAction } from '@/features/import-steward/dsiStewardCandidateFilterLogic';
import { formatPlanActionLabel } from '@/features/import-steward/dsiResolutionPlanDisplay';
import {
  buildInboundEvidenceMappingCandidateWorkspaceColumns,
  type InboundEvidenceMappingCandidateRow,
} from '@/features/import-steward/inboundEvidenceMappingCandidateWorkspaceColumns';
import {
  SHIPMENT_ENTITY_CUSTOMER,
  SHIPMENT_ENTITY_DISTRIBUTOR,
} from './shipmentStewardCandidateFilterLogic';

function shipmentActionChipColor(action: string): 'success' | 'warning' | 'error' | 'default' {
  if (action === 'map_customer' || action === 'map_distributor') return 'success';
  if (action === 'create_provisional_customer' || action === 'create_provisional_distributor') return 'warning';
  if (action === 'needs_review') return 'error';
  return 'default';
}

export type ShipmentResolutionWorkspaceColumnOptions = {
  planByCandidateId: Map<number, Record<string, unknown>>;
  renderActionsCell?: (row: InboundEvidenceMappingCandidateRow) => ReactNode;
};

/** Plan-aware steward columns for shipment import job resolution (DSI parity). */
export function buildShipmentResolutionWorkspaceColumns(
  opts: ShipmentResolutionWorkspaceColumnOptions
): ImportStewardWorkspaceColumn<InboundEvidenceMappingCandidateRow>[] {
  const base = buildInboundEvidenceMappingCandidateWorkspaceColumns({
    renderActionsCell: opts.renderActionsCell,
  }).filter((c) => c.id !== 'plan');

  const planCol: ImportStewardWorkspaceColumn<InboundEvidenceMappingCandidateRow> = {
    id: 'plan',
    header: 'Plan',
    cell: (r) => {
      const pr = opts.planByCandidateId.get(r.id);
      const slice = {
        ...r,
        entity_type:
          r.entity_type === SHIPMENT_ENTITY_DISTRIBUTOR || r.entity_type === 'distributor_token'
            ? 'distributor_token'
            : r.entity_type === SHIPMENT_ENTITY_CUSTOMER || r.entity_type === 'customer_dealer_token'
              ? 'customer_dealer_token'
              : r.entity_type,
      };
      const act = dsiEffectiveSuggestedAction(slice, pr);
      const ready = pr?.ready === true;
      const conf =
        pr && typeof pr.confidence === 'number'
          ? pr.confidence
          : r.confidence_score != null
            ? r.confidence_score
            : null;
      return (
        <Stack spacing={0.5} alignItems="flex-start">
          {act ? (
            <Chip size="small" label={formatPlanActionLabel(act)} color={shipmentActionChipColor(act)} />
          ) : null}
          {ready ? <Chip size="small" color="success" variant="outlined" label="Ready" /> : null}
          {conf != null ? (
            <Typography variant="caption" color="text.secondary">
              score {Number(conf).toFixed(2)}
            </Typography>
          ) : null}
        </Stack>
      );
    },
  };

  const matchIdx = base.findIndex((c) => c.id === 'match');
  if (matchIdx >= 0) {
    return [...base.slice(0, matchIdx), planCol, ...base.slice(matchIdx)];
  }
  return [...base, planCol];
}
