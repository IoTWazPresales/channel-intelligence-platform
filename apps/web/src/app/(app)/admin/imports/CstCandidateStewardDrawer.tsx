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
import { apiGet, safeDisplayError } from '@/lib/api';

import type { CstCandidateSuggestion, CstEntityTabId, CstMappingCandidate } from './cstImportSteward.config';

type DimPick = { id: number; label: string };

async function fetchProductOptions(q: string, signal: AbortSignal): Promise<DimPick[]> {
  const res = await apiGet<{ items: { id: number; sku?: string | null; sales_model_name?: string | null; marketing_name?: string | null }[] }>(
    `/api/v1/products?page=1&page_size=25&q=${encodeURIComponent(q)}`,
    { signal }
  );
  return (res.items ?? []).map((p) => ({
    id: p.id,
    label: (p.sales_model_name || p.marketing_name || p.sku || String(p.id)).trim(),
  }));
}

async function fetchLocationOptions(
  customerId: number,
  q: string,
  signal: AbortSignal
): Promise<DimPick[]> {
  const rows = await apiGet<
    { id: number; location_code?: string | null; location_name?: string | null }[]
  >(`/api/v1/customers/${customerId}/locations`, { signal });
  const needle = q.trim().toLowerCase();
  return (rows ?? [])
    .filter((loc) => {
      if (!needle) return true;
      const code = (loc.location_code || '').toLowerCase();
      const name = (loc.location_name || '').toLowerCase();
      return code.includes(needle) || name.includes(needle);
    })
    .slice(0, 25)
    .map((loc) => ({
      id: loc.id,
      label: (loc.location_name || loc.location_code || String(loc.id)).trim(),
    }));
}

export function CstCandidateStewardDrawer({
  candidate,
  entity,
  customerId,
  busy,
  onClose,
  onResolve,
  onIgnore,
}: {
  candidate: CstMappingCandidate;
  entity: CstEntityTabId;
  customerId: number | null;
  busy?: boolean;
  onClose: () => void;
  onResolve: (entityId: number) => Promise<void>;
  onIgnore: () => Promise<void>;
}) {
  const [target, setTarget] = useState<DimPick | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [mappingDimId, setMappingDimId] = useState<number | null>(null);

  const fetchOptions = useCallback(
    (q: string, signal: AbortSignal) => {
      if (entity === 'product') return fetchProductOptions(q, signal);
      if (customerId == null) return Promise.resolve([]);
      return fetchLocationOptions(customerId, q, signal);
    },
    [entity, customerId]
  );

  const runResolve = async (entityId: number) => {
    setError(null);
    setPending(true);
    setMappingDimId(entityId);
    try {
      await onResolve(entityId);
      setTarget(null);
      onClose();
    } catch (e) {
      setError(safeDisplayError(e));
    } finally {
      setPending(false);
      setMappingDimId(null);
    }
  };

  const runIgnore = async () => {
    setError(null);
    setPending(true);
    try {
      await onIgnore();
      onClose();
    } catch (e) {
      setError(safeDisplayError(e));
    } finally {
      setPending(false);
    }
  };

  const suggestions: CstCandidateSuggestion[] = candidate.suggestions ?? [];
  const band = confidenceBand(candidate.confidence_score);

  const suggestionItems = useMemo(
    () =>
      suggestions.map((s) => ({
        targetId: s.dim_id,
        label: s.label,
        score: s.score,
        reason: s.reason,
        onMap: (dimId: number) => {
          void runResolve(dimId);
        },
        mapPending: pending && mappingDimId === s.dim_id,
        mapDisabled: Boolean(busy || pending),
      })),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [suggestions, pending, mappingDimId, busy, candidate.id, entity]
  );

  return (
    <StewardDrawerChrome
      title={`Map ${entity}`}
      onClose={onClose}
      rootTestId="cst-import-candidate-steward-drawer"
      closeTestId="cst-import-steward-drawer-close"
      ariaLabel="CST import candidate steward"
    >
      <Stack spacing={2} data-testid="cst-import-drawer-body">
        <Box>
          <Typography variant="caption" color="text.secondary">
            Token
          </Typography>
          <Typography variant="body1" sx={{ fontWeight: 600, wordBreak: 'break-word' }}>
            {candidate.normalized_key}
          </Typography>
        </Box>
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap alignItems="center">
          <Chip size="small" label={candidate.status} data-testid="cst-import-drawer-status" />
          {band ? (
            <Chip
              size="small"
              variant="outlined"
              color={confidenceBandColor(band)}
              label={confidenceBandLabel(band)}
              data-testid="cst-import-drawer-confidence"
            />
          ) : null}
          {candidate.match_reason ? (
            <Typography variant="caption" color="text.secondary">
              {candidate.match_reason}
            </Typography>
          ) : null}
        </Stack>

        <StewardEvidenceSummary
          sampleRawValues={candidate.sample_raw_values}
          affectedRowCount={candidate.row_count}
          totalUnits={candidate.total_units}
          testId="cst-import-evidence-summary"
        />

        <StewardSuggestionCards
          suggestions={suggestionItems}
          testId="cst-import-suggestion-cards"
          overrideSlot={
            <Stack spacing={1} data-testid="cst-import-override-search">
              <Typography variant="subtitle2">Override search</Typography>
              {entity === 'location' && customerId == null ? (
                <Alert severity="warning">
                  Customer context missing for this job — location override search is unavailable.
                </Alert>
              ) : (
                <EntitySearchAutocomplete<DimPick>
                  value={target}
                  onChange={setTarget}
                  fetchOptions={fetchOptions}
                  getOptionLabel={(o) => o.label}
                  label={entity === 'product' ? 'Search product master' : 'Search locations'}
                  disabled={Boolean(busy || pending)}
                />
              )}
              <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                <Button
                  size="small"
                  variant="contained"
                  disabled={!target || busy || pending}
                  onClick={() => target && void runResolve(target.id)}
                  data-testid="cst-import-override-map"
                >
                  Map to selected
                </Button>
                <Button
                  size="small"
                  variant="outlined"
                  color="inherit"
                  disabled={busy || pending || candidate.status === 'ignored'}
                  onClick={() => void runIgnore()}
                  data-testid="cst-import-ignore"
                >
                  Ignore token
                </Button>
              </Stack>
            </Stack>
          }
        />

        {error ? (
          <Alert severity="error" onClose={() => setError(null)} data-testid="cst-import-drawer-error">
            {error}
          </Alert>
        ) : null}
      </Stack>
    </StewardDrawerChrome>
  );
}
