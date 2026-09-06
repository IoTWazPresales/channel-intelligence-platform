'use client';

import CloudUploadOutlinedIcon from '@mui/icons-material/CloudUploadOutlined';
import { Button } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import NextLink from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import type { ReactNode } from 'react';

import { DomainHeader } from '@/features/workbench-ui/DomainHeader';
import { WorkbenchCanvas } from '@/features/workbench-ui/WorkbenchCanvas';
import { LensTabs } from '@/features/workbench-ui/controls';
import { apiGet } from '@/lib/api';

import type { StewardshipSummary } from './types';
import { useClientReady } from './useClientReady';

export const DATA_TITLE = 'Data & Stewardship';

export const DATA_DESCRIPTION =
  'Bring files in, resolve unknown names to master records, and keep master data trustworthy. Every fact in CIP arrives through this door.';

export type DataLens = 'imports' | 'steward' | 'masters' | 'audit';

const LENSES: { value: DataLens; label: string; href: string }[] = [
  { value: 'imports', label: 'Import Center', href: '/admin/imports' },
  { value: 'steward', label: 'Steward queue', href: '/admin/mappings' },
  { value: 'masters', label: 'Master data', href: '/admin/masters' },
  { value: 'audit', label: 'Steward audit', href: '/admin/steward-audit' },
];

export function dataLensFromPath(pathname: string): DataLens {
  if (pathname.startsWith('/admin/imports')) return 'imports';
  if (pathname.startsWith('/admin/mappings')) return 'steward';
  if (pathname.startsWith('/admin/steward-audit')) return 'audit';
  return 'masters';
}

export function DataChrome({
  counts,
  title,
  children,
}: {
  counts?: Partial<Record<DataLens, number>>;
  title?: string;
  children?: ReactNode;
}) {
  const pathname = usePathname() || '/admin/imports';
  const router = useRouter();
  const lens = dataLensFromPath(pathname);
  const ready = useClientReady();
  const { data: summaryData } = useQuery({
    queryKey: ['imports', 'stewardship-summary'],
    queryFn: ({ signal }) => apiGet<StewardshipSummary>('/api/v1/imports/stewardship-summary', { signal }),
    staleTime: 30_000,
  });
  const summary = ready ? summaryData : undefined;

  const failedPlusPending =
    summary == null ? undefined : (summary.failed_all ?? 0) + (summary.pending_all ?? 0);
  const tabCounts: Partial<Record<DataLens, number>> = {
    imports: failedPlusPending,
    steward: summary?.legacy_queue_open,
    ...counts,
  };

  const meta = summary
    ? [
        `${summary.jobs_last_7d} jobs in last 7 days`,
        `${summary.legacy_queue_open} legacy queue rows`,
        `${summary.products} products`,
      ].join(' · ')
    : undefined;

  return (
    <WorkbenchCanvas>
      <DomainHeader
        crumbs={
          title
            ? [{ label: DATA_TITLE, href: '/admin/imports' }, { label: title }]
            : [{ label: DATA_TITLE }]
        }
        title={DATA_TITLE}
        description={DATA_DESCRIPTION}
        meta={meta}
        actions={
          <Button
            variant="contained"
            size="small"
            component={NextLink}
            href="/admin/imports"
            startIcon={<CloudUploadOutlinedIcon />}
            data-testid="data-new-import"
          >
            New import
          </Button>
        }
      />
      <LensTabs
        value={lens}
        onChange={(next) => {
          const href = LENSES.find((l) => l.value === next)?.href;
          if (href) router.push(href);
        }}
        ariaLabel="Data & Stewardship"
        lenses={LENSES.map((l) => ({ value: l.value, label: l.label, count: tabCounts[l.value] }))}
      />
      {children}
    </WorkbenchCanvas>
  );
}
