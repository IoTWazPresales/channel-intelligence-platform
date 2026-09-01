'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Box, Typography } from '@mui/material';
import { alpha, useTheme } from '@mui/material/styles';

import {
  activeSpineContainerId,
  shellSpineContainers,
  shellUtilityNav,
  SPINE_DRAWER_WIDTH,
  type SpineContainer,
} from '@/features/shell/spineNav';

export type SpineBadges = Partial<
  Record<'brief' | 'lineup' | 'stock' | 'settlement' | 'response' | 'steward', number | null>
>;

type WorkbenchSpineProps = {
  tenantStamp?: string;
  displayName?: string;
  sessionMeta?: string;
  badges?: SpineBadges;
  role?: string | null;
};

function badgeForContainer(id: string, badges?: SpineBadges): number | null | undefined {
  if (!badges) return undefined;
  return badges[id as keyof SpineBadges];
}

function NavLink({
  container,
  active,
  badge,
}: {
  container: SpineContainer;
  active: boolean;
  badge?: number | null;
}) {
  const theme = useTheme();
  const showBadge = badge != null && badge > 0;
  const alert = showBadge && (container.id === 'brief' || container.id === 'stock' || container.id === 'steward');

  return (
    <Box
      component={Link}
      href={container.href}
      data-testid={`spine-nav-${container.id}`}
      sx={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        px: 1.25,
        py: 1,
        borderRadius: '5px',
        color: active ? theme.palette.text.primary : alpha(theme.palette.text.primary, 0.72),
        bgcolor: active ? 'rgba(61, 184, 232, 0.13)' : 'transparent',
        boxShadow: active ? 'inset 2px 0 0 #3db8e8' : 'none',
        fontSize: '0.8125rem',
        fontWeight: 500,
        textDecoration: 'none',
        '&:hover': {
          bgcolor: active ? 'rgba(61, 184, 232, 0.13)' : alpha(theme.palette.common.white, 0.04),
          color: theme.palette.text.primary,
        },
      }}
    >
      {container.label}
      {showBadge ? (
        <Typography
          component="span"
          sx={{
            fontFamily: '"IBM Plex Mono", monospace',
            fontSize: '10.5px',
            color: alert ? '#e8b4b4' : alpha(theme.palette.text.primary, 0.5),
            fontVariantNumeric: 'tabular-nums',
          }}
        >
          {badge}
        </Typography>
      ) : null}
    </Box>
  );
}

export function WorkbenchSpine({ tenantStamp, displayName, sessionMeta, badges, role }: WorkbenchSpineProps) {
  const theme = useTheme();
  const pathname = usePathname();
  const activeId = activeSpineContainerId(pathname);
  const containers = shellSpineContainers(role);
  const utilities = shellUtilityNav(role);
  const line = alpha(theme.palette.common.white, 0.12);

  return (
    <Box
      component="aside"
      data-testid="workbench-spine"
      sx={{
        width: SPINE_DRAWER_WIDTH,
        minHeight: '100vh',
        bgcolor: '#1a1d23',
        borderRight: `1px solid ${line}`,
        display: 'flex',
        flexDirection: 'column',
        flexShrink: 0,
      }}
    >
      <Box sx={{ px: 2, py: 2.25, borderBottom: `1px solid ${line}` }}>
        <Typography sx={{ fontSize: '0.8125rem', fontWeight: 650, letterSpacing: '-0.01em' }}>
          Channel Intelligence
        </Typography>
        {tenantStamp ? (
          <Typography
            sx={{
              mt: 0.5,
              fontFamily: '"IBM Plex Mono", monospace',
              fontSize: '10px',
              color: alpha(theme.palette.text.primary, 0.5),
              letterSpacing: '0.08em',
              textTransform: 'uppercase',
            }}
          >
            {tenantStamp}
          </Typography>
        ) : null}
      </Box>

      <Box sx={{ px: 1, pt: 1.25, display: 'flex', flexDirection: 'column', gap: '1px' }}>
        {containers.map((c) => (
          <NavLink
            key={c.id}
            container={c}
            active={activeId === c.id}
            badge={badgeForContainer(c.id, badges)}
          />
        ))}
      </Box>

      <Box sx={{ height: 1, bgcolor: line, mx: 2, my: 1.5 }} />

      <Box sx={{ px: 1, display: 'flex', flexDirection: 'column', gap: '1px' }}>
        {utilities.map((u) => (
          <Box
            key={u.href}
            component={Link}
            href={u.href}
            sx={{
              px: 1.25,
              py: 0.75,
              borderRadius: '5px',
              fontSize: '12px',
              color: alpha(theme.palette.text.primary, 0.5),
              textDecoration: 'none',
              '&:hover': { color: alpha(theme.palette.text.primary, 0.72) },
            }}
          >
            {u.label}
          </Box>
        ))}
      </Box>

      <Box sx={{ mt: 'auto', px: 2, pt: 1.5, borderTop: `1px solid ${line}`, pb: 1.75 }}>
        {displayName ? (
          <Typography sx={{ fontSize: '12px', fontWeight: 500, color: alpha(theme.palette.text.primary, 0.72) }}>
            {displayName}
          </Typography>
        ) : null}
        {sessionMeta ? (
          <Typography sx={{ fontSize: '11px', color: alpha(theme.palette.text.primary, 0.5) }}>{sessionMeta}</Typography>
        ) : null}
      </Box>
    </Box>
  );
}

export { SPINE_DRAWER_WIDTH };
