'use client';

import { Box, Button, Card, CardActionArea, CardContent, Stack, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import NextLink from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';

import { HeadlineFigure, HeadlineStrip } from '@/features/workbench-ui/HeadlineFigure';
import { Panel } from '@/features/workbench-ui/Panel';
import { ScopeBar } from '@/features/workbench-ui/controls';
import { apiGet } from '@/lib/api';

import type { StewardshipSummary } from './types';
import { useClientReady } from './useClientReady';

const START_CARDS: { label: string; slug: string; href: string }[] = [
  { label: 'Distributor sell-out & SOH', slug: 'distributor_inventory', href: '/admin/imports?template=distributor_inventory' },
  { label: 'Retailer sell-through', slug: 'customer_sell_through', href: '/admin/imports?template=customer_sell_through' },
  { label: 'Inbound shipments', slug: 'inbound_shipments', href: '/admin/imports?template=inbound_shipments' },
  // unified_lineup is hidden from the generic wizard — dedicated dialog via ?unified=1.
  { label: 'Lineup (unified)', slug: 'unified_lineup', href: '/admin/imports?unified=1' },
  { label: 'Claim evidence', slug: 'cpor_claim_evidence', href: '/admin/imports?template=cpor_claim_evidence' },
  { label: 'Product master', slug: 'product_master', href: '/admin/imports?template=product_master' },
];

export function ImportCenterOverview() {
  const router = useRouter();
  const search = useSearchParams();
  const ready = useClientReady();
  const jobStatus = search.get('jobStatus');
  const { data: summary } = useQuery({
    queryKey: ['imports', 'stewardship-summary'],
    queryFn: ({ signal }) => apiGet<StewardshipSummary>('/api/v1/imports/stewardship-summary', { signal }),
    staleTime: 30_000,
  });
  const data = ready ? summary : undefined;

  const setStatus = (v: string | null) => {
    const next = new URLSearchParams(search.toString());
    if (v) next.set('jobStatus', v);
    else next.delete('jobStatus');
    const qs = next.toString();
    router.replace(qs ? `/admin/imports?${qs}` : '/admin/imports', { scroll: false });
  };

  const chips = [
    {
      key: 'failed',
      label: `Failed · ${data?.failed_all ?? '—'}`,
      active: jobStatus === 'failed',
      onToggle: () => setStatus(jobStatus === 'failed' ? null : 'failed'),
      tone: 'danger' as const,
    },
    {
      key: 'pending',
      label: `Pending mapping · ${data?.pending_all ?? '—'}`,
      active: jobStatus === 'pending',
      onToggle: () => setStatus(jobStatus === 'pending' ? null : 'pending'),
      tone: 'warning' as const,
    },
    {
      key: 'validated',
      label: 'Validated',
      active: jobStatus === 'validated',
      onToggle: () => setStatus(jobStatus === 'validated' ? null : 'validated'),
      tone: 'default' as const,
    },
    {
      key: 'completed',
      label: `Completed · ${data?.completed_all ?? '—'}`,
      active: jobStatus === 'completed',
      onToggle: () => setStatus(jobStatus === 'completed' ? null : 'completed'),
      tone: 'success' as const,
    },
  ];

  return (
    <Stack spacing={2} sx={{ mt: 2, mb: 2 }} data-testid="import-center-overview">
      <HeadlineStrip columns={5}>
        <HeadlineFigure
          label={data?.labels.jobs_last_7d ?? 'Jobs in last 7 days'}
          value={data?.jobs_last_7d ?? '—'}
          compact
          caption={data?.captions.jobs_last_7d}
        />
        <HeadlineFigure
          label={data?.labels.failed_7d ?? 'Failed (last 7 days)'}
          value={data?.failed_7d ?? '—'}
          compact
          severity="bad"
          onClick={() => setStatus('failed')}
          caption={data?.captions.failed_7d}
        />
        <HeadlineFigure
          label={data?.labels.pending_7d ?? 'Pending mapping (last 7 days)'}
          value={data?.pending_7d ?? '—'}
          compact
          severity="warn"
          onClick={() => setStatus('pending')}
          caption={data?.captions.pending_7d}
        />
        <HeadlineFigure
          label={data?.labels.completed_7d ?? 'Completed (last 7 days)'}
          value={data?.completed_7d ?? '—'}
          compact
          severity="good"
          caption={data?.captions.completed_7d}
        />
        <HeadlineFigure
          label={data?.labels.templates_enabled ?? 'Enabled import types'}
          value={data?.templates_enabled ?? '—'}
          compact
          caption={data?.captions.templates_enabled}
        />
      </HeadlineStrip>
      <Panel
        title="Start an import"
        subtitle="Upload → parse → map → validate → steward → apply → derive. Same guided wizard for every type — column mapping stays desktop-first."
        actions={
          <Button variant="contained" size="small" component={NextLink} href="/admin/imports">
            New import
          </Button>
        }
      >
        <Box sx={{ display: 'grid', gap: 1, gridTemplateColumns: { xs: 'repeat(2, 1fr)', md: 'repeat(6, 1fr)' } }}>
          {START_CARDS.map((c) => (
            <Card key={c.slug} variant="outlined" sx={{ boxShadow: 'none' }}>
              <CardActionArea component={NextLink} href={c.href} sx={{ height: '100%' }}>
                <CardContent sx={{ py: 1.25, '&:last-child': { pb: 1.25 } }}>
                  <Typography variant="body2" sx={{ fontWeight: 600 }}>
                    {c.label}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {c.slug}
                  </Typography>
                </CardContent>
              </CardActionArea>
            </Card>
          ))}
        </Box>
      </Panel>
      <ScopeBar
        chips={chips}
        summary={data ? `${data.jobs_unarchived} unarchived jobs (grid shows latest 100)` : undefined}
        onClear={() => setStatus(null)}
      />
    </Stack>
  );
}
