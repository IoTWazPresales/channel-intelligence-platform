'use client';

import { Box, Typography } from '@mui/material';
import { alpha, useTheme } from '@mui/material/styles';
import { useQuery } from '@tanstack/react-query';

import { formatGridMoney } from '@/features/cpor/fxDisplay';
import { apiGet } from '@/lib/api';

export type SettlementBookRead = {
  data_unavailable?: boolean;
  open_case_count: number;
  currency_code: string;
  book_total: number;
  settled_amount: number;
  outstanding_amount: number;
  blocked_amount: number;
  shape_segments: { settled_pct: number; outstanding_pct: number; blocked_pct: number };
  read_line: string;
  concentration: Array<{
    case_id: number;
    case_code: string;
    customer_code: string | null;
    customer_name: string | null;
    outstanding_amount: number;
    fx_blocked: boolean;
  }>;
};

export function SettlementRegimeStrip() {
  const theme = useTheme();
  const { data } = useQuery({
    queryKey: ['cpor', 'settlement', 'book'],
    queryFn: ({ signal }) => apiGet<SettlementBookRead>('/api/v1/cpor/settlement/book', { signal }),
    staleTime: 30_000,
  });

  const ccy = data?.currency_code ?? 'ZAR';
  const tiles = [
    { label: 'Book total', value: data ? formatGridMoney(data.book_total, ccy) : '—' },
    { label: 'Settled', value: data ? formatGridMoney(data.settled_amount, ccy) : '—' },
    { label: 'Outstanding', value: data ? formatGridMoney(data.outstanding_amount, ccy) : '—' },
  ];

  return (
    <Box
      data-testid="settlement-regime-strip"
      sx={{ display: 'flex', gap: 3.25, ml: 'auto', flexWrap: 'wrap', justifyContent: 'flex-end' }}
    >
      {tiles.map((t) => (
        <Box key={t.label} sx={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 0.25 }}>
          <Typography
            sx={{
              fontSize: '9.5px',
              letterSpacing: '0.09em',
              textTransform: 'uppercase',
              color: alpha(theme.palette.text.primary, 0.45),
            }}
          >
            {t.label}
          </Typography>
          <Typography
            sx={{
              fontFamily: '"IBM Plex Mono", monospace',
              fontSize: '13px',
              color: alpha(theme.palette.text.primary, 0.72),
            }}
          >
            {t.value}
          </Typography>
        </Box>
      ))}
    </Box>
  );
}
