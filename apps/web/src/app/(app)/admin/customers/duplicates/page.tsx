'use client';

import { Suspense, useCallback, useEffect } from 'react';
import { Alert, Tab, Tabs, Typography } from '@mui/material';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';

import { DataChrome } from '@/features/data-stewardship/DataChrome';

import { AliasScopeConflictsSection } from './AliasScopeConflictsSection';
import { NameSimilarityMergeSection } from './NameSimilarityMergeSection';

const DEFAULT_PAGE_SIZE = 25;

function AdminCustomerDuplicatesPageContent() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const tabParam = searchParams.get('tab');
  const activeTab = tabParam === 'alias_scope' ? 'alias_scope' : 'name_similarity';

  const setTab = useCallback(
    (tab: 'name_similarity' | 'alias_scope') => {
      const sp = new URLSearchParams(searchParams.toString());
      sp.set('tab', tab);
      if (!sp.get('page')) sp.set('page', '1');
      if (!sp.get('page_size')) sp.set('page_size', String(DEFAULT_PAGE_SIZE));
      router.replace(`${pathname}?${sp.toString()}`);
    },
    [pathname, router, searchParams]
  );

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
    const token = sp.get('token');
    const returnJob = sp.get('return_job') ?? sp.get('job');
    if ((token || returnJob) && sp.get('tab') !== 'alias_scope') {
      sp.set('tab', 'alias_scope');
      changed = true;
    }
    if (!sp.get('tab')) {
      sp.set('tab', 'name_similarity');
      changed = true;
    }
    if (changed) router.replace(`${pathname}?${sp.toString()}`);
  }, [pathname, router, searchParams]);

  return (
    <>
      <Tabs value={activeTab} onChange={(_e, v) => setTab(v)} sx={{ mb: 2 }} aria-label="Customer duplicate views">
        <Tab value="alias_scope" label="Alias-scope conflicts (merge)" />
        <Tab value="name_similarity" label="Name similarity (full merge)" />
      </Tabs>
      {activeTab === 'alias_scope' ? (
        <AliasScopeConflictsSection />
      ) : (
        <>
          <Alert severity="warning" sx={{ mb: 2 }}>
            <strong>Name-similarity merge</strong> consolidates whole <code>dim_customer</code> records (all FK
            surfaces). For DSI import alias-token conflicts only, use the alias-scope tab.
          </Alert>
          <NameSimilarityMergeSection
            page={page}
            pageSize={pageSize}
            onPageChange={(p) => setParamState({ page: String(p) })}
            onPageSizeChange={(size) => setParamState({ page_size: String(size) }, true)}
          />
        </>
      )}
    </>
  );
}

export default function AdminCustomerDuplicatesPage() {
  return (
    <DataChrome>
      <Suspense fallback={<Typography color="text.secondary">Loading duplicate groups…</Typography>}>
        <AdminCustomerDuplicatesPageContent />
      </Suspense>
    </DataChrome>
  );
}
