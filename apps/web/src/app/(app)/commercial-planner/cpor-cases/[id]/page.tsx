'use client';

import { useParams } from 'next/navigation';

import { CporCaseWorkspace } from '@/features/cpor/CporCaseWorkspace';

export default function CporCaseDetailPage() {
  const params = useParams<{ id: string }>();
  const caseId = Number(params.id);
  return <CporCaseWorkspace caseId={caseId} />;
}
