'use client';

import ChevronLeftIcon from '@mui/icons-material/ChevronLeft';
import HelpOutlineOutlinedIcon from '@mui/icons-material/HelpOutlineOutlined';
import MenuIcon from '@mui/icons-material/Menu';
import SettingsOutlinedIcon from '@mui/icons-material/SettingsOutlined';
import ViewCompactOutlinedIcon from '@mui/icons-material/ViewCompactOutlined';
import {
  AppBar,
  Box,
  Divider,
  Drawer,
  IconButton,
  List,
  ListItemButton,
  ListItemText,
  Toolbar,
  Tooltip,
  Typography,
  useMediaQuery,
} from '@mui/material';
import { useTheme } from '@mui/material/styles';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { ReactNode, useEffect, useMemo, useState } from 'react';

import { navItems } from '@/features/shell/navConfig';
import { useUiStore } from '@/stores/uiStore';

const drawerWidth = 268;

export function AppShell({ title, children }: { title: string; children: ReactNode }) {
  const muiTheme = useTheme();
  const pathname = usePathname();
  const isMdDown = useMediaQuery(muiTheme.breakpoints.down('md'));
  const [mobileOpen, setMobileOpen] = useState(false);
  const { density, setDensity, drawerOpen, drawerTitle, drawerContent, closeDrawer } = useUiStore((s) => s);

  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  const grouped = useMemo(() => {
    const m = new Map<string, typeof navItems>();
    for (const item of navItems) {
      const sec = item.section || 'General';
      if (!m.has(sec)) m.set(sec, []);
      m.get(sec)!.push(item);
    }
    return m;
  }, []);

  const drawer = (
    <Box sx={{ pt: 2, height: '100%', display: 'flex', flexDirection: 'column' }}>
      <Typography variant="subtitle2" sx={{ px: 2, pb: 1, color: 'text.secondary' }}>
        Channel Intelligence
      </Typography>
      <Divider sx={{ borderColor: 'divider' }} />
      <Box sx={{ flex: 1, overflow: 'auto' }}>
        {[...grouped.entries()].map(([section, items]) => (
          <Box key={section} sx={{ mt: 1.5 }}>
            <Typography variant="caption" sx={{ px: 2, color: 'text.disabled', letterSpacing: 0.6 }}>
              {section.toUpperCase()}
            </Typography>
            <List dense disablePadding>
              {items.map((item) => (
                <ListItemButton
                  key={item.href}
                  component={Link}
                  href={item.href}
                  selected={pathname === item.href}
                  onClick={() => isMdDown && setMobileOpen(false)}
                  sx={{ borderRadius: 1, mx: 1, mb: 0.25 }}
                >
                  <ListItemText primary={item.label} primaryTypographyProps={{ variant: 'body2' }} />
                </ListItemButton>
              ))}
            </List>
          </Box>
        ))}
      </Box>
    </Box>
  );

  return (
    <Box sx={{ display: 'flex', minHeight: '100vh' }}>
      <AppBar
        position="fixed"
        elevation={0}
        sx={{
          zIndex: (t) => t.zIndex.drawer + 1,
          ml: { md: `${drawerWidth}px` },
          width: { md: `calc(100% - ${drawerWidth}px)` },
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
          <Typography variant="h6" sx={{ flexGrow: 1, fontWeight: 600, textAlign: { xs: 'left', md: 'left' } }}>
            {title}
          </Typography>
          <Tooltip title="Getting started & how data flows">
            <IconButton color="inherit" component={Link} href="/getting-started" aria-label="Getting started">
              <HelpOutlineOutlinedIcon />
            </IconButton>
          </Tooltip>
          <Tooltip title="Settings & environment">
            <IconButton color="inherit" component={Link} href="/settings" aria-label="Settings">
              <SettingsOutlinedIcon />
            </IconButton>
          </Tooltip>
          <Tooltip title={density === 'compact' ? 'Use comfortable table row height' : 'Use compact table row height'}>
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
          sx={{ display: { xs: 'block', md: 'none' }, '& .MuiDrawer-paper': { width: drawerWidth } }}
        >
          {drawer}
        </Drawer>
        <Drawer
          variant="permanent"
          sx={{
            display: { xs: 'none', md: 'block' },
            '& .MuiDrawer-paper': { width: drawerWidth, boxSizing: 'border-box' },
          }}
          open
        >
          {drawer}
        </Drawer>
      </Box>

      <Box
        component="main"
        sx={{ flexGrow: 1, p: 3, width: { md: `calc(100% - ${drawerWidth}px)` }, mt: 8 }}
      >
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
