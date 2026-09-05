'use client';

import LogoutOutlinedIcon from '@mui/icons-material/LogoutOutlined';
import MenuIcon from '@mui/icons-material/Menu';
import MoreHorizIcon from '@mui/icons-material/MoreHoriz';
import NotificationsNoneOutlinedIcon from '@mui/icons-material/NotificationsNoneOutlined';
import SearchIcon from '@mui/icons-material/Search';
import SettingsOutlinedIcon from '@mui/icons-material/SettingsOutlined';
import ViewCompactOutlinedIcon from '@mui/icons-material/ViewCompactOutlined';
import {
  Badge,
  BottomNavigation,
  BottomNavigationAction,
  Box,
  Chip,
  Drawer,
  IconButton,
  Paper,
  Stack,
  Tooltip,
  Typography,
} from '@mui/material';
import Link from 'next/link';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { ReactNode, useCallback, useEffect, useMemo, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import { GlobalBackgroundTasksIndicator } from '@/features/background-tasks/GlobalBackgroundTasksIndicator';
import { CapabilityRail, DOMAIN_ICONS, RAIL_WIDTH, domainBadgesFromSpine } from '@/features/shell/CapabilityRail';
import { CommandPalette } from '@/features/shell/CommandPalette';
import { railNavGroups, roleMayAccess } from '@/features/shell/navConfig';
import { activeNavGroup } from '@/features/shell/navPageChrome';
import { useCurrentUser, useInvalidateCurrentUser, AUTH_ME_QUERY_KEY } from '@/features/shell/useCurrentUser';
import { apiGet, apiPost } from '@/lib/api';
import { clearAuthToken } from '@/lib/authSession';
import { useUiStore } from '@/stores/uiStore';

type BriefSignalsMeta = {
  tenant_stamp?: string;
  tenant_name?: string;
  tenant_period?: string;
  signal_count?: number;
  spine_badges?: Partial<Record<string, number | null>>;
};

function roleLabel(role: string | undefined | null): string {
  if (!role) return 'guest';
  return role.replace(/_/g, ' ');
}

/** Domains offered on the mobile bottom bar; the rest live behind "More" (the drawer). */
const MOBILE_PRIMARY = ['overview', 'stock', 'funding', 'data'];

export function AppShell({ title, children }: { title: string; children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const searchStr = searchParams.toString();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const { density, setDensity } = useUiStore((s) => s);
  const { data: me, isError: meError } = useCurrentUser();
  const invalidateMe = useInvalidateCurrentUser();
  const qc = useQueryClient();
  const [logoutBusy, setLogoutBusy] = useState(false);
  const role = me?.role ? String(me.role) : null;

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
  const badges = useMemo(() => domainBadgesFromSpine(briefMeta?.spine_badges), [briefMeta?.spine_badges]);
  const attention = briefMeta?.signal_count ?? briefMeta?.spine_badges?.brief ?? 0;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setPaletteOpen((p) => !p);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

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

  const active = activeNavGroup(pathname, searchStr ? `?${searchStr}` : '');
  const contextLabel = active?.label ?? (pathname === '/directory' ? 'What CIP does' : title);
  const mobileDomains = railNavGroups(role).filter((g) => MOBILE_PRIMARY.includes(g.id));

  const rail = (
    <CapabilityRail
      role={role}
      tenantName={briefMeta?.tenant_name}
      tenantStamp={briefMeta?.tenant_period ?? briefMeta?.tenant_stamp}
      displayName={displayName}
      sessionMeta={me ? `${roleLabel(String(me.role))} · session` : undefined}
      badges={badges}
      onNavigate={() => setMobileOpen(false)}
    />
  );

  return (
    <Box sx={{ display: 'flex', minHeight: '100vh', bgcolor: 'background.default' }} data-testid="app-shell">
      <Box
        component="nav"
        aria-label="Primary"
        sx={{
          display: { xs: 'none', md: 'block' },
          width: RAIL_WIDTH,
          flexShrink: 0,
          borderRight: '1px solid',
          borderColor: 'divider',
          position: 'sticky',
          top: 0,
          height: '100vh',
          overflow: 'hidden',
        }}
      >
        {rail}
      </Box>

      <Drawer
        variant="temporary"
        open={mobileOpen}
        onClose={() => setMobileOpen(false)}
        ModalProps={{ keepMounted: true }}
        sx={{ display: { xs: 'block', md: 'none' } }}
        PaperProps={{ sx: { width: RAIL_WIDTH + 28, boxSizing: 'border-box' } }}
      >
        {rail}
      </Drawer>

      <Box sx={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
        <Box
          component="header"
          data-testid="app-topbar"
          sx={{
            height: 52,
            display: 'flex',
            alignItems: 'center',
            gap: 1,
            px: { xs: 1, md: 2.5 },
            borderBottom: '1px solid',
            borderColor: 'divider',
            bgcolor: 'background.default',
            position: 'sticky',
            top: 0,
            zIndex: (t) => t.zIndex.appBar,
          }}
        >
          <IconButton
            color="inherit"
            edge="start"
            aria-label="Open navigation menu"
            onClick={() => setMobileOpen(true)}
            sx={{ display: { md: 'none' } }}
          >
            <MenuIcon />
          </IconButton>
          <Stack direction="row" spacing={1} alignItems="center" sx={{ minWidth: 0, flex: 1 }}>
            <Typography variant="body2" color="text.secondary" noWrap data-testid="topbar-context">
              {contextLabel}
            </Typography>
            {briefMeta?.tenant_period || briefMeta?.tenant_stamp ? (
              <Chip
                size="small"
                variant="outlined"
                label={briefMeta.tenant_period ?? briefMeta.tenant_stamp}
                sx={{ height: 22, display: { xs: 'none', sm: 'inline-flex' } }}
              />
            ) : null}
          </Stack>
          <Tooltip title="Search workflows (Ctrl/⌘ K)">
            <Paper
              component="button"
              type="button"
              onClick={() => setPaletteOpen(true)}
              elevation={0}
              data-testid="topbar-search"
              sx={{
                display: 'flex',
                alignItems: 'center',
                gap: 1,
                height: 34,
                px: 1.25,
                minWidth: { xs: 34, md: 260 },
                cursor: 'pointer',
                color: 'text.secondary',
                bgcolor: 'background.paper',
                boxShadow: 'none',
                font: 'inherit',
                '&:focus-visible': { outline: '2px solid', outlineColor: 'primary.main' },
              }}
              aria-label="Search CIP workflows"
            >
              <SearchIcon fontSize="small" />
              <Typography variant="body2" sx={{ display: { xs: 'none', md: 'block' }, flex: 1, textAlign: 'left' }}>
                Find a workflow…
              </Typography>
              <Typography
                variant="caption"
                sx={{ display: { xs: 'none', md: 'block' }, border: '1px solid', borderColor: 'divider', borderRadius: 0.75, px: 0.5 }}
              >
                ⌘K
              </Typography>
            </Paper>
          </Tooltip>
          <Tooltip title={attention ? `${attention} signal${attention === 1 ? '' : 's'} need attention` : 'Attention'}>
            <IconButton component={Link} href="/brief" aria-label="Attention" data-testid="topbar-attention">
              <Badge badgeContent={attention || 0} color="warning" max={99}>
                <NotificationsNoneOutlinedIcon />
              </Badge>
            </IconButton>
          </Tooltip>
          <GlobalBackgroundTasksIndicator />
          <Tooltip title={density === 'compact' ? 'Comfortable row height' : 'Compact row height'}>
            <IconButton
              color="inherit"
              onClick={() => setDensity(density === 'compact' ? 'comfortable' : 'compact')}
              aria-label="Toggle table density"
            >
              <ViewCompactOutlinedIcon />
            </IconButton>
          </Tooltip>
          {roleMayAccess(role, ['admin']) ? (
            <Tooltip title="Settings">
              <IconButton color="inherit" component={Link} href="/settings" aria-label="Settings">
                <SettingsOutlinedIcon />
              </IconButton>
            </Tooltip>
          ) : null}
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
        </Box>

        <Box
          component="main"
          sx={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0, pb: { xs: 9, md: 0 } }}
        >
          {children}
        </Box>
      </Box>

      <Paper
        elevation={0}
        sx={{
          display: { xs: 'block', md: 'none' },
          position: 'fixed',
          bottom: 0,
          left: 0,
          right: 0,
          borderRadius: 0,
          borderTop: '1px solid',
          borderColor: 'divider',
          zIndex: (t) => t.zIndex.appBar,
          boxShadow: 'none',
        }}
        data-testid="mobile-bottom-nav"
      >
        <BottomNavigation showLabels value={active?.id ?? 'more'} sx={{ height: 60, bgcolor: 'background.default' }}>
          {mobileDomains.map((d) => {
            const Icon = DOMAIN_ICONS[d.id] ?? MoreHorizIcon;
            return (
            <BottomNavigationAction
              key={d.id}
              value={d.id}
              label={d.short ?? d.label}
              icon={<Icon />}
              component={Link}
              href={d.href ?? d.items[0].href}
              sx={{ minWidth: 0, '& .MuiBottomNavigationAction-label': { fontSize: 11 } }}
            />
            );
          })}
          <BottomNavigationAction
            value="more"
            label="More"
            icon={<MoreHorizIcon />}
            onClick={() => setMobileOpen(true)}
            sx={{ minWidth: 0, '& .MuiBottomNavigationAction-label': { fontSize: 11 } }}
          />
        </BottomNavigation>
      </Paper>

      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} role={role} />
    </Box>
  );
}
