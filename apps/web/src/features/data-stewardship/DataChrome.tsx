'use client';

import CloudUploadOutlinedIcon from '@mui/icons-material/CloudUploadOutlined';
import { Button, Stack, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import NextLink from 'next/link';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import type { ReactNode } from 'react';

import { dataAlsoHereItems } from '@/features/data-stewardship/dataAlsoHere';
import { matchNavLeaf } from '@/features/shell/navPageChrome';
import { useCurrentUser } from '@/features/shell/useCurrentUser';
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
  const searchParams = useSearchParams();
  const searchStr = searchParams?.toString() ? `?${searchParams.toString()}` : '';
  const router = useRouter();
  const lens = dataLensFromPath(pathname);
  const { data: me } = useCurrentUser();
  const role = me?.role ? String(me.role) : null;
  const match = matchNavLeaf(pathname, searchStr);
  const leafLabel =
    title ??
    (match?.group.id === 'data' && match.item.href !== '/admin/imports' ? match.item.label : undefined);
  const tabHrefs = LENSES.map((l) => l.href);
  const alsoHere = dataAlsoHereItems(role, tabHrefs);
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
    steward: summary?.candidates_needs_review,
    ...counts,
  };

  const meta = summary
    ? [
        `${summary.jobs_last_7d} jobs in last 7 days`,
        `${summary.candidates_needs_review} candidates need review`,
        `${summary.products} products`,
      ].join(' · ')
    : undefined;

  return (
    <WorkbenchCanvas>
      <DomainHeader
        crumbs={
          leafLabel
            ? [{ label: DATA_TITLE, href: '/admin/imports' }, { label: leafLabel }]
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
      {alsoHere.length ? (
        <Stack
          direction="row"
          spacing={0.75}
          flexWrap="wrap"
          useFlexGap
          alignItems="center"
          sx={{ mt: 1, mb: 0.5 }}
          data-testid="data-also-here"
        >
          <Typography variant="caption" color="text.secondary" sx={{ mr: 0.5 }}>
            Also in this area
          </Typography>
          {alsoHere.map((l) => {
            const active = match?.item.href === l.href;
            return (
              <Button
                key={`${l.href}-${l.label}`}
                size="small"
                variant={active ? 'contained' : 'outlined'}
                component={NextLink}
                href={l.href}
                sx={{ textTransform: 'none', py: 0.25 }}
                data-testid={`data-also-here-${l.label.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`}
              >
                {l.label}
              </Button>
            );
          })}
        </Stack>
      ) : null}
      {children}
    </WorkbenchCanvas>
  );
}
