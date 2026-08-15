'use client';

import { PageHeader } from '@/components/PageHeader';
import { navPageChrome } from '@/features/shell/navPageChrome';
import { PlanVsExecutedView } from '@/features/plan-vs-executed/PlanVsExecutedView';

export default function PlanVsExecutedPage() {
  return (
    <>
      <PageHeader {...navPageChrome('/plan-vs-executed')} />
      <PlanVsExecutedView />
    </>
  );
}
