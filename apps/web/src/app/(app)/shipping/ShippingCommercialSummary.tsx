'use client';

import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import { Box, Button, Collapse, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { apiGet } from '@/lib/api';
import { CategoryBars } from '@/features/workbench-ui/charts';
import { HeadlineFigure, HeadlineStrip } from '@/features/workbench-ui/HeadlineFigure';

import {
  buildShippingCommercialSummaryUrl,
  buildShippingEtaShiftsUrl,
  type ShippingFilterParams,
} from './buildShippingLinesUrl';
import type { SmartPresetId } from './shippingSmartPresets';

type CurrencyAmount = { currency_code: string; amount: number };

export type CommercialSummary = {
  reference_date: string;
  week_start: string;
  week_end: string;
  filter_scope?: { active: boolean; cohort_line_count: number; cohort?: string | null };
  total_lines: number;
  stale_promise_line_count?: number;
  pipeline_in_transit: {
    line_count: number;
    quantity?: number;
    by_currency?: CurrencyAmount[];
    value_by_currency?: CurrencyAmount[];
    cohort_definition?: string;
    grain?: string;
  };
  arriving_this_week: {
    total: number;
    quantity?: number;
    line_count?: number;
    by_distributor: { label: string; count: number; quantity?: number; line_count?: number }[];
    grain?: string;
  };
  landed_this_week?: { total: number; quantity?: number; line_count?: number };
  delivered_this_week?: { total: number; quantity?: number; line_count?: number };
  overdue: {
    count: number;
    line_count?: number;
    quantity?: number;
    pct_of_total_lines: number;
    pct_of_scheduled_pipeline?: number;
    pct_of_current_incoming?: number;
    scheduled_pipeline_lines?: number;
    current_incoming_line_count?: number;
    stale_promise_line_count?: number;
    cohort_definition?: string;
  };
  eta_shifts: {
    slipped_count: number;
    improved_count: number;
    net_direction: string;
    cohort_definition?: string;
  };
};

type EtaShiftSample = {
  source_key: string;
  direction: string;
  previous_effective: string | null;
  current_effective: string | null;
  delta_days: number | null;
};

type EtaShiftsResponse = {
  slipped_count: number;
  improved_count: number;
  net_direction: string;
  samples: EtaShiftSample[];
};

function formatMoney(amount: number, currency: string): string {
  try {
    return new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency: currency.length === 3 ? currency : 'USD',
      maximumFractionDigits: 0,
    }).format(amount);
  } catch {
    return `${currency} ${amount.toFixed(0)}`;
  }
}

function formatQty(n: number): string {
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 }).format(n);
}

export function ShippingCommercialSummary({
  filterParams,
  onApplySmartPreset,
  onFilterScheduledPipeline,
}: {
  filterParams: ShippingFilterParams;
  onApplySmartPreset?: (id: SmartPresetId) => void;
  onFilterScheduledPipeline?: () => void;
}) {
  const [aboutOpen, setAboutOpen] = useState(false);
  const summaryUrl = buildShippingCommercialSummaryUrl(filterParams);
  const etaShiftsUrl = buildShippingEtaShiftsUrl(filterParams, 8);

  const { data: commercial, isLoading: cLoading, isError } = useQuery({
    queryKey: ['shipping-commercial-summary', summaryUrl],
    queryFn: ({ signal }) => apiGet<CommercialSummary>(summaryUrl, { signal }),
  });

  const { data: etaDetail } = useQuery({
    queryKey: ['shipping-eta-shifts', etaShiftsUrl],
    queryFn: ({ signal }) => apiGet<EtaShiftsResponse>(etaShiftsUrl, { signal }),
  });

  if (cLoading) {
    return (
      <HeadlineStrip>
        {['Pipeline value (current incoming)', 'Arriving this week', 'Delivered this week', 'Overdue shipments', 'ETA shifts vs prior job'].map(
          (label) => (
            <HeadlineFigure key={label} label={label} value="" state="loading" />
          ),
        )}
      </HeadlineStrip>
    );
  }

  if (isError || !commercial?.pipeline_in_transit || !commercial.arriving_this_week) {
    return (
      <Typography color="text.secondary" data-testid="shipping-summary-unavailable">
        The shipping summary could not be loaded.
      </Typography>
    );
  }

  const pipe = commercial.pipeline_in_transit;
  const currencies = [...(pipe.value_by_currency ?? pipe.by_currency ?? [])].sort((a, b) => b.amount - a.amount);
  const lead = currencies[0];
  const pipeQty = pipe.quantity ?? 0;
  const pipelineSubtitle = lead
    ? `${lead.currency_code} value · ${formatQty(pipeQty)} units · ${pipe.line_count.toLocaleString()} lines · current incoming (≤90d)`
    : `${pipe.line_count.toLocaleString()} lines · current incoming (≤90d)`;

  const arrivingQty = commercial.arriving_this_week.quantity ?? commercial.arriving_this_week.total ?? 0;
  const arrivingLines = commercial.arriving_this_week.line_count ?? 0;
  const arrivingData = (commercial.arriving_this_week.by_distributor ?? []).map((d) => ({
    name: d.label.length > 14 ? `${d.label.slice(0, 14)}…` : d.label,
    fullName: d.label,
    count: d.quantity ?? d.count,
  }));

  const overduePctPipe = Math.round((commercial.overdue.pct_of_current_incoming ?? commercial.overdue.pct_of_scheduled_pipeline ?? 0) * 1000) / 10;
  const deliveredWeekTotal =
    commercial.delivered_this_week?.total ?? commercial.landed_this_week?.total ?? 0;
  const deliveredQty =
    commercial.delivered_this_week?.quantity ?? commercial.landed_this_week?.quantity ?? 0;
  const filtersActive = commercial.filter_scope?.active ?? false;
  const cohortCount = commercial.filter_scope?.cohort_line_count ?? commercial.total_lines;
  const shifts = commercial.eta_shifts;
  const net = shifts.net_direction;
  const shiftDirection = net === 'slipped' ? 'down' : net === 'improved' ? 'up' : 'flat';
  const clickNote = onApplySmartPreset ? ' · Click to filter the grid' : '';
  const sampleCount = etaDetail?.samples?.length ?? 0;

  const staleExcluded = commercial.overdue.stale_promise_line_count
    ? ` · ${commercial.overdue.stale_promise_line_count.toLocaleString()} stale excluded`
    : '';

  return (
    <Box sx={{ mb: 2 }}>
      <HeadlineStrip>
        <HeadlineFigure
          testId={onFilterScheduledPipeline ? 'shipping-kpi-pipeline-value-(current-incoming)' : undefined}
          label="Pipeline value (current incoming)"
          value={lead ? formatMoney(lead.amount, lead.currency_code) : '—'}
          caption={
            lead
              ? `${formatQty(pipeQty)} units · ${pipe.line_count.toLocaleString()} lines${currencies.length > 1 ? ` · ${currencies.length - 1} other currencies` : ''}${onFilterScheduledPipeline ? ' · Click to filter the grid' : ''}`
              : pipelineSubtitle
          }
          onClick={onFilterScheduledPipeline}
          lead
        />
        <HeadlineFigure
          testId={onApplySmartPreset ? 'shipping-kpi-arriving-this-week' : undefined}
          label="Arriving this week"
          value={formatQty(arrivingQty)}
          unit="units"
          caption={`${arrivingLines.toLocaleString()} lines · ${commercial.week_start} to ${commercial.week_end}${clickNote}`}
          onClick={onApplySmartPreset ? () => onApplySmartPreset('arriving_week') : undefined}
        />
        <HeadlineFigure
          testId={onApplySmartPreset ? 'shipping-kpi-delivered-this-week' : undefined}
          label="Delivered this week"
          value={deliveredWeekTotal.toLocaleString()}
          unit="lines"
          caption={`${formatQty(deliveredQty)} units${clickNote}`}
          severity="good"
          onClick={onApplySmartPreset ? () => onApplySmartPreset('landed_week') : undefined}
        />
        <HeadlineFigure
          testId={onApplySmartPreset ? 'shipping-kpi-overdue-shipments' : undefined}
          label="Overdue shipments"
          value={(commercial.overdue.line_count ?? commercial.overdue.count).toLocaleString()}
          unit="lines"
          caption={`${formatQty(commercial.overdue.quantity ?? 0)} units · ${overduePctPipe}% of current incoming${staleExcluded}${clickNote}`}
          severity="bad"
          onClick={onApplySmartPreset ? () => onApplySmartPreset('overdue') : undefined}
        />
        <HeadlineFigure
          label="ETA shifts vs prior job"
          value={shifts.slipped_count.toLocaleString()}
          unit="slipped"
          caption={`Improved earlier ${shifts.improved_count.toLocaleString()}`}
          delta={{ text: net, direction: shiftDirection, goodWhen: 'up' }}
          severity={net === 'slipped' ? 'bad' : net === 'improved' ? 'good' : 'neutral'}
        />
      </HeadlineStrip>
      {arrivingData.length ? (
        <Box sx={{ mt: 1.5 }}>
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5 }}>
            Arriving this week by distributor
          </Typography>
          <CategoryBars
            data={arrivingData}
            x="name"
            y="count"
            horizontal
            height={Math.max(112, arrivingData.length * 28)}
            format={formatQty}
          />
        </Box>
      ) : null}
      <Button
        size="small"
        variant="text"
        onClick={() => setAboutOpen((open) => !open)}
        aria-expanded={aboutOpen}
        endIcon={<ExpandMoreIcon sx={{ transform: aboutOpen ? 'rotate(180deg)' : 'none', transition: 'transform 120ms' }} />}
        sx={{ px: 0.5, mt: 0.5 }}
        data-testid="shipping-about-figure"
      >
        About this figure
      </Button>
      <Collapse in={aboutOpen}>
        <Box sx={{ mt: 0.5, p: 1.5, borderRadius: 1, bgcolor: 'action.hover' }}>
          <Typography variant="body2">
            {filtersActive
              ? `These figures use the filtered set, ${cohortCount.toLocaleString()} lines, the same filters as the grid.`
              : 'These figures use current incoming: scheduled, not yet landed, with an ETA or promise inside 90 days. They are not the full historical book.'}
          </Typography>
          <Typography variant="body2" sx={{ mt: 1 }}>
            Delivered means the cargo status is received and a proof-of-delivery date falls in this week. Overdue means the promise date has passed, the promise is not older than 180 days, and the ETA is still inside 90 days.
          </Typography>
          <Typography variant="body2" sx={{ mt: 1 }}>
            An ETA shift compares the effective date (estimated delivery or promise) with the previous inbound job. Net is {net}. {sampleCount} sample shifts were compared.
          </Typography>
        </Box>
      </Collapse>
    </Box>
  );
}
