import { useQuery } from '@tanstack/react-query';

import type { NetRequirementResponse } from '@/features/lineup/lineupTypes';
import { apiGet } from '@/lib/api';

/**
 * The line-up page reads net requirement in several places (headline strip, regime strip, plan
 * action bar). They all use this one key and request, so a given parameter set is fetched once
 * and shared instead of once per component.
 */
const LIMIT = 200;

export function lineupNetRequirementQueryKey(applyBias: boolean) {
  return ['lineup-net-requirement', { limit: LIMIT, includeCustomerShares: false, applyBias }] as const;
}

export function lineupNetRequirementUrl(applyBias: boolean) {
  return `/api/v1/lineup/net-requirement?limit=${LIMIT}&include_customer_shares=false&apply_bias=${applyBias ? 'true' : 'false'}`;
}

export function useLineupNetRequirement(applyBias = true) {
  return useQuery({
    queryKey: lineupNetRequirementQueryKey(applyBias),
    queryFn: ({ signal }) => apiGet<NetRequirementResponse>(lineupNetRequirementUrl(applyBias), { signal }),
    staleTime: 60_000,
  });
}
