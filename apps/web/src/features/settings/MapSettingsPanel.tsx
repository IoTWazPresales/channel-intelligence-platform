'use client';

import { Alert, Box, Button, Stack, TextField, Typography } from '@mui/material';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { apiPut, safeDisplayError } from '@/lib/api';

import { MAP_SETTING_FIELDS, useMapSettings } from './useMapSettings';

type FormProps = {
  stored: Record<string, unknown>;
  queryKey: readonly unknown[];
  canEdit: boolean;
};

function MapSettingsForm({ stored, queryKey, canEdit }: FormProps) {
  const qc = useQueryClient();
  const [values, setValues] = useState<Record<string, string>>(() => Object.fromEntries(
    MAP_SETTING_FIELDS.map(({ key }) => [key, typeof stored[key] === 'string' ? stored[key] : '']),
  ));
  const save = useMutation({
    mutationFn: async (input: { values: Record<string, string>; cacheKey: readonly unknown[] }) => {
      // The existing API commits each key separately. Refresh even after a partial failure.
      for (const { key } of MAP_SETTING_FIELDS) {
        await apiPut(`/api/v1/tenant-settings/${encodeURIComponent(key)}`, {
          value: input.values[key].trim() || null,
        });
      }
    },
    onSettled: (_data, _error, input) => {
      void qc.invalidateQueries({ queryKey: input.cacheKey });
    },
  });

  return (
    <Stack spacing={2} maxWidth={620}>
      <Typography variant="body2" color="text.secondary">
        Configure this tenant&apos;s map provider. Nothing is prefilled or enabled automatically.
        Clearing the TileJSON URL disables the prototype basemap.
      </Typography>
      {!canEdit ? <Alert severity="info">A steward or admin can edit these settings.</Alert> : null}
      {MAP_SETTING_FIELDS.map(({ key, label, help }) => (
        <TextField
          key={key}
          label={label}
          helperText={help}
          value={values[key]}
          disabled={!canEdit || save.isPending}
          fullWidth
          onChange={(event) => {
            save.reset();
            setValues((current) => ({ ...current, [key]: event.target.value }));
          }}
        />
      ))}
      {save.isError ? (
        <Alert severity="error">
          {safeDisplayError(save.error)} Some settings may have saved. Reload before retrying.
        </Alert>
      ) : null}
      {save.isSuccess ? <Alert severity="success">Map settings saved.</Alert> : null}
      {canEdit ? (
        <Box>
          <Button
            variant="contained"
            disabled={save.isPending}
            onClick={() => save.mutate({ values: { ...values }, cacheKey: queryKey })}
          >
            {save.isPending ? 'Saving…' : 'Save map settings'}
          </Button>
        </Box>
      ) : null}
    </Stack>
  );
}

export function MapSettingsPanel() {
  const state = useMapSettings();
  return (
    <Box id="map-settings" data-testid="map-settings-panel" sx={{ scrollMarginTop: 80 }}>
      <Typography variant="subtitle1" fontWeight={600} gutterBottom>Map</Typography>
      {state.pending ? <Typography variant="body2">Loading map settings…</Typography> : null}
      {state.error ? <Alert severity="error">{safeDisplayError(state.error)}</Alert> : null}
      {!state.pending && !state.error && state.query.data ? (
        <MapSettingsForm
          key={JSON.stringify(state.queryKey)}
          stored={state.query.data.settings}
          queryKey={state.queryKey}
          canEdit={state.canEdit}
        />
      ) : null}
    </Box>
  );
}
