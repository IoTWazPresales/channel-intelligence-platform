'use client';

import ClearIcon from '@mui/icons-material/Clear';
import { Box, Button, Chip, Stack, Tab, Tabs, Typography } from '@mui/material';
import type { ReactNode } from 'react';

/** Shared lens/tab switcher replacing LineupTaskCrumb / StockLensSwitcher / SettlementTaskCrumb. */
export function LensTabs<T extends string>({
  value,
  onChange,
  lenses,
  ariaLabel,
}: {
  value: T;
  onChange: (v: T) => void;
  lenses: { value: T; label: string; count?: number }[];
  ariaLabel: string;
}) {
  return (
    <Tabs
      value={value}
      onChange={(_, v) => onChange(v as T)}
      variant="scrollable"
      scrollButtons="auto"
      allowScrollButtonsMobile
      aria-label={ariaLabel}
      sx={{ minHeight: 40, borderBottom: '1px solid', borderColor: 'divider', '& .MuiTab-root': { minHeight: 40, textTransform: 'none', fontWeight: 500 } }}
    >
      {lenses.map((l) => (
        <Tab
          key={l.value}
          value={l.value}
          label={
            <Stack direction="row" spacing={0.75} alignItems="center">
              <span>{l.label}</span>
              {l.count !== undefined ? (
                <Typography component="span" variant="caption" sx={{ px: 0.75, borderRadius: 1, bgcolor: 'action.selected', fontVariantNumeric: 'tabular-nums' }}>
                  {l.count}
                </Typography>
              ) : null}
            </Stack>
          }
        />
      ))}
    </Tabs>
  );
}

export type ScopeChip = { key: string; label: string; active: boolean; onToggle: () => void; tone?: 'danger' | 'warning' | 'success' | 'default' };

/**
 * Shared scope bar replacing LineupScopeBar / SettlementScopeBar / SettlementShapeBar:
 * chips (one-click presets), a saved-view selector, active-filter summary and a clear action.
 */
export function ScopeBar({
  chips,
  savedViews,
  savedView,
  onSavedView,
  summary,
  onClear,
  trailing,
}: {
  chips: ScopeChip[];
  savedViews?: string[];
  savedView?: string;
  onSavedView?: (v: string) => void;
  summary?: ReactNode;
  onClear?: () => void;
  trailing?: ReactNode;
}) {
  const anyActive = chips.some((c) => c.active);
  return (
    <Box
      role="toolbar"
      aria-label="Scope"
      sx={{
        display: 'flex',
        flexWrap: 'wrap',
        alignItems: 'center',
        gap: 1,
        py: 1,
        px: 1.5,
        border: '1px solid',
        borderColor: 'divider',
        borderRadius: 1.5,
        bgcolor: 'background.paper',
      }}
    >
      {savedViews?.length ? (
        <Stack direction="row" spacing={0.5} sx={{ pr: 1, borderRight: '1px solid', borderColor: 'divider', mr: 0.5 }}>
          {savedViews.map((v) => (
            <Chip
              key={v}
              size="small"
              label={v}
              variant={savedView === v ? 'filled' : 'outlined'}
              color={savedView === v ? 'primary' : 'default'}
              onClick={() => onSavedView?.(v)}
            />
          ))}
        </Stack>
      ) : null}
      {chips.map((c) => (
        <Chip
          key={c.key}
          size="small"
          label={c.label}
          clickable
          onClick={c.onToggle}
          variant={c.active ? 'filled' : 'outlined'}
          color={c.active ? (c.tone === 'danger' ? 'error' : c.tone === 'warning' ? 'warning' : c.tone === 'success' ? 'success' : 'primary') : 'default'}
        />
      ))}
      <Box sx={{ flex: 1 }} />
      {summary ? (
        <Typography variant="caption" color="text.secondary" sx={{ fontVariantNumeric: 'tabular-nums' }}>
          {summary}
        </Typography>
      ) : null}
      {anyActive && onClear ? (
        <Button size="small" startIcon={<ClearIcon fontSize="small" />} onClick={onClear} sx={{ minWidth: 0 }}>
          Clear
        </Button>
      ) : null}
      {trailing}
    </Box>
  );
}

export function StatusChip({ label, tone }: { label: string; tone: 'danger' | 'warning' | 'success' | 'info' | 'neutral' }) {
  const color = tone === 'danger' ? 'error' : tone === 'warning' ? 'warning' : tone === 'success' ? 'success' : tone === 'info' ? 'primary' : 'default';
  return <Chip size="small" label={label} color={color} variant={tone === 'neutral' ? 'outlined' : 'filled'} sx={{ height: 22, fontWeight: 500 }} />;
}
