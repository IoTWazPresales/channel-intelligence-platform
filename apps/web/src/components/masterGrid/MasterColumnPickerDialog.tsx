'use client';

import {
  Alert,
  Button,
  Checkbox,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  Paper,
  Stack,
  TextField,
  Typography,
} from '@mui/material';

/** Admin master column groups — not commercial-planner ColumnSelectorModal. */
export type MasterColumnPickerGroup = {
  label: string;
  /** AG Grid colIds / field names */
  fields: string[];
};

export function MasterColumnPickerDialog({
  open,
  onClose,
  title,
  groups,
  columnLabelByField,
  visibility,
  onToggle,
  gridReady,
  search,
  onSearchChange,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  groups: MasterColumnPickerGroup[];
  columnLabelByField?: Record<string, string>;
  visibility: Record<string, boolean>;
  onToggle: (field: string, visible: boolean) => void;
  gridReady: boolean;
  search: string;
  onSearchChange: (value: string) => void;
}) {
  const query = search.trim().toLowerCase();
  const blocks = groups
    .map((group) => ({
      label: group.label,
      options: group.fields
        .map((field) => ({
          id: field,
          label: columnLabelByField?.[field] ?? field,
        }))
        .filter(
          (opt) =>
            !query ||
            opt.label.toLowerCase().includes(query) ||
            opt.id.toLowerCase().includes(query)
        ),
    }))
    .filter((group) => group.options.length > 0);

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="md" data-testid="master-column-picker">
      <DialogTitle>{title}</DialogTitle>
      <DialogContent>
        <Stack spacing={1.5} sx={{ mt: 0.5 }}>
          <TextField
            size="small"
            label="Search columns"
            placeholder="Find by label or field key"
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
            data-testid="master-column-picker-search"
          />
          {!gridReady ? (
            <Alert severity="info">Grid is still initializing. Column toggles become available in a moment.</Alert>
          ) : null}
          {blocks.map((group) => (
            <Paper key={group.label} variant="outlined" sx={{ p: 1.25 }}>
              <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
                {group.label}
              </Typography>
              <Stack>
                {group.options.map((opt) => (
                  <FormControlLabel
                    key={opt.id}
                    control={
                      <Checkbox
                        checked={visibility[opt.id] ?? false}
                        onChange={(e) => onToggle(opt.id, e.target.checked)}
                        disabled={!gridReady}
                        data-testid={`master-column-toggle-${opt.id}`}
                      />
                    }
                    label={opt.label}
                  />
                ))}
              </Stack>
            </Paper>
          ))}
          {!blocks.length ? (
            <Typography variant="body2" color="text.secondary">
              No columns match the current search.
            </Typography>
          ) : null}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Done</Button>
      </DialogActions>
    </Dialog>
  );
}
