'use client';

import { Box, Button, Chip, Stack, Typography } from '@mui/material';
import NextLink from 'next/link';

import { DomainHeader } from '../primitives/DomainHeader';
import { Panel } from '../primitives/Panel';
import { labDomains } from '../shell/labNav';

/**
 * Capability directory: the "what does CIP do" page an unfamiliar operator can read in a minute.
 * Every leaf states what it computes. Unpopulated scaffolds are shown honestly as such.
 */
export function DirectorySurface() {
  return (
    <Box data-testid="directory-surface">
      <DomainHeader
        title="What CIP does"
        description="Channel Intelligence tracks stock and money from OEM through distributors and retailers to the consumer. Files come in through Data & Stewardship; every other area is derived from those facts. Nothing here is estimated — if a figure is shown, the data layer computed it."
        meta="8 capability areas · 47 workflows · 19 import types · ~30 governed metrics"
      />
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
                {d.leaves.map((l) => (
                  <Box component="li" key={l.href} sx={{ display: 'grid', gridTemplateColumns: 'minmax(120px, 34%) 1fr', gap: 1.5, alignItems: 'baseline' }}>
                    {l.populated === false ? (
                      <Typography variant="body2" color="text.disabled">
                        {l.label}
                      </Typography>
                    ) : (
                      <Typography component={NextLink} href={l.href} variant="body2" sx={{ color: 'text.primary', fontWeight: 500, textDecoration: 'none', '&:hover': { textDecoration: 'underline' } }}>
                        {l.label}
                      </Typography>
                    )}
                    <Typography variant="caption" color={l.populated === false ? 'text.disabled' : 'text.secondary'}>
                      {l.populated === false ? 'Not yet populated — route exists, no derived data. Hidden from navigation until it computes something.' : l.what}
                    </Typography>
                  </Box>
                ))}
              </Stack>
            </Panel>
          );
        })}
      </Box>
    </Box>
  );
}
