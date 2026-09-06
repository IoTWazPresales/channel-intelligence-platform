'use client';

import { Button } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import NextLink from 'next/link';
import { usePathname, useRouter } from 'next/navigation';

import { fmtCompact, fmtPct } from '@/features/promotions-funding/format';
import { countPlanning } from '@/features/promotions-funding/lifecycle';
import type { CporCasesPage } from '@/features/promotions-funding/types';
import { apiGet } from '@/lib/api';
import { DomainHeader } from '@/features/workbench-ui/DomainHeader';
import { WorkbenchCanvas } from '@/features/workbench-ui/WorkbenchCanvas';
import { LensTabs } from '@/features/workbench-ui/controls';
import type { ReactNode } from 'react';

export const FUNDING_TITLE = 'Promotions & Funding';

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

type SettlementBook = {
  book_total?: number;
  currency_code?: string;
  open_case_count?: number;
};

type PortfolioIntel = {
  totals?: { delivery_rate?: number | null };
  evidence_basis_mix?: { claim_evidenced?: number; source_attested?: number; none?: number };
};

type BriefMeta = {
  tenant_stamp?: string;
  tenant_period?: string;
};

export function FundingChrome({
  counts,
  title,
  children,
}: {
  counts?: Partial<Record<FundingLens, number>>;
  title?: string;
  children?: ReactNode;
}) {
  const pathname = usePathname() || '/';
  const router = useRouter();
  const lens = fundingLensFromPath(pathname);

  const { data: listPage } = useQuery({
    queryKey: ['cpor', 'cases', 'funding-chrome'],
    queryFn: ({ signal }) => apiGet<CporCasesPage>('/api/v1/cpor/cases?page=1&page_size=1', { signal }),
    staleTime: 30_000,
  });
  const { data: settlement } = useQuery({
    queryKey: ['cpor', 'settlement', 'book'],
    queryFn: ({ signal }) => apiGet<SettlementBook>('/api/v1/cpor/settlement/book', { signal }),
    staleTime: 30_000,
  });
  const { data: portfolio } = useQuery({
    queryKey: ['cpor', 'intelligence', 'portfolio'],
    queryFn: ({ signal }) => apiGet<PortfolioIntel>('/api/v1/cpor/intelligence/portfolio', { signal }),
    staleTime: 60_000,
  });
  const { data: briefMeta } = useQuery({
    queryKey: ['brief', 'signals-meta'],
    queryFn: ({ signal }) => apiGet<BriefMeta>('/api/v1/brief/signals', { signal }),
    staleTime: 60_000,
  });

  const statusCounts = listPage?.status_counts ?? {};
  const planningN = countPlanning(statusCounts);
  const liveN = statusCounts.active ?? 0;
  const endedN = statusCounts.ended ?? 0;
  const period = briefMeta?.tenant_period || briefMeta?.tenant_stamp || '';
  const bookAmt = settlement?.book_total;
  const delivery = portfolio?.totals?.delivery_rate ?? null;
  const meta = [
    period || null,
    `${planningN} plans in planning (draft / proposed / approved)`,
    `${liveN} live`,
    `${endedN} ended`,
    bookAmt != null ? `book ${fmtCompact(bookAmt, settlement?.currency_code)}` : null,
    delivery != null ? `delivery rate ${fmtPct(delivery)} (mixed evidence)` : null,
  ]
    .filter(Boolean)
    .join(' · ');

  const tabCounts: Partial<Record<FundingLens, number>> = {
    planner: planningN,
    book: settlement?.open_case_count ?? listPage?.total,
    ...counts,
  };

  return (
    <WorkbenchCanvas>
      <DomainHeader
        crumbs={
          title
            ? [{ label: FUNDING_TITLE, href: '/promotions' }, { label: title }]
            : [{ label: FUNDING_TITLE }]
        }
        title={FUNDING_TITLE}
        description={FUNDING_DESCRIPTION}
        meta={meta}
        actions={
          <>
            <Button variant="outlined" size="small" component={NextLink} href="/reports">
              Open in Reports
            </Button>
            <Button variant="outlined" size="small" component={NextLink} href="/admin/imports">
              Import claims / payments
            </Button>
            <Button
              variant="contained"
              size="small"
              component={NextLink}
              href="/promotions?new=1"
              data-testid="funding-new-plan"
            >
              New promotion plan
            </Button>
          </>
        }
      />
      <LensTabs
        value={lens}
        onChange={(next) => {
          const href = LENSES.find((l) => l.value === next)?.href;
          if (href) router.push(href);
        }}
        ariaLabel="Promotions & Funding lenses"
        lenses={LENSES.map((l) => ({ value: l.value, label: l.label, count: tabCounts[l.value] }))}
      />
      {children}
    </WorkbenchCanvas>
  );
}

export function FundingNewPlanButton({ onClick }: { onClick: () => void }) {
  return (
    <Button variant="contained" size="small" onClick={onClick} data-testid="funding-new-plan">
      New promotion plan
    </Button>
  );
}
