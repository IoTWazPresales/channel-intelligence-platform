'use client';

import { Button, Dialog, DialogActions, DialogContent, DialogTitle, TextField } from '@mui/material';
import type { ColumnState } from 'ag-grid-community';
import type { AgGridReact } from 'ag-grid-react';
import { useEffect, useRef, useState, type RefObject } from 'react';

const ALL_VIEW = 'All';

/** Sort, visibility, width, and pin for one column. JSON-safe subset of AG Grid column state. */
export type SavedColumnState = {
  colId: string;
  hide?: boolean | null;
  width?: number;
  sort?: 'asc' | 'desc' | null;
  sortIndex?: number | null;
  pinned?: 'left' | 'right' | boolean | null;
};

/**
 * Named snapshot for one fact grid.
 * `optionalFields` is the N-0034 picker selection. Applying a view writes it back
 * through `replaceOptionalFields`, which persists `cip.grid.<id>.optional.v1`.
 * The view list itself stays on `cip.grid.<id>.views.v1`.
 */
export type SavedFindView = {
  name: string;
  find: string;
  optionalFields?: string[];
  columnState?: SavedColumnState[];
  filterModel?: Record<string, unknown> | null;
};

export type FactGridLayout = {
  optionalFields: string[];
  replaceOptionalFields: (fields: string[]) => void;
};

export function savedFindViewsKey(gridId: string) {
  return `cip.grid.${gridId}.views.v1`;
}

function stringList(value: unknown): string[] | undefined {
  if (!Array.isArray(value) || value.some((item) => typeof item !== 'string')) return undefined;
  return value;
}

function columnStateList(value: unknown): SavedColumnState[] | undefined {
  if (!Array.isArray(value)) return undefined;
  const cols: SavedColumnState[] = [];
  for (const item of value) {
    if (!item || typeof item !== 'object') continue;
    const colId = (item as SavedColumnState).colId;
    if (typeof colId !== 'string' || !colId) continue;
    const raw = item as SavedColumnState;
    const sort = raw.sort === 'asc' || raw.sort === 'desc' ? raw.sort : null;
    const pinned = raw.pinned === 'left' || raw.pinned === 'right' || raw.pinned === true ? raw.pinned : null;
    cols.push({
      colId,
      hide: typeof raw.hide === 'boolean' ? raw.hide : null,
      width: typeof raw.width === 'number' ? raw.width : undefined,
      sort,
      sortIndex: typeof raw.sortIndex === 'number' ? raw.sortIndex : null,
      pinned,
    });
  }
  return cols.length ? cols : undefined;
}

export function readSavedFindViews(raw: string | null): SavedFindView[] {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    const views: SavedFindView[] = [];
    for (const item of parsed) {
      if (!item || typeof item !== 'object') continue;
      const rec = item as SavedFindView;
      if (typeof rec.name !== 'string' || rec.name.trim() === '' || rec.name === ALL_VIEW) continue;
      if (typeof rec.find !== 'string') continue;
      const view: SavedFindView = { name: rec.name, find: rec.find };
      const fields = stringList(rec.optionalFields);
      if (fields) view.optionalFields = fields;
      const cols = columnStateList(rec.columnState);
      if (cols) view.columnState = cols;
      if (rec.filterModel === null) view.filterModel = null;
      else if (rec.filterModel && typeof rec.filterModel === 'object' && !Array.isArray(rec.filterModel)) {
        view.filterModel = rec.filterModel;
      }
      views.push(view);
    }
    return views;
  } catch {
    return [];
  }
}

export function factGridLayout(columns: {
  optionalFieldSelection: string[];
  replaceOptionalFields: (fields: string[]) => void;
}): FactGridLayout {
  return {
    optionalFields: columns.optionalFieldSelection,
    replaceOptionalFields: columns.replaceOptionalFields,
  };
}

export function slimColumnState(state: ColumnState[]): SavedColumnState[] {
  return state
    .filter((col) => typeof col.colId === 'string' && col.colId.length > 0)
    .map((col) => ({
      colId: col.colId,
      hide: col.hide ?? null,
      width: typeof col.width === 'number' ? col.width : undefined,
      sort: col.sort === 'asc' || col.sort === 'desc' ? col.sort : null,
      sortIndex: typeof col.sortIndex === 'number' ? col.sortIndex : null,
      pinned: col.pinned === 'left' || col.pinned === 'right' || col.pinned === true ? col.pinned : null,
    }));
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
 * Find, named grid views, and CSV export for one fact grid.
 * A view stores the find text, the picker columns, sort, and filters.
 * Applying it writes the picker columns back onto the N-0034 layout key.
 */
export function useFactGridChrome(
  gridId: string,
  opts?: {
    findTestId?: string;
    exportDisabled?: boolean;
    findDisabled?: boolean;
    label?: string;
    layout?: FactGridLayout;
  },
) {
  const find = useGridFind();
  const gridRef = useRef<AgGridReact>(null);
  const layoutRef = useRef(opts?.layout);
  layoutRef.current = opts?.layout;
  const pendingRef = useRef<SavedFindView | null>(null);
  const [views, setViews] = useState<SavedFindView[]>([]);
  const [active, setActive] = useState(ALL_VIEW);
  const [saveOpen, setSaveOpen] = useState(false);
  const [saveName, setSaveName] = useState('');
  const optionalFields = opts?.layout?.optionalFields;

  useEffect(() => {
    setViews(readSavedFindViews(window.localStorage.getItem(savedFindViewsKey(gridId))));
    setActive(ALL_VIEW);
    pendingRef.current = null;
  }, [gridId]);

  const persist = (next: SavedFindView[]) => {
    setViews(next);
    window.localStorage.setItem(savedFindViewsKey(gridId), JSON.stringify(next));
  };

  const applyGridState = (view: SavedFindView) => {
    const api = gridRef.current?.api;
    if (!api) return false;
    const wanted = view.optionalFields ?? [];
    const have = new Set((api.getColumns() ?? []).map((col) => col.getColId()));
    if (wanted.some((field) => !have.has(`opt:${field}`) && !have.has(field))) return false;
    if (view.columnState?.length) {
      api.applyColumnState({ state: view.columnState, applyOrder: true });
    }
    if ('filterModel' in view) api.setFilterModel(view.filterModel ?? null);
    return true;
  };

  useEffect(() => {
    const view = pendingRef.current;
    if (!view) return;
    const wanted = view.optionalFields ?? [];
    const have = optionalFields ?? [];
    if (wanted.some((field) => !have.includes(field))) return;
    let tries = 0;
    let timer = 0;
    const tick = () => {
      if (pendingRef.current !== view) return;
      if (applyGridState(view)) {
        pendingRef.current = null;
        return;
      }
      tries += 1;
      if (tries > 8) {
        const api = gridRef.current?.api;
        if (api && 'filterModel' in view) api.setFilterModel(view.filterModel ?? null);
        pendingRef.current = null;
        return;
      }
      timer = window.setTimeout(tick, 50);
    };
    timer = window.setTimeout(tick, 0);
    return () => window.clearTimeout(timer);
  }, [optionalFields, active, views]);

  const selectView = (name: string) => {
    setActive(name);
    if (name === ALL_VIEW) {
      find.apply('');
      pendingRef.current = { name: ALL_VIEW, find: '', filterModel: null };
      return;
    }
    const match = views.find((v) => v.name === name);
    if (!match) return;
    find.apply(match.find);
    if (match.optionalFields) layoutRef.current?.replaceOptionalFields(match.optionalFields);
    pendingRef.current = match;
  };

  const clearFind = () => {
    find.apply('');
    setActive(ALL_VIEW);
    pendingRef.current = { name: ALL_VIEW, find: '', filterModel: null };
  };

  const commitSave = () => {
    const name = saveName.trim();
    if (!name || name === ALL_VIEW) return;
    const api = gridRef.current?.api;
    const view: SavedFindView = {
      name,
      find: find.draft,
      optionalFields: layoutRef.current?.optionalFields ?? [],
      columnState: api ? slimColumnState(api.getColumnState()) : [],
      filterModel: api ? (api.getFilterModel() as Record<string, unknown>) : null,
    };
    persist([...views.filter((v) => v.name !== name), view]);
    setActive(name);
    setSaveOpen(false);
    setSaveName('');
  };

  const deleteActive = () => {
    if (active === ALL_VIEW) return;
    persist(views.filter((v) => v.name !== active));
    find.apply('');
    setActive(ALL_VIEW);
    pendingRef.current = { name: ALL_VIEW, find: '', filterModel: null };
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
        disabled={opts?.findDisabled}
        data-testid={`grid-save-view-${gridId}`}
        onClick={() => {
          setSaveName(active === ALL_VIEW ? '' : active);
          setSaveOpen(true);
        }}
      >
        Save view
      </Button>
      {active !== ALL_VIEW ? (
        <Button size="small" color="inherit" data-testid={`grid-delete-view-${gridId}`} onClick={deleteActive}>
          Delete view
        </Button>
      ) : null}
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
