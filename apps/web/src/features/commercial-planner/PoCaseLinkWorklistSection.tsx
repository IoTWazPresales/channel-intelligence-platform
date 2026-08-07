/**
 * Active case↔PO link worklist — Unlink disposition on ResolutionWorklist (Unit 6a / BACKLOG-109).
 * PO-shaped verb only (no requiresTarget). Stamp/alias is Unit 6b.
 */
'use client';

import { useMemo, useState, type InputHTMLAttributes } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Checkbox,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  Stack,
  TextField,
  Typography,
  Chip,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiGet, apiPost } from '@/lib/api';
import {
  ResolutionWorklist,
  type ResolutionBucket,
  type WorkItemProtection,
} from '@/features/steward-worklist';

export type CasePoLinkItem = {
  link_id: number;
  item_key: string;
  case_id: number;
  case_period_label?: string | null;
  commercial_status?: string | null;
  purchase_order_id: number;
  po_number?: string | null;
  po_number_norm?: string | null;
  notes?: string | null;
  carried_under_d032: boolean;
  row_class: 'active' | 'historical';
  po_link_count: number;
  bulk_protection?: {
    selection_protected: boolean;
    requires_allow_protected: boolean;
    reasons: string[];
    contested: boolean;
  } | null;
};

type CasePoLinksResponse = {
  links: CasePoLinkItem[];
  total: number;
  data_unavailable?: boolean;
};

type UnlinkResponse = {
  unlinked_count: number;
  results: Array<{
    case_id: number;
    purchase_order_id: number;
    before_status?: string;
    after_status?: string;
    before_po_count?: number;
    after_po_count?: number;
    carried_under_d032?: boolean;
  }>;
  reason: string;
};

function toProtection(item: CasePoLinkItem): WorkItemProtection | null {
  const p = item.bulk_protection;
  if (!p) return null;
  if (!p.selection_protected && !p.requires_allow_protected && !p.contested) return null;
  return {
    selectionProtected: !!p.selection_protected,
    requiresOverride: !!p.requires_allow_protected,
    contested: !!p.contested,
    reasonLabels: p.reasons ?? [],
  };
}

export const PO_CASE_LINK_SECTION_ID = 'po-case-link-section';

export function PoCaseLinkWorklistSection() {
  const qc = useQueryClient();
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const [unlinkTarget, setUnlinkTarget] = useState<CasePoLinkItem | null>(null);
  const [bulkKeys, setBulkKeys] = useState<string[] | null>(null);
  const [reason, setReason] = useState('wrong link');
  const [allowProtected, setAllowProtected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const linksQ = useQuery({
    queryKey: ['case-po-links'],
    queryFn: ({ signal }) =>
      apiGet<CasePoLinksResponse>('/api/v1/commercial-planner/lineup/case-po-links?limit=500', {
        signal,
      }),
  });

  const links = linksQ.data?.links ?? [];
  const byKey = useMemo(() => {
    const m = new Map<string, CasePoLinkItem>();
    for (const l of links) m.set(l.item_key, l);
    return m;
  }, [links]);

  const unlinkMut = useMutation({
    mutationFn: (vars: {
      items: Array<{ case_id: number; purchase_order_id: number; allow_protected?: boolean }>;
      reason: string;
      allow_protected?: boolean;
    }) => apiPost<UnlinkResponse>('/api/v1/commercial-planner/lineup/case-po-links/unlink', vars),
    onSuccess: (data) => {
      const lines = data.results.map(
        (r) =>
          `case ${r.case_id}↔PO ${r.purchase_order_id}: ${r.before_po_count}→${r.after_po_count} links, status ${r.before_status}→${r.after_status}`,
      );
      setSuccess(`Unlinked ${data.unlinked_count}: ${lines.join('; ')}`);
      setError(null);
      setUnlinkTarget(null);
      setBulkKeys(null);
      setAllowProtected(false);
      setSelected(new Set());
      void qc.invalidateQueries({ queryKey: ['case-po-links'] });
      void qc.invalidateQueries({ queryKey: ['po-auto-link'] });
      void qc.invalidateQueries({ queryKey: ['po-management'] });
    },
    onError: (err: unknown) => {
      const msg =
        err && typeof err === 'object' && 'message' in err
          ? String((err as { message?: string }).message)
          : String(err);
      setError(msg);
    },
  });

  const buckets: ResolutionBucket<'all' | 'protected' | 'carried'>[] = [
    { id: 'all', label: 'All active', count: links.length },
    {
      id: 'protected',
      label: 'Protected',
      count: links.filter((l) => l.bulk_protection?.requires_allow_protected).length,
    },
    {
      id: 'carried',
      label: 'D-032 carried',
      count: links.filter((l) => l.carried_under_d032).length,
    },
  ];
  const [bucket, setBucket] = useState<'all' | 'protected' | 'carried'>('all');
  const filtered = links.filter((l) => {
    if (bucket === 'protected') return !!l.bulk_protection?.requires_allow_protected;
    if (bucket === 'carried') return l.carried_under_d032;
    return true;
  });

  const openUnlink = (item: CasePoLinkItem) => {
    setUnlinkTarget(item);
    setReason('wrong link');
    setAllowProtected(false);
    setError(null);
  };

  const confirmUnlink = () => {
    if (unlinkTarget) {
      unlinkMut.mutate({
        items: [
          {
            case_id: unlinkTarget.case_id,
            purchase_order_id: unlinkTarget.purchase_order_id,
            allow_protected: allowProtected,
          },
        ],
        reason,
        allow_protected: allowProtected,
      });
      return;
    }
    if (bulkKeys?.length) {
      const items = bulkKeys
        .map((k) => byKey.get(k))
        .filter((x): x is CasePoLinkItem => !!x)
        .filter((x) => !x.bulk_protection?.requires_allow_protected)
        .map((x) => ({
          case_id: x.case_id,
          purchase_order_id: x.purchase_order_id,
          allow_protected: false,
        }));
      if (!items.length) {
        setError('No unprotected links in selection — protected cases must be unlinked individually.');
        return;
      }
      unlinkMut.mutate({ items, reason, allow_protected: false });
    }
  };

  const activeItem = activeKey ? byKey.get(activeKey) ?? null : null;

  return (
    <Card variant="outlined" id={PO_CASE_LINK_SECTION_ID} data-testid="po-case-link-section" sx={{ mb: 2 }}>
      <CardContent>
        <Stack spacing={1.5}>
          <Typography variant="h6">Linked case ↔ PO (unlink)</Typography>
          <Typography variant="body2" color="text.secondary">
            Remove an active link only. Historical links on superseded cases are refused. Protected cases
            require individual confirm with allow_protected.
          </Typography>
          {linksQ.isLoading ? (
            <Typography variant="body2" color="text.secondary">
              Loading links…
            </Typography>
          ) : linksQ.data?.data_unavailable ? (
            <Alert severity="info">Link list unavailable.</Alert>
          ) : !filtered.length ? (
            <Alert severity="info" data-testid="po-case-link-empty">
              No active case↔PO links.
            </Alert>
          ) : (
            <ResolutionWorklist<CasePoLinkItem, 'all' | 'protected' | 'carried'>
              rootTestId="po-case-link"
              getCheckboxTestId={(k) => `po-case-link-select-${k}`}
              items={filtered}
              getItemKey={(i) => i.item_key}
              getProtection={toProtection}
              buckets={buckets}
              activeBucket={bucket}
              onBucketChange={setBucket}
              selection={{
                selected,
                onToggle: (k) =>
                  setSelected((prev) => {
                    const next = new Set(prev);
                    if (next.has(k)) next.delete(k);
                    else next.add(k);
                    return next;
                  }),
                onReplace: (ks) => setSelected(new Set(ks)),
              }}
              actions={[
                {
                  id: 'unlink',
                  label: 'Unlink',
                  allowBulk: true,
                  requiresTarget: false,
                  onRun: ({ items }) => {
                    if (items.length === 1) openUnlink(items[0]);
                    else {
                      setBulkKeys(items.map((i) => i.item_key));
                      setReason('wrong link');
                      setAllowProtected(false);
                    }
                  },
                },
              ]}
              bulkActions={[
                {
                  id: 'unlink-bulk',
                  label: 'Unlink selected',
                  allowBulk: true,
                  requiresTarget: false,
                  onRun: ({ items }) => {
                    setBulkKeys(items.map((i) => i.item_key));
                    setReason('wrong link');
                    setAllowProtected(false);
                  },
                },
              ]}
              renderRow={(item, api) => (
                <Stack
                  direction="row"
                  spacing={1}
                  alignItems="center"
                  onClick={() => setActiveKey(item.item_key)}
                  sx={{ cursor: 'pointer', opacity: api.selected ? 1 : 0.95 }}
                >
                  <Typography variant="body2" sx={{ minWidth: 120 }}>
                    Case {item.case_id}
                  </Typography>
                  <Chip size="small" label={item.po_number ?? item.purchase_order_id} />
                  <Chip size="small" variant="outlined" label={item.commercial_status ?? '—'} />
                  {item.carried_under_d032 ? (
                    <Chip size="small" color="info" label="D-032 carried" data-testid={`po-case-link-carried-${item.item_key}`} />
                  ) : null}
                  {item.bulk_protection?.requires_allow_protected ? (
                    <Chip size="small" color="warning" label="Protected" data-testid={`po-case-link-protected-${item.item_key}`} />
                  ) : null}
                  <Box sx={{ flex: 1 }} />
                  <Button
                    size="small"
                    color="warning"
                    data-testid={`po-case-link-unlink-${item.item_key}`}
                    onClick={(e) => {
                      e.stopPropagation();
                      openUnlink(item);
                    }}
                  >
                    Unlink
                  </Button>
                </Stack>
              )}
              renderToolbar={() => (
                <Stack direction="row" spacing={1}>
                  <Button
                    size="small"
                    variant="outlined"
                    disabled={!selected.size || unlinkMut.isPending}
                    data-testid="po-case-link-bulk-unlink"
                    onClick={() => setBulkKeys([...selected])}
                  >
                    Unlink selected ({selected.size})
                  </Button>
                </Stack>
              )}
              drawer={{
                activeKey,
                onClose: () => setActiveKey(null),
                title: (item) => `Case ${item.case_id} ↔ ${item.po_number ?? item.purchase_order_id}`,
                renderEvidence: (item) => (
                  <Stack spacing={1}>
                    <Typography variant="body2">Status: {item.commercial_status}</Typography>
                    <Typography variant="body2">PO links on case: {item.po_link_count}</Typography>
                    <Typography variant="body2">
                      Carried under D-032: {item.carried_under_d032 ? 'yes' : 'no'}
                    </Typography>
                    {item.notes ? (
                      <Typography variant="body2" color="text.secondary">
                        Notes: {item.notes}
                      </Typography>
                    ) : null}
                  </Stack>
                ),
                renderDispositionActions: (item) => (
                  <Button
                    size="small"
                    color="warning"
                    variant="contained"
                    data-testid={`po-case-link-drawer-unlink-${item.item_key}`}
                    onClick={() => openUnlink(item)}
                  >
                    Unlink
                  </Button>
                ),
              }}
            />
          )}
          {success ? (
            <Alert severity="success" data-testid="po-case-link-success" onClose={() => setSuccess(null)}>
              {success}
            </Alert>
          ) : null}
          {error ? (
            <Alert severity="error" data-testid="po-case-link-error" onClose={() => setError(null)}>
              {error}
            </Alert>
          ) : null}
        </Stack>
      </CardContent>

      <Dialog
        open={!!unlinkTarget || !!bulkKeys}
        onClose={() => {
          setUnlinkTarget(null);
          setBulkKeys(null);
        }}
        data-testid="po-case-link-unlink-dialog"
      >
        <DialogTitle>
          {unlinkTarget
            ? `Unlink case ${unlinkTarget.case_id} ↔ ${unlinkTarget.po_number ?? unlinkTarget.purchase_order_id}`
            : `Unlink ${bulkKeys?.length ?? 0} selected links`}
        </DialogTitle>
        <DialogContent>
          <Stack spacing={1.5} sx={{ mt: 1 }}>
            <Typography variant="body2">
              Removes the active link row. Historical (superseded-case) links are refused. Does not delete the
              purchase order or shipment facts.
            </Typography>
            {unlinkTarget ? (
              <Typography variant="body2" data-testid="po-case-link-unlink-before">
                Before: {unlinkTarget.po_link_count} link(s) on case · status {unlinkTarget.commercial_status}
                {unlinkTarget.carried_under_d032 ? ' · originally carried under D-032' : ''}
              </Typography>
            ) : null}
            <TextField
              label="Reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              fullWidth
              size="small"
              inputProps={{ 'data-testid': 'po-case-link-unlink-reason' }}
            />
            {unlinkTarget?.bulk_protection?.requires_allow_protected ? (
              <FormControlLabel
                control={
                  <Checkbox
                    checked={allowProtected}
                    onChange={(e) => setAllowProtected(e.target.checked)}
                    inputProps={{ 'data-testid': 'po-case-link-allow-protected' } as InputHTMLAttributes<HTMLInputElement>}
                  />
                }
                label="Allow protected case (individual override)"
              />
            ) : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button
            onClick={() => {
              setUnlinkTarget(null);
              setBulkKeys(null);
            }}
          >
            Cancel
          </Button>
          <Button
            color="warning"
            variant="contained"
            disabled={!reason.trim() || unlinkMut.isPending}
            data-testid="po-case-link-unlink-submit"
            onClick={confirmUnlink}
          >
            {unlinkMut.isPending ? 'Unlinking…' : 'Confirm unlink'}
          </Button>
        </DialogActions>
      </Dialog>
    </Card>
  );
}
