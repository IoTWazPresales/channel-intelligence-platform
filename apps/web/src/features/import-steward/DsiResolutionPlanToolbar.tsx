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
import { useState } from 'react';

import { safeDisplayError } from '@/lib/api';

import { StewardPendingButton } from './StewardPendingButton';

type PlanToolbarSlice = {
  candidatesCount: number;
  resolutionPlan: Record<string, unknown> | null;
  planGlobalSuspicious: boolean;
  setPlanGlobalSuspicious: (v: boolean) => void;
  planLoadToken: number;
  planTableRows: Array<Record<string, unknown>>;
  suggestionsQuery: UseQueryResult<Record<string, unknown>>;
  refreshPlanEffective: UseMutationResult<
    Record<string, unknown>,
    Error,
    { overrides: Array<Record<string, unknown>>; globalSuspicious: boolean }
  >;
  overridesPayload: () => Array<Record<string, unknown>>;
};

/** Compact plan controls above the steward tabs (refresh, summary chips, plan options menu). */
export function DsiResolutionPlanToolbar(plan: PlanToolbarSlice) {
  const {
    candidatesCount,
    resolutionPlan,
    planGlobalSuspicious,
    setPlanGlobalSuspicious,
    planLoadToken,
    planTableRows,
    suggestionsQuery,
    refreshPlanEffective,
    overridesPayload,
  } = plan;

  const [menuAnchor, setMenuAnchor] = useState<null | HTMLElement>(null);
  const planComputing =
    candidatesCount > 0 && suggestionsQuery.fetchStatus === 'fetching' && !suggestionsQuery.data;

  return (
    <Stack spacing={1} data-testid="dsi-resolution-plan-toolbar">
      <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" alignItems="center">
        <StewardPendingButton
          variant="outlined"
          size="small"
          pending={suggestionsQuery.isFetching}
          pendingLabel="Refreshing…"
          disabled={candidatesCount === 0}
          onClick={() => void suggestionsQuery.refetch().catch(() => {})}
          data-testid="dsi-resolution-suggestions-refresh"
        >
          Refresh suggestions
        </StewardPendingButton>
        {resolutionPlan?.summary && typeof resolutionPlan.summary === 'object' ? (
          <>
            <Chip
              size="small"
              label={`Candidates ${String((resolutionPlan.summary as Record<string, unknown>).total ?? '—')}`}
            />
            <Chip
              size="small"
              color="success"
              variant="outlined"
              label={`Ready ${String((resolutionPlan.summary as Record<string, unknown>).ready ?? '—')}`}
            />
            <Chip
              size="small"
              color="warning"
              variant="outlined"
              label={`Needs work ${String((resolutionPlan.summary as Record<string, unknown>).not_ready ?? '—')}`}
            />
            <Chip
              size="small"
              variant="outlined"
              label={`On hold ${String((resolutionPlan.summary as Record<string, unknown>).hold ?? '—')}`}
            />
          </>
        ) : null}
        <Box sx={{ flexGrow: 1 }} />
        <IconButton
          size="small"
          aria-label="Resolution plan options"
          onClick={(e) => setMenuAnchor(e.currentTarget)}
          data-testid="dsi-plan-options-open"
        >
          <MoreVertIcon fontSize="small" />
        </IconButton>
        <Menu
          anchorEl={menuAnchor}
          open={Boolean(menuAnchor)}
          onClose={() => setMenuAnchor(null)}
          data-testid="dsi-plan-options-menu"
        >
          <MenuItem disableRipple sx={{ flexDirection: 'column', alignItems: 'stretch', py: 1 }}>
            <FormControlLabel
              sx={{ alignItems: 'flex-start', m: 0 }}
              control={
                <Checkbox
                  checked={planGlobalSuspicious}
                  onChange={(e) => setPlanGlobalSuspicious(e.target.checked)}
                  data-testid="dsi-plan-global-suspicious-confirm"
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
            disabled={planLoadToken === 0 || refreshPlanEffective.isPending}
            onClick={() => {
              setMenuAnchor(null);
              void refreshPlanEffective
                .mutateAsync({
                  overrides: overridesPayload(),
                  globalSuspicious: planGlobalSuspicious,
                })
                .catch(() => {});
            }}
            data-testid="dsi-resolution-plan-refresh-effective"
          >
            Update plan after edits
          </MenuItem>
        </Menu>
      </Stack>
      {planComputing ? (
        <Alert severity="info" variant="outlined" data-testid="dsi-resolution-plan-panel-loading">
          Computing resolution plan…
        </Alert>
      ) : null}
      {suggestionsQuery.isFetching && suggestionsQuery.data ? (
        <Alert severity="info" variant="outlined" data-testid="dsi-resolution-plan-refreshing">
          Refreshing resolution suggestions…
        </Alert>
      ) : null}
      {planTableRows.some((x) => x.needs_confirm_suspicious_distributor === true) ? (
        <Alert severity="warning" data-testid="dsi-plan-suspicious-hint" sx={{ display: { xs: 'flex', md: 'none' } }}>
          Some rows need permission for provisional distributors — open plan options (⋮) and update plan after edits.
        </Alert>
      ) : null}
      {suggestionsQuery.isError ? (
        <Alert severity="error" data-testid="dsi-resolution-suggestions-error">
          {safeDisplayError(suggestionsQuery.error)}
        </Alert>
      ) : null}
      {refreshPlanEffective.isError ? (
        <Alert severity="error" data-testid="dsi-resolution-plan-effective-error">
          {safeDisplayError(refreshPlanEffective.error)}
        </Alert>
      ) : null}
    </Stack>
  );
}
