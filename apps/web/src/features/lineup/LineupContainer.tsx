'use client';

import { Box } from '@mui/material';
import { alpha, useTheme } from '@mui/material/styles';
import { useSearchParams } from 'next/navigation';
import { Suspense, useState } from 'react';

import { LineupReadStrip } from '@/features/lineup/LineupReadStrip';
import { LineupRegimeStrip } from '@/features/lineup/LineupRegimeStrip';
import { LineupScopeBar } from '@/features/lineup/LineupScopeBar';
import { LineupTaskCrumb } from '@/features/lineup/LineupTaskCrumb';
import { LineupTrendInstrument } from '@/features/lineup/LineupTrendInstrument';
import { LineupWorkspace } from '@/features/lineup/LineupWorkspace';
import { DEFAULT_LINEUP_SCOPE, parseLineupApprovalFilter, type LineupScope } from '@/features/lineup/lineupViews';

function LineupContainerInner() {
  const theme = useTheme();
  const line = alpha(theme.palette.common.white, 0.12);
  const searchParams = useSearchParams();
  const approval = parseLineupApprovalFilter(searchParams?.get('approval'));
  const [scope, setScope] = useState<LineupScope>({ ...DEFAULT_LINEUP_SCOPE, approval });

  const activeScope: LineupScope = { ...scope, approval };

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0 }} data-testid="lineup-container">
      <Box
        sx={{
          display: 'flex',
          alignItems: 'baseline',
          justifyContent: 'space-between',
          gap: 2,
          px: 2.75,
          py: 1.25,
          borderBottom: `1px solid ${line}`,
          flexWrap: 'wrap',
        }}
      >
        <LineupTaskCrumb scope={activeScope} />
        <LineupRegimeStrip />
      </Box>
      <LineupScopeBar scope={activeScope} onScopeChange={(next) => setScope((s) => ({ ...s, ...next }))} />
      <Box sx={{ px: 2.75, py: 1.5, borderBottom: `1px solid ${line}`, bgcolor: '#1a1d23' }}>
        <LineupReadStrip />
        <LineupTrendInstrument />
      </Box>
      <Box sx={{ flex: 1, overflow: 'auto', minHeight: 0 }}>
        <LineupWorkspace />
      </Box>
    </Box>
  );
}

export function LineupContainer() {
  return (
    <Suspense fallback={<Box sx={{ p: 3 }}>Loading Lineup…</Box>}>
      <LineupContainerInner />
    </Suspense>
  );
}
