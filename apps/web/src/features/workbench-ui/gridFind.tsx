'use client';

import { Button, Dialog, DialogActions, DialogContent, DialogTitle, TextField } from '@mui/material';
import type { AgGridReact } from 'ag-grid-react';
import { useEffect, useRef, useState, type RefObject } from 'react';

const ALL_VIEW = 'All';

export type SavedFindView = { name: string; find: string };

export function savedFindViewsKey(gridId: string) {
  return `cip.grid.${gridId}.views.v1`;
}

export function readSavedFindViews(raw: string | null): SavedFindView[] {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (v): v is SavedFindView =>
        !!v &&
        typeof v === 'object' &&
        typeof (v as SavedFindView).name === 'string' &&
        (v as SavedFindView).name.trim() !== '' &&
        (v as SavedFindView).name !== ALL_VIEW &&
        typeof (v as SavedFindView).find === 'string',
    );
  } catch {
    return [];
  }
}

/** Draft updates the field immediately. `query` follows 300ms later, matching steward search. */
export function useGridFind() {
  const [draft, setDraft] = useState('');
  const [query, setQuery] = useState('');
  useEffect(() => {
    const t = window.setTimeout(() => setQuery(draft), 300);
    return () => window.clearTimeout(t);
  }, [draft]);
  const apply = (value: string) => {
    setDraft(value);
    setQuery(value);
  };
  return { draft, setDraft, query, apply, clear: () => apply('') };
}

export function GridFindField({
  value,
  onChange,
  testId,
  label = 'Find',
  disabled,
}: {
  value: string;
  onChange: (value: string) => void;
  testId: string;
  label?: string;
  disabled?: boolean;
}) {
  return (
    <TextField
      size="small"
      label={label}
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
      sx={{ minWidth: 220 }}
      data-testid={testId}
    />
  );
}

export function GridCsvExportButton({
  gridRef,
  fileName,
  disabled,
}: {
  gridRef: RefObject<AgGridReact | null>;
  fileName: string;
  disabled?: boolean;
}) {
  return (
    <Button
      size="small"
      variant="outlined"
      disabled={disabled}
      data-testid={`grid-export-${fileName}`}
      onClick={() => gridRef.current?.api?.exportDataAsCsv({ fileName: `${fileName}.csv` })}
    >
      Export
    </Button>
  );
}

/**
 * Find field, named find-views in localStorage, and CSV export for one fact grid.
 * Views store the find text only. Column layout stays on `cip.grid.<id>.optional.v1`.
 */
export function useFactGridChrome(
  gridId: string,
  opts?: { findTestId?: string; exportDisabled?: boolean; findDisabled?: boolean; label?: string },
) {
  const find = useGridFind();
  const gridRef = useRef<AgGridReact>(null);
  const [views, setViews] = useState<SavedFindView[]>([]);
  const [active, setActive] = useState(ALL_VIEW);
  const [saveOpen, setSaveOpen] = useState(false);
  const [saveName, setSaveName] = useState('');

  useEffect(() => {
    setViews(readSavedFindViews(window.localStorage.getItem(savedFindViewsKey(gridId))));
  }, [gridId]);

  const persist = (next: SavedFindView[]) => {
    setViews(next);
    window.localStorage.setItem(savedFindViewsKey(gridId), JSON.stringify(next));
  };

  const selectView = (name: string) => {
    setActive(name);
    if (name === ALL_VIEW) {
      find.apply('');
      return;
    }
    const match = views.find((v) => v.name === name);
    if (match) find.apply(match.find);
  };

  const clearFind = () => {
    find.apply('');
    setActive(ALL_VIEW);
  };

  const commitSave = () => {
    const name = saveName.trim();
    if (!name || name === ALL_VIEW) return;
    persist([...views.filter((v) => v.name !== name), { name, find: find.draft }]);
    setActive(name);
    setSaveOpen(false);
    setSaveName('');
  };

  const filters = (
    <GridFindField
      value={find.draft}
      onChange={find.setDraft}
      testId={opts?.findTestId ?? `grid-find-${gridId}`}
      label={opts?.label ?? 'Find'}
      disabled={opts?.findDisabled}
    />
  );

  const trailing = (
    <>
      <Button
        size="small"
        disabled={!find.draft.trim() || opts?.findDisabled}
        data-testid={`grid-save-view-${gridId}`}
        onClick={() => {
          setSaveName('');
          setSaveOpen(true);
        }}
      >
        Save view
      </Button>
      <GridCsvExportButton gridRef={gridRef} fileName={gridId} disabled={opts?.exportDisabled} />
      <Dialog open={saveOpen} onClose={() => setSaveOpen(false)} fullWidth maxWidth="xs">
        <DialogTitle>Save view</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            label="Name"
            fullWidth
            value={saveName}
            onChange={(e) => setSaveName(e.target.value)}
            data-testid={`grid-save-view-name-${gridId}`}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setSaveOpen(false)}>Cancel</Button>
          <Button
            onClick={commitSave}
            disabled={!saveName.trim() || saveName.trim() === ALL_VIEW}
            variant="contained"
          >
            Save
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );

  return {
    gridRef,
    query: find.query,
    draft: find.draft,
    clearFind,
    filters,
    trailing,
    viewNames: [ALL_VIEW, ...views.map((v) => v.name)],
    active,
    selectView,
  };
}
