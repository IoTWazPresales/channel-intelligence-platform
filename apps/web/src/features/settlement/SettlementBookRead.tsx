'use client';

import { Box, Stack, Typography } from '@mui/material';
import { alpha, useTheme } from '@mui/material/styles';
import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';

import { formatGridMoney } from '@/features/cpor/fxDisplay';
import { SettlementShapeBar } from '@/features/settlement/SettlementShapeBar';
import type { SettlementBookRead } from '@/features/settlement/SettlementRegimeStrip';
import { apiGet } from '@/lib/api';

export function SettlementBookRead() {
  const theme = useTheme();
  const { data, isLoading } = useQuery({
    queryKey: ['cpor', 'settlement', 'book'],
    queryFn: ({ signal }) => apiGet<SettlementBookRead>('/api/v1/cpor/settlement/book', { signal }),
    staleTime: 30_000,
  });

  const seg = data?.shape_segments;
  const ccy = data?.currency_code ?? 'ZAR';

  return (
    <Box data-testid="settlement-book-read">
      <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
        <Typography
          sx={{
            fontSize: '9px',
            letterSpacing: '0.12em',
            textTransform: 'uppercase',
            color: alpha(theme.palette.primary.main, 0.9),
            border: `1px solid ${alpha(theme.palette.primary.main, 0.35)}`,
            px: 0.75,
            py: 0.25,
          }}
        >
          Read
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {isLoading ? 'Loading book…' : data?.read_line ?? '—'}
        </Typography>
      </Stack>
      {seg ? (
        <SettlementShapeBar
          settledPct={seg.settled_pct}
          outstandingPct={seg.outstanding_pct}
          blockedPct={seg.blocked_pct}
        />
      ) : null}
      {data?.concentration?.length ? (
        <Stack spacing={0.5} sx={{ mt: 1.5 }}>
          <Typography variant="caption" color="text.secondary">
            Top outstanding
          </Typography>
          {data.concentration.slice(0, 5).map((row) => (
            <Typography key={row.case_id} variant="body2" sx={{ fontSize: '12px' }}>
              <Link href={`/commercial-planner/cpor-cases/${row.case_id}`}>{row.case_code}</Link>
              {' · '}
              {row.customer_code ?? '—'}
              {' · '}
              {formatGridMoney(row.outstanding_amount, ccy)}
              {row.fx_blocked ? ' · FX blocked' : ''}
            </Typography>
          ))}
        </Stack>
      ) : null}
    </Box>
  );
}
