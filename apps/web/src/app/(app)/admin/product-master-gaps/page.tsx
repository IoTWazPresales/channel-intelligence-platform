'use client';

import { PageHeader } from '@/components/PageHeader';
import { ProductMasterGapWorklistView } from '@/features/imports/ProductMasterGapWorklistView';

export default function ProductMasterGapsPage() {
  return (
    <>
      <PageHeader
        crumbs={[{ label: 'Master Data' }, { label: 'Product catalogue gaps' }]}
        title="Product catalogue gaps"
      />
      <ProductMasterGapWorklistView />
    </>
  );
}
