'use client';

import { InboundShipmentsWorkspace } from '@/app/(app)/shipping/page';
import { SupplyChrome } from '@/features/supply-inbound/SupplyChrome';

export default function SupplyShipmentsPage() {
  return (
    <SupplyChrome>
      <InboundShipmentsWorkspace />
    </SupplyChrome>
  );
}
