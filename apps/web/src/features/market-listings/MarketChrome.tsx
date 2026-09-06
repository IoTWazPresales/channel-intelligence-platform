'use client';

import { Button } from '@mui/material';
import NextLink from 'next/link';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import type { ReactNode } from 'react';

import { DomainHeader } from '@/features/workbench-ui/DomainHeader';
import { WorkbenchCanvas } from '@/features/workbench-ui/WorkbenchCanvas';
import { LensTabs } from '@/features/workbench-ui/controls';

export const MARKET_TITLE = 'Market & Listings';

export const MARKET_DESCRIPTION =
  'Evidence from the shelf: monitored retailer listings and prices, whether promotions are live at the planned price, and which competitor products sit against ours. Reused by planning, promotions, dashboards and attention.';

export type MarketLens =
  | 'listings'
  | 'history'
  | 'activation'
  | 'proposals'
  | 'competition'
  | 'competitor-prices'
  | 'competitor-listings'
  | 'quality';

const LENSES: { value: MarketLens; label: string; href: string }[] = [
  { value: 'listings', label: 'Monitored listings', href: '/listing-capture?tab=registry' },
  { value: 'history', label: 'Price history', href: '/listing-capture?tab=observations' },
  { value: 'activation', label: 'Promotion activation', href: '/listing-capture?tab=intelligence' },
  { value: 'proposals', label: 'Feed proposals', href: '/listing-capture?tab=proposals' },
  { value: 'competition', label: 'Competitor mappings', href: '/competition?tab=mappings' },
  { value: 'competitor-prices', label: 'Competitor prices', href: '/competition?tab=prices' },
  { value: 'competitor-listings', label: 'Competitor listings', href: '/competition?tab=competitor-listings' },
  { value: 'quality', label: 'Listing quality / SEO', href: '/listing-capture?tab=quality' },
];

export function marketLensFromLocation(pathname: string, search: URLSearchParams): MarketLens {
  const tab = (search.get('tab') || '').toLowerCase();
  if (pathname.startsWith('/competition')) {
    if (tab === 'prices') return 'competitor-prices';
    if (tab === 'competitor-listings') return 'competitor-listings';
    return 'competition';
  }
  if (tab === 'observations') return 'history';
  if (tab === 'intelligence') return 'activation';
  if (tab === 'proposals') return 'proposals';
  if (tab === 'quality') return 'quality';
  return 'listings';
}

function hrefWithScope(baseHref: string, search: URLSearchParams): string {
  const [path, qs] = baseHref.split('?');
  const next = new URLSearchParams(qs || '');
  for (const key of ['customer', 'product', 'activation']) {
    const v = search.get(key);
    if (v) next.set(key, v);
  }
  const s = next.toString();
  return s ? `${path}?${s}` : path;
}

export function MarketChrome({
  counts,
  meta,
  actions,
  children,
}: {
  counts?: Partial<Record<MarketLens, number>>;
  meta?: string;
  actions?: ReactNode;
  children?: ReactNode;
}) {
  const pathname = usePathname() || '/';
  const search = useSearchParams();
  const router = useRouter();
  const lens = marketLensFromLocation(pathname, search);

  return (
    <WorkbenchCanvas>
      <DomainHeader
        crumbs={[{ label: MARKET_TITLE }]}
        title={MARKET_TITLE}
        description={MARKET_DESCRIPTION}
        meta={meta}
        actions={
          actions ?? (
            <>
              <Button variant="outlined" size="small" component={NextLink} href="/reports">
                Open in Reports
              </Button>
            </>
          )
        }
      />
      <LensTabs
        value={lens}
        onChange={(next) => {
          const found = LENSES.find((l) => l.value === next);
          if (found) router.push(hrefWithScope(found.href, search));
        }}
        ariaLabel="Market lenses"
        lenses={LENSES.map((l) => ({
          value: l.value,
          label: l.label,
          count: counts?.[l.value],
        }))}
      />
      {children}
    </WorkbenchCanvas>
  );
}
