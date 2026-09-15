from pathlib import Path

p = Path("apps/web/src/features/promotions-funding/CaseBookSurface.tsx")
text = p.read_text(encoding="utf-8")
start = text.index(
    "      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', md: '2fr 3fr' } }}>"
)
end = text.index("      <ScopeBar", start)
box = text[start:end]
text = text[:start] + text[end:]
marker = "      </ModuleDataSection>\n\n      {toastAction ? ("
insert = (
    "      </ModuleDataSection>\n\n      <PaymentEvidenceOverlayPanel />\n\n"
    + box
    + "      {toastAction ? ("
)
if marker not in text:
    raise SystemExit("marker missing after cut")
text = text.replace(marker, insert, 1)
p.write_text(text, encoding="utf-8")
print(f"moved ageing box ({len(box)} chars) below grid")
