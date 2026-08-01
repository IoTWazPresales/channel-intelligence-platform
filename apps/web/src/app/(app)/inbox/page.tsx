'use client';

import { Alert, Chip, Paper, Stack, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';

import { ModuleDataSection } from '@/components/ModuleDataSection';
import { PageHeader } from '@/components/PageHeader';
import { apiGet, safeDisplayError } from '@/lib/api';

type Delivery = {
  id: number;
  subject: string;
  body_summary: string | null;
  status: string;
  trigger: string;
  format: string;
  metric_key: string | null;
  value_preview: string | null;
  data_vintage: Record<string, unknown> | null;
  missing_data_alert: boolean;
  created_at: string | null;
};

export default function ReportInboxPage() {
  const q = useQuery({
    queryKey: ['report-inbox'],
    queryFn: ({ signal }) =>
      apiGet<{ items: Delivery[]; count: number }>('/api/v1/reports/inbox', { signal }),
    retry: false,
  });

  return (
    <>
      <PageHeader crumbs={[{ label: 'Inbox' }]} title="Report inbox" />
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2, maxWidth: 720 }}>
        Scheduled and manual deliveries land here with data vintage on the face. Missing-data alerts are
        intentional — empty sources are intelligence, not silence.
      </Typography>

      {q.isError && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          Inbox unavailable — apply alembic <code>20260801_0007</code> on cip. {safeDisplayError(q.error)}
        </Alert>
      )}

      <ModuleDataSection
        isLoading={q.isLoading}
        isError={false}
        error={null}
        isEmpty={!q.isLoading && !q.isError && (q.data?.items?.length ?? 0) === 0}
        empty={{
          title: 'Inbox empty',
          description: 'Deliver a saved report from the Report builder, or run a schedule.',
        }}
      >
        <Stack spacing={1.5} data-testid="report-inbox-list">
          {(q.data?.items ?? []).map((d) => (
            <Paper
              key={d.id}
              variant="outlined"
              sx={{ p: 2 }}
              data-testid={`report-inbox-item-${d.id}`}
            >
              <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                <Typography variant="subtitle2" fontWeight={700}>
                  {d.subject}
                </Typography>
                <Chip size="small" label={d.status} color={d.status === 'delivered' ? 'success' : 'error'} />
                <Chip size="small" variant="outlined" label={d.trigger} />
                <Chip size="small" variant="outlined" label={d.format} />
                {d.missing_data_alert && (
                  <Chip size="small" color="warning" label="missing data" data-testid="inbox-missing-alert" />
                )}
              </Stack>
              <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
                {d.created_at || '—'}
                {d.metric_key ? ` · ${d.metric_key}` : ''}
                {d.value_preview != null ? ` · value ${d.value_preview}` : ''}
              </Typography>
              {d.data_vintage && (
                <Alert severity="info" sx={{ mt: 1 }} data-testid={`inbox-vintage-${d.id}`}>
                  Data vintage: {JSON.stringify(d.data_vintage)}
                </Alert>
              )}
              {d.body_summary && (
                <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                  {d.body_summary}
                </Typography>
              )}
            </Paper>
          ))}
        </Stack>
      </ModuleDataSection>
    </>
  );
}
