'use client';

/**
 * The widget's three-dot menu (spec s.6): Edit stays a visible icon; the rest live here. Every action
 * has a test id. A disabled action says why (as its secondary text, not only a tooltip).
 */

import MoreVertIcon from '@mui/icons-material/MoreVert';
import {
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  Divider,
  IconButton,
  ListItemText,
  Menu,
  MenuItem,
  Tooltip,
} from '@mui/material';
import { useState, type Ref } from 'react';

export type WidgetAction = {
  id: 'duplicate' | 'fullscreen' | 'view-rows' | 'export-csv' | 'export-png' | 'promote' | 'remove';
  label: string;
  onClick: () => void;
  /** Why the action is not available, shown under its label. */
  disabledReason?: string | null;
  /** Ask before running (Remove). */
  confirm?: { title: string; body: string; confirmLabel: string };
  dividerBefore?: boolean;
};

export function WidgetMenu({ widgetId, title, actions, buttonRef }: { widgetId: number | string; title: string; actions: WidgetAction[]; buttonRef?: Ref<HTMLButtonElement> }) {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const [pending, setPending] = useState<WidgetAction | null>(null);
  const close = () => setAnchor(null);
  return (
    <>
      <Tooltip title="Widget actions">
        <IconButton
          ref={buttonRef}
          size="small"
          aria-label={`Actions for ${title}`}
          aria-haspopup="menu"
          aria-expanded={anchor ? true : undefined}
          onClick={(e) => setAnchor(e.currentTarget)}
          data-testid={`dashboard-widget-menu-${widgetId}`}
        >
          <MoreVertIcon fontSize="small" />
        </IconButton>
      </Tooltip>
      <Menu anchorEl={anchor} open={Boolean(anchor)} onClose={close} slotProps={{ paper: { sx: { minWidth: 220, maxWidth: 320 } } }}>
        {actions.flatMap((a) => {
          const item = (
            <MenuItem
              key={a.id}
              disabled={Boolean(a.disabledReason)}
              onClick={() => {
                close();
                if (a.confirm) setPending(a);
                else a.onClick();
              }}
              data-testid={`dashboard-widget-${a.id}-${widgetId}`}
              sx={{ whiteSpace: 'normal', '&.Mui-disabled': { opacity: 1, '& .MuiListItemText-primary': { color: 'text.disabled' } } }}
            >
              <ListItemText primary={a.label} secondary={a.disabledReason ?? undefined} slotProps={{ secondary: { variant: 'caption' } }} />
            </MenuItem>
          );
          return a.dividerBefore ? [<Divider key={`${a.id}-divider`} />, item] : [item];
        })}
      </Menu>
      <Dialog open={Boolean(pending)} onClose={() => setPending(null)} maxWidth="xs" fullWidth>
        <DialogTitle>{pending?.confirm?.title}</DialogTitle>
        <DialogContent>
          <DialogContentText>{pending?.confirm?.body}</DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPending(null)}>Cancel</Button>
          <Button
            color="error"
            variant="contained"
            onClick={() => {
              const a = pending;
              setPending(null);
              a?.onClick();
            }}
            data-testid={`dashboard-widget-confirm-${widgetId}`}
          >
            {pending?.confirm?.confirmLabel}
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
