"use client";

import type { ReactNode } from "react";
import {
  Checkbox,
  Chip,
  FormControl,
  FormControlLabel,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  TextField,
  Typography,
} from "@mui/material";

import {
  formatDsiRegionEvidenceDisplay,
  formatDsiRegionEvidenceTitle,
} from "@/app/(app)/admin/imports/dsi/dsiRegionEvidenceDisplay";
import type { DsiCatalogOpt, DsiPlanRowOverride, DsiRegionEvidenceDto } from "@/app/(app)/admin/imports/dsi/dsiSteward.types";
import type { DsiCandidateRow } from "@/app/(app)/admin/imports/dsi/dsi-mapping-steward-panel";
import {
  formatDsiProductRunningChangeSummary,
  isDsiTokenLevelResolveProductBlocked,
  dsiIgnoreReasonCodeLabel,
} from "@/app/(app)/admin/imports/dsi/dsiProductRunningChangeDisplay";
import { DsiProductResolutionEvidenceCard } from "@/app/(app)/admin/imports/dsi/DsiProductResolutionEvidenceCard";
import {
  DsiPlanWhyPanel,
  formatPlanRulePathLabel,
  type DsiPlanWhy,
} from "@/app/(app)/admin/imports/dsi/dsiPlanExplainabilityDisplay";

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

export function allowedOverrideActions(
  entityType: string,
  ctx?: Record<string, unknown> | null,
  planRow?: Record<string, unknown> | null
): string[] {
  if (entityType === 'distributor_token') {
    return ['ignore', 'map_distributor', 'create_provisional_distributor'];
  }
  if (entityType === 'product_identifier') {
    if (isDsiTokenLevelResolveProductBlocked(ctx, planRow)) {
      return ['ignore'];
    }
    return ['ignore', 'resolve_product'];
  }
  if (entityType === 'customer_dealer_token') {
    return ['ignore', 'map_customer', 'create_provisional_customer'];
  }
  return [];
}

export function formatPlanActionLabel(action: string): string {
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

function truncateEllipsis(s: string, max: number): string {
  const t = s.trim();
  if (t.length <= max) return t;
  return `${t.slice(0, Math.max(0, max - 1))}…`;
}

function fallbackPlanWhy(r: Record<string, unknown>, blockersJoined: string): DsiPlanWhy {
  return {
    narrative: String(r.reason ?? ''),
    blockers: blockersJoined
      ? blockersJoined.split(',').map((b) => b.trim()).filter(Boolean)
      : [],
    rule_path: typeof r.rule_path === 'string' ? r.rule_path : '',
    corroboration_hits: [],
  };
}

export function planReasonSummary(r: Record<string, unknown>): string {
  const blockers = Array.isArray(r.resolution_blockers)
    ? (r.resolution_blockers as string[]).join(', ')
    : '';
  const base = String(r.reason ?? '');
  return blockers ? `${base} · ${blockers}` : base;
}

export function isProvisionalCustomerReadyWithUnassignedGeo(r: Record<string, unknown>): boolean {
  const act = String(r.suggested_action ?? '');
  if (act !== 'create_provisional_customer' || r.ready !== true) return false;
  const er = r.effective_region_id;
  const ec = r.effective_channel_id;
  return er == null || er === '' || ec == null || ec === '';
}

export function planCatalogChannelCell(
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

export function planGeoReadinessHint(
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

export function summarizeApplyAllReadyProvisional(rows: Array<Record<string, unknown>>): {
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

export function planTargetSummary(
  action: string,
  targetId: unknown,
  c: DsiCandidateRow | Record<string, unknown> | undefined,
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
  const planLabel =
    planRow && typeof planRow.suggested_target_label === 'string'
      ? String(planRow.suggested_target_label).trim()
      : '';
  if (action === 'map_customer') {
    return planLabel ? `${planLabel} (id ${id})` : `Customer master · id ${id}`;
  }
  if (action === 'map_distributor') {
    return planLabel ? `${planLabel} (id ${id})` : `Distributor master · id ${id}`;
  }
  if (action === 'resolve_product') {
    if (planLabel) return `${planLabel} (id ${id})`;
    const ctx =
      c && typeof c === 'object' && 'context' in c
        ? (c as DsiCandidateRow).context
        : undefined;
    const pm = ctx ? dsiProductMatchSummaryCell(ctx) : '';
    return pm ? `Product id ${id} · ${pm}` : `Product master · id ${id}`;
  }
  return planLabel ? `${planLabel} (id ${id})` : `Id ${id}`;
}

export type PlanDialogRowDetailProps = {
  r: Record<string, unknown>;
  candidate: DsiCandidateRow | undefined;
  regions: DsiCatalogOpt[];
  channels: DsiCatalogOpt[];
  planOverrideMap: Record<number, DsiPlanRowOverride>;
  patchPlanOverride: (candidateId: number, patch: DsiPlanRowOverride) => void;
};

export function PlanDialogRowDetail({
  r,
  candidate: cand,
  regions,
  channels,
  planOverrideMap,
  patchPlanOverride,
}: PlanDialogRowDetailProps) {
  const id = Number(r.candidate_id);
  const et = String(r.entity_type ?? '');
  const actions = allowedOverrideActions(et, cand?.context ?? null, r);
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
              {(() => {
                const regionDisplay = formatDsiRegionEvidenceDisplay(
                  r.region_evidence as DsiRegionEvidenceDto | undefined
                );
                if (!regionDisplay) return null;
                return (
                  <>
                    <Typography variant="caption" color="text.secondary">
                      {regionDisplay.kind === 'fallback' ? 'Fallback region' : 'Suggested region'}
                    </Typography>
                    <Typography
                      variant="body2"
                      data-testid="dsi-plan-detail-region-evidence"
                      title={formatDsiRegionEvidenceTitle(r.region_evidence as DsiRegionEvidenceDto)}
                    >
                      {regionDisplay.line}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      Source: {regionDisplay.sourceLabel}
                    </Typography>
                    {Array.isArray((r.region_evidence as DsiRegionEvidenceDto).channel_geographic_hints) &&
                    (r.region_evidence as DsiRegionEvidenceDto).channel_geographic_hints.length > 0 ? (
                      <Stack spacing={0.5} sx={{ mt: 0.5 }}>
                        <Typography variant="caption" color="text.secondary">
                          Channel tokens detected as geography
                        </Typography>
                        {(r.region_evidence as DsiRegionEvidenceDto).channel_geographic_hints.map((h, i) => (
                          <Typography key={i} variant="body2" component="div">
                            {String(h.raw_token ?? '—')} → {String(h.guessed_region_code ?? '?')}
                            {typeof h.row_count === 'number'
                              ? ` · ${h.row_count.toLocaleString()} row(s) on this customer`
                              : ''}
                          </Typography>
                        ))}
                      </Stack>
                    ) : null}
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
              <Typography variant="body2">
                {formatDsiProductRunningChangeSummary(cand?.context ?? null) ||
                  dsiProductMatchSummaryCell(cand?.context ?? null) ||
                  '—'}
              </Typography>
              <DsiProductResolutionEvidenceCard context={cand?.context ?? null} />
              {isDsiTokenLevelResolveProductBlocked(cand?.context ?? null, r) ? (
                <Typography variant="caption" color="warning.main" data-testid="dsi-plan-running-change-blocked">
                  Token-level ProductAlias bind blocked — receipt/temporal splits rows by distributor and date.
                  Use ignore for indeterminate remainder or choose product per date cluster in Review.
                </Typography>
              ) : null}
              {typeof r.suggested_ignore_reason_code === 'string' ? (
                <Typography variant="caption" color="text.secondary">
                  Suggested ignore: {dsiIgnoreReasonCodeLabel(String(r.suggested_ignore_reason_code))}
                </Typography>
              ) : null}
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
        <DsiPlanWhyPanel planWhy={(r.plan_why as DsiPlanWhy | undefined) ?? fallbackPlanWhy(r, blockers)} />
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