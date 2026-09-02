'use client';

import AppsOutlinedIcon from '@mui/icons-material/AppsOutlined';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import MenuIcon from '@mui/icons-material/Menu';
import MoreHorizIcon from '@mui/icons-material/MoreHoriz';
import NotificationsNoneOutlinedIcon from '@mui/icons-material/NotificationsNoneOutlined';
import SearchIcon from '@mui/icons-material/Search';
import {
  Avatar,
  Badge,
  BottomNavigation,
  BottomNavigationAction,
  Box,
  Chip,
  Collapse,
  Divider,
  Drawer,
  IconButton,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  MenuItem,
  Paper,
  Select,
  Stack,
  Tooltip,
  Typography,
  useMediaQuery,
} from '@mui/material';
import { alpha, useTheme } from '@mui/material/styles';
import NextLink from 'next/link';
import { usePathname, useSearchParams } from 'next/navigation';
import { ReactNode, useCallback, useEffect, useMemo, useState } from 'react';

import { tenant } from '../fixtures/entities';
import { signals } from '../fixtures/operations';
import { CommandPalette } from './CommandPalette';
import { domainForPath, labDomains, visibleDomains, visibleLeaves, type LabDomain, type Role } from './labNav';

export const RAIL_WIDTH = 252;

/** Fixture role switcher — demonstrates role → visibility/defaults without persona modes. */
function useLabRole(): [Role, (r: Role) => void] {
  const [role, setRole] = useState<Role>('planner');
  useEffect(() => {
    const saved = typeof window !== 'undefined' ? (window.localStorage.getItem('cip.design-lab.role') as Role | null) : null;
    if (saved) setRole(saved);
  }, []);
  const set = useCallback((r: Role) => {
    setRole(r);
    window.localStorage.setItem('cip.design-lab.role', r);
  }, []);
  return [role, set];
}

function leafIsActive(href: string, pathname: string, search: string): boolean {
  const [path, qs] = href.split('?');
  if (path !== pathname) return false;
  if (!qs) return !search;
  const want = new URLSearchParams(qs);
  const have = new URLSearchParams(search);
  for (const [k, v] of want.entries()) if (have.get(k) !== v) return false;
  return true;
}

function Rail({ role, onNavigate }: { role: Role; onNavigate?: () => void }) {
  const pathname = usePathname();
  const search = useSearchParams();
  const searchStr = search.toString();
  const active = domainForPath(pathname);
  const [open, setOpen] = useState<Record<string, boolean>>({});
  useEffect(() => {
    if (active) setOpen((o) => ({ ...o, [active.id]: true }));
  }, [active]);
  const attentionCount = signals.filter((s) => s.severity !== 'info').length;

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <Box sx={{ px: 2, pt: 2, pb: 1.5 }}>
        <Stack direction="row" alignItems="center" spacing={1}>
          <Box sx={{ width: 28, height: 28, borderRadius: 1.5, bgcolor: 'primary.main', display: 'grid', placeItems: 'center', color: 'primary.contrastText', fontWeight: 800, fontSize: 13 }}>
            CI
          </Box>
          <Box sx={{ minWidth: 0 }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 700, lineHeight: 1.1 }}>
              Channel Intelligence
            </Typography>
            <Typography variant="caption" color="text.secondary" noWrap sx={{ display: 'block' }}>
              {tenant.name}
            </Typography>
          </Box>
        </Stack>
      </Box>
      <Divider />
      <List dense component="nav" aria-label="Capability areas" sx={{ flex: 1, overflowY: 'auto', py: 1 }}>
        {visibleDomains(role).map((d) => {
          const Icon = d.icon;
          const isActive = active?.id === d.id;
          const leaves = visibleLeaves(d, role);
          const expanded = open[d.id] ?? isActive;
          return (
            <Box key={d.id} sx={{ px: 1 }}>
              <ListItemButton
                component={NextLink}
                href={d.href}
                onClick={onNavigate}
                selected={isActive}
                sx={{
                  borderRadius: 1.5,
                  py: 0.75,
                  '&.Mui-selected': { bgcolor: (t) => alpha(t.palette.primary.main, 0.14), '&:hover': { bgcolor: (t) => alpha(t.palette.primary.main, 0.18) } },
                }}
              >
                <ListItemIcon sx={{ minWidth: 34, color: isActive ? 'primary.main' : 'text.secondary' }}>
                  <Icon fontSize="small" />
                </ListItemIcon>
                <ListItemText primary={d.label} primaryTypographyProps={{ variant: 'body2', fontWeight: isActive ? 600 : 500 }} />
                {d.id === 'overview' && attentionCount ? <Chip size="small" color="warning" label={attentionCount} sx={{ height: 18, fontSize: 11, mr: 0.5 }} /> : null}
                <IconButton
                  size="small"
                  aria-label={expanded ? `Collapse ${d.label}` : `Expand ${d.label}`}
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    setOpen((o) => ({ ...o, [d.id]: !expanded }));
                  }}
                  sx={{ p: 0.25, transform: expanded ? 'rotate(180deg)' : undefined, transition: 'transform 120ms' }}
                >
                  <ExpandMoreIcon fontSize="small" />
                </IconButton>
              </ListItemButton>
              <Collapse in={expanded} unmountOnExit>
                <List dense disablePadding sx={{ ml: 4.25, borderLeft: '1px solid', borderColor: 'divider', mb: 0.5 }}>
                  {leaves.map((l) => {
                    const on = leafIsActive(l.href, pathname, searchStr);
                    return (
                      <ListItemButton
                        key={l.href}
                        component={NextLink}
                        href={l.href}
                        onClick={onNavigate}
                        selected={on}
                        sx={{ py: 0.4, pl: 1.5, borderRadius: '0 8px 8px 0', ml: '-1px', borderLeft: on ? '2px solid' : '2px solid transparent', borderLeftColor: on ? 'primary.main' : 'transparent' }}
                      >
                        <ListItemText primary={l.label} primaryTypographyProps={{ variant: 'body2', color: on ? 'text.primary' : 'text.secondary', fontWeight: on ? 600 : 400 }} />
                      </ListItemButton>
                    );
                  })}
                </List>
              </Collapse>
            </Box>
          );
        })}
      </List>
      <Divider />
      <List dense sx={{ py: 0.5, px: 1 }}>
        <ListItemButton component={NextLink} href="/design-lab/directory" onClick={onNavigate} selected={pathname === '/design-lab/directory'} sx={{ borderRadius: 1.5 }}>
          <ListItemIcon sx={{ minWidth: 34, color: 'text.secondary' }}>
            <AppsOutlinedIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText primary="What CIP does" secondary="Capability directory" primaryTypographyProps={{ variant: 'body2', fontWeight: 500 }} secondaryTypographyProps={{ variant: 'caption' }} />
        </ListItemButton>
      </List>
    </Box>
  );
}

function TopBar({ role, setRole, onSearch, onMenu, isMobile }: { role: Role; setRole: (r: Role) => void; onSearch: () => void; onMenu: () => void; isMobile: boolean }) {
  const pathname = usePathname();
  const active = domainForPath(pathname);
  const attention = signals.filter((s) => s.severity !== 'info').length;
  return (
    <Box
      component="header"
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
      {isMobile ? (
        <IconButton aria-label="Open navigation" onClick={onMenu}>
          <MenuIcon />
        </IconButton>
      ) : null}
      <Stack direction="row" spacing={1} alignItems="center" sx={{ minWidth: 0, flex: 1 }}>
        <Typography variant="body2" color="text.secondary" noWrap>
          {active?.label ?? (pathname === '/design-lab/directory' ? 'What CIP does' : 'Channel Intelligence')}
        </Typography>
        <Chip size="small" variant="outlined" label={tenant.period} sx={{ height: 22, display: { xs: 'none', sm: 'inline-flex' } }} />
      </Stack>
      <Tooltip title="Search (Ctrl/⌘ K)">
        <Paper
          component="button"
          onClick={onSearch}
          elevation={0}
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
          aria-label="Search CIP"
        >
          <SearchIcon fontSize="small" />
          <Typography variant="body2" sx={{ display: { xs: 'none', md: 'block' }, flex: 1, textAlign: 'left' }}>
            Find a workflow or entity…
          </Typography>
          <Typography variant="caption" sx={{ display: { xs: 'none', md: 'block' }, border: '1px solid', borderColor: 'divider', borderRadius: 0.75, px: 0.5 }}>
            ⌘K
          </Typography>
        </Paper>
      </Tooltip>
      <Tooltip title={`${attention} items need attention`}>
        <IconButton component={NextLink} href="/design-lab?zone=attention" aria-label="Attention">
          <Badge badgeContent={attention} color="warning">
            <NotificationsNoneOutlinedIcon />
          </Badge>
        </IconButton>
      </Tooltip>
      <Select
        size="small"
        value={role}
        onChange={(e) => setRole(e.target.value as Role)}
        inputProps={{ 'aria-label': 'Role (design-lab fixture)' }}
        sx={{ height: 34, fontSize: 13, display: { xs: 'none', sm: 'inline-flex' }, '& .MuiSelect-select': { py: 0.5 } }}
      >
        {(['admin', 'steward', 'planner', 'viewer'] as Role[]).map((r) => (
          <MenuItem key={r} value={r} sx={{ fontSize: 13 }}>
            {r}
          </MenuItem>
        ))}
      </Select>
      <Avatar sx={{ width: 30, height: 30, fontSize: 13, bgcolor: 'secondary.main', color: 'secondary.contrastText' }}>W</Avatar>
    </Box>
  );
}

function MobileBottomNav({ onMore, role }: { onMore: () => void; role: Role }) {
  const pathname = usePathname();
  const active = domainForPath(pathname);
  const primary: LabDomain[] = visibleDomains(role).filter((d) => ['overview', 'stock', 'funding', 'data'].includes(d.id)).slice(0, 4);
  return (
    <Paper elevation={0} sx={{ position: 'fixed', bottom: 0, left: 0, right: 0, borderRadius: 0, borderTop: '1px solid', borderColor: 'divider', zIndex: (t) => t.zIndex.appBar, boxShadow: 'none' }}>
      <BottomNavigation showLabels value={active?.id ?? 'more'} sx={{ height: 60, bgcolor: 'background.default' }}>
        {primary.map((d) => {
          const Icon = d.icon;
          return <BottomNavigationAction key={d.id} value={d.id} label={d.short} icon={<Icon />} component={NextLink} href={d.href} sx={{ minWidth: 0, '& .MuiBottomNavigationAction-label': { fontSize: 11 } }} />;
        })}
        <BottomNavigationAction value="more" label="More" icon={<MoreHorizIcon />} onClick={onMore} sx={{ minWidth: 0, '& .MuiBottomNavigationAction-label': { fontSize: 11 } }} />
      </BottomNavigation>
    </Paper>
  );
}

export function LabShell({ children }: { children: ReactNode }) {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  const [drawer, setDrawer] = useState(false);
  const [palette, setPalette] = useState(false);
  const [role, setRole] = useLabRole();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setPalette((p) => !p);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const railSx = useMemo(() => ({ width: RAIL_WIDTH, flexShrink: 0, borderRight: '1px solid', borderColor: 'divider', bgcolor: 'background.default', position: 'sticky', top: 0, height: '100vh', overflow: 'hidden' }), []);

  return (
    <Box sx={{ display: 'flex', minHeight: '100vh', bgcolor: 'background.default' }} data-testid="design-lab-shell">
      {!isMobile ? (
        <Box component="aside" sx={railSx}>
          <Rail role={role} />
        </Box>
      ) : (
        <Drawer open={drawer} onClose={() => setDrawer(false)} PaperProps={{ sx: { width: RAIL_WIDTH + 28 } }}>
          <Rail role={role} onNavigate={() => setDrawer(false)} />
        </Drawer>
      )}
      <Box sx={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
        <TopBar role={role} setRole={setRole} onSearch={() => setPalette(true)} onMenu={() => setDrawer(true)} isMobile={isMobile} />
        <Box component="main" sx={{ flex: 1, px: { xs: 1.5, md: 2.5 }, py: { xs: 1.5, md: 2 }, pb: isMobile ? 10 : 3 }}>
          {children}
        </Box>
      </Box>
      {isMobile ? <MobileBottomNav onMore={() => setDrawer(true)} role={role} /> : null}
      <CommandPalette open={palette} onClose={() => setPalette(false)} />
    </Box>
  );
}
