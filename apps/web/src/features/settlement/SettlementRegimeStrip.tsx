'use client';

import { Box, Typography } from '@mui/material';
import { alpha, useTheme } from '@mui/material/styles';

import { formatLocalMoney } from '@/features/cpor/fxDisplay';
import { useSettlementBook } from '@/features/settlement/useSettlementBook';

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
    evidence_basis?: string;
  }>;
  by_evidence_basis?: Record<
    string,
    { case_count: number; owed: number; paid: number; outstanding: number }
  >;
  evidence_basis_note?: string;
};

export function SettlementRegimeStrip() {
  const theme = useTheme();
  const { data, isLoading, isFetching } = useSettlementBook();

  const ccy = data?.currency_code ?? 'ZAR';
  const loading = isLoading && !data;
  const tiles = [
    { label: 'Book total', value: loading ? 'Loading…' : data ? formatLocalMoney(data.book_total, ccy) : '—' },
    { label: 'Settled', value: loading ? 'Loading…' : data ? formatLocalMoney(data.settled_amount, ccy) : '—' },
    {
      label: 'Outstanding',
      value: loading ? 'Loading…' : data ? formatLocalMoney(data.outstanding_amount, ccy) : '—',
    },
  ];

  return (
    <Box
      data-testid="settlement-regime-strip"
      sx={{ display: 'flex', gap: 3.25, ml: 'auto', flexWrap: 'wrap', justifyContent: 'flex-end' }}
      aria-busy={isFetching}
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
            data-testid={`settlement-regime-${t.label.toLowerCase().replace(/\s+/g, '-')}`}
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
