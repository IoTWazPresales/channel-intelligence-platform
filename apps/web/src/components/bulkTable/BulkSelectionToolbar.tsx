'use client';

import CloseIcon from '@mui/icons-material/Close';
import PlaylistAddCheckIcon from '@mui/icons-material/PlaylistAddCheck';
import SelectAllIcon from '@mui/icons-material/SelectAll';
import VisibilityOutlinedIcon from '@mui/icons-material/VisibilityOutlined';
import { Button, Chip, Stack, Typography } from '@mui/material';

export type BulkTableSelectionMode = 'normal' | 'selecting';

export function BulkSelectionToolbar({
  mode,
  selectedCount,
  visibleRowCount,
  onEnterSelectionMode,
  onExitSelectionMode,
  onSelectAllVisible,
  onDeselectAll,
  onPreviewDangerAction,
  previewDangerLabel = 'Preview delete',
  previewDangerDisabled,
  busy,
}: {
  mode: BulkTableSelectionMode;
  selectedCount: number;
  visibleRowCount: number;
  onEnterSelectionMode: () => void;
  onExitSelectionMode: () => void;
  onSelectAllVisible: () => void;
  onDeselectAll: () => void;
  onPreviewDangerAction: () => void;
  previewDangerLabel?: string;
  previewDangerDisabled?: boolean;
  busy?: boolean;
}) {
  if (mode === 'normal') {
    return (
      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
        <Button
          size="small"
          variant="outlined"
          startIcon={<PlaylistAddCheckIcon />}
          onClick={onEnterSelectionMode}
          disabled={busy}
        >
          Bulk actions
        </Button>
      </Stack>
    );
  }

  return (
    <Stack
      direction="row"
      spacing={1}
      alignItems="center"
      flexWrap="wrap"
      useFlexGap
      sx={{ rowGap: 1 }}
      data-testid="bulk-selection-toolbar"
    >
      <Chip
        size="small"
        color="primary"
        variant="outlined"
        label={`${selectedCount} selected`}
        data-testid="bulk-selection-count"
      />
      <Typography variant="caption" color="text.secondary" sx={{ alignSelf: 'center' }}>
        {visibleRowCount} visible
      </Typography>
      <Button
        size="small"
        variant="outlined"
        startIcon={<SelectAllIcon />}
        onClick={onSelectAllVisible}
        disabled={busy || visibleRowCount === 0}
      >
        Select visible
      </Button>
      <Button size="small" variant="outlined" onClick={onDeselectAll} disabled={busy || selectedCount === 0}>
        Deselect all
      </Button>
      <Button
        size="small"
        color="error"
        variant="outlined"
        startIcon={<VisibilityOutlinedIcon />}
        onClick={onPreviewDangerAction}
        disabled={Boolean(previewDangerDisabled) || busy || selectedCount === 0}
        data-testid="bulk-preview-danger"
      >
        {previewDangerLabel}
      </Button>
      <Button
        size="small"
        variant="text"
        color="inherit"
        startIcon={<CloseIcon />}
        onClick={onExitSelectionMode}
        disabled={busy}
      >
        Cancel
      </Button>
    </Stack>
  );
}
