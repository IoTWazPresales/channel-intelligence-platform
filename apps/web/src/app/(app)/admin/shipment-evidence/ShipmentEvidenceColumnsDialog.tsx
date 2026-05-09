'use client';

import CloseIcon from '@mui/icons-material/Close';
import SearchIcon from '@mui/icons-material/Search';
import {
  Alert,
  Box,
  Button,
  Checkbox,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  IconButton,
  InputAdornment,
  Paper,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { useEffect, useMemo, useState } from 'react';

/** Canonical API fields not shown in the default grid — user can add via this dialog. */
export const SHIPMENT_EVIDENCE_OPTIONAL_FIELDS: { field: string; label: string }[] = [
  { field: 'operating_unit', label: 'Operating unit' },
  { field: 'ship_to_raw', label: 'Ship to' },
  { field: 'order_no', label: 'Order no.' },
  { field: 'order_line', label: 'Order line' },
  { field: 'delivery_no', label: 'Delivery no.' },
  { field: 'invoice_line', label: 'Invoice line' },
  { field: 'customer_item', label: 'Customer item' },
  { field: 'ean_code', label: 'EAN' },
  { field: 'upc_code', label: 'UPC' },
  { field: 'mpor_item_no', label: 'MPOR item no.' },
  { field: 'unit_price', label: 'Unit price' },
  { field: 'schedule_ship_date', label: 'Schedule ship' },
  { field: 'promise_date', label: 'Promise date' },
  { field: 'exwork_date', label: 'Ex-work date' },
  { field: 'erd_date', label: 'ERD date' },
  { field: 'product_id', label: 'Product ID' },
  { field: 'product_resolution_token', label: 'Product resolution token' },
  { field: 'product_resolution_detail', label: 'Product resolution detail' },
  { field: 'distributor_id', label: 'Distributor ID' },
  { field: 'distributor_resolution_token', label: 'Distributor resolution token' },
  { field: 'created_at', label: 'Created at' },
];

export type ShipmentEvidenceColumnsDialogProps = {
  open: boolean;
  onClose: () => void;
  optionalFields: string[];
  onOptionalFieldsChange: (fields: string[]) => void;
  rawKeys: string[];
  onRawKeysChange: (keys: string[]) => void;
  /** Import job used to load distinct raw JSON keys (inferred from filter, row context, or single-job page). */
  catalogJobId: number | null;
  catalogKeys: string[];
  catalogLoading: boolean;
  /** Shown when ``catalogJobId`` is null — parent composes guidance. */
  catalogUnavailableHint: string;
};

const checkboxLabelSx = {
  display: 'flex',
  alignItems: 'flex-start',
  m: 0,
  py: 0.25,
  '& .MuiCheckbox-root': { pt: 0.25 },
  '& .MuiFormControlLabel-label': {
    whiteSpace: 'normal',
    wordBreak: 'break-word',
    lineHeight: 1.35,
    fontSize: '0.875rem',
  },
} as const;

export function ShipmentEvidenceColumnsDialog({
  open,
  onClose,
  optionalFields,
  onOptionalFieldsChange,
  rawKeys,
  onRawKeysChange,
  catalogJobId,
  catalogKeys,
  catalogLoading,
  catalogUnavailableHint,
}: ShipmentEvidenceColumnsDialogProps) {
  const [q, setQ] = useState('');

  useEffect(() => {
    if (!open) {
      setQ('');
    }
  }, [open]);

  const optionalSet = useMemo(() => new Set(optionalFields), [optionalFields]);
  const rawSet = useMemo(() => new Set(rawKeys), [rawKeys]);

  const filteredOptional = useMemo(() => {
    const n = q.trim().toLowerCase();
    if (!n) return SHIPMENT_EVIDENCE_OPTIONAL_FIELDS;
    return SHIPMENT_EVIDENCE_OPTIONAL_FIELDS.filter(
      (c) => c.label.toLowerCase().includes(n) || c.field.toLowerCase().includes(n)
    );
  }, [q]);

  const filteredRaw = useMemo(() => {
    const n = q.trim().toLowerCase();
    if (!n) return catalogKeys;
    return catalogKeys.filter((k) => k.toLowerCase().includes(n));
  }, [catalogKeys, q]);

  const toggleOptional = (field: string, on: boolean) => {
    const next = new Set(optionalSet);
    if (on) next.add(field);
    else next.delete(field);
    onOptionalFieldsChange([...next]);
  };

  const toggleRaw = (key: string, on: boolean) => {
    const next = new Set(rawSet);
    if (on) next.add(key);
    else next.delete(key);
    onRawKeysChange([...next]);
  };

  const onReset = () => {
    onOptionalFieldsChange([]);
    onRawKeysChange([]);
    setQ('');
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth="md"
      fullWidth
      scroll="paper"
      slotProps={{
        paper: {
          sx: { maxHeight: 'min(92vh, 820px)', display: 'flex', flexDirection: 'column' },
        },
      }}
      data-testid="shipment-evidence-column-dialog"
    >
      <DialogTitle sx={{ pr: 6, flexShrink: 0 }}>
        Additional columns
        <IconButton
          aria-label="Close"
          onClick={onClose}
          size="small"
          sx={{ position: 'absolute', right: 8, top: 12, color: 'text.secondary' }}
        >
          <CloseIcon fontSize="small" />
        </IconButton>
      </DialogTitle>
      <DialogContent dividers sx={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', px: 2.5 }}>
        <Stack spacing={2.5} sx={{ flex: 1, minHeight: 0 }}>
          <Typography variant="body2" color="text.secondary">
            Add optional canonical fields to the grid, and when an import job is in scope, pick columns from the
            original file (raw JSON keys). Large page sizes with many raw columns increase payload size.
          </Typography>
          <TextField
            size="small"
            placeholder="Search columns…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            fullWidth
            InputProps={{
              startAdornment: (
                <InputAdornment position="start">
                  <SearchIcon fontSize="small" color="action" />
                </InputAdornment>
              ),
            }}
          />

          <Paper variant="outlined" sx={{ p: 2, display: 'flex', flexDirection: 'column', gap: 1.5, minHeight: 0 }}>
            <Typography variant="subtitle1" fontWeight={600}>
              Canonical fields
            </Typography>
            <Typography variant="caption" color="text.secondary">
              API-backed columns; values match the evidence line record.
            </Typography>
            <Box
              sx={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
                gap: 0.75,
                maxHeight: { xs: 200, sm: 240 },
                overflow: 'auto',
                pr: 0.5,
              }}
            >
              {filteredOptional.map((c) => (
                <FormControlLabel
                  key={c.field}
                  sx={checkboxLabelSx}
                  control={
                    <Checkbox
                      size="small"
                      checked={optionalSet.has(c.field)}
                      onChange={(e) => toggleOptional(c.field, e.target.checked)}
                    />
                  }
                  label={c.label}
                />
              ))}
            </Box>
          </Paper>

          <Paper variant="outlined" sx={{ p: 2, display: 'flex', flexDirection: 'column', gap: 1.5, flex: 1, minHeight: 0 }}>
            <Typography variant="subtitle1" fontWeight={600}>
              Raw import columns
            </Typography>
            <Typography variant="caption" color="text.secondary">
              Values read from <code style={{ fontSize: '0.75rem' }}>raw_source_row</code> for the catalog job.
            </Typography>
            {catalogJobId == null ? (
              <Alert severity="info" sx={{ py: 1 }}>
                {catalogUnavailableHint}
              </Alert>
            ) : catalogLoading ? (
              <Typography variant="body2" color="text.secondary">
                Loading column names…
              </Typography>
            ) : filteredRaw.length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                No raw keys found for this job (or no rows yet).
              </Typography>
            ) : (
              <Box
                sx={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
                  gap: 0.75,
                  flex: 1,
                  minHeight: 160,
                  maxHeight: { xs: 220, sm: 320 },
                  overflow: 'auto',
                  pr: 0.5,
                }}
              >
                {filteredRaw.map((k) => (
                  <FormControlLabel
                    key={k}
                    sx={checkboxLabelSx}
                    control={
                      <Checkbox
                        size="small"
                        checked={rawSet.has(k)}
                        onChange={(e) => toggleRaw(k, e.target.checked)}
                      />
                    }
                    label={
                      <Typography component="span" variant="body2" title={k} sx={{ wordBreak: 'break-all' }}>
                        {k}
                      </Typography>
                    }
                  />
                ))}
              </Box>
            )}
          </Paper>
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 2.5, py: 2, flexShrink: 0, borderTop: 1, borderColor: 'divider' }}>
        <Button onClick={onReset} color="inherit" size="medium">
          Reset all
        </Button>
        <Box sx={{ flex: 1 }} />
        <Button onClick={onClose} variant="contained" color="primary" size="medium">
          Done
        </Button>
      </DialogActions>
    </Dialog>
  );
}
