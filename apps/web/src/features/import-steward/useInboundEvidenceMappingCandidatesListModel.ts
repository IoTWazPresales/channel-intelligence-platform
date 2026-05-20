'use client';

import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';

import { apiGet } from '@/lib/api';

import { inboundEvidenceMappingCandidatesListDomain } from './inboundEvidenceMappingCandidates.domain';
import type { InboundEvidenceMappingCandidateRow } from './inboundEvidenceMappingCandidateWorkspaceColumns';

/**
 * Fetches inbound evidence mapping candidates + derives open (non-terminal) rows.
 * Intended for future `ImportStewardCandidateWorkspace` wiring (not used by shipment steward yet).
 */
export function useInboundEvidenceMappingCandidatesListModel(importJobId: number | null) {
  const d = inboundEvidenceMappingCandidatesListDomain;

  const candidatesQuery = useQuery({
    queryKey: importJobId != null ? d.candidatesQueryKey(importJobId) : ['inbound-evidence-mapping-candidates', 'disabled'],
    queryFn: ({ signal }) => apiGet<InboundEvidenceMappingCandidateRow[]>(d.candidatesUrl(importJobId!), { signal }),
    enabled: importJobId != null,
  });

  const openRows = useMemo(() => {
    const raw = candidatesQuery.data ?? [];
    return raw.filter((r) => !d.terminalStatuses.has((r.status || '').trim()));
  }, [candidatesQuery.data, d]);

  return {
    listDomain: d,
    rawRows: candidatesQuery.data ?? [],
    openRows,
    ...candidatesQuery,
  };
}
