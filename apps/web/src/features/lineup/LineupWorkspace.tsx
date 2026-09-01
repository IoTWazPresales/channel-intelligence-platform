'use client';

import { Box } from '@mui/material';
import { alpha, useTheme } from '@mui/material/styles';
import { useQuery } from '@tanstack/react-query';
import { useSearchParams } from 'next/navigation';

import { LineupPlanActionBar } from '@/features/lineup/LineupPlanActionBar';
import { LineupPlanGrid } from '@/features/lineup/LineupPlanGrid';
import { type LineupPlanRow } from '@/features/lineup/lineupTypes';
import { parseLineupApprovalFilter } from '@/features/lineup/lineupViews';
import { ModuleDataSection } from '@/components/ModuleDataSection';
import { apiGet } from '@/lib/api';
import { toQueryError } from '@/lib/queryError';

export function LineupWorkspace() {
  const theme = useTheme();
  const searchParams = useSearchParams();
  const pendingOnly = parseLineupApprovalFilter(searchParams?.get('approval')) === 'pending';

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['lineup-items'],
    queryFn: ({ signal }) => apiGet<LineupPlanRow[]>('/api/v1/lineup/items', { signal }),
  });

  const rows = data ?? [];

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
        <Box sx={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0, bgcolor: alpha(theme.palette.common.black, 0.12) }}>
          <LineupPlanGrid rows={rows} pendingOnly={pendingOnly} />
          <LineupPlanActionBar />
        </Box>
      </ModuleDataSection>
    </Box>
  );
}
