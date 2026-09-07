'use client';

import { useQuery } from '@tanstack/react-query';
import { usePathname, useRouter } from 'next/navigation';
import type { ReactNode } from 'react';

import { DomainHeader } from '@/features/workbench-ui/DomainHeader';
import { WorkbenchCanvas } from '@/features/workbench-ui/WorkbenchCanvas';
import { LensTabs } from '@/features/workbench-ui/controls';
import { apiGet } from '@/lib/api';

import { fmtInt } from './format';
import { SUPPLY_LEAVES, supplyLensFromPath, type SupplyLens } from './supplyPaths';
import type { SupplyOverview } from './types';
import { useClientReady } from './useClientReady';

export const SUPPLY_TITLE = 'Supply & Inbound';

export const SUPPLY_DESCRIPTION =
  'Inbound shipments through their lifecycle, receipt and proof-of-delivery evidence, PO coverage.';

export type { SupplyLens };

export { supplyLensFromPath };

export function SupplyChrome({ children }: { children?: ReactNode }) {
  const pathname = usePathname() || '/supply';
  const router = useRouter();
  const lens = supplyLensFromPath(pathname);
  const ready = useClientReady();
  const { data: summaryData } = useQuery({
    queryKey: ['supply', 'overview'],
    queryFn: ({ signal }) => apiGet<SupplyOverview>('/api/v1/supply/overview', { signal }),
    staleTime: 30_000,
  });
  const summary = ready ? summaryData : undefined;
  const leaf = SUPPLY_LEAVES.find((l) => l.value === lens);

  const meta = summary
    ? `${fmtInt(summary.open_lines)} open · ${fmtInt(summary.eta_past_no_pod_lines)} past ETA`
    : undefined;

  return (
    <WorkbenchCanvas>
      <DomainHeader
        crumbs={
          leaf
            ? [{ label: SUPPLY_TITLE, href: '/supply' }, { label: leaf.label }]
            : [{ label: SUPPLY_TITLE }]
        }
        title={SUPPLY_TITLE}
        description={SUPPLY_DESCRIPTION}
        meta={meta}
      />
      {lens !== 'hub' ? (
        <LensTabs
          value={lens}
          onChange={(next) => {
            const href = SUPPLY_LEAVES.find((l) => l.value === next)?.href;
            if (href) router.push(href);
          }}
          ariaLabel="Supply & Inbound"
          lenses={SUPPLY_LEAVES.map((l) => ({ value: l.value, label: l.label }))}
        />
      ) : null}
      {children}
    </WorkbenchCanvas>
  );
}
