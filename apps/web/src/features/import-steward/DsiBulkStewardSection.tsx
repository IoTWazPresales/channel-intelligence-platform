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
import { BulkSelectionToolbar } from "@/components/bulkTable/BulkSelectionToolbar";

import { safeDisplayError } from "@/lib/api";

import { DsiPendingButton } from "./DsiPendingButton";

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
      <BulkSelectionToolbar
                  mode={bulkMode}
                  selectedCount={selectedIds.length}
                  visibleRowCount={displayedCandidateIds.length}
                  onEnterSelectionMode={() => setBulkMode('selecting')}
                  onExitSelectionMode={() => {
                    setBulkMode('normal');
                    setSelectedIds([]);
                  }}
                  onSelectAllVisible={() => {
                    setSelectedIds([...displayedCandidateIds]);
                  }}
                  onDeselectAll={() => {
                    setSelectedIds([]);
                  }}
                  busy={
                    bulkPreview.isPending ||
                    bulkApply.isPending ||
                    applyResolutionPlan.isPending ||
                    refreshPlanEffective.isPending
                  }
                  previewDangerLabel="Preview bulk steward"
                  previewDangerDisabled={
                    selectedIds.length === 0 || bulkPreview.isPending || !bulkFormReady
                  }
                  onPreviewDangerAction={() => void bulkPreview.mutateAsync()}
                />

      {bulkMode === 'selecting' ? (
                <Stack spacing={2} data-testid="dsi-bulk-action-form">
                  <Typography variant="caption" color="text.secondary">
                    Bulk raw-token override applies only to <strong>map / resolve product</strong>; provisional creates always use
                    each candidate&apos;s own samples for aliases.
                  </Typography>
                  <FormControl size="small" fullWidth>
                    <InputLabel id="dsi-bulk-action">Bulk action</InputLabel>
                    <Select
                      labelId="dsi-bulk-action"
                      label="Bulk action"
                      value={bulkAction}
                      onChange={(e) => setBulkAction(e.target.value as DsiBulkAction)}
                    >
                      <ListSubheader disableSticky>Map to existing master (one shared target)</ListSubheader>
                      <MenuItem value="map_customer">Map to existing customer</MenuItem>
                      <MenuItem value="map_distributor">Map to existing distributor</MenuItem>
                      <MenuItem value="resolve_product">Resolve product (ProductAlias)</MenuItem>
                      <ListSubheader disableSticky>Create provisional masters (one per selected candidate)</ListSubheader>
                      <MenuItem value="create_provisional_customer">Create provisional customers</MenuItem>
                      <MenuItem value="create_provisional_distributor">Create provisional distributors</MenuItem>
                      <ListSubheader disableSticky>Other</ListSubheader>
                      <MenuItem value="ignore">Ignore candidate</MenuItem>
                    </Select>
                  </FormControl>
                  {bulkAction === 'ignore' ? (
                    <TextField
                      label="Notes (optional)"
                      value={bulkNotes}
                      onChange={(e) => setBulkNotes(e.target.value)}
                      fullWidth
                      size="small"
                    />
                  ) : null}
                  {bulkAction === 'map_customer' ? (
                    <TextField
                      label="Customer id"
                      value={bulkCustomerId}
                      onChange={(e) => setBulkCustomerId(e.target.value)}
                      type="number"
                      required
                      fullWidth
                      size="small"
                    />
                  ) : null}
                  {bulkAction === 'map_distributor' ? (
                    <TextField
                      label="Distributor id"
                      value={bulkDistributorId}
                      onChange={(e) => setBulkDistributorId(e.target.value)}
                      type="number"
                      required
                      fullWidth
                      size="small"
                    />
                  ) : null}
                  {bulkAction === 'resolve_product' ? (
                    <Stack spacing={1}>
                      <TextField
                        label="Product id"
                        value={bulkProductId}
                        onChange={(e) => setBulkProductId(e.target.value)}
                        type="number"
                        required
                        fullWidth
                        size="small"
                      />
                      <label>
                        <input
                          type="checkbox"
                          checked={bulkConfirmIneligible}
                          onChange={(e) => setBulkConfirmIneligible(e.target.checked)}
                        />{' '}
                        Confirm inactive/ineligible product (requires audit note)
                      </label>
                      <TextField
                        label="Audit note (when confirming inactive)"
                        value={bulkAuditNote}
                        onChange={(e) => setBulkAuditNote(e.target.value)}
                        fullWidth
                        size="small"
                        multiline
                        minRows={2}
                      />
                    </Stack>
                  ) : null}
                  {bulkAction === 'create_provisional_customer' ? (
                    <Stack spacing={1}>
                      <Alert severity="info" variant="outlined" data-testid="dsi-bulk-prov-customer-hint">
                        One new <strong>unverified</strong> customer account per selected row; display names follow dealer/source
                        evidence. Region and channel default from each row&apos;s mapped source fields when possible; use the
                        dropdowns only as batch <strong>fallback</strong> when the file leaves values blank or they do not match
                        catalog codes/names.
                      </Alert>
                      <FormControl size="small" fullWidth>
                        <InputLabel id="dsi-bulk-region">Fallback region (optional)</InputLabel>
                        <Select
                          labelId="dsi-bulk-region"
                          label="Fallback region (optional)"
                          value={bulkRegionId}
                          onChange={(e) => setBulkRegionId(String(e.target.value))}
                        >
                          <MenuItem value="">
                            <em>None — use source + catalog resolution only</em>
                          </MenuItem>
                          {regions.map((r) => (
                            <MenuItem key={r.id} value={String(r.id)}>
                              {r.code} — {r.name}
                            </MenuItem>
                          ))}
                        </Select>
                      </FormControl>
                      <FormControl size="small" fullWidth>
                        <InputLabel id="dsi-bulk-channel">Fallback channel (optional)</InputLabel>
                        <Select
                          labelId="dsi-bulk-channel"
                          label="Fallback channel (optional)"
                          value={bulkChannelId}
                          onChange={(e) => setBulkChannelId(String(e.target.value))}
                        >
                          <MenuItem value="">
                            <em>None — use source + catalog resolution only</em>
                          </MenuItem>
                          {channels.map((c) => (
                            <MenuItem key={c.id} value={String(c.id)}>
                              {c.code} — {c.name}
                            </MenuItem>
                          ))}
                        </Select>
                      </FormControl>
                      <FormControl size="small" fullWidth>
                        <InputLabel id="dsi-bulk-tier">Partner tier</InputLabel>
                        <Select
                          labelId="dsi-bulk-tier"
                          label="Partner tier"
                          value={bulkPartnerTier}
                          onChange={(e) => setBulkPartnerTier(e.target.value)}
                        >
                          <MenuItem value="unmanaged">unmanaged</MenuItem>
                          <MenuItem value="strategic">strategic</MenuItem>
                          <MenuItem value="tier_1">tier_1</MenuItem>
                          <MenuItem value="tier_2">tier_2</MenuItem>
                          <MenuItem value="tier_3">tier_3</MenuItem>
                          <MenuItem value="core">core</MenuItem>
                          <MenuItem value="long_tail">long_tail</MenuItem>
                        </Select>
                      </FormControl>
                      <TextField
                        label="Preferred distributor id (optional)"
                        value={bulkPreferredDistributorId}
                        onChange={(e) => setBulkPreferredDistributorId(e.target.value)}
                        type="number"
                        fullWidth
                        size="small"
                      />
                      <TextField
                        label="Notes appended to each new customer (optional)"
                        value={bulkProvisionalNotes}
                        onChange={(e) => setBulkProvisionalNotes(e.target.value)}
                        fullWidth
                        size="small"
                        multiline
                        minRows={2}
                      />
                    </Stack>
                  ) : null}
                  {bulkAction === 'create_provisional_distributor' ? (
                    <Stack spacing={1}>
                      <Alert severity="info" variant="outlined" data-testid="dsi-bulk-prov-dist-hint">
                        One provisional distributor per selected row; names come from token samples. Check the box if any selected
                        token is placeholder-like (unknown, n/a, …) — same rule as single-row steward.
                      </Alert>
                      <TextField
                        label="Distributor code override (optional, leave blank for auto TMP-DIST code)"
                        value={bulkProvisionalDistCode}
                        onChange={(e) => setBulkProvisionalDistCode(e.target.value)}
                        fullWidth
                        size="small"
                      />
                      <label>
                        <input
                          type="checkbox"
                          checked={bulkDistSuspiciousOk}
                          onChange={(e) => setBulkDistSuspiciousOk(e.target.checked)}
                          data-testid="dsi-bulk-dist-suspicious"
                        />{' '}
                        Confirm create despite placeholder-like tokens
                      </label>
                    </Stack>
                  ) : null}
                  {(bulkAction === 'map_customer' || bulkAction === 'map_distributor' || bulkAction === 'resolve_product') ? (
                    <TextField
                      label="Raw token override for all selected (optional)"
                      value={bulkRawToken}
                      onChange={(e) => setBulkRawToken(e.target.value)}
                      fullWidth
                      size="small"
                    />
                  ) : null}
                  <Typography variant="caption" color="text.secondary">
                    Use <strong>Preview bulk steward</strong> in the toolbar above, then <strong>Apply bulk steward</strong>{' '}
                    here or in the preview dialog after reviewing rows.
                  </Typography>
                  <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                    <DsiPendingButton
                      variant="contained"
                      pending={bulkApply.isPending}
                      pendingLabel="Applying…"
                      disabled={!applyReady || !bulkFormReady || bulkPreview.isPending}
                      onClick={() => void bulkApply.mutateAsync().catch(() => {})}
                      data-testid="dsi-bulk-apply"
                    >
                      Apply bulk steward
                    </DsiPendingButton>
                  </Stack>
                </Stack>
              ) : null}

              {bulkPreview.isError ? (
                <Alert severity="error" data-testid="dsi-bulk-preview-error">
                  {safeDisplayError(bulkPreview.error)}
                </Alert>
              ) : null}
              {bulkApply.isError ? (
                <Alert severity="error" data-testid="dsi-bulk-apply-error">
                  {safeDisplayError(bulkApply.error)}
                </Alert>
              ) : null}
              {bulkApplySummary ? (
                <Alert severity="success" data-testid="dsi-bulk-apply-summary" onClose={() => setBulkApplySummary(null)}>
                  {bulkApplySummary}
                </Alert>
              ) : null}
      {applyResolutionPlan.isError ? (
        <Alert severity="error">{safeDisplayError(applyResolutionPlan.error)}</Alert>
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
                <DsiPendingButton
                  variant="contained"
                  pending={bulkApply.isPending}
                  pendingLabel="Applying…"
                  disabled={!applyReady || !bulkFormReady}
                  onClick={() => void bulkApply.mutateAsync().catch(() => {})}
                >
                  Apply
                </DsiPendingButton>
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
                <DsiPendingButton
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
                </DsiPendingButton>
              </DialogActions>
            </Dialog>
    </>
  );
}
