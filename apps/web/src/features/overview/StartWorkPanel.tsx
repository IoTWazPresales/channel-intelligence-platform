'use client';

import { Box, Card, CardActionArea, CardContent, Typography } from '@mui/material';
import NextLink from 'next/link';

import { startVerbsForRole } from '@/features/overview/startWork';
import { useCurrentUser } from '@/features/shell/useCurrentUser';

export function StartWorkPanel() {
  const { data: me } = useCurrentUser();
  const role = me?.role ? String(me.role) : null;
  const verbs = startVerbsForRole(role);

  return (
    <Box data-testid="start-work">
      <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
        Start work
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
        {verbs.length
          ? 'Jobs you can begin from here. Needs attention stays exceptions-only.'
          : 'No start actions for this role. Find a workflow from the directory or Ctrl+K.'}
      </Typography>
      {verbs.length ? (
        <Box
          sx={{
            display: 'grid',
            gap: 1,
            gridTemplateColumns: { xs: 'repeat(2, 1fr)', md: 'repeat(3, 1fr)', lg: 'repeat(4, 1fr)' },
          }}
        >
          {verbs.map((v) => (
            <Card key={v.id} variant="outlined" sx={{ boxShadow: 'none' }}>
              <CardActionArea component={NextLink} href={v.href} sx={{ height: '100%' }}>
                <CardContent sx={{ py: 1.25, '&:last-child': { pb: 1.25 } }}>
                  <Typography variant="body2" sx={{ fontWeight: 600 }} data-testid={`start-work-${v.id}`}>
                    {v.label}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {v.what}
                  </Typography>
                </CardContent>
              </CardActionArea>
            </Card>
          ))}
        </Box>
      ) : (
        <Typography variant="body2" color="text.secondary">
          Nothing this role can start from Overview. The capability directory lists every workflow.
        </Typography>
      )}
    </Box>
  );
}
