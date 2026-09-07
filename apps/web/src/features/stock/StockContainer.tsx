'use client';

import { Box } from '@mui/material';
import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useEffect } from 'react';

import { CoverLensView } from '@/features/stock/CoverLensView';
import { ExecutionLensView } from '@/features/stock/ExecutionLensView';
import { MovementLensView } from '@/features/stock/MovementLensView';
import { StockChrome } from '@/features/stock/StockChrome';
import { parseStockLens, type StockLensId } from '@/features/stock/stockLenses';

function StockLensBody({ lens }: { lens: StockLensId }) {
  if (lens === 'execution') {
    return (
      <Box data-testid="stock-execution-lens" sx={{ px: { xs: 1, md: 0 } }}>
        <ExecutionLensView />
      </Box>
    );
  }
  if (lens === 'cover') return <CoverLensView />;
  if (lens === 'movement') {
    return (
      <Box sx={{ px: { xs: 1, md: 2 }, pb: 2 }}>
        <MovementLensView />
      </Box>
    );
  }
  return null;
}

function StockContainerInner() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const lens = parseStockLens(searchParams?.get('lens'));

  useEffect(() => {
    if (lens === 'sellthrough') router.replace('/channel-intelligence');
    if (lens === 'forecast') router.replace('/forecasts');
    if (lens === 'inbound') {
      const next = new URLSearchParams(searchParams.toString());
      next.delete('lens');
      const qs = next.toString();
      router.replace(qs ? `/supply/shipments?${qs}` : '/supply/shipments');
    }
  }, [lens, router, searchParams]);

  if (lens === 'inbound') {
    return (
      <Box sx={{ p: 3 }} data-testid="stock-container">
        Opening shipments…
      </Box>
    );
  }

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0 }} data-testid="stock-container">
      <StockChrome>
        <StockLensBody lens={lens} />
      </StockChrome>
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
