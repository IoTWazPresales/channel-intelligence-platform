"""One-off: update CstBulkUploadDialog.test.tsx for the identifier slots and the re-map offer (N-0111, 2026-10-19)."""

from pathlib import Path

p = Path("apps/web/src/app/(app)/admin/imports/CstBulkUploadDialog.test.tsx")
s = p.read_bytes().decode("utf-8")
crlf = "\r\n" in s
s = s.replace("\r\n", "\n")


def rep(old: str, new: str) -> None:
    global s
    assert s.count(old) == 1, (old[:70], s.count(old))
    s = s.replace(old, new)


rep(
    """const TARGETS = [
  { value: 'raw_product_token', label: 'Product (code, barcode or SKU)' },
  { value: 'units_sold', label: 'Units sold' },
  { value: 'reported_soh', label: 'On-hand (stock)' },
];""",
    """const LEGACY_LABEL = 'Product, any identifier (older layouts)';
const TARGETS = [
  { value: 'raw_sales_model_token', label: 'Sales model / marketing name', group: 'main' },
  { value: 'raw_part_number_token', label: 'Part number', group: 'main' },
  { value: 'raw_barcode_token', label: 'Barcode (EAN or UPC)', group: 'main' },
  { value: 'raw_article_token', label: 'Customer product code', group: 'main' },
  { value: 'units_sold', label: 'Units sold', group: 'main' },
  { value: 'reported_soh', label: 'On-hand (stock)', group: 'main' },
  { value: 'unit_mac', label: 'Unit MAC', group: 'more' },
  { value: 'raw_product_token', label: LEGACY_LABEL, group: 'more', legacy: true },
];""",
)

rep(
    """    // The dropdown is portalled outside the dialog, so the dialog marks it hidden to role queries.
    await user.click(await screen.findByRole('option', { name: /Product \\(code, barcode or SKU\\)/, hidden: true }));
    await waitFor(() => expect(screen.getByTestId('cst-bulk-upload-submit')).toBeEnabled());
""",
    """    // The dropdown is portalled outside the dialog, so the dialog marks it hidden to role queries.
    // It offers the separate identifier columns and a "More columns" group, but not the older single column.
    expect(await screen.findByRole('option', { name: /^Part number/, hidden: true })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: /^Sales model \\/ marketing name/, hidden: true })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: /^Customer product code/, hidden: true })).toBeInTheDocument();
    expect(screen.getByText('More columns')).toBeInTheDocument();
    expect(screen.getByRole('option', { name: /^Unit MAC/, hidden: true })).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: LEGACY_LABEL, hidden: true })).toBeNull();
    await user.click(screen.getByRole('option', { name: /^Barcode \\(EAN or UPC\\)/, hidden: true }));
    await waitFor(() => expect(screen.getByTestId('cst-bulk-upload-submit')).toBeEnabled());
""",
)

rep(
    """        field_mapping: { Stuks: 'units_sold', 'Artikel Nr': 'raw_product_token' },
      },
    ]);
  });
""",
    """        field_mapping: { Stuks: 'units_sold', 'Artikel Nr': 'raw_barcode_token' },
      },
    ]);
  });

  it('a layout that maps the older single product column keeps loading and is offered a re-map into the new slots', async () => {
    apiPostMock.mockImplementation(async (path: string) => {
      if (path.endsWith('/batch-propose')) {
        return {
          group_count: 1,
          file_count: 1,
          customer_id: 20,
          targets: TARGETS,
          files: [
            {
              filename: 'week 1.csv',
              readable: true,
              columns: ['Artikel Nr', 'Stuks'],
              layout_signature: 'sigOLD',
              layout: {
                id: 7,
                name: 'Weekly report',
                legacy_product_slot: true,
                mapping: { 'Artikel Nr': 'raw_product_token', Stuks: 'units_sold' },
              },
              detected_mapping: {},
              samples: { 'Artikel Nr': ['A1'], Stuks: ['3'] },
            },
          ],
        };
      }
      return { group_count: 1, jobs: [{ outcome: 'created', import_job_id: 57, filenames: ['week 1.csv'] }] };
    });
    const { user, onJobsCreated } = renderDialog();
    await pickCustomer(user, 'Takealot');
    await user.upload(document.querySelector('input[type="file"]') as HTMLInputElement, file());
    await user.click(screen.getByTestId('cst-bulk-preview-groups'));

    // It still matches by itself (nothing to map) and the file list says the layout is the older kind.
    expect(await screen.findByText(/Every file matches a saved layout/)).toBeInTheDocument();
    expect(screen.getByText('Layout: Weekly report (older product column)')).toBeInTheDocument();
    const offer = screen.getByTestId('cst-legacy-layout-sigOLD');
    expect(offer).toHaveTextContent('It keeps loading as before');
    expect(screen.getByTestId('cst-bulk-upload-submit')).toBeEnabled();

    // Re-map: the mapping step opens on what the layout maps today, with the older column flagged.
    await user.click(within(offer).getByTestId('cst-remap-sigOLD'));
    const card = await screen.findByTestId('cst-new-layout-sigOLD');
    expect(within(card).getByText(/Re-map column layout/)).toBeInTheDocument();
    expect(within(card).getByText(/Older single product column/)).toBeInTheDocument();
    const mapProduct = within(card).getByTestId('cst-map-sigOLD-map-Artikel Nr');
    await user.click(mapProduct);
    await user.click(await screen.findByRole('option', { name: /^Part number/, hidden: true }));
    await waitFor(() => expect(screen.getByTestId('cst-bulk-upload-submit')).toBeEnabled());

    await user.click(screen.getByTestId('cst-bulk-upload-submit'));
    await waitFor(() => expect(onJobsCreated).toHaveBeenCalledWith([57]));
    const fd = apiPostMock.mock.calls[1][1] as FormData;
    expect(JSON.parse(String(fd.get('layouts')))).toEqual([
      {
        signature: 'sigOLD',
        layout_id: 7,
        name: 'Weekly report',
        field_mapping: { 'Artikel Nr': 'raw_part_number_token', Stuks: 'units_sold' },
      },
    ]);
  });

  it('does not send a re-map unless the uploader asks for one', async () => {
    apiPostMock.mockImplementation(async (path: string) => {
      if (path.endsWith('/batch-propose')) {
        return {
          group_count: 1,
          file_count: 1,
          customer_id: 20,
          targets: TARGETS,
          files: [
            {
              filename: 'week 1.csv',
              readable: true,
              columns: ['Artikel Nr', 'Stuks'],
              layout_signature: 'sigOLD',
              layout: {
                id: 7,
                name: 'Weekly report',
                legacy_product_slot: true,
                mapping: { 'Artikel Nr': 'raw_product_token', Stuks: 'units_sold' },
              },
              detected_mapping: {},
              samples: {},
            },
          ],
        };
      }
      return { group_count: 1, jobs: [{ outcome: 'created', import_job_id: 58, filenames: ['week 1.csv'] }] };
    });
    const { user, onJobsCreated } = renderDialog();
    await pickCustomer(user, 'Takealot');
    await user.upload(document.querySelector('input[type="file"]') as HTMLInputElement, file());
    await user.click(screen.getByTestId('cst-bulk-preview-groups'));
    await screen.findByTestId('cst-legacy-layout-sigOLD');
    await user.click(screen.getByTestId('cst-bulk-upload-submit'));
    await waitFor(() => expect(onJobsCreated).toHaveBeenCalledWith([58]));
    expect((apiPostMock.mock.calls[1][1] as FormData).has('layouts')).toBe(false);
  });
""",
)

if crlf:
    s = s.replace("\n", "\r\n")
p.write_bytes(s.encode("utf-8"))
print("patched", p)
