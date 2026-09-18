'use client';

import { Alert, Typography } from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { SettlementConfirmDialog } from '@/features/settlement/SettlementConfirmDialog';
import { apiGet, apiPost, apiPostFormData } from '@/lib/api';

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

  if (detailQ.isLoading || settlementQ.isLoading) {
    return <Typography sx={{ p: 2 }}>Loading…</Typography>;
  }
  if (detailQ.isError || !detailQ.data) {
    return <Alert severity="error">{String((detailQ.error as Error)?.message ?? 'Failed to load case')}</Alert>;
  }
  if (settlementQ.isError || !settlementQ.data) {
    return (
      <Alert severity="error">
        {String((settlementQ.error as Error)?.message ?? 'Failed to load settlement')}
      </Alert>
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
      <SettlementDesk
        view={view}
        embedded={embedded}
        uploading={importClaims.isPending}
        settling={settle.isPending}
        onUploadCustomerReport={(file) => importClaims.mutate(file)}
        onSettle={view.canSettle ? () => setSettleOpen(true) : undefined}
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
