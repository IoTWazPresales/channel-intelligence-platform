import { OverviewChrome } from '@/features/overview/OverviewChrome';
import { OverviewHub } from '@/features/overview/OverviewHub';

export default function BriefPage() {
  return (
    <OverviewChrome>
      <OverviewHub />
    </OverviewChrome>
  );
}
