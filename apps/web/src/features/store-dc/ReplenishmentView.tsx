'use client';

import { Alert, Box, Button, Checkbox, FormControlLabel, MenuItem, TextField, Typography } from '@mui/material';
import { useState } from 'react';

import type {
  CustomerThresholds,
  LeadLeg,
  NeedLine,
  ReplenishmentViewData,
  SiteBlock,
  SiteCandidateRow,
  StoreDcConfig,
  StoreDcConfigInput,
  ThresholdInput,
} from './types';

type CustomerOption = { id: number; code: string; name: string };

function fmt(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '—';
  return Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function LegPanel({ leg }: { leg: LeadLeg }) {
  return (
    <Box data-testid={`lead-leg-${leg.leg}`} sx={{ mb: 1 }}>
      <Typography variant="body2">
        {leg.title}: {leg.lead_time_label}
      </Typography>
      {leg.note ? (
        <Typography variant="caption" data-testid={`lead-note-${leg.leg}`}>
          {leg.note}
        </Typography>
      ) : null}
      <Typography variant="caption" sx={{ display: 'block' }}>
        {leg.history} · {leg.sample_count} deliveries · min {fmt(leg.min_days)} · p25 {fmt(leg.p25_days)} · median {fmt(leg.median_days)} · p75 {fmt(leg.p75_days)} · max {fmt(leg.max_days)}
      </Typography>
      <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
        {leg.histogram.map((bucket) => (
          <Typography key={bucket.bucket} variant="caption" data-testid={`hist-${leg.leg}-${bucket.bucket}`}>
            {bucket.bucket}: {bucket.count}
          </Typography>
        ))}
      </Box>
    </Box>
  );
}

function Lines({ lines }: { lines: NeedLine[] }) {
  const [note, setNote] = useState<string | null>(null);
  return (
    <Box>
      {lines.map((line) => (
        <Box key={line.product_id} sx={{ mb: 1 }} data-testid="need-line">
          <Typography variant="body2">
            {line.sku ?? line.product_name} · need {fmt(line.need_units)} · {line.need_reason} · {line.lead_time_label} · stock {fmt(line.stock_on_hand)} · cover {fmt(line.weeks_of_cover)}
          </Typography>
          {line.suggestions.length > 0 ? (
            <Box>
              {line.suggestions.map((suggestion) => (
                <Button
                  key={suggestion}
                  size="small"
                  type="button"
                  data-testid={`suggestion-${suggestion}`}
                  onClick={() => setNote('Suggestion only. Nothing was created.')}
                >
                  {suggestion}
                </Button>
              ))}
            </Box>
          ) : null}
        </Box>
      ))}
      {note ? (
        <Alert severity="info" data-testid="suggestion-note">
          {note}
        </Alert>
      ) : null}
    </Box>
  );
}

function positiveNumber(raw: string): number | null {
  const text = raw.trim();
  if (!text) return null;
  const value = Number(text);
  if (!Number.isFinite(value) || value <= 0) return Number.NaN;
  return value;
}

function ConfigForm({
  config,
  onSave,
}: {
  config: StoreDcConfig;
  onSave: (body: StoreDcConfigInput) => void;
}) {
  const [minDeliveries, setMinDeliveries] = useState(String(config.lead_time_min_deliveries));
  const [patterns, setPatterns] = useState(config.dc_name_patterns.join(', '));
  const [minSoh, setMinSoh] = useState(String(config.stock_behaviour_min_soh));
  const [localError, setLocalError] = useState<string | null>(null);

  function save() {
    const deliveries = Number(minDeliveries);
    const soh = Number(minSoh);
    if (!Number.isInteger(deliveries) || deliveries < 1 || deliveries > 1000) {
      setLocalError('Minimum deliveries must be a whole number from 1 to 1000.');
      return;
    }
    if (!Number.isFinite(soh) || soh <= 0) {
      setLocalError('Minimum stock on hand must be greater than 0.');
      return;
    }
    setLocalError(null);
    onSave({
      lead_time_min_deliveries: deliveries,
      dc_name_patterns: patterns.split(',').map((pattern) => pattern.trim()).filter(Boolean),
      stock_behaviour_min_soh: soh,
    });
  }

  return (
    <Box data-testid="store-dc-config" sx={{ display: 'grid', gap: 1, maxWidth: 720 }}>
      <Typography variant="subtitle2">Store and DC settings</Typography>
      <TextField
        size="small"
        label="Minimum deliveries for a lead time"
        value={minDeliveries}
        onChange={(event) => setMinDeliveries(event.target.value)}
        inputProps={{ 'data-testid': 'config-min-deliveries' }}
      />
      <TextField
        size="small"
        label="Distribution centre name patterns"
        value={patterns}
        onChange={(event) => setPatterns(event.target.value)}
        helperText="Comma-separated. Used when refreshing site questions."
        inputProps={{ 'data-testid': 'config-patterns' }}
      />
      <TextField
        size="small"
        label="Minimum stock on hand for stock behaviour"
        value={minSoh}
        onChange={(event) => setMinSoh(event.target.value)}
        inputProps={{ 'data-testid': 'config-min-soh' }}
      />
      {localError ? <Alert severity="warning">{localError}</Alert> : null}
      <Button size="small" data-testid="config-save" onClick={save} sx={{ justifySelf: 'start' }}>
        Save settings
      </Button>
    </Box>
  );
}

function ThresholdForm({
  saved,
  onSave,
}: {
  saved: CustomerThresholds | null;
  onSave: (body: ThresholdInput) => void;
}) {
  const [slow, setSlow] = useState(saved?.slow_cover_multiple != null ? String(saved.slow_cover_multiple) : '');
  const [unsold, setUnsold] = useState(saved?.unsold_weeks != null ? String(saved.unsold_weeks) : '');
  const [localError, setLocalError] = useState<string | null>(null);

  function save() {
    const slowValue = positiveNumber(slow);
    const unsoldValue = positiveNumber(unsold);
    if (Number.isNaN(slowValue) || Number.isNaN(unsoldValue)) {
      setLocalError('Enter a number greater than 0, or leave the field blank.');
      return;
    }
    const body: ThresholdInput = {};
    if (slowValue != null) body.slow_cover_multiple = slowValue;
    if (unsoldValue != null) body.unsold_weeks = unsoldValue;
    if (body.slow_cover_multiple == null && body.unsold_weeks == null) {
      setLocalError('Enter a slow cover multiple or unsold weeks. A blank field stays as it is.');
      return;
    }
    setLocalError(null);
    onSave(body);
  }

  return (
    <Box data-testid="customer-thresholds" sx={{ display: 'grid', gap: 1, maxWidth: 720 }}>
      <Typography variant="subtitle2">Slow and unsold</Typography>
      <TextField
        size="small"
        label="Slow cover multiple"
        value={slow}
        onChange={(event) => setSlow(event.target.value)}
        helperText="Blank leaves the stored multiple unchanged."
        inputProps={{ 'data-testid': 'threshold-slow' }}
      />
      <TextField
        size="small"
        label="Unsold weeks"
        value={unsold}
        onChange={(event) => setUnsold(event.target.value)}
        helperText="Blank leaves the stored weeks unchanged."
        inputProps={{ 'data-testid': 'threshold-unsold' }}
      />
      {localError ? <Alert severity="warning">{localError}</Alert> : null}
      <Button size="small" data-testid="threshold-save" onClick={save} sx={{ justifySelf: 'start' }}>
        Save thresholds
      </Button>
    </Box>
  );
}

function servedSeed(candidate: SiteCandidateRow, view: ReplenishmentViewData | null): number[] {
  const section = view?.dc_sections.find((row) => row.candidate_id === candidate.id);
  if (section) return section.serves.map((row) => row.customer_id);
  return candidate.customer_id != null ? [candidate.customer_id] : [];
}

function ServedAccountControl({
  candidateId,
  customers,
  initialIds,
  onSave,
}: {
  candidateId: number;
  customers: CustomerOption[];
  initialIds: number[];
  /** visibleCustomerIds: every account that had a checkbox row (matches server merge for out-of-scope links). */
  onSave: (candidateId: number, customerIds: number[], visibleCustomerIds: number[]) => void;
}) {
  const [selected, setSelected] = useState(initialIds);
  const rows: CustomerOption[] = [
    ...customers,
    ...initialIds
      .filter((id) => !customers.some((customer) => customer.id === id))
      .map((id) => ({ id, code: String(id), name: `Customer ${id}` })),
  ];

  return (
    <Box data-testid="served-accounts" sx={{ display: 'flex', gap: 1, alignItems: 'center', flexWrap: 'wrap' }}>
      {rows.map((customer) => (
        <Box key={customer.id} data-testid={`served-customer-${customer.id}`}>
          <FormControlLabel
            label={customer.name}
            control={
              <Checkbox
                size="small"
                checked={selected.includes(customer.id)}
                onChange={() =>
                  setSelected((current) =>
                    current.includes(customer.id) ? current.filter((id) => id !== customer.id) : [...current, customer.id],
                  )
                }
              />
            }
          />
        </Box>
      ))}
      <Button
        size="small"
        data-testid={`served-save-${candidateId}`}
        onClick={() => {
          const visible = rows.map((row) => row.id);
          onSave(
            candidateId,
            visible.filter((id) => selected.includes(id)),
            visible,
          );
        }}
      >
        Save served accounts
      </Button>
    </Box>
  );
}

function SiteCard({ block, title }: { block: SiteBlock; title: string }) {
  return (
    <Box data-testid="site-block" sx={{ mb: 1.5 }}>
      <Typography variant="subtitle2">{title}</Typography>
      <Typography variant="caption">
        {block.supply === 'customer_dc' ? 'Supplied from the customer distribution centre' : 'Supplied from the distributor'} · {block.lead_time_label}
      </Typography>
      <Lines lines={block.lines} />
    </Box>
  );
}

export function ReplenishmentView({
  customers,
  customerId,
  onSelect,
  view,
  candidates,
  onDecide,
  decisionError,
  onRefresh,
  refreshNote,
  refreshError,
  config,
  onSaveConfig,
  configError,
  savedThresholds,
  onSaveThresholds,
  thresholdError,
  onAssignServed,
  servedError,
  onReloadLeadTimes,
  leadTimeError,
}: {
  customers: CustomerOption[];
  customerId: number | null;
  onSelect: (id: number) => void;
  view: ReplenishmentViewData | null;
  candidates: SiteCandidateRow[];
  onDecide: (id: number, decision: 'confirm' | 'reject') => void;
  decisionError?: string | null;
  onRefresh?: () => void;
  refreshNote?: string | null;
  refreshError?: string | null;
  config?: StoreDcConfig | null;
  onSaveConfig?: (body: StoreDcConfigInput) => void;
  configError?: string | null;
  savedThresholds?: CustomerThresholds | null;
  onSaveThresholds?: (body: ThresholdInput) => void;
  thresholdError?: string | null;
  onAssignServed?: (candidateId: number, customerIds: number[], visibleCustomerIds: number[]) => void;
  servedError?: string | null;
  onReloadLeadTimes?: () => void;
  leadTimeError?: string | null;
}) {
  const configKey = config
    ? `${config.lead_time_min_deliveries}:${config.stock_behaviour_min_soh}:${config.dc_name_patterns.join('|')}`
    : 'config';
  const thresholdKey = `${customerId ?? 'none'}:${savedThresholds?.slow_cover_multiple ?? ''}:${savedThresholds?.unsold_weeks ?? ''}`;

  return (
    <Box data-testid="replenishment-board" sx={{ display: 'grid', gap: 2 }}>
      <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', flexWrap: 'wrap' }}>
        <TextField
          select
          size="small"
          label="Customer"
          value={customerId ?? ''}
          onChange={(event) => onSelect(Number(event.target.value))}
          inputProps={{ 'data-testid': 'replenishment-customer' }}
          sx={{ maxWidth: 360 }}
        >
          {customers.map((customer) => (
            <MenuItem key={customer.id} value={customer.id}>
              {customer.name}
            </MenuItem>
          ))}
        </TextField>
        {onRefresh ? (
          <Button size="small" data-testid="candidates-refresh" onClick={onRefresh}>
            Refresh site questions
          </Button>
        ) : null}
      </Box>
      {refreshNote ? (
        <Typography variant="body2" data-testid="refresh-note">
          {refreshNote}
        </Typography>
      ) : null}
      {refreshError ? <Alert severity="error">{refreshError}</Alert> : null}
      {configError ? (
        <Alert severity="error" data-testid="config-error">
          {configError}
        </Alert>
      ) : null}
      {config && onSaveConfig ? <ConfigForm key={configKey} config={config} onSave={onSaveConfig} /> : null}
      {thresholdError ? <Alert severity="error">{thresholdError}</Alert> : null}
      {onSaveThresholds && customerId != null ? (
        <ThresholdForm key={thresholdKey} saved={savedThresholds ?? null} onSave={onSaveThresholds} />
      ) : null}
      {view ? (
        <Box data-testid="replenishment-view">
          <Typography variant="body2" data-testid="cover-settings">
            Cover {fmt(view.cover.min_weeks)} to {fmt(view.cover.target_weeks)} weeks ({view.cover.source}). A need uses a lead time only when that leg has at least {view.lead_time_min_deliveries} deliveries.
          </Typography>
          {view.dc_sections.length === 0 ? (
            <Alert severity="info" data-testid="no-dc">
              {view.account
                ? 'Account grain. There is no site label and no distribution centre.'
                : 'No confirmed distribution centre. Stores are supplied by the distributor.'}
            </Alert>
          ) : null}
          {view.collapsed_grain ? (
            <Alert severity="warning" data-testid="collapsed-grain">
              {view.collapsed_grain.note}
            </Alert>
          ) : null}
          {view.dc_sections.map((section) => (
            <Box key={section.candidate_id} data-testid="dc-section" sx={{ mt: 1 }}>
              <Typography variant="subtitle1">{section.site_label}</Typography>
              <Typography variant="body2" data-testid="dc-stock">
                Stock on hand {fmt(section.stock_on_hand)}
                {section.stock_note ? ` · ${section.stock_note}` : ''} · serves {section.serves.map((row) => row.customer_name).join(', ')}
              </Typography>
              <LegPanel leg={section.lead_time} />
              <LegPanel leg={section.onward} />
              {section.stores.map((store) => (
                <SiteCard key={`${store.customer_id}:${store.site_label}`} block={store} title={`${store.site_label} · ${store.customer_name}`} />
              ))}
              {section.need_from_distributor.map((line) => (
                <Typography key={line.product_id} variant="body2" data-testid="dc-need">
                  {line.sku} · distributor need {fmt(line.need_units)} · {line.need_reason} · {line.lead_time_label} · DC stock {fmt(line.stock_on_hand)}
                </Typography>
              ))}
            </Box>
          ))}
          {view.dc_sections.length === 0
            ? view.sites.map((site) => (
                <SiteCard key={site.site_label ?? 'site'} block={site} title={`${site.site_label} · ${site.customer_name}`} />
              ))
            : null}
          {view.account ? <SiteCard block={view.account} title={`${view.customer_name} · account`} /> : null}
          <Box data-testid="lead-time-panel" sx={{ mt: 1 }}>
            <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
              <Typography variant="subtitle2">Lead time</Typography>
              {onReloadLeadTimes ? (
                <Button size="small" data-testid="lead-time-reload" onClick={onReloadLeadTimes}>
                  Reload lead time
                </Button>
              ) : null}
            </Box>
            {leadTimeError ? <Alert severity="error">{leadTimeError}</Alert> : null}
            {view.lead_times.length === 0 ? (
              <Typography variant="body2">lead time: no history</Typography>
            ) : (
              view.lead_times.map((row) => (
                <Box key={`${row.distributor_id}:${row.receiving_site ?? 'account'}`} data-testid="lead-time-row">
                  <Typography variant="caption">
                    {row.distributor_name ?? 'Distributor'} · {row.receiving_site ?? 'no receiving site'}
                  </Typography>
                  <LegPanel leg={row.inbound} />
                  <LegPanel leg={row.onward} />
                </Box>
              ))
            )}
          </Box>
        </Box>
      ) : null}
      <Box data-testid="candidate-list">
        <Typography variant="subtitle2">Site questions</Typography>
        {decisionError ? <Alert severity="error">{decisionError}</Alert> : null}
        {servedError ? <Alert severity="error">{servedError}</Alert> : null}
        {candidates.length === 0 ? (
          <Typography variant="body2">No open questions.</Typography>
        ) : (
          candidates.map((candidate) => (
            <Box key={candidate.id} data-testid="candidate-row" sx={{ display: 'flex', gap: 1, alignItems: 'center', flexWrap: 'wrap', mb: 0.5 }}>
              <Typography variant="body2">
                {candidate.site_label} · {candidate.customer_name} · {candidate.evidence_kind} · {candidate.status}
                {candidate.blocked_as_distributor_site ? ' · distributor site' : ''}
              </Typography>
              {candidate.status === 'open' ? (
                <>
                  <Button size="small" data-testid="candidate-confirm" onClick={() => onDecide(candidate.id, 'confirm')}>
                    Confirm
                  </Button>
                  <Button size="small" data-testid="candidate-reject" onClick={() => onDecide(candidate.id, 'reject')}>
                    Reject
                  </Button>
                </>
              ) : null}
              {onAssignServed && candidate.status === 'confirmed' && !candidate.blocked_as_distributor_site ? (
                <ServedAccountControl
                  key={`${candidate.id}:${servedSeed(candidate, view).join(',')}`}
                  candidateId={candidate.id}
                  customers={customers}
                  initialIds={servedSeed(candidate, view)}
                  onSave={onAssignServed}
                />
              ) : null}
            </Box>
          ))
        )}
      </Box>
    </Box>
  );
}
