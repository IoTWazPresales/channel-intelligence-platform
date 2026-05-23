'use client';

import { Box, Button, Stack, Typography } from '@mui/material';

import type { DsiCandidateRow } from './dsi-mapping-steward-panel';

function peerDisplayLines(peer: DsiCandidateRow): { account: string; source: string; rows: number } {
  const c = (peer.context ?? null) as Record<string, unknown> | null;
  const raw =
    typeof c?.dealer_group_account_raw === 'string' ? c.dealer_group_account_raw.trim() : '';
  const account = (raw || peer.dealer_group_token || peer.normalized_key || '').toString();
  const samples = c?.source_customer_name_raw_samples;
  let source = '';
  if (Array.isArray(samples)) {
    source = samples
      .filter((x) => typeof x === 'string' && x.trim())
      .map((x) => String(x).trim())
      .join('; ');
  }
  return { account, source, rows: peer.row_count ?? 0 };
}

/** Inline duplicate peer summary — does not change drawer scroll position. */
export function DsiDuplicatePeerCompare({
  normalizedKey,
  lookupPeerCandidate,
  onOpenFullSteward,
}: {
  normalizedKey: string;
  lookupPeerCandidate?: (normalizedKey: string) => DsiCandidateRow | null;
  onOpenFullSteward?: (normalizedKey: string) => void;
}) {
  const peer = lookupPeerCandidate?.(normalizedKey) ?? null;

  return (
    <Box
      sx={{ mt: 0.75, mb: 0.5, pl: 1.5, borderLeft: 2, borderColor: 'warning.light' }}
      data-testid={`dsi-duplicate-peer-inline-${normalizedKey}`}
    >
      {peer ? (
        <Stack spacing={0.5}>
          {(() => {
            const { account, source, rows } = peerDisplayLines(peer);
            return (
              <>
                <Typography variant="caption" color="text.secondary">
                  <strong>Peer account:</strong> {account || '—'}
                </Typography>
                {source ? (
                  <Typography variant="caption" color="text.secondary" display="block">
                    <strong>Source customer:</strong> {source}
                  </Typography>
                ) : null}
                <Typography variant="caption" color="text.secondary" display="block">
                  <strong>Staging rows:</strong> {rows} · <strong>Status:</strong> {peer.status || '—'}
                </Typography>
              </>
            );
          })()}
        </Stack>
      ) : (
        <Typography variant="caption" color="text.secondary">
          Peer not on this page. Filter by normalized key <code>{normalizedKey}</code> or open from the grid.
        </Typography>
      )}
      {onOpenFullSteward ? (
        <Button
          size="small"
          variant="text"
          sx={{ mt: 0.5, p: 0, minWidth: 0 }}
          onClick={() => onOpenFullSteward(normalizedKey)}
          data-testid="dsi-duplicate-peer-open-steward"
        >
          Open full steward for peer
        </Button>
      ) : null}
    </Box>
  );
}
