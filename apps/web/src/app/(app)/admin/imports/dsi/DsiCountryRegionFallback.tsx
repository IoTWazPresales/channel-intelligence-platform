'use client';

import { useState } from 'react';
import {
  Alert,
  FormControl,
  FormControlLabel,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  Switch,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { apiGet, apiPost, safeDisplayError } from '@/lib/api';

import { DSI_STEWARD_CONFIG } from './dsiSteward.config';
import type { DsiCatalogOpt } from './dsiSteward.types';

export type IsoCountry = { alpha2: string; name: string };

export function DsiCountryRegionFallback({
  enabled,
  onEnabledChange,
  onRegionIdChange,
  disabled,
  catalogRegions = [],
}: {
  importJobId: number;
  enabled: boolean;
  onEnabledChange: (v: boolean) => void;
  onRegionIdChange: (regionId: string) => void;
  disabled?: boolean;
  catalogRegions?: DsiCatalogOpt[];
}) {
  const qc = useQueryClient();
  const [selectedIso, setSelectedIso] = useState('');

  const { data: countriesPayload } = useQuery({
    queryKey: ['reference-countries'],
    queryFn: ({ signal }) => apiGet<{ countries: IsoCountry[] }>('/api/v1/reference/countries', { signal }),
    staleTime: 60 * 60 * 1000,
  });
  const countries = countriesPayload?.countries ?? [];

  const ensureRegion = useMutation({
    mutationFn: (iso: string) =>
      apiPost<{ region_id: number; region_code: string; region_name: string; created: boolean }>(
        '/api/v1/reference/regions/ensure-from-country',
        { iso_alpha2: iso }
      ),
    onSuccess: (data) => {
      onRegionIdChange(String(data.region_id));
      void qc.invalidateQueries({ queryKey: DSI_STEWARD_CONFIG.catalogRegionsQueryKey() });
    },
  });

  return (
    <Stack
      direction={{ xs: 'column', sm: 'row' }}
      spacing={1}
      alignItems={{ sm: 'center' }}
      useFlexGap
      flexWrap="wrap"
      data-testid="dsi-country-region-fallback"
    >
      <FormControlLabel
        control={
          <Switch
            checked={enabled}
            onChange={(e) => {
              const on = e.target.checked;
              onEnabledChange(on);
              if (!on) {
                setSelectedIso('');
                onRegionIdChange('');
              }
            }}
            disabled={disabled}
            data-testid="dsi-region-fallback-enable"
          />
        }
        label={
          <Typography variant="body2" component="span">
            Operating region fallback
          </Typography>
        }
      />
      <FormControl
        size="small"
        sx={{ minWidth: 280 }}
        disabled={!enabled || disabled || ensureRegion.isPending}
      >
        <InputLabel id="dsi-country-fallback-select">Country (plan only)</InputLabel>
        <Select
          labelId="dsi-country-fallback-select"
          label="Country (plan only)"
          value={enabled ? selectedIso : ''}
          onChange={(e) => {
            const iso = String(e.target.value);
            setSelectedIso(iso);
            ensureRegion.reset();
            if (!iso) {
              onRegionIdChange('');
              return;
            }
            const existing = catalogRegions.find((r) => r.code.trim().toUpperCase() === iso.toUpperCase());
            if (existing) {
              onRegionIdChange(String(existing.id));
              return;
            }
            void ensureRegion.mutateAsync(iso).catch(() => {});
          }}
          data-testid="dsi-country-fallback-select"
        >
          <MenuItem value="">
            <em>Select country…</em>
          </MenuItem>
          {countries.map((c) => (
            <MenuItem key={c.alpha2} value={c.alpha2}>
              {c.name} ({c.alpha2})
            </MenuItem>
          ))}
        </Select>
      </FormControl>
      {enabled ? (
        <Typography variant="caption" color="text.secondary" sx={{ maxWidth: 400 }}>
          Plan-level default when province is empty — does not map channel to region. Revalidate after steward
          catalog work.
        </Typography>
      ) : null}
      {ensureRegion.isError ? (
        <Alert severity="error" sx={{ width: '100%' }}>
          {safeDisplayError(ensureRegion.error) || 'Could not ensure region for selected country.'}
        </Alert>
      ) : null}
    </Stack>
  );
}
