'use client';

import { Alert, Box, Button, Chip, Stack, Typography } from '@mui/material';
import { useCallback, useMemo, useState } from 'react';

import { EntitySearchAutocomplete } from '@/features/commercial-planner/EntitySearchAutocomplete';
import {
  confidenceBand,
  confidenceBandColor,
  confidenceBandLabel,
} from '@/features/import-steward/confidenceBand';
import { StewardDrawerChrome } from '@/features/import-steward/StewardDrawerChrome';
import { StewardEvidenceSummary } from '@/features/import-steward/StewardEvidenceSummary';
import { StewardSuggestionCards } from '@/features/import-steward/StewardSuggestionCards';
import type { ImportStewardCandidateRowBase } from '@/features/import-steward/importStewardCandidateWorkspace.types';
import { safeDisplayError } from '@/lib/api';

import type {
  CporCandidateSuggestion,
  CporEntityTabId,
  CporPlanClass,
} from './cporHistoricalSteward.config';
import {
  cporDimLabel,
  fetchCporDimOptions,
  type CporDimPick,
} from './cporHistoricalImportApi';

export type CporStewardRow = ImportStewardCandidateRowBase & {
  token: string;
  plan_class?: CporPlanClass | string | null;
  suggestions?: CporCandidateSuggestion[];
  /** Affected case codes from staging enrichment (Unit C S6 payload). */
  case_codes?: string[];
};

export function CporCandidateStewardDrawer({
  candidate,
  entity,
  busy,
  onClose,
  onMap,
}: {
  candidate: CporStewardRow;
  entity: CporEntityTabId;
  busy?: boolean;
  onClose: () => void;
  onMap: (args: { token: string; dimId: number }) => Promise<void>;
}) {
  const [target, setTarget] = useState<CporDimPick | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [mappingDimId, setMappingDimId] = useState<number | null>(null);

  const fetchOptions = useCallback(
    (q: string, signal: AbortSignal) => fetchCporDimOptions(entity, q, signal),
    [entity]
  );

  const runMap = async (dimId: number) => {
    setError(null);
    setPending(true);
    setMappingDimId(dimId);
    try {
      await onMap({ token: candidate.token, dimId });
      setTarget(null);
      onClose();
    } catch (e) {
      setError(safeDisplayError(e));
    } finally {
      setPending(false);
      setMappingDimId(null);
    }
  };

  const suggestions = candidate.suggestions ?? [];
  const band = confidenceBand(candidate.confidence_score);

  const suggestionItems = useMemo(
    () =>
      suggestions.map((s) => ({
        targetId: s.dim_id,
        label: s.label,
        score: s.score,
        reason: s.reason,
        onMap: (dimId: number) => {
          void runMap(dimId);
        },
        mapPending: pending && mappingDimId === s.dim_id,
        mapDisabled: Boolean(busy || pending),
      })),
    // runMap closes over latest candidate/busy — recreate when those change
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [suggestions, pending, mappingDimId, busy, candidate.token, entity]
  );

  const caseCodes = (candidate.case_codes ?? []).filter(Boolean);

  return (
    <StewardDrawerChrome
      title={`Map ${entity}`}
      onClose={onClose}
      rootTestId="cpor-historical-candidate-steward-drawer"
      closeTestId="cpor-historical-steward-drawer-close"
      ariaLabel="CPOR historical candidate steward"
    >
      <Stack spacing={2} data-testid="cpor-historical-drawer-intelligence">
        <Box>
          <Typography variant="caption" color="text.secondary">
            Token
          </Typography>
          <Typography variant="body1" sx={{ fontWeight: 600, wordBreak: 'break-word' }}>
            {candidate.token}
          </Typography>
        </Box>
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap alignItems="center">
          {candidate.plan_class ? (
            <Chip
              size="small"
              label={String(candidate.plan_class).replace(/_/g, ' ')}
              data-testid="cpor-historical-drawer-plan-class"
            />
          ) : null}
          {band ? (
            <Chip
              size="small"
              variant="outlined"
              color={confidenceBandColor(band)}
              label={confidenceBandLabel(band)}
              data-testid="cpor-historical-drawer-confidence-band"
            />
          ) : null}
        </Stack>
        {candidate.match_reason ? (
          <Typography variant="caption" color="text.secondary" data-testid="cpor-historical-drawer-match-reason">
            Match reason: {candidate.match_reason}
          </Typography>
        ) : null}

        <StewardEvidenceSummary
          sampleRawValues={candidate.sample_raw_values}
          affectedRowCount={candidate.row_count}
          totalUnits={candidate.total_units}
          totalReportedValue={candidate.total_reported_value}
          testId="cpor-historical-drawer-evidence"
          extras={
            caseCodes.length > 0 ? (
              <Stack spacing={0.5}>
                <Typography variant="caption" color="text.secondary">
                  Affected cases
                </Typography>
                <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                  {caseCodes.map((c) => (
                    <Chip key={c} size="small" label={c} data-testid={`cpor-historical-drawer-case-${c}`} />
                  ))}
                </Stack>
              </Stack>
            ) : null
          }
        />

        <StewardSuggestionCards
          suggestions={suggestionItems}
          testId="cpor-historical-suggestion"
          overrideSlot={
            <Stack spacing={1} data-testid="cpor-historical-drawer-override-search">
              <Typography variant="subtitle2">None of these — search…</Typography>
              <EntitySearchAutocomplete<CporDimPick>
                label={`Map ${entity} to…`}
                value={target}
                onChange={setTarget}
                fetchOptions={fetchOptions}
                getOptionLabel={cporDimLabel}
                disabled={busy || pending}
              />
              <Button
                variant="outlined"
                disabled={!target || busy || pending}
                onClick={() => {
                  if (!target) return;
                  void runMap(target.id);
                }}
                data-testid="cpor-historical-drawer-map"
              >
                {pending && mappingDimId === target?.id ? 'Mapping…' : 'Map token (override)'}
              </Button>
            </Stack>
          }
        />

        {error ? <Alert severity="error">{error}</Alert> : null}
      </Stack>
    </StewardDrawerChrome>
  );
}
