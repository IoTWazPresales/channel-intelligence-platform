'use client';

import MoreVertIcon from '@mui/icons-material/MoreVert';
import {
  Alert,
  Box,
  Checkbox,
  Chip,
  FormControlLabel,
  IconButton,
  Menu,
  MenuItem,
  Stack,
  Typography,
} from '@mui/material';
import type { UseMutationResult, UseQueryResult } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { useState } from 'react';

import { safeDisplayError } from '@/lib/api';

import { StewardPendingButton } from './StewardPendingButton';
import type { StewardResolutionPlanTestIds } from './stewardEngine.types';

/** Core plan slice — domain-neutral controls. */
export type StewardResolutionPlanToolbarSlice = {
  candidatesCount: number;
  readyCount?: number;
  suggestionsQuery: UseQueryResult<Record<string, unknown>>;
};

/** DSI extras for optional slots (summary chips, options menu, effective refresh). */
export type StewardResolutionPlanToolbarDsiExtras = {
  resolutionPlan: Record<string, unknown> | null;
  planGlobalSuspicious: boolean;
  setPlanGlobalSuspicious: (v: boolean) => void;
  planLoadToken: number;
  planTableRows: Array<Record<string, unknown>>;
  refreshPlanEffective: UseMutationResult<
    Record<string, unknown>,
    Error,
    { overrides: Array<Record<string, unknown>>; globalSuspicious: boolean }
  >;
  overridesPayload: () => Array<Record<string, unknown>>;
};

export type StewardResolutionPlanToolbarCopy = {
  refreshLabel?: string;
  refreshPendingLabel?: string;
  computingMessage?: string;
  refreshingMessage?: string;
};

/**
 * Compact plan controls above steward tabs.
 * Core: refresh + optional candidates/ready chips + optional apply-all + alerts.
 * DSI extras (summary chips, options menu) via optional slots — absent = absent UI.
 */
export function StewardResolutionPlanToolbar({
  plan,
  testIds,
  copy,
  onApplyAllReady,
  applyAllPending,
  applyAllDisabled,
  applyAllLabel,
  applyAllTestId,
  summaryChipsSlot,
  planOptionsSlot,
  dsiExtras,
}: {
  plan: StewardResolutionPlanToolbarSlice;
  testIds: StewardResolutionPlanTestIds;
  copy?: StewardResolutionPlanToolbarCopy;
  /** When set, renders Apply all ready in the plan toolbar (shipment placement). */
  onApplyAllReady?: () => void;
  applyAllPending?: boolean;
  applyAllDisabled?: boolean;
  applyAllLabel?: string;
  applyAllTestId?: string;
  /** Replace default candidates/ready chips (e.g. DSI summary from resolutionPlan). */
  summaryChipsSlot?: ReactNode;
  /** Full replace for options menu; when omitted and dsiExtras set, default DSI menu renders. */
  planOptionsSlot?: ReactNode;
  /** When set (and no planOptionsSlot), render DSI options menu + summary chips + effective errors. */
  dsiExtras?: StewardResolutionPlanToolbarDsiExtras;
}) {
  const { candidatesCount, readyCount, suggestionsQuery } = plan;

  const [menuAnchor, setMenuAnchor] = useState<null | HTMLElement>(null);
  const planComputing =
    candidatesCount > 0 && suggestionsQuery.fetchStatus === 'fetching' && !suggestionsQuery.data;

  const refreshLabel = copy?.refreshLabel ?? 'Refresh suggestions';
  const refreshPendingLabel = copy?.refreshPendingLabel ?? 'Refreshing…';
  const computingMessage = copy?.computingMessage ?? 'Computing resolution plan…';
  const refreshingMessage = copy?.refreshingMessage ?? 'Refreshing resolution suggestions…';

  const defaultSummaryChips =
    summaryChipsSlot !== undefined ? (
      summaryChipsSlot
    ) : dsiExtras?.resolutionPlan?.summary && typeof dsiExtras.resolutionPlan.summary === 'object' ? (
      <>
        <Chip
          size="small"
          label={`Candidates ${String((dsiExtras.resolutionPlan.summary as Record<string, unknown>).total ?? '—')}`}
        />
        <Chip
          size="small"
          color="success"
          variant="outlined"
          label={`Ready ${String((dsiExtras.resolutionPlan.summary as Record<string, unknown>).ready ?? '—')}`}
        />
        <Chip
          size="small"
          color="warning"
          variant="outlined"
          label={`Needs work ${String((dsiExtras.resolutionPlan.summary as Record<string, unknown>).not_ready ?? '—')}`}
        />
        <Chip
          size="small"
          variant="outlined"
          label={`On hold ${String((dsiExtras.resolutionPlan.summary as Record<string, unknown>).hold ?? '—')}`}
        />
      </>
    ) : readyCount != null ? (
      <>
        <Chip size="small" label={`Candidates ${candidatesCount}`} />
        <Chip size="small" color="success" variant="outlined" label={`Ready ${readyCount}`} />
      </>
    ) : null;

  const defaultOptions =
    planOptionsSlot !== undefined ? (
      planOptionsSlot
    ) : dsiExtras ? (
      <>
        <Box sx={{ flexGrow: 1 }} />
        <IconButton
          size="small"
          aria-label="Resolution plan options"
          onClick={(e) => setMenuAnchor(e.currentTarget)}
          data-testid={testIds.optionsOpen}
        >
          <MoreVertIcon fontSize="small" />
        </IconButton>
        <Menu
          anchorEl={menuAnchor}
          open={Boolean(menuAnchor)}
          onClose={() => setMenuAnchor(null)}
          data-testid={testIds.optionsMenu}
        >
          <MenuItem disableRipple sx={{ flexDirection: 'column', alignItems: 'stretch', py: 1 }}>
            <FormControlLabel
              sx={{ alignItems: 'flex-start', m: 0 }}
              control={
                <Checkbox
                  checked={dsiExtras.planGlobalSuspicious}
                  onChange={(e) => dsiExtras.setPlanGlobalSuspicious(e.target.checked)}
                  data-testid={testIds.globalSuspicious}
                />
              }
              label={
                <Typography variant="body2" component="span">
                  Allow provisional <strong>distributor</strong> creates for placeholder-like tokens for all rows in this
                  plan
                </Typography>
              }
            />
          </MenuItem>
          <MenuItem
            disabled={dsiExtras.planLoadToken === 0 || dsiExtras.refreshPlanEffective.isPending}
            onClick={() => {
              setMenuAnchor(null);
              void dsiExtras.refreshPlanEffective
                .mutateAsync({
                  overrides: dsiExtras.overridesPayload(),
                  globalSuspicious: dsiExtras.planGlobalSuspicious,
                })
                .catch(() => {});
            }}
            data-testid={testIds.refreshEffective}
          >
            Update plan after edits
          </MenuItem>
        </Menu>
      </>
    ) : null;

  return (
    <Stack spacing={1} data-testid={testIds.toolbar}>
      <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" alignItems="center">
        <StewardPendingButton
          variant="outlined"
          size="small"
          pending={suggestionsQuery.isFetching}
          pendingLabel={refreshPendingLabel}
          disabled={candidatesCount === 0}
          onClick={() => void suggestionsQuery.refetch().catch(() => {})}
          data-testid={testIds.refresh}
        >
          {refreshLabel}
        </StewardPendingButton>
        {defaultSummaryChips}
        {onApplyAllReady ? (
          <StewardPendingButton
            variant="contained"
            size="small"
            pending={Boolean(applyAllPending)}
            pendingLabel="Applying…"
            disabled={Boolean(applyAllDisabled) || planComputing}
            onClick={onApplyAllReady}
            data-testid={applyAllTestId ?? 'steward-resolution-plan-apply-all'}
          >
            {applyAllLabel ?? `Apply all ready (${readyCount ?? 0})`}
          </StewardPendingButton>
        ) : null}
        {defaultOptions}
      </Stack>
      {planComputing ? (
        <Alert severity="info" variant="outlined" data-testid={testIds.panelLoading}>
          {computingMessage}
        </Alert>
      ) : null}
      {suggestionsQuery.isFetching && suggestionsQuery.data ? (
        <Alert severity="info" variant="outlined" data-testid={testIds.refreshing}>
          {refreshingMessage}
        </Alert>
      ) : null}
      {dsiExtras?.planTableRows.some((x) => x.needs_confirm_suspicious_distributor === true) ? (
        <Alert severity="warning" data-testid={testIds.suspiciousHint} sx={{ display: { xs: 'flex', md: 'none' } }}>
          Some rows need permission for provisional distributors — open plan options (⋮) and update plan after edits.
        </Alert>
      ) : null}
      {suggestionsQuery.isError ? (
        <Alert severity="error" data-testid={testIds.suggestionsError}>
          {safeDisplayError(suggestionsQuery.error)}
        </Alert>
      ) : null}
      {dsiExtras?.refreshPlanEffective.isError ? (
        <Alert severity="error" data-testid={testIds.effectiveError}>
          {safeDisplayError(dsiExtras.refreshPlanEffective.error)}
        </Alert>
      ) : null}
    </Stack>
  );
}
