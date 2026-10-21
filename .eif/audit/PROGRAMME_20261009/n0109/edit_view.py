"""N-0109 unit 1: layout, numeric alignment and bar axis edits to ReportBuilderView.tsx."""
import pathlib

p = pathlib.Path(__file__).resolve().parents[4] / 'apps' / 'web' / 'src' / 'features' / 'reports' / 'ReportBuilderView.tsx'
s = p.read_text(encoding='utf-8')


def rep(a, b):
    global s
    assert s.count(a) == 1, a[:80]
    s = s.replace(a, b)


rep("""        <Box sx={{ display: { xs: 'none', md: 'block' }, minWidth: 0 }}>
          <Panel title="Metric\"""", """        <Box sx={{ display: { xs: 'none', md: 'block' }, minWidth: 0, gridColumn: { md: '1' }, gridRow: { md: '1 / span 2' } }}>
          <Panel title="Metric\"""")
rep("""        <Stack spacing={2} sx={{ minWidth: 0 }}>
          <Panel
            title={selected?.label ?? metricLabelOf(metricKey)}""", """        <Stack spacing={2} sx={{ minWidth: 0, gridColumn: { md: '2' }, gridRow: { md: '1' } }}>
          <Panel
            title={selected?.label ?? metricLabelOf(metricKey)}""")
rep("""          </Panel>

          {result?.ok && effectiveVisual !== 'table' && table && table.rows.length > 0 ? (
            <Panel title="Result" subtitle="The same numbers as the chart, row by row" flush sx={{ height: 'auto' }}>
              <ResultGrid table={table} />
            </Panel>
          ) : null}
        </Stack>

        {/* ---------- saved reports + recent runs ---------- */}
        <Stack spacing={2} sx={{ minWidth: 0, gridColumn: { md: '1 / -1', lg: 'auto' } }}>""", """          </Panel>
        </Stack>

        {/* ---------- result table: spans the question and side columns on wide screens ---------- */}
        {result?.ok && !runMut.isPending && table && table.rows.length > 0 ? (
          <Box
            sx={{ minWidth: 0, gridColumn: { md: '2', lg: '2 / -1' }, gridRow: { md: '2' } }}
            data-testid={effectiveVisual === 'table' ? 'report-table' : undefined}
          >
            <Panel
              title="Result"
              subtitle={
                effectiveVisual === 'table'
                  ? `Row by row · ${table.rows.length} ${table.rows.length === 1 ? 'row' : 'rows'}`
                  : 'The same numbers as the chart, row by row'
              }
              flush
              sx={{ height: 'auto' }}
            >
              <ResultGrid table={table} />
            </Panel>
          </Box>
        ) : null}

        {/* ---------- saved reports + recent runs ---------- */}
        <Stack spacing={2} sx={{ minWidth: 0, gridColumn: { md: '1 / -1', lg: '3' }, gridRow: { md: '3', lg: '1' } }}>""")
rep("""  if (visual === 'table') {
    return table && table.rows.length ? (
      <Box data-testid="report-table">
        <ResultGrid table={table} />
      </Box>
    ) : (""", """  if (visual === 'table') {
    return table && table.rows.length ? (
      <Typography variant="body2" color="text.secondary">
        Shown as a table below.
      </Typography>
    ) : (""")
rep("""const NUMERIC_CELL: CellStyle = { fontVariantNumeric: 'tabular-nums' };""", """// The shared grid lays cells out with flex, so right alignment needs justify-content, not text-align.
const NUMERIC_CELL: CellStyle = { fontVariantNumeric: 'tabular-nums', justifyContent: 'flex-end' };""")
rep("""        format={unitFormat}
        summary={`Horizontal bar chart""", """        format={unitFormat}
        axisFormat={(v) => unitFormat(v).replace(/\\.0(?=\\D*$)/, '')}
        summary={`Horizontal bar chart""")
p.write_text(s, encoding='utf-8')
print('ok')
