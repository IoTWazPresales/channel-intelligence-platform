'use client';

import { Alert, CircularProgress } from '@mui/material';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { apiGet, apiPost, safeDisplayError } from '@/lib/api';

import { ReplenishmentView } from './ReplenishmentView';
import type { ReplenishmentViewData, SiteCandidateRow } from './types';

export function ReplenishmentBoard() {
  const queryClient = useQueryClient();
  const [customerId, setCustomerId] = useState<number | null>(null);
  const [decisionError, setDecisionError] = useState<string | null>(null);
  const customers = useQuery({
    queryKey: ['store-dc-customers'],
    queryFn: ({ signal }) => apiGet<{ customers: { id: number; code: string; name: string }[] }>('/api/v1/store-dc/customers', { signal }),
  });
  const selected = customerId ?? customers.data?.customers[0]?.id ?? null;
  const view = useQuery({
    queryKey: ['store-dc-customer', selected],
    enabled: selected != null,
    queryFn: ({ signal }) => apiGet<ReplenishmentViewData>(`/api/v1/store-dc/customers/${selected}`, { signal }),
  });
  const candidateQuery = useQuery({
    queryKey: ['store-dc-candidates'],
    queryFn: ({ signal }) => apiGet<{ candidates: SiteCandidateRow[] }>('/api/v1/store-dc/candidates', { signal }),
  });

  async function onDecide(id: number, decision: 'confirm' | 'reject') {
    setDecisionError(null);
    try {
      await apiPost(`/api/v1/store-dc/candidates/${id}/decision`, { decision });
      await queryClient.invalidateQueries({ queryKey: ['store-dc-candidates'] });
      await queryClient.invalidateQueries({ queryKey: ['store-dc-customer'] });
    } catch (error) {
      setDecisionError(safeDisplayError(error));
    }
  }

  if (customers.isLoading) return <CircularProgress size={18} />;
  if (customers.isError) return <Alert severity="error">{safeDisplayError(customers.error)}</Alert>;

  return (
    <ReplenishmentView
      customers={customers.data?.customers ?? []}
      customerId={selected}
      onSelect={setCustomerId}
      view={view.data ?? null}
      candidates={candidateQuery.data?.candidates ?? []}
      onDecide={(id, decision) => void onDecide(id, decision)}
      decisionError={decisionError}
    />
  );
}
