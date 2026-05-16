'use client';

import CloseIcon from '@mui/icons-material/Close';
import {
  Button,
  Checkbox,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  IconButton,
  Stack,
  Typography,
} from '@mui/material';
import { useEffect, useMemo, useState } from 'react';

/** Optional fact fields (resolution / lineage) hidden by default on the inbound shipments grid. */
export const INBOUND_SHIPMENTS_OPTIONAL_FIELDS: { field: string; label: string }[] = [
  { field: 'import_job_id', label: 'Import job ID' },
  { field: 'source_key', label: 'Source key' },
  { field: 'report_type', label: 'Report type' },
  { field: 'product_resolution_status', label: 'Product resolution' },
  { field: 'product_resolution_token', label: 'Product resolution token' },
  { field: 'distributor_resolution_status', label: 'Distributor resolution' },
  { field: 'distributor_resolution_token', label: 'Distributor resolution token' },
  { field: 'customer_resolution_status', label: 'Customer resolution' },
  { field: 'customer_dealer_token', label: 'Customer dealer token' },
  { field: 'order_no', label: 'Order no.' },
  { field: 'delivery_no', label: 'Delivery no.' },
  { field: 'quantity', label: 'Quantity' },
];

export type InboundShipmentsColumnsDialogProps = {
  open: boolean;
  onClose: () => void;
  optionalFields: string[];
  onOptionalFieldsChange: (fields: string[]) => void;
};

export function InboundShipmentsColumnsDialog({
  open,
  onClose,
  optionalFields,
  onOptionalFieldsChange,
}: InboundShipmentsColumnsDialogProps) {
  const [draft, setDraft] = useState<string[]>(optionalFields);
  const draftSet = useMemo(() => new Set(draft), [draft]);

  useEffect(() => {
    if (open) setDraft(optionalFields);
  }, [open, optionalFields]);

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        Additional columns
        <IconButton aria-label="Close" onClick={onClose} size="small">
          <CloseIcon fontSize="small" />
        </IconButton>
      </DialogTitle>
      <DialogContent dividers>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Default columns stay shipping-focused (distributor, product model + SKU, line/cargo state, key dates).
          Enable extra audit fields below.
        </Typography>
        <Stack spacing={0.5}>
          {INBOUND_SHIPMENTS_OPTIONAL_FIELDS.map((c) => (
            <FormControlLabel
              key={c.field}
              control={
                <Checkbox
                  size="small"
                  checked={draftSet.has(c.field)}
                  onChange={(e) => {
                    const on = e.target.checked;
                    setDraft((prev) => {
                      const s = new Set(prev);
                      if (on) s.add(c.field);
                      else s.delete(c.field);
                      return [...s];
                    });
                  }}
                />
              }
              label={c.label}
            />
          ))}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button
          variant="contained"
          onClick={() => {
            onOptionalFieldsChange(draft);
            onClose();
          }}
        >
          Apply
        </Button>
      </DialogActions>
    </Dialog>
  );
}
