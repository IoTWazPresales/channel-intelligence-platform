'use client';

import { useQuery } from '@tanstack/react-query';
import { usePathname, useRouter } from 'next/navigation';
import type { ReactNode } from 'react';

import { DomainHeader } from '@/features/workbench-ui/DomainHeader';
import { WorkbenchCanvas } from '@/features/workbench-ui/WorkbenchCanvas';
import { LensTabs } from '@/features/workbench-ui/controls';
import { apiGet } from '@/lib/api';

import { fmtInt } from './format';
import { PLANNING_DESCRIPTION, PLANNING_LEAVES, PLANNING_TITLE, planningLensFromPath, type PlanningLens } from './planningPaths';
import type { PlanningOverview } from './types';
import { useClientReady } from './useClientReady';

export type { PlanningLens };

export { planningLensFromPath };

export function PlanningChrome({ children }: { children?: ReactNode }) {
  const pathname = usePathname() || '/lineup';
  const router = useRouter();
  const lens = planningLensFromPath(pathname);
  const ready = useClientReady();
  const { data: summaryData } = useQuery({
    queryKey: ['planning', 'overview'],
    queryFn: ({ signal }) => apiGet<PlanningOverview>('/api/v1/planning/overview', { signal }),
    staleTime: 30_000,
  });
  const summary = ready ? summaryData : undefined;
  const leaf = PLANNING_LEAVES.find((l) => l.value === lens);

  const meta =
    summary && !summary.data_unavailable
      ? `${fmtInt(summary.cases)} cases · ${fmtInt(summary.lines)} lines`
      : undefined;

  return (
    <WorkbenchCanvas>
      <DomainHeader
        crumbs={
          leaf
            ? [{ label: PLANNING_TITLE, href: '/lineup' }, { label: leaf.label }]
            : [{ label: PLANNING_TITLE }]
        }
        title={PLANNING_TITLE}
        description={PLANNING_DESCRIPTION}
        meta={meta}
      />
      {lens !== 'hub' ? (
        <LensTabs
          value={lens}
          onChange={(next) => {
            const href = PLANNING_LEAVES.find((l) => l.value === next)?.href;
            if (href) router.push(href);
          }}
          ariaLabel="Planning"
          lenses={PLANNING_LEAVES.map((l) => ({ value: l.value, label: l.label }))}
        />
      ) : null}
      {children}
    </WorkbenchCanvas>
  );
}
