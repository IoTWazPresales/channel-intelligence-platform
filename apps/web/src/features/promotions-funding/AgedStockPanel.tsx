'use client';

import { Alert, Button, Chip, Stack, Typography } from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { apiGet, apiPost } from '@/lib/api';

import { groupAgedLines, lineReasons, type AgedLine, type AgedReason } from './agedStockGroups';

type AgedList = { lines?: AgedLine[]; truncated?: boolean };

type ActionResult = { created: boolean; case_id: number; reason?: string };

type ProposeResult = { created?: { case_id: number }[]; skipped?: unknown[] };

const REASON_LABEL: Record<AgedReason, string> = { slow: 'Slow', unsold: 'Unsold' };

function ReasonBadges({ reasons, testId }: { reasons: AgedReason[]; testId: string }) {
  if (!reasons.length) return null;
  return (
    <Stack direction="row" spacing={0.5} data-testid={testId}>
      {reasons.map((r) => (
        <Chip
          key={r}
          size="small"
          color={r === 'unsold' ? 'warning' : 'default'}
          label={REASON_LABEL[r]}
        />
      ))}
    </Stack>
  );
}

const ACTIONS = [
  ['promote', 'Promote'],
  ['move', 'Move'],
  ['return', 'Return'],
] as const;

export function AgedStockPanel({ onOpen }: { onOpen?: (caseId: number) => void }) {
  const qc = useQueryClient();
  const list = useQuery({
    queryKey: ['cpor', 'aged-stock'],
    queryFn: ({ signal }) =>
      apiGet<AgedList>('/api/v1/cpor/intelligence/promo-plan-draft/aged-stock', { signal }),
  });
  const act = useMutation({
    mutationFn: (body: {
      customer_id: number;
      product_id: number;
      action: string;
      site_label?: string | null;
    }) =>
      apiPost<ActionResult>('/api/v1/cpor/intelligence/promo-plan-draft/aged-stock-action', {
        customer_id: body.customer_id,
        product_id: body.product_id,
        action: body.action,
        site_label: body.site_label ?? null,
      }),
    onSuccess: (res) => {
      void qc.invalidateQueries({ queryKey: ['cpor', 'aged-stock'] });
      void qc.invalidateQueries({ queryKey: ['cpor', 'cases'] });
      if (res?.created && res.case_id && onOpen) onOpen(res.case_id);
    },
  });
  const propose = useMutation({
    mutationFn: () =>
      apiPost<ProposeResult>('/api/v1/cpor/intelligence/promo-plan-draft/auto-propose', {}),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['cpor', 'aged-stock'] });
      void qc.invalidateQueries({ queryKey: ['cpor', 'cases'] });
    },
  });
  const lines = list.data?.lines ?? [];
  const truncated = Boolean(list.data?.truncated);
  const groups = groupAgedLines(lines, truncated);
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const actionButtons = (line: AgedLine, idSuffix: string) => {
    const taken = new Set(line.executed_actions ?? []);
    return ACTIONS.map(([action, label]) => (
      <Button
        key={action}
        size="small"
        variant={action === 'promote' ? 'contained' : 'outlined'}
        disabled={act.isPending || taken.has(action) || !(line.suggestions ?? []).includes(action)}
        data-testid={`aged-stock-${action}-${idSuffix}`}
        onClick={() =>
          act.mutate({
            customer_id: line.customer_id,
            product_id: line.product_id,
            action,
            site_label: line.site_label,
          })
        }
      >
        {taken.has(action) ? `${label} open` : label}
      </Button>
    ));
  };
  return (
    <Stack spacing={1} data-testid="aged-stock-panel" sx={{ px: 1.5, py: 1 }}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={1}>
        <Typography variant="body2" color="text.secondary">
          Opening this list does not create a case. Promote writes a draft. Move and return are
          stock actions, not support claims.
        </Typography>
        <Button
          size="small"
          variant="outlined"
          data-testid="aged-stock-raise"
          disabled={propose.isPending}
          onClick={() => propose.mutate()}
        >
          Raise promotion drafts
        </Button>
      </Stack>
      {list.isError ? (
        <Alert severity="error">
          {(list.error as Error)?.message ?? 'Aged stock could not be loaded'}
        </Alert>
      ) : null}
      {propose.isError ? (
        <Alert severity="error">
          {(propose.error as Error)?.message ?? 'Could not raise drafts'}
        </Alert>
      ) : null}
      {act.isError ? (
        <Alert severity="error">
          {(act.error as Error)?.message ?? 'Could not record the action'}
        </Alert>
      ) : null}
      {propose.data ? (
        <Alert severity="info" data-testid="aged-stock-raise-result">
          {propose.data.created?.length ?? 0} draft
          {(propose.data.created?.length ?? 0) === 1 ? '' : 's'} opened
          {(propose.data.skipped?.length ?? 0) ? ` · ${propose.data.skipped?.length} skipped` : ''}
        </Alert>
      ) : null}
      {truncated ? (
        <Alert severity="warning" data-testid="aged-stock-truncated">
          Showing the first {lines.length} site lines only. Lines marked &quot;at least&quot; may
          be missing sites, so their site count and stock on hand are lower bounds.
        </Alert>
      ) : null}
      {!list.isLoading && lines.length === 0 ? (
        <Typography variant="body2" color="text.secondary" data-testid="aged-stock-empty">
          No slow or unsold lines.
        </Typography>
      ) : null}
      {groups.map((group) => {
        const name = group.product_name || group.sku || `Product ${group.product_id}`;
        const single = group.sites.length === 1 ? group.sites[0] : null;
        const expanded = Boolean(open[group.key]);
        const anyOpen = group.sites.some((site) => site.suggestion_executed);
        return (
          <Stack key={group.key} spacing={0.5} data-testid={`aged-stock-group-${group.key}`}>
            <Stack
              direction="row"
              spacing={1}
              alignItems="center"
              flexWrap="wrap"
              useFlexGap
              data-testid={`aged-stock-line-${group.product_id}`}
            >
              <Typography
                variant="body2"
                sx={{ fontWeight: 600, minWidth: 140 }}
                data-testid={`aged-stock-customer-${group.key}`}
              >
                {group.customer_name ?? ''}
              </Typography>
              <Typography variant="body2" sx={{ flex: 1, minWidth: 160 }}>
                {name}
                {single
                  ? single.site_label
                    ? ` · ${single.site_label}`
                    : ''
                  : ` · ${group.incomplete ? 'at least ' : ''}${group.sites.length} sites`}
                {single && group.incomplete ? ' · may be missing sites' : ''}
                {group.stock_on_hand != null
                  ? ` · ${group.incomplete ? 'at least ' : ''}${group.stock_on_hand} on hand`
                  : ''}
                {anyOpen ? ' · action open' : ''}
              </Typography>
              <ReasonBadges reasons={group.reasons} testId={`aged-stock-reasons-${group.key}`} />
              {single ? (
                actionButtons(single, String(group.product_id))
              ) : (
                <Button
                  size="small"
                  variant="text"
                  data-testid={`aged-stock-sites-toggle-${group.key}`}
                  aria-expanded={expanded}
                  onClick={() => setOpen((cur) => ({ ...cur, [group.key]: !cur[group.key] }))}
                >
                  {expanded ? 'Hide sites' : `Show ${group.sites.length} sites`}
                </Button>
              )}
            </Stack>
            {!single && expanded
              ? group.sites.map((site, index) => (
                  <Stack
                    key={`${group.key}-${index}`}
                    direction="row"
                    spacing={1}
                    alignItems="center"
                    flexWrap="wrap"
                    useFlexGap
                    sx={{ pl: 4 }}
                    data-testid={`aged-stock-site-${group.key}-${index}`}
                  >
                    <Typography variant="body2" sx={{ flex: 1, minWidth: 160 }}>
                      {site.site_label ?? 'Account'}
                      {site.stock_on_hand != null ? ` · ${site.stock_on_hand} on hand` : ''}
                      {site.suggestion_executed ? ' · action open' : ''}
                    </Typography>
                    <ReasonBadges
                      reasons={lineReasons(site)}
                      testId={`aged-stock-site-reasons-${group.key}-${index}`}
                    />
                    {actionButtons(site, `${group.product_id}-${index}`)}
                  </Stack>
                ))
              : null}
          </Stack>
        );
      })}
    </Stack>
  );
}
