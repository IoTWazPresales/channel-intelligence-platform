'use client';

import { LineupContainer } from '@/features/lineup/LineupContainer';
import { PlanningChrome } from '@/features/planning/PlanningChrome';

export default function LineupCasesPage() {
  return (
    <PlanningChrome>
      <LineupContainer />
    </PlanningChrome>
  );
}
