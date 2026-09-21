'use client';

import { InboundShipmentsWorkspace } from '@/features/supply-inbound/InboundShipmentsWorkspace';
import { SupplyChrome } from '@/features/supply-inbound/SupplyChrome';

export default function SupplyShipmentsPage() {
  return (
    <SupplyChrome>
      <InboundShipmentsWorkspace />
    </SupplyChrome>
  );
}
