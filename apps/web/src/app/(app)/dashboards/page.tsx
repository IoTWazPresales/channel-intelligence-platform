'use client';

import { DashboardWorkspace } from '@/features/dashboards/DashboardWorkspace';
import { OverviewChrome } from '@/features/overview/OverviewChrome';

export default function DashboardsPage() {
  return (
    <OverviewChrome>
      <DashboardWorkspace hidePageHeader />
    </OverviewChrome>
  );
}
