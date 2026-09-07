'use client';

import { SupplyChrome } from '@/features/supply-inbound/SupplyChrome';
import { SupplyOverview } from '@/features/supply-inbound/SupplyOverview';

export default function SupplyPage() {
  return (
    <SupplyChrome>
      <SupplyOverview />
    </SupplyChrome>
  );
}
