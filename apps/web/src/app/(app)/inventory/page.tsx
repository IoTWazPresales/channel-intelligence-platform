'use client';

import { Box } from '@mui/material';
import { Suspense } from 'react';

import { CoverLensView } from '@/features/stock/CoverLensView';
import { StockChrome } from '@/features/stock/StockChrome';

export default function InventoryPage() {
  return (
    <Suspense fallback={<Box sx={{ p: 3 }}>Loading Inventory.</Box>}>
      <StockChrome>
        <CoverLensView />
      </StockChrome>
    </Suspense>
  );
}
