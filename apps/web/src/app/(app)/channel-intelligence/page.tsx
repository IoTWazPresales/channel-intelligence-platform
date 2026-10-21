'use client';

import { StockChrome } from '@/features/stock/StockChrome';
import { SellThroughOverview } from '@/features/stock/SellThroughOverview';

export default function ChannelIntelligencePage() {
  return (
    <StockChrome>
      <SellThroughOverview />
    </StockChrome>
  );
}
