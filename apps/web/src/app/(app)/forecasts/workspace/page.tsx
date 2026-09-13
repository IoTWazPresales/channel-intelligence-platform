'use client';

import { ForecastsWorkspace } from '@/features/stock/ForecastsWorkspace';
import { StockChrome } from '@/features/stock/StockChrome';

export default function ForecastsWorkspacePage() {
  return (
    <StockChrome>
      <ForecastsWorkspace />
    </StockChrome>
  );
}
