'use client';

import { useState } from 'react';
import {
  Alert,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Paper,
  Stack,
  Typography,
} from '@mui/material';
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
  has_html_preview?: boolean;
  channel?: string;
  recipient_email?: string | null;
};

function sectionCounts(vintage: Record<string, unknown> | null): Record<string, number> | null {
  const raw = vintage?.section_counts;
  if (!raw || typeof raw !== 'object') return null;
  const out: Record<string, number> = {};
  for (const [k, v] of Object.entries(raw as Record<string, unknown>)) {
    if (typeof v === 'number') out[k] = v;
  }
  return Object.keys(out).length ? out : null;
}

function sectionDims(vintage: Record<string, unknown> | null): Record<string, Record<string, number>> | null {
  const raw = vintage?.section_dims;
  if (!raw || typeof raw !== 'object') return null;
  const out: Record<string, Record<string, number>> = {};
  for (const [k, v] of Object.entries(raw as Record<string, unknown>)) {
    if (!v || typeof v !== 'object') continue;
    const dims: Record<string, number> = {};
    for (const [dk, dv] of Object.entries(v as Record<string, unknown>)) {
      if (typeof dv === 'number') dims[dk] = dv;
    }
    if (Object.keys(dims).length) out[k] = dims;
  }
  return Object.keys(out).length ? out : null;
}

function chipLabel(id: string, n: number, dims: Record<string, number> | undefined): string {
  const title = SECTION_LABELS[id] || id;
  if (!dims) return `${title}: ${n}`;
  const models = dims.models ?? n;
  const customers = dims.customers;
  const distis = dims.distis;
  return `${title}: ${n} rows · ${models} models · ${customers} customers · ${distis} distis`;
}

const SECTION_LABELS: Record<string, string> = {
  arriving_week: 'ETA this week',
  arriving_next_week: 'ETA next week',
  newly_landed: 'Newly POD’d',
  eta_changes: 'ETA changes',
};

export default function ReportInboxPage() {
  const [previewId, setPreviewId] = useState<number | null>(null);
  const q = useQuery({
    queryKey: ['report-inbox'],
    queryFn: ({ signal }) =>
      apiGet<{ items: Delivery[]; count: number }>('/api/v1/reports/inbox', { signal }),
    retry: false,
  });
  const preview = useQuery({
    queryKey: ['report-inbox-html', previewId],
    queryFn: ({ signal }) =>
      apiGet<{ id: number; subject: string; html: string }>(
        `/api/v1/reports/inbox/${previewId}/html`,
        { signal },
      ),
    enabled: previewId != null,
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
          Inbox unavailable. {safeDisplayError(q.error)}
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
          {(q.data?.items ?? []).map((d) => {
            const counts = sectionCounts(d.data_vintage);
            const dims = sectionDims(d.data_vintage);
            const showHtml = Boolean(d.has_html_preview);
            return (
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
                  {d.channel ? <Chip size="small" variant="outlined" label={d.channel} /> : null}
                  {d.recipient_email ? (
                    <Chip size="small" variant="outlined" label={d.recipient_email} />
                  ) : null}
                  {d.missing_data_alert && (
                    <Chip size="small" color="warning" label="missing data" data-testid="inbox-missing-alert" />
                  )}
                  {showHtml && (
                    <Button
                      size="small"
                      variant="outlined"
                      onClick={() => setPreviewId(d.id)}
                      data-testid={`report-inbox-open-preview-${d.id}`}
                    >
                      Open email preview
                    </Button>
                  )}
                </Stack>
                <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
                  {d.created_at || '—'}
                  {d.metric_key ? ` · ${d.metric_key}` : ''}
                </Typography>
                {counts && (
                  <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mt: 1 }}>
                    {Object.entries(counts).map(([id, n]) => (
                      <Chip
                        key={id}
                        size="small"
                        variant="outlined"
                        label={chipLabel(id, n, dims?.[id])}
                      />
                    ))}
                  </Stack>
                )}
              </Paper>
            );
          })}
        </Stack>
      </ModuleDataSection>

      <Dialog
        open={previewId != null}
        onClose={() => setPreviewId(null)}
        fullWidth
        maxWidth="lg"
        data-testid="report-inbox-email-preview-dialog"
      >
        <DialogTitle>{preview.data?.subject || 'Email preview'}</DialogTitle>
        <DialogContent dividers sx={{ p: 0, minHeight: 480 }}>
          {preview.isLoading && (
            <Typography sx={{ p: 2 }} color="text.secondary">
              Loading preview…
            </Typography>
          )}
          {preview.isError && (
            <Alert severity="warning" sx={{ m: 2 }}>
              {safeDisplayError(preview.error)}
            </Alert>
          )}
          {preview.data?.html ? (
            <iframe
              title="Email preview"
              sandbox=""
              srcDoc={preview.data.html}
              style={{ width: '100%', height: '70vh', border: 0, background: '#fff' }}
            />
          ) : null}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPreviewId(null)}>Close</Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
