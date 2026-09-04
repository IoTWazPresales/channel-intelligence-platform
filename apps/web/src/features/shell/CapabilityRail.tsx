'use client';

import type { SvgIconComponent } from '@mui/icons-material';
import AccountBalanceOutlinedIcon from '@mui/icons-material/AccountBalanceOutlined';
import AdminPanelSettingsOutlinedIcon from '@mui/icons-material/AdminPanelSettingsOutlined';
import AppsOutlinedIcon from '@mui/icons-material/AppsOutlined';
import DashboardOutlinedIcon from '@mui/icons-material/DashboardOutlined';
import EventNoteOutlinedIcon from '@mui/icons-material/EventNoteOutlined';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import Inventory2OutlinedIcon from '@mui/icons-material/Inventory2Outlined';
import LocalShippingOutlinedIcon from '@mui/icons-material/LocalShippingOutlined';
import StorefrontOutlinedIcon from '@mui/icons-material/StorefrontOutlined';
import StorageOutlinedIcon from '@mui/icons-material/StorageOutlined';
import {
  Box,
  Chip,
  Collapse,
  Divider,
  IconButton,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Stack,
  Typography,
} from '@mui/material';
import { alpha } from '@mui/material/styles';
import NextLink from 'next/link';
import { usePathname, useSearchParams } from 'next/navigation';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { NAV_STORAGE_GROUP_EXPANDED, railNavGroups, type NavGroup } from '@/features/shell/navConfig';
import { activeNavGroup } from '@/features/shell/navPageChrome';

export const RAIL_WIDTH = 296;

/** Icons stay out of navConfig so the nav model remains a plain, testable module. */
export const DOMAIN_ICONS: Record<string, SvgIconComponent> = {
  overview: DashboardOutlinedIcon,
  stock: Inventory2OutlinedIcon,
  supply: LocalShippingOutlinedIcon,
  planning: EventNoteOutlinedIcon,
  funding: AccountBalanceOutlinedIcon,
  market: StorefrontOutlinedIcon,
  data: StorageOutlinedIcon,
  admin: AdminPanelSettingsOutlinedIcon,
};

/**
 * Counts per domain, sourced from `/api/v1/brief/signals.spine_badges` (API still keys them by the
 * pre-D-0008 container ids; mapped here so the contract does not have to move in this slice).
 */
export type DomainBadges = Partial<Record<string, number | null>>;

export function domainBadgesFromSpine(spine?: Partial<Record<string, number | null>> | null): DomainBadges {
  if (!spine) return {};
  return {
    overview: spine.brief ?? null,
    stock: spine.stock ?? null,
    funding: spine.settlement ?? null,
    data: spine.steward ?? null,
  };
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

function useExpandedState(activeId: string | undefined): [Record<string, boolean>, (id: string, next: boolean) => void] {
  const [open, setOpen] = useState<Record<string, boolean>>({});
  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(NAV_STORAGE_GROUP_EXPANDED);
      if (raw) setOpen(JSON.parse(raw) as Record<string, boolean>);
    } catch {
      /* ignore */
    }
  }, []);
  useEffect(() => {
    if (activeId) setOpen((o) => (o[activeId] ? o : { ...o, [activeId]: true }));
  }, [activeId]);
  const set = useCallback((id: string, next: boolean) => {
    setOpen((o) => {
      const out = { ...o, [id]: next };
      try {
        window.localStorage.setItem(NAV_STORAGE_GROUP_EXPANDED, JSON.stringify(out));
      } catch {
        /* ignore */
      }
      return out;
    });
  }, []);
  return [open, set];
}

type CapabilityRailProps = {
  role?: string | null;
  tenantName?: string;
  tenantStamp?: string;
  displayName?: string;
  sessionMeta?: string;
  badges?: DomainBadges;
  onNavigate?: () => void;
};

export function CapabilityRail({
  role,
  tenantName,
  tenantStamp,
  displayName,
  sessionMeta,
  badges,
  onNavigate,
}: CapabilityRailProps) {
  const pathname = usePathname();
  const search = useSearchParams();
  const searchStr = search.toString();
  const groups = useMemo(() => railNavGroups(role), [role]);
  const active = activeNavGroup(pathname, searchStr ? `?${searchStr}` : '');
  const [open, setOpen] = useExpandedState(active?.id);

  return (
    <Box
      component="aside"
      data-testid="capability-rail"
      sx={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}
    >
      <Box sx={{ px: 2, pt: 2, pb: 1.5 }}>
        <Stack direction="row" alignItems="center" spacing={1}>
          <Box
            sx={{
              width: 28,
              height: 28,
              borderRadius: 1.5,
              bgcolor: 'primary.main',
              display: 'grid',
              placeItems: 'center',
              color: 'primary.contrastText',
              fontWeight: 800,
              fontSize: 13,
            }}
          >
            CI
          </Box>
          <Box sx={{ minWidth: 0 }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 700, lineHeight: 1.1 }}>
              Channel Intelligence
            </Typography>
            {tenantName || tenantStamp ? (
              <Typography variant="caption" color="text.secondary" noWrap sx={{ display: 'block' }} data-testid="rail-tenant-stamp">
                {tenantName || tenantStamp}
              </Typography>
            ) : null}
          </Box>
        </Stack>
      </Box>
      <Divider />
      <List dense component="nav" aria-label="Capability areas" sx={{ flex: 1, overflowY: 'auto', py: 1 }}>
        {groups.map((d: NavGroup) => {
          const Icon = DOMAIN_ICONS[d.id] ?? AppsOutlinedIcon;
          const isActive = active?.id === d.id;
          const expanded = open[d.id] ?? isActive;
          const badge = badges?.[d.id];
          return (
            <Box key={d.id} sx={{ px: 1 }}>
              <ListItemButton
                component={NextLink}
                href={d.href ?? d.items[0].href}
                onClick={onNavigate}
                selected={isActive}
                data-testid={`rail-domain-${d.id}`}
                sx={{
                  borderRadius: 1.5,
                  py: 0.75,
                  '&.Mui-selected': {
                    bgcolor: (t) => alpha(t.palette.primary.main, 0.14),
                    '&:hover': { bgcolor: (t) => alpha(t.palette.primary.main, 0.18) },
                  },
                }}
              >
                <ListItemIcon sx={{ minWidth: 34, color: isActive ? 'primary.main' : 'text.secondary' }}>
                  <Icon fontSize="small" />
                </ListItemIcon>
                <ListItemText
                  primary={d.label}
                  primaryTypographyProps={{
                    variant: 'body2',
                    fontWeight: isActive ? 600 : 500,
                    noWrap: false,
                    sx: { overflow: 'visible', textOverflow: 'clip' },
                  }}
                />
                {badge != null && badge > 0 ? (
                  <Chip
                    size="small"
                    color={d.id === 'overview' || d.id === 'data' ? 'warning' : 'default'}
                    label={badge}
                    data-testid={`rail-badge-${d.id}`}
                    sx={{ height: 18, fontSize: 11, mr: 0.5 }}
                  />
                ) : null}
                <IconButton
                  size="small"
                  aria-label={expanded ? `Collapse ${d.label}` : `Expand ${d.label}`}
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    setOpen(d.id, !expanded);
                  }}
                  sx={{ p: 0.25, transform: expanded ? 'rotate(180deg)' : undefined, transition: 'transform 120ms' }}
                >
                  <ExpandMoreIcon fontSize="small" />
                </IconButton>
              </ListItemButton>
              <Collapse in={expanded} unmountOnExit>
                <List dense disablePadding sx={{ ml: 4.25, borderLeft: '1px solid', borderColor: 'divider', mb: 0.5 }}>
                  {d.items.map((l) => {
                    const on = leafIsActive(l.href, pathname, searchStr);
                    return (
                      <ListItemButton
                        key={l.href}
                        component={NextLink}
                        href={l.href}
                        onClick={onNavigate}
                        selected={on}
                        sx={{
                          py: 0.4,
                          pl: 1.5,
                          borderRadius: '0 8px 8px 0',
                          ml: '-1px',
                          borderLeft: '2px solid',
                          borderLeftColor: on ? 'primary.main' : 'transparent',
                          gap: 0.75,
                        }}
                      >
                        <ListItemText
                          primary={l.label}
                          primaryTypographyProps={{
                            variant: 'body2',
                            color: on ? 'text.primary' : 'text.secondary',
                            fontWeight: on ? 600 : 400,
                            noWrap: false,
                            sx: { overflow: 'visible', textOverflow: 'clip' },
                          }}
                        />
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
        <ListItemButton
          component={NextLink}
          href="/directory"
          onClick={onNavigate}
          selected={pathname === '/directory'}
          sx={{ borderRadius: 1.5 }}
          data-testid="rail-directory"
        >
          <ListItemIcon sx={{ minWidth: 34, color: 'text.secondary' }}>
            <AppsOutlinedIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText
            primary="What CIP does"
            secondary="Capability directory"
            primaryTypographyProps={{ variant: 'body2', fontWeight: 500 }}
            secondaryTypographyProps={{ variant: 'caption' }}
          />
        </ListItemButton>
      </List>
      {displayName || sessionMeta ? (
        <Box sx={{ px: 2, pt: 1, pb: 1.5, borderTop: '1px solid', borderColor: 'divider' }}>
          {displayName ? (
            <Typography variant="body2" sx={{ fontWeight: 500 }} noWrap>
              {displayName}
            </Typography>
          ) : null}
          {sessionMeta ? (
            <Typography variant="caption" color="text.secondary" noWrap sx={{ display: 'block' }}>
              {sessionMeta}
            </Typography>
          ) : null}
        </Box>
      ) : null}
    </Box>
  );
}
