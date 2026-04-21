'use client';

import AddIcon from '@mui/icons-material/Add';
import DeleteSweepIcon from '@mui/icons-material/DeleteSweep';
import RefreshIcon from '@mui/icons-material/Refresh';
import UploadIcon from '@mui/icons-material/Upload';
import { Button, Stack } from '@mui/material';
import type { SxProps, Theme } from '@mui/material/styles';
import NextLink from 'next/link';

export function ModuleGridToolbar({
  onRefresh,
  onAdd,
  onUpload,
  uploadLabel = 'Paste upload',
  onClearAll,
  clearAllLabel = 'Clear all rows',
  importsHref,
  refreshDisabled,
  busy,
  sx,
}: {
  onRefresh?: () => void;
  onAdd?: () => void;
  onUpload?: () => void;
  uploadLabel?: string;
  /** Remove every row for this module (server); parent should confirm in a dialog first. */
  onClearAll?: () => void;
  clearAllLabel?: string;
  /** When set, shows a secondary navigation control for file-based ingestion (no in-page paste API). */
  importsHref?: string;
  refreshDisabled?: boolean;
  busy?: boolean;
  sx?: SxProps<Theme>;
}) {
  return (
    <Stack direction="row" spacing={1} sx={{ mb: 2, flexWrap: 'wrap', ...sx }} useFlexGap>
      {onRefresh ? (
        <Button
          startIcon={<RefreshIcon />}
          variant="outlined"
          size="small"
          disabled={refreshDisabled || busy}
          onClick={onRefresh}
        >
          Refresh
        </Button>
      ) : null}
      {onClearAll ? (
        <Button
          startIcon={<DeleteSweepIcon />}
          color="warning"
          variant="outlined"
          size="small"
          disabled={busy}
          onClick={onClearAll}
        >
          {clearAllLabel}
        </Button>
      ) : null}
      {onAdd ? (
        <Button startIcon={<AddIcon />} variant="contained" size="small" disabled={busy} onClick={onAdd}>
          Add row
        </Button>
      ) : null}
      {onUpload ? (
        <Button startIcon={<UploadIcon />} variant="outlined" size="small" disabled={busy} onClick={onUpload}>
          {uploadLabel}
        </Button>
      ) : null}
      {importsHref ? (
        <Button component={NextLink} href={importsHref} size="small" variant="outlined">
          Data imports
        </Button>
      ) : null}
    </Stack>
  );
}
