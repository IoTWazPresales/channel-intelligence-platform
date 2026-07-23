'use client';

import { Alert, Box, Button, Chip, Divider, Stack, Typography } from '@mui/material';
import { useCallback, useState } from 'react';

import { EntitySearchAutocomplete } from '@/features/commercial-planner/EntitySearchAutocomplete';
import {
  confidenceBand,
  confidenceBandColor,
  confidenceBandLabel,
} from '@/features/import-steward/confidenceBand';
import { StewardDrawerChrome } from '@/features/import-steward/StewardDrawerChrome';
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
          <Typography variant="body2" color="text.secondary">
            Appears on {candidate.row_count} staging row{candidate.row_count === 1 ? '' : 's'}
          </Typography>
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

        <Box data-testid="cpor-historical-drawer-suggestions">
          <Typography variant="subtitle2" sx={{ mb: 1 }}>
            Suggested masters
          </Typography>
          {suggestions.length === 0 ? (
            <Alert severity="info">
              No ranked suggestions for this token. Search an existing master below — never auto-created.
            </Alert>
          ) : (
            <Stack spacing={1}>
              {suggestions.map((s) => {
                const sBand = confidenceBand(s.score);
                return (
                  <Box
                    key={`${s.dim_id}-${s.reason}`}
                    sx={{
                      border: 1,
                      borderColor: 'divider',
                      borderRadius: 1,
                      p: 1.25,
                    }}
                    data-testid={`cpor-historical-suggestion-${s.dim_id}`}
                  >
                    <Stack spacing={0.75}>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        {s.label}
                      </Typography>
                      <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
                        {sBand ? (
                          <Chip
                            size="small"
                            variant="outlined"
                            color={confidenceBandColor(sBand)}
                            label={confidenceBandLabel(sBand)}
                          />
                        ) : null}
                        <Chip size="small" variant="outlined" label={`score ${Number(s.score).toFixed(2)}`} />
                        <Chip size="small" variant="outlined" label={s.reason} />
                      </Stack>
                      <Button
                        size="small"
                        variant="contained"
                        disabled={busy || pending}
                        onClick={() => void runMap(s.dim_id)}
                        data-testid={`cpor-historical-suggestion-map-${s.dim_id}`}
                      >
                        {pending && mappingDimId === s.dim_id ? 'Mapping…' : 'Map to this master'}
                      </Button>
                    </Stack>
                  </Box>
                );
              })}
            </Stack>
          )}
        </Box>

        <Divider />

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

        {error ? <Alert severity="error">{error}</Alert> : null}
      </Stack>
    </StewardDrawerChrome>
  );
}
