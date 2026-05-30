'use client';

import AdminPanelSettingsOutlinedIcon from '@mui/icons-material/AdminPanelSettingsOutlined';
import ChevronLeftIcon from '@mui/icons-material/ChevronLeft';
import ChevronRightIcon from '@mui/icons-material/ChevronRight';
import CloudUploadOutlinedIcon from '@mui/icons-material/CloudUploadOutlined';
import DashboardOutlinedIcon from '@mui/icons-material/DashboardOutlined';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import HelpOutlineOutlinedIcon from '@mui/icons-material/HelpOutlineOutlined';
import HubOutlinedIcon from '@mui/icons-material/HubOutlined';
import MenuIcon from '@mui/icons-material/Menu';
import SettingsOutlinedIcon from '@mui/icons-material/SettingsOutlined';
import StorageOutlinedIcon from '@mui/icons-material/StorageOutlined';
import TimelineOutlinedIcon from '@mui/icons-material/TimelineOutlined';
import ViewCompactOutlinedIcon from '@mui/icons-material/ViewCompactOutlined';
import WorkOutlineOutlinedIcon from '@mui/icons-material/WorkOutlineOutlined';
import {
  AppBar,
  Avatar,
  Box,
  Collapse,
  Divider,
  Drawer,
  IconButton,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Menu,
  MenuItem,
  Toolbar,
  Tooltip,
  Typography,
  useMediaQuery,
} from '@mui/material';
import { alpha, useTheme } from '@mui/material/styles';
import type { SvgIconComponent } from '@mui/icons-material';
import Link from 'next/link';
import { usePathname, useSearchParams } from 'next/navigation';
import { ReactNode, useCallback, useEffect, useMemo, useState } from 'react';

import { GlobalBackgroundTasksIndicator } from '@/features/background-tasks/GlobalBackgroundTasksIndicator';
import {
  activeGroupId,
  defaultGroupExpandedState,
  NAV_STORAGE_COLLAPSED,
  NAV_STORAGE_GROUP_EXPANDED,
  navGroups,
  navHrefMatches,
  type NavGroup,
} from '@/features/shell/navConfig';
import { useUiStore } from '@/stores/uiStore';

const DRAWER_WIDTH_EXPANDED = 280;
const DRAWER_WIDTH_COLLAPSED = 76;

const GROUP_ICONS: Record<string, SvgIconComponent> = {
  overview: DashboardOutlinedIcon,
  'channel-intelligence': HubOutlinedIcon,
  'commercial-planning': WorkOutlineOutlinedIcon,
  'data-imports': CloudUploadOutlinedIcon,
  'master-data': StorageOutlinedIcon,
  admin: AdminPanelSettingsOutlinedIcon,
};

function readCollapsed(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    return localStorage.getItem(NAV_STORAGE_COLLAPSED) === '1';
  } catch {
    return false;
  }
}

function readGroupExpanded(): Record<string, boolean> {
  if (typeof window === 'undefined') return defaultGroupExpandedState();
  try {
    const raw = localStorage.getItem(NAV_STORAGE_GROUP_EXPANDED);
    if (!raw) return defaultGroupExpandedState();
    const parsed = JSON.parse(raw) as Record<string, boolean>;
    return { ...defaultGroupExpandedState(), ...parsed };
  } catch {
    return defaultGroupExpandedState();
  }
}

export function AppShell({ title, children }: { title: string; children: ReactNode }) {
  const theme = useTheme();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const search = searchParams.toString() ? `?${searchParams.toString()}` : '';
  const isMdDown = useMediaQuery(theme.breakpoints.down('md'));
  const [mobileOpen, setMobileOpen] = useState(false);
  const [navCollapsed, setNavCollapsed] = useState(false);
  const [groupExpanded, setGroupExpanded] = useState<Record<string, boolean>>(defaultGroupExpandedState);
  const [collapsedMenuAnchor, setCollapsedMenuAnchor] = useState<HTMLElement | null>(null);
  const [collapsedMenuGroup, setCollapsedMenuGroup] = useState<NavGroup | null>(null);
  const { density, setDensity, drawerOpen, drawerTitle, drawerContent, closeDrawer } = useUiStore((s) => s);

  useEffect(() => {
    setNavCollapsed(readCollapsed());
    setGroupExpanded(readGroupExpanded());
  }, []);

  useEffect(() => {
    const active = activeGroupId(pathname, search);
    if (!active || navCollapsed) return;
    setGroupExpanded((prev) => ({ ...prev, [active]: true }));
  }, [pathname, search, navCollapsed]);

  useEffect(() => {
    setMobileOpen(false);
  }, [pathname, search]);

  const drawerWidth = navCollapsed ? DRAWER_WIDTH_COLLAPSED : DRAWER_WIDTH_EXPANDED;

  const toggleNavCollapsed = useCallback(() => {
    setNavCollapsed((prev) => {
      const next = !prev;
      try {
        localStorage.setItem(NAV_STORAGE_COLLAPSED, next ? '1' : '0');
      } catch {
        // no-op
      }
      return next;
    });
  }, []);

  const toggleGroup = useCallback((groupId: string) => {
    setGroupExpanded((prev) => {
      const next = { ...prev, [groupId]: !prev[groupId] };
      try {
        localStorage.setItem(NAV_STORAGE_GROUP_EXPANDED, JSON.stringify(next));
      } catch {
        // no-op
      }
      return next;
    });
  }, []);

  const sidebarBg = theme.palette.mode === 'dark' ? '#0c0e14' : '#111318';
  const sidebarBorder = alpha(theme.palette.common.white, 0.08);
  const activeBg = alpha(theme.palette.primary.main, 0.16);
  const hoverBg = alpha(theme.palette.common.white, 0.06);

  const renderNavItem = (href: string, label: string, inset = false) => {
    const selected = navHrefMatches(pathname, search, href);
    return (
      <ListItemButton
        key={`${href}-${label}`}
        component={Link}
        href={href}
        selected={selected}
        onClick={() => isMdDown && setMobileOpen(false)}
        sx={{
          borderRadius: 1.5,
          mx: navCollapsed ? 0.75 : 1,
          mb: 0.25,
          pl: navCollapsed ? 1.25 : inset ? 3.5 : 2,
          minHeight: 40,
          '&.Mui-selected': {
            bgcolor: activeBg,
            borderLeft: `3px solid ${theme.palette.primary.main}`,
            '&:hover': { bgcolor: alpha(theme.palette.primary.main, 0.22) },
          },
          '&:hover': { bgcolor: hoverBg },
        }}
      >
        {!navCollapsed ? (
          <ListItemText
            primary={label}
            primaryTypographyProps={{
              variant: 'body2',
              fontWeight: selected ? 600 : 500,
              fontSize: '0.8125rem',
            }}
          />
        ) : null}
      </ListItemButton>
    );
  };

  const drawerContentNav = (
    <Box
      sx={{
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        bgcolor: sidebarBg,
        color: alpha(theme.palette.common.white, 0.92),
        borderRight: `1px solid ${sidebarBorder}`,
      }}
    >
      <Box
        sx={{
          px: navCollapsed ? 1 : 2,
          py: 2,
          display: 'flex',
          alignItems: 'center',
          gap: 1.25,
          minHeight: 64,
        }}
      >
        <Box
          sx={{
            width: 36,
            height: 36,
            borderRadius: 2,
            bgcolor: alpha(theme.palette.primary.main, 0.2),
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
          }}
        >
          <TimelineOutlinedIcon sx={{ fontSize: 22, color: theme.palette.primary.light }} />
        </Box>
        {!navCollapsed ? (
          <Box sx={{ minWidth: 0 }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 700, letterSpacing: -0.2, lineHeight: 1.2 }}>
              Channel Intelligence
            </Typography>
            <Typography variant="caption" sx={{ color: alpha(theme.palette.common.white, 0.5) }}>
              Commercial platform
            </Typography>
          </Box>
        ) : null}
      </Box>

      <Divider sx={{ borderColor: sidebarBorder }} />

      <Box sx={{ flex: 1, overflow: 'auto', py: 1 }}>
        {navGroups.map((group) => {
          const GroupIcon = GROUP_ICONS[group.id] ?? DashboardOutlinedIcon;
          const expanded = groupExpanded[group.id] !== false;

          if (navCollapsed) {
            return (
              <Tooltip key={group.id} title={group.label} placement="right" arrow>
                <ListItemButton
                  onClick={(e) => {
                    setCollapsedMenuAnchor(e.currentTarget);
                    setCollapsedMenuGroup(group);
                  }}
                  sx={{
                    borderRadius: 2,
                    mx: 0.75,
                    my: 0.5,
                    justifyContent: 'center',
                    minHeight: 44,
                    bgcolor: activeGroupId(pathname, search) === group.id ? activeBg : 'transparent',
                    '&:hover': { bgcolor: hoverBg },
                  }}
                >
                  <ListItemIcon sx={{ minWidth: 0, color: 'inherit', justifyContent: 'center' }}>
                    <GroupIcon fontSize="small" />
                  </ListItemIcon>
                </ListItemButton>
              </Tooltip>
            );
          }

          return (
            <Box key={group.id} sx={{ mb: 0.5 }}>
              <ListItemButton
                onClick={() => toggleGroup(group.id)}
                sx={{
                  borderRadius: 1,
                  mx: 1,
                  py: 0.75,
                  '&:hover': { bgcolor: hoverBg },
                }}
              >
                <ListItemIcon sx={{ minWidth: 32, color: alpha(theme.palette.common.white, 0.7) }}>
                  <GroupIcon sx={{ fontSize: 18 }} />
                </ListItemIcon>
                <ListItemText
                  primary={group.label}
                  primaryTypographyProps={{
                    variant: 'caption',
                    sx: {
                      textTransform: 'uppercase',
                      letterSpacing: '0.1em',
                      fontWeight: 600,
                      color: alpha(theme.palette.common.white, 0.45),
                      fontSize: '0.68rem',
                    },
                  }}
                />
                <ExpandMoreIcon
                  sx={{
                    fontSize: 18,
                    color: alpha(theme.palette.common.white, 0.4),
                    transform: expanded ? 'rotate(0deg)' : 'rotate(-90deg)',
                    transition: theme.transitions.create('transform', { duration: 200 }),
                  }}
                />
              </ListItemButton>
              <Collapse in={expanded} timeout={200}>
                <List dense disablePadding>
                  {group.items.map((item) => renderNavItem(item.href, item.label, true))}
                </List>
              </Collapse>
            </Box>
          );
        })}
      </Box>

      <Divider sx={{ borderColor: sidebarBorder }} />

      <Box sx={{ p: navCollapsed ? 1 : 1.5, display: 'flex', alignItems: 'center', gap: 1 }}>
        {!navCollapsed ? (
          <>
            <Avatar sx={{ width: 36, height: 36, bgcolor: alpha(theme.palette.primary.main, 0.35), fontSize: 14 }}>
              WE
            </Avatar>
            <Box sx={{ minWidth: 0, flex: 1 }}>
              <Typography variant="body2" fontWeight={600} noWrap>
                Warren Eliason
              </Typography>
              <Typography variant="caption" sx={{ color: alpha(theme.palette.common.white, 0.5) }} noWrap>
                Admin · demo-user
              </Typography>
            </Box>
          </>
        ) : (
          <Tooltip title="Warren Eliason" placement="right">
            <Avatar sx={{ width: 36, height: 36, mx: 'auto', bgcolor: alpha(theme.palette.primary.main, 0.35) }}>
              WE
            </Avatar>
          </Tooltip>
        )}
        <Tooltip title={navCollapsed ? 'Expand navigation' : 'Collapse navigation'}>
          <IconButton
            size="small"
            onClick={toggleNavCollapsed}
            sx={{ color: alpha(theme.palette.common.white, 0.7) }}
            aria-label={navCollapsed ? 'Expand navigation' : 'Collapse navigation'}
          >
            {navCollapsed ? <ChevronRightIcon fontSize="small" /> : <ChevronLeftIcon fontSize="small" />}
          </IconButton>
        </Tooltip>
      </Box>

      <Menu
        anchorEl={collapsedMenuAnchor}
        open={Boolean(collapsedMenuAnchor && collapsedMenuGroup)}
        onClose={() => {
          setCollapsedMenuAnchor(null);
          setCollapsedMenuGroup(null);
        }}
        anchorOrigin={{ horizontal: 'right', vertical: 'top' }}
        transformOrigin={{ horizontal: 'left', vertical: 'top' }}
      >
        {collapsedMenuGroup?.items.map((item) => (
          <MenuItem
            key={`${item.href}-${item.label}`}
            component={Link}
            href={item.href}
            selected={navHrefMatches(pathname, search, item.href)}
            onClick={() => {
              setCollapsedMenuAnchor(null);
              setCollapsedMenuGroup(null);
              setMobileOpen(false);
            }}
          >
            {item.label}
          </MenuItem>
        ))}
      </Menu>
    </Box>
  );

  const mainMargin = useMemo(() => ({ md: `${drawerWidth}px` }), [drawerWidth]);

  return (
    <Box sx={{ display: 'flex', minHeight: '100vh', bgcolor: 'background.default' }}>
      <AppBar
        position="fixed"
        elevation={0}
        sx={{
          zIndex: (t) => t.zIndex.drawer + 1,
          ml: mainMargin,
          width: { md: `calc(100% - ${drawerWidth}px)` },
          bgcolor: alpha(theme.palette.background.paper, 0.85),
          backdropFilter: 'blur(12px)',
          borderBottom: `1px solid ${theme.palette.divider}`,
          color: 'text.primary',
        }}
      >
        <Toolbar sx={{ gap: 1 }}>
          <IconButton
            color="inherit"
            edge="start"
            aria-label="Open navigation menu"
            onClick={() => setMobileOpen(true)}
            sx={{ mr: 0.5, display: { md: 'none' } }}
          >
            <MenuIcon />
          </IconButton>
          <Typography variant="h6" sx={{ flexGrow: 1, fontWeight: 600, fontSize: '1.05rem' }}>
            {title}
          </Typography>
          <GlobalBackgroundTasksIndicator />
          <Tooltip title="Getting started">
            <IconButton color="inherit" component={Link} href="/getting-started" aria-label="Getting started">
              <HelpOutlineOutlinedIcon />
            </IconButton>
          </Tooltip>
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
        </Toolbar>
      </AppBar>

      <Box component="nav" sx={{ width: { md: drawerWidth }, flexShrink: { md: 0 } }}>
        <Drawer
          variant="temporary"
          open={mobileOpen}
          onClose={() => setMobileOpen(false)}
          ModalProps={{ keepMounted: true }}
          sx={{
            display: { xs: 'block', md: 'none' },
            '& .MuiDrawer-paper': { width: DRAWER_WIDTH_EXPANDED, boxSizing: 'border-box' },
          }}
        >
          {drawerContentNav}
        </Drawer>
        <Drawer
          variant="permanent"
          sx={{
            display: { xs: 'none', md: 'block' },
            '& .MuiDrawer-paper': {
              width: drawerWidth,
              boxSizing: 'border-box',
              transition: theme.transitions.create('width', { duration: 220, easing: 'ease-in-out' }),
              overflowX: 'hidden',
            },
          }}
          open
        >
          {drawerContentNav}
        </Drawer>
      </Box>

      <Box component="main" sx={{ flexGrow: 1, p: { xs: 2, md: 3 }, width: { md: `calc(100% - ${drawerWidth}px)` }, mt: 8 }}>
        {children}
      </Box>

      <Drawer anchor="right" open={drawerOpen} onClose={closeDrawer}>
        <Box sx={{ width: 420, p: 2 }}>
          <Toolbar sx={{ justifyContent: 'space-between', px: 0 }}>
            <Typography variant="subtitle1" fontWeight={600}>
              {drawerTitle}
            </Typography>
            <IconButton onClick={closeDrawer} aria-label="Close panel">
              <ChevronLeftIcon />
            </IconButton>
          </Toolbar>
          <Divider />
          <Typography variant="body2" sx={{ mt: 2, whiteSpace: 'pre-wrap', color: 'text.secondary' }}>
            {drawerContent}
          </Typography>
        </Box>
      </Drawer>
    </Box>
  );
}
