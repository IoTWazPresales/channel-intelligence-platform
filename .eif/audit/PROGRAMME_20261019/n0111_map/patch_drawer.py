"""One-off: show every identifier a steward candidate's rows carried (N-0111, 2026-10-19)."""

from pathlib import Path

p = Path("apps/web/src/app/(app)/admin/imports/CstCandidateStewardDrawer.tsx")
s = p.read_bytes().decode("utf-8")
crlf = "\r\n" in s
s = s.replace("\r\n", "\n")


def rep(old: str, new: str) -> None:
    global s
    assert s.count(old) == 1, (old[:60], s.count(old))
    s = s.replace(old, new)


rep(
    """type DimPick = { id: number; label: string };
""",
    """type DimPick = { id: number; label: string };

const IDENTIFIER_LABELS: Record<string, string> = {
  part_number: 'Part number',
  barcode: 'Barcode',
  sales_model: 'Sales model',
  any_identifier: 'Product code (older layout)',
  customer_code: 'Customer product code',
};

type IdentifierMatch = { slot?: string; token?: string; status?: string; tier?: string | null; product_ids?: number[] };
type IdentifierRow = { identifiers?: Record<string, string>; tier?: string | null; matched?: IdentifierMatch[] };

function matchText(m: IdentifierMatch | undefined): string {
  if (!m) return '';
  if (m.status === 'unique') return `matches product ${m.product_ids?.[0] ?? ''} (${m.tier ?? ''})`;
  if (m.status === 'ambiguous') return `matches ${m.product_ids?.length ?? 'several'} products`;
  return 'no match';
}

/** Every identifier the candidate's rows carried, with what each matched (N-0111). */
function CandidateIdentifiers({ context }: { context: Record<string, unknown> | null | undefined }) {
  const rows = (context?.identifier_rows as IdentifierRow[] | undefined) ?? [];
  const conflicts = Number(context?.identifier_conflict_rows ?? 0);
  if (!rows.length && !conflicts) return null;
  return (
    <Stack spacing={1} data-testid="cst-import-identifiers">
      {conflicts > 0 ? (
        <Alert severity="warning" data-testid="cst-import-identifier-conflict">
          {conflicts} row{conflicts === 1 ? '' : 's'} carry identifiers that point at different products. They are not
          loaded until you choose the product.
        </Alert>
      ) : null}
      <Typography variant="subtitle2">Identifiers on these rows</Typography>
      {rows.map((r, i) => (
        <Box key={i} sx={{ border: 1, borderColor: 'divider', borderRadius: 1, p: 1 }}>
          {Object.entries(r.identifiers ?? {}).map(([slot, token]) => (
            <Typography key={slot} variant="body2">
              {IDENTIFIER_LABELS[slot] ?? slot}: <strong>{token}</strong>
              {r.matched ? (
                <Typography component="span" variant="caption" color="text.secondary">
                  {' '}
                  · {matchText(r.matched.find((m) => m.slot === slot))}
                </Typography>
              ) : null}
            </Typography>
          ))}
        </Box>
      ))}
    </Stack>
  );
}
""",
)

rep(
    """        <StewardSuggestionCards
          suggestions={suggestionItems}""",
    """        {entity === 'product' ? <CandidateIdentifiers context={candidate.context} /> : null}

        <StewardSuggestionCards
          suggestions={suggestionItems}""",
)

if crlf:
    s = s.replace("\n", "\r\n")
p.write_bytes(s.encode("utf-8"))
print("patched", p)
