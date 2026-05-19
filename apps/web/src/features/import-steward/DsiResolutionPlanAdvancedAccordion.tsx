'use client';

import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Button,
  Checkbox,
  Chip,
  FormControl,
  FormControlLabel,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  Typography,
} from '@mui/material';
import type { UseMutationResult, UseQueryResult } from '@tanstack/react-query';

import { safeDisplayError } from '@/lib/api';

import { DsiGeoStewardAccordion } from './DsiGeoStewardAccordion';
import { DsiStewardLoadingCallout } from './DsiStewardLoadingCallout';
import { DsiPendingButton } from './DsiPendingButton';
import type { DsiCatalogOpt, DsiUnresolvedGeoRowDto } from './dsiSteward.types';

type PlanHookSlice = {
  importJobId: number;
  candidatesCount: number;
  regions: DsiCatalogOpt[];
  channels: DsiCatalogOpt[];
  unresolvedGeoQuery: UseQueryResult<{
    import_job_id: number;
    channels: DsiUnresolvedGeoRowDto[];
    regions: DsiUnresolvedGeoRowDto[];
  }>;
  planRegionId: string;
  setPlanRegionId: (v: string) => void;
  planChannelId: string;
  setPlanChannelId: (v: string) => void;
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
  onInvalidate: () => void;
  planApplySummary?: string | null;
  onClearPlanApplySummary?: () => void;
};

export function DsiResolutionPlanAdvancedAccordion(plan: PlanHookSlice) {
  const {
    importJobId,
    candidatesCount,
    regions,
    channels,
    unresolvedGeoQuery,
    planRegionId,
    setPlanRegionId,
    planChannelId,
    setPlanChannelId,
    resolutionPlan,
    planGlobalSuspicious,
    setPlanGlobalSuspicious,
    planLoadToken,
    planTableRows,
    suggestionsQuery,
    refreshPlanEffective,
    overridesPayload,
    onInvalidate,
    planApplySummary,
    onClearPlanApplySummary,
  } = plan;

  return (
    <Accordion
      disableGutters
      elevation={0}
      defaultExpanded={false}
      sx={{ border: 1, borderColor: 'divider', borderRadius: 1, '&:before': { display: 'none' } }}
      data-testid="dsi-resolution-plan-advanced"
    >
      <AccordionSummary expandIcon={<ExpandMoreIcon />}>
        <Typography variant="body2" color="text.secondary">
          Resolution plan & geo tools (optional)
        </Typography>
      </AccordionSummary>
      <AccordionDetails>
        <Stack spacing={2} data-testid="dsi-resolution-plan-panel">
          {planApplySummary ? (
            <Alert
              severity="success"
              data-testid="dsi-plan-apply-summary"
              onClose={onClearPlanApplySummary}
            >
              {planApplySummary}
            </Alert>
          ) : null}
          {suggestionsQuery.isPending && !suggestionsQuery.data ? (
            <DsiStewardLoadingCallout
              message="Computing resolution plan…"
              detail="Large imports can take 30+ seconds. Plan chips and row hints appear when this finishes."
              testId="dsi-resolution-plan-panel-loading"
            />
          ) : null}
          {suggestionsQuery.isFetching && suggestionsQuery.data ? (
            <Alert severity="info" variant="outlined" data-testid="dsi-resolution-plan-refreshing">
              Refreshing resolution suggestions…
            </Alert>
          ) : null}
          <Typography variant="subtitle2" gutterBottom>
            Resolution suggestions (read-only until you apply)
          </Typography>
          <Typography variant="body2" color="text.secondary">
            <strong>Source-first:</strong> customer candidates use mapped file columns for region and channel when
            validation has run. Use <strong>Plan…</strong> on a row for overrides. Refresh suggestions recomputes the plan
            without re-running import validation.
          </Typography>
          <DsiGeoStewardAccordion
            importJobId={importJobId}
            unresolvedGeoQuery={unresolvedGeoQuery}
            catalogChannels={channels}
            catalogRegions={regions}
            onInvalidate={onInvalidate}
          />
          <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" alignItems="center" sx={{ mb: 1 }}>
            <DsiPendingButton
              variant="outlined"
              size="small"
              pending={suggestionsQuery.isFetching}
              pendingLabel="Refreshing…"
              disabled={candidatesCount === 0}
              onClick={() => void suggestionsQuery.refetch().catch(() => {})}
              data-testid="dsi-resolution-suggestions-refresh"
            >
              Refresh suggestions
            </DsiPendingButton>
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
          </Stack>
          <Accordion
            disableGutters
            elevation={0}
            sx={{ mt: 1.5, border: 1, borderColor: 'divider', borderRadius: 1, '&:before': { display: 'none' } }}
            data-testid="dsi-resolution-plan-fallback-accordion"
          >
            <AccordionSummary expandIcon={<ExpandMoreIcon />}>
              <Typography variant="body2" color="text.secondary">
                Optional global catalog fallbacks (missing / unresolved / mixed source only)
              </Typography>
            </AccordionSummary>
            <AccordionDetails>
              <Stack spacing={1.5}>
                <Alert severity="warning" variant="outlined" icon={false}>
                  <Typography variant="caption" display="block">
                    Lists are the full API catalog (often including demo rows such as NA-E, NA-W, ECOM, RET). They are not
                    applied when the file already supplies a resolvable value. Choose only values that match your DSI
                    geography and channel reality.
                  </Typography>
                </Alert>
                <Stack
                  direction={{ xs: 'column', sm: 'row' }}
                  spacing={2}
                  alignItems={{ sm: 'flex-start' }}
                  flexWrap="wrap"
                  useFlexGap
                >
                  <FormControl size="small" sx={{ minWidth: 220 }}>
                    <InputLabel id="dsi-plan-region">Fallback region</InputLabel>
                    <Select
                      labelId="dsi-plan-region"
                      label="Fallback region"
                      value={planRegionId}
                      onChange={(e) => setPlanRegionId(String(e.target.value))}
                    >
                      <MenuItem value="">
                        <em>None</em>
                      </MenuItem>
                      {regions.map((r) => (
                        <MenuItem key={r.id} value={String(r.id)}>
                          {r.code} — {r.name}
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                  <FormControl size="small" sx={{ minWidth: 220 }}>
                    <InputLabel id="dsi-plan-channel">Fallback channel</InputLabel>
                    <Select
                      labelId="dsi-plan-channel"
                      label="Fallback channel"
                      value={planChannelId}
                      onChange={(e) => setPlanChannelId(String(e.target.value))}
                    >
                      <MenuItem value="">
                        <em>None</em>
                      </MenuItem>
                      {channels.map((c) => (
                        <MenuItem key={c.id} value={String(c.id)}>
                          {c.code} — {c.name}
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                </Stack>
              </Stack>
            </AccordionDetails>
          </Accordion>
          <Stack
            direction={{ xs: 'column', md: 'row' }}
            spacing={2}
            alignItems={{ md: 'flex-start' }}
            useFlexGap
            flexWrap="wrap"
            sx={{ mt: 2 }}
          >
            <FormControlLabel
              sx={{ alignItems: 'flex-start', mr: 0, maxWidth: 420 }}
              control={
                <Checkbox
                  checked={planGlobalSuspicious}
                  onChange={(e) => setPlanGlobalSuspicious(e.target.checked)}
                  data-testid="dsi-plan-global-suspicious-confirm"
                />
              }
              label={
                <Typography variant="body2" component="span">
                  Allow provisional <strong>distributor</strong> creates for placeholder-like tokens (e.g. unknown, n/a) for{' '}
                  <strong>all rows</strong> in this plan
                </Typography>
              }
            />
            <DsiPendingButton
              variant="outlined"
              size="small"
              pending={refreshPlanEffective.isPending}
              pendingLabel="Updating plan…"
              disabled={planLoadToken === 0}
              onClick={() =>
                void refreshPlanEffective
                  .mutateAsync({
                    overrides: overridesPayload(),
                    globalSuspicious: planGlobalSuspicious,
                  })
                  .catch(() => {})
              }
              data-testid="dsi-resolution-plan-refresh-effective"
            >
              Update plan after edits
            </DsiPendingButton>
          </Stack>
          {planTableRows.some((x) => x.needs_confirm_suspicious_distributor === true) ? (
            <Alert severity="warning" data-testid="dsi-plan-suspicious-hint" sx={{ mt: 1.5 }}>
              Some rows need explicit permission before creating a provisional distributor from a placeholder-like token.
              Use the row override and/or the global option above, then click <strong>Update plan after edits</strong>.
            </Alert>
          ) : null}
          {suggestionsQuery.isError ? (
            <Alert severity="error" sx={{ mt: 1 }} data-testid="dsi-resolution-suggestions-error">
              {safeDisplayError(suggestionsQuery.error)}
            </Alert>
          ) : null}
          {refreshPlanEffective.isError ? (
            <Alert severity="error" sx={{ mt: 1 }} data-testid="dsi-resolution-plan-effective-error">
              {safeDisplayError(refreshPlanEffective.error)}
            </Alert>
          ) : null}
        </Stack>
      </AccordionDetails>
    </Accordion>
  );
}
