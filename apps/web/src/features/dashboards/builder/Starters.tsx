'use client';

/**
 * Starter templates (spec s.7, S14): listed from `GET /dashboards/templates`, created on demand as a
 * personal dashboard, marked "Template — editable", with what each one leaves out and why.
 */

import CloseIcon from '@mui/icons-material/Close';
import { Alert, Box, Button, Card, CardActions, CardContent, Chip, Collapse, IconButton, Stack, Typography } from '@mui/material';
import { useEffect, useState } from 'react';

import type { DashboardTemplate } from './types';

function LeftOut({ items, testId }: { items: DashboardTemplate['left_out']; testId: string }) {
  if (!items.length) return null;
  return (
    <Box component="ul" sx={{ m: 0, pl: 2.5 }} data-testid={testId}>
      {items.map((it) => (
        <Typography component="li" variant="caption" color="text.secondary" key={it.what} sx={{ display: 'list-item' }}>
          <strong>{it.what}</strong>: {it.reason}
        </Typography>
      ))}
    </Box>
  );
}

export function StarterGallery({
  templates,
  onPick,
  creatingKey,
  heading = 'Start from a starter',
}: {
  templates: DashboardTemplate[];
  onPick: (key: string) => void;
  creatingKey?: string | null;
  heading?: string;
}) {
  const [open, setOpen] = useState<string | null>(null);
  if (!templates.length) return null;
  return (
    <Box data-testid="starter-gallery">
      <Typography variant="subtitle1" fontWeight={700} sx={{ mb: 1 }} component="h2">
        {heading}
      </Typography>
      <Box sx={{ display: 'grid', gap: 1.5, gridTemplateColumns: { xs: 'minmax(0, 1fr)', md: 'repeat(3, minmax(0, 1fr))' } }}>
        {templates.map((t) => (
          <Card variant="outlined" key={t.key} data-testid={`starter-${t.key}`} sx={{ display: 'flex', flexDirection: 'column' }}>
            <CardContent sx={{ flex: 1 }}>
              <Typography variant="subtitle2" fontWeight={700} component="h3">
                {t.title}
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                {t.description}
              </Typography>
              <Stack direction="row" spacing={1} sx={{ mt: 1 }} flexWrap="wrap" useFlexGap>
                <Chip size="small" label={`${t.widget_count} widgets`} />
                {t.required_filters.map((r) => (
                  <Chip size="small" variant="outlined" key={r} label={`Needs a ${r}`} />
                ))}
              </Stack>
              {t.left_out.length ? (
                <>
                  <Button size="small" sx={{ mt: 1, px: 0 }} onClick={() => setOpen((o) => (o === t.key ? null : t.key))} aria-expanded={open === t.key}>
                    Left out ({t.left_out.length})
                  </Button>
                  <Collapse in={open === t.key}>
                    <LeftOut items={t.left_out} testId={`starter-left-out-${t.key}`} />
                  </Collapse>
                </>
              ) : null}
            </CardContent>
            <CardActions>
              <Button size="small" variant="contained" disabled={Boolean(creatingKey)} onClick={() => onPick(t.key)} data-testid={`starter-create-${t.key}`}>
                {creatingKey === t.key ? 'Creating…' : 'Create my copy'}
              </Button>
            </CardActions>
          </Card>
        ))}
      </Box>
    </Box>
  );
}

const DISMISS_KEY = 'cip.dashboard.template-note.dismissed';

function readDismissed(): number[] {
  try {
    const raw = window.localStorage.getItem(DISMISS_KEY);
    const v = raw ? (JSON.parse(raw) as unknown) : [];
    return Array.isArray(v) ? v.filter((x): x is number => typeof x === 'number') : [];
  } catch {
    return [];
  }
}

function writeDismissed(ids: number[]) {
  try {
    window.localStorage.setItem(DISMISS_KEY, JSON.stringify(ids.slice(-50)));
  } catch {
    /* storage unavailable: the note simply comes back */
  }
}

/** "Template — editable" chip. */
export function TemplateChip() {
  return <Chip size="small" color="secondary" variant="outlined" label="Template — editable" data-testid="dashboard-template-chip" />;
}

/** The starter's one-line description and what it leaves out; dismissible per dashboard. */
export function TemplateNote({ dashboardId, description, template }: { dashboardId: number; description: string | null; template?: DashboardTemplate }) {
  const [hidden, setHidden] = useState(false);
  useEffect(() => setHidden(readDismissed().includes(dashboardId)), [dashboardId]);
  if (hidden) return null;
  const text = description || template?.description;
  return (
    <Alert
      severity="info"
      variant="outlined"
      data-testid="dashboard-template-note"
      action={
        <IconButton
          size="small"
          aria-label="Dismiss the starter note"
          onClick={() => {
            writeDismissed([...readDismissed(), dashboardId]);
            setHidden(true);
          }}
        >
          <CloseIcon fontSize="small" />
        </IconButton>
      }
    >
      {text ? <Typography variant="body2">{text}</Typography> : null}
      {template?.left_out.length ? (
        <>
          <Typography variant="caption" fontWeight={700} display="block" sx={{ mt: 0.5 }}>
            Left out, and why
          </Typography>
          <LeftOut items={template.left_out} testId="dashboard-template-left-out" />
        </>
      ) : null}
    </Alert>
  );
}
