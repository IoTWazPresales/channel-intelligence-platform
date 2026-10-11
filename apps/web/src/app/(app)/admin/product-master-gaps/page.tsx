'use client';

import { StewardWriteGate } from '@/components/StewardWriteGate';
import { DataChrome } from '@/features/data-stewardship/DataChrome';
import { ProductMasterGapWorklistView } from '@/features/imports/ProductMasterGapWorklistView';

export default function ProductMasterGapsPage() {
  return (
    <DataChrome>
      <StewardWriteGate>
        <ProductMasterGapWorklistView />
      </StewardWriteGate>
    </DataChrome>
  );
}
