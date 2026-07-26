'use client';

import MoreVertIcon from '@mui/icons-material/MoreVert';
import { Box, IconButton, Menu, MenuItem } from '@mui/material';
import type { UseMutationResult } from '@tanstack/react-query';
import { useState } from 'react';

/** Shipment plan options — effective refresh only (no global-suspicious; D-012 waiver). */
export function ShipmentPlanOptionsMenu({
  planLoadToken,
  refreshPlanEffective,
  optionsOpenTestId,
  optionsMenuTestId,
  refreshEffectiveTestId,
}: {
  planLoadToken: number;
  refreshPlanEffective: UseMutationResult<Record<string, unknown>, Error, void>;
  optionsOpenTestId: string;
  optionsMenuTestId: string;
  refreshEffectiveTestId: string;
}) {
  const [menuAnchor, setMenuAnchor] = useState<null | HTMLElement>(null);

  return (
    <>
      <Box sx={{ flexGrow: 1 }} />
      <IconButton
        size="small"
        aria-label="Resolution plan options"
        onClick={(e) => setMenuAnchor(e.currentTarget)}
        data-testid={optionsOpenTestId}
      >
        <MoreVertIcon fontSize="small" />
      </IconButton>
      <Menu
        anchorEl={menuAnchor}
        open={Boolean(menuAnchor)}
        onClose={() => setMenuAnchor(null)}
        data-testid={optionsMenuTestId}
      >
        <MenuItem
          disabled={planLoadToken === 0 || refreshPlanEffective.isPending}
          onClick={() => {
            setMenuAnchor(null);
            void refreshPlanEffective.mutateAsync().catch(() => {});
          }}
          data-testid={refreshEffectiveTestId}
        >
          Update plan after edits
        </MenuItem>
      </Menu>
    </>
  );
}
