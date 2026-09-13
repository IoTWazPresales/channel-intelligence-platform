'use client';

import { useQuery } from '@tanstack/react-query';
import { usePathname, useRouter } from 'next/navigation';
import type { ReactNode } from 'react';

import { DomainHeader } from '@/features/workbench-ui/DomainHeader';
import { WorkbenchCanvas } from '@/features/workbench-ui/WorkbenchCanvas';
import { LensTabs } from '@/features/workbench-ui/controls';
import { apiGet } from '@/lib/api';

import { fmtInt } from './format';
import { ADMIN_DESCRIPTION, ADMIN_LEAVES, ADMIN_TITLE, adminLensFromPath, type AdminLens } from './adminPaths';
import type { AdministrationOverview } from './types';
import { useClientReady } from './useClientReady';

export type { AdminLens };

export { adminLensFromPath };

export function AdminChrome({ children }: { children?: ReactNode }) {
  const pathname = usePathname() || '/admin/users';
  const router = useRouter();
  const lens = adminLensFromPath(pathname);
  const ready = useClientReady();
  const { data: summaryData } = useQuery({
    queryKey: ['administration', 'overview'],
    queryFn: ({ signal }) => apiGet<AdministrationOverview>('/api/v1/administration/overview', { signal }),
    staleTime: 30_000,
  });
  const summary = ready ? summaryData : undefined;
  const leaf = ADMIN_LEAVES.find((l) => l.value === lens);

  const meta =
    summary && !summary.data_unavailable
      ? `${fmtInt(summary.users)} users · ${fmtInt(summary.jobs_running)} running`
      : undefined;

  return (
    <WorkbenchCanvas>
      <DomainHeader
        crumbs={
          leaf
            ? [{ label: ADMIN_TITLE, href: '/admin/users' }, { label: leaf.label }]
            : [{ label: ADMIN_TITLE }]
        }
        title={ADMIN_TITLE}
        description={ADMIN_DESCRIPTION}
        meta={meta}
      />
      {lens !== 'hub' ? (
        <LensTabs
          value={lens}
          onChange={(next) => {
            const href = ADMIN_LEAVES.find((l) => l.value === next)?.href;
            if (href) router.push(href);
          }}
          ariaLabel="Administration"
          lenses={ADMIN_LEAVES.map((l) => ({ value: l.value, label: l.label }))}
        />
      ) : null}
      {children}
    </WorkbenchCanvas>
  );
}
