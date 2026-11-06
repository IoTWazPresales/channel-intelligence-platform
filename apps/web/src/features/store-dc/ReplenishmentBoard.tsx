'use client';

import { Alert, CircularProgress } from '@mui/material';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { apiGet, apiPost, apiPut, safeDisplayError } from '@/lib/api';

import { ReplenishmentView } from './ReplenishmentView';
import type {
  CustomerThresholds,
  LeadTimesPayload,
  ReplenishmentViewData,
  SiteCandidateRow,
  StoreDcConfig,
  StoreDcConfigInput,
  ThresholdInput,
} from './types';

type RefreshResult = {
  inserted: number;
  open_questions: number;
  locations_created: number;
};

export function ReplenishmentBoard() {
  const queryClient = useQueryClient();
  const [customerId, setCustomerId] = useState<number | null>(null);
  const [decisionError, setDecisionError] = useState<string | null>(null);
  const [refreshNote, setRefreshNote] = useState<string | null>(null);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  const [configError, setConfigError] = useState<string | null>(null);
  const [thresholdError, setThresholdError] = useState<string | null>(null);
  const [servedError, setServedError] = useState<string | null>(null);
  const [savedThresholds, setSavedThresholds] = useState<Record<number, CustomerThresholds>>({});
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
  const configQuery = useQuery({
    queryKey: ['store-dc-config'],
    queryFn: ({ signal }) => apiGet<StoreDcConfig>('/api/v1/store-dc/config', { signal }),
  });
  const leadQuery = useQuery({
    queryKey: ['store-dc-lead-times', selected],
    enabled: selected != null,
    queryFn: ({ signal }) =>
      apiGet<LeadTimesPayload>(`/api/v1/store-dc/lead-times?customer_id=${selected}`, { signal }),
  });

  const shownView: ReplenishmentViewData | null = view.data
    ? {
        ...view.data,
        ...(leadQuery.data
          ? {
              lead_times: leadQuery.data.lead_times,
              lead_time_min_deliveries: leadQuery.data.lead_time_min_deliveries,
            }
          : {}),
      }
    : null;

  async function invalidateReads() {
    await queryClient.invalidateQueries({ queryKey: ['store-dc-candidates'] });
    await queryClient.invalidateQueries({ queryKey: ['store-dc-customer'] });
    await queryClient.invalidateQueries({ queryKey: ['store-dc-lead-times'] });
  }

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

  async function onRefresh() {
    setRefreshError(null);
    setRefreshNote(null);
    try {
      const result = await apiPost<RefreshResult>('/api/v1/store-dc/candidates/refresh');
      setRefreshNote(`New questions: ${result.inserted}. Open questions: ${result.open_questions}.`);
      await invalidateReads();
    } catch (error) {
      setRefreshError(safeDisplayError(error));
    }
  }

  async function onSaveConfig(body: StoreDcConfigInput) {
    setConfigError(null);
    try {
      const saved = await apiPut<StoreDcConfig>('/api/v1/store-dc/config', body);
      queryClient.setQueryData(['store-dc-config'], saved);
      await queryClient.invalidateQueries({ queryKey: ['store-dc-customer'] });
      await queryClient.invalidateQueries({ queryKey: ['store-dc-lead-times'] });
    } catch (error) {
      setConfigError(safeDisplayError(error));
    }
  }

  async function onSaveThresholds(body: ThresholdInput) {
    if (selected == null) return;
    setThresholdError(null);
    try {
      const saved = await apiPut<CustomerThresholds>(`/api/v1/store-dc/customers/${selected}/thresholds`, body);
      setSavedThresholds((current) => ({ ...current, [saved.customer_id]: saved }));
      await queryClient.invalidateQueries({ queryKey: ['store-dc-customer', selected] });
    } catch (error) {
      setThresholdError(safeDisplayError(error));
    }
  }

  async function onAssignServed(candidateId: number, customerIds: number[]) {
    setServedError(null);
    try {
      await apiPut(`/api/v1/store-dc/candidates/${candidateId}/served-accounts`, { customer_ids: customerIds });
      await queryClient.invalidateQueries({ queryKey: ['store-dc-customer'] });
    } catch (error) {
      setServedError(safeDisplayError(error));
    }
  }

  if (customers.isLoading) return <CircularProgress size={18} />;
  if (customers.isError) return <Alert severity="error">{safeDisplayError(customers.error)}</Alert>;

  return (
    <ReplenishmentView
      customers={customers.data?.customers ?? []}
      customerId={selected}
      onSelect={setCustomerId}
      view={shownView}
      candidates={candidateQuery.data?.candidates ?? []}
      onDecide={(id, decision) => void onDecide(id, decision)}
      decisionError={decisionError}
      onRefresh={() => void onRefresh()}
      refreshNote={refreshNote}
      refreshError={refreshError}
      config={configQuery.data ?? null}
      onSaveConfig={(body) => void onSaveConfig(body)}
      configError={configError ?? (configQuery.isError ? safeDisplayError(configQuery.error) : null)}
      savedThresholds={selected != null ? savedThresholds[selected] ?? null : null}
      onSaveThresholds={(body) => void onSaveThresholds(body)}
      thresholdError={thresholdError}
      onAssignServed={(candidateId, customerIds) => void onAssignServed(candidateId, customerIds)}
      servedError={servedError}
      onReloadLeadTimes={selected != null ? () => void leadQuery.refetch() : undefined}
      leadTimeError={leadQuery.isError ? safeDisplayError(leadQuery.error) : null}
    />
  );
}
