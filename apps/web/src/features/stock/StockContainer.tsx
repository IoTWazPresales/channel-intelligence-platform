'use client';

import { Box } from '@mui/material';
import { alpha, useTheme } from '@mui/material/styles';
import dynamic from 'next/dynamic';
import { useSearchParams } from 'next/navigation';
import { Suspense } from 'react';

import { PlanVsExecutedView } from '@/features/plan-vs-executed/PlanVsExecutedView';
import { ChannelOpsStockWorkspace } from '@/features/stock/ChannelOpsStockWorkspace';
import { CoverLensView } from '@/features/stock/CoverLensView';
import { StockLensSwitcher, StockTaskCrumb } from '@/features/stock/StockLensSwitcher';
import { StockRegimeStrip } from '@/features/stock/StockRegimeStrip';
import { parseStockLens, type StockLensId } from '@/features/stock/stockLenses';

const InboundShipmentsWorkspace = dynamic(
  () => import('@/app/(app)/shipping/page').then((m) => m.InboundShipmentsWorkspace),
  { ssr: false, loading: () => <Box sx={{ p: 3 }}>Loading inbound…</Box> },
);

function StockLensBody({ lens }: { lens: StockLensId }) {
  if (lens === 'execution') {
    return (
      <Box data-testid="stock-execution-lens" sx={{ px: { xs: 1, md: 0 } }}>
        <PlanVsExecutedView />
      </Box>
    );
  }
  if (lens === 'cover') return <CoverLensView />;
  if (lens === 'inbound') {
    return (
      <Box data-testid="stock-inbound-lens" sx={{ px: { xs: 1, md: 2 } }}>
        <InboundShipmentsWorkspace />
      </Box>
    );
  }
  return (
    <Box sx={{ px: { xs: 1, md: 2 }, pb: 2 }}>
      <ChannelOpsStockWorkspace />
    </Box>
  );
}

function StockContainerInner() {
  const theme = useTheme();
  const line = alpha(theme.palette.common.white, 0.12);
  const searchParams = useSearchParams();
  const lens = parseStockLens(searchParams?.get('lens'));

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0 }} data-testid="stock-container">
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
        <StockTaskCrumb lens={lens} />
        <StockRegimeStrip />
      </Box>
      <Box sx={{ px: 2.75, pt: 1.5, bgcolor: '#1a1d23', borderBottom: `1px solid ${line}` }}>
        <StockLensSwitcher lens={lens} />
      </Box>
      <Box sx={{ flex: 1, overflow: 'auto', minHeight: 0 }}>
        <StockLensBody lens={lens} />
      </Box>
    </Box>
  );
}

export function StockContainer() {
  return (
    <Suspense fallback={<Box sx={{ p: 3 }}>Loading Stock…</Box>}>
      <StockContainerInner />
    </Suspense>
  );
}
