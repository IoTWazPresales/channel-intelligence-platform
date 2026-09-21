'use client';

import { Stack } from '@mui/material';
import { useQuery } from '@tanstack/react-query';

import { ModuleDataSection } from '@/components/ModuleDataSection';
import { Panel, PanelRow } from '@/features/workbench-ui/Panel';
import { apiGet } from '@/lib/api';

export type CporCaseEvent = {
  id: number;
  event_type: string;
  actor: string | null;
  created_at: string | null;
};

/** Lifecycle events for one CPOR case, newest as the API returns them. Read-only. */
export function CporEventsPanel({ caseId }: { caseId: number }) {
  const q = useQuery({
    queryKey: ['cpor', 'events', caseId],
    queryFn: ({ signal }) => apiGet<CporCaseEvent[]>(`/api/v1/cpor/cases/${caseId}/events`, { signal }),
    enabled: caseId > 0,
  });
  const events = q.data ?? [];

  return (
    <ModuleDataSection
      isLoading={q.isLoading}
      isError={q.isError}
      error={q.isError ? new Error(String((q.error as Error)?.message ?? 'Failed to load case events')) : null}
      onRetry={() => void q.refetch()}
      isEmpty={events.length === 0}
      empty={{
        title: 'No events recorded',
        description: 'Lifecycle transitions, approvals and settlements are written here as they happen on this case.',
      }}
      loadingLabel="Loading case events…"
    >
      <Panel title="Case events" subtitle="Who did what, and when — stamped by the API on every transition" flush>
        <Stack spacing={0.25} sx={{ px: 1, pb: 1 }} data-testid="cpor-events">
          {events.map((e) => (
            <PanelRow
              key={e.id}
              primary={e.event_type}
              secondary={`${e.created_at ?? '—'} · ${e.actor ?? 'actor not stamped'}`}
              severity="neutral"
            />
          ))}
        </Stack>
      </Panel>
    </ModuleDataSection>
  );
}
