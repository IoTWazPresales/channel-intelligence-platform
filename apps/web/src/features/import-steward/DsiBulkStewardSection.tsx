"use client";

import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  InputLabel,
  ListSubheader,
  MenuItem,
  Select,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from "@mui/material";
import type { BulkTableSelectionMode } from "@/components/bulkTable/BulkSelectionToolbar";

import { StewardPendingButton } from "./StewardPendingButton";

import { bulkPreviewAliasEvidence, bulkPreviewProposedLabel } from "./dsiBulkStewardDisplay";
import type { useDsiBulkSteward } from "./useDsiBulkSteward";
import type { useDsiResolutionPlan } from "./useDsiResolutionPlan";
import type { DsiBulkAction, DsiCatalogOpt } from "./dsiSteward.types";

type BulkSteward = ReturnType<typeof useDsiBulkSteward>;
type PlanSteward = ReturnType<typeof useDsiResolutionPlan>;

export function DsiBulkStewardSection({
  bulkMode,
  setBulkMode,
  selectedIds,
  setSelectedIds,
  displayedCandidateIds,
  bulk,
  plan,
  regions,
  channels,
  stewardOverlayBusy,
}: {
  bulkMode: BulkTableSelectionMode;
  setBulkMode: (mode: BulkTableSelectionMode) => void;
  selectedIds: number[];
  setSelectedIds: (ids: number[] | ((prev: number[]) => number[])) => void;
  displayedCandidateIds: number[];
  bulk: BulkSteward;
  plan: PlanSteward;
  regions: DsiCatalogOpt[];
  channels: DsiCatalogOpt[];
  stewardOverlayBusy: boolean;
}) {
  const {
    bulkAction,
    setBulkAction,
    bulkNotes,
    setBulkNotes,
    bulkCustomerId,
    setBulkCustomerId,
    bulkDistributorId,
    setBulkDistributorId,
    bulkProductId,
    setBulkProductId,
    bulkRawToken,
    setBulkRawToken,
    bulkConfirmIneligible,
    setBulkConfirmIneligible,
    bulkAuditNote,
    setBulkAuditNote,
    bulkRegionId,
    setBulkRegionId,
    bulkChannelId,
    setBulkChannelId,
    bulkPreferredDistributorId,
    setBulkPreferredDistributorId,
    bulkPartnerTier,
    setBulkPartnerTier,
    bulkProvisionalNotes,
    setBulkProvisionalNotes,
    bulkDistSuspiciousOk,
    setBulkDistSuspiciousOk,
    bulkProvisionalDistCode,
    setBulkProvisionalDistCode,
    bulkApplySummary,
    setBulkApplySummary,
    previewOpen,
    setPreviewOpen,
    previewData,
    bulkPreview,
    bulkApply,
    bulkFormReady,
    applyReady,
  } = bulk;

  const {
    applyAllConfirmOpen,
    setApplyAllConfirmOpen,
    applyResolutionPlan,
    readyPlanCandidateIds,
    applyAllProvisionalStats,
    overridesPayload,
    planGlobalSuspicious,
    refreshPlanEffective,
  } = plan;

  return (
    <>
      {bulkApplySummary ? (
                <Alert severity="success" data-testid="dsi-bulk-apply-summary" onClose={() => setBulkApplySummary(null)}>
                  {bulkApplySummary}
                </Alert>
              ) : null}

      <Dialog open={previewOpen} onClose={() => setPreviewOpen(false)} fullWidth maxWidth="lg">
              <DialogTitle>Bulk steward preview</DialogTitle>
              <DialogContent>
                {previewData ? (
                  <Stack spacing={2} sx={{ mt: 1 }}>
                    <Typography variant="body2">
                      Action <strong>{previewData.action}</strong> · ok count{' '}
                      <strong>{String(previewData.totals?.ok_count ?? '—')}</strong> · staging rows (ok){' '}
                      <strong>{String(previewData.totals?.staging_rows_affected ?? '—')}</strong>
                    </Typography>
                    <Table size="small" data-testid="dsi-bulk-preview-table">
                      <TableHead>
                        <TableRow>
                          <TableCell>ID</TableCell>
                          <TableCell>Type</TableCell>
                          <TableCell>Ok</TableCell>
                          <TableCell>Proposed name</TableCell>
                          <TableCell>Alias / evidence</TableCell>
                          <TableCell>Detail</TableCell>
                          <TableCell align="right">Rows</TableCell>
                          <TableCell align="right">Units</TableCell>
                          <TableCell align="right">Value</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {previewData.results.map((r) => (
                          <TableRow key={String(r.candidate_id)}>
                            <TableCell>{String(r.candidate_id)}</TableCell>
                            <TableCell>{String(r.entity_type ?? '')}</TableCell>
                            <TableCell>{String(r.ok)}</TableCell>
                            <TableCell>{bulkPreviewProposedLabel(r)}</TableCell>
                            <TableCell sx={{ maxWidth: 280 }}>{bulkPreviewAliasEvidence(r)}</TableCell>
                            <TableCell sx={{ maxWidth: 220 }}>
                              {String(r.detail ?? r.skip_reason ?? '')}
                              {r.idempotent_noop ? ' (already done)' : ''}
                            </TableCell>
                            <TableCell align="right">{String(r.row_count ?? '')}</TableCell>
                            <TableCell align="right">{String(r.total_units ?? '')}</TableCell>
                            <TableCell align="right">{String(r.total_reported_value ?? '')}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </Stack>
                ) : null}
              </DialogContent>
              <DialogActions>
                <Button onClick={() => setPreviewOpen(false)}>Close</Button>
                <StewardPendingButton
                  variant="contained"
                  pending={bulkApply.isPending}
                  pendingLabel="Applying…"
                  disabled={!applyReady || !bulkFormReady}
                  onClick={() => void bulkApply.mutateAsync().catch(() => {})}
                >
                  Apply
                </StewardPendingButton>
              </DialogActions>
            </Dialog>

            <Dialog open={applyAllConfirmOpen} onClose={() => setApplyAllConfirmOpen(false)}>
              <DialogTitle>Apply all ready rows?</DialogTitle>
              <DialogContent>
                <Typography variant="body2" sx={{ mb: 1 }}>
                  You are about to apply <strong>{readyPlanCandidateIds.length}</strong> ready candidate(s), including{' '}
                  <strong>{applyAllProvisionalStats.provisionalCustomerReady}</strong> provisional customer create(s).
                </Typography>
                {applyAllProvisionalStats.unassignedGeoReady > 0 ? (
                  <Alert severity="warning" sx={{ mb: 1 }}>
                    {applyAllProvisionalStats.unassignedGeoReady} ready provisional row(s) still have unassigned region and/or
                    channel on the plan — confirm that is intentional.
                  </Alert>
                ) : null}
                {applyAllProvisionalStats.fallbackGeoReady > 0 ? (
                  <Alert severity="info" variant="outlined" sx={{ mb: 1 }}>
                    {applyAllProvisionalStats.fallbackGeoReady} provisional row(s) use global fallback region/channel for at least
                    one dimension — source evidence did not fully resolve.
                  </Alert>
                ) : null}
                <Typography variant="caption" color="text.secondary">
                  Apply runs the same steward executors as the Mapping queue. Refresh suggestions after apply if you need an
                  updated grid.
                </Typography>
              </DialogContent>
              <DialogActions>
                <Button onClick={() => setApplyAllConfirmOpen(false)}>Cancel</Button>
                <StewardPendingButton
                  variant="contained"
                  pending={applyResolutionPlan.isPending}
                  pendingLabel="Applying…"
                  onClick={() => {
                    setApplyAllConfirmOpen(false);
                    void applyResolutionPlan
                      .mutateAsync({
                        candidateIds: readyPlanCandidateIds,
                        overrides: overridesPayload(),
                        globalSuspicious: planGlobalSuspicious,
                      })
                      .catch(() => {});
                  }}
                  data-testid="dsi-resolution-plan-apply-all-confirm"
                >
                  Apply all ready
                </StewardPendingButton>
              </DialogActions>
            </Dialog>
    </>
  );
}
