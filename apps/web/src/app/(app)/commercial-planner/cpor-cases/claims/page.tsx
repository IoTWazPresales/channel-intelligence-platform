'use client';

import { FundingChrome } from '@/features/promotions-funding/FundingChrome';
import { FundingPointerLens } from '@/features/promotions-funding/FundingPointerLens';

export default function CporClaimsPage() {
  return (
    <FundingChrome>
      <FundingPointerLens
        testId="funding-claims"
        title="Claim evidence is matched per case"
        description="Claim files are stewarded in Import Center (cpor_claim_evidence). Out-of-window rows and unresolved product tokens stay on the import job. Apply still happens on the case settlement desk — this lens does not list cases or invent KPIs."
        primary={{ label: 'Open Import Center', href: '/admin/imports?template=cpor_claim_evidence' }}
        secondary={{ label: 'Case book', href: '/commercial-planner/cpor-cases' }}
      />
    </FundingChrome>
  );
}
