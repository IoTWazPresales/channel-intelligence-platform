import pathlib
p = pathlib.Path("apps/web/src/app/(app)/admin/customer-commercial-terms/page.tsx")
s = p.read_text(encoding="utf-8")
def rep(old, new):
    global s
    assert s.count(old) == 1, old[:60]
    s = s.replace(old, new)
rep("""import { EntitySearchAutocomplete } from '@/features/commercial-planner/EntitySearchAutocomplete';
""", """import { EntitySearchAutocomplete } from '@/features/commercial-planner/EntitySearchAutocomplete';
import { FactColumnPicker, FactColumnsButton } from '@/features/workbench-ui/FactColumnPicker';
import { useFactColumns } from '@/features/workbench-ui/useFactColumns';
""")
rep("""  customer_rebate_pct: number;
};

type CustomerPick""", """  customer_rebate_pct: number;
  target_cover_weeks?: number | null;
};

type CustomerPick""")
rep("""  const [rebate, setRebate] = useState('0.03');
""", """  const [rebate, setRebate] = useState('0.03');
  const factColumns = useFactColumns<CustomerTermRow>('customer-terms');
""")
rep("""      {
        headerName: '',
        width: 100,
        sortable: false,""", """      ...factColumns.optionalColDefs,
      {
        headerName: '',
        width: 100,
        sortable: false,""")
rep("""          ) : null,
      },
    ],
    [],
  );""", """          ) : null,
      },
    ],
    // openEdit only calls state setters, so it is stable enough for the grid's cell renderer.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [factColumns.optionalColDefs],
  );""")
rep("""        <Box sx={{ flex: 1 }} />
        <Button
          component={NextLink}""", """        <Box sx={{ flex: 1 }} />
        <FactColumnsButton
          gridId="customer-terms"
          onClick={factColumns.openPicker}
          count={factColumns.optionalFields.length}
        />
        <Button
          component={NextLink}""")
rep("""      </ModuleDataSection>

      <Dialog""", """      </ModuleDataSection>
      <FactColumnPicker {...factColumns.pickerProps} />

      <Dialog""")
p.write_text(s, encoding="utf-8")
print("ok")
