'use client';

import { Alert, Box, Button, MenuItem, TextField, Typography } from '@mui/material';
import { useState } from 'react';

import type { LeadLeg, NeedLine, ReplenishmentViewData, SiteBlock, SiteCandidateRow } from './types';

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
}: {
  customers: { id: number; code: string; name: string }[];
  customerId: number | null;
  onSelect: (id: number) => void;
  view: ReplenishmentViewData | null;
  candidates: SiteCandidateRow[];
  onDecide: (id: number, decision: 'confirm' | 'reject') => void;
  decisionError?: string | null;
}) {
  return (
    <Box data-testid="replenishment-board" sx={{ display: 'grid', gap: 2 }}>
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
            <Typography variant="subtitle2">Lead time</Typography>
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
            </Box>
          ))
        )}
      </Box>
    </Box>
  );
}
