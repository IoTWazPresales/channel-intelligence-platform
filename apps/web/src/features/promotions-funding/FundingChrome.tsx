'use client';

import { Button } from '@mui/material';
import { usePathname, useRouter } from 'next/navigation';
import type { ReactNode } from 'react';

import { navPageChrome } from '@/features/shell/navPageChrome';
import { DomainHeader } from '@/features/workbench-ui/DomainHeader';
import { LensTabs } from '@/features/workbench-ui/controls';

export const FUNDING_DESCRIPTION =
  'One promotion case from plan to settlement: propose or author the plan, approve it, watch it run, claim and settle the support.';

export type FundingLens = 'planner' | 'book' | 'claims' | 'payments' | 'templates' | 'pricing' | 'budgets';

const LENSES: { value: FundingLens; label: string; href: string }[] = [
  { value: 'planner', label: 'Promotion planner', href: '/promotions' },
  { value: 'book', label: 'Case book', href: '/commercial-planner/cpor-cases' },
  { value: 'claims', label: 'Claims evidence', href: '/commercial-planner/cpor-cases/claims' },
  { value: 'payments', label: 'Payments', href: '/commercial-planner/cpor-cases/payment-evidence-import' },
  { value: 'templates', label: 'Plan templates', href: '/commercial-planner/cpor-cases/historical-import' },
  { value: 'pricing', label: 'Terms & assumptions', href: '/admin/customer-commercial-terms' },
  { value: 'budgets', label: 'Budget ledger', href: '/budgets' },
];

export function fundingLensFromPath(pathname: string): FundingLens {
  if (pathname.startsWith('/promotions')) return 'planner';
  if (pathname.includes('/cpor-cases/claims')) return 'claims';
  if (pathname.includes('/payment-evidence-import')) return 'payments';
  if (pathname.includes('/historical-import')) return 'templates';
  if (pathname.includes('/customer-commercial-terms')) return 'pricing';
  if (pathname.startsWith('/budgets') || pathname.startsWith('/budget-requests')) return 'budgets';
  return 'book';
}

export function FundingChrome({
  actions,
  meta,
  counts,
  title,
  description,
}: {
  actions?: ReactNode;
  meta?: ReactNode;
  counts?: Partial<Record<FundingLens, number>>;
  title?: string;
  description?: string;
}) {
  const pathname = usePathname() || '/';
  const router = useRouter();
  const lens = fundingLensFromPath(pathname);
  const chrome = navPageChrome(pathname);
  return (
    <>
      <DomainHeader
        crumbs={chrome.crumbs}
        title={title ?? chrome.title}
        description={description ?? FUNDING_DESCRIPTION}
        meta={meta}
        actions={actions}
      />
      <LensTabs
        value={lens}
        onChange={(next) => {
          const href = LENSES.find((l) => l.value === next)?.href;
          if (href) router.push(href);
        }}
        ariaLabel="Promotions & Funding lenses"
        lenses={LENSES.map((l) => ({ value: l.value, label: l.label, count: counts?.[l.value] }))}
      />
    </>
  );
}

export function FundingNewPlanButton({ onClick }: { onClick: () => void }) {
  return (
    <Button variant="contained" size="small" onClick={onClick} data-testid="funding-new-plan">
      New promotion plan
    </Button>
  );
}
