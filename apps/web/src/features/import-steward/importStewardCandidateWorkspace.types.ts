import type { MouseEvent, ReactNode } from 'react';
import type { SxProps, Theme } from '@mui/material/styles';

/** Minimal row shape the workspace table requires (domain rows may extend this). */
export type ImportStewardCandidateRowBase = {
  id: number;
  entity_type: string;
  normalized_key: string;
  row_count: number;
  total_units: number | null;
  total_reported_value: number | null;
  sample_raw_values: string[] | null;
  status: string;
  match_reason: string | null;
  confidence_score: number | null;
  context: Record<string, unknown> | null;
};

export type ImportStewardWorkspaceColumnAlign = 'left' | 'right' | 'center';

export type ImportStewardWorkspaceColumn<TRow extends ImportStewardCandidateRowBase> = {
  /** Stable column key for React list keys */
  id: string;
  header: ReactNode;
  align?: ImportStewardWorkspaceColumnAlign;
  /** Table cell maxWidth / width passthrough */
  cellSx?: SxProps<Theme>;
  cell: (row: TRow) => ReactNode;
};

export type ImportStewardSelectionHeaderState = 'none' | 'partial' | 'all';

/** Optional row selection (checkbox column + header tri-state). */
export type ImportStewardSelectionModel = {
  selectedIds: Set<number>;
  onToggle: (rowId: number, event?: MouseEvent) => void;
  onToggleAllVisible: () => void;
  visibleRowIds: number[];
  headerState: ImportStewardSelectionHeaderState;
};

export type ImportStewardListCopy = {
  title: ReactNode;
  description: ReactNode;
  /** Rendered when `importJobId` is null (e.g. prompt to pick a job). */
  missingJobPrompt?: ReactNode;
  /** Shown when the job is set but there are zero open (non-terminal) rows. */
  emptyOpenListMessage?: ReactNode;
  /** Shown when filters yield zero visible rows but open rows exist. */
  emptyFilteredMessage?: ReactNode;
  /** Loading label while the list query is resolving. */
  loadingLabel?: ReactNode;
  /** Shown above the skeleton while the list query is resolving. */
  loadingMessage?: ReactNode;
};

export type ImportStewardWorkspaceBusyOverlay = {
  /** Short label on the in-table overlay (e.g. "Applying bulk steward…"). */
  message?: ReactNode;
};

export type ImportStewardActionFeedback = {
  message: string;
  severity: 'error' | 'warning';
  onDismiss: () => void;
};

export type ImportStewardCandidateWorkspaceProps<TRow extends ImportStewardCandidateRowBase> = {
  /** Opaque domain discriminator for analytics / future multi-domain shells */
  listDomainId: string;
  importJobId: number | null;
  copy: ImportStewardListCopy;
  /** Open (non-terminal) rows — used for bulk toolbar counts / selection scope */
  openRows: TRow[];
  /** Rows after client filters (subset of `openRows`) */
  filteredRows: TRow[];
  isLoading: boolean;
  busy: boolean;
  busyOverlay?: ImportStewardWorkspaceBusyOverlay | null;
  /** Skeleton row count when `isLoading` (default 8). */
  skeletonRowCount?: number;
  columns: ImportStewardWorkspaceColumn<TRow>[];
  selection?: ImportStewardSelectionModel;
  /** Rendered after list title/description — e.g. entity tabs that filter the table below. */
  tabsSlot?: ReactNode;
  filtersSlot?: ReactNode;
  /** Rendered directly under toolbar and above filters (e.g. bulk steward form). */
  bulkFormSlot?: ReactNode;
  toolbarSlot?: ReactNode;
  actionFeedback?: ImportStewardActionFeedback | null;
  getRowSx?: (row: TRow) => SxProps<Theme> | undefined;
  /** Root Paper `data-testid` */
  rootTestId?: string;
  /** Region wrapping filters (a11y + tests) */
  filtersRegionTestId?: string;
  filtersRegionAriaLabel?: string;
  /** Focus a row for single-row steward (clicks on the checkbox column are ignored). */
  onRowClick?: (row: TRow) => void;
  /** When true, omit the outer Paper wrapper (use inside another container). */
  embedded?: boolean;
  /**
   * When true with `embedded`, tabs/filters/toolbar stay fixed and the candidate table scrolls
   * inside a flex child (`flex: 1`, `overflow: auto`). Use inside height-capped steward layouts.
   */
  embeddedScrollableTable?: boolean;
  /** Keep table chrome (and filter-empty row) when `openRows` is empty but filters are active. */
  keepTableWhenFilterEmpty?: boolean;
  /** When set, replaces the candidate table (e.g. Region & channel catalog stewardship tab). */
  mainContentSlot?: ReactNode;
};
