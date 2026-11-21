'use client';

import { useQuery } from '@tanstack/react-query';

import { useCurrentUser } from '@/features/shell/useCurrentUser';
import type { MapSettings } from '@/features/workbench-ui/map/style';
import { apiGet } from '@/lib/api';

export type TenantSettingsPayload = {
  settings: Record<string, unknown>;
  known_keys: string[];
};

export const MAP_SETTING_FIELDS = [
  {
    key: 'map.tilejson_url',
    label: 'TileJSON URL',
    help: 'Public HTTP(S) TileJSON URL for OpenMapTiles-schema vector tiles. No API keys or credentials.',
  },
  {
    key: 'map.glyphs_url',
    label: 'Glyph URL template',
    help: 'Font URL containing {fontstack} and {range}; the provider must supply Noto Sans Regular.',
  },
  {
    key: 'map.attribution',
    label: 'Additional map attribution',
    help: 'Plain-text provider attribution. OpenStreetMap and TileJSON attribution remain visible.',
  },
] as const;

export function readMapSettings(values: Record<string, unknown>): MapSettings {
  const text = (key: string) => typeof values[key] === 'string'
    ? String(values[key]).trim() || undefined
    : undefined;
  return {
    tilejsonUrl: text('map.tilejson_url'),
    glyphsUrl: text('map.glyphs_url'),
    attribution: text('map.attribution'),
  };
}

export function useMapSettings() {
  const identity = useCurrentUser();
  const queryKey = [
    'tenant-settings', 'map', identity.data?.tenant_id ?? null, identity.data?.id ?? null,
  ] as const;
  const query = useQuery({
    queryKey,
    queryFn: ({ signal }) => apiGet<TenantSettingsPayload>('/api/v1/tenant-settings', { signal }),
    enabled: !!identity.data,
    staleTime: 30_000,
    retry: false,
  });
  const role = String(identity.data?.role ?? '').toLowerCase();
  return {
    query,
    queryKey,
    settings: readMapSettings(query.data?.settings ?? {}),
    pending: identity.isPending || (identity.isSuccess && query.isPending),
    error: identity.error ?? query.error,
    canEdit: ['admin', 'steward', 'data_steward'].includes(role),
  };
}
