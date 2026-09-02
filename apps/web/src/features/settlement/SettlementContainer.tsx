'use client';

import { Box } from '@mui/material';
import { alpha, useTheme } from '@mui/material/styles';
import { useQueryClient } from '@tanstack/react-query';
import { useSearchParams } from 'next/navigation';
import { Suspense, useEffect, useState, type ReactNode } from 'react';

import { SettlementBookRead } from '@/features/settlement/SettlementBookRead';
import { SettlementCasePane } from '@/features/settlement/SettlementCasePane';
import { SettlementRegimeStrip } from '@/features/settlement/SettlementRegimeStrip';
import { SettlementScopeBar } from '@/features/settlement/SettlementScopeBar';
import { SettlementTaskCrumb } from '@/features/settlement/SettlementTaskCrumb';
import { DEFAULT_SETTLEMENT_SCOPE, type SettlementScope } from '@/features/settlement/settlementViews';
import { apiGet } from '@/lib/api';

import type { SettlementBookRead as SettlementBookReadType } from '@/features/settlement/SettlementRegimeStrip';

type Props = {
  queue: ReactNode;
};

function SettlementContainerInner({ queue }: Props) {
  const theme = useTheme();
  const line = alpha(theme.palette.common.white, 0.12);
  const searchParams = useSearchParams();
  const qc = useQueryClient();
  const caseParam = searchParams.get('case');
  const selectedCaseId = caseParam && /^\d+$/.test(caseParam) ? Number(caseParam) : null;
  const [scope, setScope] = useState<SettlementScope>(DEFAULT_SETTLEMENT_SCOPE);

  useEffect(() => {
    void qc.prefetchQuery({
      queryKey: ['cpor', 'settlement', 'book'],
      queryFn: ({ signal }) => apiGet<SettlementBookReadType>('/api/v1/cpor/settlement/book', { signal }),
      staleTime: 30_000,
    });
  }, [qc]);

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0 }} data-testid="settlement-container">
      <Box
        sx={{
          display: 'flex',
          alignItems: 'baseline',
          justifyContent: 'space-between',
          gap: 2,
          px: 2.75,
          py: 1.25,
          borderBottom: `1px solid ${line}`,
          flexWrap: 'wrap',
        }}
      >
        <SettlementTaskCrumb />
        <SettlementRegimeStrip />
      </Box>
      <SettlementScopeBar scope={scope} onScopeChange={(next) => setScope((s) => ({ ...s, ...next }))} />
      <Box sx={{ px: 2.75, py: 1.5, borderBottom: `1px solid ${line}`, bgcolor: '#1a1d23' }}>
        <SettlementBookRead />
      </Box>
      <Box
        sx={{
          flex: 1,
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', lg: '56% 44%' },
          minHeight: 0,
          overflow: 'hidden',
        }}
      >
        <Box
          data-testid="settlement-queue-pane"
          sx={{ overflow: 'auto', minHeight: 0, p: { xs: 1, md: 2 } }}
        >
          {queue}
        </Box>
        <SettlementCasePane caseId={selectedCaseId} />
      </Box>
    </Box>
  );
}

export function SettlementContainer({ queue }: Props) {
  return (
    <Suspense fallback={<Box sx={{ p: 3 }}>Loading Settlement…</Box>}>
      <SettlementContainerInner queue={queue} />
    </Suspense>
  );
}
