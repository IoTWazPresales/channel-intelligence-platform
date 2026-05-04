'use client';

import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useMemo, useState } from 'react';

import { apiGet, apiPost } from '@/lib/api';
import { toQueryError } from '@/lib/queryError';

export type DsiCandidateRow = {
  id: number;
  import_job_id: number;
  source_definition_id: number | null;
  entity_type: string;
  normalized_key: string;
  dealer_group_token: string | null;
  row_count: number;
  total_units: number | null;
  total_reported_value: number | null;
  sample_raw_values: string[] | null;
  suggested_entity_id: number | null;
  match_reason: string | null;
  confidence_score: number | null;
  status: string;
  context: Record<string, unknown> | null;
};

type RegionOpt = { id: number; code: string; name: string };
type ChannelOpt = { id: number; code: string; name: string };
type CustomerHit = { id: number; customer_code: string; customer_name: string };
type DistributorHit = { id: number; distributor_code: string; distributor_name: string };
type ProductHit = { id: number; sku: string; name: string; sales_model_name: string | null; is_active: boolean };

function strategicHint(ctx: Record<string, unknown> | null | undefined): boolean {
  return Boolean(ctx && ctx.strategic_channel_hint === true);
}

function blankishCustomerKey(norm: string): boolean {
  const t = (norm || '').trim().toLowerCase();
  return t === '' || t === '__blank__' || t === 'none' || t === 'n/a' || t === 'na' || t === 'unknown';
}

export function DsiCandidateStewardPanel({
  importJobId,
  candidate,
  onDone,
}: {
  importJobId: number;
  candidate: DsiCandidateRow | null;
  onDone: () => void;
}) {
  const qc = useQueryClient();
  const [mapCustOpen, setMapCustOpen] = useState(false);
  const [createCustOpen, setCreateCustOpen] = useState(false);
  const [mapDistOpen, setMapDistOpen] = useState(false);
  const [createDistOpen, setCreateDistOpen] = useState(false);
  const [mapProdOpen, setMapProdOpen] = useState(false);
  const [ocOpen, setOcOpen] = useState(false);

  const [custQ, setCustQ] = useState('');
  const [distQ, setDistQ] = useState('');
  const [prodQ, setProdQ] = useState('');
  const [pickCustomerId, setPickCustomerId] = useState<number | ''>('');
  const [pickDistributorId, setPickDistributorId] = useState<number | ''>('');
  const [pickProductId, setPickProductId] = useState<number | ''>('');

  const [displayName, setDisplayName] = useState('');
  const [regionId, setRegionId] = useState<number | ''>('');
  const [channelId, setChannelId] = useState<number | ''>('');
  const [distDisplayName, setDistDisplayName] = useState('');
  const [distConfirmSuspicious, setDistConfirmSuspicious] = useState(false);
  const [ocNamedConfirm, setOcNamedConfirm] = useState(false);
  const [ocStrategicConfirm, setOcStrategicConfirm] = useState(false);
  const [confirmIneligibleProduct, setConfirmIneligibleProduct] = useState(false);
  const [productAuditNote, setProductAuditNote] = useState('');
  const [productRawOverride, setProductRawOverride] = useState('');

  const { data: regions = [] } = useQuery({
    queryKey: ['catalog-regions'],
    queryFn: ({ signal }) => apiGet<RegionOpt[]>('/api/v1/catalog/regions', { signal }),
  });
  const { data: channels = [] } = useQuery({
    queryKey: ['catalog-channels'],
    queryFn: ({ signal }) => apiGet<ChannelOpt[]>('/api/v1/catalog/channels', { signal }),
  });

  const { data: custHits = [] } = useQuery({
    queryKey: ['customers-search', custQ],
    queryFn: ({ signal }) =>
      apiGet<{ items: CustomerHit[] }>(`/api/v1/customers?q=${encodeURIComponent(custQ)}&page_size=20`, { signal }),
    enabled: custQ.trim().length >= 2,
    select: (r) => r.items ?? [],
  });

  const { data: distHits = [] } = useQuery({
    queryKey: ['distributors-search', distQ],
    queryFn: ({ signal }) =>
      apiGet<{ items: DistributorHit[] }>(
        `/api/v1/distributors?q=${encodeURIComponent(distQ)}&page_size=20`,
        { signal }
      ),
    enabled: distQ.trim().length >= 1,
    select: (r) => r.items ?? [],
  });

  const { data: prodHits = [] } = useQuery({
    queryKey: ['products-search-dsi-steward', prodQ],
    queryFn: ({ signal }) =>
      apiGet<{ items: ProductHit[] }>(`/api/v1/products?q=${encodeURIComponent(prodQ)}&page_size=20`, { signal }),
    enabled: prodQ.trim().length >= 1,
    select: (r) => r.items ?? [],
  });

  const invalidate = useCallback(() => {
    void qc.invalidateQueries({ queryKey: ['dsi-mapping-candidates', importJobId] });
    onDone();
  }, [qc, importJobId, onDone]);

  const mapCustomer = useMutation({
    mutationFn: (body: { customer_id: number }) =>
      apiPost<{ ok: boolean }>(`/api/v1/mappings/import-candidates/${candidate?.id}/map-customer`, body),
    onSuccess: () => {
      setMapCustOpen(false);
      invalidate();
    },
  });

  const createProvCustomer = useMutation({
    mutationFn: (body: {
      display_name: string;
      region_id: number;
      channel_id: number;
      preferred_distributor_id?: number | null;
    }) =>
      apiPost<{ ok: boolean }>(
        `/api/v1/mappings/import-candidates/${candidate?.id}/create-provisional-customer`,
        body
      ),
    onSuccess: () => {
      setCreateCustOpen(false);
      invalidate();
    },
  });

  const markOpenChannel = useMutation({
    mutationFn: (body: { confirm_for_named_dealer: boolean; confirm_for_strategic_channel_hint: boolean }) =>
      apiPost<{ ok: boolean }>(`/api/v1/mappings/import-candidates/${candidate?.id}/mark-open-channel`, body),
    onSuccess: () => {
      setOcOpen(false);
      invalidate();
    },
  });

  const ignoreCand = useMutation({
    mutationFn: (body: { notes?: string | null }) =>
      apiPost<{ ok: boolean }>(`/api/v1/mappings/import-candidates/${candidate?.id}/ignore`, body),
    onSuccess: () => invalidate(),
  });

  const mapDistributor = useMutation({
    mutationFn: (body: { distributor_id: number }) =>
      apiPost<{ ok: boolean }>(`/api/v1/mappings/import-candidates/${candidate?.id}/map-distributor`, body),
    onSuccess: () => {
      setMapDistOpen(false);
      invalidate();
    },
  });

  const createProvDistributor = useMutation({
    mutationFn: (body: { display_name: string; confirm_for_suspicious_token: boolean }) =>
      apiPost<{ ok: boolean }>(
        `/api/v1/mappings/import-candidates/${candidate?.id}/create-provisional-distributor`,
        body
      ),
    onSuccess: () => {
      setCreateDistOpen(false);
      invalidate();
    },
  });

  const resolveProduct = useMutation({
    mutationFn: (body: {
      product_id: number;
      raw_token?: string | null;
      confirm_ineligible_product: boolean;
      audit_note?: string | null;
    }) =>
      apiPost<{ ok: boolean }>(`/api/v1/mappings/import-candidates/${candidate?.id}/resolve-product`, body),
    onSuccess: () => {
      setMapProdOpen(false);
      invalidate();
    },
  });

  const revalidate = useMutation({
    mutationFn: () =>
      apiPost<{ ok: boolean }>(`/api/v1/mappings/import-jobs/${importJobId}/revalidate-distributor-sales-inventory`),
    onSuccess: () => invalidate(),
  });

  /** Customer account (Dealer Name Group) vs source customer evidence — match DSI aggregation / mapping queue. */
  const stewardLabels = useMemo(() => {
    if (!candidate) {
      return { customerAccount: '', sourceCustomer: '', distributorOrProductLabel: '' };
    }
    const sampleFirst =
      candidate.sample_raw_values?.find((x) => x && String(x).trim()) || candidate.normalized_key || '';
    if (candidate.entity_type !== 'customer_dealer_token') {
      return { customerAccount: '', sourceCustomer: '', distributorOrProductLabel: String(sampleFirst) };
    }
    const c = (candidate.context ?? null) as Record<string, unknown> | null;
    const raw =
      typeof c?.dealer_group_account_raw === 'string' ? c.dealer_group_account_raw.trim() : '';
    const customerAccount = (raw || candidate.dealer_group_token || candidate.normalized_key || '').toString();
    const samples = c?.source_customer_name_raw_samples;
    let sourceCustomer = '';
    if (Array.isArray(samples)) {
      const parts = samples
        .filter((x) => typeof x === 'string' && x.trim())
        .map((x) => String(x).trim());
      if (parts.length) sourceCustomer = parts.join('; ');
    }
    return { customerAccount, sourceCustomer, distributorOrProductLabel: String(sampleFirst) };
  }, [candidate]);

  if (!candidate) {
    return (
      <Typography variant="body2" color="text.secondary" data-testid="dsi-steward-no-selection">
        Select a candidate row in the grid to run steward actions (map, provisional create, Open Channel, ignore).
      </Typography>
    );
  }

  const ctx = (candidate.context ?? null) as Record<string, unknown> | null;
  const strat = strategicHint(ctx);
  const isTerminal = ['resolved', 'ignored', 'waived_open_channel'].includes(candidate.status);

  return (
    <Stack spacing={2} sx={{ mt: 2 }} data-testid="dsi-steward-panel">
      <Alert severity="info">
        Provisional records are created as <strong>unverified</strong> and editable. They give facts a stable system ID
        without implying the profile is complete. Open Channel / blank inventory evidence must not create fake
        customers—use <strong>Mark Open Channel</strong> only for blank or explicitly confirmed cases.
      </Alert>
      {strat ? (
        <Alert severity="warning" data-testid="dsi-strategic-hint-alert">
          Channel evidence resembles a strategic marketplace or major retail chain. Do not assume Open Channel—map or
          create a customer, or confirm explicitly if Open Channel is correct.
        </Alert>
      ) : null}
      <Typography variant="body2">
        <strong>Selected:</strong> {candidate.entity_type} · normalized: {candidate.normalized_key}
        {stewardLabels.customerAccount ? ` · customer account: ${stewardLabels.customerAccount}` : ''}
        {stewardLabels.sourceCustomer ? ` · source customer: ${stewardLabels.sourceCustomer}` : ''} · status{' '}
        {candidate.status}
      </Typography>
      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
        <Button
          variant="outlined"
          size="small"
          disabled={isTerminal || candidate.entity_type !== 'customer_dealer_token'}
          onClick={() => {
            setDisplayName(
              stewardLabels.customerAccount || candidate.normalized_key || stewardLabels.distributorOrProductLabel
            );
            if (regions[0]) setRegionId(regions[0].id);
            if (channels[0]) setChannelId(channels[0].id);
            setCreateCustOpen(true);
          }}
          data-testid="dsi-action-create-provisional-customer"
        >
          Create provisional customer
        </Button>
        <Button
          variant="outlined"
          size="small"
          disabled={isTerminal || candidate.entity_type !== 'customer_dealer_token'}
          onClick={() => {
            setCustQ('');
            setPickCustomerId('');
            setMapCustOpen(true);
          }}
          data-testid="dsi-action-map-customer"
        >
          Map to existing customer
        </Button>
        <Button
          variant="outlined"
          size="small"
          disabled={isTerminal || candidate.entity_type !== 'customer_dealer_token'}
          onClick={() => {
            setOcNamedConfirm(false);
            setOcStrategicConfirm(false);
            setOcOpen(true);
          }}
          data-testid="dsi-action-open-channel"
        >
          Mark Open Channel (alias)
        </Button>
        <Button
          variant="outlined"
          size="small"
          disabled={isTerminal || candidate.entity_type !== 'distributor_token'}
          onClick={() => {
            setDistQ('');
            setPickDistributorId('');
            setMapDistOpen(true);
          }}
          data-testid="dsi-action-map-distributor"
        >
          Map to existing distributor
        </Button>
        <Button
          variant="outlined"
          size="small"
          disabled={isTerminal || candidate.entity_type !== 'distributor_token'}
          onClick={() => {
            setDistDisplayName(stewardLabels.distributorOrProductLabel);
            setDistConfirmSuspicious(false);
            setCreateDistOpen(true);
          }}
          data-testid="dsi-action-create-provisional-distributor"
        >
          Create provisional distributor
        </Button>
        <Button
          variant="outlined"
          size="small"
          disabled={isTerminal || candidate.entity_type !== 'product_identifier'}
          onClick={() => {
            setProdQ('');
            setPickProductId('');
            setConfirmIneligibleProduct(false);
            setProductAuditNote('');
            setProductRawOverride('');
            setMapProdOpen(true);
          }}
          data-testid="dsi-action-resolve-product"
        >
          Map to Product Master (alias)
        </Button>
        <Button
          variant="outlined"
          color="warning"
          size="small"
          disabled={isTerminal}
          onClick={() => void ignoreCand.mutateAsync({ notes: null })}
          data-testid="dsi-action-ignore"
        >
          Ignore candidate
        </Button>
      </Stack>
      {(mapCustomer.isError ||
        createProvCustomer.isError ||
        markOpenChannel.isError ||
        mapDistributor.isError ||
        createProvDistributor.isError ||
        resolveProduct.isError ||
        ignoreCand.isError) && (
        <Alert severity="error">
          {toQueryError(
            mapCustomer.error ||
              createProvCustomer.error ||
              markOpenChannel.error ||
              mapDistributor.error ||
              createProvDistributor.error ||
              resolveProduct.error ||
              ignoreCand.error
          )?.message ?? 'Action failed'}
        </Alert>
      )}

      <Dialog open={mapCustOpen} onClose={() => setMapCustOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>Map to existing customer</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="Search customers"
              value={custQ}
              onChange={(e) => setCustQ(e.target.value)}
              helperText="Type at least 2 characters"
              fullWidth
            />
            <FormControl fullWidth>
              <InputLabel id="pick-cust">Customer</InputLabel>
              <Select
                labelId="pick-cust"
                label="Customer"
                value={pickCustomerId === '' ? '' : String(pickCustomerId)}
                onChange={(e) => setPickCustomerId(e.target.value === '' ? '' : Number(e.target.value))}
              >
                {custHits.map((c) => (
                  <MenuItem key={c.id} value={String(c.id)}>
                    {c.customer_code} — {c.customer_name}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setMapCustOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            disabled={pickCustomerId === '' || mapCustomer.isPending}
            onClick={() => {
              if (pickCustomerId === '') return;
              void mapCustomer.mutateAsync({ customer_id: Number(pickCustomerId) });
            }}
          >
            Save alias
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={createCustOpen} onClose={() => setCreateCustOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>Create provisional customer</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField label="Display name" value={displayName} onChange={(e) => setDisplayName(e.target.value)} fullWidth />
            <FormControl fullWidth>
              <InputLabel id="reg">Region</InputLabel>
              <Select
                labelId="reg"
                label="Region"
                value={regionId === '' ? '' : String(regionId)}
                onChange={(e) => setRegionId(e.target.value === '' ? '' : Number(e.target.value))}
              >
                {regions.map((r) => (
                  <MenuItem key={r.id} value={String(r.id)}>
                    {r.code} — {r.name}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <FormControl fullWidth>
              <InputLabel id="ch">Channel</InputLabel>
              <Select
                labelId="ch"
                label="Channel"
                value={channelId === '' ? '' : String(channelId)}
                onChange={(e) => setChannelId(e.target.value === '' ? '' : Number(e.target.value))}
              >
                {channels.map((c) => (
                  <MenuItem key={c.id} value={String(c.id)}>
                    {c.code} — {c.name}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCreateCustOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            disabled={
              !displayName.trim() ||
              regionId === '' ||
              channelId === '' ||
              createProvCustomer.isPending
            }
            onClick={() =>
              void createProvCustomer.mutateAsync({
                display_name: displayName.trim(),
                region_id: Number(regionId),
                channel_id: Number(channelId),
              })
            }
          >
            Create &amp; alias
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={ocOpen} onClose={() => setOcOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>Mark Open Channel</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Typography variant="body2">
              Saves an approved alias to the Open Channel customer for this token. Named dealers require explicit
              confirmation; strategic channel hints require a separate confirmation.
            </Typography>
            {!blankishCustomerKey(candidate.normalized_key) ? (
              <label>
                <input
                  type="checkbox"
                  checked={ocNamedConfirm}
                  onChange={(e) => setOcNamedConfirm(e.target.checked)}
                  data-testid="dsi-oc-named-confirm"
                />{' '}
                I confirm mapping this named dealer token to Open Channel
              </label>
            ) : null}
            {strat ? (
              <label>
                <input
                  type="checkbox"
                  checked={ocStrategicConfirm}
                  onChange={(e) => setOcStrategicConfirm(e.target.checked)}
                  data-testid="dsi-oc-strategic-confirm"
                />{' '}
                I confirm Open Channel despite strategic / marketplace-style channel evidence
              </label>
            ) : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOcOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            disabled={
              markOpenChannel.isPending ||
              (!blankishCustomerKey(candidate.normalized_key) && !ocNamedConfirm) ||
              (strat && !ocStrategicConfirm)
            }
            onClick={() =>
              void markOpenChannel.mutateAsync({
                confirm_for_named_dealer: !blankishCustomerKey(candidate.normalized_key) ? ocNamedConfirm : false,
                confirm_for_strategic_channel_hint: strat ? ocStrategicConfirm : false,
              })
            }
          >
            Save Open Channel alias
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={mapDistOpen} onClose={() => setMapDistOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>Map to existing distributor</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField label="Search distributors" value={distQ} onChange={(e) => setDistQ(e.target.value)} fullWidth />
            <FormControl fullWidth>
              <InputLabel id="pick-dist">Distributor</InputLabel>
              <Select
                labelId="pick-dist"
                label="Distributor"
                value={pickDistributorId === '' ? '' : String(pickDistributorId)}
                onChange={(e) => setPickDistributorId(e.target.value === '' ? '' : Number(e.target.value))}
              >
                {distHits.map((d) => (
                  <MenuItem key={d.id} value={String(d.id)}>
                    {d.distributor_code} — {d.distributor_name}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setMapDistOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            disabled={pickDistributorId === '' || mapDistributor.isPending}
            onClick={() => {
              if (pickDistributorId === '') return;
              void mapDistributor.mutateAsync({ distributor_id: Number(pickDistributorId) });
            }}
          >
            Save alias
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={createDistOpen} onClose={() => setCreateDistOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>Create provisional distributor</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="Display name"
              value={distDisplayName}
              onChange={(e) => setDistDisplayName(e.target.value)}
              fullWidth
            />
            <label>
              <input
                type="checkbox"
                checked={distConfirmSuspicious}
                onChange={(e) => setDistConfirmSuspicious(e.target.checked)}
                data-testid="dsi-dist-suspicious-confirm"
              />{' '}
              Confirm create despite placeholder-like distributor token
            </label>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCreateDistOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            disabled={!distDisplayName.trim() || createProvDistributor.isPending}
            onClick={() =>
              void createProvDistributor.mutateAsync({
                display_name: distDisplayName.trim(),
                confirm_for_suspicious_token: distConfirmSuspicious,
              })
            }
          >
            Create &amp; alias
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={mapProdOpen} onClose={() => setMapProdOpen(false)} fullWidth maxWidth="md">
        <DialogTitle>Map product token to Product Master</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Typography variant="body2" color="text.secondary">
              Creates an approved <strong>ProductAlias</strong> for this import token, then mark this candidate resolved.
              Run <strong>Revalidate import job</strong> from the mapping queue page so staging picks up the new alias.
            </Typography>
            <TextField
              label="Search products (SKU / model)"
              value={prodQ}
              onChange={(e) => setProdQ(e.target.value)}
              helperText="Type at least 1 character"
              fullWidth
            />
            <FormControl fullWidth>
              <InputLabel id="pick-prod">Product</InputLabel>
              <Select
                labelId="pick-prod"
                label="Product"
                value={pickProductId === '' ? '' : String(pickProductId)}
                onChange={(e) => setPickProductId(e.target.value === '' ? '' : Number(e.target.value))}
              >
                {prodHits.map((p) => (
                  <MenuItem key={p.id} value={String(p.id)}>
                    {p.sku} — {p.name}
                    {p.sales_model_name ? ` (${p.sales_model_name})` : ''}
                    {!p.is_active ? ' [inactive]' : ''}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <TextField
              label="Raw token override (optional)"
              value={productRawOverride}
              onChange={(e) => setProductRawOverride(e.target.value)}
              helperText="Leave blank to use candidate samples / normalized token"
              fullWidth
            />
            <label>
              <input
                type="checkbox"
                checked={confirmIneligibleProduct}
                onChange={(e) => setConfirmIneligibleProduct(e.target.checked)}
                data-testid="dsi-product-ineligible-confirm"
              />{' '}
              Confirm mapping to an inactive / ineligible Product Master row (requires audit note)
            </label>
            <TextField
              label="Audit note (required if confirming inactive/ineligible)"
              value={productAuditNote}
              onChange={(e) => setProductAuditNote(e.target.value)}
              multiline
              minRows={2}
              fullWidth
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setMapProdOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            disabled={pickProductId === '' || resolveProduct.isPending}
            onClick={() => {
              if (pickProductId === '') return;
              const rawTok = productRawOverride.trim() || undefined;
              void resolveProduct.mutateAsync({
                product_id: Number(pickProductId),
                raw_token: rawTok,
                confirm_ineligible_product: confirmIneligibleProduct,
                audit_note: productAuditNote.trim() || undefined,
              });
            }}
            data-testid="dsi-product-resolve-save"
          >
            Save ProductAlias &amp; resolve
          </Button>
        </DialogActions>
      </Dialog>

      {candidate.entity_type === 'product_identifier' ? (
        <Stack spacing={1}>
          <Alert severity="warning" data-testid="dsi-product-guidance">
            Product identifiers are governed through Product Master / ProductAlias. Map via Product Master workflows; this
            screen does not create products or provisional SKUs.
          </Alert>
          {typeof ctx?.product_match_summary === 'string' && ctx.product_match_summary.trim() ? (
            <Alert severity="info" data-testid="dsi-product-match-summary">
              <Typography variant="body2">{String(ctx.product_match_summary)}</Typography>
              {ctx.product_match_status === 'ambiguous_eligible' && Array.isArray(ctx.product_ambiguous_eligible?.eligible_products) ? (
                <Typography variant="caption" component="div" sx={{ mt: 1, whiteSpace: 'pre-wrap' }}>
                  {JSON.stringify(ctx.product_ambiguous_eligible, null, 2)}
                </Typography>
              ) : null}
              {ctx.product_match_status === 'inactive_only' && Array.isArray(ctx.product_inactive_matches) ? (
                <Typography variant="caption" component="div" sx={{ mt: 1, whiteSpace: 'pre-wrap' }}>
                  {JSON.stringify(ctx.product_inactive_matches, null, 2)}
                </Typography>
              ) : null}
            </Alert>
          ) : null}
        </Stack>
      ) : null}
    </Stack>
  );
}
