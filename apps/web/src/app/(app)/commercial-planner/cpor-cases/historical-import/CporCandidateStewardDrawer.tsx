'use client';

import CloseIcon from '@mui/icons-material/Close';
import { Alert, Box, Button, IconButton, Stack, Typography } from '@mui/material';
import { useCallback, useState } from 'react';

import { EntitySearchAutocomplete } from '@/features/commercial-planner/EntitySearchAutocomplete';
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
    <Box
      component="aside"
      role="complementary"
      aria-label="CPOR historical candidate steward"
      data-testid="cpor-historical-candidate-steward-drawer"
      sx={{
        width: { xs: '100%', md: '40%' },
        minWidth: { md: 320 },
        maxWidth: '100%',
        flexShrink: 0,
        borderLeft: { md: 1 },
        borderColor: 'divider',
        bgcolor: 'background.paper',
        display: 'flex',
        flexDirection: 'column',
        maxHeight: { xs: 'none', md: 'min(72vh, calc(100vh - 96px))' },
        overflow: 'hidden',
        position: { md: 'sticky' },
        top: { md: 80 },
        alignSelf: { md: 'flex-start' },
      }}
    >
      <Stack
        direction="row"
        alignItems="center"
        justifyContent="space-between"
        sx={{ px: 2, py: 1.25, borderBottom: 1, borderColor: 'divider', flexShrink: 0 }}
      >
        <Typography variant="subtitle1">Map {entity}</Typography>
        <IconButton
          size="small"
          aria-label="Close steward drawer"
          onClick={onClose}
          data-testid="cpor-historical-steward-drawer-close"
        >
          <CloseIcon fontSize="small" />
        </IconButton>
      </Stack>
      <Box sx={{ flex: 1, overflow: 'auto', px: 2, py: 1.5 }}>
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
      </Box>
    </Box>
  );
}
