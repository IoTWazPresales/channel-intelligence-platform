'use client';

import CloudUploadOutlinedIcon from '@mui/icons-material/CloudUploadOutlined';
import { Alert, Box, Button, Chip, LinearProgress, Stack, Typography } from '@mui/material';
import { useCallback, useState } from 'react';

const DEFAULT_ACCEPT =
  '.csv,.xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv';

export type ImportFileUploadZoneProps = {
  /** When set, the large drop zone is collapsed unless `expanded` is true. */
  boundJobId?: number | null;
  boundJobFileName?: string | null;
  boundJobStage?: string | null;
  expanded: boolean;
  onExpandedChange: (expanded: boolean) => void;
  canUpload: boolean;
  pending?: boolean;
  error?: string | null;
  onFile: (file: File | undefined) => void;
  title?: string;
  subtitle?: string;
  testIdPrefix?: string;
};

export function ImportFileUploadZone({
  boundJobId,
  boundJobFileName,
  boundJobStage,
  expanded,
  onExpandedChange,
  canUpload,
  pending = false,
  error,
  onFile,
  title = 'Drop CSV or XLSX here',
  subtitle = 'Or choose a file.',
  testIdPrefix = 'import-upload',
}: ImportFileUploadZoneProps) {
  const [dragActive, setDragActive] = useState(false);
  const collapsed = boundJobId != null && !expanded;

  const handleDrop = useCallback(
    (file: File | undefined) => {
      setDragActive(false);
      onFile(file);
      if (file) onExpandedChange(false);
    },
    [onExpandedChange, onFile]
  );

  if (collapsed) {
    return (
      <Stack spacing={1} data-testid={`${testIdPrefix}-compact`}>
        <Box
          sx={{
            display: 'flex',
            flexWrap: 'wrap',
            alignItems: 'center',
            gap: 1,
            px: 1.5,
            py: 1,
            border: '1px solid',
            borderColor: 'divider',
            borderRadius: 1,
            bgcolor: 'action.hover',
          }}
        >
          <Typography variant="body2" fontWeight={600}>
            Job <strong>#{boundJobId}</strong>
          </Typography>
          {boundJobFileName ? (
            <Typography variant="body2" color="text.secondary" sx={{ maxWidth: 360 }} noWrap title={boundJobFileName}>
              {boundJobFileName}
            </Typography>
          ) : null}
          {boundJobStage ? (
            <Chip size="small" label={boundJobStage} variant="outlined" data-testid={`${testIdPrefix}-stage-chip`} />
          ) : null}
          <Button
            size="small"
            variant="outlined"
            sx={{ ml: 'auto' }}
            onClick={() => onExpandedChange(true)}
            data-testid={`${testIdPrefix}-replace-btn`}
          >
            Upload different file
          </Button>
        </Box>
        {pending ? <LinearProgress data-testid={`${testIdPrefix}-pending`} /> : null}
        {error ? (
          <Alert severity="error" data-testid={`${testIdPrefix}-error`}>
            {error}
          </Alert>
        ) : null}
      </Stack>
    );
  }

  return (
    <Stack spacing={1} data-testid={`${testIdPrefix}-dropzone`}>
      {boundJobId != null ? (
        <Button
          size="small"
          variant="text"
          sx={{ alignSelf: 'flex-start' }}
          onClick={() => onExpandedChange(false)}
          data-testid={`${testIdPrefix}-collapse-btn`}
        >
          Back to job #{boundJobId}
        </Button>
      ) : null}
      <Box
        onDragEnter={(e) => {
          e.preventDefault();
          setDragActive(true);
        }}
        onDragOver={(e) => {
          e.preventDefault();
        }}
        onDragLeave={() => setDragActive(false)}
        onDrop={(e) => {
          e.preventDefault();
          handleDrop(e.dataTransfer.files?.[0]);
        }}
        sx={{
          border: '2px dashed',
          borderColor: dragActive ? 'primary.main' : 'divider',
          borderRadius: 2,
          px: 3,
          py: 4,
          textAlign: 'center',
          bgcolor: dragActive ? 'action.selected' : 'action.hover',
        }}
      >
        <CloudUploadOutlinedIcon sx={{ fontSize: 40, color: 'primary.main', mb: 1 }} />
        <Typography variant="subtitle1" fontWeight={600}>
          {title}
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          {subtitle}
        </Typography>
        <Button variant="contained" component="label" disabled={!canUpload || pending}>
          Choose file
          <input
            hidden
            type="file"
            accept={DEFAULT_ACCEPT}
            onChange={(e) => {
              handleDrop(e.target.files?.[0]);
              e.target.value = '';
            }}
          />
        </Button>
      </Box>
      {pending ? <LinearProgress data-testid={`${testIdPrefix}-pending`} /> : null}
      {error ? (
        <Alert severity="error" data-testid={`${testIdPrefix}-error`}>
          {error}
        </Alert>
      ) : null}
    </Stack>
  );
}
