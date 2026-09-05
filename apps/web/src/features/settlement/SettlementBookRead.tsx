'use client';

import { Box, Stack, Typography } from '@mui/material';
import { alpha, useTheme } from '@mui/material/styles';
import Link from 'next/link';

import { formatLocalMoney } from '@/features/cpor/fxDisplay';
import { evidenceBasisLabel } from '@/features/promotions-funding/evidenceBasis';
import { SettlementPortfolioRead } from '@/features/settlement/SettlementPortfolioRead';
import { SettlementShapeBar } from '@/features/settlement/SettlementShapeBar';
import { useSettlementBook } from '@/features/settlement/useSettlementBook';

export function SettlementBookRead() {
  const theme = useTheme();
  const { data, isLoading, isFetching } = useSettlementBook();

  const seg = data?.shape_segments;
  const ccy = data?.currency_code ?? 'ZAR';
  const loading = isLoading && !data;

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
        <Typography variant="body2" color="text.secondary" data-testid="settlement-book-read-line">
          {loading ? 'Loading book…' : data?.read_line ?? (isFetching ? 'Refreshing book…' : '—')}
        </Typography>
      </Stack>
      {data?.by_evidence_basis ? (
        <Typography variant="caption" color="text.secondary" data-testid="settlement-book-evidence-mix">
          {data.evidence_basis_note ?? 'Open-book totals mix evidence bases.'} Claim{' '}
          {data.by_evidence_basis.claim_evidenced?.case_count ?? 0} · attested{' '}
          {data.by_evidence_basis.source_attested?.case_count ?? 0} · none{' '}
          {data.by_evidence_basis.none?.case_count ?? 0}.
        </Typography>
      ) : null}
      {seg ? (
        <SettlementShapeBar
          settledPct={seg.settled_pct}
          outstandingPct={seg.outstanding_pct}
          blockedPct={seg.blocked_pct}
        />
      ) : null}
      <SettlementPortfolioRead />
      {data?.concentration?.length ? (
        <Stack spacing={0.5} sx={{ mt: 1.5 }}>
          <Typography variant="caption" color="text.secondary">
            Top outstanding
          </Typography>
          {data.concentration.slice(0, 5).map((row) => (
            <Typography key={row.case_id} variant="body2" sx={{ fontSize: '12px' }}>
              <Link href={`/commercial-planner/cpor-cases?case=${row.case_id}`}>{row.case_code}</Link>
              {' · '}
              {row.customer_code ?? '—'}
              {' · '}
              {formatLocalMoney(row.outstanding_amount, ccy)}
              {row.fx_blocked ? ' · FX blocked' : ''}
              {row.evidence_basis ? ` · ${evidenceBasisLabel(row.evidence_basis)}` : ''}
            </Typography>
          ))}
        </Stack>
      ) : null}
    </Box>
  );
}
