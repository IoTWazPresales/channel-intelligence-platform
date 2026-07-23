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
  FormControlLabel,
  Radio,
  RadioGroup,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { useEffect, useMemo, useState } from 'react';

import { DsiCustomerSearchFields } from './DsiCustomerSearchFields';
import { StewardPendingButton } from './StewardPendingButton';
import type { DsiCandidateRow } from './dsi-mapping-steward-panel';
import {
  buildDupClusterSameEntitySubmitBody,
  buildDuplicateSameEntitySuggestions,
  dealerGroupAccountLabel,
  defaultDupCreateExpanded,
  defaultDupDisplayNameSource,
  firstSuggestionCustomerId,
  isDupClusterSameEntitySubmitDisabled,
  resolveDupDisplayName,
  tokenDisplayLabel,
  type DupDisplayNameSource,
  type DuplicateSameEntitySuggestion,
} from './dsiDuplicateSameEntityDialogLogic';

export function DsiDuplicateClusterSameEntityDialog({
  open,
  onClose,
  pending,
  importJobId,
  primaryCandidate,
  clusterNormalizedKeys,
  planRow,
  onSubmit,
}: {
  open: boolean;
  onClose: () => void;
  pending: boolean;
  importJobId: number;
  primaryCandidate: DsiCandidateRow;
  clusterNormalizedKeys: readonly string[];
  planRow?: Record<string, unknown> | null;
  onSubmit: (body: {
    normalized_keys: string[];
    customer_id?: number;
    display_name?: string;
    plan_suggested_target_id?: number;
    audit_note?: string;
  }) => void;
}) {
  const keys = useMemo(
    () => [...new Set(clusterNormalizedKeys.map((k) => k.trim()).filter(Boolean))].sort((a, b) => a.localeCompare(b)),
    [clusterNormalizedKeys]
  );

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
        peerSuggestedEntityId: null,
      }),
    [planRow?.suggested_target_id, histRes?.customer_id, primaryCandidate.suggested_entity_id]
  );

  const primaryCtx = (primaryCandidate.context ?? null) as Record<string, unknown> | null;
  const dealerGroup = dealerGroupAccountLabel(primaryCtx);
  const primaryLabel = tokenDisplayLabel(
    primaryCandidate.normalized_key,
    primaryCandidate.sample_raw_values
  );

  const [custQ, setCustQ] = useState('');
  const [pickCustomerId, setPickCustomerId] = useState<number | ''>('');
  const [dupCreateMode, setDupCreateMode] = useState(false);
  const [dupDisplayNameSource, setDupDisplayNameSource] = useState<DupDisplayNameSource>('primary');
  const [dupCustomName, setDupCustomName] = useState('');
  const [auditNote, setAuditNote] = useState('');

  useEffect(() => {
    if (!open) return;
    setCustQ('');
    setPickCustomerId(firstSuggestionCustomerId(suggestions));
    setDupCreateMode(defaultDupCreateExpanded(suggestions));
    setDupDisplayNameSource(defaultDupDisplayNameSource(suggestions));
    setDupCustomName('');
    setAuditNote('');
  }, [open, primaryCandidate.id, suggestions]);

  const dupDisplayName = useMemo(
    () =>
      resolveDupDisplayName(dupDisplayNameSource, primaryLabel, '', dealerGroup, dupCustomName),
    [dupDisplayNameSource, primaryLabel, dealerGroup, dupCustomName]
  );

  const disabled =
    keys.length < 2 ||
    isDupClusterSameEntitySubmitDisabled({
      pickCustomerId,
      dupCreateMode,
      dupDisplayName,
    });

  const applySuggestion = (s: DuplicateSameEntitySuggestion) => {
    setPickCustomerId(s.customerId);
    setDupCreateMode(false);
  };

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm" data-testid="dsi-duplicate-cluster-dialog">
      <DialogTitle>Map duplicate cluster to one customer</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Alert severity="info" variant="outlined">
            Maps all {keys.length} tokens on import job {importJobId} to the same customer in one action. Steward
            confirms the cluster explicitly (pairwise hints between every token are not required).
          </Alert>
          <Typography variant="body2" component="div">
            <strong>Cluster tokens:</strong>
            <ul style={{ margin: '4px 0 0', paddingLeft: 20 }}>
              {keys.map((k) => (
                <li key={k}>
                  <code>{k}</code>
                </li>
              ))}
            </ul>
          </Typography>

          <Typography variant="subtitle2">Map to existing customer</Typography>
          {suggestions.length > 0 ? (
            <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
              {suggestions.map((s) => (
                <Chip
                  key={`${s.source}-${s.customerId}`}
                  size="small"
                  variant={pickCustomerId === s.customerId ? 'filled' : 'outlined'}
                  color="primary"
                  label={s.label}
                  onClick={() => applySuggestion(s)}
                />
              ))}
            </Stack>
          ) : null}
          <DsiCustomerSearchFields
            searchQuery={custQ}
            onSearchQueryChange={setCustQ}
            customerId={pickCustomerId}
            onCustomerIdChange={(id) => {
              setPickCustomerId(id);
              if (id !== '') setDupCreateMode(false);
            }}
            selectTestId="dsi-duplicate-cluster-customer-select"
            searchTestId="dsi-duplicate-cluster-customer-search"
            size="medium"
          />

          <Accordion
            expanded={dupCreateMode}
            onChange={(_, exp) => {
              setDupCreateMode(exp);
              if (exp) setPickCustomerId('');
            }}
          >
            <AccordionSummary expandIcon={<ExpandMoreIcon />}>
              <Typography variant="subtitle2">Or create a new provisional customer</Typography>
            </AccordionSummary>
            <AccordionDetails>
              <Stack spacing={2}>
                <RadioGroup
                  value={dupDisplayNameSource}
                  onChange={(e) => setDupDisplayNameSource(e.target.value as DupDisplayNameSource)}
                >
                  <FormControlLabel
                    value="primary"
                    control={<Radio size="small" />}
                    label={`Use primary token name (${primaryLabel})`}
                  />
                  <FormControlLabel value="custom" control={<Radio size="small" />} label="Custom name" />
                </RadioGroup>
                {dupDisplayNameSource === 'custom' ? (
                  <TextField
                    label="Custom display name"
                    value={dupCustomName}
                    onChange={(e) => setDupCustomName(e.target.value)}
                    fullWidth
                  />
                ) : (
                  <TextField label="Provisional display name" value={dupDisplayName} InputProps={{ readOnly: true }} fullWidth />
                )}
              </Stack>
            </AccordionDetails>
          </Accordion>

          <TextField
            label="Audit note (optional)"
            value={auditNote}
            onChange={(e) => setAuditNote(e.target.value)}
            fullWidth
            multiline
            minRows={2}
          />
        </Stack>
      </DialogContent>
      <DialogActions>
        <StewardPendingButton onClick={onClose} disabled={pending}>
          Cancel
        </StewardPendingButton>
        <StewardPendingButton
          variant="contained"
          pending={pending}
          pendingLabel="Mapping…"
          disabled={disabled}
          data-testid="dsi-duplicate-cluster-submit"
          onClick={() => {
            const body = buildDupClusterSameEntitySubmitBody({
              pickCustomerId,
              dupCreateMode,
              dupDisplayName,
              planSuggestedTargetId: planRow?.suggested_target_id,
              auditNote,
            });
            if (!body || keys.length < 2) return;
            onSubmit({ normalized_keys: keys, ...body });
          }}
        >
          Map cluster ({keys.length} tokens)
        </StewardPendingButton>
      </DialogActions>
    </Dialog>
  );
}
