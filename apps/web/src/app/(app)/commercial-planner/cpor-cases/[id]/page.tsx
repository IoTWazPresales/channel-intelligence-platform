'use client';

import { useParams } from 'next/navigation';

import { FundingChrome } from '@/features/promotions-funding/FundingChrome';
import { SettlementDeskLive } from '@/features/settlement/SettlementDeskLive';

export default function CporCaseDetailPage() {
  const params = useParams<{ id: string }>();
  const caseId = Number(params.id);
  // The desk is a Promotions & Funding lens like every other funding route: it needs the
  // WorkbenchCanvas inset and the lens tabs. hideDomainHeader because the desk renders its
  // own DomainHeader (case code, customer, stage CTA) — two page headers would be clutter.
  return (
    <FundingChrome hideDomainHeader>
      <SettlementDeskLive caseId={caseId} />
    </FundingChrome>
  );
}
