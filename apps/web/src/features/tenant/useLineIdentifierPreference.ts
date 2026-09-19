'use client';

import { useQuery } from '@tanstack/react-query';

import { apiGet } from '@/lib/api';

import {
  lineIdentifierHeader,
  lineIdentifierValue,
  type LineIdentifierPreference,
} from './lineIdentifier';

type TenantCommercialProfile = {
  line_identifier_preference?: LineIdentifierPreference;
};

export function useLineIdentifierPreference(): {
  preference: LineIdentifierPreference;
  header: string;
  value: (sku: string | null | undefined, salesModel: string | null | undefined) => string;
} {
  const { data } = useQuery({
    queryKey: ['auth', 'tenant-commercial-profile'],
    queryFn: ({ signal }) =>
      apiGet<TenantCommercialProfile>('/api/v1/auth/tenant-commercial-profile', { signal }),
    staleTime: 60_000,
  });
  const preference: LineIdentifierPreference =
    data?.line_identifier_preference === 'sales_model' ? 'sales_model' : 'sku';
  return {
    preference,
    header: lineIdentifierHeader(preference),
    value: (sku, salesModel) => lineIdentifierValue(preference, sku, salesModel),
  };
}
