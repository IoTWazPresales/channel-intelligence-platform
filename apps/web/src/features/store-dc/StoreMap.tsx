'use client';

import { Box, Button, TextField, Typography } from '@mui/material';
import { useTheme } from '@mui/material/styles';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useMemo, useState } from 'react';

import { apiGet, apiPost, safeDisplayError } from '@/lib/api';
import { tokensFor } from '@/theme/cipTokens';

import { projectStores, sellThroughColor, spreadOverlaps } from './storeMapLayout';
import type { StoreMapPayload, StoreMapStore } from './types';

function fmt(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '—';
  return Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function storeKey(store: StoreMapStore): string {
  return `${store.customer_id}:${store.site_label}`;
}

export function StoreMap() {
  const theme = useTheme();
  const tokens = tokensFor(theme.palette.mode);
  const queryClient = useQueryClient();
  const [customerId, setCustomerId] = useState<number | 'all'>('all');
  const [hoverKey, setHoverKey] = useState<string | null>(null);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [pinFor, setPinFor] = useState<string | null>(null);
  const [latitude, setLatitude] = useState('');
  const [longitude, setLongitude] = useState('');
  const [pinError, setPinError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const mapQuery = useQuery({
    queryKey: ['store-dc-map'],
    queryFn: ({ signal }) => apiGet<StoreMapPayload>('/api/v1/store-dc/map', { signal }),
    staleTime: 30_000,
  });

  const card = {
    bgcolor: tokens.bg.surface,
    border: `1px solid ${tokens.border.subtle}`,
    borderRadius: 1.5,
    p: 2,
  } as const;

  const stores = mapQuery.data?.stores ?? [];
  const visible = customerId === 'all' ? stores : stores.filter((store) => store.customer_id === customerId);
  const pinned = visible.filter((store) => store.pinned && store.latitude != null && store.longitude != null);
  const unpinned = visible.filter((store) => !store.pinned);
  const projected = useMemo(
    () =>
      projectStores(
        pinned.map((store) => ({
          id: storeKey(store),
          latitude: store.latitude as number,
          longitude: store.longitude as number,
        })),
      ),
    [pinned],
  );
  const placed = spreadOverlaps(projected);
  const placeOf = new Map(placed.map((pin) => [pin.id, pin]));
  const selected = visible.find((store) => storeKey(store) === selectedKey) ?? null;
  const hover = visible.find((store) => storeKey(store) === hoverKey) ?? null;

  async function savePin(store: StoreMapStore) {
    const lat = Number(latitude);
    const lon = Number(longitude);
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
      setPinError('Enter both coordinates.');
      return;
    }
    setSaving(true);
    setPinError(null);
    try {
      await apiPost('/api/v1/store-dc/pins', {
        customer_id: store.customer_id,
        site_label: store.site_label,
        latitude: lat,
        longitude: lon,
      });
      setPinFor(null);
      setLatitude('');
      setLongitude('');
      await queryClient.invalidateQueries({ queryKey: ['store-dc-map'] });
    } catch (error) {
      setPinError(safeDisplayError(error));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Box data-testid="store-map" sx={{ mt: 1.5, ...card }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 1, flexWrap: 'wrap', mb: 1 }}>
        <Typography variant="subtitle1">Stores</Typography>
        <Box data-testid="store-map-legend" sx={{ display: 'flex', alignItems: 'center', gap: 1, minWidth: 180 }}>
          <Typography variant="caption" sx={{ color: tokens.text.secondary }}>
            Worst
          </Typography>
          <Box
            sx={{
              flex: 1,
              height: 8,
              borderRadius: 4,
              background: `linear-gradient(90deg, ${tokens.semantic.danger}, ${tokens.semantic.success})`,
            }}
          />
          <Typography variant="caption" sx={{ color: tokens.text.secondary }}>
            Best
          </Typography>
        </Box>
      </Box>
      <Typography variant="caption" sx={{ display: 'block', color: tokens.text.muted, mb: 1 }}>
        {mapQuery.data?.legend?.formula ?? "last week's units / (last week's units + stock on hand)"}
      </Typography>
      {mapQuery.isLoading ? (
        <Typography variant="body2" sx={{ color: tokens.text.secondary }} data-testid="store-map-loading">
          Loading stores.
        </Typography>
      ) : null}
      {mapQuery.isError ? (
        <Typography variant="body2" color="error">
          Store map could not be loaded: {safeDisplayError(mapQuery.error)}
        </Typography>
      ) : null}
      <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap', mb: 1 }} data-testid="store-map-customers">
        <Button size="small" variant={customerId === 'all' ? 'contained' : 'outlined'} onClick={() => setCustomerId('all')}>
          All customers
        </Button>
        {(mapQuery.data?.customers ?? []).map((customer) => (
          <Button
            key={customer.id}
            size="small"
            variant={customerId === customer.id ? 'contained' : 'outlined'}
            onClick={() => setCustomerId(customer.id)}
          >
            {customer.name}
          </Button>
        ))}
      </Box>
      <Box sx={{ display: 'grid', gap: 1.5, gridTemplateColumns: { xs: '1fr', md: 'minmax(0, 1fr) 260px' } }}>
        <Box
          data-testid="store-map-canvas"
          sx={{
            position: 'relative',
            height: { xs: 220, md: 320 },
            borderRadius: 1,
            bgcolor: tokens.bg.surfaceMuted,
            border: `1px solid ${tokens.border.subtle}`,
          }}
        >
          {pinned.length === 0 ? (
            <Typography variant="body2" sx={{ p: 2, color: tokens.text.secondary }}>
              No store has coordinates yet.
            </Typography>
          ) : null}
          {pinned.map((store) => {
            const pin = placeOf.get(storeKey(store));
            if (!pin) return null;
            const color = sellThroughColor(store.sell_through, tokens.semantic.success, tokens.semantic.danger);
            return (
              <Box
                key={storeKey(store)}
                component="button"
                type="button"
                data-testid="store-dot"
                data-customer-id={store.customer_id}
                aria-label={`${store.site_label}, ${store.customer_name ?? ''}`}
                onMouseEnter={() => setHoverKey(storeKey(store))}
                onMouseLeave={() => setHoverKey((current) => (current === storeKey(store) ? null : current))}
                onClick={() => setSelectedKey(storeKey(store))}
                sx={{
                  position: 'absolute',
                  left: `${pin.x}%`,
                  top: `${pin.y}%`,
                  width: 14,
                  height: 14,
                  transform: `translate(calc(-50% + ${pin.dx}px), calc(-50% + ${pin.dy}px))`,
                  borderRadius: '50%',
                  border: `2px solid ${tokens.bg.surface}`,
                  bgcolor: color,
                  p: 0,
                  cursor: 'pointer',
                }}
              />
            );
          })}
          {hover ? (
            <Box
              data-testid="store-map-hover"
              sx={{
                position: 'absolute',
                left: 8,
                bottom: 8,
                maxWidth: '90%',
                px: 1,
                py: 0.75,
                borderRadius: 1,
                bgcolor: tokens.bg.elevated,
                border: `1px solid ${tokens.border.strong}`,
                color: tokens.text.primary,
                fontSize: 12,
              }}
            >
              <div>{hover.site_label}</div>
              <div>{hover.customer_name}</div>
              <div>Last week {fmt(hover.last_week_units)} units</div>
              <div>Stock on hand {fmt(hover.stock_on_hand)}</div>
              <div>Weeks of cover {fmt(hover.weeks_of_cover)}</div>
            </Box>
          ) : null}
        </Box>
        <Box data-testid="store-map-unpinned">
          <Typography variant="caption" sx={{ color: tokens.text.secondary }}>
            No coordinates
          </Typography>
          {unpinned.length === 0 ? (
            <Typography variant="body2" sx={{ color: tokens.text.muted, mt: 0.5 }}>
              Every store in this view has a pin.
            </Typography>
          ) : (
            unpinned.map((store) => {
              const key = storeKey(store);
              return (
                <Box key={key} sx={{ mt: 1 }}>
                  <Typography variant="body2">
                    {store.site_label}
                    <Box component="span" sx={{ color: tokens.text.secondary }}>
                      {' '}
                      · {store.customer_name}
                    </Box>
                  </Typography>
                  <Button size="small" data-testid="drop-pin" onClick={() => { setPinFor(key); setPinError(null); }}>
                    Drop pin
                  </Button>
                  {pinFor === key ? (
                    <Box sx={{ display: 'grid', gap: 0.5, mt: 0.5 }}>
                      <TextField
                        size="small"
                        label="Latitude"
                        value={latitude}
                        onChange={(event) => setLatitude(event.target.value)}
                        inputProps={{ 'data-testid': 'pin-latitude' }}
                      />
                      <TextField
                        size="small"
                        label="Longitude"
                        value={longitude}
                        onChange={(event) => setLongitude(event.target.value)}
                        inputProps={{ 'data-testid': 'pin-longitude' }}
                      />
                      {pinError ? (
                        <Typography variant="caption" color="error">
                          {pinError}
                        </Typography>
                      ) : null}
                      <Button size="small" variant="contained" disabled={saving} onClick={() => void savePin(store)}>
                        Save pin
                      </Button>
                    </Box>
                  ) : null}
                </Box>
              );
            })
          )}
        </Box>
      </Box>
      {selected ? (
        <Box data-testid="store-map-lines" sx={{ mt: 1.5 }}>
          <Typography variant="subtitle2">
            {selected.site_label} · {selected.customer_name}
          </Typography>
          {selected.lines.length === 0 ? (
            <Typography variant="body2" sx={{ color: tokens.text.secondary }}>
              No product lines for this store.
            </Typography>
          ) : (
            selected.lines.map((line) => (
              <Typography key={line.product_id} variant="body2" data-testid="store-line">
                {line.sku ?? line.product_name} · {fmt(line.units)} units · stock {fmt(line.stock_on_hand)} · cover {fmt(line.weeks_of_cover)}
              </Typography>
            ))
          )}
        </Box>
      ) : null}
    </Box>
  );
}
