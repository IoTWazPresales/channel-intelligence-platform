'use client';

import { Box, Stack, Typography } from '@mui/material';
import { alpha, useTheme } from '@mui/material/styles';
import { useQuery } from '@tanstack/react-query';

import { apiGet } from '@/lib/api';

type PortfolioIntelligence = {
  cases_in_scope: number;
  lines_included: number;
  evidence_basis_mix?: { claim_evidenced?: number; source_attested?: number; none?: number };
  evidence_basis_note?: string;
  totals: {
    support_usd: number;
    support_zar: number;
    estimate_qty: number;
    result_qty: number;
    delivery_rate: number | null;
    support_per_unit_sold_usd: number | null;
    support_per_unit_sold_zar: number | null;
  };
  incremental_unit_cost?: {
    cases_ok: number;
    cases_flagged: number;
    avg_cost_per_incremental_unit_usd: number | null;
  };
};

function fmtUsd(n: number | null | undefined): string {
  if (n == null) return '—';
  return n.toLocaleString(undefined, { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });
}

function fmtZar(n: number | null | undefined): string {
  if (n == null) return '—';
  return `R ${n.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

function fmtPct(n: number | null | undefined): string {
  if (n == null) return '—';
  return `${(n * 100).toFixed(1)}%`;
}

/** Condensed portfolio intelligence for Settlement book read strip (folded from list-surface panel). */
export function SettlementPortfolioRead() {
  const theme = useTheme();
  const { data, isLoading } = useQuery({
    queryKey: ['cpor', 'intelligence', 'portfolio'],
    queryFn: ({ signal }) => apiGet<PortfolioIntelligence>('/api/v1/cpor/intelligence/portfolio', { signal }),
    staleTime: 60_000,
  });

  const t = data?.totals;
  const tiles = [
    {
      label: 'Support spend',
      primary: isLoading ? '—' : fmtUsd(t?.support_usd),
      secondary: isLoading ? '—' : fmtZar(t?.support_zar),
    },
    {
      label: 'Delivery rate',
      primary: isLoading ? '—' : fmtPct(t?.delivery_rate),
      secondary: isLoading
        ? '—'
        : `result ${t?.result_qty?.toLocaleString() ?? '—'} / est ${t?.estimate_qty?.toLocaleString() ?? '—'}`,
    },
    {
      label: 'Support / unit sold',
      primary: isLoading ? '—' : fmtUsd(t?.support_per_unit_sold_usd),
      secondary: isLoading ? '—' : fmtZar(t?.support_per_unit_sold_zar),
    },
    {
      label: 'Cost / incremental unit',
      primary: isLoading ? '—' : fmtUsd(data?.incremental_unit_cost?.avg_cost_per_incremental_unit_usd),
      secondary: isLoading
        ? '—'
        : `${data?.incremental_unit_cost?.cases_ok ?? 0} ok / ${data?.incremental_unit_cost?.cases_flagged ?? 0} flagged`,
    },
  ];

  return (
    <Stack spacing={0.75} data-testid="settlement-portfolio-read" sx={{ mt: 1.5 }}>
      <Typography variant="caption" color="text.secondary">
        Portfolio · {isLoading ? '…' : `${data?.cases_in_scope ?? 0} cases / ${data?.lines_included ?? 0} lines`}
        {data?.evidence_basis_mix
          ? ` · mixed ${data.evidence_basis_mix.claim_evidenced ?? 0} claim / ${data.evidence_basis_mix.source_attested ?? 0} attested / ${data.evidence_basis_mix.none ?? 0} none`
          : ''}
      </Typography>
      <Stack direction="row" spacing={2} useFlexGap flexWrap="wrap">
        {tiles.map((tile) => (
          <Box key={tile.label} sx={{ minWidth: 120 }}>
            <Typography
              sx={{
                fontSize: '9.5px',
                letterSpacing: '0.08em',
                textTransform: 'uppercase',
                color: alpha(theme.palette.text.primary, 0.45),
              }}
            >
              {tile.label}
            </Typography>
            <Typography sx={{ fontFamily: '"IBM Plex Mono", monospace', fontSize: '13px', fontWeight: 500 }}>
              {tile.primary}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {tile.secondary}
            </Typography>
          </Box>
        ))}
      </Stack>
    </Stack>
  );
}
