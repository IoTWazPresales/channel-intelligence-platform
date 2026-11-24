'use client';

import { Alert, Stack, Typography } from '@mui/material';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';

import { AdminChrome } from '@/features/administration/AdminChrome';
import { ListingCaptureHealth } from '@/features/market-listings/ListingCaptureHealth';
import { LensTabs } from '@/features/workbench-ui/controls';

type DataHealthTab = 'sources' | 'imports' | 'masters';

const TABS: { value: DataHealthTab; label: string }[] = [
  { value: 'sources', label: 'Sources' },
  { value: 'imports', label: 'Imports' },
  { value: 'masters', label: 'Master counts' },
];

function tabFromSearch(search: URLSearchParams): DataHealthTab {
  const t = (search.get('tab') || 'sources').toLowerCase();
  if (t === 'imports' || t === 'masters') return t;
  return 'sources';
}

export default function DataHealthPage() {
  const search = useSearchParams();
  const router = useRouter();
  const pathname = usePathname() || '/admin/data-health';
  const tab = tabFromSearch(search);

  return (
    <AdminChrome>
      <Stack spacing={2} sx={{ mt: 1 }} data-testid="admin-data-health">
        <Typography variant="body2" color="text.secondary">
          Operational health for listings capture and related pipelines. More tabs are planned.
        </Typography>
        <LensTabs
          value={tab}
          onChange={(next) => {
            const params = new URLSearchParams(search.toString());
            params.set('tab', next);
            router.push(`${pathname}?${params.toString()}`);
          }}
          ariaLabel="Data health tabs"
          lenses={TABS.map((t) => ({ value: t.value, label: t.label }))}
        />
        {tab === 'sources' ? <ListingCaptureHealth /> : null}
        {tab === 'imports' ? (
          <Alert severity="info" variant="outlined" data-testid="data-health-imports-placeholder">
            Import evidence health dashboard — coming later (BACKLOG-031 remains parked).
          </Alert>
        ) : null}
        {tab === 'masters' ? (
          <Alert severity="info" variant="outlined" data-testid="data-health-masters-placeholder">
            Master data table counts — coming later.
          </Alert>
        ) : null}
      </Stack>
    </AdminChrome>
  );
}