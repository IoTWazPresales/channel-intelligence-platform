'use client';

import { Button } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import NextLink from 'next/link';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import type { ReactNode } from 'react';

import { DomainHeader } from '@/features/workbench-ui/DomainHeader';
import { WorkbenchCanvas } from '@/features/workbench-ui/WorkbenchCanvas';
import { LensTabs } from '@/features/workbench-ui/controls';
import { apiGet } from '@/lib/api';

export const STOCK_TITLE = 'Stock & Sell-through';

export const STOCK_DESCRIPTION =
  'Distributor and retailer stock, weeks of cover, sell-out velocity and execution against plan — all derived from imported sell-out, SOH and shipment files.';

export type StockDomainLens = 'cover' | 'movement' | 'sellthrough' | 'execution' | 'forecast';

const LENSES: { value: StockDomainLens; label: string; href: string }[] = [
  { value: 'cover', label: 'Cover', href: '/stock?lens=cover' },
  { value: 'movement', label: 'Movement', href: '/stock?lens=movement' },
  { value: 'sellthrough', label: 'Sell-through', href: '/channel-intelligence' },
  { value: 'execution', label: 'Execution vs plan', href: '/stock?lens=execution' },
  { value: 'forecast', label: 'Forecasts', href: '/forecasts' },
];

export function stockLensFromLocation(pathname: string, search: URLSearchParams): StockDomainLens {
  if (pathname.startsWith('/channel-intelligence')) return 'sellthrough';
  if (pathname.startsWith('/forecasts')) return 'forecast';
  const lens = (search.get('lens') || '').toLowerCase();
  if (lens === 'movement') return 'movement';
  if (lens === 'execution') return 'execution';
  if (lens === 'sellthrough') return 'sellthrough';
  if (lens === 'forecast') return 'forecast';
  return 'cover';
}

export function StockChrome({
  counts,
  meta,
  actions,
  children,
}: {
  counts?: Partial<Record<StockDomainLens, number>>;
  meta?: string;
  actions?: ReactNode;
  children?: ReactNode;
}) {
  const pathname = usePathname() || '/stock';
  const search = useSearchParams();
  const router = useRouter();
  const lens = stockLensFromLocation(pathname, search);
  const { data: coverDist } = useQuery({
    queryKey: ['channel-ops', 'cover-distribution', 'stock-chrome'],
    queryFn: ({ signal }) =>
      apiGet<{ buckets?: { lt2?: number }; pair_count?: number; cover_as_of_date?: string | null; data_unavailable?: boolean }>(
        '/api/v1/channel-ops/cover-distribution',
        { signal },
      ),
    staleTime: 60_000,
  });
  const breachCount = coverDist?.data_unavailable ? undefined : coverDist?.buckets?.lt2;
  const metaText =
    meta ??
    (coverDist?.cover_as_of_date
      ? `Cover as of ${coverDist.cover_as_of_date} · ${coverDist.pair_count ?? 0} pairs · SOH is calculated, never stored`
      : 'SOH is calculated, never stored');

  return (
    <WorkbenchCanvas>
      <DomainHeader
        crumbs={[{ label: STOCK_TITLE }]}
        title={STOCK_TITLE}
        description={STOCK_DESCRIPTION}
        meta={metaText}
        actions={
          actions ?? (
            <>
              <Button variant="outlined" size="small" component={NextLink} href="/reports">
                Open in Reports
              </Button>
              <Button variant="contained" size="small" component={NextLink} href="/admin/imports">
                Import sell-out / SOH
              </Button>
            </>
          )
        }
      />
      <LensTabs
        value={lens}
        onChange={(next) => {
          const found = LENSES.find((l) => l.value === next);
          if (found) router.push(found.href);
        }}
        ariaLabel="Stock lenses"
        lenses={LENSES.map((l) => ({
          value: l.value,
          label: l.label,
          count: counts?.[l.value] ?? (l.value === 'cover' ? breachCount : undefined),
        }))}
      />
      {children}
    </WorkbenchCanvas>
  );
}
