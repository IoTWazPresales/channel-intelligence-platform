'use client';

import {
  Alert,
  Box,
  Button,
  Checkbox,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  FormControlLabel,
  List,
  ListItemButton,
  MenuItem,
  Paper,
  Stack,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useMemo, useState } from 'react';

import { apiGet, apiPost } from '@/lib/api';

export type ShipmentMappingCandidateRow = {
  id: number;
  import_job_id: number;
  entity_type: string;
  normalized_key: string;
  row_count: number;
  total_units: number | null;
  total_reported_value: number | null;
  sample_raw_values: string[] | null;
  suggested_entity_id: number | null;
  suggested_distributor_code: string | null;
  suggested_distributor_name: string | null;
  suggested_customer_code: string | null;
  suggested_customer_name: string | null;
  suggested_action: string | null;
  match_reason: string | null;
  confidence_score: number | null;
  status: string;
  context: Record<string, unknown> | null;
};

type DistributorHit = { id: number; distributor_code: string; distributor_name: string };
type CustomerHit = {
  id: number;
  customer_code: string;
  customer_name: string;
  customer_status?: string;
  created_at?: string | null;
};

const TERMINAL = new Set(['resolved', 'ignored', 'waived_open_channel']);

const ENTITY_DIST = 'shipment_distributor';
const ENTITY_CUST = 'shipment_customer_token';

function partyLabel(party: string): string {
  return party === 'bill_to' ? 'Bill To' : party === 'ship_to' ? 'Ship To' : party;
}

function sampleToken(r: ShipmentMappingCandidateRow): string {
  const s = r.sample_raw_values;
  if (Array.isArray(s) && s.length > 0 && typeof s[0] === 'string' && s[0].trim()) {
    return s[0].trim();
  }
  return (r.normalized_key || '').trim() || '—';
}

function contextParty(ctx: Record<string, unknown> | null): string {
  if (!ctx || typeof ctx.party !== 'string') return '—';
  return partyLabel(ctx.party);
}

function suggestedNameFromContext(ctx: Record<string, unknown> | null, fallback: string): string {
  if (!ctx || typeof ctx.suggested_name !== 'string') return fallback;
  const t = ctx.suggested_name.trim();
  return t || fallback;
}

function contextNeedsNameReview(ctx: Record<string, unknown> | null): boolean {
  return Boolean(ctx && ctx.needs_name_review === true);
}

function contextSpecialCategory(ctx: Record<string, unknown> | null): string | null {
  if (!ctx || typeof ctx.special_category !== 'string') return null;
  const t = ctx.special_category.trim();
  return t || null;
}

function customerSpecialCategoryBlocksProvisional(ctx: Record<string, unknown> | null): boolean {
  const c = contextSpecialCategory(ctx);
  return c === 'noise_only' || c === 'internal_note';
}

function contextPossibleDuplicateOf(ctx: Record<string, unknown> | null): string[] {
  if (!ctx || !Array.isArray(ctx.possible_duplicate_of)) return [];
  return ctx.possible_duplicate_of
    .filter((x): x is string => typeof x === 'string' && x.trim())
    .slice(0, 8);
}

function entityChipLabel(entityType: string): string {
  if (entityType === ENTITY_DIST) return 'Distributor';
  if (entityType === ENTITY_CUST) return 'Channel partner';
  return entityType;
}

function humanizeSnakeTitle(s: string | null): string {
  if (!s) return '—';
  return s.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function humanizeMatchReasonCaption(reason: string | null): string {
  if (!reason) return '';
  const t = reason.trim();
  if (t === 'no_alias_or_exact_dim_match') return '';
  return humanizeSnakeTitle(t);
}

function CustomerMatchById({ id }: { id: number }) {
  const { data, isPending } = useQuery({
    queryKey: ['customers-list-by-id-shipment-steward', id],
    queryFn: ({ signal }) =>
      apiGet<{ items: CustomerHit[] }>(`/api/v1/customers?customer_id=${id}&page_size=1`, { signal }),
    enabled: Number.isFinite(id) && id > 0,
  });
  const hit = data?.items?.[0];
  if (isPending) {
    return (
      <Typography variant="caption" color="text.secondary">
        Loading…
      </Typography>
    );
  }
  if (!hit) {
    return (
      <Stack spacing={0.25}>
        <Typography variant="body2">Matched customer</Typography>
        <Typography variant="caption" color="text.secondary">
          ID {id}
        </Typography>
      </Stack>
    );
  }
  return (
    <Stack spacing={0.25}>
      <Typography variant="body2">{hit.customer_name || '—'}</Typography>
      <Typography variant="caption" color="text.secondary">
        {(hit.customer_code || '').trim() || '—'}
      </Typography>
    </Stack>
  );
}

function ShipmentCandidateMatchCell({ row }: { row: ShipmentMappingCandidateRow }) {
  const mr = (row.match_reason || '').trim();
  const act = (row.suggested_action || '').trim();
  const sid = row.suggested_entity_id;
  const needsReview =
    act === 'needs_review' || ((!act || act === '') && (row.status || '').trim() === 'needs_review');

  if (row.entity_type === ENTITY_DIST) {
    if (!row.match_reason) {
      return (
        <Typography variant="caption" color="text.secondary">
          —
        </Typography>
      );
    }
    return (
      <Typography variant="caption" color="text.secondary">
        {humanizeSnakeTitle(mr)}
      </Typography>
    );
  }

  if (act === 'map_customer' && sid != null && Number(sid) > 0) {
    const hasName =
      Boolean((row.suggested_customer_name || '').trim()) ||
      Boolean((row.suggested_customer_code || '').trim());
    if (hasName) {
      return (
        <Stack spacing={0.25}>
          <Typography variant="body2">{(row.suggested_customer_name || '').trim() || '—'}</Typography>
          <Typography variant="caption" color="text.secondary">
            {(row.suggested_customer_code || '').trim() || '—'}
          </Typography>
        </Stack>
      );
    }
    return <CustomerMatchById id={Number(sid)} />;
  }

  if (needsReview) {
    const cap = humanizeMatchReasonCaption(row.match_reason);
    return (
      <Stack spacing={0.25}>
        <Typography variant="body2">Needs review</Typography>
        {cap ? (
          <Typography variant="caption" color="text.secondary">
            {cap}
          </Typography>
        ) : null}
      </Stack>
    );
  }

  if (mr === 'no_alias_or_exact_dim_match') {
    return (
      <Typography variant="body2" color="text.secondary">
        No match found
      </Typography>
    );
  }

  return (
    <Typography variant="caption" color="text.secondary">
      {humanizeSnakeTitle(row.match_reason)}
    </Typography>
  );
}

function formatCustomerCreatedAt(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}

export function ShipmentEntityStewardPanel({ importJobId }: { importJobId: number | null }) {
  const qc = useQueryClient();
  const [mapOpen, setMapOpen] = useState(false);
  const [provOpen, setProvOpen] = useState(false);
  const [bulkProvOpen, setBulkProvOpen] = useState(false);
  const [active, setActive] = useState<ShipmentMappingCandidateRow | null>(null);
  const [distQ, setDistQ] = useState('');
  const [custQ, setCustQ] = useState('');
  const [pickDistId, setPickDistId] = useState<number | ''>('');
  const [pickCustId, setPickCustId] = useState<number | ''>('');
  const [provName, setProvName] = useState('');
  const [provCode, setProvCode] = useState('');
  const [provConfirmSuspicious, setProvConfirmSuspicious] = useState(false);
  const [custRegionId, setCustRegionId] = useState('');
  const [custChannelId, setCustChannelId] = useState('');
  const [custPrefDistId, setCustPrefDistId] = useState('');
  const [custPartnerTier, setCustPartnerTier] = useState('unmanaged');
  const [custNotes, setCustNotes] = useState('');
  const [selectedCandidateIds, setSelectedCandidateIds] = useState<Set<number>>(new Set());
  /** Display names for unified bulk provisional dialog, keyed by candidate id */
  const [bulkProvNamesById, setBulkProvNamesById] = useState<Record<number, string>>({});
  const [bulkMapOpen, setBulkMapOpen] = useState(false);
  const [bulkMapSearch, setBulkMapSearch] = useState('');
  const [bulkMapPickId, setBulkMapPickId] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const candidatesUrl =
    importJobId != null
      ? `/api/v1/shipment-evidence/import-jobs/${importJobId}/mapping-candidates`
      : '';

  const { data: rawRows, refetch, isLoading } = useQuery({
    queryKey: ['shipment-evidence-mapping-candidates', importJobId],
    queryFn: ({ signal }) => apiGet<ShipmentMappingCandidateRow[]>(candidatesUrl, { signal }),
    enabled: importJobId != null,
  });

  const rows = useMemo(
    () => (rawRows ?? []).filter((r) => !TERMINAL.has((r.status || '').trim())),
    [rawRows]
  );

  const customerRows = useMemo(() => rows.filter((r) => r.entity_type === ENTITY_CUST), [rows]);
  const distributorRows = useMemo(() => rows.filter((r) => r.entity_type === ENTITY_DIST), [rows]);

  const selectedCustomerIdsList = useMemo(
    () => [...selectedCandidateIds].filter((id) => customerRows.some((r) => r.id === id)),
    [selectedCandidateIds, customerRows]
  );

  const visibleRowIds = useMemo(() => rows.map((r) => r.id), [rows]);
  const allVisibleSelected =
    visibleRowIds.length > 0 && visibleRowIds.every((id) => selectedCandidateIds.has(id));
  const someVisibleSelected = visibleRowIds.some((id) => selectedCandidateIds.has(id));

  const selectedIncludeSpecialCategory = useMemo(
    () =>
      rows.some(
        (r) =>
          r.entity_type === ENTITY_CUST &&
          selectedCandidateIds.has(r.id) &&
          customerSpecialCategoryBlocksProvisional(r.context)
      ),
    [rows, selectedCandidateIds]
  );

  const { data: distHits = [] } = useQuery({
    queryKey: ['distributors-search-shipment-steward', distQ],
    queryFn: ({ signal }) =>
      apiGet<{ items: DistributorHit[] }>(
        `/api/v1/distributors?q=${encodeURIComponent(distQ)}&page_size=20`,
        { signal }
      ),
    enabled: distQ.trim().length >= 1,
    select: (r) => r.items ?? [],
  });

  const { data: custHits = [] } = useQuery({
    queryKey: ['customers-search-shipment-steward', custQ],
    queryFn: ({ signal }) =>
      apiGet<{ items: CustomerHit[] }>(`/api/v1/customers?q=${encodeURIComponent(custQ)}&page_size=20`, {
        signal,
      }),
    enabled: custQ.trim().length >= 1,
    select: (r) => r.items ?? [],
  });

  const { data: bulkMapRecent = [] } = useQuery({
    queryKey: ['customers-recent-provisionals-bulk-map', importJobId],
    queryFn: ({ signal }) =>
      apiGet<{ items: CustomerHit[] }>(
        `/api/v1/customers?q=&job_id=${importJobId}&status=unverified&sort_by=created_at&sort_dir=desc&page_size=10`,
        { signal }
      ),
    enabled: bulkMapOpen && importJobId != null,
    select: (r) => r.items ?? [],
  });

  const { data: bulkMapSearchHits = [] } = useQuery({
    queryKey: ['customers-bulk-map-search', bulkMapSearch],
    queryFn: ({ signal }) =>
      apiGet<{ items: CustomerHit[] }>(
        `/api/v1/customers?q=${encodeURIComponent(bulkMapSearch.trim())}&page_size=20`,
        { signal }
      ),
    enabled: bulkMapOpen && bulkMapSearch.trim().length >= 1,
    select: (r) => r.items ?? [],
  });

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ['shipment-evidence'] });
    if (importJobId != null) {
      void qc.invalidateQueries({ queryKey: ['shipment-evidence-mapping-candidates', importJobId] });
      void qc.invalidateQueries({ queryKey: ['customers-recent-provisionals-bulk-map', importJobId] });
    }
    void qc.invalidateQueries({ queryKey: ['customers-bulk-map-search'] });
    void qc.invalidateQueries({ queryKey: ['customers-list-by-id-shipment-steward'] });
  };

  const parseOptInt = (s: string): number | null => {
    const t = s.trim();
    if (!t) return null;
    const n = Number(t);
    return Number.isFinite(n) && n >= 1 ? n : null;
  };

  const mapMut = useMutation({
    mutationFn: (body: {
      candidate_id: number;
      mode: 'distributor' | 'customer';
      distributor_id?: number;
      customer_id?: number;
      raw_token: string | null;
    }) => {
      if (body.mode === 'distributor') {
        return apiPost<Record<string, unknown>>(
          `/api/v1/shipment-evidence/import-candidates/${body.candidate_id}/map-distributor`,
          { distributor_id: body.distributor_id, raw_token: body.raw_token }
        );
      }
      return apiPost<Record<string, unknown>>(
        `/api/v1/shipment-evidence/import-candidates/${body.candidate_id}/map-customer`,
        { customer_id: body.customer_id, raw_token: body.raw_token }
      );
    },
    onSuccess: () => {
      setActionError(null);
      setMapOpen(false);
      setActive(null);
      invalidate();
      void refetch();
    },
    onError: (e: Error) => setActionError(e.message),
  });

  const provDistMut = useMutation({
    mutationFn: (body: {
      candidate_id: number;
      display_name: string | null;
      distributor_code: string | null;
      confirm_for_suspicious_token: boolean;
    }) =>
      apiPost<Record<string, unknown>>(
        `/api/v1/shipment-evidence/import-candidates/${body.candidate_id}/create-provisional-distributor`,
        {
          display_name: body.display_name,
          distributor_code: body.distributor_code,
          confirm_for_suspicious_token: body.confirm_for_suspicious_token,
        }
      ),
    onSuccess: () => {
      setActionError(null);
      setProvOpen(false);
      setActive(null);
      invalidate();
      void refetch();
    },
    onError: (e: Error) => setActionError(e.message),
  });

  const provCustMut = useMutation({
    mutationFn: (body: {
      candidate_id: number;
      display_name: string | null;
      region_id: number | null;
      channel_id: number | null;
      preferred_distributor_id: number | null;
      partner_tier: string;
      notes_summary: string | null;
    }) =>
      apiPost<Record<string, unknown>>(
        `/api/v1/shipment-evidence/import-candidates/${body.candidate_id}/create-provisional-customer`,
        {
          display_name: body.display_name,
          region_id: body.region_id,
          channel_id: body.channel_id,
          preferred_distributor_id: body.preferred_distributor_id,
          partner_tier: body.partner_tier,
          notes_summary: body.notes_summary,
        }
      ),
    onSuccess: () => {
      setActionError(null);
      setProvOpen(false);
      setActive(null);
      invalidate();
      void refetch();
    },
    onError: (e: Error) => setActionError(e.message),
  });

  type BulkProvFailure = { id: number; kind: 'distributor' | 'customer'; message: string };

  const unifiedBulkProvMut = useMutation({
    mutationFn: async (): Promise<{ successes: number[]; failures: BulkProvFailure[] }> => {
      const failures: BulkProvFailure[] = [];
      const successes: number[] = [];
      const tasks: Promise<void>[] = [];

      for (const id of selectedCandidateIds) {
        const row = rows.find((r) => r.id === id);
        if (!row) continue;
        const displayName = (bulkProvNamesById[id] ?? '').trim();
        if (!displayName) continue;

        if (row.entity_type === ENTITY_DIST) {
          tasks.push(
            (async () => {
              try {
                await apiPost<Record<string, unknown>>(
                  `/api/v1/shipment-evidence/import-candidates/${id}/create-provisional-distributor`,
                  {
                    display_name: displayName,
                    distributor_code: null,
                    confirm_for_suspicious_token: false,
                  }
                );
                successes.push(id);
              } catch (e) {
                failures.push({
                  id,
                  kind: 'distributor',
                  message: e instanceof Error ? e.message : String(e),
                });
              }
            })()
          );
        } else if (row.entity_type === ENTITY_CUST) {
          tasks.push(
            (async () => {
              try {
                await apiPost<Record<string, unknown>>(
                  `/api/v1/shipment-evidence/import-candidates/${id}/create-provisional-customer`,
                  {
                    display_name: displayName,
                    region_id: parseOptInt(custRegionId),
                    channel_id: parseOptInt(custChannelId),
                    preferred_distributor_id: parseOptInt(custPrefDistId),
                    partner_tier: custPartnerTier,
                    notes_summary: custNotes.trim() || null,
                  }
                );
                successes.push(id);
              } catch (e) {
                failures.push({
                  id,
                  kind: 'customer',
                  message: e instanceof Error ? e.message : String(e),
                });
              }
            })()
          );
        }
      }

      await Promise.all(tasks);
      return { successes, failures };
    },
    onSuccess: (data) => {
      const nOk = data.successes.length;
      const fails = data.failures;
      const failSummary = fails
        .slice(0, 8)
        .map((f) => `${f.kind} #${f.id}: ${f.message}`)
        .join('; ');
      const suffix = fails.length > 8 ? '…' : '';
      if (fails.length && nOk > 0) {
        setActionError(`Partial success: ${nOk} created. Failed: ${failSummary}${suffix}`);
      } else if (fails.length) {
        setActionError(`Bulk provisional failed: ${failSummary}${suffix}`);
        return;
      } else {
        setActionError(null);
      }
      setBulkProvOpen(false);
      setBulkProvNamesById({});
      setSelectedCandidateIds(new Set());
      invalidate();
      void refetch();
    },
    onError: (e: Error) => setActionError(e.message),
  });

  const bulkMapMut = useMutation({
    mutationFn: (body: { candidate_ids: number[]; customer_id: number }) =>
      apiPost<{ mapped: number[]; errors: { candidate_id: number; reason: string }[] }>(
        '/api/v1/shipment-evidence/import-candidates/bulk-map-customer',
        body
      ),
    onSuccess: (data) => {
      const nMap = data.mapped?.length ?? 0;
      const errs = data.errors ?? [];
      const errSummary = errs
        .slice(0, 6)
        .map((e) => `#${e.candidate_id}: ${e.reason}`)
        .join('; ');
      const suffix = errs.length > 6 ? '…' : '';
      if (errs.length && nMap > 0) {
        setActionError(`Partial success: mapped ${nMap}. Failed: ${errSummary}${suffix}`);
      } else if (errs.length) {
        setActionError(`Bulk map failed: ${errSummary}${suffix}`);
      } else {
        setActionError(null);
      }
      setBulkMapOpen(false);
      setBulkMapSearch('');
      setBulkMapPickId(null);
      setSelectedCandidateIds(new Set());
      invalidate();
      void refetch();
    },
    onError: (e: Error) => setActionError(e.message),
  });

  const toggleSelectCandidate = (id: number) => {
    setSelectedCandidateIds((prev) => {
      const n = new Set(prev);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  };

  const toggleSelectAllVisible = () => {
    setSelectedCandidateIds((prev) => {
      const next = new Set(prev);
      const allOn = visibleRowIds.length > 0 && visibleRowIds.every((id) => next.has(id));
      if (allOn) {
        for (const id of visibleRowIds) next.delete(id);
      } else {
        for (const id of visibleRowIds) next.add(id);
      }
      return next;
    });
  };

  const openMap = (r: ShipmentMappingCandidateRow) => {
    setActive(r);
    setPickDistId('');
    setPickCustId('');
    setDistQ('');
    setCustQ('');
    setActionError(null);
    setMapOpen(true);
  };

  const openProv = (r: ShipmentMappingCandidateRow) => {
    setActive(r);
    const tok = sampleToken(r);
    const sug = suggestedNameFromContext(r.context, tok);
    setProvName(sug.slice(0, 200));
    setProvCode('');
    setProvConfirmSuspicious(false);
    setCustRegionId('');
    setCustChannelId('');
    setCustPrefDistId('');
    setCustPartnerTier('unmanaged');
    setCustNotes('');
    setActionError(null);
    setProvOpen(true);
  };

  const actionChipColor = (a: string | null) => {
    switch (a) {
      case 'map_distributor':
      case 'map_customer':
        return 'success' as const;
      case 'create_provisional_distributor':
      case 'create_provisional_customer':
        return 'warning' as const;
      case 'needs_review':
        return 'error' as const;
      default:
        return 'default' as const;
    }
  };

  return (
    <Paper sx={{ p: 2 }} data-testid="shipment-entity-steward-panel">
      <Stack spacing={2}>
        <Typography variant="h6">Shipment mapping candidates (import job)</Typography>
        <Typography variant="body2" color="text.secondary">
          Distributor rows: unresolved Bill To / Ship To tokens. Channel partner rows: unresolved customer remarks
          tokens. Suggested actions are hints only; map and provisional apply create approved aliases and update
          evidence lines.
        </Typography>
        {importJobId == null ? (
          <Alert severity="info">
            Set <strong>Import job ID</strong> in the filters above to load candidates for that job.
          </Alert>
        ) : null}
        {actionError ? (
          <Alert
            severity={actionError.startsWith('Partial success') ? 'warning' : 'error'}
            onClose={() => setActionError(null)}
          >
            {actionError}
          </Alert>
        ) : null}
        {importJobId != null && rows.length > 0 ? (
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
            <Button
              size="small"
              variant="outlined"
              disabled={selectedCustomerIdsList.length === 0}
              onClick={() => {
                setBulkMapSearch('');
                setBulkMapPickId(null);
                setActionError(null);
                setBulkMapOpen(true);
              }}
            >
              Bulk map…
            </Button>
            <Button
              size="small"
              variant="outlined"
              disabled={
                selectedCandidateIds.size === 0 ||
                selectedIncludeSpecialCategory
              }
              onClick={() => {
                setCustRegionId('');
                setCustChannelId('');
                setCustPrefDistId('');
                setCustPartnerTier('unmanaged');
                setCustNotes('');
                setActionError(null);
                const init: Record<number, string> = {};
                for (const id of selectedCandidateIds) {
                  const row = rows.find((r) => r.id === id);
                  if (!row) continue;
                  init[id] = suggestedNameFromContext(row.context, sampleToken(row)).slice(0, 256);
                }
                setBulkProvNamesById(init);
                setBulkProvOpen(true);
              }}
            >
              Bulk provisional…
            </Button>
            <Typography variant="caption" color="text.secondary">
              {selectedCandidateIds.size} selected
              {selectedIncludeSpecialCategory
                ? ' · deselect special-category or internal-note channel partner rows to run bulk provisional'
                : ''}
            </Typography>
          </Stack>
        ) : null}
        {importJobId != null && isLoading ? (
          <Typography variant="body2">Loading…</Typography>
        ) : importJobId != null && rows.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            No open mapping candidates for this job.
          </Typography>
        ) : importJobId != null ? (
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell padding="checkbox">
                  <Checkbox
                    size="small"
                    indeterminate={someVisibleSelected && !allVisibleSelected}
                    checked={allVisibleSelected && rows.length > 0}
                    onChange={toggleSelectAllVisible}
                    inputProps={{ 'aria-label': 'Select all visible candidates' }}
                  />
                </TableCell>
                <TableCell>Type</TableCell>
                <TableCell>Party / scope</TableCell>
                <TableCell>Token (sample)</TableCell>
                <TableCell align="right">Rows</TableCell>
                <TableCell align="right">Qty / value</TableCell>
                <TableCell>Suggested</TableCell>
                <TableCell>Plan</TableCell>
                <TableCell>Match</TableCell>
                <TableCell align="right">Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((r) => (
                <TableRow
                  key={r.id}
                  sx={
                    r.entity_type === ENTITY_CUST && contextNeedsNameReview(r.context)
                      ? (theme) => ({
                          boxShadow: `inset 3px 0 0 ${theme.palette.warning.main}`,
                        })
                      : undefined
                  }
                >
                  <TableCell padding="checkbox">
                    <Checkbox
                      size="small"
                      checked={selectedCandidateIds.has(r.id)}
                      onChange={() => toggleSelectCandidate(r.id)}
                      inputProps={{ 'aria-label': `Select candidate ${r.id}` }}
                    />
                  </TableCell>
                  <TableCell>
                    <Chip size="small" label={entityChipLabel(r.entity_type)} variant="outlined" />
                  </TableCell>
                  <TableCell>
                    <Typography variant="body2">
                      {r.entity_type === ENTITY_DIST ? contextParty(r.context) : '—'}
                    </Typography>
                  </TableCell>
                  <TableCell sx={{ maxWidth: 260 }}>
                    <Typography variant="body2" noWrap title={sampleToken(r)}>
                      {sampleToken(r)}
                    </Typography>
                    <Typography variant="caption" color="text.secondary" display="block" noWrap title={r.normalized_key}>
                      key: {r.normalized_key}
                    </Typography>
                  </TableCell>
                  <TableCell align="right">{r.row_count}</TableCell>
                  <TableCell align="right">
                    <Typography variant="caption" display="block">
                      {r.total_units ?? '—'} / {r.total_reported_value ?? '—'}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Stack spacing={0.5} alignItems="flex-start">
                      <Typography variant="body2">
                        {suggestedNameFromContext(r.context, sampleToken(r))}
                      </Typography>
                      {r.entity_type === ENTITY_CUST && contextSpecialCategory(r.context) === 'noise_only' ? (
                        <Chip size="small" color="secondary" variant="outlined" label="Special category" />
                      ) : null}
                      {r.entity_type === ENTITY_CUST && contextSpecialCategory(r.context) === 'internal_note' ? (
                        <Chip size="small" color="info" variant="outlined" label="Internal note" />
                      ) : null}
                      {r.entity_type === ENTITY_CUST && contextPossibleDuplicateOf(r.context).length > 0 ? (
                        <Typography variant="caption" color="text.secondary">
                          Similar to: {contextPossibleDuplicateOf(r.context).join(', ')}
                        </Typography>
                      ) : null}
                      {r.entity_type === ENTITY_CUST && contextNeedsNameReview(r.context) ? (
                        <Chip size="small" color="warning" variant="outlined" label="Verify name" />
                      ) : null}
                      {r.entity_type === ENTITY_DIST &&
                      (r.suggested_distributor_code || r.suggested_distributor_name) ? (
                        <Typography variant="caption" color="text.secondary">
                          {(r.suggested_distributor_code || '').trim()}
                          {r.suggested_distributor_name ? ` — ${r.suggested_distributor_name}` : ''}
                        </Typography>
                      ) : null}
                      {r.entity_type === ENTITY_CUST && (r.suggested_customer_code || r.suggested_customer_name) ? (
                        <Typography variant="caption" color="text.secondary">
                          {(r.suggested_customer_code || '').trim()}
                          {r.suggested_customer_name ? ` — ${r.suggested_customer_name}` : ''}
                        </Typography>
                      ) : null}
                    </Stack>
                  </TableCell>
                  <TableCell>
                    <Stack spacing={0.5} alignItems="flex-start">
                      {r.suggested_action ? (
                        <Chip size="small" label={r.suggested_action} color={actionChipColor(r.suggested_action)} />
                      ) : null}
                      {r.confidence_score != null ? (
                        <Typography variant="caption" color="text.secondary">
                          score {r.confidence_score.toFixed(2)}
                        </Typography>
                      ) : null}
                    </Stack>
                  </TableCell>
                  <TableCell sx={{ maxWidth: 220 }}>
                    <ShipmentCandidateMatchCell row={r} />
                  </TableCell>
                  <TableCell align="right">
                    <Stack direction="row" spacing={0.5} justifyContent="flex-end" flexWrap="wrap">
                      <Button size="small" variant="outlined" onClick={() => openMap(r)}>
                        Map…
                      </Button>
                      {r.entity_type === ENTITY_CUST && customerSpecialCategoryBlocksProvisional(r.context) ? (
                        <Tooltip title="Special category or internal-note text is not treated as a channel partner name. Provisional customer creation is disabled.">
                          <span>
                            <Button size="small" variant="outlined" disabled>
                              Provisional…
                            </Button>
                          </span>
                        </Tooltip>
                      ) : (
                        <Button size="small" variant="outlined" onClick={() => openProv(r)}>
                          Provisional…
                        </Button>
                      )}
                    </Stack>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : null}
      </Stack>

      <Dialog open={mapOpen} onClose={() => setMapOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>
          {active?.entity_type === ENTITY_CUST ? 'Map token to customer' : 'Map token to distributor'}
        </DialogTitle>
        <DialogContent>
          {active ? (
            <Stack spacing={2} sx={{ mt: 1 }}>
              <Typography variant="body2">
                Candidate {active.id} · <Chip size="small" label={entityChipLabel(active.entity_type)} /> ·{' '}
                <strong>{sampleToken(active)}</strong>
              </Typography>
              {active.entity_type === ENTITY_DIST ? (
                <>
                  <TextField
                    label="Search distributors"
                    size="small"
                    value={distQ}
                    onChange={(e) => setDistQ(e.target.value)}
                    fullWidth
                  />
                  <TextField
                    select
                    label="Distributor"
                    size="small"
                    value={pickDistId}
                    onChange={(e) => setPickDistId(e.target.value === '' ? '' : Number(e.target.value))}
                    fullWidth
                  >
                    <MenuItem value="">
                      <em>Select…</em>
                    </MenuItem>
                    {distHits.map((d) => (
                      <MenuItem key={d.id} value={d.id}>
                        {d.distributor_code} — {d.distributor_name}
                      </MenuItem>
                    ))}
                  </TextField>
                </>
              ) : (
                <>
                  <TextField
                    label="Search customers"
                    size="small"
                    value={custQ}
                    onChange={(e) => setCustQ(e.target.value)}
                    fullWidth
                  />
                  <TextField
                    select
                    label="Customer"
                    size="small"
                    value={pickCustId}
                    onChange={(e) => setPickCustId(e.target.value === '' ? '' : Number(e.target.value))}
                    fullWidth
                  >
                    <MenuItem value="">
                      <em>Select…</em>
                    </MenuItem>
                    {custHits.map((c) => (
                      <MenuItem key={c.id} value={c.id}>
                        {c.customer_code} — {c.customer_name}
                      </MenuItem>
                    ))}
                  </TextField>
                </>
              )}
            </Stack>
          ) : null}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setMapOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            disabled={
              !active ||
              mapMut.isPending ||
              (active.entity_type === ENTITY_DIST && pickDistId === '') ||
              (active.entity_type === ENTITY_CUST && pickCustId === '')
            }
            onClick={() => {
              if (!active) return;
              const tok = sampleToken(active) !== '—' ? sampleToken(active) : null;
              if (active.entity_type === ENTITY_DIST && pickDistId !== '') {
                mapMut.mutate({
                  candidate_id: active.id,
                  mode: 'distributor',
                  distributor_id: Number(pickDistId),
                  raw_token: tok,
                });
              } else if (active.entity_type === ENTITY_CUST && pickCustId !== '') {
                mapMut.mutate({
                  candidate_id: active.id,
                  mode: 'customer',
                  customer_id: Number(pickCustId),
                  raw_token: tok,
                });
              }
            }}
          >
            Map
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={provOpen} onClose={() => setProvOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>
          {active?.entity_type === ENTITY_CUST ? 'Create provisional customer' : 'Create provisional distributor'}
        </DialogTitle>
        <DialogContent>
          {active ? (
            <Stack spacing={2} sx={{ mt: 1 }}>
              <Typography variant="body2">
                Candidate {active.id} · <Chip size="small" label={entityChipLabel(active.entity_type)} /> ·{' '}
                <strong>{sampleToken(active)}</strong>
              </Typography>
              <TextField
                label="Display name"
                size="small"
                value={provName}
                onChange={(e) => setProvName(e.target.value)}
                fullWidth
              />
              {active.entity_type === ENTITY_DIST ? (
                <>
                  <TextField
                    label="Distributor code (optional)"
                    size="small"
                    value={provCode}
                    onChange={(e) => setProvCode(e.target.value)}
                    helperText="Leave blank to auto-generate a TMP-DIST-… code."
                    fullWidth
                  />
                  <FormControlLabel
                    control={
                      <Switch
                        checked={provConfirmSuspicious}
                        onChange={(e) => setProvConfirmSuspicious(e.target.checked)}
                      />
                    }
                    label="Confirm if token looks like a placeholder (required for suspicious tokens)"
                  />
                </>
              ) : (
                <>
                  <TextField
                    label="Region id (optional)"
                    size="small"
                    value={custRegionId}
                    onChange={(e) => setCustRegionId(e.target.value)}
                    fullWidth
                  />
                  <TextField
                    label="Channel id (optional)"
                    size="small"
                    value={custChannelId}
                    onChange={(e) => setCustChannelId(e.target.value)}
                    fullWidth
                  />
                  <TextField
                    label="Preferred distributor id (optional)"
                    size="small"
                    value={custPrefDistId}
                    onChange={(e) => setCustPrefDistId(e.target.value)}
                    fullWidth
                  />
                  <TextField
                    select
                    label="Partner tier"
                    size="small"
                    value={custPartnerTier}
                    onChange={(e) => setCustPartnerTier(e.target.value)}
                    fullWidth
                  >
                    {['strategic', 'tier_1', 'tier_2', 'tier_3', 'core', 'long_tail', 'unmanaged'].map((t) => (
                      <MenuItem key={t} value={t}>
                        {t}
                      </MenuItem>
                    ))}
                  </TextField>
                  <TextField
                    label="Notes (optional)"
                    size="small"
                    value={custNotes}
                    onChange={(e) => setCustNotes(e.target.value)}
                    fullWidth
                    multiline
                    minRows={2}
                  />
                </>
              )}
            </Stack>
          ) : null}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setProvOpen(false)}>Cancel</Button>
          <Tooltip
            title={
              active?.entity_type === ENTITY_CUST && customerSpecialCategoryBlocksProvisional(active.context)
                ? 'Special category or internal-note rows cannot be turned into provisional customers.'
                : ''
            }
          >
            <span>
              <Button
                variant="contained"
                disabled={
                  !active ||
                  provDistMut.isPending ||
                  provCustMut.isPending ||
                  (active.entity_type === ENTITY_CUST && customerSpecialCategoryBlocksProvisional(active.context))
                }
                onClick={() => {
                  if (!active) return;
                  if (active.entity_type === ENTITY_DIST) {
                    provDistMut.mutate({
                      candidate_id: active.id,
                      display_name: provName.trim() || null,
                      distributor_code: provCode.trim() || null,
                      confirm_for_suspicious_token: provConfirmSuspicious,
                    });
                  } else {
                    provCustMut.mutate({
                      candidate_id: active.id,
                      display_name: provName.trim() || null,
                      region_id: parseOptInt(custRegionId),
                      channel_id: parseOptInt(custChannelId),
                      preferred_distributor_id: parseOptInt(custPrefDistId),
                      partner_tier: custPartnerTier,
                      notes_summary: custNotes.trim() || null,
                    });
                  }
                }}
              >
                Create
              </Button>
            </span>
          </Tooltip>
        </DialogActions>
      </Dialog>

      <Dialog open={bulkProvOpen} onClose={() => setBulkProvOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle>Bulk provisional</DialogTitle>
        <DialogContent>
          <Stack spacing={3} sx={{ mt: 1 }}>
            <Typography variant="body2" color="text.secondary">
              Edit display names for each selected candidate, then confirm. Distributor and channel partner requests run
              in parallel.
            </Typography>

            <Box>
              <Typography variant="subtitle2" gutterBottom>
                Distributors
              </Typography>
              {distributorRows.filter((r) => selectedCandidateIds.has(r.id)).length === 0 ? (
                <Typography variant="caption" color="text.secondary">
                  No distributor candidates in the current selection.
                </Typography>
              ) : (
                <Stack spacing={2}>
                  {distributorRows
                    .filter((r) => selectedCandidateIds.has(r.id))
                    .map((r) => (
                      <TextField
                        key={r.id}
                        label={`#${r.id} · ${contextParty(r.context)} · ${sampleToken(r)}`}
                        size="small"
                        value={bulkProvNamesById[r.id] ?? ''}
                        onChange={(e) =>
                          setBulkProvNamesById((p) => ({ ...p, [r.id]: e.target.value }))
                        }
                        fullWidth
                      />
                    ))}
                </Stack>
              )}
            </Box>

            <Divider />

            <Box>
              <Typography variant="subtitle2" gutterBottom>
                Channel partners
              </Typography>
              {customerRows.filter((r) => selectedCandidateIds.has(r.id)).length === 0 ? (
                <Typography variant="caption" color="text.secondary">
                  No channel partner candidates in the current selection.
                </Typography>
              ) : (
                <Stack spacing={2}>
                  {customerRows
                    .filter((r) => selectedCandidateIds.has(r.id))
                    .map((r) => (
                      <TextField
                        key={r.id}
                        label={`#${r.id} · ${sampleToken(r)}`}
                        size="small"
                        value={bulkProvNamesById[r.id] ?? ''}
                        onChange={(e) =>
                          setBulkProvNamesById((p) => ({ ...p, [r.id]: e.target.value }))
                        }
                        fullWidth
                      />
                    ))}
                  <TextField
                    label="Region id (optional, all partners)"
                    size="small"
                    value={custRegionId}
                    onChange={(e) => setCustRegionId(e.target.value)}
                    fullWidth
                  />
                  <TextField
                    label="Channel id (optional, all partners)"
                    size="small"
                    value={custChannelId}
                    onChange={(e) => setCustChannelId(e.target.value)}
                    fullWidth
                  />
                  <TextField
                    label="Preferred distributor id (optional, all partners)"
                    size="small"
                    value={custPrefDistId}
                    onChange={(e) => setCustPrefDistId(e.target.value)}
                    fullWidth
                  />
                  <TextField
                    select
                    label="Partner tier (all partners)"
                    size="small"
                    value={custPartnerTier}
                    onChange={(e) => setCustPartnerTier(e.target.value)}
                    fullWidth
                  >
                    {['strategic', 'tier_1', 'tier_2', 'tier_3', 'core', 'long_tail', 'unmanaged'].map((t) => (
                      <MenuItem key={t} value={t}>
                        {t}
                      </MenuItem>
                    ))}
                  </TextField>
                  <TextField
                    label="Notes (optional, all partners)"
                    size="small"
                    value={custNotes}
                    onChange={(e) => setCustNotes(e.target.value)}
                    fullWidth
                    multiline
                    minRows={2}
                  />
                </Stack>
              )}
            </Box>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setBulkProvOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            disabled={
              selectedCandidateIds.size === 0 ||
              [...selectedCandidateIds].some((id) => !(bulkProvNamesById[id] ?? '').trim()) ||
              unifiedBulkProvMut.isPending ||
              selectedIncludeSpecialCategory
            }
            onClick={() => unifiedBulkProvMut.mutate()}
          >
            Confirm
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={bulkMapOpen} onClose={() => setBulkMapOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Bulk map to customer</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Typography variant="body2">
              Maps <strong>{selectedCustomerIdsList.length}</strong> selected channel partner candidate(s) to one
              existing customer.
            </Typography>
            <Typography variant="subtitle2">Recent provisionals from this job</Typography>
            {bulkMapRecent.length === 0 ? (
              <Typography variant="caption" color="text.secondary">
                No recent unverified customers linked to this job, or still loading.
              </Typography>
            ) : (
              <List dense disablePadding sx={{ border: 1, borderColor: 'divider', borderRadius: 1 }}>
                {bulkMapRecent.map((c) => (
                  <ListItemButton
                    key={c.id}
                    selected={bulkMapPickId === c.id}
                    onClick={() => setBulkMapPickId(c.id)}
                  >
                    <Stack spacing={0.25} alignItems="flex-start" sx={{ py: 0.5 }}>
                      <Typography variant="body2" component="div">
                        {c.customer_name || '—'}{' '}
                        <Typography component="span" variant="caption" color="text.secondary">
                          ({(c.customer_code || '').trim() || '—'})
                        </Typography>
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        Created {formatCustomerCreatedAt(c.created_at)}
                      </Typography>
                    </Stack>
                  </ListItemButton>
                ))}
              </List>
            )}
            <Divider />
            <Typography variant="subtitle2">Search all customers</Typography>
            <TextField
              label="Search by name or code"
              size="small"
              value={bulkMapSearch}
              onChange={(e) => setBulkMapSearch(e.target.value)}
              fullWidth
              helperText="Provisional (unverified) matches are listed first when you search."
            />
            {bulkMapSearch.trim().length >= 1 ? (
              bulkMapSearchHits.length === 0 ? (
                <Typography variant="caption" color="text.secondary">
                  No matches.
                </Typography>
              ) : (
                <List dense disablePadding sx={{ border: 1, borderColor: 'divider', borderRadius: 1, maxHeight: 280, overflow: 'auto' }}>
                  {bulkMapSearchHits.map((c) => (
                    <ListItemButton
                      key={c.id}
                      selected={bulkMapPickId === c.id}
                      onClick={() => setBulkMapPickId(c.id)}
                    >
                      <Typography
                        variant="body2"
                        component="div"
                        sx={{ display: 'flex', flexDirection: 'row', gap: 1, alignItems: 'baseline', flexWrap: 'wrap' }}
                      >
                        <span>{c.customer_name || '—'}</span>
                        <Typography component="span" variant="caption" color="text.secondary">
                          {(c.customer_code || '').trim() || '—'}
                        </Typography>
                        {c.customer_status === 'unverified' ? (
                          <Chip size="small" label="Unverified" variant="outlined" />
                        ) : null}
                      </Typography>
                    </ListItemButton>
                  ))}
                </List>
              )
            ) : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setBulkMapOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            disabled={
              importJobId == null ||
              selectedCustomerIdsList.length === 0 ||
              bulkMapPickId == null ||
              bulkMapMut.isPending
            }
            onClick={() => {
              if (importJobId == null || bulkMapPickId == null) return;
              bulkMapMut.mutate({
                candidate_ids: selectedCustomerIdsList,
                customer_id: bulkMapPickId,
              });
            }}
          >
            Map selected
          </Button>
        </DialogActions>
      </Dialog>
    </Paper>
  );
}
