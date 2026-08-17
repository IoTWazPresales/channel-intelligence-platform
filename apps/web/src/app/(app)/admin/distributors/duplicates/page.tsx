'use client';

import { Suspense, useCallback, useEffect } from 'react';
import { Alert, Typography } from '@mui/material';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';

import { PageHeader } from '@/components/PageHeader';
import { navPageChrome } from '@/features/shell/navPageChrome';

import { DistributorNameSimilarityMergeSection } from './DistributorNameSimilarityMergeSection';

const DEFAULT_PAGE_SIZE = 25;

function AdminDistributorDuplicatesPageContent() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const page = Number(searchParams.get('page') || '1') || 1;
  const pageSize = Number(searchParams.get('page_size') || `${DEFAULT_PAGE_SIZE}`) || DEFAULT_PAGE_SIZE;

  const setParamState = useCallback(
    (changes: Record<string, string | null>, resetPage = false) => {
      const sp = new URLSearchParams(searchParams.toString());
      for (const [k, v] of Object.entries(changes)) {
        if (v == null || v === '') sp.delete(k);
        else sp.set(k, v);
      }
      if (resetPage) sp.set('page', '1');
      router.replace(`${pathname}?${sp.toString()}`);
    },
    [pathname, router, searchParams]
  );

  useEffect(() => {
    const sp = new URLSearchParams(searchParams.toString());
    let changed = false;
    if (!sp.get('page')) {
      sp.set('page', '1');
      changed = true;
    }
    if (!sp.get('page_size')) {
      sp.set('page_size', String(DEFAULT_PAGE_SIZE));
      changed = true;
    }
    if (changed) router.replace(`${pathname}?${sp.toString()}`);
  }, [pathname, router, searchParams]);

  return (
    <>
      <PageHeader {...navPageChrome('/admin/distributors/duplicates')} />
      <Alert severity="warning" sx={{ mb: 2 }}>
        <strong>Name-similarity merge</strong> consolidates whole <code>dim_distributor</code> records with runtime FK
        discovery and PO row consolidation when <code>po_number_norm</code> collides. Preview always lists PO merge plans
        before confirm.
      </Alert>
      <DistributorNameSimilarityMergeSection
        page={page}
        pageSize={pageSize}
        onPageChange={(p) => setParamState({ page: String(p) })}
        onPageSizeChange={(size) => setParamState({ page_size: String(size) }, true)}
      />
    </>
  );
}

export default function AdminDistributorDuplicatesPage() {
  return (
    <Suspense fallback={<Typography color="text.secondary">Loading duplicate groups…</Typography>}>
      <AdminDistributorDuplicatesPageContent />
    </Suspense>
  );
}
