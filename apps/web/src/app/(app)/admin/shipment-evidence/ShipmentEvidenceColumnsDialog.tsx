'use client';

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
  Divider,
  FormControlLabel,
  InputAdornment,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { useMemo, useState } from 'react';

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
  /** Distinct keys from ``raw_source_row`` for the filtered import job (when set). */
  catalogKeys: string[];
  catalogLoading: boolean;
  importJobIdFilter: string;
};

export function ShipmentEvidenceColumnsDialog({
  open,
  onClose,
  optionalFields,
  onOptionalFieldsChange,
  rawKeys,
  onRawKeysChange,
  catalogKeys,
  catalogLoading,
  importJobIdFilter,
}: ShipmentEvidenceColumnsDialogProps) {
  const [q, setQ] = useState('');

  const jobIdTrim = importJobIdFilter.trim();
  const jobFilterSet = jobIdTrim.length > 0 && Number.isFinite(Number(jobIdTrim)) && Number(jobIdTrim) > 0;

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
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth data-testid="shipment-evidence-column-dialog">
      <DialogTitle>Additional columns</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2}>
          <Typography variant="body2" color="text.secondary">
            Choose optional canonical fields and, when an import job is filtered, columns from the original file
            (raw row). Large page sizes with many raw columns increase payload size.
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
                  <SearchIcon fontSize="small" />
                </InputAdornment>
              ),
            }}
          />
          <Box>
            <Typography variant="subtitle2" sx={{ mb: 1 }}>
              Canonical fields
            </Typography>
            <Box
              sx={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
                gap: 0.5,
                maxHeight: 220,
                overflow: 'auto',
              }}
            >
              {filteredOptional.map((c) => (
                <FormControlLabel
                  key={c.field}
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
          </Box>
          <Divider />
          <Box>
            <Typography variant="subtitle2" sx={{ mb: 1 }}>
              Raw import columns
            </Typography>
            {!jobFilterSet ? (
              <Alert severity="info">
                Enter an <strong>Import job ID</strong> in the filters above to load distinct column names from the
                uploaded file for this job.
              </Alert>
            ) : catalogLoading ? (
              <Typography variant="body2">Loading column names…</Typography>
            ) : filteredRaw.length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                No raw keys found for this job (or no rows yet).
              </Typography>
            ) : (
              <Box
                sx={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
                  gap: 0.5,
                  maxHeight: 260,
                  overflow: 'auto',
                }}
              >
                {filteredRaw.map((k) => (
                  <FormControlLabel
                    key={k}
                    control={
                      <Checkbox
                        size="small"
                        checked={rawSet.has(k)}
                        onChange={(e) => toggleRaw(k, e.target.checked)}
                      />
                    }
                    label={k}
                  />
                ))}
              </Box>
            )}
          </Box>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onReset} color="inherit">
          Reset
        </Button>
        <Button onClick={onClose} variant="contained">
          Done
        </Button>
      </DialogActions>
    </Dialog>
  );
}
