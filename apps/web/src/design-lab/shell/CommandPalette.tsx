'use client';

import SearchIcon from '@mui/icons-material/Search';
import { Box, Dialog, InputBase, List, ListItemButton, ListItemText, Typography } from '@mui/material';
import { useRouter } from 'next/navigation';
import { useEffect, useMemo, useState } from 'react';

import { customers, distributors, products } from '../fixtures/entities';
import { inRail, labDomains } from './labNav';

type Hit = { kind: 'workflow' | 'product' | 'customer' | 'distributor'; label: string; meta: string; href: string };

/** Findability accelerator (not the primary IA): workflows by name/what-it-does, plus entities. */
export function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const router = useRouter();
  const [q, setQ] = useState('');
  useEffect(() => {
    if (!open) setQ('');
  }, [open]);

  const hits = useMemo<Hit[]>(() => {
    const needle = q.trim().toLowerCase();
    const workflows: Hit[] = labDomains.flatMap((d) =>
      d.leaves
        .filter(inRail)
        .map((l) => ({ kind: 'workflow' as const, label: `${d.label} › ${l.label}${l.status === 'partial' ? ' (partly built)' : ''}`, meta: l.what, href: l.href }))
    );
    if (!needle) return workflows.slice(0, 8);
    const ents: Hit[] = [
      ...products.map((p) => ({ kind: 'product' as const, label: p.name, meta: `${p.sku} · ${p.family}`, href: `/design-lab/stock?lens=cover&product=${p.id}` })),
      ...customers.map((c) => ({ kind: 'customer' as const, label: c.name, meta: c.group, href: `/design-lab/planning?customer=${c.id}` })),
      ...distributors.map((d) => ({ kind: 'distributor' as const, label: d.name, meta: d.region, href: `/design-lab/stock?lens=cover&distributor=${d.id}` })),
    ];
    return [...workflows, ...ents].filter((h) => `${h.label} ${h.meta}`.toLowerCase().includes(needle)).slice(0, 12);
  }, [q]);

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm" PaperProps={{ sx: { mt: { xs: 2, md: 10 }, alignSelf: 'flex-start' } }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, px: 2, py: 1.5, borderBottom: '1px solid', borderColor: 'divider' }}>
        <SearchIcon fontSize="small" color="disabled" />
        <InputBase
          autoFocus
          fullWidth
          placeholder="Find a workflow, product, customer or distributor…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          inputProps={{ 'aria-label': 'Search CIP' }}
        />
        <Typography variant="caption" color="text.disabled">
          Esc
        </Typography>
      </Box>
      <List dense sx={{ maxHeight: 420, overflow: 'auto' }}>
        {hits.map((h) => (
          <ListItemButton
            key={`${h.kind}-${h.href}-${h.label}`}
            onClick={() => {
              onClose();
              router.push(h.href);
            }}
          >
            <ListItemText
              primary={h.label}
              secondary={h.meta}
              primaryTypographyProps={{ variant: 'body2', fontWeight: 500 }}
              secondaryTypographyProps={{ variant: 'caption', noWrap: true }}
            />
            <Typography variant="caption" color="text.disabled" sx={{ ml: 2, textTransform: 'capitalize' }}>
              {h.kind}
            </Typography>
          </ListItemButton>
        ))}
        {!hits.length ? (
          <Typography variant="body2" color="text.secondary" sx={{ p: 2 }}>
            Nothing matches “{q}”.
          </Typography>
        ) : null}
      </List>
    </Dialog>
  );
}
