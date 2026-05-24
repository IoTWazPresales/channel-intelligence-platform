'use client';

import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  FormControlLabel,
  Radio,
  RadioGroup,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { useEffect, useMemo, useState } from 'react';

import { formatDsiRegionEvidenceDisplay } from './dsiRegionEvidenceDisplay';
import type { DsiRegionEvidenceDto } from './dsiSteward.types';
import { DsiCustomerSearchFields } from './DsiCustomerSearchFields';
import { DsiPendingButton } from './DsiPendingButton';
import type { DsiCandidateRow } from './dsi-mapping-steward-panel';
import {
  buildDupSameEntitySubmitBody,
  buildDuplicateSameEntitySuggestions,
  dealerGroupAccountLabel,
  defaultDupCreateExpanded,
  defaultDupDisplayNameSource,
  firstSuggestionCustomerId,
  isDupSameEntitySubmitDisabled,
  resolveDupDisplayName,
  tokenDisplayLabel,
  type DupDisplayNameSource,
  type DuplicateSameEntitySuggestion,
} from './dsiDuplicateSameEntityDialogLogic';

function fileChannelLabel(
  planRow: Record<string, unknown> | null | undefined,
  candidateContext: Record<string, unknown> | null | undefined
): string {
  const rawToken = planRow?.source_channel_raw_token;
  if (typeof rawToken === 'string' && rawToken.trim()) return rawToken.trim();
  const samples = candidateContext?.source_channel_raw_samples;
  if (Array.isArray(samples)) {
    const parts = samples.filter((x): x is string => typeof x === 'string' && x.trim().length > 0);
    if (parts.length) return parts.join('; ');
  }
  const msg = planRow?.source_channel_resolution_message;
  if (typeof msg === 'string' && msg.trim()) return msg.trim();
  return '—';
}

export function DsiDuplicateSameEntityDialog({
  open,
  onClose,
  pending,
  primaryCandidate,
  peerNormalizedKey,
  peerCandidate,
  planRow,
  onSubmit,
}: {
  open: boolean;
  onClose: () => void;
  pending: boolean;
  primaryCandidate: DsiCandidateRow;
  peerNormalizedKey: string;
  peerCandidate: DsiCandidateRow | null;
  planRow?: Record<string, unknown> | null;
  onSubmit: (body: {
    peer_normalized_key: string;
    customer_id?: number;
    display_name?: string;
    plan_suggested_target_id?: number;
    audit_note?: string;
  }) => void;
}) {
  const histRes =
    planRow && typeof planRow.historical_resolution === 'object' && planRow.historical_resolution !== null
      ? (planRow.historical_resolution as Record<string, unknown>)
      : null;

  const suggestions = useMemo(
    () =>
      buildDuplicateSameEntitySuggestions({
        planSuggestedTargetId: planRow?.suggested_target_id,
        historicalCustomerId: histRes?.customer_id,
        primarySuggestedEntityId: primaryCandidate.suggested_entity_id,
        peerSuggestedEntityId: peerCandidate?.suggested_entity_id,
      }),
    [
      planRow?.suggested_target_id,
      histRes?.customer_id,
      primaryCandidate.suggested_entity_id,
      peerCandidate?.suggested_entity_id,
    ]
  );

  const primaryCtx = (primaryCandidate.context ?? null) as Record<string, unknown> | null;
  const peerCtx = (peerCandidate?.context ?? null) as Record<string, unknown> | null;
  const dealerGroup = dealerGroupAccountLabel(primaryCtx) || dealerGroupAccountLabel(peerCtx);
  const primaryLabel = tokenDisplayLabel(
    primaryCandidate.normalized_key,
    primaryCandidate.sample_raw_values
  );
  const peerLabel = peerCandidate
    ? tokenDisplayLabel(peerCandidate.normalized_key, peerCandidate.sample_raw_values)
    : peerNormalizedKey;

  const regionDisplay = formatDsiRegionEvidenceDisplay(
    planRow?.region_evidence as DsiRegionEvidenceDto | undefined
  );
  const channelLabel = fileChannelLabel(planRow, primaryCtx);

  const [custQ, setCustQ] = useState('');
  const [pickCustomerId, setPickCustomerId] = useState<number | ''>('');
  const [dupAuditNote, setDupAuditNote] = useState('');
  const [dupCreateMode, setDupCreateMode] = useState(false);
  const [dupDisplayNameSource, setDupDisplayNameSource] = useState<DupDisplayNameSource>('primary');
  const [dupCustomName, setDupCustomName] = useState('');
  const [peerKeyError, setPeerKeyError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setCustQ('');
    setDupAuditNote('');
    setPeerKeyError(null);
    setPickCustomerId(firstSuggestionCustomerId(suggestions));
    const expandCreate = defaultDupCreateExpanded(suggestions);
    setDupCreateMode(expandCreate);
    setDupDisplayNameSource(defaultDupDisplayNameSource(suggestions));
    setDupCustomName('');
  }, [open, primaryCandidate.id, peerNormalizedKey, suggestions]);

  const dupDisplayName = useMemo(
    () =>
      resolveDupDisplayName(
        dupDisplayNameSource,
        primaryLabel,
        peerLabel,
        dealerGroup,
        dupCustomName
      ),
    [dupDisplayNameSource, primaryLabel, peerLabel, dealerGroup, dupCustomName]
  );

  const submitDisabled = isDupSameEntitySubmitDisabled({
    peerKey: peerNormalizedKey,
    primaryNormalizedKey: primaryCandidate.normalized_key,
    pickCustomerId,
    dupCreateMode,
    dupDisplayName,
  });

  const applySuggestion = (s: DuplicateSameEntitySuggestion) => {
    setPickCustomerId(s.customerId);
    setDupCreateMode(false);
  };

  const handleSubmit = () => {
    if (peerNormalizedKey.trim() === (primaryCandidate.normalized_key || '').trim()) {
      setPeerKeyError('Peer token must differ from this candidate');
      return;
    }
    setPeerKeyError(null);
    const body = buildDupSameEntitySubmitBody({
      peerKey: peerNormalizedKey,
      pickCustomerId,
      dupCreateMode,
      dupDisplayName,
      planSuggestedTargetId: planRow?.suggested_target_id,
      auditNote: dupAuditNote,
    });
    if (!body) return;
    onSubmit(body);
  };

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm" data-testid="dsi-duplicate-same-entity-dialog">
      <DialogTitle>Same entity — map both tokens</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Alert severity="info" variant="outlined" data-testid="dsi-duplicate-same-entity-intro">
            <Typography variant="body2">
              Map both file tokens to one customer. Each token keeps its own alias; use dealer group and region
              evidence for analytics.
            </Typography>
          </Alert>
          <Typography variant="body2">
            <strong>Primary token:</strong> <code>{primaryCandidate.normalized_key}</code>
            {primaryLabel !== primaryCandidate.normalized_key ? ` (${primaryLabel})` : ''}
          </Typography>
          <Typography variant="body2">
            <strong>Peer token:</strong> <code>{peerNormalizedKey || '—'}</code>
            {peerLabel && peerLabel !== peerNormalizedKey ? ` (${peerLabel})` : ''}
          </Typography>
          {peerKeyError ? (
            <Typography variant="body2" color="error" data-testid="dsi-duplicate-same-entity-peer-error">
              {peerKeyError}
            </Typography>
          ) : null}

          <Typography variant="subtitle2">Map to existing customer</Typography>
          {suggestions.length > 0 ? (
            <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap data-testid="dsi-dup-same-suggestions">
              {suggestions.map((s) => (
                <Chip
                  key={`${s.source}-${s.customerId}`}
                  size="small"
                  variant={pickCustomerId === s.customerId ? 'filled' : 'outlined'}
                  color="primary"
                  label={s.label}
                  onClick={() => applySuggestion(s)}
                  data-testid={`dsi-dup-suggestion-${s.source}`}
                />
              ))}
            </Stack>
          ) : (
            <Typography variant="caption" color="text.secondary">
              No automatic suggestions — search for an existing customer or create a new provisional below.
            </Typography>
          )}
          <DsiCustomerSearchFields
            searchQuery={custQ}
            onSearchQueryChange={setCustQ}
            customerId={pickCustomerId}
            onCustomerIdChange={(id) => {
              setPickCustomerId(id);
              if (id !== '') setDupCreateMode(false);
            }}
            selectTestId="dsi-duplicate-same-entity-customer-select"
            searchTestId="dsi-duplicate-same-entity-customer-search"
            size="medium"
          />

          <Accordion
            expanded={dupCreateMode}
            onChange={(_, exp) => {
              setDupCreateMode(exp);
              if (exp) setPickCustomerId('');
            }}
            data-testid="dsi-duplicate-same-entity-create-accordion"
          >
            <AccordionSummary expandIcon={<ExpandMoreIcon />}>
              <Typography variant="subtitle2">Or create a new provisional customer</Typography>
            </AccordionSummary>
            <AccordionDetails>
              <Stack spacing={2}>
                <Typography variant="body2" color="text.secondary">
                  File evidence (read-only): region{' '}
                  <strong>{regionDisplay?.line ?? '—'}</strong>
                  {regionDisplay?.sourceLabel ? ` (${regionDisplay.sourceLabel})` : ''}; channel{' '}
                  <strong>{channelLabel}</strong>
                </Typography>
                <RadioGroup
                  value={dupDisplayNameSource}
                  onChange={(e) => setDupDisplayNameSource(e.target.value as DupDisplayNameSource)}
                >
                  <FormControlLabel
                    value="primary"
                    control={<Radio size="small" />}
                    label={`Use primary token name (${primaryLabel})`}
                  />
                  <FormControlLabel
                    value="peer"
                    control={<Radio size="small" />}
                    label={`Use peer token name (${peerLabel})`}
                  />
                  <FormControlLabel value="custom" control={<Radio size="small" />} label="Custom name" />
                </RadioGroup>
                {dealerGroup ? (
                  <Typography variant="caption" color="text.secondary">
                    Dealer group account from file: <strong>{dealerGroup}</strong> (used when not custom)
                  </Typography>
                ) : null}
                {dupDisplayNameSource === 'custom' ? (
                  <TextField
                    label="Custom display name"
                    value={dupCustomName}
                    onChange={(e) => setDupCustomName(e.target.value)}
                    fullWidth
                    data-testid="dsi-duplicate-same-entity-custom-name"
                  />
                ) : (
                  <TextField
                    label="Provisional display name"
                    value={dupDisplayName}
                    InputProps={{ readOnly: true }}
                    fullWidth
                    data-testid="dsi-duplicate-same-entity-resolved-name"
                  />
                )}
              </Stack>
            </AccordionDetails>
          </Accordion>

          <TextField
            label="Audit note (optional)"
            value={dupAuditNote}
            onChange={(e) => setDupAuditNote(e.target.value)}
            fullWidth
            multiline
            minRows={2}
            data-testid="dsi-duplicate-same-entity-audit-note"
          />
        </Stack>
      </DialogContent>
      <DialogActions>
        <DsiPendingButton onClick={onClose} disabled={pending}>
          Cancel
        </DsiPendingButton>
        <DsiPendingButton
          variant="contained"
          pending={pending}
          pendingLabel="Mapping…"
          disabled={submitDisabled}
          onClick={handleSubmit}
          data-testid="dsi-duplicate-same-entity-submit"
        >
          Map both to customer
        </DsiPendingButton>
      </DialogActions>
    </Dialog>
  );
}
