'use client';

import { StockChrome } from '@/features/stock/StockChrome';
import { ReplenishmentBoard } from '@/features/store-dc/ReplenishmentBoard';

export default function StoreReplenishmentPage() {
  return (
    <StockChrome>
      <ReplenishmentBoard />
    </StockChrome>
  );
}
