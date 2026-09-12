'use client';

import { usePathname } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import type { ReactNode } from 'react';

import { DomainHeader } from '@/features/workbench-ui/DomainHeader';
import { WorkbenchCanvas } from '@/features/workbench-ui/WorkbenchCanvas';
import { apiGet } from '@/lib/api';

import { OVERVIEW_DESCRIPTION, OVERVIEW_LEAVES, OVERVIEW_TITLE, overviewLeafFromPath } from './overviewPaths';
import { useClientReady } from './useClientReady';

type BriefSignalsResponse = {
  as_of?: string;
  signal_count?: number;
  signals?: unknown[];
};

export function OverviewChrome({
  title,
  children,
}: {
  title?: string;
  children?: ReactNode;
}) {
  const pathname = usePathname() || '/brief';
  const leaf = overviewLeafFromPath(pathname);
  const leafMeta = OVERVIEW_LEAVES.find((l) => l.value === leaf);
  const ready = useClientReady();
  const { data: briefData } = useQuery({
    queryKey: ['brief', 'signals'],
    queryFn: ({ signal }) => apiGet<BriefSignalsResponse>('/api/v1/brief/signals', { signal }),
    staleTime: 30_000,
  });
  const brief = ready ? briefData : undefined;
  const signalCount = brief?.signal_count ?? brief?.signals?.length;
  const meta =
    signalCount == null
      ? undefined
      : `${signalCount} signal${signalCount === 1 ? '' : 's'} · live from brief/signals`;

  const crumbs =
    leaf === 'hub'
      ? [{ label: OVERVIEW_TITLE }]
      : [{ label: OVERVIEW_TITLE, href: '/brief' }, { label: leafMeta?.label ?? leaf }];

  return (
    <WorkbenchCanvas>
      <DomainHeader
        crumbs={crumbs}
        title={title ?? OVERVIEW_TITLE}
        description={OVERVIEW_DESCRIPTION}
        meta={meta}
      />
      {children}
    </WorkbenchCanvas>
  );
}
