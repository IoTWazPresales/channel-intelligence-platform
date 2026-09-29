'use client';

import { useQuery } from '@tanstack/react-query';
import type { ColDef } from 'ag-grid-community';
import { useMemo } from 'react';

import { apiGet } from '@/lib/api';

import {
  lineIdentifierColumns,
  lineIdentifierHeader,
  lineIdentifierHeaders,
  lineIdentifierValue,
  lineIdentifierValues,
  parseLineIdentifierPreference,
  type LineIdentifierFields,
  type LineIdentifierPreference,
} from './lineIdentifier';

type TenantCommercialProfile = {
  line_identifier_preference?: LineIdentifierPreference;
};

export type LineIdentifierApi = {
  preference: LineIdentifierPreference;
  /** Single text-slot header (`SKU`, `Sales model`, or `SKU · Sales model`). */
  header: string;
  /** Single text-slot value with fallback; `both` welds `sku · model`. */
  value: (sku: string | null | undefined, salesModel: string | null | undefined) => string;
  /** One header per rendered column — for MUI tables. */
  headers: string[];
  /** One value per rendered column, aligned with `headers` — for MUI tables. */
  values: (sku: string | null | undefined, salesModel: string | null | undefined) => string[];
  /** Identity ColDef(s) for an AG Grid host: one welded column, or two field columns under `both`. */
  columns: <T>(fields: LineIdentifierFields, base?: Partial<ColDef<T>>) => ColDef<T>[];
};

export function useLineIdentifierPreference(): LineIdentifierApi {
  const { data } = useQuery({
    queryKey: ['auth', 'tenant-commercial-profile'],
    queryFn: ({ signal }) =>
      apiGet<TenantCommercialProfile>('/api/v1/auth/tenant-commercial-profile', { signal }),
    staleTime: 60_000,
  });
  const preference = parseLineIdentifierPreference(data?.line_identifier_preference);
  return useMemo<LineIdentifierApi>(
    () => ({
      preference,
      header: lineIdentifierHeader(preference),
      value: (sku, salesModel) => lineIdentifierValue(preference, sku, salesModel),
      headers: lineIdentifierHeaders(preference),
      values: (sku, salesModel) => lineIdentifierValues(preference, sku, salesModel),
      columns: (fields, base) => lineIdentifierColumns(preference, fields, base),
    }),
    [preference],
  );
}
