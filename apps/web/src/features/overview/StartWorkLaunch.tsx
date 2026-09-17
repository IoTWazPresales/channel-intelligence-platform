'use client';

import AccountTreeOutlinedIcon from '@mui/icons-material/AccountTreeOutlined';
import ListAltOutlinedIcon from '@mui/icons-material/ListAltOutlined';
import LocalOfferOutlinedIcon from '@mui/icons-material/LocalOfferOutlined';
import LocalShippingOutlinedIcon from '@mui/icons-material/LocalShippingOutlined';
import ReceiptLongOutlinedIcon from '@mui/icons-material/ReceiptLongOutlined';
import StorefrontOutlinedIcon from '@mui/icons-material/StorefrontOutlined';
import ViewQuiltOutlinedIcon from '@mui/icons-material/ViewQuiltOutlined';
import { Box, Typography } from '@mui/material';
import type { ReactNode } from 'react';

import { START_GROUP_LABEL, startVerbsForRole, type StartVerb } from '@/features/overview/startWork';
import { ActionCard } from '@/features/workbench-ui/ActionCard';

const START_ICONS: Record<string, ReactNode> = {
  'create-lineup': <ViewQuiltOutlinedIcon fontSize="small" />,
  'open-lineup': <ListAltOutlinedIcon fontSize="small" />,
  'create-promo-plan': <LocalOfferOutlinedIcon fontSize="small" />,
  'import-sell-through': <StorefrontOutlinedIcon fontSize="small" />,
  'import-shipping': <LocalShippingOutlinedIcon fontSize="small" />,
  'steward-queue': <AccountTreeOutlinedIcon fontSize="small" />,
  'settle-case': <ReceiptLongOutlinedIcon fontSize="small" />,
};

export function StartWorkLaunch({
  role,
  hrefFor,
  layout = 'strip',
}: {
  role: string | null | undefined;
  hrefFor?: (verb: StartVerb) => string;
  layout?: 'strip' | 'column';
}) {
  const verbs = startVerbsForRole(role);

  return (
    <Box data-testid="start-work">
      <Typography variant="subtitle1" sx={{ fontWeight: 600, lineHeight: 1.3 }}>
        Start work
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1.25 }}>
        {verbs.length
          ? 'Begin a job from here. Needs attention stays exceptions-only.'
          : 'No start actions for this role. Find a workflow from the directory or Ctrl+K.'}
      </Typography>
      {verbs.length ? (
        <Box
          data-testid="start-work-cards"
          sx={{
            display: 'grid',
            gap: 1,
            gridTemplateColumns:
              layout === 'column'
                ? { xs: 'minmax(0, 1fr)', sm: 'repeat(2, minmax(0, 1fr))' }
                : {
                    xs: 'minmax(0, 1fr)',
                    sm: 'repeat(2, minmax(0, 1fr))',
                    md: 'repeat(3, minmax(0, 1fr))',
                    lg: 'repeat(4, minmax(0, 1fr))',
                  },
          }}
        >
          {verbs.map((v) => (
            <ActionCard
              key={v.id}
              href={hrefFor ? hrefFor(v) : v.href}
              eyebrow={START_GROUP_LABEL[v.group]}
              title={<span data-testid={`start-work-${v.id}`}>{v.label}</span>}
              description={v.what}
              actionLabel="Start"
              icon={START_ICONS[v.id]}
            />
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
