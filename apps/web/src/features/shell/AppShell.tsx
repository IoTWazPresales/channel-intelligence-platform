'use client';

import LogoutOutlinedIcon from '@mui/icons-material/LogoutOutlined';
import MenuIcon from '@mui/icons-material/Menu';
import SettingsOutlinedIcon from '@mui/icons-material/SettingsOutlined';
import ViewCompactOutlinedIcon from '@mui/icons-material/ViewCompactOutlined';
import {
  AppBar,
  Box,
  Drawer,
  IconButton,
  Toolbar,
  Tooltip,
  Typography,
} from '@mui/material';
import { alpha, useTheme } from '@mui/material/styles';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { ReactNode, useCallback, useState } from 'react';
import { useQuery } from '@tanstack/react-query';

import { GlobalBackgroundTasksIndicator } from '@/features/background-tasks/GlobalBackgroundTasksIndicator';
import { WorkbenchSpine, SPINE_DRAWER_WIDTH, type SpineBadges } from '@/features/shell/WorkbenchSpine';
import { shellSpineContainers, shellUtilityNav } from '@/features/shell/spineNav';
import { useCurrentUser, useInvalidateCurrentUser, AUTH_ME_QUERY_KEY } from '@/features/shell/useCurrentUser';
import { apiGet, apiPost } from '@/lib/api';
import { clearAuthToken } from '@/lib/authSession';
import { useUiStore } from '@/stores/uiStore';
import { useQueryClient } from '@tanstack/react-query';

type BriefSignalsMeta = {
  tenant_stamp?: string;
  spine_badges?: SpineBadges;
};

function roleLabel(role: string | undefined | null): string {
  if (!role) return 'guest';
  return role.replace(/_/g, ' ');
}

function isBriefChromeRoute(pathname: string): boolean {
  return pathname === '/brief' || pathname.startsWith('/brief/');
}

export function AppShell({ title, children }: { title: string; children: ReactNode }) {
  const theme = useTheme();
  const router = useRouter();
  const pathname = usePathname();
  const briefChrome = isBriefChromeRoute(pathname);
  const [mobileOpen, setMobileOpen] = useState(false);
  const { density, setDensity } = useUiStore((s) => s);
  const { data: me, isError: meError } = useCurrentUser();
  const invalidateMe = useInvalidateCurrentUser();
  const qc = useQueryClient();
  const [logoutBusy, setLogoutBusy] = useState(false);

  const displayName =
    (me?.display_name && me.display_name.trim()) ||
    (me?.email && me.email.trim()) ||
    (meError ? 'Signed out' : '…');

  const { data: briefMeta } = useQuery({
    queryKey: ['brief', 'signals-meta'],
    queryFn: ({ signal }) => apiGet<BriefSignalsMeta>('/api/v1/brief/signals', { signal }),
    staleTime: 60_000,
    retry: 1,
  });

  const handleLogout = useCallback(async () => {
    if (logoutBusy) return;
    setLogoutBusy(true);
    try {
      try {
        await apiPost('/api/v1/auth/logout');
      } catch {
        /* revoke best-effort */
      }
      clearAuthToken();
      await invalidateMe();
      await qc.resetQueries({ queryKey: AUTH_ME_QUERY_KEY });
      router.replace('/login');
    } finally {
      setLogoutBusy(false);
    }
  }, [invalidateMe, logoutBusy, qc, router]);

  const spineProps = {
    tenantStamp: briefMeta?.tenant_stamp,
    displayName,
    sessionMeta: me ? `${roleLabel(String(me.role))} · session` : undefined,
    badges: briefMeta?.spine_badges,
    role: me?.role ? String(me.role) : null,
  };

  const spine = <WorkbenchSpine {...spineProps} />;

  return (
    <Box
      sx={{
        display: 'grid',
        gridTemplateColumns: { xs: '1fr', md: `${SPINE_DRAWER_WIDTH}px 1fr` },
        minHeight: '100vh',
        bgcolor: '#14161a',
      }}
    >
      <Box component="nav" sx={{ display: { xs: 'none', md: 'block' } }}>
        {spine}
      </Box>

      <Drawer
        variant="temporary"
        open={mobileOpen}
        onClose={() => setMobileOpen(false)}
        ModalProps={{ keepMounted: true }}
        sx={{
          display: { xs: 'block', md: 'none' },
          '& .MuiDrawer-paper': { width: SPINE_DRAWER_WIDTH, boxSizing: 'border-box', bgcolor: '#1a1d23' },
        }}
      >
        {spine}
      </Drawer>

      <Box sx={{ display: 'flex', flexDirection: 'column', minWidth: 0, minHeight: '100vh' }}>
        {briefChrome ? (
          <Box
            sx={{
              display: { xs: 'flex', md: 'none' },
              alignItems: 'center',
              gap: 1,
              px: 1,
              py: 0.5,
              borderBottom: `1px solid ${alpha(theme.palette.common.white, 0.12)}`,
            }}
          >
            <IconButton color="inherit" aria-label="Open navigation menu" onClick={() => setMobileOpen(true)}>
              <MenuIcon />
            </IconButton>
            <Typography variant="subtitle2" sx={{ flexGrow: 1, fontWeight: 600 }}>
              Brief
            </Typography>
            {!meError ? (
              <IconButton
                color="inherit"
                onClick={() => void handleLogout()}
                disabled={logoutBusy}
                aria-label="Sign out"
                data-testid="shell-sign-out"
              >
                <LogoutOutlinedIcon fontSize="small" />
              </IconButton>
            ) : null}
          </Box>
        ) : (
          <AppBar
            position="sticky"
            elevation={0}
            sx={{
              bgcolor: alpha('#14161a', 0.92),
              backdropFilter: 'blur(12px)',
              borderBottom: `1px solid ${alpha(theme.palette.common.white, 0.12)}`,
              color: 'text.primary',
            }}
          >
            <Toolbar sx={{ gap: 1, minHeight: 48 }}>
              <IconButton
                color="inherit"
                edge="start"
                aria-label="Open navigation menu"
                onClick={() => setMobileOpen(true)}
                sx={{ mr: 0.5, display: { md: 'none' } }}
              >
                <MenuIcon />
              </IconButton>
              <Typography variant="subtitle1" sx={{ flexGrow: 1, fontWeight: 600, fontSize: '1rem' }}>
                {title}
              </Typography>
              <GlobalBackgroundTasksIndicator />
              <Tooltip title="Settings">
                <IconButton color="inherit" component={Link} href="/settings" aria-label="Settings">
                  <SettingsOutlinedIcon />
                </IconButton>
              </Tooltip>
              <Tooltip title={density === 'compact' ? 'Comfortable row height' : 'Compact row height'}>
                <IconButton
                  color="inherit"
                  onClick={() => setDensity(density === 'compact' ? 'comfortable' : 'compact')}
                  aria-label="Toggle table density"
                >
                  <ViewCompactOutlinedIcon />
                </IconButton>
              </Tooltip>
              {!meError ? (
                <Tooltip title="Sign out">
                  <IconButton
                    color="inherit"
                    onClick={() => void handleLogout()}
                    disabled={logoutBusy}
                    aria-label="Sign out"
                    data-testid="shell-sign-out"
                  >
                    <LogoutOutlinedIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
              ) : null}
            </Toolbar>
          </AppBar>
        )}

        <Box component="main" sx={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
          {children}
        </Box>
      </Box>
    </Box>
  );
}

/** @deprecated legacy group nav — spine containers are canonical for NS-2+. */
export { shellSpineContainers, shellUtilityNav };
