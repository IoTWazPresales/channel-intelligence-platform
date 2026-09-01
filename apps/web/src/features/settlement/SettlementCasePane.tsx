'use client';

import { Box, Button, Stack, Typography } from '@mui/material';
import { alpha, useTheme } from '@mui/material/styles';
import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';

import { CporFxAnchorPanel } from '@/features/cpor/CporFxAnchorPanel';
import { CporSettleReadinessRow } from '@/features/cpor/CporSettleReadinessRow';
import type { SettleReadiness } from '@/features/cpor/fxDisplay';
import { apiGet } from '@/lib/api';

type CaseDetail = {
  id: number;
  case_code: string;
  customer_code: string | null;
  customer_name: string | null;
  promotion_type: string;
  status: string;
  outstanding_amount?: number | null;
  owed_amount?: number | null;
  paid_amount_sum?: number | null;
  currency_code?: string;
  roe_snapshot?: number | null;
  settle_readiness?: SettleReadiness;
  missing_roe?: boolean;
};

type Props = {
  caseId: number | null;
};

export function SettlementCasePane({ caseId }: Props) {
  const theme = useTheme();
  const { data, isLoading, isError } = useQuery({
    queryKey: ['cpor', 'case', caseId],
    queryFn: ({ signal }) => apiGet<CaseDetail>(`/api/v1/cpor/cases/${caseId}`, { signal }),
    enabled: caseId != null,
  });

  if (!caseId) {
    return (
      <Box
        data-testid="settlement-case-empty"
        sx={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          height: '100%',
          minHeight: 240,
          color: alpha(theme.palette.text.primary, 0.45),
          borderLeft: `1px solid ${alpha(theme.palette.common.white, 0.12)}`,
        }}
      >
        <Typography variant="body2">Select a case from the queue</Typography>
      </Box>
    );
  }

  return (
    <Box
      data-testid="settlement-case-pane"
      sx={{
        height: '100%',
        overflow: 'auto',
        borderLeft: `1px solid ${alpha(theme.palette.common.white, 0.12)}`,
        minHeight: 0,
        p: 2,
      }}
    >
      {isLoading ? <Typography variant="body2">Loading case…</Typography> : null}
      {isError ? <Typography color="error">Failed to load case</Typography> : null}
      {data ? (
        <Stack spacing={1.5}>
          <Typography variant="overline" color="text.secondary">
            Case record
          </Typography>
          <Typography variant="h6" data-testid="settlement-case-title">
            {data.case_code}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {data.customer_code} — {data.customer_name} · {data.promotion_type} · {data.status}
          </Typography>
          <CporFxAnchorPanel
            localLabel="Outstanding"
            localAmount={data.outstanding_amount ?? data.owed_amount}
            currencyCode={data.currency_code ?? 'ZAR'}
            missingRoe={data.missing_roe}
            roeSnapshot={data.roe_snapshot}
          />
          {data.settle_readiness ? (
            <CporSettleReadinessRow readiness={data.settle_readiness} testIdPrefix="settlement-case-readiness" />
          ) : null}
          <Button
            component={Link}
            variant="outlined"
            size="small"
            href={`/commercial-planner/cpor-cases/${caseId}`}
            data-testid="settlement-case-open-full"
          >
            Open full record
          </Button>
        </Stack>
      ) : null}
    </Box>
  );
}
