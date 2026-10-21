"""One-off: patch CstBulkUploadDialog.tsx for the identifier slots and the re-map offer (N-0111, 2026-10-19)."""

from pathlib import Path

p = Path("apps/web/src/app/(app)/admin/imports/CstBulkUploadDialog.tsx")
s = p.read_bytes().decode("utf-8")
crlf = "\r\n" in s
s = s.replace("\r\n", "\n")


def rep(old: str, new: str, count: int = 1) -> None:
    global s
    assert s.count(old) == count, (old[:80], s.count(old))
    s = s.replace(old, new)


rep(
    """  layout: { id: number; name: string } | null;
  similar_layout?:""",
    """  layout: {
    id: number;
    name: string;
    /** The layout maps the older single product column (it keeps loading as before). */
    legacy_product_slot?: boolean;
    /** What the layout maps today, by this file's headers. */
    mapping?: Record<string, string>;
  } | null;
  similar_layout?:""",
)

rep(
    """/** A column layout not yet saved: the file headers the mapping step is working on. */
type NewLayoutDraft = {
  signature: string;""",
    """/** A column layout not yet saved, or a saved one being re-mapped: the file headers the mapping step is working on. */
type NewLayoutDraft = {
  signature: string;
  /** Set when a saved layout is being re-mapped into the separate identifier columns. */
  layoutId?: number;""",
)

rep(
    """/** The product column and a figure to load must be mapped (the same gate the server applies). */
const REQUIRED_GROUPS: CanonicalRequiredGroup[] = [
  { id: 'product', label: 'Product (code, barcode or SKU)', anyOf: ['raw_product_token'] },""",
    """/** The older single product column; offered only while a layout still uses it. */
const LEGACY_PRODUCT_TARGET = 'raw_product_token';

/** A product identifier and a figure to load must be mapped (the same gate the server applies). */
const REQUIRED_GROUPS: CanonicalRequiredGroup[] = [
  {
    id: 'product',
    label: 'Product identifier (part number, barcode, sales model or customer product code)',
    anyOf: [
      'raw_part_number_token',
      'raw_barcode_token',
      'raw_sales_model_token',
      'raw_article_token',
      LEGACY_PRODUCT_TARGET,
    ],
  },""",
)

rep(
    """  const [layoutNames, setLayoutNames] = useState<Record<string, string>>({});

  const { data: customers""",
    """  const [layoutNames, setLayoutNames] = useState<Record<string, string>>({});
  /** Signatures of saved layouts the uploader chose to re-map into the separate identifier columns. */
  const [remapped, setRemapped] = useState<Record<string, boolean>>({});

  const { data: customers""",
)

rep(
    """    setDrafts({});
    setLayoutNames({});
  }, []);""",
    """    setDrafts({});
    setLayoutNames({});
    setRemapped({});
  }, []);""",
)

rep(
    """    const bySig = new Map<string, NewLayoutDraft>();
    for (const f of preview?.files ?? []) {
      if (!f.readable || f.layout || !f.layout_signature) continue;
      const cur = bySig.get(f.layout_signature);
      if (cur) cur.filenames.push(f.filename);
      else
        bySig.set(f.layout_signature, {
          signature: f.layout_signature,
          filenames: [f.filename],
          columns: f.columns,
          samples: f.samples,
          similar: f.similar_layout ?? null,
        });
    }
    return [...bySig.values()];
  }, [preview]);""",
    """    const bySig = new Map<string, NewLayoutDraft>();
    for (const f of preview?.files ?? []) {
      if (!f.readable || !f.layout_signature) continue;
      if (f.layout && !remapped[f.layout_signature]) continue;
      const cur = bySig.get(f.layout_signature);
      if (cur) cur.filenames.push(f.filename);
      else
        bySig.set(f.layout_signature, {
          signature: f.layout_signature,
          layoutId: f.layout?.id,
          filenames: [f.filename],
          columns: f.columns,
          samples: f.samples,
          similar: f.similar_layout ?? null,
        });
    }
    return [...bySig.values()];
  }, [preview, remapped]);

  /** Saved layouts that still map the older single product column: they load as before; re-map is offered. */
  const legacyLayouts = useMemo(() => {
    const bySig = new Map<
      string,
      { signature: string; name: string; mapping: Record<string, string>; filenames: string[] }
    >();
    for (const f of preview?.files ?? []) {
      if (!f.readable || !f.layout?.legacy_product_slot || !f.layout_signature) continue;
      const cur = bySig.get(f.layout_signature);
      if (cur) cur.filenames.push(f.filename);
      else
        bySig.set(f.layout_signature, {
          signature: f.layout_signature,
          name: f.layout.name,
          mapping: f.layout.mapping ?? {},
          filenames: [f.filename],
        });
    }
    return [...bySig.values()];
  }, [preview]);""",
)

rep(
    """            newLayouts.map((l) => ({
              signature: l.signature,
              name: (layoutNames[l.signature] ?? '').trim(),
              field_mapping: drafts[l.signature] ?? {},
            }))""",
    """            newLayouts.map((l) => ({
              signature: l.signature,
              ...(l.layoutId != null ? { layout_id: l.layoutId } : {}),
              name: (layoutNames[l.signature] ?? '').trim(),
              field_mapping: drafts[l.signature] ?? {},
            }))""",
)

rep(
    """  const targets = preview?.targets ?? [];
  const failed""",
    """  const targets = preview?.targets ?? [];
  /** The older single product column is offered for a layout only while that layout still maps it. */
  const targetsFor = (draft: Record<string, string>): CanonicalTargetOption[] =>
    Object.values(draft).includes(LEGACY_PRODUCT_TARGET)
      ? targets
      : targets.filter((t) => t.value !== LEGACY_PRODUCT_TARGET);
  const failed""",
)

rep(
    """                        ) : info.layout ? (
                          <Chip size="small" color="success" variant="outlined" label={`Layout: ${info.layout.name}`} />
                        ) : (""",
    """                        ) : info.layout ? (
                          <Chip
                            size="small"
                            color={info.layout.legacy_product_slot ? 'default' : 'success'}
                            variant="outlined"
                            label={`Layout: ${info.layout.name}${info.layout.legacy_product_slot ? ' (older product column)' : ''}`}
                          />
                        ) : (""",
)

rep(
    """              {newLayouts.length === 0 && readableCount > 0 ? (
                <Alert severity="success">
                  Every file matches a saved layout of this customer. Nothing to map.
                </Alert>
              ) : null}""",
    """              {newLayouts.length === 0 && readableCount > 0 ? (
                <Alert severity="success">
                  Every file matches a saved layout of this customer. Nothing to map.
                </Alert>
              ) : null}
              {legacyLayouts
                .filter((l) => !remapped[l.signature])
                .map((l) => (
                  <Alert
                    key={l.signature}
                    severity="info"
                    data-testid={`cst-legacy-layout-${l.signature}`}
                    action={
                      <Button
                        size="small"
                        data-testid={`cst-remap-${l.signature}`}
                        onClick={() => {
                          setRemapped((p) => ({ ...p, [l.signature]: true }));
                          // Start from what the layout maps today; its older product column is left to re-map.
                          setDrafts((p) => ({ ...p, [l.signature]: { ...l.mapping } }));
                          setLayoutNames((p) => ({ ...p, [l.signature]: l.name }));
                        }}
                      >
                        Re-map product columns
                      </Button>
                    }
                  >
                    Layout {l.name} maps one product column that may hold any identifier. It keeps loading as before.
                    You can re-map it into Part number, Barcode, Sales model and Customer product code.
                  </Alert>
                ))}""",
)

rep(
    """                    <Stack spacing={1}>
                      <Typography variant="subtitle2">
                        New column layout · {l.filenames.length} file{l.filenames.length === 1 ? '' : 's'}
                      </Typography>""",
    """                    <Stack spacing={1}>
                      <Typography variant="subtitle2">
                        {l.layoutId != null ? 'Re-map column layout' : 'New column layout'} · {l.filenames.length} file
                        {l.filenames.length === 1 ? '' : 's'}
                      </Typography>""",
)

rep(
    """                        onChange={(e) => setLayoutNames((p) => ({ ...p, [l.signature]: e.target.value }))}
                        sx={{ maxWidth: 420 }}
                      />""",
    """                        onChange={(e) => setLayoutNames((p) => ({ ...p, [l.signature]: e.target.value }))}
                        disabled={l.layoutId != null}
                        sx={{ maxWidth: 420 }}
                      />""",
)

rep(
    """                        targetOptions={targets}
                        columnSamples={l.samples}""",
    """                        targetOptions={targetsFor(drafts[l.signature] ?? {})}
                        columnNotes={
                          l.layoutId != null
                            ? Object.fromEntries(
                                Object.entries(drafts[l.signature] ?? {})
                                  .filter(([, t]) => t === LEGACY_PRODUCT_TARGET)
                                  .map(([h]) => [
                                    h,
                                    'Older single product column. Re-map it to Part number, Barcode, Sales model or Customer product code.',
                                  ])
                              )
                            : undefined
                        }
                        columnSamples={l.samples}""",
)

if crlf:
    s = s.replace("\n", "\r\n")
p.write_bytes(s.encode("utf-8"))
print("patched", p)
