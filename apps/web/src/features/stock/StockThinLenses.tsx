'use client';

import { Box } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { useEffect, useState } from 'react';

import { ModuleDataSection } from '@/components/ModuleDataSection';
import { apiGet } from '@/lib/api';

import { FORECAST_WORKSPACE_HREF, SELLTHROUGH_WORKSPACE_HREF } from './stockLeafPaths';
import type { StockLeavesHonesty } from './stockLeavesTypes';

function useClientReady() {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    setReady(true);
  }, []);
  return ready;
}

function ThinLens({
  testId,
  title,
  body,
  importHref,
  workspaceHref,
}: {
  testId: string;
  title: string;
  body: string;
  importHref: string;
  workspaceHref: string;
}) {
  return (
    <Box data-testid={testId} sx={{ mt: 2 }}>
      <ModuleDataSection
        isEmpty
        empty={{
          title,
          description: body,
          primary: { label: 'Go to Import Center', href: importHref },
          secondary: { label: 'Open workspace', href: workspaceHref },
        }}
      >
        <span />
      </ModuleDataSection>
    </Box>
  );
}

export function SellthroughHonesty() {
  const ready = useClientReady();
  const { data, isLoading, isError } = useQuery({
    queryKey: ['stock', 'leaves-honesty'],
    queryFn: ({ signal }) => apiGet<StockLeavesHonesty>('/api/v1/stock/leaves-honesty', { signal }),
    staleTime: 30_000,
  });
  const summary = ready ? data : undefined;
  if (!ready || isLoading) {
    return (
      <Box sx={{ px: 1, py: 2 }} data-testid="sellthrough-honesty-loading">
        Loading Sell-through…
      </Box>
    );
  }
  if (isError || !summary || summary.data_unavailable || !summary.sellthrough?.title) {
    return (
      <ThinLens
        testId="sellthrough-honesty"
        title="Retailer sell-through is not available yet"
        body="Sell-through is derived from retailer files. Headlines could not be loaded."
        importHref="/admin/imports?template=customer_sell_through"
        workspaceHref={SELLTHROUGH_WORKSPACE_HREF}
      />
    );
  }
  return (
    <ThinLens
      testId="sellthrough-honesty"
      title={summary.sellthrough.title}
      body={summary.sellthrough.body ?? ''}
      importHref="/admin/imports?template=customer_sell_through"
      workspaceHref={SELLTHROUGH_WORKSPACE_HREF}
    />
  );
}

export function ForecastHonesty() {
  const ready = useClientReady();
  const { data, isLoading, isError } = useQuery({
    queryKey: ['stock', 'leaves-honesty'],
    queryFn: ({ signal }) => apiGet<StockLeavesHonesty>('/api/v1/stock/leaves-honesty', { signal }),
    staleTime: 30_000,
  });
  const summary = ready ? data : undefined;
  if (!ready || isLoading) {
    return (
      <Box sx={{ px: 1, py: 2 }} data-testid="forecast-honesty-loading">
        Loading Forecasts…
      </Box>
    );
  }
  if (isError || !summary || summary.data_unavailable || !summary.forecast?.title) {
    return (
      <ThinLens
        testId="forecast-honesty"
        title="Forecasts need 8 weeks of applied sell-out"
        body="Velocity and analogue projections are labelled by method and computed only when the trailing window is complete."
        importHref="/admin/imports"
        workspaceHref={FORECAST_WORKSPACE_HREF}
      />
    );
  }
  return (
    <ThinLens
      testId="forecast-honesty"
      title={summary.forecast.title}
      body={summary.forecast.body ?? ''}
      importHref="/admin/imports"
      workspaceHref={FORECAST_WORKSPACE_HREF}
    />
  );
}
