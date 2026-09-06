'use client';

import { DataChrome } from '@/features/data-stewardship/DataChrome';
import { ProductMasterGapWorklistView } from '@/features/imports/ProductMasterGapWorklistView';

export default function ProductMasterGapsPage() {
  return (
    <DataChrome>
      <ProductMasterGapWorklistView />
    </DataChrome>
  );
}
