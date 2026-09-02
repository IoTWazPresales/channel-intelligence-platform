'use client';

import SwapHorizOutlinedIcon from '@mui/icons-material/SwapHorizOutlined';
import UploadFileOutlinedIcon from '@mui/icons-material/UploadFileOutlined';
import { Alert, Box, Button, Card, CardActionArea, CardContent, Chip, Snackbar, Stack, Step, StepLabel, Stepper, Typography } from '@mui/material';
import { useRouter, useSearchParams } from 'next/navigation';
import { useCallback, useMemo, useState } from 'react';

import { CanonicalColumnMappingPanel, type CanonicalRequiredGroup, type CanonicalTargetOption } from '@/features/import-mapping/CanonicalColumnMappingPanel';

import { planTemplates, templateFieldMaps, type PlanTemplate } from '../fixtures/commercial';
import { CapabilityLedger } from '../primitives/CapabilityLedger';
import { CapabilityStatus } from '../primitives/CapabilityStatus';
import { StatusChip } from '../primitives/controls';
import { HeadlineFigure, HeadlineStrip } from '../primitives/HeadlineFigure';
import { Panel } from '../primitives/Panel';

/**
 * Plan templates — one bidirectional profile per customer workbook (CONSULT Q2).
 *
 * The profile is learned once from an example workbook (a historical plan upload is exactly that),
 * stored as sheet roles + column map + value maps (the shape `cpor_historical_mapping_profile`
 * already has), and used in both directions: to read the customer's historical plans and to render
 * new plans back into their layout. The mapping step mounts the REAL production
 * `CanonicalColumnMappingPanel` (features/import-mapping) — no bespoke mapping table.
 */

const CANONICAL: CanonicalTargetOption[] = [
  { value: 'case_code', label: 'Case reference', description: 'External case / promo reference' },
  { value: 'customer', label: 'Customer', description: 'Resolved via customer token' },
  { value: 'promotion_type', label: 'Promotion type', description: 'Sell-Through PP · Sell out PP · Stock PP' },
  { value: 'window_start', label: 'Window start' },
  { value: 'window_end', label: 'Window end' },
  { value: 'product_token', label: 'Product (SKU / model)', description: 'Resolved via product token' },
  { value: 'distributor', label: 'Distributor', description: 'Resolved via distributor token' },
  { value: 'layer', label: 'POD quarter / layer' },
  { value: 'srp', label: 'Promo SRP (incl VAT)' },
  { value: 'dealer_margin_pct', label: 'Dealer margin %' },
  { value: 'disti_margin_pct', label: 'Distributor margin %' },
  { value: 'rebate_pct', label: 'Rebate %' },
  { value: 'cost_basis', label: 'Cost basis (ex VAT)' },
  { value: 'support_unit', label: 'Support per unit', description: 'Computed on export' },
  { value: 'estimate_qty', label: 'Estimated units' },
  { value: 'ttl_support', label: 'Total support', description: 'Computed on export' },
  { value: 'result_qty', label: 'Actual units (result)' },
  { value: 'claim_amount', label: 'Claimed amount' },
  { value: 'settled_amount', label: 'Settled amount' },
];

const REQUIRED: CanonicalRequiredGroup[] = [
  { id: 'who', label: 'Customer', anyOf: ['customer'], externallySatisfied: true },
  { id: 'what', label: 'Product', anyOf: ['product_token'] },
  { id: 'when', label: 'Window', anyOf: ['window_start'] },
  { id: 'type', label: 'Promotion type', anyOf: ['promotion_type'] },
  { id: 'price', label: 'Promo SRP', anyOf: ['srp'] },
  { id: 'qty', label: 'Estimated units', anyOf: ['estimate_qty'] },
];

const statusTone = (s: PlanTemplate['status']) => (s === 'mapped' ? 'success' : s === 'needs_mapping' ? 'warning' : 'neutral');
const statusLabel: Record<PlanTemplate['status'], string> = { mapped: 'Mapped', needs_mapping: 'Needs mapping', draft: 'Draft' };

export function PlanTemplatesSurface() {
  const router = useRouter();
  const search = useSearchParams();
  const code = search.get('template') ?? 'techmart_promo_grid_v2';
  const setTemplate = useCallback(
    (c: string) => {
      const next = new URLSearchParams(search.toString());
      next.set('template', c);
      router.replace(`/design-lab/funding?${next.toString()}`, { scroll: false });
    },
    [router, search]
  );
  const template = planTemplates.find((t) => t.code === code) ?? planTemplates[1];
  const fields = useMemo(() => templateFieldMaps[template.code] ?? [], [template.code]);

  const fileHeaders = useMemo(() => fields.filter((f) => f.header).map((f) => f.header as string), [fields]);
  const columnSamples = useMemo(() => Object.fromEntries(fields.filter((f) => f.header).map((f) => [f.header as string, f.example ? [f.example] : []])), [fields]);
  const columnNotes = useMemo(() => Object.fromEntries(fields.filter((f) => f.header && f.transform).map((f) => [f.header as string, f.transform as string])), [fields]);
  const initialDraft = useMemo(() => Object.fromEntries(fields.filter((f) => f.header).map((f) => [f.header as string, f.canonical])), [fields]);
  const [drafts, setDrafts] = useState<Record<string, Record<string, string>>>({});
  const draft = drafts[template.code] ?? initialDraft;
  const dirty = drafts[template.code] !== undefined && JSON.stringify(drafts[template.code]) !== JSON.stringify(initialDraft);
  const [toast, setToast] = useState<string | null>(null);

  const mappedCanonical = new Set(Object.values(draft));
  const missingRequired = REQUIRED.filter((g) => !g.externallySatisfied && !g.anyOf.some((v) => mappedCanonical.has(v)));
  const step = template.status === 'mapped' && !dirty ? 3 : missingRequired.length ? 1 : 2;

  return (
    <Stack spacing={2} sx={{ mt: 2 }} data-testid="plan-templates">
      <Alert severity="info" variant="outlined" icon={<SwapHorizOutlinedIcon />}>
        <b>Learn once, use both ways.</b> A customer’s promotion-plan workbook is mapped to CIP’s canonical case model one time — usually from a historical plan they already sent. The same profile then reads their future files and writes CIP plans back into their layout. Nothing about a customer’s spreadsheet lives in code.
      </Alert>

      <HeadlineStrip columns={4}>
        <HeadlineFigure label="Templates" value={planTemplates.length} compact caption={`${planTemplates.filter((t) => t.status === 'mapped').length} mapped · ${planTemplates.filter((t) => t.status === 'needs_mapping').length} need mapping`} />
        <HeadlineFigure label="Plans read through templates" value={planTemplates.reduce((a, t) => a + t.usedByPlans, 0)} compact caption="Historical + current cases" />
        <HeadlineFigure label="Canonical fields" value={CANONICAL.length} compact caption={`${REQUIRED.length} required groups`} />
        <HeadlineFigure label="Export side" value="—" compact caption="Import profile exists in DB; template-driven export is the N-0010 build" />
      </HeadlineStrip>

      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: 'minmax(0, 1fr)', lg: 'minmax(260px, 1fr) minmax(0, 3fr)' }, alignItems: 'start' }}>
        <Stack spacing={2} sx={{ minWidth: 0 }}>
          <Panel title="Templates" subtitle="One per customer workbook layout" flush>
            <Stack spacing={1} sx={{ px: 1.5, pb: 1.5 }}>
              {planTemplates.map((t) => (
                <Card key={t.code} variant="outlined" sx={{ boxShadow: 'none', borderColor: t.code === template.code ? 'primary.main' : 'divider' }}>
                  <CardActionArea onClick={() => setTemplate(t.code)} data-testid={`template-${t.code}`}>
                    <CardContent sx={{ py: 1.25, '&:last-child': { pb: 1.25 } }}>
                      <Stack direction="row" justifyContent="space-between" alignItems="flex-start" spacing={1}>
                        <Box sx={{ minWidth: 0 }}>
                          <Typography variant="body2" sx={{ fontWeight: 600 }} noWrap>{t.name}</Typography>
                          <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }} noWrap>{t.owner} · {t.direction}</Typography>
                        </Box>
                        <StatusChip label={statusLabel[t.status]} tone={statusTone(t.status)} />
                      </Stack>
                      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
                        {t.mappedFields}/{t.canonicalFields} fields · {t.valueMaps} value map{t.valueMaps === 1 ? '' : 's'} · used by {t.usedByPlans} plan{t.usedByPlans === 1 ? '' : 's'}
                      </Typography>
                    </CardContent>
                  </CardActionArea>
                </Card>
              ))}
              <Button variant="outlined" size="small" startIcon={<UploadFileOutlinedIcon />} onClick={() => setToast('Upload an example workbook (a historical plan works). CIP reads sheets and headers, proposes a mapping, and you confirm it here.')} data-testid="template-learn">
                Learn a new template from a workbook
              </Button>
            </Stack>
          </Panel>
          <CapabilityLedger
            title="What works here"
            items={[
              { label: 'Store a profile: sheet roles, column map, value maps', state: 'live', note: 'cpor_historical_mapping_profile — the import side, used by historical CPOR loads today.' },
              { label: 'Confirm a mapping in the shared mapping panel', state: 'live', note: 'This screen mounts the production CanonicalColumnMappingPanel unchanged.' },
              { label: 'Learn a profile from an example workbook', state: 'partial', note: 'Header detection exists in the import parser; the “propose mapping from file” step is not wired.' },
              { label: 'Render an export in the profile’s layout', state: 'planned', note: 'Export is one frozen 32-column tuple today. N-0010 delta.' },
            ]}
          />
        </Stack>

        <Stack spacing={2} sx={{ minWidth: 0 }}>
          <Panel
            title={
              <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                <span>{template.name}</span>
                <Chip size="small" variant="outlined" label={template.code} sx={{ height: 20, fontSize: 11, fontFamily: 'monospace' }} />
                <CapabilityStatus status={template.status === 'mapped' ? 'live' : 'partial'} size="inline" />
              </Stack>
            }
            subtitle={`${template.owner} · sheets: ${template.sheets.join(', ')} · header row ${template.headerRow} · learned from ${template.learnedFrom} · last used ${template.lastUsed}`}
            actions={
              <Stack direction="row" spacing={1}>
                <Button size="small" disabled={!dirty} onClick={() => setDrafts((d) => ({ ...d, [template.code]: initialDraft }))}>Discard</Button>
                <Button size="small" variant="contained" disabled={!dirty || missingRequired.length > 0} onClick={() => { setToast(`${template.name} saved — ${Object.keys(draft).length} columns mapped. Used for the next import and export.`); }} data-testid="template-save">
                  Save profile
                </Button>
              </Stack>
            }
          >
            <Stepper activeStep={step} alternativeLabel sx={{ mb: 2 }}>
              <Step completed><StepLabel>Example workbook</StepLabel></Step>
              <Step completed={step > 1}><StepLabel>Map columns → canonical</StepLabel></Step>
              <Step completed={step > 2}><StepLabel>Value maps & constants</StepLabel></Step>
              <Step completed={step > 2}><StepLabel>Use for import & export</StepLabel></Step>
            </Stepper>
            <CanonicalColumnMappingPanel
              fileHeaders={fileHeaders}
              draft={draft}
              onChange={(next) => setDrafts((d) => ({ ...d, [template.code]: next }))}
              targetOptions={CANONICAL}
              columnSamples={columnSamples}
              columnNotes={columnNotes}
              requiredGroups={REQUIRED}
              blockingErrors={missingRequired.map((g) => ({ code: `missing_${g.id}`, message: `Required canonical field “${g.label}” has no column in this workbook — map a column or set a constant.` }))}
              adjustmentNotices={template.code === 'techmart_promo_grid_v2' ? [{ code: 'constant_customer', message: 'Customer is a constant (TechMart) — this workbook never names it.' }, { code: 'computed', message: '“Support per unit” and “Total support” are computed from the waterfall on export; on import they are read as evidence only.' }] : undefined}
              dirty={dirty}
              testIdPrefix="plan-template"
            />
          </Panel>
          <Panel title="Unmapped canonical fields" subtitle="Canonical fields with no target column in this workbook. Required ones block export; optional ones are simply omitted from the file.">
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
              {CANONICAL.filter((c) => !mappedCanonical.has(c.value)).map((c) => {
                const req = REQUIRED.some((g) => !g.externallySatisfied && g.anyOf.includes(c.value));
                return <Chip key={c.value} size="small" label={c.label} color={req ? 'error' : 'default'} variant={req ? 'filled' : 'outlined'} />;
              })}
            </Stack>
          </Panel>
        </Stack>
      </Box>
      <Snackbar open={!!toast} autoHideDuration={4500} onClose={() => setToast(null)} message={toast} anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }} />
    </Stack>
  );
}
