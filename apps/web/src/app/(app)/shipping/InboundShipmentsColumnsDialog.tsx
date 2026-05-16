'use client';

import CloseIcon from '@mui/icons-material/Close';
import {
  Button,
  Checkbox,
  CircularProgress,
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

export type OptionalColumnMeta = { field: string; label: string };

export type InboundShipmentsColumnsDialogProps = {
  open: boolean;
  onClose: () => void;
  optionalFields: string[];
  onOptionalFieldsChange: (fields: string[]) => void;
  columnOptions: OptionalColumnMeta[];
  columnsLoading?: boolean;
};

export function InboundShipmentsColumnsDialog({
  open,
  onClose,
  optionalFields,
  onOptionalFieldsChange,
  columnOptions,
  columnsLoading,
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
          Every other column on <strong>fact_inbound_shipment</strong> can be toggled on below.
        </Typography>
        {columnsLoading ? (
          <Stack alignItems="center" py={2}>
            <CircularProgress size={28} />
          </Stack>
        ) : (
          <Stack spacing={0.5}>
            {columnOptions.map((c) => (
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
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button
          variant="contained"
          disabled={columnsLoading}
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
