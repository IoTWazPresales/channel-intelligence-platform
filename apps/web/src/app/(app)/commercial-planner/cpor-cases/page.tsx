'use client';

import { FundingChrome } from '@/features/promotions-funding/FundingChrome';
import { CaseBookSurface } from '@/features/promotions-funding/CaseBookSurface';

export default function CporCasesListPage() {
  return (
    <FundingChrome>
      <CaseBookSurface />
    </FundingChrome>
  );
}
