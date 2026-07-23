'use client';

import { Alert, Chip, Stack } from '@mui/material';
import type { UseMutationResult, UseQueryResult } from '@tanstack/react-query';

import { safeDisplayError } from '@/lib/api';

import { StewardPendingButton } from './StewardPendingButton';

type ShipmentPlanToolbarSlice = {
  candidatesCount: number;
  planByCandidateId: Map<number, Record<string, unknown>>;
  readyPlanCandidateIds: number[];
  suggestionsQuery: UseQueryResult<Record<string, unknown>>;
  applyResolutionPlan: UseMutationResult<unknown, Error, number[]>;
  applyAllConfirmOpen: boolean;
  setApplyAllConfirmOpen: (open: boolean) => void;
};

/** Compact plan controls above shipment steward tabs (DSI parity). */
export function ShipmentResolutionPlanToolbar(plan: ShipmentPlanToolbarSlice) {
  const { candidatesCount, planByCandidateId, readyPlanCandidateIds, suggestionsQuery, applyResolutionPlan } = plan;

  const planComputing =
    candidatesCount > 0 && suggestionsQuery.fetchStatus === 'fetching' && !suggestionsQuery.data;

  const readyCount = readyPlanCandidateIds.length;

  return (
    <Stack spacing={1} data-testid="shipment-resolution-plan-toolbar">
      <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" alignItems="center">
        <StewardPendingButton
          variant="outlined"
          size="small"
          pending={suggestionsQuery.isFetching}
          pendingLabel="Computing plan…"
          disabled={candidatesCount === 0}
          onClick={() => void suggestionsQuery.refetch().catch(() => {})}
          data-testid="shipment-resolution-plan-refresh"
        >
          Refresh plan
        </StewardPendingButton>
        <Chip size="small" label={`Candidates ${candidatesCount}`} />
        <Chip size="small" color="success" variant="outlined" label={`Ready ${readyCount}`} />
        <StewardPendingButton
          variant="contained"
          size="small"
          pending={applyResolutionPlan.isPending}
          pendingLabel="Applying…"
          disabled={readyCount === 0 || planComputing || applyResolutionPlan.isPending}
          onClick={() => plan.setApplyAllConfirmOpen(true)}
          data-testid="shipment-resolution-plan-apply-all"
        >
          Apply all ready ({readyCount})
        </StewardPendingButton>
      </Stack>
      {planComputing ? (
        <Alert severity="info" data-testid="shipment-resolution-plan-loading">
          Computing resolution plan for the current page of candidates…
        </Alert>
      ) : null}
      {suggestionsQuery.isError ? (
        <Alert severity="error">{safeDisplayError(suggestionsQuery.error)}</Alert>
      ) : null}
    </Stack>
  );
}
