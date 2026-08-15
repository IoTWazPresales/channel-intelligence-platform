'use client';

import { PageHeader } from '@/components/PageHeader';
import { navPageChrome } from '@/features/shell/navPageChrome';
import { ProductMasterGapWorklistView } from '@/features/imports/ProductMasterGapWorklistView';

export default function ProductMasterGapsPage() {
  return (
    <>
      <PageHeader {...navPageChrome('/admin/product-master-gaps')} />
      <ProductMasterGapWorklistView />
    </>
  );
}
