'use client';

import SwapHorizOutlinedIcon from '@mui/icons-material/SwapHorizOutlined';
import UploadFileOutlinedIcon from '@mui/icons-material/UploadFileOutlined';
import {
  Alert,
  Box,
  Button,
  Card,
  CardActionArea,
  CardContent,
  Chip,
  Snackbar,
  Stack,
  Step,
  StepLabel,
  Stepper,
  Typography,
} from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { useRouter, useSearchParams } from 'next/navigation';
import { useCallback, useMemo, useState } from 'react';

import {
  CanonicalColumnMappingPanel,
  type CanonicalRequiredGroup,
  type CanonicalTargetOption,
} from '@/features/import-mapping/CanonicalColumnMappingPanel';
import { TEMPLATE_CAPABILITIES } from '@/features/promotions-funding/capabilities';
import type { CporCasesPage } from '@/features/promotions-funding/types';
import { apiGet } from '@/lib/api';
import { CapabilityLedger } from '@/features/workbench-ui/CapabilityLedger';
import { CapabilityStatus } from '@/features/shell/CapabilityStatus';
import { StatusChip } from '@/features/workbench-ui/controls';
import { HeadlineFigure, HeadlineStrip } from '@/features/workbench-ui/HeadlineFigure';
import { Panel } from '@/features/workbench-ui/Panel';

/** Canonical targets for the stored historical-import profile (not the frozen 32-column export). */
export const TEMPLATE_CANONICAL: CanonicalTargetOption[] = [
  { value: 'case_code', label: 'Case reference' },
  { value: 'case_name', label: 'Case name' },
  { value: 'customer_token', label: 'Customer' },
  { value: 'promotion_type', label: 'Promotion type' },
  { value: 'window_start', label: 'Window start' },
  { value: 'window_end', label: 'Window end' },
  { value: 'sales_model_token', label: 'Product (SKU / model)' },
  { value: 'distributor_token', label: 'Distributor' },
  { value: 'pod_quarter', label: 'POD quarter / layer' },
  { value: 'srp', label: 'Promo SRP' },
  { value: 'dealer_margin_pct', label: 'Dealer margin %' },
  { value: 'disti_margin_pct', label: 'Distributor margin %' },
  { value: 'rebate_pct', label: 'Rebate %' },
  { value: 'cost_basis', label: 'Cost basis' },
  { value: 'support_unit', label: 'Support per unit' },
  { value: 'estimate_qty', label: 'Estimated units' },
  { value: 'ttl_support', label: 'Total support' },
  { value: 'result_qty', label: 'Actual units (result)' },
  { value: 'status', label: 'Status' },
];

const REQUIRED: CanonicalRequiredGroup[] = [
  { id: 'who', label: 'Customer', anyOf: ['customer_token'] },
  { id: 'what', label: 'Product', anyOf: ['sales_model_token'] },
  { id: 'when', label: 'Window', anyOf: ['window_start'] },
  { id: 'type', label: 'Promotion type', anyOf: ['promotion_type'] },
  { id: 'price', label: 'Promo SRP', anyOf: ['srp'] },
  { id: 'qty', label: 'Estimated units', anyOf: ['estimate_qty'] },
];

export type MappingProfile = {
  id: number;
  profile_code: string;
  display_name: string;
  header_row_index?: number;
  column_map_json: Record<string, string[]>;
  sheet_roles_json: Record<string, string>;
  value_maps_json?: Record<string, unknown>;
  is_default: boolean;
  notes?: string | null;
};

export function draftFromColumnMap(map: Record<string, string[]> | undefined): Record<string, string> {
  const draft: Record<string, string> = {};
  for (const [canonical, headers] of Object.entries(map ?? {})) {
    for (const header of headers ?? []) {
      if (header) draft[header] = canonical;
    }
  }
  return draft;
}

function mappedCount(map: Record<string, string[]> | undefined): number {
  return Object.values(map ?? {}).filter((h) => (h ?? []).some((x) => Boolean(x))).length;
}

export function PlanTemplatesSurface() {
  const router = useRouter();
  const search = useSearchParams();
  const code = search.get('template');
  const setTemplate = useCallback(
    (c: string) => {
      const next = new URLSearchParams(search.toString());
      next.set('template', c);
      next.delete('learn');
      router.replace(`/commercial-planner/cpor-cases/historical-import?${next.toString()}`, { scroll: false });
    },
    [router, search],
  );

  const { data: profilePage } = useQuery({
    queryKey: ['cpor', 'historical', 'profiles'],
    queryFn: ({ signal }) =>
      apiGet<{ profiles: MappingProfile[] }>('/api/v1/cpor/historical-import/profiles', { signal }),
  });
  const { data: casesPage } = useQuery({
    queryKey: ['cpor', 'cases', 'templates-origin'],
    queryFn: ({ signal }) =>
      apiGet<CporCasesPage>('/api/v1/cpor/cases?page=1&page_size=500', { signal }),
  });

  const profiles = profilePage?.profiles ?? [];
  const selected =
    profiles.find((p) => p.profile_code === code) ?? profiles.find((p) => p.is_default) ?? profiles[0];
  const historicalN = (casesPage?.items ?? []).filter((r) => r.origin === 'historical_import').length;

  const [drafts, setDrafts] = useState<Record<string, Record<string, string>>>({});
  const [toast, setToast] = useState<string | null>(null);

  const initialDraft = useMemo(
    () => (selected ? draftFromColumnMap(selected.column_map_json) : {}),
    [selected],
  );
  const draft = (selected && drafts[selected.profile_code]) || initialDraft;
  const dirty =
    !!selected &&
    drafts[selected.profile_code] !== undefined &&
    JSON.stringify(drafts[selected.profile_code]) !== JSON.stringify(initialDraft);

  const extraTargets = useMemo(() => {
    const known = new Set(TEMPLATE_CANONICAL.map((c) => c.value));
    const extra: CanonicalTargetOption[] = [];
    for (const p of profiles) {
      for (const key of Object.keys(p.column_map_json ?? {})) {
        if (!known.has(key)) {
          known.add(key);
          extra.push({ value: key, label: key.replace(/_/g, ' ') });
        }
      }
    }
    return extra;
  }, [profiles]);
  const targets = [...TEMPLATE_CANONICAL, ...extraTargets];

  const fileHeaders = Object.keys(draft);
  const mappedCanonical = new Set(Object.values(draft));
  const missingRequired = REQUIRED.filter((g) => !g.anyOf.some((v) => mappedCanonical.has(v)));
  const step = selected && missingRequired.length === 0 && !dirty ? 3 : missingRequired.length ? 1 : 2;
  const canonicalFieldCount = Object.keys(selected?.column_map_json ?? {}).length || targets.length;

  return (
    <Stack spacing={2} sx={{ mt: 2 }} data-testid="plan-templates">
      <Alert severity="info" variant="outlined" icon={<SwapHorizOutlinedIcon />}>
        <b>Learn once, use both ways.</b> A customer’s promotion-plan workbook is mapped to CIP’s
        canonical case model one time — usually from a historical plan they already sent. The same
        profile then reads their future files. Template-driven export into that layout is not built —
        export remains the frozen 32-column XLSX.
      </Alert>

      <HeadlineStrip columns={4}>
        <HeadlineFigure
          label="Templates"
          value={profiles.length}
          compact
          caption={`${profiles.filter((p) => mappedCount(p.column_map_json) > 0).length} with a stored column map`}
        />
        <HeadlineFigure
          label="Plans read through templates"
          value={historicalN}
          compact
          caption="origin=historical_import on this book (profile is not stored on the case)"
        />
        <HeadlineFigure
          label="Canonical fields"
          value={canonicalFieldCount}
          compact
          caption={`${REQUIRED.length} required groups`}
        />
        <HeadlineFigure
          label="Export side"
          value="—"
          compact
          caption="Import profile exists in DB; template-driven export is not built"
        />
      </HeadlineStrip>

      <Box
        sx={{
          display: 'grid',
          gap: 2,
          gridTemplateColumns: { xs: 'minmax(0, 1fr)', lg: 'minmax(260px, 1fr) minmax(0, 3fr)' },
          alignItems: 'start',
        }}
      >
        <Stack spacing={2} sx={{ minWidth: 0 }}>
          <Panel title="Templates" subtitle="One per customer workbook layout" flush>
            <Stack spacing={1} sx={{ px: 1.5, pb: 1.5 }}>
              {profiles.map((t) => {
                const mapped = mappedCount(t.column_map_json);
                const ok = REQUIRED.every((g) =>
                  g.anyOf.some((v) => (t.column_map_json[v] ?? []).some(Boolean)),
                );
                return (
                  <Card
                    key={t.profile_code}
                    variant="outlined"
                    sx={{
                      boxShadow: 'none',
                      borderColor: t.profile_code === selected?.profile_code ? 'primary.main' : 'divider',
                    }}
                  >
                    <CardActionArea
                      onClick={() => setTemplate(t.profile_code)}
                      data-testid={`template-${t.profile_code}`}
                    >
                      <CardContent sx={{ py: 1.25, '&:last-child': { pb: 1.25 } }}>
                        <Stack direction="row" justifyContent="space-between" alignItems="flex-start" spacing={1}>
                          <Box sx={{ minWidth: 0 }}>
                            <Typography variant="body2" sx={{ fontWeight: 600 }} noWrap>
                              {t.display_name}
                            </Typography>
                            <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }} noWrap>
                              {t.profile_code}
                              {t.is_default ? ' · default' : ''}
                            </Typography>
                          </Box>
                          <StatusChip
                            label={ok ? 'Mapped' : 'Needs mapping'}
                            tone={ok ? 'success' : 'warning'}
                          />
                        </Stack>
                        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
                          {mapped}/{Object.keys(t.column_map_json ?? {}).length || mapped} fields ·{' '}
                          {Object.keys(t.value_maps_json ?? {}).length} value maps
                        </Typography>
                      </CardContent>
                    </CardActionArea>
                  </Card>
                );
              })}
              <Button
                variant="outlined"
                size="small"
                startIcon={<UploadFileOutlinedIcon />}
                onClick={() => router.push('/commercial-planner/cpor-cases/historical-import?learn=1')}
                data-testid="template-learn"
              >
                Learn a new template from a workbook
              </Button>
            </Stack>
          </Panel>
          <CapabilityLedger title="What works here" items={TEMPLATE_CAPABILITIES} />
        </Stack>

        {selected ? (
          <Stack spacing={2} sx={{ minWidth: 0 }}>
            <Panel
              title={
                <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                  <span>{selected.display_name}</span>
                  <Chip
                    size="small"
                    variant="outlined"
                    label={selected.profile_code}
                    sx={{ height: 20, fontSize: 11, fontFamily: 'monospace' }}
                  />
                  <CapabilityStatus status={missingRequired.length ? 'partial' : 'live'} size="inline" />
                </Stack>
              }
              subtitle={`sheets: ${Object.keys(selected.sheet_roles_json ?? {}).join(', ') || '—'} · header row ${selected.header_row_index ?? 1}${selected.notes ? ` · ${selected.notes}` : ''}`}
              actions={
                <Stack direction="row" spacing={1}>
                  <Button
                    size="small"
                    disabled={!dirty}
                    onClick={() =>
                      setDrafts((d) => {
                        const next = { ...d };
                        delete next[selected.profile_code];
                        return next;
                      })
                    }
                  >
                    Discard
                  </Button>
                  <Button
                    size="small"
                    variant="contained"
                    disabled={!dirty || missingRequired.length > 0}
                    onClick={() =>
                      setToast(
                        'Profile edits are not a writer on this surface — the stored map is cpor_historical_mapping_profile, applied on the next historical import. Template-driven export is Planned.',
                      )
                    }
                    data-testid="template-save"
                  >
                    Save profile
                  </Button>
                </Stack>
              }
            >
              <Stepper activeStep={step} alternativeLabel sx={{ mb: 2 }}>
                <Step completed>
                  <StepLabel>Example workbook</StepLabel>
                </Step>
                <Step completed={step > 1}>
                  <StepLabel>Map columns → canonical</StepLabel>
                </Step>
                <Step completed={step > 2}>
                  <StepLabel>Value maps & constants</StepLabel>
                </Step>
                <Step completed={false}>
                  <StepLabel>Use for import & export</StepLabel>
                </Step>
              </Stepper>
              <CanonicalColumnMappingPanel
                fileHeaders={fileHeaders}
                draft={draft}
                onChange={(next) => setDrafts((d) => ({ ...d, [selected.profile_code]: next }))}
                targetOptions={targets}
                requiredGroups={REQUIRED}
                blockingErrors={missingRequired.map((g) => ({
                  code: `missing_${g.id}`,
                  message: `Required canonical field “${g.label}” has no column in this workbook — map a column or set a constant.`,
                }))}
                adjustmentNotices={[
                  {
                    code: 'export_planned',
                    message:
                      '“Use for import & export” is Partly built / Planned: import uses this profile today; template-driven export is not built. The frozen 32-column XLSX remains.',
                  },
                ]}
                dirty={dirty}
                testIdPrefix="plan-template"
              />
            </Panel>
            <Panel
              title="Unmapped canonical fields"
              subtitle="Canonical fields with no target column in this workbook. Required ones block a complete map; optional ones are omitted."
            >
              <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                {TEMPLATE_CANONICAL.filter((c) => !mappedCanonical.has(c.value)).map((c) => {
                  const req = REQUIRED.some((g) => g.anyOf.includes(c.value));
                  return (
                    <Chip
                      key={c.value}
                      size="small"
                      label={c.label}
                      color={req ? 'error' : 'default'}
                      variant={req ? 'filled' : 'outlined'}
                    />
                  );
                })}
              </Stack>
            </Panel>
          </Stack>
        ) : (
          <Alert severity="info">No mapping profiles yet. Learn one from a workbook.</Alert>
        )}
      </Box>
      <Snackbar
        open={!!toast}
        autoHideDuration={6000}
        onClose={() => setToast(null)}
        message={toast}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      />
    </Stack>
  );
}
