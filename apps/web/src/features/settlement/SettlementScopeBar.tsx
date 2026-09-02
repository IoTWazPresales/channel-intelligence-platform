'use client';

import { Box, Button, MenuItem, Select, Typography } from '@mui/material';
import { alpha, useTheme } from '@mui/material/styles';
import { useRouter, useSearchParams } from 'next/navigation';
import { useCallback } from 'react';

import {
  DEFAULT_SETTLEMENT_SCOPE,
  parseSettlementSavedView,
  parseSettlementStateFilter,
  settlementScopeLabel,
  type SettlementScope,
  type SettlementStateFilter,
} from '@/features/settlement/settlementViews';
import { useSettlementBook } from '@/features/settlement/useSettlementBook';

type Props = {
  scope: SettlementScope;
  onScopeChange: (next: Partial<SettlementScope>) => void;
};

const STATE_OPTIONS: { value: SettlementStateFilter; label: string }[] = [
  { value: 'open', label: 'Open' },
  { value: 'active', label: 'Active' },
  { value: 'ended', label: 'Ended' },
  { value: 'approved', label: 'Approved' },
  { value: 'settled', label: 'Settled' },
  { value: 'blocked', label: 'FX blocked' },
  { value: '', label: 'All states' },
];

export function SettlementScopeBar({ scope, onScopeChange }: Props) {
  const theme = useTheme();
  const line = alpha(theme.palette.common.white, 0.12);
  const router = useRouter();
  const searchParams = useSearchParams();
  const { data: book } = useSettlementBook();

  const applyScopeToUrl = useCallback(
    (patch: { state?: SettlementStateFilter; view?: string }) => {
      const params = new URLSearchParams(searchParams?.toString() ?? '');
      if (patch.state !== undefined) {
        if (patch.state && patch.state !== 'open') params.set('state', patch.state);
        else params.delete('state');
      }
      if (patch.view !== undefined) {
        if (patch.view && patch.view !== 'desk') params.set('view', patch.view);
        else params.delete('view');
      }
      params.set('page', '1');
      const q = params.toString();
      router.replace(q ? `/commercial-planner/cpor-cases?${q}` : '/commercial-planner/cpor-cases', {
        scroll: false,
      });
    },
    [router, searchParams],
  );

  const stateFilter = parseSettlementStateFilter(searchParams?.get('state') ?? scope.state);
  const savedView = parseSettlementSavedView(searchParams?.get('view') ?? scope.savedView);

  return (
    <Box
      data-testid="settlement-scope-bar"
      sx={{
        display: 'flex',
        alignItems: 'flex-end',
        gap: 1.5,
        px: 2.75,
        py: 1.25,
        borderBottom: `1px solid ${line}`,
        bgcolor: '#1a1d23',
        position: 'sticky',
        top: 0,
        zIndex: 3,
        flexWrap: 'wrap',
      }}
    >
      {(['From', 'To', 'BU', 'Customer'] as const).map((label) => (
        <Box key={label} sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
          <Typography
            sx={{
              fontSize: '9.5px',
              color: alpha(theme.palette.text.primary, 0.45),
              textTransform: 'uppercase',
              letterSpacing: '0.07em',
            }}
          >
            {label}
          </Typography>
          <Typography
            sx={{
              fontSize: '12px',
              fontWeight: 500,
              px: 1.25,
              py: 0.625,
              borderRadius: '4px',
              border: `1px solid ${alpha(theme.palette.common.white, 0.2)}`,
              bgcolor: '#1e2229',
              minWidth: 96,
            }}
          >
            {label === 'From' || label === 'To' ? scope.periodLabel : label === 'BU' ? 'All BUs' : 'All customers'}
          </Typography>
        </Box>
      ))}
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
        <Typography
          sx={{
            fontSize: '9.5px',
            color: alpha(theme.palette.text.primary, 0.45),
            textTransform: 'uppercase',
            letterSpacing: '0.07em',
          }}
        >
          State
        </Typography>
        <Select
          size="small"
          value={stateFilter}
          onChange={(e) => {
            const next = e.target.value as SettlementStateFilter;
            onScopeChange({ state: next });
            applyScopeToUrl({ state: next });
          }}
          data-testid="settlement-scope-state"
          sx={{
            minWidth: 120,
            fontSize: '12px',
            bgcolor: '#1e2229',
            '.MuiOutlinedInput-notchedOutline': { borderColor: alpha(theme.palette.common.white, 0.2) },
          }}
        >
          {STATE_OPTIONS.map((opt) => (
            <MenuItem key={opt.value || 'all'} value={opt.value}>
              {opt.label}
              {opt.value === 'open' && book?.open_case_count != null ? ` · ${book.open_case_count}` : ''}
            </MenuItem>
          ))}
        </Select>
      </Box>
      <Button
        size="small"
        sx={{
          fontWeight: 600,
          color: '#bfe8f8',
          bgcolor: alpha('#3db8e8', 0.16),
          border: `1px solid ${alpha('#3db8e8', 0.55)}`,
          px: 2,
          py: 0.75,
          textTransform: 'none',
        }}
        data-testid="settlement-scope-apply"
      >
        Apply
      </Button>
      <Button
        size="small"
        sx={{ color: alpha(theme.palette.text.primary, 0.45), textTransform: 'none' }}
        onClick={() => {
          onScopeChange(DEFAULT_SETTLEMENT_SCOPE);
          applyScopeToUrl({ state: 'open', view: 'desk' });
        }}
        data-testid="settlement-scope-reset"
      >
        Reset
      </Button>
      <Box sx={{ ml: 'auto', display: 'flex', flexDirection: 'column', gap: 0.5, alignItems: 'flex-end' }}>
        <Typography
          sx={{ fontSize: '9.5px', color: alpha(theme.palette.text.primary, 0.45), textTransform: 'uppercase' }}
        >
          Saved view
        </Typography>
        <Select
          size="small"
          value={savedView}
          onChange={(e) => {
            const view = e.target.value as 'desk' | 'all' | 'blocked';
            onScopeChange({ savedView: view });
            if (view === 'blocked') {
              applyScopeToUrl({ view, state: 'blocked' });
              onScopeChange({ state: 'blocked' });
            } else if (view === 'desk') {
              applyScopeToUrl({ view, state: 'open' });
              onScopeChange({ state: 'open' });
            } else {
              applyScopeToUrl({ view, state: '' });
              onScopeChange({ state: '' });
            }
          }}
          data-testid="settlement-saved-view"
          sx={{
            minWidth: 170,
            fontSize: '12px',
            color: '#3db8e8',
            '.MuiOutlinedInput-notchedOutline': { borderColor: alpha('#3db8e8', 0.35) },
          }}
        >
          <MenuItem value="desk">
            Settlement desk · {settlementScopeLabel({ ...scope, state: 'open' }, book?.open_case_count)}
          </MenuItem>
          <MenuItem value="blocked">FX blocked</MenuItem>
          <MenuItem value="all">All cases</MenuItem>
        </Select>
      </Box>
    </Box>
  );
}
