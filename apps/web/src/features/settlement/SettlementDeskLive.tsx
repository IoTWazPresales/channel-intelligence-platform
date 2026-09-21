'use client';

import { Alert } from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { CporCaseSupersedeDialog } from '@/features/cpor/CporCaseSupersedeDialog';
import { SettlementConfirmDialog } from '@/features/settlement/SettlementConfirmDialog';
import { apiGet, apiPost, apiPostFormData } from '@/lib/api';

import { ModuleDataSection } from '@/components/ModuleDataSection';
import { SettlementDesk } from './SettlementDesk';
import {
  mapSettlementDeskView,
  type SettlementDeskApi,
  type SettlementDeskCase,
} from './mapSettlementDeskView';

type Props = {
  caseId: number;
  embedded?: boolean;
};

export function SettlementDeskLive({ caseId, embedded = false }: Props) {
  const qc = useQueryClient();
  const [settleOpen, setSettleOpen] = useState(false);
  const [supersedeOpen, setSupersedeOpen] = useState(false);

  const detailQ = useQuery({
    queryKey: ['cpor', 'case', caseId],
    queryFn: ({ signal }) => apiGet<SettlementDeskCase>(`/api/v1/cpor/cases/${caseId}`, { signal }),
    enabled: caseId > 0,
  });

  const settlementQ = useQuery({
    queryKey: ['cpor', 'settlement', caseId],
    queryFn: ({ signal }) =>
      apiGet<SettlementDeskApi>(`/api/v1/cpor/cases/${caseId}/settlement`, { signal }),
    enabled: caseId > 0,
  });

  const importClaims = useMutation({
    mutationFn: (file: File) => {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('include_out_of_window', 'false');
      return apiPostFormData(`/api/v1/cpor/cases/${caseId}/claim-evidence/import`, fd);
    },
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['cpor', 'case', caseId] });
      await qc.invalidateQueries({ queryKey: ['cpor', 'settlement', caseId] });
    },
  });

  const settle = useMutation({
    mutationFn: () => apiPost(`/api/v1/cpor/cases/${caseId}/transition`, { action: 'settle' }),
    onSuccess: async () => {
      setSettleOpen(false);
      await qc.invalidateQueries({ queryKey: ['cpor', 'case', caseId] });
      await qc.invalidateQueries({ queryKey: ['cpor', 'settlement', caseId] });
      await qc.invalidateQueries({ queryKey: ['cpor', 'settlement', 'book'] });
      await qc.invalidateQueries({ queryKey: ['cpor', 'cases'] });
    },
  });

  const restoreSupersession = useMutation({
    mutationFn: () => apiPost(`/api/v1/cpor/cases/${caseId}/supersede/restore`, { confirm: true }),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['cpor', 'case', caseId] });
      await qc.invalidateQueries({ queryKey: ['cpor', 'settlement', 'book'] });
      await qc.invalidateQueries({ queryKey: ['cpor', 'cases'] });
    },
  });

  // Gate the desk on both queries in the canonical chrome rather than bare text / a bare
  // Alert: this is the same loading box and Retry every other module section shows.
  const gateLoading = detailQ.isLoading || settlementQ.isLoading;
  // Must exclude the loading phase: data is legitimately undefined while in flight, and
  // ModuleDataSection checks isError BEFORE isLoading, so an un-gated !data would paint
  // "Failed to load case" over every first render.
  const gateError =
    !gateLoading &&
    (detailQ.isError || !detailQ.data || settlementQ.isError || !settlementQ.data);
  // The two `!…data` terms repeat gateError on purpose: TypeScript narrows property access in a
  // condition, not through a boolean variable, so this is what lets `detailQ.data` be typed as
  // defined for the rest of the component instead of `T | undefined`.
  if (gateLoading || gateError || !detailQ.data || !settlementQ.data) {
    const gateMessage = detailQ.isError || !detailQ.data
      ? String((detailQ.error as Error)?.message ?? 'Failed to load case')
      : String((settlementQ.error as Error)?.message ?? 'Failed to load settlement');
    return (
      <ModuleDataSection
        isLoading={gateLoading}
        isError={gateError}
        error={gateError ? new Error(gateMessage) : null}
        onRetry={() => {
          void detailQ.refetch();
          void settlementQ.refetch();
        }}
        // A case detail is never "empty" — it either loads or it fails. isEmpty is pinned
        // false and this empty copy is unreachable; it exists to satisfy the contract.
        isEmpty={false}
        empty={{ title: 'Case unavailable', description: 'This case could not be loaded.' }}
        loadingLabel="Loading case…"
      >
        {null}
      </ModuleDataSection>
    );
  }

  const view = mapSettlementDeskView(detailQ.data, settlementQ.data);
  const periodLabel =
    detailQ.data.window_start || detailQ.data.window_end
      ? `${detailQ.data.window_start ?? '…'} → ${detailQ.data.window_end ?? '…'}`
      : undefined;

  return (
    <>
      {importClaims.isError ? (
        <Alert severity="error" sx={{ mb: 1 }}>
          {String((importClaims.error as Error)?.message)}
        </Alert>
      ) : null}
      {settle.isError ? (
        <Alert severity="error" sx={{ mb: 1 }}>
          {String((settle.error as Error)?.message)}
        </Alert>
      ) : null}
      {restoreSupersession.isError ? (
        <Alert severity="error" sx={{ mb: 1 }}>
          {String((restoreSupersession.error as Error)?.message)}
        </Alert>
      ) : null}
      <SettlementDesk
        view={view}
        embedded={embedded}
        uploading={importClaims.isPending}
        settling={settle.isPending}
        onUploadCustomerReport={(file) => importClaims.mutate(file)}
        onSettle={view.canSettle ? () => setSettleOpen(true) : undefined}
        onSupersede={() => setSupersedeOpen(true)}
        onRestoreSupersession={() => restoreSupersession.mutate()}
        restoringSupersession={restoreSupersession.isPending}
      />
      <CporCaseSupersedeDialog
        open={supersedeOpen}
        onClose={() => setSupersedeOpen(false)}
        caseId={caseId}
        caseCode={view.caseCode}
        customerId={detailQ.data.customer_id}
      />
      <SettlementConfirmDialog
        open={settleOpen}
        onClose={() => setSettleOpen(false)}
        onConfirm={() => settle.mutate()}
        confirming={settle.isPending}
        caseCode={view.caseCode}
        customerLabel={view.customerName}
        periodLabel={periodLabel}
        outstandingAmount={view.agreedAmount ?? view.customerAmount ?? view.cipAmount}
        currencyCode={view.currency}
        settleReadiness={settlementQ.data.settle_readiness ?? detailQ.data.settle_readiness}
        claimRowCount={view.claimRowCount}
      />
    </>
  );
}
