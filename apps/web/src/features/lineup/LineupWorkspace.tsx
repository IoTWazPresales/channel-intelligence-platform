'use client';

import { Box } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { useRouter, useSearchParams } from 'next/navigation';

import { LineupGroupsPanel } from '@/features/lineup/LineupGroupsPanel';
import { LineupPlanActionBar } from '@/features/lineup/LineupPlanActionBar';
import { LineupPlanGrid } from '@/features/lineup/LineupPlanGrid';
import { type LineupPlanRow } from '@/features/lineup/lineupTypes';
import {
  filterLineupRowsByExactProductId,
  filterLineupRowsBySlice,
  parseExactLineupProductId,
  parseLineupApprovalFilter,
  parseLineupSlice,
} from '@/features/lineup/lineupViews';
import { ModuleDataSection } from '@/components/ModuleDataSection';
import { apiGet } from '@/lib/api';
import { toQueryError } from '@/lib/queryError';

export function LineupWorkspace() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const slice = parseLineupSlice(searchParams?.get('customer'), searchParams?.get('period'));
  const pendingOnly = parseLineupApprovalFilter(searchParams?.get('approval')) === 'pending';
  const productId = parseExactLineupProductId(searchParams?.get('product'));

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['lineup-items'],
    queryFn: ({ signal }) => apiGet<LineupPlanRow[]>('/api/v1/lineup/items', { signal }),
  });

  const rows = data ?? [];
  // A slice is a filtered view of the master line-up (same rows, same edits), never a copy.
  const sliced = filterLineupRowsBySlice(rows, slice);
  const scoped = productId == null ? sliced : filterLineupRowsByExactProductId(sliced, productId);
  const openSlice = (customerId: number, periodStart: string) => {
    const params = new URLSearchParams(searchParams?.toString() ?? '');
    params.set('customer', String(customerId));
    params.set('period', periodStart);
    router.replace(`/lineup/cases?${params.toString()}`, { scroll: false });
  };

  return (
    <Box data-testid="lineup-workspace" sx={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0 }}>
      <ModuleDataSection
        isLoading={isLoading}
        isError={isError}
        error={toQueryError(error)}
        onRetry={() => void refetch()}
        isEmpty={rows.length === 0}
        empty={{
          title: 'No line-up plan rows',
          description: 'Use Calc and Apply on the net requirement bar when forecast pairs exist, or ingest via Steward.',
          primary: { label: 'Steward imports', href: '/admin/imports' },
        }}
      >
        <LineupGroupsPanel rows={rows} slice={slice} onOpen={(g) => openSlice(g.customerId, g.periodStart)} />
        <Box sx={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0 }}>
          <LineupPlanGrid rows={scoped} pendingOnly={pendingOnly} />
        </Box>
      </ModuleDataSection>
      <LineupPlanActionBar />
    </Box>
  );
}
