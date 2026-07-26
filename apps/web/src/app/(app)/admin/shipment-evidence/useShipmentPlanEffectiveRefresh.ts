'use client';

import { useMutation } from '@tanstack/react-query';
import { useMemo } from 'react';

import { apiPost } from '@/lib/api';

import type { StewardPlanRowOverride } from '@/features/import-steward/stewardEngine.types';

/** Shipment plan toolbar — effective refresh without DSI geo / global-suspicious compose. */
export function useShipmentPlanEffectiveRefresh({
  importJobId,
  candidateIds,
  effectivePlanPath,
  planOverrideMap,
  replaceResolutionPlan,
}: {
  importJobId: number;
  candidateIds: number[];
  effectivePlanPath: (importJobId: number) => string;
  planOverrideMap: Record<number, StewardPlanRowOverride>;
  replaceResolutionPlan: (data: Record<string, unknown>) => void;
}) {
  const pageCandidateIds = useMemo(() => [...candidateIds], [candidateIds]);

  const refreshPlanEffective = useMutation({
    mutationFn: async () => {
      const overrides = Object.entries(planOverrideMap).map(([cid, o]) => ({
        candidate_id: Number(cid),
        ...o,
      }));
      return apiPost<Record<string, unknown>>(effectivePlanPath(importJobId), {
        candidate_ids: pageCandidateIds,
        overrides,
      });
    },
    onSuccess: (data) => {
      replaceResolutionPlan(data);
    },
  });

  return { refreshPlanEffective };
}
