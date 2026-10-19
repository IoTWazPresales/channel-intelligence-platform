'use client';

import { Box, Link, Stack, Tooltip, Typography } from '@mui/material';
import { alpha, useTheme } from '@mui/material/styles';
import NextLink from 'next/link';

import type { CoverageStatus, SellThroughOverview } from './sellThroughTypes';

const STATUS_TEXT: Record<CoverageStatus, string> = {
  received: 'Received',
  partial: 'Partly received',
  due: 'Not due yet',
  missing: 'Missing',
  not_expected: 'Not expected',
  future: 'Not started',
};

function useStatusColor() {
  const t = useTheme();
  return (s: CoverageStatus): string => {
    switch (s) {
      case 'received':
        return t.palette.success.main;
      case 'partial':
        return t.palette.warning.main;
      case 'missing':
        return t.palette.error.main;
      case 'due':
        return alpha(t.palette.info.main, 0.45);
      default:
        return alpha(t.palette.text.primary, 0.08);
    }
  };
}

function importHref(customerId: number) {
  return `/admin/imports?template=customer_sell_through&customer=${customerId}`;
}

/**
 * Which reports arrived, per reporting customer and period (Warren 2026-10-19). Rows are customers,
 * columns the weeks (or months, for long windows) of the chosen window, in the tenant calendar.
 */
export function SellThroughCoverageGrid({
  coverage,
  onCustomer,
}: {
  coverage: SellThroughOverview['coverage'];
  onCustomer?: (customerId: number) => void;
}) {
  const color = useStatusColor();
  const cols = coverage.columns;
  if (!coverage.customers.length) {
    return (
      <Typography variant="body2" color="text.secondary">
        No reporting customers yet. Mark customers as reporting in Sell-through steward → Key accounts.
      </Typography>
    );
  }
  return (
    <Box data-testid="sellthrough-coverage" sx={{ overflowX: 'auto' }}>
      <Box
        role="table"
        aria-label="Reports received per customer and period"
        sx={{
          display: 'grid',
          gridTemplateColumns: `minmax(160px, 220px) repeat(${cols.length}, minmax(18px, 1fr)) 120px`,
          alignItems: 'center',
          columnGap: '3px',
          rowGap: '4px',
          minWidth: 160 + cols.length * 21 + 120,
        }}
      >
        <Box role="columnheader" />
        {cols.map((c, i) => (
          <Box
            role="columnheader"
            key={c.start}
            sx={{ fontSize: 10, color: 'text.secondary', textAlign: 'center', whiteSpace: 'nowrap', overflow: 'hidden' }}
          >
            {i % Math.max(1, Math.ceil(cols.length / 13)) === 0 ? c.label : ''}
          </Box>
        ))}
        <Box role="columnheader" sx={{ fontSize: 11, color: 'text.secondary', pl: 1 }}>
          Last figures
        </Box>
        {coverage.customers.map((r) => (
          <Box key={r.customer_id} role="row" sx={{ display: 'contents' }}>
            <Box role="rowheader" sx={{ minWidth: 0 }}>
              <Link
                component="button"
                type="button"
                underline="hover"
                onClick={() => onCustomer?.(r.customer_id)}
                sx={{ fontSize: 13, textAlign: 'left', color: 'text.primary', display: 'block', maxWidth: '100%', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
              >
                {r.name}
              </Link>
              <Typography variant="caption" color="text.secondary">
                {r.reports_expected ? r.cadence : 'not expected'}
              </Typography>
            </Box>
            {r.cells.map((cell, i) => {
              const col = cols[i];
              const tip = `${r.name} · ${col?.label ?? cell.start}: ${STATUS_TEXT[cell.status]}${
                cell.ratio != null && cell.status === 'partial' ? ` (${Math.round(cell.ratio * 100)}% of days)` : ''
              }`;
              const box = (
                <Box
                  role="cell"
                  aria-label={tip}
                  sx={{
                    height: 18,
                    borderRadius: 0.5,
                    bgcolor: color(cell.status),
                    cursor: cell.status === 'missing' || cell.status === 'partial' ? 'pointer' : 'default',
                  }}
                />
              );
              return (
                <Tooltip key={cell.start} title={tip} arrow disableInteractive>
                  {cell.status === 'missing' || cell.status === 'partial' ? (
                    <Box component={NextLink} href={importHref(r.customer_id)} sx={{ display: 'block' }}>
                      {box}
                    </Box>
                  ) : (
                    box
                  )}
                </Tooltip>
              );
            })}
            <Box sx={{ pl: 1, fontSize: 12 }}>
              {r.last_reported_day ? (
                <>
                  {r.last_reported_day}
                  <Typography variant="caption" color={r.missing ? 'error.main' : 'text.secondary'} display="block">
                    {r.days_since_last != null ? (r.days_since_last === 1 ? '1 day ago' : r.days_since_last === 0 ? 'today' : `${r.days_since_last} days ago`) : ''}
                  </Typography>
                </>
              ) : (
                <Typography variant="caption" color="text.secondary">
                  Nothing loaded
                </Typography>
              )}
            </Box>
          </Box>
        ))}
      </Box>
      <Stack direction="row" spacing={2} sx={{ mt: 1.5 }} flexWrap="wrap" useFlexGap>
        {(['received', 'partial', 'due', 'missing', 'not_expected'] as CoverageStatus[]).map((s) => (
          <Stack key={s} direction="row" spacing={0.75} alignItems="center">
            <Box sx={{ width: 12, height: 12, borderRadius: 0.5, bgcolor: color(s) }} />
            <Typography variant="caption">{STATUS_TEXT[s]}</Typography>
          </Stack>
        ))}
        <Typography variant="caption" color="text.secondary">
          Click a red or amber cell to upload that customer&apos;s file.
        </Typography>
      </Stack>
    </Box>
  );
}
