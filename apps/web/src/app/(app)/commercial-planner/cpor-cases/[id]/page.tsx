'use client';

import { useParams } from 'next/navigation';

import { SettlementDeskLive } from '@/features/settlement/SettlementDeskLive';

export default function CporCaseDetailPage() {
  const params = useParams<{ id: string }>();
  const caseId = Number(params.id);
  return <SettlementDeskLive caseId={caseId} />;
}
