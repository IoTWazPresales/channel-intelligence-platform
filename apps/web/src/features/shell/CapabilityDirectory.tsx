'use client';

import { Box, Button, Chip, Paper, Stack, Typography } from '@mui/material';
import NextLink from 'next/link';

import { CapabilityStatus } from '@/features/shell/CapabilityStatus';
import { leafStatus, leafStatusLabel, shellNavGroups, type LeafStatus } from '@/features/shell/navConfig';
import { useCurrentUser } from '@/features/shell/useCurrentUser';

const LEGEND: Record<Exclude<LeafStatus, 'live'>, string> = {
  partial: 'real code path, a required step is missing or hard-coded — in navigation, marked',
  substrate: 'tables or endpoints exist, no working view — directory only',
  planned: 'chartered, not built — directory only',
};

/**
 * Capability directory: the "what does CIP do" page an unfamiliar operator can read in a minute.
 * Every leaf the role may see states what it does and carries the four-state status, so partly
 * built, data-only and planned capability is visible — never hidden, never dressed up as working.
 */
export function CapabilityDirectory() {
  const { data: me } = useCurrentUser();
  const role = me?.role ? String(me.role) : null;
  const groups = shellNavGroups(role);
  const leaves = groups.flatMap((g) => g.items);
  const count = (s: LeafStatus) => leaves.filter((l) => leafStatus(l) === s).length;

  return (
    <Box data-testid="capability-directory" sx={{ p: { xs: 1.5, md: 2.5 } }}>
      <Typography variant="h5" sx={{ fontWeight: 600, mb: 0.5 }}>
        What CIP does
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ maxWidth: 880 }}>
        Channel Intelligence tracks stock and money from OEM through distributors and retailers to the consumer. Files come
        in through Data &amp; Stewardship; every other area is derived from those facts. If a figure is shown, the data layer
        computed it.
      </Typography>
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }} data-testid="directory-meta">
        {groups.length} capability areas · {leaves.length} workflows · {count('live')} work today · {count('partial')} partly
        built · {count('substrate')} data only · {count('planned')} planned
      </Typography>
      <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap sx={{ my: 2 }} data-testid="directory-legend">
        {(Object.keys(LEGEND) as Array<keyof typeof LEGEND>).map((s) => (
          <Stack key={s} direction="row" spacing={0.75} alignItems="center">
            <CapabilityStatus status={s} />
            <Typography variant="caption" color="text.secondary">
              {LEGEND[s]}
            </Typography>
          </Stack>
        ))}
        <Typography variant="caption" color="text.secondary">
          Unmarked = {leafStatusLabel.live.toLowerCase()}.
        </Typography>
      </Stack>
      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', md: 'repeat(2, 1fr)' } }}>
        {groups.map((d) => (
          <Paper key={d.id} variant="outlined" sx={{ p: 2 }} data-testid={`directory-domain-${d.id}`}>
            <Stack direction="row" alignItems="flex-start" justifyContent="space-between" spacing={1} sx={{ mb: 1 }}>
              <Box sx={{ minWidth: 0 }}>
                <Stack direction="row" spacing={1} alignItems="center">
                  <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
                    {d.label}
                  </Typography>
                  {d.roles ? <Chip size="small" variant="outlined" label={d.roles.join(' · ')} sx={{ height: 20, fontSize: 11 }} /> : null}
                </Stack>
                {d.what ? (
                  <Typography variant="body2" color="text.secondary">
                    {d.what}
                  </Typography>
                ) : null}
              </Box>
              {d.href ? (
                <Button size="small" component={NextLink} href={d.href}>
                  Open
                </Button>
              ) : null}
            </Stack>
            <Stack spacing={0.75} component="ul" sx={{ listStyle: 'none', m: 0, p: 0 }}>
              {d.items.map((l) => {
                const s = leafStatus(l);
                const dim = s === 'planned';
                return (
                  <Box
                    component="li"
                    key={`${l.href}-${l.label}`}
                    sx={{ display: 'grid', gridTemplateColumns: 'minmax(140px, 36%) 1fr', gap: 1.5, alignItems: 'baseline' }}
                  >
                    <Stack direction="row" spacing={0.75} alignItems="center" flexWrap="wrap" useFlexGap>
                      {dim ? (
                        <Typography variant="body2" color="text.disabled">
                          {l.label}
                        </Typography>
                      ) : (
                        <Typography
                          component={NextLink}
                          href={l.href}
                          variant="body2"
                          sx={{ color: 'text.primary', fontWeight: 500, textDecoration: 'none', '&:hover': { textDecoration: 'underline' } }}
                        >
                          {l.label}
                        </Typography>
                      )}
                      <CapabilityStatus status={s} size="inline" />
                    </Stack>
                    <Typography variant="caption" color={dim ? 'text.disabled' : 'text.secondary'}>
                      {l.what}
                    </Typography>
                  </Box>
                );
              })}
            </Stack>
          </Paper>
        ))}
      </Box>
    </Box>
  );
}
