'use client';

import { useDraggable } from '@dnd-kit/core';
import { CSS } from '@dnd-kit/utilities';
import SearchOutlinedIcon from '@mui/icons-material/SearchOutlined';
import { Box, InputAdornment, List, ListItemButton, ListItemText, ListSubheader, TextField, Typography } from '@mui/material';
import { useMemo, useState } from 'react';

import { isPickableGoverned } from './catalog';
import { paletteItemId } from '../MetricBrowser';
import type { CatalogV2, V2Measure } from './types';

/**
 * The measures you can build a widget from, on the dashboard home.
 * Same catalog as the editor: one model section per model, then governed metrics.
 */
export function MeasurePalette({
  catalog,
  onPick,
}: {
  catalog: CatalogV2;
  onPick: (measureId: string) => void;
}) {
  const [query, setQuery] = useState('');
  const q = query.trim().toLowerCase();
  const matches = (m: V2Measure) => !m.hidden && (!q || m.label.toLowerCase().includes(q) || m.id.toLowerCase().includes(q));
  const groups = useMemo(
    () =>
      catalog.models
        .map((model) => ({
          model,
          measures: catalog.measures.filter((m) => m.model === model.id && m.kind !== 'governed' && matches(m)),
        }))
        .filter((g) => g.measures.length),
    // matches closes over q; catalog identity is the fetch result.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [catalog, q],
  );
  const governed = catalog.measures.filter((m) => isPickableGoverned(m) && matches(m));

  return (
    <Box data-testid="measure-palette" sx={{ display: 'flex', flexDirection: 'column', minHeight: 0, flex: 1 }}>
      <TextField
        size="small"
        fullWidth
        placeholder="Search measures"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        slotProps={{
          input: {
            startAdornment: (
              <InputAdornment position="start">
                <SearchOutlinedIcon fontSize="small" />
              </InputAdornment>
            ),
          },
        }}
        inputProps={{ 'aria-label': 'Search measures' }}
        sx={{ mb: 1 }}
      />
      <List dense sx={{ overflowY: 'auto', flex: 1, pt: 0, mx: -1 }} data-testid="measure-palette-list">
        {groups.map(({ model, measures }) => (
          <li key={model.id}>
            <ul style={{ padding: 0 }}>
              <ListSubheader sx={{ lineHeight: 1.6, bgcolor: 'transparent' }}>{model.label}</ListSubheader>
              {measures.map((m) => (
                <PaletteRow key={m.id} measure={m} onPick={onPick} />
              ))}
            </ul>
          </li>
        ))}
        {governed.length ? (
          <li>
            <ul style={{ padding: 0 }}>
              <ListSubheader sx={{ lineHeight: 1.6, bgcolor: 'transparent' }}>Governed metrics</ListSubheader>
              {governed.map((m) => (
                <PaletteRow key={m.id} measure={m} onPick={onPick} />
              ))}
            </ul>
          </li>
        ) : null}
        {!groups.length && !governed.length ? (
          <Typography variant="body2" color="text.secondary" sx={{ px: 1, py: 1 }}>
            No measures match.
          </Typography>
        ) : null}
      </List>
    </Box>
  );
}

function PaletteRow({ measure, onPick }: { measure: V2Measure; onPick: (id: string) => void }) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: paletteItemId(measure.id),
    data: { type: 'metric', metricKey: measure.id },
  });
  return (
    <ListItemButton
      ref={setNodeRef}
      dense
      onClick={() => onPick(measure.id)}
      {...attributes}
      {...listeners}
      data-testid={`measure-palette-${measure.id}`}
      sx={{
        borderRadius: 1,
        cursor: 'grab',
        opacity: isDragging ? 0.5 : 1,
        transform: CSS.Translate.toString(transform),
      }}
    >
      <ListItemText
        primary={measure.label}
        secondary={measure.unit ? measure.unit.replace(/_/g, ' ') : undefined}
        primaryTypographyProps={{ variant: 'body2' }}
        secondaryTypographyProps={{ variant: 'caption' }}
      />
    </ListItemButton>
  );
}
