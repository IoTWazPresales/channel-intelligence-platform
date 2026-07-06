'use client';

import { PageHeader } from '@/components/PageHeader';
import { PlanVsExecutedView } from '@/features/plan-vs-executed/PlanVsExecutedView';

export default function PlanVsExecutedPage() {
  return (
    <>
      <PageHeader
        crumbs={[{ label: 'Intelligence' }, { label: 'Plan vs Executed' }]}
        title="Plan vs Executed"
      />
      <PlanVsExecutedView />
    </>
  );
}
