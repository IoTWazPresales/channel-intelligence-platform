'use client';

import { Box, Button, Chip, Stack, Typography } from '@mui/material';
import NextLink from 'next/link';

import { CapabilityStatus } from '../primitives/CapabilityStatus';
import { DomainHeader } from '../primitives/DomainHeader';
import { Panel } from '../primitives/Panel';
import { labDomains, leafStatusLabel, type LeafStatus } from '../shell/labNav';

/**
 * Capability directory: the "what does CIP do" page an unfamiliar operator can read in a minute.
 * Every leaf states what it computes and carries the four-state status so partly built, data-only
 * and planned capability is visible — never hidden, never dressed up as working.
 */
export function DirectorySurface() {
  const leaves = labDomains.flatMap((d) => d.leaves);
  const count = (s: LeafStatus) => leaves.filter((l) => (l.status ?? 'live') === s).length;
  return (
    <Box data-testid="directory-surface">
      <DomainHeader
        title="What CIP does"
        description="Channel Intelligence tracks stock and money from OEM through distributors and retailers to the consumer. Files come in through Data & Stewardship; every other area is derived from those facts. Nothing here is estimated — if a figure is shown, the data layer computed it."
        meta={`${labDomains.length} capability areas · ${leaves.length} workflows · ${count('live')} work today · ${count('partial')} partly built · ${count('substrate')} data only · ${count('planned')} planned`}
      />
      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mb: 2 }} data-testid="directory-legend">
        {(['partial', 'substrate', 'planned'] as LeafStatus[]).map((s) => (
          <Stack key={s} direction="row" spacing={0.75} alignItems="center">
            <CapabilityStatus status={s} />
            <Typography variant="caption" color="text.secondary">
              {s === 'partial' ? 'real code path, a required step is missing or hard-coded — in navigation, marked' : s === 'substrate' ? 'tables or endpoints exist, no working view — directory only' : 'chartered, not built — directory only'}
            </Typography>
          </Stack>
        ))}
        <Typography variant="caption" color="text.secondary">
          Unmarked = {leafStatusLabel.live.toLowerCase()}.
        </Typography>
      </Stack>
      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', md: 'repeat(2, 1fr)', xl: 'repeat(2, 1fr)' } }}>
        {labDomains.map((d) => {
          const Icon = d.icon;
          return (
            <Panel
              key={d.id}
              title={
                <Stack direction="row" spacing={1} alignItems="center">
                  <Icon fontSize="small" color="primary" />
                  <span>{d.label}</span>
                  {d.roles ? <Chip size="small" variant="outlined" label={d.roles.join(' · ')} sx={{ height: 20, fontSize: 11 }} /> : null}
                </Stack>
              }
              subtitle={d.what}
              actions={
                <Button size="small" component={NextLink} href={d.href}>
                  Open
                </Button>
              }
            >
              <Stack spacing={0.75} component="ul" sx={{ listStyle: 'none', m: 0, p: 0 }}>
                {d.leaves.map((l) => {
                  const s = l.status ?? 'live';
                  const dim = s === 'planned';
                  return (
                    <Box component="li" key={l.href} sx={{ display: 'grid', gridTemplateColumns: 'minmax(120px, 34%) 1fr', gap: 1.5, alignItems: 'baseline' }}>
                      <Stack direction="row" spacing={0.75} alignItems="center" flexWrap="wrap" useFlexGap>
                        {dim ? (
                          <Typography variant="body2" color="text.disabled">
                            {l.label}
                          </Typography>
                        ) : (
                          <Typography component={NextLink} href={l.href} variant="body2" sx={{ color: 'text.primary', fontWeight: 500, textDecoration: 'none', '&:hover': { textDecoration: 'underline' } }}>
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
            </Panel>
          );
        })}
      </Box>
    </Box>
  );
}
