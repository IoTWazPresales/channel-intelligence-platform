'use client';

import SearchIcon from '@mui/icons-material/Search';
import { Box, Dialog, InputBase, List, ListItemButton, ListItemText, Stack, Typography } from '@mui/material';
import { useRouter } from 'next/navigation';
import { useEffect, useMemo, useState } from 'react';

import { CapabilityStatus } from '@/features/shell/CapabilityStatus';
import { leafStatus, shellNavGroups, type LeafStatus } from '@/features/shell/navConfig';

export type PaletteHit = {
  label: string;
  domain: string;
  meta: string;
  href: string;
  status: LeafStatus;
};

/** Pure ranking so it can be unit-tested without the dialog. */
export function paletteHits(role: string | null | undefined, query: string, limit = 12): PaletteHit[] {
  const needle = query.trim().toLowerCase();
  const all: PaletteHit[] = shellNavGroups(role).flatMap((g) =>
    g.items.map((l) => ({
      label: l.label,
      domain: g.label,
      meta: l.what ?? '',
      href: l.href,
      status: leafStatus(l),
    })),
  );
  const navigable = all.filter((h) => h.status !== 'planned');
  if (!needle) return navigable.filter((h) => h.status === 'live' || h.status === 'partial').slice(0, 8);
  const score = (h: PaletteHit): number => {
    const label = h.label.toLowerCase();
    const domain = h.domain.toLowerCase();
    if (label.startsWith(needle)) return 4;
    if (label.includes(needle)) return 3;
    if (domain.includes(needle)) return 2;
    if (h.meta.toLowerCase().includes(needle)) return 1;
    return 0;
  };
  return navigable
    .map((h) => ({ h, s: score(h) }))
    .filter((x) => x.s > 0)
    .sort((a, b) => b.s - a.s)
    .slice(0, limit)
    .map((x) => x.h);
}

/**
 * Findability accelerator (not the primary IA): every workflow the role may see, by name, domain
 * or what-it-does. Partial / data-only leaves carry their status so nothing unbuilt is dressed up
 * as working; planned leaves are not navigable and stay in the directory.
 */
export function CommandPalette({ open, onClose, role }: { open: boolean; onClose: () => void; role?: string | null }) {
  const router = useRouter();
  const [q, setQ] = useState('');
  useEffect(() => {
    if (!open) setQ('');
  }, [open]);

  const hits = useMemo(() => paletteHits(role, q), [role, q]);

  return (
    <Dialog
      open={open}
      onClose={onClose}
      fullWidth
      maxWidth="sm"
      PaperProps={{ sx: { mt: { xs: 2, md: 10 }, alignSelf: 'flex-start' } }}
    >
      <Box
        data-testid="command-palette"
        sx={{ display: 'flex', alignItems: 'center', gap: 1, px: 2, py: 1.5, borderBottom: '1px solid', borderColor: 'divider' }}
      >
        <SearchIcon fontSize="small" color="disabled" />
        <InputBase
          autoFocus
          fullWidth
          placeholder="Find a workflow…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          inputProps={{ 'aria-label': 'Search CIP workflows', 'data-testid': 'command-palette-input' }}
        />
        <Typography variant="caption" color="text.disabled">
          Esc
        </Typography>
      </Box>
      <List dense sx={{ maxHeight: 420, overflow: 'auto' }}>
        {hits.map((h) => (
          <ListItemButton
            key={`${h.href}-${h.label}`}
            onClick={() => {
              onClose();
              router.push(h.href);
            }}
          >
            <ListItemText
              primary={
                <Stack direction="row" spacing={1} alignItems="center">
                  <span>
                    {h.domain} › {h.label}
                  </span>
                  <CapabilityStatus status={h.status} size="inline" />
                </Stack>
              }
              secondary={h.meta}
              primaryTypographyProps={{ variant: 'body2', fontWeight: 500, component: 'div' }}
              secondaryTypographyProps={{ variant: 'caption', noWrap: true }}
            />
          </ListItemButton>
        ))}
        {!hits.length ? (
          <Typography variant="body2" color="text.secondary" sx={{ p: 2 }}>
            Nothing matches “{q}”. The capability directory lists everything, including planned work.
          </Typography>
        ) : null}
      </List>
    </Dialog>
  );
}
