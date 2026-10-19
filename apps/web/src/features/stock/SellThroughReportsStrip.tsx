'use client';

import { Box, Chip, Link, Stack, Typography } from '@mui/material';
import NextLink from 'next/link';

import type { SellThroughOverview } from './sellThroughTypes';

function ago(days: number | null): string {
  if (days == null) return 'nothing loaded';
  if (days === 0) return 'today';
  return days === 1 ? '1 day ago' : `${days} days ago`;
}

/**
 * One line near the top of the Sell-through tab (Warren 2026-10-19): how many reporting customers
 * are up to date, and a chip per customer with reports missing in this window, oldest first. Each
 * chip opens that customer's upload. The full week-by-week grid sits at the bottom of the page.
 */
export function SellThroughReportsStrip({ coverage }: { coverage: SellThroughOverview['coverage'] }) {
  const rows = coverage.customers;
  const overdue = rows
    .filter((r) => r.missing > 0 || r.partial > 0)
    .sort((a, b) => (b.days_since_last ?? 1e9) - (a.days_since_last ?? 1e9));
  const upToDate = rows.length - overdue.length;
  return (
    <Box
      data-testid="sellthrough-reports-strip"
      sx={{
        display: 'flex',
        flexWrap: 'wrap',
        alignItems: 'center',
        gap: 0.75,
        px: 1.5,
        py: 1,
        border: '1px solid',
        borderColor: 'divider',
        borderRadius: 1.5,
        bgcolor: 'background.paper',
      }}
    >
      <Typography variant="body2" sx={{ fontWeight: 600, mr: 0.5 }}>
        Reports
      </Typography>
      <Chip size="small" color="success" variant="outlined" label={`${upToDate} up to date`} />
      {overdue.length ? (
        <Chip size="small" color="error" variant="outlined" label={`${overdue.length} with reports missing`} />
      ) : null}
      <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap sx={{ flex: 1, minWidth: 0 }}>
        {overdue.map((r) => (
          <Chip
            key={r.customer_id}
            size="small"
            component={NextLink}
            href={`/admin/imports?template=customer_sell_through&customer=${r.customer_id}`}
            clickable
            label={`${r.name} · ${r.days_since_last == null ? 'nothing loaded' : `last ${ago(r.days_since_last)}`}`}
            title={`Upload ${r.name}'s sell-through`}
          />
        ))}
      </Stack>
      <Link href="#sellthrough-reports-grid" underline="hover" variant="caption">
        Week by week
      </Link>
    </Box>
  );
}
