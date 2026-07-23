'use client';

import { useEffect, useMemo, useState } from 'react';
import { Accordion, AccordionDetails, AccordionSummary, Stack, TextField, Typography } from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';

import { StewardPendingButton } from './StewardPendingButton';
import { prefillGeoCreateFromFileToken } from './geoStewardFilePrefill';
import type { DsiUnresolvedGeoRowDto } from './dsiSteward.types';

export function GeoStewardRegisterFromFile({
  row,
  dimension,
  pending,
  geoBusy,
  onRegister,
  testIdPrefix,
}: {
  row: DsiUnresolvedGeoRowDto;
  dimension: 'channel' | 'region';
  pending: boolean;
  geoBusy: boolean;
  onRegister: (args: { raw_token: string; code: string; name: string }) => Promise<void>;
  testIdPrefix: string;
}) {
  const prefill = useMemo(
    () => prefillGeoCreateFromFileToken(row.raw_token, row.normalized_token, dimension),
    [row.raw_token, row.normalized_token, dimension]
  );
  const [code, setCode] = useState(prefill.code);
  const [name, setName] = useState(prefill.name);
  const [overrideOpen, setOverrideOpen] = useState(false);

  useEffect(() => {
    setCode(prefill.code);
    setName(prefill.name);
  }, [prefill.code, prefill.name, row.normalized_token]);

  const canRegister = Boolean(code.trim() && name.trim());

  return (
    <Stack spacing={1} sx={{ mt: 1 }} data-testid={`${testIdPrefix}-register-from-file`}>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} alignItems={{ sm: 'center' }} flexWrap="wrap" useFlexGap>
        <Typography variant="body2" color="text.secondary" sx={{ flex: '1 1 200px' }}>
          <strong>Suggested from file:</strong> {code} — {name}
        </Typography>
        <StewardPendingButton
          size="small"
          variant="contained"
          pending={pending}
          pendingLabel="Registering…"
          disabled={(geoBusy && !pending) || !canRegister}
          onClick={() =>
            void onRegister({
              raw_token: row.raw_token,
              code: code.trim(),
              name: name.trim(),
            }).catch(() => {})
          }
          data-testid={`${testIdPrefix}-register-btn`}
        >
          Register from file
        </StewardPendingButton>
      </Stack>
      <Accordion
        expanded={overrideOpen}
        onChange={(_, exp) => setOverrideOpen(exp)}
        disableGutters
        elevation={0}
        sx={{ bgcolor: 'transparent', '&:before': { display: 'none' } }}
      >
        <AccordionSummary expandIcon={<ExpandMoreIcon fontSize="small" />}>
          <Typography variant="caption" color="text.secondary">
            Override code and name (optional)
          </Typography>
        </AccordionSummary>
        <AccordionDetails>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
            <TextField
              size="small"
              label={dimension === 'channel' ? 'Channel code' : 'Region code'}
              value={code}
              onChange={(e) => setCode(e.target.value)}
              inputProps={{ 'data-testid': `${testIdPrefix}-code` }}
            />
            <TextField
              size="small"
              label={dimension === 'channel' ? 'Channel name' : 'Region name'}
              value={name}
              onChange={(e) => setName(e.target.value)}
              inputProps={{ 'data-testid': `${testIdPrefix}-name` }}
            />
          </Stack>
        </AccordionDetails>
      </Accordion>
    </Stack>
  );
}
