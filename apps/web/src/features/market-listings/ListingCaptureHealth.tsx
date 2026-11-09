'use client';

import { Alert, Stack, Table, TableBody, TableCell, TableHead, TableRow, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { useMemo } from 'react';

import { apiGet } from '@/lib/api';
import { StatusChip } from '@/features/workbench-ui/controls';
import { HeadlineFigure, HeadlineStrip } from '@/features/workbench-ui/HeadlineFigure';

type NewestObservation = {
  fetched_at: string | null;
  status: string | null;
  price: number | null;
};

type SiteHealth = {
  site_id: number | null;
  site_key: string;
  configured: boolean;
  newest_observation: NewestObservation | null;
  listings_due: number;
  skipped_not_configured: number;
};

type DiscoveryRow = {
  customer_id: number;
  site_key: string | null;
  outcome: string;
  reason: string | null;
  reasons?: string[];
  pattern_status: string | null;
};

type CaptureHealth = {
  data_unavailable?: boolean;
  sites?: SiteHealth[];
  listings_due?: number;
  skipped_not_configured?: Record<string, number>;
  exclusions?: DiscoveryRow[];
  configured?: DiscoveryRow[];
};

type CustomerRow = { id: number; customer_code: string; customer_name: string };

type CustomerList = { items?: CustomerRow[] };

const PATTERN_LABEL: Record<string, string> = {
  derived: 'One link pattern',
  mixed: 'Links do not share one pattern',
  none: 'No pattern yet',
};

const REASON_LABEL: Record<string, string> = {
  no_site_key: 'No site key',
  no_seller_data: 'No seller name or id',
  needs_details_pattern: 'Page reader is not configured',
  seller_seed_invalid: 'Seller details are not usable',
  autoconfigure_failed: 'This customer could not be read',
};

const OUTCOME_LABEL: Record<string, string> = {
  configured: 'Configured',
  excluded: 'Left out',
  needs_pattern: 'Needs a page reader',
};

function fmtWhen(value: string | null | undefined): string {
  if (!value) return 'not yet';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
}

function fmtPrice(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '—';
  return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function patternLabel(status: string | null | undefined): string {
  if (!status) return '—';
  return PATTERN_LABEL[status] ?? status;
}

function patternTone(status: string | null | undefined): 'success' | 'warning' | 'neutral' {
  if (status === 'derived') return 'success';
  if (status === 'mixed' || status === 'none') return 'warning';
  return 'neutral';
}

function reasonText(row: DiscoveryRow): string {
  const reasons = row.reasons && row.reasons.length > 0 ? row.reasons : row.reason ? [row.reason] : [];
  if (reasons.length === 0) return '—';
  return reasons.map((reason) => REASON_LABEL[reason] ?? reason).join('; ');
}

export function ListingCaptureHealth() {
  const health = useQuery({
    queryKey: ['listing-capture', 'capture-health'],
    queryFn: ({ signal }) => apiGet<CaptureHealth>('/api/v1/listing-capture/capture-health', { signal }),
  });
  const { data: customersPage } = useQuery({
    queryKey: ['customers', 'listing-capture-health-names'],
    queryFn: ({ signal }) => apiGet<CustomerList>('/api/v1/customers?page=1&page_size=200', { signal }),
    staleTime: 60_000,
  });
  const customerLabelById = useMemo(() => {
    const m = new Map<number, string>();
    for (const c of customersPage?.items ?? []) {
      const label = (c.customer_name || c.customer_code || '').trim();
      if (label) m.set(c.id, label);
    }
    return m;
  }, [customersPage]);
  const data = health.data;
  const sites = data?.sites ?? [];
  const configured = data?.configured ?? [];
  const exclusions = data?.exclusions ?? [];
  const discovery = [...configured, ...exclusions];
  const listingsDue = data?.listings_due ?? 0;
  const skipped = Object.values(data?.skipped_not_configured ?? {}).reduce((sum, count) => sum + Number(count || 0), 0);
  const ready = sites.filter((site) => site.configured).length;
  const patternGaps = discovery.filter((row) => row.pattern_status === 'mixed' || row.pattern_status === 'none').length;
  const unavailable = health.isError || data?.data_unavailable === true;
  const dashPlaceholder = unavailable && !health.isLoading;

  return (
    <Stack spacing={1.5} sx={{ mt: 2 }} data-testid="listing-capture-health">
      <Typography variant="body2" color="text.secondary">
        Capture health is read from the latest saved sites and checks. It does not fetch a page.
      </Typography>
      {unavailable ? (
        <Alert severity="warning" data-testid="listing-capture-health-unavailable">
          Capture health could not be loaded.
        </Alert>
      ) : null}
      <HeadlineStrip columns={4}>
        <HeadlineFigure
          label="Listings due"
          value={health.isLoading ? '…' : dashPlaceholder ? '—' : listingsDue}
          compact
          testId="listing-capture-health-due"
          caption="Active listings waiting for a check"
        />
        <HeadlineFigure
          label="Skipped, not configured"
          value={health.isLoading ? '…' : dashPlaceholder ? '—' : skipped}
          compact
          severity={dashPlaceholder ? 'neutral' : skipped ? 'warn' : 'neutral'}
          testId="listing-capture-health-skipped"
          caption="Due listings on a site with no page reader"
        />
        <HeadlineFigure
          label="Sites ready"
          value={health.isLoading ? '…' : dashPlaceholder ? '—' : ready}
          unit={!dashPlaceholder && sites.length ? `of ${sites.length}` : undefined}
          compact
          severity={
            dashPlaceholder ? 'neutral' : sites.length && ready === sites.length ? 'good' : 'neutral'
          }
          testId="listing-capture-health-ready"
        />
        <HeadlineFigure
          label="Link patterns to look at"
          value={health.isLoading ? '…' : dashPlaceholder ? '—' : patternGaps}
          compact
          severity={dashPlaceholder ? 'neutral' : patternGaps ? 'warn' : 'neutral'}
          testId="listing-capture-health-patterns"
          caption="Mixed links, or no shared pattern yet"
        />
      </HeadlineStrip>
      {sites.length === 0 && !health.isLoading && !unavailable ? (
        <Typography variant="body2" data-testid="listing-capture-health-sites-empty">
          No sites in capture health.
        </Typography>
      ) : null}
      {sites.length > 0 ? (
        <Table size="small" data-testid="listing-capture-health-sites">
          <TableHead>
            <TableRow>
              <TableCell>Site</TableCell>
              <TableCell>Page reader</TableCell>
              <TableCell align="right">Due</TableCell>
              <TableCell align="right">Skipped</TableCell>
              <TableCell>Newest check</TableCell>
              <TableCell>Check</TableCell>
              <TableCell align="right">Price</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {sites.map((site) => (
              <TableRow key={site.site_key} data-testid={`listing-capture-health-site-${site.site_key}`}>
                <TableCell>{site.site_key}</TableCell>
                <TableCell>
                  <StatusChip
                    label={site.configured ? 'Configured' : 'Not configured'}
                    tone={site.configured ? 'success' : 'warning'}
                  />
                </TableCell>
                <TableCell align="right">{dashPlaceholder ? '—' : site.listings_due}</TableCell>
                <TableCell align="right">{dashPlaceholder ? '—' : site.skipped_not_configured}</TableCell>
                <TableCell>{fmtWhen(site.newest_observation?.fetched_at)}</TableCell>
                <TableCell>{site.newest_observation?.status ?? '—'}</TableCell>
                <TableCell align="right">{fmtPrice(site.newest_observation?.price)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      ) : null}
      <Typography variant="subtitle2">Link discovery</Typography>
      {discovery.length === 0 && !health.isLoading && !unavailable ? (
        <Typography variant="body2" data-testid="listing-capture-health-discovery-empty">
          No link-pattern status yet.
        </Typography>
      ) : null}
      {discovery.map((row) => {
        const siteKey = row.site_key || 'none';
        return (
          <Stack
            key={`${row.customer_id}-${siteKey}-${row.outcome}`}
            direction="row"
            spacing={1}
            useFlexGap
            flexWrap="wrap"
            alignItems="center"
            data-testid={`listing-capture-health-discovery-${row.customer_id}-${siteKey}`}
          >
            <Typography variant="body2">
              {row.site_key || 'No site'} · {customerLabelById.get(row.customer_id) ?? '—'}
            </Typography>
            <StatusChip label={OUTCOME_LABEL[row.outcome] ?? row.outcome} tone={row.outcome === 'configured' ? 'success' : 'warning'} />
            {row.pattern_status ? <StatusChip label={patternLabel(row.pattern_status)} tone={patternTone(row.pattern_status)} /> : null}
            <Typography variant="body2" color="text.secondary">
              {reasonText(row)}
            </Typography>
          </Stack>
        );
      })}
    </Stack>
  );
}
