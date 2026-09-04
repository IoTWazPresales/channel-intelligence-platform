'use client';

import { PlanVsExecutedView } from '@/features/plan-vs-executed/PlanVsExecutedView';
import { PageHeader } from '@/components/PageHeader';
import { navPageChrome } from '@/features/shell/navPageChrome';

/** Legacy route — middleware redirects to /stock?lens=execution. */
export default function PlanVsExecutedPage() {
  return (
    <>
      <PageHeader {...navPageChrome('/stock', { search: '?lens=execution' })} />
      <PlanVsExecutedView />
    </>
  );
}
