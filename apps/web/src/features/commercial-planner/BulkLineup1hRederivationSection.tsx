'use client';

import {
  Alert,
  Box,
  Button,
  Chip,
  FormControl,
  FormControlLabel,
  Radio,
  RadioGroup,
  Stack,
  Switch,
  Typography,
} from '@mui/material';

export type LineAllocationPreview = {
  line_id?: number;
  part_number_raw?: string | null;
  model_raw?: string | null;
  customer_token?: string | null;
  months_detected?: Record<string, number>;
  month_total_units?: number;
  qty_cell?: number | null;
  q1_allocated_units?: number;
  q2_allocated_units?: number;
  allocation_tier?: string;
  allocation_flag?: string;
  qty_month_disagreement?: Record<string, unknown> | null;
};

export type RederivationProposal = {
  proposal_key: string;
  source_case_id: number;
  file_name: string | null;
  business_unit?: string | null;
  allocation_summary?: {
    source_total_units: number;
    q1_allocated_units: number;
    q2_allocated_units: number;
    allocation_flag: string;
    month_derived_line_count?: number;
    uniform_half_line_count?: number;
  };
  line_allocations?: LineAllocationPreview[];
  qty_month_disagreement_count?: number;
  q1_adjustment?: {
    planned_units_before: number;
    planned_units_after: number;
    po_link_count: number;
    already_allocated?: boolean;
  };
  half_year_signal_source?: string;
};

export type RederivationCollisionGroup = {
  supersession_group_key: string;
  winner_proposal_key: string;
  winner_member_key?: string;
  members?: Array<{
    member_key?: string;
    filename?: string;
    kind?: string;
    case_id?: number;
    business_unit?: string | null;
  }>;
};

export type RederivationPreviewTotals = {
  eligible_cases?: number;
  collision_groups?: number;
};

function signalSourceLabel(source: string | undefined): string {
  if (source === 'filename_1h') return 'filename';
  if (source === 'stored_month_columns') return 'stored Jan–Jun month columns (no re-upload)';
  if (source === 'workbook_sibling_1h') return 'same workbook as another 1H sheet';
  return source ?? 'unknown';
}

function workbookShortName(filename: string | null | undefined): string {
  if (!filename) return 'workbook';
  const parts = filename.replace(/\\/g, '/').split('/');
  return parts[parts.length - 1] || filename;
}

function memberDisplayLabel(
  m: NonNullable<RederivationCollisionGroup['members']>[number],
): string {
  const bu = m.business_unit?.trim();
  const slice = bu ? `${bu} slice of ${workbookShortName(m.filename)}` : workbookShortName(m.filename);
  if (m.kind === 'existing_case') {
    return `Existing case #${m.case_id ?? '?'}`;
  }
  if (m.kind === 'proposed_q2_twin') {
    return `Proposed Q2 twin (${slice})`;
  }
  return m.kind ?? 'member';
}

function collisionGroupPending(
  group: RederivationCollisionGroup,
  proposals: RederivationProposal[],
): boolean {
  const twinMember = group.members?.find((m) => m.kind === 'proposed_q2_twin');
  if (!twinMember?.member_key) {
    return proposals.some((p) => !p.q1_adjustment?.already_allocated);
  }
  const prop = proposals.find((p) => p.proposal_key === twinMember.member_key);
  if (!prop) {
    return proposals.some((p) => !p.q1_adjustment?.already_allocated);
  }
  return !prop.q1_adjustment?.already_allocated;
}

export function computeRederivationDoneState(proposals: RederivationProposal[]) {
  const eligible = proposals.length;
  const pending = proposals.filter((p) => !p.q1_adjustment?.already_allocated).length;
  const allDone = eligible > 0 && pending === 0;
  return { eligible, pending, allDone };
}

export type BulkLineup1hRederivationSectionProps = {
  preview: {
    rederivation_proposals: RederivationProposal[];
    supersession_collisions: RederivationCollisionGroup[];
    totals?: RederivationPreviewTotals;
  } | null;
  collisionWinners: Record<string, string>;
  onCollisionWinnerChange: (groupKey: string, memberKey: string) => void;
  applyNotice: string | null;
  onDismissApplyNotice: () => void;
  previewError: string | null;
  applyError: string | null;
  onPreview: () => void;
  previewPending: boolean;
  confirmRederivation: boolean;
  onConfirmRederivationChange: (v: boolean) => void;
  onApply: () => void;
  applyPending: boolean;
  canApply: boolean;
};

export function BulkLineup1hRederivationSection({
  preview,
  collisionWinners,
  onCollisionWinnerChange,
  applyNotice,
  onDismissApplyNotice,
  previewError,
  applyError,
  onPreview,
  previewPending,
  confirmRederivation,
  onConfirmRederivationChange,
  onApply,
  applyPending,
  canApply,
}: BulkLineup1hRederivationSectionProps) {
  const proposals = preview?.rederivation_proposals ?? [];
  const collisions = preview?.supersession_collisions ?? [];
  const { eligible, pending, allDone } = computeRederivationDoneState(proposals);

  return (
    <Box sx={{ pt: 2, borderTop: '1px solid', borderColor: 'divider' }} data-testid="bulk-lineup-1h-rederivation">
      <Typography variant="subtitle1" gutterBottom>
        Re-derive existing 1H cases
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
        Split 1H cases into fiscal Q1+Q2 using month columns when present (falls back to uniform 50/50
        only when no qualifying month block exists). Adjusts Q1 quantities in place (preserving case id
        and PO links), then create or collide Q2 twins. Steward confirm required — nothing auto-applies.
      </Typography>
      {previewError && <Alert severity="error">{previewError}</Alert>}
      {applyError && <Alert severity="error">{applyError}</Alert>}
      {applyNotice && (
        <Alert severity="success" onClose={onDismissApplyNotice}>
          {applyNotice}
        </Alert>
      )}
      {preview && allDone && (
        <Alert severity="success" data-testid="rederivation-all-done-banner">
          All {eligible} eligible 1H case{eligible === 1 ? '' : 's'} re-derived
        </Alert>
      )}
      {preview && !allDone && (
        <Alert severity="info" sx={{ mb: 1 }}>
          {preview.totals?.eligible_cases ?? eligible} eligible 1H case(s),{' '}
          {preview.totals?.collision_groups ?? collisions.length} Q2 collision group(s).
          {eligible - pending > 0 ? ` ${eligible - pending} already re-derived, ${pending} pending apply.` : null}
        </Alert>
      )}
      {proposals.map((p) => (
        <Box
          key={p.proposal_key}
          sx={{
            mb: 1,
            p: allDone ? 0.75 : 1,
            border: '1px solid',
            borderColor: 'divider',
            borderRadius: 1,
          }}
          data-testid={`rederivation-proposal-${p.source_case_id}`}
        >
          <Typography variant={allDone ? 'caption' : 'body2'}>
            Case #{p.source_case_id} · {p.file_name}
            {p.q1_adjustment?.already_allocated ? (
              <Chip size="small" label="Already re-derived" color="success" sx={{ ml: 1 }} />
            ) : null}
          </Typography>
          {!allDone && p.half_year_signal_source && (
            <Typography variant="caption" color="text.secondary" component="div">
              1H detected via: {signalSourceLabel(p.half_year_signal_source)}
            </Typography>
          )}
          {!allDone && p.allocation_summary && (
            <Typography variant="caption" color="text.secondary" component="div">
              Source {p.allocation_summary.source_total_units} → Q1 {p.allocation_summary.q1_allocated_units} / Q2{' '}
              {p.allocation_summary.q2_allocated_units} ({p.allocation_summary.allocation_flag})
            </Typography>
          )}
          {!allDone && p.q1_adjustment && (
            <Typography variant="caption" color="text.secondary" component="div">
              Q1 adjust: {p.q1_adjustment.planned_units_before} → {p.q1_adjustment.planned_units_after} units ·{' '}
              {p.q1_adjustment.po_link_count} PO link(s) preserved
              {typeof p.qty_month_disagreement_count === 'number' && p.qty_month_disagreement_count > 0
                ? ` · ${p.qty_month_disagreement_count} Qty≠months steward flag(s)`
                : null}
            </Typography>
          )}
          {!allDone && (p.line_allocations?.length ?? 0) > 0 && (
            <Box component="div" sx={{ mt: 0.5, maxHeight: 160, overflow: 'auto' }} data-testid={`line-alloc-${p.source_case_id}`}>
              {p.line_allocations!.slice(0, 12).map((ln) => (
                <Typography key={ln.line_id ?? `${ln.model_raw}-${ln.customer_token}`} variant="caption" component="div" display="block">
                  {ln.customer_token ?? '—'} · {ln.model_raw ?? ln.part_number_raw ?? 'row'} — months{' '}
                  {ln.months_detected ? JSON.stringify(ln.months_detected) : '{}'} → Q1 {ln.q1_allocated_units} / Q2{' '}
                  {ln.q2_allocated_units} ({ln.allocation_tier ?? ln.allocation_flag})
                  {ln.qty_month_disagreement ? ' · Qty≠months' : ''}
                </Typography>
              ))}
              {(p.line_allocations?.length ?? 0) > 12 ? (
                <Typography variant="caption" color="text.secondary">
                  …and {(p.line_allocations?.length ?? 0) - 12} more lines
                </Typography>
              ) : null}
            </Box>
          )}
        </Box>
      ))}
      {collisions.length > 0 && (
        <Box sx={{ mb: 1 }}>
          <Typography variant="subtitle2">Q2 collision groups</Typography>
          {!allDone && (
            <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
              Prefer the existing dedicated Q2 case when one is already loaded — only choose the proposed twin
              if you intend to replace it.
            </Typography>
          )}
          {collisions.map((g) => {
            const defaultWinner = g.winner_member_key ?? g.winner_proposal_key;
            const isPending = collisionGroupPending(g, proposals);
            const appliedKey = collisionWinners[g.supersession_group_key] ?? defaultWinner;
            const appliedMember = g.members?.find((m) => m.member_key === appliedKey);
            return (
              <Box key={g.supersession_group_key} sx={{ mt: 1 }} data-testid={`collision-group-${g.supersession_group_key}`}>
                <Typography variant="caption">{g.supersession_group_key}</Typography>
                {isPending ? (
                  <FormControl component="fieldset" size="small">
                    <RadioGroup
                      value={appliedKey}
                      onChange={(e) => onCollisionWinnerChange(g.supersession_group_key, e.target.value)}
                    >
                      {g.members?.map((m) => {
                        const memberKey = m.member_key ?? '';
                        const isDefault = memberKey === defaultWinner;
                        return (
                          <FormControlLabel
                            key={memberKey || m.filename}
                            value={memberKey}
                            control={<Radio size="small" />}
                            label={`${memberDisplayLabel(m)}: ${workbookShortName(m.filename)}${
                              isDefault ? ' (recommended)' : ''
                            }`}
                          />
                        );
                      })}
                    </RadioGroup>
                  </FormControl>
                ) : (
                  <Typography variant="body2" color="text.secondary" data-testid={`collision-resolved-${g.supersession_group_key}`}>
                    Resolved: {appliedMember ? memberDisplayLabel(appliedMember) : appliedKey}
                  </Typography>
                )}
              </Box>
            );
          })}
        </Box>
      )}
      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
        <Button size="small" variant="outlined" disabled={previewPending} onClick={onPreview}>
          {previewPending ? 'Loading…' : 'Preview 1H re-derivation'}
        </Button>
        {!allDone && (
          <>
            <FormControlLabel
              control={
                <Switch checked={confirmRederivation} onChange={(e) => onConfirmRederivationChange(e.target.checked)} />
              }
              label="Confirm re-derivation apply"
            />
            <Button
              size="small"
              variant="contained"
              color="secondary"
              disabled={!canApply || !confirmRederivation || applyPending}
              onClick={onApply}
              data-testid="rederivation-apply-button"
            >
              Apply re-derivation
            </Button>
          </>
        )}
      </Stack>
    </Box>
  );
}