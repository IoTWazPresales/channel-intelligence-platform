'use client';

import { Alert, Box, Button, Stack, Typography } from '@mui/material';
import { useCallback, useState } from 'react';

import { EntitySearchAutocomplete } from '@/features/commercial-planner/EntitySearchAutocomplete';
import { StewardDrawerChrome } from '@/features/import-steward/StewardDrawerChrome';
import type { ImportStewardCandidateRowBase } from '@/features/import-steward/importStewardCandidateWorkspace.types';
import { safeDisplayError } from '@/lib/api';

import type { CporEntityTabId } from './cporHistoricalSteward.config';
import {
  cporDimLabel,
  fetchCporDimOptions,
  type CporDimPick,
} from './cporHistoricalImportApi';

export type CporStewardRow = ImportStewardCandidateRowBase & { token: string };

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

  const fetchOptions = useCallback(
    (q: string, signal: AbortSignal) => fetchCporDimOptions(entity, q, signal),
    [entity]
  );

  const handleMap = async () => {
    if (!target) return;
    setError(null);
    setPending(true);
    try {
      await onMap({ token: candidate.token, dimId: target.id });
      setTarget(null);
      onClose();
    } catch (e) {
      setError(safeDisplayError(e));
    } finally {
      setPending(false);
    }
  };

  return (
    <StewardDrawerChrome
      title={`Map ${entity}`}
      onClose={onClose}
      rootTestId="cpor-historical-candidate-steward-drawer"
      closeTestId="cpor-historical-steward-drawer-close"
      ariaLabel="CPOR historical candidate steward"
    >
      <Stack spacing={2}>
        <Box>
          <Typography variant="caption" color="text.secondary">
            Token
          </Typography>
          <Typography variant="body1" sx={{ fontWeight: 600, wordBreak: 'break-word' }}>
            {candidate.token}
          </Typography>
        </Box>
        <Typography variant="body2" color="text.secondary">
          Appears on {candidate.row_count} staging row{candidate.row_count === 1 ? '' : 's'} · status{' '}
          {candidate.status}
        </Typography>
        <EntitySearchAutocomplete<CporDimPick>
          label={`Map ${entity} to…`}
          value={target}
          onChange={setTarget}
          fetchOptions={fetchOptions}
          getOptionLabel={cporDimLabel}
          disabled={busy || pending}
        />
        {error ? <Alert severity="error">{error}</Alert> : null}
        <Button
          variant="contained"
          disabled={!target || busy || pending}
          onClick={() => void handleMap()}
          data-testid="cpor-historical-drawer-map"
        >
          {pending ? 'Mapping…' : 'Map token'}
        </Button>
      </Stack>
    </StewardDrawerChrome>
  );
}
