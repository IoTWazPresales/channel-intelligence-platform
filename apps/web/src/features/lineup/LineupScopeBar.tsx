'use client';

import { Box, Button, MenuItem, Select, Typography } from '@mui/material';
import { alpha, useTheme } from '@mui/material/styles';
import { useRouter, useSearchParams } from 'next/navigation';
import { useCallback } from 'react';

import { parseLineupApprovalFilter, type LineupScope } from '@/features/lineup/lineupViews';

type Props = {
  scope: LineupScope;
  onScopeChange: (next: Partial<LineupScope>) => void;
};

export function LineupScopeBar({ scope, onScopeChange }: Props) {
  const theme = useTheme();
  const line = alpha(theme.palette.common.white, 0.12);
  const router = useRouter();
  const searchParams = useSearchParams();

  const setApprovalFilter = useCallback(
    (approval: 'all' | 'pending') => {
      const params = new URLSearchParams(searchParams?.toString() ?? '');
      if (approval === 'pending') params.set('approval', 'pending');
      else params.delete('approval');
      const q = params.toString();
      router.replace(q ? `/lineup?${q}` : '/lineup', { scroll: false });
      onScopeChange({ approval });
    },
    [onScopeChange, router, searchParams],
  );

  const approvalFilter = parseLineupApprovalFilter(searchParams?.get('approval'));

  return (
    <Box
      data-testid="lineup-scope-bar"
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
          <Typography sx={{ fontSize: '9.5px', color: alpha(theme.palette.text.primary, 0.45), textTransform: 'uppercase', letterSpacing: '0.07em' }}>
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
            {label === 'From' || label === 'To' ? '26Q3' : label === 'BU' ? 'All BUs' : 'All customers'}
          </Typography>
        </Box>
      ))}
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
        <Typography sx={{ fontSize: '9.5px', color: alpha(theme.palette.text.primary, 0.45), textTransform: 'uppercase', letterSpacing: '0.07em' }}>
          Period
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
          {scope.periodLabel}
        </Typography>
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
      >
        Apply
      </Button>
      <Button size="small" sx={{ color: alpha(theme.palette.text.primary, 0.45), textTransform: 'none' }}>
        Reset
      </Button>
      <Box sx={{ ml: 'auto', display: 'flex', flexDirection: 'column', gap: 0.5, alignItems: 'flex-end' }}>
        <Typography sx={{ fontSize: '9.5px', color: alpha(theme.palette.text.primary, 0.45), textTransform: 'uppercase' }}>
          Saved view
        </Typography>
        <Select
          size="small"
          value={approvalFilter}
          onChange={(e) => setApprovalFilter(e.target.value === 'pending' ? 'pending' : 'all')}
          data-testid="lineup-saved-view"
          sx={{
            minWidth: 170,
            fontSize: '12px',
            color: '#3db8e8',
            '.MuiOutlinedInput-notchedOutline': { borderColor: alpha('#3db8e8', 0.35) },
          }}
        >
          <MenuItem value="all">Lineup · 26Q3</MenuItem>
          <MenuItem value="pending">Pending approval</MenuItem>
        </Select>
      </Box>
    </Box>
  );
}
