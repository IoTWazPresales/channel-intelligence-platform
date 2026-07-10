'use client';

import {
  Alert,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  MenuItem,
  Stack,
  Switch,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';

import { DsiPendingButton } from './DsiPendingButton';
import { apiGet, apiPost } from '@/lib/api';
import { invalidateShipmentImportJobStewardQueries, isShipmentStewardRowActionBlocked } from './shipmentSteward.config';
import {
  SHIPMENT_ENTITY_CUST,
  SHIPMENT_ENTITY_DIST,
  isShipmentCustomerEntity,
  isShipmentDistributorEntity,
  shipmentCanClearSpecialCategory,
  shipmentCustomerSpecialCategoryBlocksProvisional,
  shipmentEntityChipLabel,
  shipmentSampleToken,
  shipmentSuggestedNameFromContext,
  type ShipmentMappingCandidateRow,
} from './shipmentMappingCandidateDisplay';

type DistributorHit = { id: number; distributor_code: string; distributor_name: string };
type CustomerHit = { id: number; customer_code: string; customer_name: string };

type ShipmentStewardActionsApi = {
  openMap: (row: ShipmentMappingCandidateRow) => void;
  openProv: (row: ShipmentMappingCandidateRow) => void;
  openSpecialCat: (row: ShipmentMappingCandidateRow) => void;
  openReject: (row: ShipmentMappingCandidateRow) => void;
  clearSpecial: (candidateId: number) => void;
  actionBusy: boolean;
  actionError: string | null;
  clearActionError: () => void;
};

const ShipmentStewardActionsContext = createContext<ShipmentStewardActionsApi | null>(null);

function parseOptInt(s: string): number | null {
  const t = s.trim();
  if (!t) return null;
  const n = Number(t);
  return Number.isFinite(n) && n >= 1 ? n : null;
}

export function ShipmentStewardActionsProvider({
  importJobId,
  onInvalidate,
  children,
}: {
  importJobId: number;
  onInvalidate: () => void;
  children: ReactNode;
}) {
  const qc = useQueryClient();
  const [active, setActive] = useState<ShipmentMappingCandidateRow | null>(null);
  const [mapOpen, setMapOpen] = useState(false);
  const [provOpen, setProvOpen] = useState(false);
  const [specialCatOpen, setSpecialCatOpen] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [specialCatChoice, setSpecialCatChoice] = useState<'noise_only' | 'internal_note'>('noise_only');
  const [actionError, setActionError] = useState<string | null>(null);

  const [distQ, setDistQ] = useState('');
  const [custQ, setCustQ] = useState('');
  const [distQDebounced, setDistQDebounced] = useState('');
  const [custQDebounced, setCustQDebounced] = useState('');
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

  useEffect(() => {
    const t = window.setTimeout(() => setCustQDebounced(custQ), 300);
    return () => window.clearTimeout(t);
  }, [custQ]);

  useEffect(() => {
    const t = window.setTimeout(() => setDistQDebounced(distQ), 300);
    return () => window.clearTimeout(t);
  }, [distQ]);

  const invalidate = useCallback(() => {
    invalidateShipmentImportJobStewardQueries(qc, importJobId);
    onInvalidate();
  }, [importJobId, onInvalidate, qc]);

  const { data: distHits = [] } = useQuery({
    queryKey: ['distributors-search-shipment-steward', distQDebounced],
    queryFn: ({ signal }) =>
      apiGet<{ items: DistributorHit[] }>(
        `/api/v1/distributors?q=${encodeURIComponent(distQDebounced)}&page_size=20`,
        { signal }
      ),
    enabled: mapOpen && distQDebounced.trim().length >= 1,
    select: (r) => r.items ?? [],
  });

  const { data: custHits = [] } = useQuery({
    queryKey: ['customers-search-shipment-steward', custQDebounced],
    queryFn: ({ signal }) =>
      apiGet<{ items: CustomerHit[] }>(
        `/api/v1/customers?q=${encodeURIComponent(custQDebounced)}&page_size=20`,
        { signal }
      ),
    enabled: mapOpen && custQDebounced.trim().length >= 1,
    select: (r) => r.items ?? [],
  });

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
        body
      ),
    onSuccess: () => {
      setActionError(null);
      setProvOpen(false);
      setActive(null);
      invalidate();
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
        body
      ),
    onSuccess: () => {
      setActionError(null);
      setProvOpen(false);
      setActive(null);
      invalidate();
    },
    onError: (e: Error) => setActionError(e.message),
  });

  const manualSpecialMut = useMutation({
    mutationFn: (body: { candidate_id: number; special_category: 'noise_only' | 'internal_note' }) =>
      apiPost<Record<string, unknown>>(
        `/api/v1/shipment-evidence/import-candidates/${body.candidate_id}/manual-special-category`,
        { special_category: body.special_category }
      ),
    onSuccess: () => {
      setActionError(null);
      setSpecialCatOpen(false);
      setActive(null);
      invalidate();
    },
    onError: (e: Error) => setActionError(e.message),
  });

  const rejectMut = useMutation({
    mutationFn: (candidate_id: number) =>
      apiPost<Record<string, unknown>>(`/api/v1/shipment-evidence/import-candidates/${candidate_id}/reject`),
    onSuccess: () => {
      setActionError(null);
      setRejectOpen(false);
      setActive(null);
      invalidate();
    },
    onError: (e: Error) => setActionError(e.message),
  });

  const clearSpecialMut = useMutation({
    mutationFn: (candidate_id: number) =>
      apiPost<Record<string, unknown>>(
        `/api/v1/shipment-evidence/import-candidates/${candidate_id}/clear-special-category`,
        {}
      ),
    onSuccess: () => {
      setActionError(null);
      setActive(null);
      invalidate();
    },
    onError: (e: Error) => setActionError(e.message),
  });

  const actionBusy =
    mapMut.isPending ||
    provDistMut.isPending ||
    provCustMut.isPending ||
    manualSpecialMut.isPending ||
    clearSpecialMut.isPending ||
    rejectMut.isPending;

  const openMap = useCallback((r: ShipmentMappingCandidateRow) => {
    setActive(r);
    setPickDistId('');
    setPickCustId('');
    const tok = shipmentSampleToken(r);
    const sug =
      (r.context && typeof r.context.suggested_name === 'string' ? r.context.suggested_name : '') ||
      (r.suggested_distributor_name || '').trim();
    if (isShipmentDistributorEntity(r.entity_type)) {
      setDistQ(sug || (tok !== '—' ? tok : ''));
      setCustQ('');
    } else {
      setCustQ(tok !== '—' ? tok : '');
      setDistQ('');
    }
    setActionError(null);
    setMapOpen(true);
  }, []);

  const openProv = useCallback((r: ShipmentMappingCandidateRow) => {
    setActive(r);
    const tok = shipmentSampleToken(r);
    setProvName(shipmentSuggestedNameFromContext(r.context, tok).slice(0, 200));
    setProvCode('');
    setProvConfirmSuspicious(false);
    setCustRegionId('');
    setCustChannelId('');
    setCustPrefDistId('');
    setCustPartnerTier('unmanaged');
    setCustNotes('');
    setActionError(null);
    setProvOpen(true);
  }, []);

  const openSpecialCat = useCallback((r: ShipmentMappingCandidateRow) => {
    setActive(r);
    setSpecialCatChoice('noise_only');
    setActionError(null);
    setSpecialCatOpen(true);
  }, []);

  const openReject = useCallback((r: ShipmentMappingCandidateRow) => {
    setActive(r);
    setActionError(null);
    setRejectOpen(true);
  }, []);

  const api = useMemo<ShipmentStewardActionsApi>(
    () => ({
      openMap,
      openProv,
      openSpecialCat,
      openReject,
      clearSpecial: (id) => clearSpecialMut.mutate(id),
      actionBusy,
      actionError,
      clearActionError: () => setActionError(null),
    }),
    [actionBusy, actionError, clearSpecialMut, openMap, openProv, openReject, openSpecialCat]
  );

  return (
    <ShipmentStewardActionsContext.Provider value={api}>
      {children}
      {actionError ? (
        <Alert
          severity={actionError.startsWith('Partial success') ? 'warning' : 'error'}
          onClose={() => setActionError(null)}
          sx={{ mb: 1 }}
          data-testid="shipment-steward-action-error"
        >
          {actionError}
        </Alert>
      ) : null}

      <Dialog open={mapOpen} onClose={() => setMapOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>
          {active && isShipmentCustomerEntity(active.entity_type)
            ? 'Map token to customer'
            : 'Map token to distributor'}
        </DialogTitle>
        <DialogContent>
          {active ? (
            <Stack spacing={2} sx={{ mt: 1 }}>
              <Typography variant="body2">
                Candidate {active.id} · <Chip size="small" label={shipmentEntityChipLabel(active.entity_type)} /> ·{' '}
                <strong>{shipmentSampleToken(active)}</strong>
              </Typography>
              {isShipmentDistributorEntity(active.entity_type) ? (
                <>
                  <TextField label="Search distributors" size="small" value={distQ} onChange={(e) => setDistQ(e.target.value)} fullWidth />
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
                  <TextField label="Search customers" size="small" value={custQ} onChange={(e) => setCustQ(e.target.value)} fullWidth />
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
              (active && isShipmentDistributorEntity(active.entity_type) && pickDistId === '') ||
              (active && isShipmentCustomerEntity(active.entity_type) && pickCustId === '')
            }
            onClick={() => {
              if (!active) return;
              const tok = shipmentSampleToken(active) !== '—' ? shipmentSampleToken(active) : null;
              if (isShipmentDistributorEntity(active.entity_type) && pickDistId !== '') {
                mapMut.mutate({
                  candidate_id: active.id,
                  mode: 'distributor',
                  distributor_id: Number(pickDistId),
                  raw_token: tok,
                });
              } else if (isShipmentCustomerEntity(active.entity_type) && pickCustId !== '') {
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
          {active?.entity_type === SHIPMENT_ENTITY_CUST ? 'Create provisional customer' : 'Create provisional distributor'}
        </DialogTitle>
        <DialogContent>
          {active ? (
            <Stack spacing={2} sx={{ mt: 1 }}>
              <TextField label="Display name" size="small" value={provName} onChange={(e) => setProvName(e.target.value)} fullWidth />
              {active.entity_type === SHIPMENT_ENTITY_DIST ? (
                <>
                  <TextField label="Distributor code (optional)" size="small" value={provCode} onChange={(e) => setProvCode(e.target.value)} fullWidth />
                  <FormControlLabel
                    control={<Switch checked={provConfirmSuspicious} onChange={(e) => setProvConfirmSuspicious(e.target.checked)} />}
                    label="Confirm if token looks like a placeholder"
                  />
                </>
              ) : (
                <>
                  <TextField label="Region id (optional)" size="small" value={custRegionId} onChange={(e) => setCustRegionId(e.target.value)} fullWidth />
                  <TextField label="Channel id (optional)" size="small" value={custChannelId} onChange={(e) => setCustChannelId(e.target.value)} fullWidth />
                  <TextField label="Preferred distributor id (optional)" size="small" value={custPrefDistId} onChange={(e) => setCustPrefDistId(e.target.value)} fullWidth />
                  <TextField select label="Partner tier" size="small" value={custPartnerTier} onChange={(e) => setCustPartnerTier(e.target.value)} fullWidth>
                    {['strategic', 'tier_1', 'tier_2', 'tier_3', 'core', 'long_tail', 'unmanaged'].map((t) => (
                      <MenuItem key={t} value={t}>
                        {t}
                      </MenuItem>
                    ))}
                  </TextField>
                  <TextField label="Notes (optional)" size="small" value={custNotes} onChange={(e) => setCustNotes(e.target.value)} fullWidth multiline minRows={2} />
                </>
              )}
            </Stack>
          ) : null}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setProvOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            disabled={
              !active ||
              provDistMut.isPending ||
              provCustMut.isPending ||
              (active.entity_type === SHIPMENT_ENTITY_CUST && shipmentCustomerSpecialCategoryBlocksProvisional(active.context))
            }
            onClick={() => {
              if (!active) return;
              if (active.entity_type === SHIPMENT_ENTITY_DIST) {
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
        </DialogActions>
      </Dialog>

      <Dialog open={specialCatOpen} onClose={() => setSpecialCatOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle>Special category</DialogTitle>
        <DialogContent>
          <TextField
            select
            label="Category"
            size="small"
            value={specialCatChoice}
            onChange={(e) => setSpecialCatChoice(e.target.value as 'noise_only' | 'internal_note')}
            fullWidth
            sx={{ mt: 1 }}
          >
            <MenuItem value="noise_only">Noise only</MenuItem>
            <MenuItem value="internal_note">Internal note</MenuItem>
          </TextField>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setSpecialCatOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            disabled={!active || manualSpecialMut.isPending}
            onClick={() => active && manualSpecialMut.mutate({ candidate_id: active.id, special_category: specialCatChoice })}
          >
            Apply
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={rejectOpen} onClose={() => setRejectOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle>Reject candidate</DialogTitle>
        <DialogContent>
          <Typography variant="body2" sx={{ mt: 1 }}>
            Rejecting leaves evidence lines unresolved; this candidate will not auto-apply on import apply.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRejectOpen(false)}>Cancel</Button>
          <Button color="error" variant="contained" disabled={!active || rejectMut.isPending} onClick={() => active && rejectMut.mutate(active.id)}>
            Reject
          </Button>
        </DialogActions>
      </Dialog>
    </ShipmentStewardActionsContext.Provider>
  );
}

export function useShipmentStewardActions(): ShipmentStewardActionsApi {
  const ctx = useContext(ShipmentStewardActionsContext);
  if (!ctx) throw new Error('useShipmentStewardActions requires ShipmentStewardActionsProvider');
  return ctx;
}

export function ShipmentCandidateDrawerActions({ row }: { row: ShipmentMappingCandidateRow }) {
  const { openMap, openProv, openSpecialCat, openReject, clearSpecial, actionBusy } = useShipmentStewardActions();
  const blocked = isShipmentStewardRowActionBlocked(row.status);

  if (blocked) {
    return (
      <Typography variant="caption" color="text.secondary">
        —
      </Typography>
    );
  }

  return (
    <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap data-testid={`shipment-drawer-actions-${row.id}`}>
      <Button size="small" variant="outlined" disabled={actionBusy} onClick={() => openMap(row)}>
        Map
      </Button>
      {isShipmentCustomerEntity(row.entity_type) && shipmentCustomerSpecialCategoryBlocksProvisional(row.context) ? (
        <Button size="small" variant="outlined" disabled>
          Prov
        </Button>
      ) : (
        <Button size="small" variant="outlined" disabled={actionBusy} onClick={() => openProv(row)}>
          Prov
        </Button>
      )}
      <Button size="small" variant="outlined" color="warning" disabled={actionBusy} onClick={() => openSpecialCat(row)}>
        Special
      </Button>
      {shipmentCanClearSpecialCategory(row) ? (
        <Button size="small" variant="outlined" disabled={actionBusy} onClick={() => clearSpecial(row.id)}>
          Clear
        </Button>
      ) : null}
      <Button size="small" variant="outlined" color="error" disabled={actionBusy} onClick={() => openReject(row)}>
        Reject
      </Button>
    </Stack>
  );
}

export function ShipmentCandidateInlineActions({
  row,
  onReview,
  pending,
}: {
  row: ShipmentMappingCandidateRow;
  onReview: (row: ShipmentMappingCandidateRow) => void;
  pending?: boolean;
}) {
  const blocked = isShipmentStewardRowActionBlocked(row.status);

  if (pending) {
    return (
      <Typography variant="caption" color="text.secondary">
        Saving…
      </Typography>
    );
  }

  if (blocked) {
    return (
      <Typography variant="caption" color="text.secondary">
        —
      </Typography>
    );
  }

  return (
    <DsiPendingButton
      size="small"
      variant="outlined"
      onClick={(ev) => {
        ev.stopPropagation();
        onReview(row);
      }}
      data-testid={`shipment-action-review-${row.id}`}
    >
      Review…
    </DsiPendingButton>
  );
}
