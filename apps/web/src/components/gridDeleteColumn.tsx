'use client';

import { Button } from '@mui/material';
import type { ColDef, ICellRendererParams } from 'ag-grid-community';

export type GridDeleteColumnOpts = {
  label?: string;
  busy?: boolean;
  /** If `false`, skip the browser confirm dialog. Default: ask before delete. */
  confirm?: boolean;
  /** Overrides the default confirm message. */
  confirmMessage?: string;
};

const DEFAULT_DELETE_CONFIRM = 'Delete this row? This cannot be undone.';

/** Right-pinned Delete action column for row `id`. */
export function gridDeleteColumn<T extends { id: number }>(
  onDelete: (id: number) => void,
  opts?: GridDeleteColumnOpts
): ColDef<T> {
  const label = opts?.label ?? 'Delete';
  const busy = opts?.busy ?? false;
  const skipConfirm = opts?.confirm === false;
  const confirmMessage = opts?.confirmMessage ?? DEFAULT_DELETE_CONFIRM;
  return {
    headerName: '',
    colId: '__delete',
    width: 88,
    maxWidth: 100,
    pinned: 'right',
    sortable: false,
    filter: false,
    resizable: false,
    cellRenderer: (p: ICellRendererParams<T, unknown>) => {
      const id = p.data?.id;
      if (id == null) return null;
      return (
        <Button
          size="small"
          color="error"
          variant="text"
          disabled={busy}
          onClick={() => {
            if (!skipConfirm && !window.confirm(confirmMessage)) return;
            onDelete(id);
          }}
        >
          {label}
        </Button>
      );
    },
  };
}
