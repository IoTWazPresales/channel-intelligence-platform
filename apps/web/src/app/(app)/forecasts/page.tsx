'use client';

import { ForecastHonesty } from '@/features/stock/StockThinLenses';
import { StockChrome } from '@/features/stock/StockChrome';

export default function ForecastsPage() {
  return (
    <StockChrome>
      <ForecastHonesty />
    </StockChrome>
  );
}
