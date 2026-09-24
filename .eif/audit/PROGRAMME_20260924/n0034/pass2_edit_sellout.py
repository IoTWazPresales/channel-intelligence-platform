import pathlib
p = pathlib.Path("apps/web/src/app/(app)/sell-out/SellOutTab.tsx")
s = p.read_text(encoding="utf-8")
def rep(old, new):
    global s
    assert s.count(old) == 1, old[:60]
    s = s.replace(old, new)
rep("""type ChannelSelloutLine = {
  date: string;
  distributor_name: string | null;
  customer_name: string | null;""", """type ChannelSelloutLine = {
  date: string;
  distributor_name: string | null;
  distributor_code?: string | null;
  customer_name: string | null;
  customer_code?: string | null;""")
rep("""  const factColumns = useFactColumns<SelloutLine>('sellout.commercial-lines');
""", """  const factColumns = useFactColumns<SelloutLine>('sellout.commercial-lines');
  const channelColumns = useFactColumns<ChannelSelloutLine>('channel-ops.sell-out');
""")
rep("""        },
      );
    }
    return cols;
  }, [operational, lineId]);""", """        },
      );
    }
    return [...cols, ...channelColumns.optionalColDefs];
  }, [operational, lineId, channelColumns.optionalColDefs]);""")
rep("""              toolbar={
                useChannelApi ? undefined : (
                  <Stack direction="row" sx={{ mb: 1 }}>
                    <FactColumnsButton
                      gridId="sellout.commercial-lines"
                      onClick={factColumns.openPicker}
                      count={factColumns.optionalFields.length}
                    />
                  </Stack>
                )
              }""", """              toolbar={
                <Stack direction="row" sx={{ mb: 1 }}>
                  {useChannelApi ? (
                    <FactColumnsButton
                      gridId="channel-ops.sell-out"
                      onClick={channelColumns.openPicker}
                      count={channelColumns.optionalFields.length}
                    />
                  ) : (
                    <FactColumnsButton
                      gridId="sellout.commercial-lines"
                      onClick={factColumns.openPicker}
                      count={factColumns.optionalFields.length}
                    />
                  )}
                </Stack>
              }""")
rep("""      <FactColumnPicker {...factColumns.pickerProps} />
""", """      <FactColumnPicker {...factColumns.pickerProps} />
      <FactColumnPicker {...channelColumns.pickerProps} />
""")
p.write_text(s, encoding="utf-8")
print("ok")
