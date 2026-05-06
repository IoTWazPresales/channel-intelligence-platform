'use client';

import type { ReactNode } from 'react';
import type { ColDef, GridOptions, ICellRendererParams, RowClickedEvent } from 'ag-grid-community';
import NextLink from 'next/link';
import Link from '@mui/material/Link';
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
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
  Drawer,
  FormControl,
  FormControlLabel,
  InputLabel,
  ListSubheader,
  MenuItem,
  Paper,
  Select,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AgGridReact } from 'ag-grid-react';

import { BulkSelectionToolbar, type BulkTableSelectionMode } from '@/components/bulkTable/BulkSelectionToolbar';
import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { apiGet, apiPost, safeDisplayError } from '@/lib/api';

import {
  DsiCandidateStewardPanel,
  type DsiCandidateRow,
} from '../mappings/DsiCandidateStewardPanel';

type BulkAction =
  | 'ignore'
  | 'map_customer'
  | 'map_distributor'
  | 'resolve_product'
  | 'create_provisional_customer'
  | 'create_provisional_distributor';

type CatalogOpt = { id: number; code: string; name: string };

function dsiSourceCustomerNameCell(ctx: Record<string, unknown> | null | undefined): string {
  if (!ctx) return '';
  const s = ctx.source_customer_name_raw_samples;
  if (!Array.isArray(s)) return '';
  return s
    .filter((x): x is string => typeof x === 'string' && x.trim().length > 0)
    .map((x) => x.trim())
    .join('; ');
}

function dsiProductMatchSummaryCell(ctx: Record<string, unknown> | null | undefined): string {
  if (!ctx) return '';
  const sum = ctx.product_match_summary;
  if (typeof sum === 'string' && sum.trim()) return sum.trim();
  return '';
}

type BulkPreviewResponse = {
  import_job_id: number;
  action: BulkAction;
  results: Array<Record<string, unknown>>;
  totals: Record<string, unknown>;
};

type BulkApplyResponse = {
  import_job_id: number;
  action: BulkAction;
  applied: number;
  failed: number;
  results: Array<Record<string, unknown>>;
  totals: Record<string, unknown>;
};

function bulkPreviewProposedLabel(r: Record<string, unknown>): string {
  const x = r.proposed_display_name;
  if (typeof x === 'string' && x.trim()) return x.trim();
  return '';
}

function bulkPreviewAliasEvidence(r: Record<string, unknown>): string {
  const ev =
    r.source_customer_alias_evidence ??
    r.source_customer_alias_raw_preview ??
    r.alias_raw_preview ??
    r.normalized_token_preview;
  if (typeof ev === 'string' && ev.trim()) return ev.trim();
  return '';
}

type PlanRowOverride = {
  action?: string;
  target_id?: number | null;
  region_id?: number | null;
  channel_id?: number | null;
  hold_for_manual_review?: boolean;
  ack_strategic_channel_hint?: boolean;
  confirm_for_suspicious_distributor_token?: boolean;
  confirm_ineligible_product?: boolean;
  audit_note?: string | null;
};

function allowedOverrideActions(entityType: string): string[] {
  if (entityType === 'distributor_token') {
    return ['ignore', 'map_distributor', 'create_provisional_distributor'];
  }
  if (entityType === 'product_identifier') {
    return ['ignore', 'resolve_product'];
  }
  if (entityType === 'customer_dealer_token') {
    return ['ignore', 'map_customer', 'create_provisional_customer'];
  }
  return [];
}

function formatPlanActionLabel(action: string): string {
  const m: Record<string, string> = {
    ignore: 'Ignore',
    map_distributor: 'Map to distributor',
    create_provisional_distributor: 'Create provisional distributor',
    map_customer: 'Map to customer',
    create_provisional_customer: 'Create provisional customer',
    resolve_product: 'Resolve product (alias)',
    none: 'None',
  };
  return m[action] ?? action;
}

type PlanReviewFilter =
  | 'all'
  | 'ready'
  | 'needs_work'
  | 'customer'
  | 'distributor'
  | 'product'
  | 'provisional'
  | 'map_resolve'
  | 'ignore'
  | 'manual';

function planRowMatchesReviewFilter(r: Record<string, unknown>, f: PlanReviewFilter): boolean {
  const et = String(r.entity_type ?? '');
  const act = String(r.suggested_action ?? '');
  const ready = r.ready === true;
  const hold = r.hold_for_manual_review === true;
  const blockers = Array.isArray(r.resolution_blockers) ? (r.resolution_blockers as unknown[]).length > 0 : false;
  switch (f) {
    case 'all':
      return true;
    case 'ready':
      return ready;
    case 'needs_work':
      return !ready;
    case 'customer':
      return et === 'customer_dealer_token';
    case 'distributor':
      return et === 'distributor_token';
    case 'product':
      return et === 'product_identifier';
    case 'provisional':
      return act === 'create_provisional_customer' || act === 'create_provisional_distributor';
    case 'map_resolve':
      return act === 'map_customer' || act === 'map_distributor' || act === 'resolve_product';
    case 'ignore':
      return act === 'ignore';
    case 'manual':
      return Boolean(hold) || blockers;
    default:
      return true;
  }
}

function truncateEllipsis(s: string, max: number): string {
  const t = s.trim();
  if (t.length <= max) return t;
  return `${t.slice(0, Math.max(0, max - 1))}…`;
}

function planReasonSummary(r: Record<string, unknown>): string {
  const blockers = Array.isArray(r.resolution_blockers)
    ? (r.resolution_blockers as string[]).join(', ')
    : '';
  const base = String(r.reason ?? '');
  return blockers ? `${base} · ${blockers}` : base;
}

function isProvisionalCustomerReadyWithUnassignedGeo(r: Record<string, unknown>): boolean {
  const act = String(r.suggested_action ?? '');
  if (act !== 'create_provisional_customer' || r.ready !== true) return false;
  const er = r.effective_region_id;
  const ec = r.effective_channel_id;
  return er == null || er === '' || ec == null || ec === '';
}

function rawSamplesLine(c: DsiCandidateRow | undefined): string {
  if (!c?.sample_raw_values?.length) return '';
  return c.sample_raw_values.filter(Boolean).join('; ');
}

function customerAccountLine(c: DsiCandidateRow | undefined): string {
  if (!c) return '';
  const ctx = c.context;
  const dg =
    (ctx && typeof ctx.dealer_group_account_raw === 'string' && ctx.dealer_group_account_raw.trim()) ||
    (c.dealer_group_token && String(c.dealer_group_token).trim()) ||
    '';
  return dg || '—';
}

function planProvisionalGeoSummary(r: Record<string, unknown>): string {
  const rc = r.effective_region_code;
  const rn = r.effective_region_name;
  const cc = r.effective_channel_code;
  const cn = r.effective_channel_name;
  const rid = r.effective_region_id;
  const cid = r.effective_channel_id;
  const reg =
    typeof rc === 'string' && rc.trim()
      ? `${rc}${typeof rn === 'string' && rn.trim() ? ` — ${rn}` : ''}`
      : rid == null || rid === ''
        ? 'Region: unassigned'
        : `Region id ${String(rid)}`;
  const ch =
    typeof cc === 'string' && cc.trim()
      ? `${cc}${typeof cn === 'string' && cn.trim() ? ` — ${cn}` : ''}`
      : cid == null || cid === ''
        ? 'Channel: unassigned'
        : `Channel id ${String(cid)}`;
  return `${reg}; ${ch}`;
}

function dsiSourceRegionChannelLines(ctx: Record<string, unknown> | null | undefined): { region: string; channel: string } {
  if (!ctx) return { region: '', channel: '' };
  const rs = ctx.source_region_raw_samples;
  const cs = ctx.source_channel_raw_samples;
  const region =
    Array.isArray(rs) && rs.length
      ? rs.filter((x): x is string => typeof x === 'string' && x.trim().length > 0).join('; ')
      : '';
  const channel =
    Array.isArray(cs) && cs.length
      ? cs.filter((x): x is string => typeof x === 'string' && x.trim().length > 0).join('; ')
      : '';
  return { region, channel };
}

function planCatalogChannelCell(
  r: Record<string, unknown> | undefined,
  ctx: Record<string, unknown> | null | undefined
): string {
  if (!r) return '';
  const sid = r.suggested_channel_id;
  const cc = r.suggested_channel_code;
  const cn = r.suggested_channel_name;
  if (sid != null && sid !== '') {
    if (typeof cc === 'string' && cc.trim())
      return `${cc.trim()}${typeof cn === 'string' && cn.trim() ? ` — ${cn.trim()}` : ''}`;
    return `id ${String(sid)}`;
  }
  const srcCh = dsiSourceRegionChannelLines(ctx ?? null).channel;
  if (srcCh) return 'No catalog mapping';
  return '';
}

function planGeoReadinessHint(
  r: Record<string, unknown> | undefined,
  ctx: Record<string, unknown> | null | undefined
): string {
  if (!r) return '';
  const act = String(r.suggested_action ?? '');
  if (act !== 'create_provisional_customer' || r.ready !== true) return '';
  const { region: srcRg, channel: srcCh } = dsiSourceRegionChannelLines(ctx ?? null);
  const er = r.effective_region_id;
  const ec = r.effective_channel_id;
  const resCh = r.suggested_channel_id != null && r.suggested_channel_id !== '';
  const ufc = r.used_global_fallback_channel === true;
  const ufr = r.used_global_fallback_region === true;
  const parts: string[] = [];
  if (er == null || er === '') {
    parts.push(srcRg.trim() ? 'Rg unresolved' : 'Rg unassigned');
  } else if (ufr) {
    parts.push('Rg fallback');
  }
  if (ec == null || ec === '') {
    parts.push(srcCh.trim() ? 'Ch unmapped' : 'Ch unassigned');
  } else if (!resCh && ufc) {
    parts.push('Ch fallback');
  }
  return parts.join(' · ');
}

function summarizeApplyAllReadyProvisional(rows: Array<Record<string, unknown>>): {
  provisionalCustomerReady: number;
  unassignedGeoReady: number;
  fallbackGeoReady: number;
} {
  let provisionalCustomerReady = 0;
  let unassignedGeoReady = 0;
  let fallbackGeoReady = 0;
  for (const r of rows) {
    if (r.ready !== true) continue;
    if (String(r.suggested_action ?? '') !== 'create_provisional_customer') continue;
    provisionalCustomerReady += 1;
    if (isProvisionalCustomerReadyWithUnassignedGeo(r)) unassignedGeoReady += 1;
    if (r.used_global_fallback_channel === true || r.used_global_fallback_region === true) fallbackGeoReady += 1;
  }
  return { provisionalCustomerReady, unassignedGeoReady, fallbackGeoReady };
}

function planProvisionalGeoNarrative(r: Record<string, unknown>): ReactNode {
  const et = String(r.entity_type ?? '');
  const act = String(r.suggested_action ?? '');
  if (et !== 'customer_dealer_token' || act !== 'create_provisional_customer') return null;
  const sr = r.source_region_resolution_message;
  const sc = r.source_channel_resolution_message;
  const ufr = r.used_global_fallback_region === true;
  const ufc = r.used_global_fallback_channel === true;
  if (!sr && !sc && !ufr && !ufc) return null;
  return (
    <Stack spacing={0.5} sx={{ mt: 0.75 }}>
      <Typography variant="caption" color="text.secondary">
        Region / channel (source-first)
      </Typography>
      {typeof sr === 'string' && sr.trim() ? (
        <Typography variant="body2" sx={{ wordBreak: 'break-word' }}>
          {sr.trim()}
        </Typography>
      ) : null}
      {typeof sc === 'string' && sc.trim() ? (
        <Typography variant="body2" sx={{ wordBreak: 'break-word' }}>
          {sc.trim()}
        </Typography>
      ) : null}
      {ufr || ufc ? (
        <Typography variant="caption" color="warning.main" display="block">
          {ufr ? 'Global fallback applied for region (source missing/unresolved).' : null}
          {ufr && ufc ? ' ' : null}
          {ufc ? 'Global fallback applied for channel (source missing/unresolved).' : null}
        </Typography>
      ) : null}
    </Stack>
  );
}

function planTargetSummary(
  action: string,
  targetId: unknown,
  c: DsiCandidateRow | undefined,
  planRow?: Record<string, unknown>
): string {
  if (targetId == null || targetId === '') {
    if (action === 'create_provisional_customer') {
      return planRow ? planProvisionalGeoSummary(planRow) : 'New provisional (per steward rules)';
    }
    if (action === 'create_provisional_distributor') {
      return 'New provisional (per steward rules)';
    }
    if (action === 'ignore') return '—';
    return 'Set target ID';
  }
  const id = String(targetId);
  if (action === 'map_customer') return `Customer master · id ${id}`;
  if (action === 'map_distributor') return `Distributor master · id ${id}`;
  if (action === 'resolve_product') {
    const pm = c ? dsiProductMatchSummaryCell(c.context) : '';
    return pm ? `Product id ${id} · ${pm}` : `Product master · id ${id}`;
  }
  return `Id ${id}`;
}

type PlanDialogRowDetailProps = {
  r: Record<string, unknown>;
  candidate: DsiCandidateRow | undefined;
  regions: CatalogOpt[];
  channels: CatalogOpt[];
  planOverrideMap: Record<number, PlanRowOverride>;
  patchPlanOverride: (candidateId: number, patch: PlanRowOverride) => void;
};

function PlanDialogRowDetail({
  r,
  candidate: cand,
  regions,
  channels,
  planOverrideMap,
  patchPlanOverride,
}: PlanDialogRowDetailProps) {
  const id = Number(r.candidate_id);
  const et = String(r.entity_type ?? '');
  const actions = allowedOverrideActions(et);
  const strategicHint = String(r.reason ?? '').toLowerCase().includes('strategic');
  const blockers = Array.isArray(r.resolution_blockers)
    ? (r.resolution_blockers as string[]).join(', ')
    : '';
  const actionEff = String(r.suggested_action ?? '');
  const baselineAct = String(r.baseline_suggested_action ?? actionEff);
  const ready = r.ready === true;

  return (
    <Stack spacing={2} data-testid="dsi-resolution-plan-row-detail">
      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
        <Typography variant="subtitle2">Candidate #{id}</Typography>
        {ready ? (
          <Chip size="small" color="success" label="Ready" data-testid="dsi-plan-detail-ready" />
        ) : (
          <Chip size="small" color="default" label="Not ready" />
        )}
        {isProvisionalCustomerReadyWithUnassignedGeo(r) ? (
          <Chip
            size="small"
            color="warning"
            variant="outlined"
            label="Ready with unassigned geo/channel"
            data-testid="dsi-plan-unassigned-geo-badge"
          />
        ) : null}
      </Stack>

      <Stack spacing={1}>
        <Typography variant="caption" color="text.secondary">
          Source evidence
        </Typography>
        <Stack spacing={0.75}>
          <Typography variant="caption" color="text.secondary">
            Raw from file
          </Typography>
          <Typography variant="body2">{rawSamplesLine(cand) || '—'}</Typography>
          {et === 'customer_dealer_token' ? (
            <>
              <Typography variant="caption" color="text.secondary">
                Customer account
              </Typography>
              <Typography variant="body2">{customerAccountLine(cand)}</Typography>
              <Typography variant="caption" color="text.secondary">
                Source customer name
              </Typography>
              <Typography variant="body2">{dsiSourceCustomerNameCell(cand?.context ?? null) || '—'}</Typography>
              {(() => {
                const { region, channel } = dsiSourceRegionChannelLines(cand?.context ?? null);
                return (
                  <>
                    <Typography variant="caption" color="text.secondary">
                      Source region / province
                    </Typography>
                    <Typography variant="body2">{region || '—'}</Typography>
                    <Typography variant="caption" color="text.secondary">
                      Source channel / route-to-market
                    </Typography>
                    <Typography variant="body2">{channel || '—'}</Typography>
                  </>
                );
              })()}
            </>
          ) : null}
          {et === 'distributor_token' ? (
            <Typography variant="caption" color="text.secondary">
              Normalized key: {String(r.normalized_key ?? '')}
            </Typography>
          ) : null}
          {et === 'product_identifier' ? (
            <>
              <Typography variant="caption" color="text.secondary">
                Product match summary
              </Typography>
              <Typography variant="body2">{dsiProductMatchSummaryCell(cand?.context ?? null) || '—'}</Typography>
            </>
          ) : null}
        </Stack>
      </Stack>

      <Stack spacing={0.75}>
        <Typography variant="caption" color="text.secondary">
          Plan suggestion
        </Typography>
        <Typography variant="caption" color="text.secondary">
          Auto
        </Typography>
        <Typography variant="body2">{formatPlanActionLabel(baselineAct)}</Typography>
        <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block' }}>
          Effective
        </Typography>
        <Typography variant="body2">{formatPlanActionLabel(actionEff)}</Typography>
        <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block' }}>
          Target / proposed
        </Typography>
        <Typography variant="body2">{planTargetSummary(actionEff, r.suggested_target_id, cand, r)}</Typography>
        {r.suggested_target_id != null && r.suggested_target_id !== '' ? (
          <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
            Master id: {String(r.suggested_target_id)}
          </Typography>
        ) : null}
        {planProvisionalGeoNarrative(r)}
        {et === 'customer_dealer_token' ? (
          <Stack spacing={0.5} sx={{ mt: 0.75 }}>
            <Typography variant="caption" color="text.secondary">
              Governed catalog channel (plan)
            </Typography>
            <Typography variant="body2">
              {typeof r.suggested_channel_code === 'string' && r.suggested_channel_code.trim()
                ? `${r.suggested_channel_code.trim()}${
                    typeof r.suggested_channel_name === 'string' && r.suggested_channel_name.trim()
                      ? ` — ${r.suggested_channel_name.trim()}`
                      : ''
                  }`
                : '— (not resolved from source)'}
            </Typography>
            {typeof r.source_channel_resolution_detail === 'string' && r.source_channel_resolution_detail ? (
              <Typography variant="caption" color="text.secondary" data-testid="dsi-plan-detail-channel-resolution-detail">
                Resolution path: {r.source_channel_resolution_detail}
              </Typography>
            ) : null}
          </Stack>
        ) : null}
        <Typography variant="caption" color="text.secondary" sx={{ mt: 0.75, display: 'block' }}>
          Why
        </Typography>
        <Typography variant="body2" sx={{ wordBreak: 'break-word' }}>
          {String(r.reason ?? '')}
          {blockers ? ` · ${blockers}` : ''}
        </Typography>
        {typeof r.confidence === 'number' ? (
          <Typography variant="caption" color="text.secondary">
            Confidence {r.confidence.toFixed(2)}
          </Typography>
        ) : null}
      </Stack>

      <Stack spacing={1.25} alignItems="stretch">
        <Typography variant="subtitle2">Overrides</Typography>
        {actions.length ? (
          <FormControl size="small" fullWidth>
            <InputLabel id={`plan-act-${id}`}>Action</InputLabel>
            <Select
              labelId={`plan-act-${id}`}
              label="Action"
              value={actionEff}
              onChange={(e) => patchPlanOverride(id, { action: String(e.target.value) })}
              data-testid={`dsi-plan-action-${id}`}
            >
              {actions.map((a) => (
                <MenuItem key={a} value={a}>
                  {formatPlanActionLabel(a)}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        ) : null}
        <TextField
          size="small"
          fullWidth
          type="number"
          label="Map / resolve master id"
          helperText="Numeric id only; names show in Target when known from the grid"
          value={r.suggested_target_id != null ? String(r.suggested_target_id) : ''}
          onChange={(e) => {
            const v = e.target.value;
            if (v === '') {
              patchPlanOverride(id, { target_id: null });
              return;
            }
            const n = Number(v);
            patchPlanOverride(id, { target_id: Number.isFinite(n) ? n : null });
          }}
          inputProps={{ 'data-testid': `dsi-plan-target-${id}` }}
        />
        {et === 'customer_dealer_token' && actionEff === 'create_provisional_customer' ? (
          <Stack spacing={1}>
            <Typography variant="caption" color="text.secondary">
              Catalog row override (optional — use when blocked for mixed source evidence or to pick a specific{' '}
              <strong>dim_region</strong> / <strong>dim_channel</strong> for an unresolved file token)
            </Typography>
            <FormControl size="small" fullWidth>
              <InputLabel id={`plan-or-r-${id}`}>Region override</InputLabel>
              <Select
                labelId={`plan-or-r-${id}`}
                label="Region override"
                value={planOverrideMap[id]?.region_id != null ? String(planOverrideMap[id].region_id) : ''}
                displayEmpty
                renderValue={(sel) => {
                  if (sel === '') {
                    const er = r.effective_region_id;
                    const ec = r.effective_region_code;
                    const en = r.effective_region_name;
                    if (er != null && er !== '')
                      return ec ? `${String(ec)}${en ? ` — ${String(en)}` : ''} (plan)` : `id ${String(er)} (plan)`;
                    return 'Plan effective: unassigned';
                  }
                  const hit = regions.find((x) => String(x.id) === sel);
                  return hit ? `${hit.code} — ${hit.name}` : String(sel);
                }}
                onChange={(e) => {
                  const v = String(e.target.value);
                  if (v === '') patchPlanOverride(id, { region_id: null });
                  else patchPlanOverride(id, { region_id: Number(v) });
                }}
                inputProps={{ 'data-testid': `dsi-plan-region-override-${id}` }}
              >
                <MenuItem value="">
                  <em>Use plan effective</em>
                </MenuItem>
                {regions.map((reg) => (
                  <MenuItem key={reg.id} value={String(reg.id)}>
                    {reg.code} — {reg.name}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <FormControl size="small" fullWidth>
              <InputLabel id={`plan-or-c-${id}`}>Channel override</InputLabel>
              <Select
                labelId={`plan-or-c-${id}`}
                label="Channel override"
                value={planOverrideMap[id]?.channel_id != null ? String(planOverrideMap[id].channel_id) : ''}
                displayEmpty
                renderValue={(sel) => {
                  if (sel === '') {
                    const er = r.effective_channel_id;
                    const ec = r.effective_channel_code;
                    const en = r.effective_channel_name;
                    if (er != null && er !== '')
                      return ec ? `${String(ec)}${en ? ` — ${String(en)}` : ''} (plan)` : `id ${String(er)} (plan)`;
                    return 'Plan effective: unassigned';
                  }
                  const hit = channels.find((x) => String(x.id) === sel);
                  return hit ? `${hit.code} — ${hit.name}` : String(sel);
                }}
                onChange={(e) => {
                  const v = String(e.target.value);
                  if (v === '') patchPlanOverride(id, { channel_id: null });
                  else patchPlanOverride(id, { channel_id: Number(v) });
                }}
                inputProps={{ 'data-testid': `dsi-plan-channel-override-${id}` }}
              >
                <MenuItem value="">
                  <em>Use plan effective</em>
                </MenuItem>
                {channels.map((ch) => (
                  <MenuItem key={ch.id} value={String(ch.id)}>
                    {ch.code} — {ch.name}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Stack>
        ) : null}
        <FormControlLabel
          control={
            <Checkbox
              size="small"
              checked={r.hold_for_manual_review === true}
              onChange={(e) => patchPlanOverride(id, { hold_for_manual_review: e.target.checked })}
              inputProps={{ 'data-testid': `dsi-plan-hold-${id}` }}
            />
          }
          label="Hold (skip in apply)"
        />
        {et === 'distributor_token' ? (
          <FormControlLabel
            control={
              <Checkbox
                size="small"
                checked={planOverrideMap[id]?.confirm_for_suspicious_distributor_token === true}
                onChange={(e) =>
                  patchPlanOverride(id, {
                    confirm_for_suspicious_distributor_token: e.target.checked,
                  })
                }
                inputProps={{ 'data-testid': `dsi-plan-dist-confirm-${id}` }}
              />
            }
            label="Confirm placeholder-like distributor token"
          />
        ) : null}
        {et === 'product_identifier' ? (
          <Stack spacing={1}>
            <FormControlLabel
              control={
                <Checkbox
                  size="small"
                  checked={planOverrideMap[id]?.confirm_ineligible_product === true}
                  onChange={(e) => patchPlanOverride(id, { confirm_ineligible_product: e.target.checked })}
                />
              }
              label="Confirm inactive / ineligible product"
            />
            <TextField
              size="small"
              fullWidth
              label="Audit note (≥8 chars if confirming)"
              value={planOverrideMap[id]?.audit_note ?? ''}
              onChange={(e) => patchPlanOverride(id, { audit_note: e.target.value })}
              data-testid={`dsi-plan-product-audit-${id}`}
            />
          </Stack>
        ) : null}
        {et === 'customer_dealer_token' && strategicHint ? (
          <FormControlLabel
            control={
              <Checkbox
                size="small"
                checked={planOverrideMap[id]?.ack_strategic_channel_hint === true}
                onChange={(e) => patchPlanOverride(id, { ack_strategic_channel_hint: e.target.checked })}
                inputProps={{ 'data-testid': `dsi-plan-strategic-${id}` }}
              />
            }
            label="Acknowledge strategic / marketplace evidence"
          />
        ) : null}
      </Stack>
    </Stack>
  );
}

const PLAN_REVIEW_FILTER_CHIPS: { value: PlanReviewFilter; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'ready', label: 'Ready' },
  { value: 'needs_work', label: 'Needs work' },
  { value: 'customer', label: 'Customer' },
  { value: 'distributor', label: 'Distributor' },
  { value: 'product', label: 'Product' },
  { value: 'provisional', label: 'Create provisional' },
  { value: 'map_resolve', label: 'Map / resolve' },
  { value: 'ignore', label: 'Ignore' },
  { value: 'manual', label: 'Manual / blocked' },
];

export function DsiImportJobResolutionSection({
  importJobId,
  candidates,
  onInvalidate,
}: {
  importJobId: number;
  candidates: DsiCandidateRow[];
  onInvalidate: () => void;
}) {
  const qc = useQueryClient();
  const gridRef = useRef<AgGridReact<DsiCandidateRow> | null>(null);
  const [detailCandidate, setDetailCandidate] = useState<DsiCandidateRow | null>(null);

  const [bulkMode, setBulkMode] = useState<BulkTableSelectionMode>('normal');
  const [selectedIds, setSelectedIds] = useState<number[]>([]);

  const [bulkAction, setBulkAction] = useState<BulkAction>('ignore');
  const [bulkNotes, setBulkNotes] = useState('');
  const [bulkCustomerId, setBulkCustomerId] = useState('');
  const [bulkDistributorId, setBulkDistributorId] = useState('');
  const [bulkProductId, setBulkProductId] = useState('');
  const [bulkRawToken, setBulkRawToken] = useState('');
  const [bulkConfirmIneligible, setBulkConfirmIneligible] = useState(false);
  const [bulkAuditNote, setBulkAuditNote] = useState('');

  const [bulkRegionId, setBulkRegionId] = useState('');
  const [bulkChannelId, setBulkChannelId] = useState('');
  const [bulkPreferredDistributorId, setBulkPreferredDistributorId] = useState('');
  const [bulkPartnerTier, setBulkPartnerTier] = useState('unmanaged');
  const [bulkProvisionalNotes, setBulkProvisionalNotes] = useState('');
  const [bulkDistSuspiciousOk, setBulkDistSuspiciousOk] = useState(false);
  const [bulkProvisionalDistCode, setBulkProvisionalDistCode] = useState('');

  const [bulkApplySummary, setBulkApplySummary] = useState<string | null>(null);

  const [planRegionId, setPlanRegionId] = useState('');
  const [planChannelId, setPlanChannelId] = useState('');
  const [resolutionPlan, setResolutionPlan] = useState<Record<string, unknown> | null>(null);
  const [suggestionDrawerId, setSuggestionDrawerId] = useState<number | null>(null);
  const [planOverrideMap, setPlanOverrideMap] = useState<Record<number, PlanRowOverride>>({});
  const [planGlobalSuspicious, setPlanGlobalSuspicious] = useState(false);
  const planDebounceSkipRef = useRef(false);
  /** Non-zero while a generated plan session is active (avoids effect deps on resolutionPlan object). */
  const [planLoadToken, setPlanLoadToken] = useState(0);
  const [planReviewFilter, setPlanReviewFilter] = useState<PlanReviewFilter>('all');
  const [applyAllConfirmOpen, setApplyAllConfirmOpen] = useState(false);

  const { data: regions = [] } = useQuery({
    queryKey: ['catalog-regions'],
    queryFn: ({ signal }) => apiGet<CatalogOpt[]>('/api/v1/catalog/regions', { signal }),
  });
  const { data: channels = [] } = useQuery({
    queryKey: ['catalog-channels'],
    queryFn: ({ signal }) => apiGet<CatalogOpt[]>('/api/v1/catalog/channels', { signal }),
  });

  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewData, setPreviewData] = useState<BulkPreviewResponse | null>(null);
  const [previewApplyToken, setPreviewApplyToken] = useState<string | null>(null);

  const buildBulkBody = useCallback(() => {
    const ids = [...selectedIds];
    const base: Record<string, unknown> = {
      action: bulkAction,
      candidate_ids: ids,
    };
    if (bulkAction === 'ignore') {
      base.notes = bulkNotes.trim() || null;
    }
    if (bulkAction === 'map_customer') {
      base.customer_id = Number(bulkCustomerId);
      base.raw_token = bulkRawToken.trim() || null;
    }
    if (bulkAction === 'map_distributor') {
      base.distributor_id = Number(bulkDistributorId);
      base.raw_token = bulkRawToken.trim() || null;
    }
    if (bulkAction === 'resolve_product') {
      base.product_id = Number(bulkProductId);
      base.raw_token = bulkRawToken.trim() || null;
      base.confirm_ineligible_product = bulkConfirmIneligible;
      base.audit_note = bulkAuditNote.trim() || null;
    }
    if (bulkAction === 'create_provisional_customer') {
      const r = bulkRegionId.trim();
      const c = bulkChannelId.trim();
      base.region_id = r !== '' && Number.isFinite(Number(r)) ? Number(r) : null;
      base.channel_id = c !== '' && Number.isFinite(Number(c)) ? Number(c) : null;
      base.partner_tier = bulkPartnerTier.trim() || 'unmanaged';
      base.provisional_notes_summary = bulkProvisionalNotes.trim() || null;
      const pd = bulkPreferredDistributorId.trim();
      base.preferred_distributor_id = pd !== '' && Number.isFinite(Number(pd)) ? Number(pd) : null;
    }
    if (bulkAction === 'create_provisional_distributor') {
      base.confirm_for_suspicious_distributor_token = bulkDistSuspiciousOk;
      base.provisional_distributor_code = bulkProvisionalDistCode.trim() || null;
    }
    return base;
  }, [
    selectedIds,
    bulkAction,
    bulkNotes,
    bulkCustomerId,
    bulkDistributorId,
    bulkProductId,
    bulkRawToken,
    bulkConfirmIneligible,
    bulkAuditNote,
    bulkRegionId,
    bulkChannelId,
    bulkPreferredDistributorId,
    bulkPartnerTier,
    bulkProvisionalNotes,
    bulkDistSuspiciousOk,
    bulkProvisionalDistCode,
  ]);

  const previewToken = useMemo(() => JSON.stringify(buildBulkBody()), [buildBulkBody]);

  const bulkFormReady = useMemo(() => {
    if (bulkAction === 'ignore') return true;
    if (bulkAction === 'map_customer') {
      return bulkCustomerId.trim() !== '' && Number.isFinite(Number(bulkCustomerId));
    }
    if (bulkAction === 'map_distributor') {
      return bulkDistributorId.trim() !== '' && Number.isFinite(Number(bulkDistributorId));
    }
    if (bulkAction === 'resolve_product') {
      const pid = bulkProductId.trim();
      if (!pid || !Number.isFinite(Number(pid))) return false;
      if (bulkConfirmIneligible && bulkAuditNote.trim().length < 8) return false;
      return true;
    }
    if (bulkAction === 'create_provisional_customer') {
      return true;
    }
    if (bulkAction === 'create_provisional_distributor') {
      return true;
    }
    return false;
  }, [
    bulkAction,
    bulkCustomerId,
    bulkDistributorId,
    bulkProductId,
    bulkConfirmIneligible,
    bulkAuditNote,
    bulkRegionId,
    bulkChannelId,
  ]);

  const bulkPreview = useMutation({
    mutationFn: async () => {
      const body = buildBulkBody();
      return apiPost<BulkPreviewResponse>(
        `/api/v1/mappings/import-jobs/${importJobId}/dsi-steward-bulk-preview`,
        body
      );
    },
    onSuccess: (data) => {
      setBulkApplySummary(null);
      setPreviewData(data);
      setPreviewApplyToken(previewToken);
      setPreviewOpen(true);
    },
  });

  const bulkApply = useMutation({
    mutationFn: async () => {
      const body = buildBulkBody();
      return apiPost<BulkApplyResponse>(
        `/api/v1/mappings/import-jobs/${importJobId}/dsi-steward-bulk-apply`,
        body
      );
    },
    onSuccess: (data) => {
      setBulkApplySummary(
        `Bulk steward: applied ${data.applied}, failed ${data.failed}. Re-run import validation (server) when ready.`
      );
      setPreviewOpen(false);
      setPreviewData(null);
      setPreviewApplyToken(null);
      setBulkMode('normal');
      gridRef.current?.api?.deselectAll();
      setSelectedIds([]);
      qc.invalidateQueries({ queryKey: ['distributor-si-candidates', importJobId] });
      qc.invalidateQueries({ queryKey: ['import-job-rows', importJobId] });
      qc.invalidateQueries({ queryKey: ['import-jobs'] });
      void qc.invalidateQueries({ queryKey: ['dsi-resolution-suggestions', importJobId] });
      onInvalidate();
    },
  });

  const dsiRevalidateFromServer = useMutation({
    mutationFn: async () =>
      apiPost<{ ok: boolean }>(
        `/api/v1/mappings/import-jobs/${importJobId}/revalidate-distributor-sales-inventory`,
        {}
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['dsi-resolution-suggestions', importJobId] });
      void qc.invalidateQueries({ queryKey: ['distributor-si-candidates', importJobId] });
      void qc.invalidateQueries({ queryKey: ['import-job-rows', importJobId] });
      void qc.invalidateQueries({ queryKey: ['import-jobs'] });
      onInvalidate();
    },
  });

  const planDefaultsBody = useCallback(
    () => ({
      default_region_id:
        planRegionId.trim() !== '' && Number.isFinite(Number(planRegionId)) ? Number(planRegionId) : null,
      default_channel_id:
        planChannelId.trim() !== '' && Number.isFinite(Number(planChannelId)) ? Number(planChannelId) : null,
    }),
    [planRegionId, planChannelId]
  );

  const candidateIdsKey = useMemo(
    () =>
      [...candidates]
        .map((c) => c.id)
        .sort((a, b) => a - b)
        .join(','),
    [candidates]
  );

  const suggestionsQuery = useQuery({
    queryKey: ['dsi-resolution-suggestions', importJobId, candidateIdsKey, planRegionId, planChannelId],
    enabled: importJobId > 0 && candidates.length > 0,
    refetchOnWindowFocus: false,
    queryFn: ({ signal }) =>
      apiPost<Record<string, unknown>>(
        `/api/v1/mappings/import-jobs/${importJobId}/dsi-resolution-plan`,
        planDefaultsBody(),
        { signal }
      ),
  });

  useEffect(() => {
    if (!suggestionsQuery.data) return;
    planDebounceSkipRef.current = true;
    setPlanOverrideMap({});
    setPlanGlobalSuspicious(false);
    setResolutionPlan(suggestionsQuery.data);
    setPlanLoadToken((n) => n + 1);
  }, [suggestionsQuery.data]);

  const overridesPayload = useCallback((): Array<Record<string, unknown>> => {
    return Object.entries(planOverrideMap).map(([cid, o]) => ({
      candidate_id: Number(cid),
      ...o,
    }));
  }, [planOverrideMap]);

  const patchPlanOverride = useCallback((candidateId: number, patch: PlanRowOverride) => {
    setPlanOverrideMap((m) => ({
      ...m,
      [candidateId]: { ...m[candidateId], ...patch },
    }));
  }, []);

  const refreshPlanEffective = useMutation({
    mutationFn: async (args: { overrides: Array<Record<string, unknown>>; globalSuspicious: boolean }) =>
      apiPost<Record<string, unknown>>(`/api/v1/mappings/import-jobs/${importJobId}/dsi-resolution-plan/effective`, {
        ...planDefaultsBody(),
        confirm_for_suspicious_distributor_token: args.globalSuspicious,
        overrides: args.overrides,
      }),
    onSuccess: (data) => {
      setResolutionPlan(data);
    },
  });

  const refreshEffectiveAsyncRef = useRef(refreshPlanEffective.mutateAsync);
  refreshEffectiveAsyncRef.current = refreshPlanEffective.mutateAsync;

  useEffect(() => {
    if (planLoadToken === 0) return;
    if (planDebounceSkipRef.current) {
      planDebounceSkipRef.current = false;
      return;
    }
    const ovList = Object.entries(planOverrideMap).map(([cid, o]) => ({
      candidate_id: Number(cid),
      ...o,
    }));
    const t = window.setTimeout(() => {
      void refreshEffectiveAsyncRef
        .current({ overrides: ovList, globalSuspicious: planGlobalSuspicious })
        .catch(() => {});
    }, 450);
    return () => window.clearTimeout(t);
  }, [planOverrideMap, planGlobalSuspicious, planLoadToken]);

  const applyResolutionPlan = useMutation({
    mutationFn: async (args: {
      candidateIds: number[];
      overrides: Array<Record<string, unknown>>;
      globalSuspicious: boolean;
    }) =>
      apiPost<Record<string, unknown>>(`/api/v1/mappings/import-jobs/${importJobId}/dsi-resolution-plan/apply`, {
        candidate_ids: args.candidateIds,
        ...planDefaultsBody(),
        partner_tier: 'unmanaged',
        provisional_notes_summary: null,
        confirm_for_suspicious_distributor_token: args.globalSuspicious,
        overrides: args.overrides.length ? args.overrides : null,
      }),
    onSuccess: (data) => {
      const applied = Number(data.applied ?? 0);
      const failed = Number(data.failed ?? 0);
      const skippedHold = Number(data.skipped_hold ?? 0);
      const skippedNr = Number(data.skipped_not_ready ?? 0);
      setBulkApplySummary(
        `Resolution plan: applied ${applied}, failed ${failed}, skipped (hold) ${skippedHold}, skipped (not ready) ${skippedNr}. Re-run import validation (server) when ready.`
      );
      setSuggestionDrawerId(null);
      setResolutionPlan(null);
      setPlanOverrideMap({});
      setPlanGlobalSuspicious(false);
      setPlanLoadToken(0);
      setPlanReviewFilter('all');
      void qc.invalidateQueries({ queryKey: ['dsi-resolution-suggestions', importJobId] });
      void qc.invalidateQueries({ queryKey: ['distributor-si-candidates', importJobId] });
      void qc.invalidateQueries({ queryKey: ['import-job-rows', importJobId] });
      void qc.invalidateQueries({ queryKey: ['import-jobs'] });
      gridRef.current?.api?.deselectAll();
      setSelectedIds([]);
      onInvalidate();
    },
  });

  const planTableRows = useMemo(() => {
    const raw = resolutionPlan?.rows;
    if (!raw || !Array.isArray(raw)) return [];
    return raw as Array<Record<string, unknown>>;
  }, [resolutionPlan]);

  const applyAllProvisionalStats = useMemo(
    () => summarizeApplyAllReadyProvisional(planTableRows),
    [planTableRows]
  );

  const filteredPlanCount = useMemo(() => {
    if (planTableRows.length === 0) return 0;
    return planTableRows.filter((r) => planRowMatchesReviewFilter(r, planReviewFilter)).length;
  }, [planTableRows, planReviewFilter]);

  const planByCandidateId = useMemo(() => {
    const m = new Map<number, Record<string, unknown>>();
    for (const r of planTableRows) {
      const id = Number(r.candidate_id);
      if (Number.isFinite(id)) m.set(id, r);
    }
    return m;
  }, [planTableRows]);

  const displayedCandidates = useMemo(() => {
    if (suggestionsQuery.isPending && planTableRows.length === 0) return candidates;
    if (planReviewFilter === 'all') return candidates;
    return candidates.filter((c) => {
      const r = planByCandidateId.get(c.id);
      if (!r) return false;
      return planRowMatchesReviewFilter(r, planReviewFilter);
    });
  }, [candidates, planByCandidateId, planReviewFilter, planTableRows.length, suggestionsQuery.isPending]);

  const readyPlanCandidateIds = useMemo(() => {
    return planTableRows
      .filter((r) => r.ready === true)
      .map((r) => Number(r.candidate_id))
      .filter((id) => Number.isFinite(id));
  }, [planTableRows]);

  const selectedReadyPlanIds = useMemo(() => {
    const ready = new Set(readyPlanCandidateIds);
    return selectedIds.filter((id) => ready.has(id));
  }, [selectedIds, readyPlanCandidateIds]);

  const planDrawerRow = useMemo(() => {
    if (suggestionDrawerId == null) return null;
    return planTableRows.find((r) => Number(r.candidate_id) === suggestionDrawerId) ?? null;
  }, [planTableRows, suggestionDrawerId]);

  const handleOpenSuggestionRow = useCallback((id: number | undefined) => {
    if (id != null) setSuggestionDrawerId(id);
  }, []);

  const selectVisibleReadyInGrid = useCallback(() => {
    const api = gridRef.current?.api;
    if (!api) return;
    api.deselectAll();
    api.forEachNode((node) => {
      const row = node.data as DsiCandidateRow | undefined;
      const rid = row?.id;
      if (rid == null) return;
      const pr = planByCandidateId.get(rid);
      if (pr?.ready === true) node.setSelected(true);
    });
  }, [planByCandidateId]);

  const candidatesById = useMemo(() => {
    const m: Record<number, DsiCandidateRow> = {};
    for (const c of candidates) m[c.id] = c;
    return m;
  }, [candidates]);

  const colDefs = useMemo<ColDef<DsiCandidateRow>[]>(
    () => [
      {
        headerName: 'Open',
        colId: 'dsi_suggest_open',
        width: 88,
        sortable: false,
        filter: false,
        pinned: 'left',
        cellRenderer: (p: ICellRendererParams<DsiCandidateRow, unknown, { openSuggestionDetail?: (id: number) => void }>) => (
          <Button
            size="small"
            variant="outlined"
            data-testid={`dsi-suggestion-open-${p.data?.id ?? 0}`}
            onClick={() => {
              const id = p.data?.id;
              if (id != null) p.context?.openSuggestionDetail?.(id);
            }}
          >
            Open
          </Button>
        ),
      },
      {
        headerName: 'Suggestion',
        colId: 'dsi_suggest_status',
        minWidth: 110,
        valueGetter: (p) => {
          const r = planByCandidateId.get(p.data?.id ?? -1);
          if (!r) return '—';
          return r.ready === true ? 'Ready' : 'Needs work';
        },
      },
      {
        headerName: 'Auto action',
        colId: 'dsi_auto_action',
        minWidth: 130,
        valueGetter: (p) => {
          const r = planByCandidateId.get(p.data?.id ?? -1);
          if (!r) return '';
          const a = String(r.baseline_suggested_action ?? r.suggested_action ?? '');
          return formatPlanActionLabel(a);
        },
      },
      {
        headerName: 'Effective',
        colId: 'dsi_effective_action',
        minWidth: 130,
        valueGetter: (p) => {
          const r = planByCandidateId.get(p.data?.id ?? -1);
          if (!r) return '';
          return formatPlanActionLabel(String(r.suggested_action ?? ''));
        },
      },
      {
        headerName: 'Proposed target',
        colId: 'dsi_proposed_target',
        minWidth: 160,
        valueGetter: (p) => {
          const r = planByCandidateId.get(p.data?.id ?? -1);
          if (!r) return '';
          const c = p.data ? candidatesById[p.data.id] : undefined;
          return truncateEllipsis(
            planTargetSummary(String(r.suggested_action ?? ''), r.suggested_target_id, c, r),
            64
          );
        },
      },
      {
        headerName: 'Reason',
        colId: 'dsi_reason',
        minWidth: 180,
        valueGetter: (p) => {
          const r = planByCandidateId.get(p.data?.id ?? -1);
          if (!r) return '';
          return truncateEllipsis(planReasonSummary(r), 80);
        },
      },
      {
        headerName: 'Geo / defaults',
        colId: 'dsi_geo_hint',
        minWidth: 150,
        valueGetter: (p) => {
          const r = planByCandidateId.get(p.data?.id ?? -1);
          if (!r) return '';
          return planGeoReadinessHint(r, p.data?.context ?? null);
        },
      },
      {
        headerName: 'Conf.',
        colId: 'dsi_plan_conf',
        width: 72,
        valueGetter: (p) => {
          const r = planByCandidateId.get(p.data?.id ?? -1);
          if (!r || typeof r.confidence !== 'number') return '';
          return r.confidence.toFixed(2);
        },
      },
      { field: 'entity_type', headerName: 'Entity type', minWidth: 160 },
      {
        headerName: 'Raw samples',
        minWidth: 160,
        valueGetter: (p) => {
          const s = p.data?.sample_raw_values;
          if (s == null || !Array.isArray(s)) return '';
          return s.filter(Boolean).join('; ');
        },
      },
      { field: 'normalized_key', headerName: 'Normalized', minWidth: 140 },
      { field: 'dealer_group_token', headerName: 'Customer account', minWidth: 120 },
      {
        headerName: 'Source customer',
        minWidth: 140,
        valueGetter: (p) => dsiSourceCustomerNameCell(p.data?.context ?? null),
      },
      {
        headerName: 'Source region (file)',
        minWidth: 130,
        valueGetter: (p) => {
          if (p.data?.entity_type !== 'customer_dealer_token') return '';
          return dsiSourceRegionChannelLines(p.data?.context ?? null).region;
        },
      },
      {
        headerName: 'Source channel (file)',
        minWidth: 140,
        valueGetter: (p) => {
          if (p.data?.entity_type !== 'customer_dealer_token') return '';
          return dsiSourceRegionChannelLines(p.data?.context ?? null).channel;
        },
      },
      {
        headerName: 'Catalog channel',
        colId: 'dsi_catalog_channel',
        minWidth: 150,
        valueGetter: (p) => {
          const r = planByCandidateId.get(p.data?.id ?? -1);
          return planCatalogChannelCell(r, p.data?.context ?? null);
        },
      },
      {
        headerName: 'Product match',
        minWidth: 160,
        valueGetter: (p) => dsiProductMatchSummaryCell(p.data?.context ?? null),
      },
      { field: 'status', headerName: 'Status', width: 110 },
      { field: 'row_count', headerName: 'Rows', width: 80 },
      { field: 'total_units', headerName: 'Units', width: 90 },
      { field: 'total_reported_value', headerName: 'Value', width: 90 },
    ],
    [planByCandidateId, candidatesById]
  );

  const onRowClicked = useCallback((e: RowClickedEvent<DsiCandidateRow>) => {
    if (e.data) setDetailCandidate(e.data);
  }, []);

  const gridOptions = useMemo<GridOptions<DsiCandidateRow>>(
    () => ({
      context: {
        openSuggestionDetail: handleOpenSuggestionRow,
      },
      getRowId: (p) => String(p.data.id),
      rowSelection: {
        mode: 'multiRow',
        checkboxes: true,
        headerCheckbox: true,
        enableClickSelection: false,
      },
      onSelectionChanged: (e) => {
        const rows = e.api.getSelectedRows() as DsiCandidateRow[];
        setSelectedIds(rows.map((r) => r.id));
      },
      onRowClicked,
    }),
    [onRowClicked, handleOpenSuggestionRow]
  );

  const applyReady = previewApplyToken !== null && previewApplyToken === previewToken && previewData !== null;

  return (
    <Paper variant="outlined" sx={{ p: 2 }} data-testid="dsi-import-job-resolution">
      <Stack spacing={2}>
        <Typography variant="subtitle2">Resolve blockers for this import</Typography>
        <Alert severity="info">
          <Typography variant="body2" component="div">
            <strong>Validate → Resolve → Revalidate → Apply</strong>: steward actions call the same APIs as the global{' '}
            <Link component={NextLink} href={`/admin/mappings?import_job_id=${importJobId}`}>
              Mapping queue
            </Link>
            . Click a row for single-row actions; use bulk mode for many candidates.{' '}
            <strong>Map to existing</strong> uses one target ID for all selected rows;{' '}
            <strong>Create provisional</strong> creates one new unverified master per candidate (names derived from the
            same evidence as single-row steward). Preview before apply, then use <strong>Re-run import validation (server)</strong>{' '}
            below when you need staging refreshed.
          </Typography>
        </Alert>

        <Alert severity="info" variant="outlined" data-testid="dsi-resolution-plan-panel">
          <Typography variant="subtitle2" gutterBottom>
            Resolution suggestions (this import only, read-only until you apply)
          </Typography>
          <Alert severity="success" variant="outlined" sx={{ mb: 1.5 }} icon={false}>
            <Typography variant="body2">
              <strong>Source-first:</strong> after <strong>Re-run import validation (server)</strong>, each customer candidate
              gets region / province and channel / route-to-market from your <strong>mapped file columns</strong> (not from
              optional fallbacks unless source values are missing, unresolved, or mixed).
            </Typography>
          </Alert>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
            Suggestions load automatically in the candidate grid. Use row <strong>Open</strong> for full evidence and
            overrides — they stay read-only until you <strong>Apply selected ready</strong> or <strong>Apply all ready</strong>.
            <strong> Refresh suggestions</strong> recomputes the steward plan on the server (read-only, does not re-run import
            validation).
          </Typography>
          <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" alignItems="center" sx={{ mb: 1 }}>
            <Button
              variant="outlined"
              size="small"
              disabled={candidates.length === 0 || suggestionsQuery.isFetching}
              onClick={() => void suggestionsQuery.refetch().catch(() => {})}
              data-testid="dsi-resolution-suggestions-refresh"
            >
              {suggestionsQuery.isFetching ? 'Refreshing…' : 'Refresh suggestions'}
            </Button>
            {resolutionPlan?.summary && typeof resolutionPlan.summary === 'object' ? (
              <>
                <Chip
                  size="small"
                  label={`Candidates ${String((resolutionPlan.summary as Record<string, unknown>).total ?? '—')}`}
                />
                <Chip
                  size="small"
                  color="success"
                  variant="outlined"
                  label={`Ready ${String((resolutionPlan.summary as Record<string, unknown>).ready ?? '—')}`}
                />
                <Chip
                  size="small"
                  color="warning"
                  variant="outlined"
                  label={`Needs work ${String((resolutionPlan.summary as Record<string, unknown>).not_ready ?? '—')}`}
                />
                <Chip
                  size="small"
                  variant="outlined"
                  label={`On hold ${String((resolutionPlan.summary as Record<string, unknown>).hold ?? '—')}`}
                />
              </>
            ) : null}
          </Stack>
          <Accordion
            disableGutters
            elevation={0}
            sx={{ mt: 1.5, border: 1, borderColor: 'divider', borderRadius: 1, '&:before': { display: 'none' } }}
            data-testid="dsi-resolution-plan-fallback-accordion"
          >
            <AccordionSummary expandIcon={<ExpandMoreIcon />}>
              <Typography variant="body2" color="text.secondary">
                Optional global catalog fallbacks (missing / unresolved / mixed source only)
              </Typography>
            </AccordionSummary>
            <AccordionDetails>
              <Stack spacing={1.5}>
                <Alert severity="warning" variant="outlined" icon={false}>
                  <Typography variant="caption" display="block">
                    Lists are the full API catalog (often including demo rows such as NA-E, NA-W, ECOM, RET). They are not
                    applied when the file already supplies a resolvable value. Choose only values that match your DSI
                    geography and channel reality.
                  </Typography>
                </Alert>
                <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems={{ sm: 'flex-start' }} flexWrap="wrap" useFlexGap>
                  <FormControl size="small" sx={{ minWidth: 220 }}>
                    <InputLabel id="dsi-plan-region">Fallback region</InputLabel>
                    <Select
                      labelId="dsi-plan-region"
                      label="Fallback region"
                      value={planRegionId}
                      onChange={(e) => setPlanRegionId(String(e.target.value))}
                    >
                      <MenuItem value="">
                        <em>None</em>
                      </MenuItem>
                      {regions.map((r) => (
                        <MenuItem key={r.id} value={String(r.id)}>
                          {r.code} — {r.name}
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                  <FormControl size="small" sx={{ minWidth: 220 }}>
                    <InputLabel id="dsi-plan-channel">Fallback channel</InputLabel>
                    <Select
                      labelId="dsi-plan-channel"
                      label="Fallback channel"
                      value={planChannelId}
                      onChange={(e) => setPlanChannelId(String(e.target.value))}
                    >
                      <MenuItem value="">
                        <em>None</em>
                      </MenuItem>
                      {channels.map((c) => (
                        <MenuItem key={c.id} value={String(c.id)}>
                          {c.code} — {c.name}
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                </Stack>
              </Stack>
            </AccordionDetails>
          </Accordion>
          <Stack
            direction={{ xs: 'column', md: 'row' }}
            spacing={2}
            alignItems={{ md: 'flex-start' }}
            useFlexGap
            flexWrap="wrap"
            sx={{ mt: 2 }}
          >
            <FormControlLabel
              sx={{ alignItems: 'flex-start', mr: 0, maxWidth: 420 }}
              control={
                <Checkbox
                  checked={planGlobalSuspicious}
                  onChange={(e) => setPlanGlobalSuspicious(e.target.checked)}
                  data-testid="dsi-plan-global-suspicious-confirm"
                />
              }
              label={
                <Typography variant="body2" component="span">
                  Allow provisional <strong>distributor</strong> creates for placeholder-like tokens (e.g. unknown, n/a)
                  for <strong>all rows</strong> in this plan
                </Typography>
              }
            />
            <Button
              variant="outlined"
              size="small"
              disabled={refreshPlanEffective.isPending || planLoadToken === 0}
              onClick={() =>
                void refreshPlanEffective
                  .mutateAsync({
                    overrides: overridesPayload(),
                    globalSuspicious: planGlobalSuspicious,
                  })
                  .catch(() => {})
              }
              data-testid="dsi-resolution-plan-refresh-effective"
            >
              {refreshPlanEffective.isPending ? 'Updating plan…' : 'Update plan after edits'}
            </Button>
          </Stack>
          {planTableRows.some((x) => x.needs_confirm_suspicious_distributor === true) ? (
            <Alert severity="warning" data-testid="dsi-plan-suspicious-hint" sx={{ mt: 1.5 }}>
              Some rows need explicit permission before creating a provisional distributor from a placeholder-like token. Use
              the row override and/or the global option above, then click <strong>Update plan after edits</strong>.
            </Alert>
          ) : null}
          {refreshPlanEffective.isError ? (
            <Alert severity="error" sx={{ mt: 1 }}>
              {safeDisplayError(refreshPlanEffective.error)}
            </Alert>
          ) : null}
        </Alert>

        <Stack spacing={1.5} data-testid="dsi-resolution-inpage-toolbar">
          <Box data-testid="dsi-resolution-plan-filters" sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.75 }}>
            {PLAN_REVIEW_FILTER_CHIPS.map(({ value, label }) => (
              <Chip
                key={value}
                size="small"
                label={label}
                color={planReviewFilter === value ? 'primary' : 'default'}
                variant={planReviewFilter === value ? 'filled' : 'outlined'}
                onClick={() => setPlanReviewFilter(value)}
                data-testid={`dsi-plan-filter-${value}`}
              />
            ))}
          </Box>
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
            <Typography variant="caption" color="text.secondary" data-testid="dsi-resolution-plan-filter-count">
              Filter match {filteredPlanCount} of {planTableRows.length} · Grid rows {displayedCandidates.length} · Ready{' '}
              {readyPlanCandidateIds.length}
            </Typography>
            <Button
              size="small"
              disabled={!displayedCandidates.some((c) => planByCandidateId.get(c.id)?.ready === true)}
              onClick={selectVisibleReadyInGrid}
              data-testid="dsi-plan-select-visible-ready"
            >
              Select visible ready
            </Button>
            <Box sx={{ flexGrow: 1 }} />
            <Button
              variant="outlined"
              size="small"
              disabled={
                selectedReadyPlanIds.length === 0 || applyResolutionPlan.isPending || refreshPlanEffective.isPending
              }
              onClick={() =>
                void applyResolutionPlan
                  .mutateAsync({
                    candidateIds: selectedReadyPlanIds,
                    overrides: overridesPayload(),
                    globalSuspicious: planGlobalSuspicious,
                  })
                  .catch(() => {})
              }
              data-testid="dsi-resolution-plan-apply-selected"
            >
              Apply selected ready ({selectedReadyPlanIds.length})
            </Button>
            <Button
              variant="contained"
              size="small"
              disabled={
                readyPlanCandidateIds.length === 0 || applyResolutionPlan.isPending || refreshPlanEffective.isPending
              }
              onClick={() => {
                const stats = applyAllProvisionalStats;
                const needsDialog =
                  stats.provisionalCustomerReady > 0 &&
                  (stats.provisionalCustomerReady >= 5 ||
                    stats.unassignedGeoReady > 0 ||
                    stats.fallbackGeoReady > 0);
                if (needsDialog) {
                  setApplyAllConfirmOpen(true);
                  return;
                }
                void applyResolutionPlan
                  .mutateAsync({
                    candidateIds: readyPlanCandidateIds,
                    overrides: overridesPayload(),
                    globalSuspicious: planGlobalSuspicious,
                  })
                  .catch(() => {});
              }}
              data-testid="dsi-resolution-plan-apply-all"
            >
              {applyResolutionPlan.isPending ? 'Applying…' : `Apply all ready (${readyPlanCandidateIds.length})`}
            </Button>
          </Stack>
        </Stack>

        {suggestionsQuery.isError ? (
          <Alert severity="error">{safeDisplayError(suggestionsQuery.error)}</Alert>
        ) : null}

        <Box data-testid="dsi-resolution-candidate-grid">
          <EnterpriseDataGrid
            ref={gridRef}
            rowData={displayedCandidates}
            columnDefs={colDefs}
            height={480}
            gridOptions={gridOptions}
          />
        </Box>

        <BulkSelectionToolbar
          mode={bulkMode}
          selectedCount={selectedIds.length}
          visibleRowCount={displayedCandidates.length}
          onEnterSelectionMode={() => setBulkMode('selecting')}
          onExitSelectionMode={() => {
            setBulkMode('normal');
            gridRef.current?.api?.deselectAll();
            setSelectedIds([]);
          }}
          onSelectAllVisible={() => {
            gridRef.current?.api?.selectAll();
          }}
          onDeselectAll={() => {
            gridRef.current?.api?.deselectAll();
            setSelectedIds([]);
          }}
          busy={
            bulkPreview.isPending ||
            bulkApply.isPending ||
            applyResolutionPlan.isPending ||
            refreshPlanEffective.isPending
          }
          previewDangerLabel="Preview bulk steward"
          previewDangerDisabled={
            selectedIds.length === 0 || bulkPreview.isPending || !bulkFormReady
          }
          onPreviewDangerAction={() => void bulkPreview.mutateAsync()}
        />

        {bulkMode === 'selecting' ? (
          <Stack spacing={2} data-testid="dsi-bulk-action-form">
            <Typography variant="caption" color="text.secondary">
              Bulk raw-token override applies only to <strong>map / resolve product</strong>; provisional creates always use
              each candidate&apos;s own samples for aliases.
            </Typography>
            <FormControl size="small" fullWidth>
              <InputLabel id="dsi-bulk-action">Bulk action</InputLabel>
              <Select
                labelId="dsi-bulk-action"
                label="Bulk action"
                value={bulkAction}
                onChange={(e) => setBulkAction(e.target.value as BulkAction)}
              >
                <ListSubheader disableSticky>Map to existing master (one shared target)</ListSubheader>
                <MenuItem value="map_customer">Map to existing customer</MenuItem>
                <MenuItem value="map_distributor">Map to existing distributor</MenuItem>
                <MenuItem value="resolve_product">Resolve product (ProductAlias)</MenuItem>
                <ListSubheader disableSticky>Create provisional masters (one per selected candidate)</ListSubheader>
                <MenuItem value="create_provisional_customer">Create provisional customers</MenuItem>
                <MenuItem value="create_provisional_distributor">Create provisional distributors</MenuItem>
                <ListSubheader disableSticky>Other</ListSubheader>
                <MenuItem value="ignore">Ignore candidate</MenuItem>
              </Select>
            </FormControl>
            {bulkAction === 'ignore' ? (
              <TextField
                label="Notes (optional)"
                value={bulkNotes}
                onChange={(e) => setBulkNotes(e.target.value)}
                fullWidth
                size="small"
              />
            ) : null}
            {bulkAction === 'map_customer' ? (
              <TextField
                label="Customer id"
                value={bulkCustomerId}
                onChange={(e) => setBulkCustomerId(e.target.value)}
                type="number"
                required
                fullWidth
                size="small"
              />
            ) : null}
            {bulkAction === 'map_distributor' ? (
              <TextField
                label="Distributor id"
                value={bulkDistributorId}
                onChange={(e) => setBulkDistributorId(e.target.value)}
                type="number"
                required
                fullWidth
                size="small"
              />
            ) : null}
            {bulkAction === 'resolve_product' ? (
              <Stack spacing={1}>
                <TextField
                  label="Product id"
                  value={bulkProductId}
                  onChange={(e) => setBulkProductId(e.target.value)}
                  type="number"
                  required
                  fullWidth
                  size="small"
                />
                <label>
                  <input
                    type="checkbox"
                    checked={bulkConfirmIneligible}
                    onChange={(e) => setBulkConfirmIneligible(e.target.checked)}
                  />{' '}
                  Confirm inactive/ineligible product (requires audit note)
                </label>
                <TextField
                  label="Audit note (when confirming inactive)"
                  value={bulkAuditNote}
                  onChange={(e) => setBulkAuditNote(e.target.value)}
                  fullWidth
                  size="small"
                  multiline
                  minRows={2}
                />
              </Stack>
            ) : null}
            {bulkAction === 'create_provisional_customer' ? (
              <Stack spacing={1}>
                <Alert severity="info" variant="outlined" data-testid="dsi-bulk-prov-customer-hint">
                  One new <strong>unverified</strong> customer account per selected row; display names follow dealer/source
                  evidence. Region and channel default from each row&apos;s mapped source fields when possible; use the
                  dropdowns only as batch <strong>fallback</strong> when the file leaves values blank or they do not match
                  catalog codes/names.
                </Alert>
                <FormControl size="small" fullWidth>
                  <InputLabel id="dsi-bulk-region">Fallback region (optional)</InputLabel>
                  <Select
                    labelId="dsi-bulk-region"
                    label="Fallback region (optional)"
                    value={bulkRegionId}
                    onChange={(e) => setBulkRegionId(String(e.target.value))}
                  >
                    <MenuItem value="">
                      <em>None — use source + catalog resolution only</em>
                    </MenuItem>
                    {regions.map((r) => (
                      <MenuItem key={r.id} value={String(r.id)}>
                        {r.code} — {r.name}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
                <FormControl size="small" fullWidth>
                  <InputLabel id="dsi-bulk-channel">Fallback channel (optional)</InputLabel>
                  <Select
                    labelId="dsi-bulk-channel"
                    label="Fallback channel (optional)"
                    value={bulkChannelId}
                    onChange={(e) => setBulkChannelId(String(e.target.value))}
                  >
                    <MenuItem value="">
                      <em>None — use source + catalog resolution only</em>
                    </MenuItem>
                    {channels.map((c) => (
                      <MenuItem key={c.id} value={String(c.id)}>
                        {c.code} — {c.name}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
                <FormControl size="small" fullWidth>
                  <InputLabel id="dsi-bulk-tier">Partner tier</InputLabel>
                  <Select
                    labelId="dsi-bulk-tier"
                    label="Partner tier"
                    value={bulkPartnerTier}
                    onChange={(e) => setBulkPartnerTier(e.target.value)}
                  >
                    <MenuItem value="unmanaged">unmanaged</MenuItem>
                    <MenuItem value="strategic">strategic</MenuItem>
                    <MenuItem value="tier_1">tier_1</MenuItem>
                    <MenuItem value="tier_2">tier_2</MenuItem>
                    <MenuItem value="tier_3">tier_3</MenuItem>
                    <MenuItem value="core">core</MenuItem>
                    <MenuItem value="long_tail">long_tail</MenuItem>
                  </Select>
                </FormControl>
                <TextField
                  label="Preferred distributor id (optional)"
                  value={bulkPreferredDistributorId}
                  onChange={(e) => setBulkPreferredDistributorId(e.target.value)}
                  type="number"
                  fullWidth
                  size="small"
                />
                <TextField
                  label="Notes appended to each new customer (optional)"
                  value={bulkProvisionalNotes}
                  onChange={(e) => setBulkProvisionalNotes(e.target.value)}
                  fullWidth
                  size="small"
                  multiline
                  minRows={2}
                />
              </Stack>
            ) : null}
            {bulkAction === 'create_provisional_distributor' ? (
              <Stack spacing={1}>
                <Alert severity="info" variant="outlined" data-testid="dsi-bulk-prov-dist-hint">
                  One provisional distributor per selected row; names come from token samples. Check the box if any selected
                  token is placeholder-like (unknown, n/a, …) — same rule as single-row steward.
                </Alert>
                <TextField
                  label="Distributor code override (optional, leave blank for auto TMP-DIST code)"
                  value={bulkProvisionalDistCode}
                  onChange={(e) => setBulkProvisionalDistCode(e.target.value)}
                  fullWidth
                  size="small"
                />
                <label>
                  <input
                    type="checkbox"
                    checked={bulkDistSuspiciousOk}
                    onChange={(e) => setBulkDistSuspiciousOk(e.target.checked)}
                    data-testid="dsi-bulk-dist-suspicious"
                  />{' '}
                  Confirm create despite placeholder-like tokens
                </label>
              </Stack>
            ) : null}
            {(bulkAction === 'map_customer' || bulkAction === 'map_distributor' || bulkAction === 'resolve_product') ? (
              <TextField
                label="Raw token override for all selected (optional)"
                value={bulkRawToken}
                onChange={(e) => setBulkRawToken(e.target.value)}
                fullWidth
                size="small"
              />
            ) : null}
            <Typography variant="caption" color="text.secondary">
              Use <strong>Preview bulk steward</strong> in the toolbar above, then <strong>Apply bulk steward</strong>{' '}
              here or in the preview dialog after reviewing rows.
            </Typography>
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
              <Button
                variant="contained"
                disabled={!applyReady || bulkApply.isPending || !bulkFormReady}
                onClick={() => void bulkApply.mutateAsync()}
                data-testid="dsi-bulk-apply"
              >
                Apply bulk steward
              </Button>
            </Stack>
          </Stack>
        ) : null}

        {bulkPreview.isError ? (
          <Alert severity="error">{safeDisplayError(bulkPreview.error)}</Alert>
        ) : null}
        {bulkApply.isError ? <Alert severity="error">{safeDisplayError(bulkApply.error)}</Alert> : null}
        {bulkApplySummary ? (
          <Alert severity="success" data-testid="dsi-bulk-apply-summary" onClose={() => setBulkApplySummary(null)}>
            {bulkApplySummary}
          </Alert>
        ) : null}
        {applyResolutionPlan.isError ? (
          <Alert severity="error">{safeDisplayError(applyResolutionPlan.error)}</Alert>
        ) : null}

        <Typography variant="caption" color="text.secondary">
          Single-row steward (selected grid row)
        </Typography>
        <DsiCandidateStewardPanel
          importJobId={importJobId}
          candidate={detailCandidate}
          onDone={() => {
            void qc.invalidateQueries({ queryKey: ['distributor-si-candidates', importJobId] });
            void qc.invalidateQueries({ queryKey: ['dsi-resolution-suggestions', importJobId] });
            onInvalidate();
          }}
        />

        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap alignItems="center">
          <Button
            variant="outlined"
            disabled={dsiRevalidateFromServer.isPending}
            onClick={() => void dsiRevalidateFromServer.mutateAsync()}
            data-testid="dsi-import-revalidate-server"
          >
            {dsiRevalidateFromServer.isPending ? 'Re-running import validation…' : 'Re-run import validation (server)'}
          </Button>
          <Typography variant="caption" color="text.secondary" sx={{ maxWidth: 520 }}>
            Runs the DSI import validator on the server so staging and blockers refresh. Use after steward saves (single-row,
            bulk, or resolution plan apply). This is <strong>not</strong> the same as <strong>Refresh suggestions</strong>{' '}
            (read-only plan recompute).
          </Typography>
        </Stack>
        {dsiRevalidateFromServer.isError ? (
          <Alert severity="error">{safeDisplayError(dsiRevalidateFromServer.error)}</Alert>
        ) : null}

      </Stack>

      <Dialog open={previewOpen} onClose={() => setPreviewOpen(false)} fullWidth maxWidth="lg">
        <DialogTitle>Bulk steward preview</DialogTitle>
        <DialogContent>
          {previewData ? (
            <Stack spacing={2} sx={{ mt: 1 }}>
              <Typography variant="body2">
                Action <strong>{previewData.action}</strong> · ok count{' '}
                <strong>{String(previewData.totals?.ok_count ?? '—')}</strong> · staging rows (ok){' '}
                <strong>{String(previewData.totals?.staging_rows_affected ?? '—')}</strong>
              </Typography>
              <Table size="small" data-testid="dsi-bulk-preview-table">
                <TableHead>
                  <TableRow>
                    <TableCell>ID</TableCell>
                    <TableCell>Type</TableCell>
                    <TableCell>Ok</TableCell>
                    <TableCell>Proposed name</TableCell>
                    <TableCell>Alias / evidence</TableCell>
                    <TableCell>Detail</TableCell>
                    <TableCell align="right">Rows</TableCell>
                    <TableCell align="right">Units</TableCell>
                    <TableCell align="right">Value</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {previewData.results.map((r) => (
                    <TableRow key={String(r.candidate_id)}>
                      <TableCell>{String(r.candidate_id)}</TableCell>
                      <TableCell>{String(r.entity_type ?? '')}</TableCell>
                      <TableCell>{String(r.ok)}</TableCell>
                      <TableCell>{bulkPreviewProposedLabel(r)}</TableCell>
                      <TableCell sx={{ maxWidth: 280 }}>{bulkPreviewAliasEvidence(r)}</TableCell>
                      <TableCell sx={{ maxWidth: 220 }}>
                        {String(r.detail ?? r.skip_reason ?? '')}
                        {r.idempotent_noop ? ' (already done)' : ''}
                      </TableCell>
                      <TableCell align="right">{String(r.row_count ?? '')}</TableCell>
                      <TableCell align="right">{String(r.total_units ?? '')}</TableCell>
                      <TableCell align="right">{String(r.total_reported_value ?? '')}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Stack>
          ) : null}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPreviewOpen(false)}>Close</Button>
          <Button
            variant="contained"
            disabled={!applyReady || bulkApply.isPending || !bulkFormReady}
            onClick={() => void bulkApply.mutateAsync()}
          >
            Apply
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={applyAllConfirmOpen} onClose={() => setApplyAllConfirmOpen(false)}>
        <DialogTitle>Apply all ready rows?</DialogTitle>
        <DialogContent>
          <Typography variant="body2" sx={{ mb: 1 }}>
            You are about to apply <strong>{readyPlanCandidateIds.length}</strong> ready candidate(s), including{' '}
            <strong>{applyAllProvisionalStats.provisionalCustomerReady}</strong> provisional customer create(s).
          </Typography>
          {applyAllProvisionalStats.unassignedGeoReady > 0 ? (
            <Alert severity="warning" sx={{ mb: 1 }}>
              {applyAllProvisionalStats.unassignedGeoReady} ready provisional row(s) still have unassigned region and/or
              channel on the plan — confirm that is intentional.
            </Alert>
          ) : null}
          {applyAllProvisionalStats.fallbackGeoReady > 0 ? (
            <Alert severity="info" variant="outlined" sx={{ mb: 1 }}>
              {applyAllProvisionalStats.fallbackGeoReady} provisional row(s) use global fallback region/channel for at least
              one dimension — source evidence did not fully resolve.
            </Alert>
          ) : null}
          <Typography variant="caption" color="text.secondary">
            Apply runs the same steward executors as the Mapping queue. Refresh suggestions after apply if you need an
            updated grid.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setApplyAllConfirmOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            disabled={applyResolutionPlan.isPending}
            onClick={() => {
              setApplyAllConfirmOpen(false);
              void applyResolutionPlan
                .mutateAsync({
                  candidateIds: readyPlanCandidateIds,
                  overrides: overridesPayload(),
                  globalSuspicious: planGlobalSuspicious,
                })
                .catch(() => {});
            }}
            data-testid="dsi-resolution-plan-apply-all-confirm"
          >
            Apply all ready
          </Button>
        </DialogActions>
      </Dialog>

      <Drawer
        anchor="right"
        open={suggestionDrawerId != null}
        onClose={() => setSuggestionDrawerId(null)}
        PaperProps={{ sx: { width: { xs: '100%', sm: 440 }, maxWidth: '100%' } }}
      >
        <Box sx={{ p: 2 }} data-testid="dsi-resolution-suggestion-drawer">
          <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1 }}>
            <Typography variant="subtitle1">Resolution detail</Typography>
            <Button size="small" onClick={() => setSuggestionDrawerId(null)}>
              Close
            </Button>
          </Stack>
          <Divider sx={{ mb: 2 }} />
          {planDrawerRow ? (
            <PlanDialogRowDetail
              r={planDrawerRow}
              candidate={candidatesById[Number(planDrawerRow.candidate_id)]}
              regions={regions}
              channels={channels}
              planOverrideMap={planOverrideMap}
              patchPlanOverride={patchPlanOverride}
            />
          ) : (
            <Typography variant="body2" color="text.secondary" data-testid="dsi-resolution-plan-detail-empty">
              No suggestion row for this candidate.
            </Typography>
          )}
        </Box>
      </Drawer>
    </Paper>
  );
}
