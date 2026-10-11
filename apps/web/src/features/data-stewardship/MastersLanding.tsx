'use client';

import { Alert, Box, Button, Stack, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import NextLink from 'next/link';

import { HeadlineFigure, HeadlineStrip } from '@/features/workbench-ui/HeadlineFigure';
import { Panel } from '@/features/workbench-ui/Panel';
import { apiGet } from '@/lib/api';

import { DataChrome } from './DataChrome';
import type { StewardshipSummary } from './types';
import { useClientReady } from './useClientReady';

const CARDS: {
  key: string;
  labelKey: 'products' | 'customers' | 'distributors' | 'stores';
  href: string | null;
  extraHref?: { label: string; href: string };
  unverifiedKey?: 'customers_unverified' | 'distributors_unverified';
  what: string;
  status?: 'partial' | 'uncovered';
}[] = [
  {
    key: 'products',
    labelKey: 'products',
    href: '/admin/products',
    extraHref: { label: 'Catalogue gaps', href: '/admin/product-master-gaps' },
    what: 'SKU, EAN, model, family, and lifecycle. A product has no provisional flag.',
  },
  {
    key: 'customers',
    labelKey: 'customers',
    href: '/admin/customers',
    extraHref: { label: 'Duplicates', href: '/admin/customers/duplicates?tab=name_similarity' },
    unverifiedKey: 'customers_unverified',
    what: 'Groups, strategic flag, commercial terms, channel mapping.',
  },
  {
    key: 'distributors',
    labelKey: 'distributors',
    href: '/admin/distributors',
    extraHref: { label: 'Duplicates', href: '/admin/distributors/duplicates' },
    unverifiedKey: 'distributors_unverified',
    what: 'Commercial terms and regions.',
  },
  {
    key: 'stores',
    labelKey: 'stores',
    href: null,
    what: 'Retail locations under customers. There is no grid for them yet.',
    status: 'uncovered',
  },
];

export function MastersLanding() {
  const ready = useClientReady();
  const { data: summary } = useQuery({
    queryKey: ['imports', 'stewardship-summary'],
    queryFn: ({ signal }) => apiGet<StewardshipSummary>('/api/v1/imports/stewardship-summary', { signal }),
    staleTime: 30_000,
  });
  const data = ready ? summary : undefined;

  return (
    <DataChrome>
      <Stack spacing={2} sx={{ mt: 2 }} data-testid="masters-landing">
        <Typography variant="body2" color="text.secondary">
          These are the product, customer, and distributor records everything else points at. An import never
          creates one of them on its own. A provisional record is added here, then filled in.
        </Typography>
        <Box sx={{ display: 'grid', gap: 1.5, gridTemplateColumns: { xs: '1fr', md: 'repeat(2, 1fr)' } }}>
          {CARDS.map((m) => {
            const count = data?.[m.labelKey];
            const unverified = m.unverifiedKey ? data?.[m.unverifiedKey] : 0;
            return (
              <Panel
                key={m.key}
                title={data?.labels[m.labelKey] ?? m.key}
                subtitle={m.what}
                actions={
                  m.href ? (
                    <Button size="small" component={NextLink} href={m.href}>
                      Open grid
                    </Button>
                  ) : (
                    <Typography variant="caption" color="text.secondary">
                      No grid
                    </Typography>
                  )
                }
              >
                <HeadlineStrip columns={3}>
                  <HeadlineFigure label="Records" value={count ?? '—'} dense />
                  <HeadlineFigure
                    label={m.unverifiedKey ? 'Unverified' : 'Provisional'}
                    value={m.key === 'products' ? 0 : (unverified ?? '—')}
                    dense
                    severity={unverified ? 'warn' : 'neutral'}
                    caption={
                      m.key === 'products'
                        ? 'Products have no provisional flag'
                        : data?.captions[m.unverifiedKey ?? '']
                    }
                  />
                  <HeadlineFigure
                    label="Possible duplicates"
                    value="—"
                    dense
                    caption="Review on the duplicates screen — no stored cluster count"
                  />
                </HeadlineStrip>
                {m.extraHref ? (
                  <Button size="small" component={NextLink} href={m.extraHref.href} sx={{ mt: 1 }}>
                    {m.extraHref.label}
                  </Button>
                ) : null}
                {m.status === 'uncovered' ? (
                  <Alert severity="info" sx={{ mt: 1 }}>
                    Stores are recorded under customers. There is no store grid on this page. Channels, regions, and retailer sell-through matching stay in the navigation.
                  </Alert>
                ) : null}
              </Panel>
            );
          })}
        </Box>
        <Typography variant="body2" color="text.secondary">
          Products, customers, duplicates, catalogue gaps, retailer sell-through matching, and channels and
          regions stay reachable from Also in this area on every Data page. Stores have no grid yet.
        </Typography>
      </Stack>
    </DataChrome>
  );
}
