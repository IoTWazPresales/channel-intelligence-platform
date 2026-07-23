'use client';

import { useState } from 'react';
import {
  Alert,
  Button,
  FormControl,
  InputLabel,
  ListSubheader,
  MenuItem,
  Select,
  Stack,
  TextField,
  Typography,
} from '@mui/material';

import { safeDisplayError } from '@/lib/api';

import { DsiCustomerSearchFields } from './DsiCustomerSearchFields';
import { StewardPendingButton } from './StewardPendingButton';
import type { useDsiBulkSteward } from './useDsiBulkSteward';
import type { DsiBulkAction, DsiCatalogOpt } from './dsiSteward.types';

type BulkSteward = ReturnType<typeof useDsiBulkSteward>;

export function DsiBulkActionInlineForm({
  bulk,
  regions,
  channels,
  onCancel,
}: {
  bulk: BulkSteward;
  regions: DsiCatalogOpt[];
  channels: DsiCatalogOpt[];
  onCancel: () => void;
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
    bulkPreview,
    bulkApply,
    bulkFormReady,
    applyReady,
  } = bulk;

  const [bulkCustQ, setBulkCustQ] = useState('');

  return (
    <Stack
      spacing={2}
      data-testid="dsi-bulk-action-form"
      sx={{
        p: 2,
        border: 1,
        borderColor: 'divider',
        borderRadius: 1,
        bgcolor: 'action.hover',
      }}
    >
      <Stack direction="row" alignItems="center" justifyContent="space-between" flexWrap="wrap" useFlexGap>
        <Typography variant="subtitle2">Bulk steward</Typography>
        <Button size="small" onClick={onCancel} data-testid="dsi-bulk-form-cancel">
          Cancel
        </Button>
      </Stack>
      <Typography variant="caption" color="text.secondary">
        Bulk raw-token override applies only to <strong>map / resolve product</strong>; provisional creates always use
        each candidate&apos;s own samples for aliases.
      </Typography>
      <FormControl size="small" fullWidth>
        <InputLabel id="dsi-bulk-action-inline">Bulk action</InputLabel>
        <Select
          labelId="dsi-bulk-action-inline"
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
          <ListSubheader disableSticky>Plan (resolution suggestions only)</ListSubheader>
          <MenuItem value="apply_suggested_region">Apply suggested region to plan</MenuItem>
          <MenuItem value="set_plan_fallback_channel">Set job fallback channel</MenuItem>
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
        <DsiCustomerSearchFields
          searchQuery={bulkCustQ}
          onSearchQueryChange={setBulkCustQ}
          customerId={bulkCustomerId === '' ? '' : Number(bulkCustomerId)}
          onCustomerIdChange={(id) => setBulkCustomerId(id === '' ? '' : String(id))}
          searchTestId="dsi-bulk-customer-search"
          selectTestId="dsi-bulk-customer-select"
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
      {bulkAction === 'apply_suggested_region' ? (
        <Alert severity="info" variant="outlined">
          Copies each selected customer&apos;s <strong>region_evidence.suggested_region_id</strong> into plan overrides
          (plan-only until Apply ready). Use the Customers tab country fallback for job-level defaults when province is
          empty.
        </Alert>
      ) : null}
      {bulkAction === 'set_plan_fallback_channel' ? (
        <Stack spacing={1}>
          <Alert severity="info" variant="outlined">
            Sets a <strong>job-level</strong> fallback channel for resolution suggestions when the file does not supply a
            resolvable channel. Does not change uploaded rows.
          </Alert>
          <FormControl size="small" fullWidth>
            <InputLabel id="dsi-bulk-plan-channel-inline">Fallback channel</InputLabel>
            <Select
              labelId="dsi-bulk-plan-channel-inline"
              label="Fallback channel"
              value={bulkChannelId}
              onChange={(e) => setBulkChannelId(String(e.target.value))}
            >
              <MenuItem value="">
                <em>None</em>
              </MenuItem>
              {channels.map((c) => (
                <MenuItem key={c.id} value={String(c.id)}>
                  {c.code} — {c.name}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        </Stack>
      ) : null}
      {bulkAction === 'create_provisional_customer' ? (
        <Stack spacing={1}>
          <Alert severity="info" variant="outlined" data-testid="dsi-bulk-prov-customer-hint">
            One new <strong>unverified</strong> customer account per selected row; display names follow dealer/source
            evidence.
          </Alert>
          <FormControl size="small" fullWidth>
            <InputLabel id="dsi-bulk-region-inline">Fallback region (optional)</InputLabel>
            <Select
              labelId="dsi-bulk-region-inline"
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
            <InputLabel id="dsi-bulk-channel-inline">Fallback channel (optional)</InputLabel>
            <Select
              labelId="dsi-bulk-channel-inline"
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
            <InputLabel id="dsi-bulk-tier-inline">Partner tier</InputLabel>
            <Select
              labelId="dsi-bulk-tier-inline"
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
            One provisional distributor per selected row; names come from token samples.
          </Alert>
          <TextField
            label="Distributor code override (optional)"
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
      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
        <StewardPendingButton
          variant="outlined"
          pending={bulkPreview.isPending}
          pendingLabel="Previewing…"
          disabled={!bulkFormReady || bulkApply.isPending}
          onClick={() => void bulkPreview.mutateAsync().catch(() => {})}
          data-testid="dsi-bulk-preview-inline"
        >
          Preview bulk steward
        </StewardPendingButton>
        <StewardPendingButton
          variant="contained"
          pending={bulkApply.isPending}
          pendingLabel="Applying…"
          disabled={!applyReady || !bulkFormReady || bulkPreview.isPending}
          onClick={() => void bulkApply.mutateAsync().catch(() => {})}
          data-testid="dsi-bulk-apply"
        >
          Apply bulk steward
        </StewardPendingButton>
      </Stack>
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
    </Stack>
  );
}
