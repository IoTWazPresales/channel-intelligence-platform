'use client';

import { Alert, Stack, Table, TableBody, TableCell, TableHead, TableRow, Typography } from '@mui/material';
import { useListingIntelligence } from '@/features/market-listings/listingIntelligence';

export type TimingAlert = {
  kind: 'late_activation' | 'early_deactivation';
  listing_id: number;
  customer_id: number;
  product_id: number | null;
  marketplace?: string | null;
  url?: string | null;
  case_id?: number | null;
  case_code?: string | null;
  window_start: string;
  window_end: string;
  alert_days: number;
  not_at_price_on?: string | null;
  at_price_from?: string | null;
  days_late_at_least?: number;
  last_at_price_on?: string | null;
  off_price_on?: string | null;
  back_at_price_on?: string | null;
  days_early_at_least?: number;
};

function detail(alert: TimingAlert): string {
  if (alert.kind === 'late_activation') {
    const live = alert.at_price_from ? `at price from ${alert.at_price_from}` : 'not at price yet';
    return `Still off price on ${alert.not_at_price_on} (${alert.days_late_at_least}+ days in); ${live}`;
  }
  const back = alert.back_at_price_on ? `; back at price ${alert.back_at_price_on}` : '';
  return `Off price on ${alert.off_price_on} (${alert.days_early_at_least}+ days before the end)${back}`;
}

/** Late activation / early deactivation from stored checks (threshold from the API setting). */
export function ActivationTimingAlerts() {
  const query = useListingIntelligence();
  const alerts = Array.isArray(query.data?.timing_alerts) ? query.data.timing_alerts : [];
  const days = query.data?.activation_alert_days;
  const failed = query.failed;

  return (
    <Stack spacing={1} data-testid="activation-timing">
      <Typography variant="subtitle2">Late activation / early deactivation</Typography>
      <Typography variant="body2" color="text.secondary" data-testid="activation-timing-rule">
        {typeof days === 'number'
          ? `A check still off the promotion price ${days} or more days after the window starts, or off it ${days} or more days before the window ends.`
          : 'A check off the promotion price too long after the window starts, or too long before it ends.'}
      </Typography>
      {failed ? (
        <Alert severity="warning" data-testid="activation-timing-error">
          Activation timing could not be loaded.
        </Alert>
      ) : null}
      {query.isPending ? (
        <Typography variant="body2" color="text.secondary" data-testid="activation-timing-loading">
          Loading…
        </Typography>
      ) : failed ? null : alerts.length === 0 ? (
        <Typography variant="body2" data-testid="activation-timing-empty">
          No late or early promotions in the stored checks.
        </Typography>
      ) : (
        <Table size="small" data-testid="activation-timing-table">
          <TableHead>
            <TableRow>
              <TableCell>Alert</TableCell>
              <TableCell>Case</TableCell>
              <TableCell>Window</TableCell>
              <TableCell>Listing</TableCell>
              <TableCell>What the checks show</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {alerts.map((alert) => (
              <TableRow
                key={`${alert.listing_id}-${alert.case_id}-${alert.window_start}-${alert.kind}`}
                data-testid={`activation-timing-row-${alert.listing_id}-${alert.kind}`}
              >
                <TableCell>{alert.kind === 'late_activation' ? 'Late activation' : 'Early deactivation'}</TableCell>
                <TableCell>{alert.case_code ?? alert.case_id ?? '—'}</TableCell>
                <TableCell>
                  {alert.window_start} – {alert.window_end}
                </TableCell>
                <TableCell>
                  {alert.marketplace ?? ''} · listing {alert.listing_id}
                </TableCell>
                <TableCell>{detail(alert)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </Stack>
  );
}
