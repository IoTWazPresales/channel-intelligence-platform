'use client';

import { Alert, Button, Stack, Typography } from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { apiGet, apiPost } from '@/lib/api';

type AgedLine = {
  customer_id: number;
  /** Name only; codes never go in the customer column. */
  customer_name?: string | null;
  product_id: number;
  sku?: string | null;
  product_name?: string | null;
  site_label?: string | null;
  stock_on_hand?: number | null;
  suggestions?: string[];
  suggestion_executed?: boolean;
  executed_actions?: string[];
};

type AgedList = { lines?: AgedLine[]; truncated?: boolean };

type ActionResult = { created: boolean; case_id: number; reason?: string };

type ProposeResult = { created?: { case_id: number }[]; skipped?: unknown[] };

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
    mutationFn: (body: { customer_id: number; product_id: number; action: string; site_label?: string | null }) =>
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
    mutationFn: () => apiPost<ProposeResult>('/api/v1/cpor/intelligence/promo-plan-draft/auto-propose', {}),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['cpor', 'aged-stock'] });
      void qc.invalidateQueries({ queryKey: ['cpor', 'cases'] });
    },
  });
  const lines = list.data?.lines ?? [];
  return (
    <Stack spacing={1} data-testid="aged-stock-panel" sx={{ px: 1.5, py: 1 }}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={1}>
        <Typography variant="body2" color="text.secondary">
          Opening this list does not create a case. Promote writes a draft. Move and return are stock actions, not support claims.
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
        <Alert severity="error">{(list.error as Error)?.message ?? 'Aged stock could not be loaded'}</Alert>
      ) : null}
      {propose.isError ? (
        <Alert severity="error">{(propose.error as Error)?.message ?? 'Could not raise drafts'}</Alert>
      ) : null}
      {act.isError ? <Alert severity="error">{(act.error as Error)?.message ?? 'Could not record the action'}</Alert> : null}
      {propose.data ? (
        <Alert severity="info" data-testid="aged-stock-raise-result">
          {propose.data.created?.length ?? 0} draft{(propose.data.created?.length ?? 0) === 1 ? '' : 's'} opened
          {(propose.data.skipped?.length ?? 0) ? ` · ${propose.data.skipped.length} skipped` : ''}
        </Alert>
      ) : null}
      {!list.isLoading && lines.length === 0 ? (
        <Typography variant="body2" color="text.secondary" data-testid="aged-stock-empty">
          No slow or unsold lines.
        </Typography>
      ) : null}
      {lines.map((line) => {
        const taken = new Set(line.executed_actions ?? []);
        const key = `${line.customer_id}-${line.product_id}-${line.site_label ?? ''}`;
        const name = line.product_name || line.sku || `Product ${line.product_id}`;
        return (
          <Stack
            key={key}
            direction="row"
            spacing={1}
            alignItems="center"
            flexWrap="wrap"
            useFlexGap
            data-testid={`aged-stock-line-${line.product_id}`}
          >
            <Typography
              variant="body2"
              sx={{ fontWeight: 600, minWidth: 140 }}
              data-testid={`aged-stock-customer-${key}`}
            >
              {line.customer_name ?? ''}
            </Typography>
            <Typography variant="body2" sx={{ flex: 1, minWidth: 160 }}>
              {name}
              {line.site_label ? ` · ${line.site_label}` : ''}
              {line.stock_on_hand != null ? ` · ${line.stock_on_hand} on hand` : ''}
              {line.suggestion_executed ? ' · action open' : ''}
            </Typography>
            {ACTIONS.map(([action, label]) => (
              <Button
                key={action}
                size="small"
                variant={action === 'promote' ? 'contained' : 'outlined'}
                disabled={act.isPending || taken.has(action) || !(line.suggestions ?? []).includes(action)}
                data-testid={`aged-stock-${action}-${line.product_id}`}
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
            ))}
          </Stack>
        );
      })}
    </Stack>
  );
}
