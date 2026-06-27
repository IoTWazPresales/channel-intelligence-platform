'use client';

import {
  Alert,
  Box,
  Button,
  Chip,
  FormControl,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  Tab,
  Tabs,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useCallback, useEffect } from 'react';

import { ModuleDataSection } from '@/components/ModuleDataSection';
import { ModuleGridToolbar } from '@/components/ModuleGridToolbar';
import { PageHeader } from '@/components/PageHeader';
import { apiGet } from '@/lib/api';
import { toQueryError } from '@/lib/queryError';

import { AliasScopeConflictsSection } from './AliasScopeConflictsSection';

type ReferenceCount = {
  label: string;
  count: number;
};

type DuplicateMember = {
  id: number;
  customer_code: string;
  customer_name: string;
  customer_status: string;
  created_at: string | null;
  survivor_hint: boolean;
  reference_counts: ReferenceCount[];
};

type DuplicateGroup = {
  similarity_key: string;
  member_count: number;
  members: DuplicateMember[];
};

type DuplicateGroupsResponse = {
  items: DuplicateGroup[];
  page: number;
  page_size: number;
  total: number;
  customers_scanned: number;
};

const DEFAULT_PAGE_SIZE = 25;

function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—';
  try {
    return new Date(value).toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' });
  } catch {
    return value;
  }
}

function totalReferenceRows(counts: ReferenceCount[]): number {
  return counts.reduce((sum, row) => sum + (row.count ?? 0), 0);
}

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

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['admin-customer-duplicate-groups', page, pageSize],
    queryFn: ({ signal }) => {
      const sp = new URLSearchParams();
      sp.set('page', String(page));
      sp.set('page_size', String(pageSize));
      return apiGet<DuplicateGroupsResponse>(`/api/v1/customers/duplicate-groups?${sp.toString()}`, { signal });
    },
  });

  const groups = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <>
      <PageHeader
        crumbs={[{ label: 'Admin' }, { label: 'Customers', href: '/admin/customers' }, { label: 'Duplicates' }]}
        title="Customer duplicates & alias conflicts"
      />
      <Tabs value={activeTab} onChange={(_e, v) => setTab(v)} sx={{ mb: 2 }} aria-label="Customer duplicate views">
        <Tab value="alias_scope" label="Alias-scope conflicts (merge)" />
        <Tab value="name_similarity" label="Name similarity (read-only)" />
      </Tabs>
      {activeTab === 'alias_scope' ? (
        <AliasScopeConflictsSection />
      ) : (
        <>
      <Alert severity="warning" sx={{ mb: 2 }}>
        <strong>This tab is read-only.</strong> It groups customers with similar names — it does not fix DSI import
        alias-scope conflicts. For job #96 and steward &quot;Master-data conflict&quot; chips, use the{' '}
        <Button size="small" variant="outlined" onClick={() => setTab('alias_scope')} sx={{ ml: 0.5, verticalAlign: 'middle' }}>
          Alias-scope conflicts (merge)
        </Button>{' '}
        tab or sidebar link <strong>Master Data → Alias-scope conflicts</strong>.
      </Alert>
      <Stack direction="row" spacing={1} sx={{ mb: 2 }} flexWrap="wrap" useFlexGap>
        <Button component={Link} href="/admin/customers" variant="outlined">
          Back to customers
        </Button>
        <ModuleGridToolbar onRefresh={() => void refetch()} sx={{ mb: 0 }} />
      </Stack>
      <Paper sx={{ p: 2 }}>
        <ModuleDataSection
          intro={
            <>
              Scanned <strong>{data?.customers_scanned ?? '…'}</strong> customers;{' '}
              <strong>{total}</strong> duplicate group{total === 1 ? '' : 's'} with 2+ members.
            </>
          }
          isLoading={isLoading}
          isError={isError}
          error={toQueryError(error)}
          onRetry={() => void refetch()}
          isEmpty={!isLoading && groups.length === 0}
          empty={{
            title: 'No duplicate groups found',
            description:
              'No customers share the same similarity-normalised name key with at least one other member. As master data grows, groups will appear here automatically.',
            primary: { label: 'Customer master', href: '/admin/customers' },
          }}
        >
          <Stack spacing={3}>
            {groups.map((group) => (
              <Paper key={group.similarity_key} variant="outlined" sx={{ p: 2 }}>
                <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap sx={{ mb: 1.5 }}>
                  <Typography variant="subtitle1" component="h2">
                    Group: {group.similarity_key}
                  </Typography>
                  <Chip size="small" label={`${group.member_count} members`} />
                </Stack>
                <TableContainer>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>Hint</TableCell>
                        <TableCell>Code</TableCell>
                        <TableCell>Name</TableCell>
                        <TableCell>Status</TableCell>
                        <TableCell>Created</TableCell>
                        <TableCell align="right">FK rows</TableCell>
                        <TableCell>Reference breakdown</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {group.members.map((member) => (
                        <TableRow key={member.id} selected={member.survivor_hint}>
                          <TableCell>
                            {member.survivor_hint ? (
                              <Chip size="small" color="primary" label="Survivor hint" variant="outlined" />
                            ) : (
                              '—'
                            )}
                          </TableCell>
                          <TableCell>{member.customer_code}</TableCell>
                          <TableCell>{member.customer_name}</TableCell>
                          <TableCell>{member.customer_status}</TableCell>
                          <TableCell>{formatDateTime(member.created_at)}</TableCell>
                          <TableCell align="right">{totalReferenceRows(member.reference_counts)}</TableCell>
                          <TableCell>
                            {member.reference_counts.length === 0 ? (
                              <Typography variant="body2" color="text.secondary">
                                No FK references
                              </Typography>
                            ) : (
                              <Box component="ul" sx={{ m: 0, pl: 2 }}>
                                {member.reference_counts.map((ref) => (
                                  <Typography key={`${ref.label}-${ref.count}`} component="li" variant="body2">
                                    {ref.label}: {ref.count}
                                  </Typography>
                                ))}
                              </Box>
                            )}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              </Paper>
            ))}
          </Stack>
          <Stack direction="row" spacing={1} sx={{ mt: 3 }} alignItems="center">
            <Button disabled={page <= 1} onClick={() => setParamState({ page: String(page - 1) })}>
              Prev
            </Button>
            <Typography variant="body2">
              Page {page} / {totalPages} ({total} groups)
            </Typography>
            <Button disabled={page >= totalPages} onClick={() => setParamState({ page: String(page + 1) })}>
              Next
            </Button>
            <FormControl size="small" sx={{ minWidth: 120 }}>
              <InputLabel>Page size</InputLabel>
              <Select
                label="Page size"
                value={String(pageSize)}
                onChange={(e) => setParamState({ page_size: String(e.target.value || DEFAULT_PAGE_SIZE) }, true)}
              >
                <MenuItem value="10">10</MenuItem>
                <MenuItem value="25">25</MenuItem>
                <MenuItem value="50">50</MenuItem>
                <MenuItem value="100">100</MenuItem>
              </Select>
            </FormControl>
          </Stack>
        </ModuleDataSection>
      </Paper>
        </>
      )}
    </>
  );
}

export default function AdminCustomerDuplicatesPage() {
  return (
    <Suspense fallback={<Typography color="text.secondary">Loading duplicate groups…</Typography>}>
      <AdminCustomerDuplicatesPageContent />
    </Suspense>
  );
}
