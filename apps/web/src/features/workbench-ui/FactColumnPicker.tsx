'use client';

import ViewColumnIcon from '@mui/icons-material/ViewColumn';
import { Button } from '@mui/material';
import { useMemo, useState } from 'react';

import { ColumnPickerDialog } from './ColumnPickerDialog';
import type { FactColumnPickerProps } from './useFactColumns';

/**
 * The one all-fields column picker for Tier A fact grids (N-0034): a thin wrapper over the md
 * `ColumnPickerDialog`, fed by `useFactColumns(gridId).pickerProps`. Groups: fact fields, then
 * Reference (customer / distributor codes, hidden by default so identity cells stay name-only).
 */
export function FactColumnPicker({
  open,
  onClose,
  gridId,
  items,
  selected,
  onToggle,
  onReset,
  gridReady,
  loading,
  title = 'Columns',
  description = 'Default columns stay as they are. Every other field on this grid can be added below; your choice is kept in this browser.',
  factGroupLabel = 'Fact fields',
  'data-testid': testId,
}: FactColumnPickerProps & {
  title?: string;
  description?: string;
  factGroupLabel?: string;
  'data-testid'?: string;
}) {
  const [search, setSearch] = useState('');
  const groups = useMemo(() => {
    const fact = items.filter((i) => i.group !== 'reference').map((i) => i.field);
    const reference = items.filter((i) => i.group === 'reference').map((i) => i.field);
    const out = [{ label: factGroupLabel, fields: fact, loading }];
    if (reference.length) {
      out.push({ label: 'Reference', fields: reference, loading: false });
    }
    return out;
  }, [items, loading, factGroupLabel]);
  const labels = useMemo(() => Object.fromEntries(items.map((i) => [i.field, i.label])), [items]);
  const visibility = useMemo(() => Object.fromEntries(selected.map((f) => [f, true])), [selected]);

  return (
    <ColumnPickerDialog
      size="md"
      data-testid={testId ?? `fact-column-picker-${gridId}`}
      open={open}
      onClose={onClose}
      title={title}
      description={description}
      groups={groups}
      columnLabelByField={labels}
      visibility={visibility}
      onToggle={onToggle}
      onReset={onReset}
      gridReady={gridReady}
      search={search}
      onSearchChange={setSearch}
    />
  );
}

/** Toolbar button that opens the picker; shows how many optional columns are on. */
export function FactColumnsButton({
  onClick,
  count = 0,
  gridId,
}: {
  onClick: () => void;
  count?: number;
  gridId: string;
}) {
  return (
    <Button
      size="small"
      variant="outlined"
      startIcon={<ViewColumnIcon />}
      onClick={onClick}
      aria-haspopup="dialog"
      data-testid={`fact-columns-button-${gridId}`}
    >
      {count > 0 ? `Columns (${count})` : 'Columns'}
    </Button>
  );
}
