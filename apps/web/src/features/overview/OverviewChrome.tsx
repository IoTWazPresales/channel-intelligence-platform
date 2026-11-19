'use client';

import { usePathname } from 'next/navigation';
import type { ReactNode } from 'react';

import { DomainHeader } from '@/features/workbench-ui/DomainHeader';
import { WorkbenchCanvas } from '@/features/workbench-ui/WorkbenchCanvas';
import { useBriefSignals } from '@/features/shell/useBriefSignals';

import { OVERVIEW_DESCRIPTION, OVERVIEW_LEAVES, OVERVIEW_TITLE, overviewLeafFromPath } from './overviewPaths';
import { useClientReady } from './useClientReady';

export function OverviewChrome({
  title,
  description,
  meta: metaOverride,
  actions,
  children,
}: {
  title?: string;
  /** Page-specific description; defaults to the Overview description. */
  description?: string;
  /** Page-specific meta line; `null` hides the brief-signals meta. */
  meta?: ReactNode | null;
  actions?: ReactNode;
  children?: ReactNode;
}) {
  const pathname = usePathname() || '/brief';
  const leaf = overviewLeafFromPath(pathname);
  const leafMeta = OVERVIEW_LEAVES.find((l) => l.value === leaf);
  const ready = useClientReady();
  const { data: briefData } = useBriefSignals();
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
        description={description ?? OVERVIEW_DESCRIPTION}
        meta={metaOverride === undefined ? meta : metaOverride ?? undefined}
        actions={actions}
      />
      {children}
    </WorkbenchCanvas>
  );
}
