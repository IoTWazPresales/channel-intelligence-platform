'use client';

import type { SvgIconComponent } from '@mui/icons-material';
import AccountBalanceOutlinedIcon from '@mui/icons-material/AccountBalanceOutlined';
import AdminPanelSettingsOutlinedIcon from '@mui/icons-material/AdminPanelSettingsOutlined';
import DashboardOutlinedIcon from '@mui/icons-material/DashboardOutlined';
import EventNoteOutlinedIcon from '@mui/icons-material/EventNoteOutlined';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import Inventory2OutlinedIcon from '@mui/icons-material/Inventory2Outlined';
import LocalShippingOutlinedIcon from '@mui/icons-material/LocalShippingOutlined';
import StorefrontOutlinedIcon from '@mui/icons-material/StorefrontOutlined';
import StorageOutlinedIcon from '@mui/icons-material/StorageOutlined';
import { Box, Chip, Collapse, IconButton, Typography } from '@mui/material';
import { alpha, type Theme } from '@mui/material/styles';
import NextLink from 'next/link';
import { usePathname, useSearchParams } from 'next/navigation';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { NAV_STORAGE_GROUP_EXPANDED, railNavGroups, type NavGroup } from '@/features/shell/navConfig';
import { activeNavGroup } from '@/features/shell/navPageChrome';

/**
 * The mock-up sidebar is 172px, but its headings are two short words ("Workspace", "Explore"). The real group
 * headings at the mock-up's own eyebrow type (10px / 700 / 1.4px / uppercase) measure up to 154.2px
 * ("PROMOTIONS & FUNDING"), more than the 144px content box a 172px rail leaves, before any chevron or count.
 * Measured (Playwright, 26 Nov): 240px is the exact minimum at which every heading fits on one line beside its count and
 * chevron (0px spare on "PROMOTIONS & FUNDING"); 244px keeps 4px for font substitution at that measured count.
 * A three-digit count is wider than that count. RAIL_COUNT sizes the chip, gap and chevron so "999" still leaves
 * at least 4px (see CapabilityRail.test.ts). The label ellipsizes if a wider font would push the count out.
 * Everything else in the rail is the mock-up's own geometry (NAV_MOCK).
 */
export const RAIL_WIDTH = 244;

/**
 * Heading-row slots for the count chip. Not tenant config: fixed so a three-digit count stays inside RAIL_WIDTH.
 * rowGapPx is the flex gap (two gaps: label|chip and chip|chevron). chipPadXPx is horizontal padding each side.
 * chevronPx is the expand control's box.
 */
export const RAIL_COUNT = {
  rowGapPx: 2,
  chipPadXPx: 4,
  chevronPx: 16,
} as const;

/**
 * Navigation rail geometry, copied value for value from the mock-up (`docs/design/dashboard-v2/index.html`:
 * `.sidebar`, `.brand`, `.nav-group`, `.nav-label`, `.nav-item`, `.sidebar-foot`). Colours come from the theme palette.
 */
export const NAV_MOCK = {
  padding: '24px 14px',
  gap: '25px',
  groupGap: '5px',
  eyebrow: { fontSize: 10, fontWeight: 700, letterSpacing: '1.4px', padding: '0 10px 7px' },
  item: { padding: '9px 10px', borderLeft: '2px solid', radius: '0 8px 8px 0', activeWeight: 600 },
  brand: { gap: '10px', fontSize: 15, fontWeight: 700, letterSpacing: '-.3px', smallSize: 10, smallLetterSpacing: '.5px' },
  foot: { padding: '12px 9px 0', fontSize: 11 },
} as const;

/** Mock-up `--accent-wash`: accent at 15% (dark) / 12% (light). */
const activeWash = (theme: Theme) => alpha(theme.palette.primary.main, theme.palette.mode === 'dark' ? 0.15 : 0.12);

/** Icons stay out of navConfig so the nav model remains a plain, testable module (AppShell's mobile bar uses them). */
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

/** Mock-up `.nav-item` / `.nav-item.active`. */
const itemSx = (on: boolean) => ({
  display: 'block',
  padding: NAV_MOCK.item.padding,
  borderLeft: NAV_MOCK.item.borderLeft,
  borderColor: on ? 'primary.main' : 'transparent',
  borderRadius: NAV_MOCK.item.radius,
  color: on ? 'primary.main' : 'text.secondary',
  bgcolor: on ? activeWash : 'transparent',
  fontWeight: on ? NAV_MOCK.item.activeWeight : 400,
  textDecoration: 'none',
  lineHeight: 1.45,
  '&:hover': { bgcolor: on ? activeWash : 'action.hover', color: on ? 'primary.main' : 'text.primary' },
});

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
      sx={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        minHeight: 0,
        boxSizing: 'border-box',
        padding: NAV_MOCK.padding,
        gap: NAV_MOCK.gap,
      }}
    >
      <Box sx={{ display: 'flex', alignItems: 'center', gap: NAV_MOCK.brand.gap, flexShrink: 0 }}>
        <Box component="svg" viewBox="0 0 27 29" aria-hidden="true" sx={{ width: 27, height: 29, color: 'primary.main', flex: 'none' }}>
          <path d="M2 21V8l11-6 12 6v13l-12 6Z" fill="none" stroke="currentColor" strokeWidth="2" />
          <path d="m2 8 11 7 12-7M13 15v12" fill="none" stroke="currentColor" strokeWidth="2" />
        </Box>
        <Box sx={{ minWidth: 0 }}>
          <Typography
            component="div"
            sx={{
              fontSize: NAV_MOCK.brand.fontSize,
              fontWeight: NAV_MOCK.brand.fontWeight,
              letterSpacing: NAV_MOCK.brand.letterSpacing,
              lineHeight: 1.45,
            }}
          >
            Channel
          </Typography>
          <Typography
            component="small"
            color="text.secondary"
            sx={{
              display: 'block',
              fontSize: NAV_MOCK.brand.smallSize,
              fontWeight: 400,
              letterSpacing: NAV_MOCK.brand.smallLetterSpacing,
              lineHeight: 1.45,
            }}
          >
            INTELLIGENCE
          </Typography>
          {tenantName || tenantStamp ? (
            <Typography
              component="small"
              color="text.secondary"
              noWrap
              sx={{ display: 'block', fontSize: NAV_MOCK.brand.smallSize, lineHeight: 1.45 }}
              data-testid="rail-tenant-stamp"
            >
              {tenantName || tenantStamp}
            </Typography>
          ) : null}
        </Box>
      </Box>
      <Box
        component="nav"
        aria-label="Capability areas"
        sx={{
          flex: 1,
          minHeight: 0,
          minWidth: 0,
          overflowY: 'auto',
          overflowX: 'hidden',
          scrollbarWidth: 'thin',
          display: 'grid',
          alignContent: 'start',
          gap: NAV_MOCK.gap,
        }}
      >
        {groups.map((d: NavGroup) => {
          const isActive = active?.id === d.id;
          const expanded = open[d.id] ?? isActive;
          const badge = badges?.[d.id];
          return (
            <Box key={d.id} sx={{ display: 'grid', gap: NAV_MOCK.groupGap, alignContent: 'start', minWidth: 0 }}>
              <Box
                component={NextLink}
                href={d.href ?? d.items[0].href}
                prefetch
                onClick={onNavigate}
                data-testid={`rail-domain-${d.id}`}
                sx={{
                  // Sticky inside its own group: the heading holds parent context while a long group scrolls.
                  position: 'sticky',
                  top: 0,
                  zIndex: 2,
                  bgcolor: 'background.elevated',
                  display: 'flex',
                  alignItems: 'center',
                  gap: `${RAIL_COUNT.rowGapPx}px`,
                  minWidth: 0,
                  overflow: 'hidden',
                  padding: NAV_MOCK.eyebrow.padding,
                  paddingRight: 0,
                  // Mock-up `.nav-label`: secondary colour; the active leaf carries the accent. Warren: "YES" to
                  // highlighting the active group's heading when its leaves are collapsed, so the current area stays visible.
                  color: isActive && !expanded ? 'text.primary' : 'text.secondary',
                  textDecoration: 'none',
                  '&:hover': { color: 'text.primary' },
                }}
              >
                <Typography
                  component="span"
                  sx={{
                    flex: 1,
                    minWidth: 0,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                    color: 'inherit',
                    fontSize: NAV_MOCK.eyebrow.fontSize,
                    fontWeight: NAV_MOCK.eyebrow.fontWeight,
                    letterSpacing: NAV_MOCK.eyebrow.letterSpacing,
                    textTransform: 'uppercase',
                    lineHeight: 1.45,
                  }}
                >
                  {d.label}
                </Typography>
                {badge != null && badge > 0 ? (
                  <Chip
                    size="small"
                    color={d.id === 'overview' || d.id === 'data' ? 'warning' : 'default'}
                    label={badge}
                    data-testid={`rail-badge-${d.id}`}
                    sx={{
                      flexShrink: 0,
                      height: 16,
                      fontSize: 10,
                      fontWeight: 500,
                      // Beat the theme chip label padding (9px) so a three-digit count keeps its measured width.
                      '&& .MuiChip-label': {
                        paddingLeft: RAIL_COUNT.chipPadXPx,
                        paddingRight: RAIL_COUNT.chipPadXPx,
                      },
                    }}
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
                  sx={{
                    p: 0,
                    width: RAIL_COUNT.chevronPx,
                    height: RAIL_COUNT.chevronPx,
                    flexShrink: 0,
                    color: 'inherit',
                    transform: expanded ? 'rotate(180deg)' : undefined,
                    transition: 'transform 120ms',
                  }}
                >
                  <ExpandMoreIcon sx={{ fontSize: 16 }} />
                </IconButton>
              </Box>
              <Collapse in={expanded} unmountOnExit>
                <Box sx={{ display: 'grid', gap: NAV_MOCK.groupGap }}>
                  {d.items.map((l) => {
                    const on = leafIsActive(l.href, pathname, searchStr);
                    return (
                      <Box
                        key={l.href}
                        component={NextLink}
                        href={l.href}
                        prefetch
                        onClick={onNavigate}
                        aria-current={on ? 'page' : undefined}
                        sx={itemSx(on)}
                      >
                        {l.label}
                      </Box>
                    );
                  })}
                </Box>
              </Collapse>
            </Box>
          );
        })}
      </Box>
      <Box sx={{ flexShrink: 0 }}>
        <Box
          component={NextLink}
          href="/directory"
          onClick={onNavigate}
          aria-current={pathname === '/directory' ? 'page' : undefined}
          data-testid="rail-directory"
          sx={itemSx(pathname === '/directory')}
        >
          What CIP does
          <Box component="small" sx={{ display: 'block', fontSize: NAV_MOCK.foot.fontSize, fontWeight: 400, opacity: 0.85 }}>
            Capability directory
          </Box>
        </Box>
      </Box>
      <Box
        sx={{
          flexShrink: 0,
          padding: NAV_MOCK.foot.padding,
          borderTop: '1px solid',
          borderColor: 'divider',
          color: 'text.secondary',
          fontSize: NAV_MOCK.foot.fontSize,
          lineHeight: 1.45,
          // Mock-up `.sidebar-foot`: the rail's own gap already separates it from the block above.
          marginTop: 0,
        }}
      >
        Your workspace
        <br />
        Only data you can access
        {displayName ? (
          <Box sx={{ mt: '8px', fontWeight: 500, color: 'text.primary', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {displayName}
          </Box>
        ) : null}
        {sessionMeta ? <Box sx={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{sessionMeta}</Box> : null}
      </Box>
    </Box>
  );
}
