'use client';

import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import DownloadIcon from '@mui/icons-material/Download';
import { Button, Stack, Typography } from '@mui/material';
import { useCallback, useState } from 'react';

import type { DsiCandidateRow } from './dsi-mapping-steward-panel';
import {
  buildDsiProductCandidateExportRows,
  copyDsiProductCandidateCsvToClipboard,
  downloadDsiProductCandidateCsv,
} from './dsiProductCandidateExport';

export function DsiProductCandidateExportToolbar({
  candidates,
}: {
  candidates: readonly DsiCandidateRow[];
}) {
  const [copyOk, setCopyOk] = useState(false);
  const rows = buildDsiProductCandidateExportRows(candidates);

  const onDownload = useCallback(() => {
    downloadDsiProductCandidateCsv(rows);
  }, [rows]);

  const onCopy = useCallback(async () => {
    try {
      await copyDsiProductCandidateCsvToClipboard(rows);
      setCopyOk(true);
      window.setTimeout(() => setCopyOk(false), 2000);
    } catch {
      setCopyOk(false);
    }
  }, [rows]);

  if (rows.length === 0) return null;

  return (
    <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
      <Typography variant="caption" color="text.secondary">
        Export {rows.length} product token{rows.length === 1 ? '' : 's'}
      </Typography>
      <Button
        size="small"
        variant="outlined"
        startIcon={<DownloadIcon fontSize="small" />}
        onClick={onDownload}
        data-testid="dsi-product-candidate-export-csv"
      >
        CSV
      </Button>
      <Button
        size="small"
        variant="outlined"
        startIcon={<ContentCopyIcon fontSize="small" />}
        onClick={() => void onCopy()}
        data-testid="dsi-product-candidate-export-clipboard"
      >
        {copyOk ? 'Copied' : 'Clipboard'}
      </Button>
    </Stack>
  );
}
